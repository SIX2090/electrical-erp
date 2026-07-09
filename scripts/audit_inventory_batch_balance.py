from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


DIMENSIONS = (
    "product_id",
    "warehouse_id",
    "location_id",
    "lot_no",
    "serial_no",
    "project_code",
)
REQUIRED_COLUMNS = {
    "batch_tracking": (*DIMENSIONS, "quantity_available"),
    "inventory_balances": (*DIMENSIONS, "quantity"),
}
DIFF_LIMIT = 200


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def missing_schema_items(cur):
    missing = []
    for table_name, columns in REQUIRED_COLUMNS.items():
        cur.execute("SELECT to_regclass(%s) AS table_ref", (table_name,))
        if not (cur.fetchone() or {}).get("table_ref"):
            missing.append(f"missing_table:{table_name}")
            continue

        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            """,
            (table_name,),
        )
        existing = {row["column_name"] for row in cur.fetchall()}
        for column in columns:
            if column not in existing:
                missing.append(f"missing_column:{table_name}.{column}")
    return missing


def fetch_summary(cur):
    cur.execute("SELECT COUNT(*) AS rows, COALESCE(SUM(quantity_available), 0) AS qty FROM batch_tracking")
    batch = cur.fetchone() or {}
    cur.execute("SELECT COUNT(*) AS rows, COALESCE(SUM(quantity), 0) AS qty FROM inventory_balances")
    balance = cur.fetchone() or {}
    return batch, balance


def fetch_differences(cur):
    cur.execute(
        """
        WITH batch AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity_available, 0)) AS batch_qty
            FROM batch_tracking
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        ),
        balance AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity, 0)) AS balance_qty
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT COALESCE(batch.product_id, balance.product_id) AS product_id,
               COALESCE(batch.warehouse_id, balance.warehouse_id) AS warehouse_id,
               COALESCE(batch.location_id, balance.location_id) AS location_id,
               COALESCE(batch.lot_no, balance.lot_no) AS lot_no,
               COALESCE(batch.serial_no, balance.serial_no) AS serial_no,
               COALESCE(batch.project_code, balance.project_code) AS project_code,
               COALESCE(batch.batch_qty, 0) AS batch_qty,
               COALESCE(balance.balance_qty, 0) AS balance_qty,
               COALESCE(batch.batch_qty, 0) - COALESCE(balance.balance_qty, 0) AS diff_qty
        FROM batch
        FULL OUTER JOIN balance
          ON batch.product_id IS NOT DISTINCT FROM balance.product_id
         AND batch.warehouse_id=balance.warehouse_id
         AND batch.location_id=balance.location_id
         AND batch.lot_no=balance.lot_no
         AND batch.serial_no=balance.serial_no
         AND batch.project_code=balance.project_code
        WHERE COALESCE(batch.batch_qty, 0) <> COALESCE(balance.balance_qty, 0)
        ORDER BY ABS(COALESCE(batch.batch_qty, 0) - COALESCE(balance.balance_qty, 0)) DESC,
                 product_id, warehouse_id, location_id, lot_no, serial_no, project_code
        LIMIT %s
        """,
        (DIFF_LIMIT,),
    )
    return cur.fetchall()


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            missing = missing_schema_items(cur)
            if missing:
                print("inventory_batch_balance_audit=failed")
                for item in missing:
                    print(f"failed | {item}")
                return 1

            batch, balance = fetch_summary(cur)
            differences = fetch_differences(cur)
    finally:
        conn.close()

    print("inventory_batch_balance_audit=ok" if not differences else "inventory_batch_balance_audit=failed")
    print(f"batch_tracking_rows={batch.get('rows', 0)}")
    print(f"batch_tracking_quantity_available={batch.get('qty', 0)}")
    print(f"inventory_balances_rows={balance.get('rows', 0)}")
    print(f"inventory_balances_quantity={balance.get('qty', 0)}")
    print(f"difference_rows={len(differences)}")
    for row in differences:
        keys = " | ".join(f"{key}={row.get(key)!r}" for key in DIMENSIONS)
        print(
            "failed | "
            f"{keys} | batch_qty={row.get('batch_qty')} | "
            f"balance_qty={row.get('balance_qty')} | diff_qty={row.get('diff_qty')}"
        )
    if len(differences) == DIFF_LIMIT:
        print(f"warning | output limited to first {DIFF_LIMIT} differences")
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
