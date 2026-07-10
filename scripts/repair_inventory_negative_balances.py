from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


AUDIT_TABLE = "inventory_negative_balance_repair_audit"


def db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Zero negative inventory_balances rows after backing them up. "
            "This is intended for pilot/test data cleanup before reconciling derived tables."
        )
    )
    parser.add_argument("--apply", action="store_true", help="write audit rows and set negative balances to zero")
    parser.add_argument("--limit", type=int, default=20, help="sample rows to print")
    return parser.parse_args()


def ensure_audit_table(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL,
            inventory_balance_id INTEGER NOT NULL,
            before_data JSONB NOT NULL,
            repair_action TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def fetch_summary(cur, limit):
    cur.execute(
        """
        SELECT COUNT(*) AS rows, COALESCE(SUM(quantity),0) AS negative_qty
        FROM inventory_balances
        WHERE COALESCE(quantity,0) < 0
        """
    )
    summary = cur.fetchone() or {}
    cur.execute(
        """
        SELECT ib.id, ib.product_id, p.code AS product_code, p.name AS product_name,
               ib.warehouse_id, ib.location_id, ib.lot_no, ib.cabinet_no, ib.project_code,
               ib.quantity, ib.unit_cost
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        WHERE COALESCE(ib.quantity,0) < 0
        ORDER BY ib.quantity ASC, ib.id
        LIMIT %s
        """,
        (limit,),
    )
    return summary, cur.fetchall()


def apply_repair(conn, cur):
    run_id = f"inventory_negative_balance_repair:{os.getpid()}"
    ensure_audit_table(cur)
    cur.execute(
        f"""
        INSERT INTO {AUDIT_TABLE} (run_id, inventory_balance_id, before_data, repair_action)
        SELECT %s, ib.id, to_jsonb(ib), 'set_quantity_to_zero'
        FROM inventory_balances ib
        WHERE COALESCE(ib.quantity,0) < 0
        """,
        (run_id,),
    )
    backup_rows = cur.rowcount
    cur.execute(
        """
        UPDATE inventory_balances
        SET quantity=0,
            updated_at=NOW()
        WHERE COALESCE(quantity,0) < 0
        """
    )
    updated_rows = cur.rowcount
    conn.commit()
    print("inventory_negative_balance_repair=applied")
    print(f"audit_table={AUDIT_TABLE}")
    print(f"audit_run_id={run_id}")
    print(f"backup_rows={backup_rows}")
    print(f"updated_rows={updated_rows}")


def main():
    args = parse_args()
    os.environ.setdefault("PG_PASSWORD", "admin")
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            summary, rows = fetch_summary(cur, args.limit)
            print("inventory_negative_balance_repair=ready" if args.apply else "inventory_negative_balance_repair=dry_run")
            print(f"negative_balance_rows={summary.get('rows', 0)}")
            print(f"negative_balance_qty={summary.get('negative_qty', 0)}")
            for row in rows:
                print(" | ".join(f"{key}={row.get(key)!r}" for key in row.keys()))
            if not args.apply:
                conn.rollback()
                return 1 if int(summary.get("rows") or 0) else 0
            apply_repair(conn, cur)
            return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
