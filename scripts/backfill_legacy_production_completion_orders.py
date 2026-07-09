from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


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
            "Create read-only formal production completion order wrappers for legacy "
            "wo_complete_items rows. The script does not post inventory again."
        )
    )
    parser.add_argument("--apply", action="store_true", help="insert missing formal wrapper documents")
    parser.add_argument("--limit", type=int, default=20, help="sample rows to print in dry run")
    return parser.parse_args()


def ensure_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS production_completion_orders (
            id SERIAL PRIMARY KEY,
            completion_no VARCHAR(120) UNIQUE NOT NULL,
            completion_date DATE NOT NULL DEFAULT CURRENT_DATE,
            work_order_id INTEGER,
            product_id INTEGER,
            quantity NUMERIC(14,4) DEFAULT 0,
            failed_quantity NUMERIC(14,4) DEFAULT 0,
            unit_cost NUMERIC(14,4) DEFAULT 0,
            warehouse_id INTEGER,
            location_id INTEGER,
            lot_no VARCHAR(120),
            serial_no VARCHAR(120),
            project_code VARCHAR(120),
            status VARCHAR(40) DEFAULT '已过账',
            remark TEXT,
            posted_at TIMESTAMP,
            wo_complete_item_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for statement in (
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS completion_no VARCHAR(120)",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS completion_date DATE DEFAULT CURRENT_DATE",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS work_order_id INTEGER",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS product_id INTEGER",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS quantity NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS failed_quantity NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS location_id INTEGER",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120)",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120)",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS project_code VARCHAR(120)",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT '已过账'",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS remark TEXT",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS wo_complete_item_id INTEGER",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_production_completion_no ON production_completion_orders(completion_no)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_production_completion_legacy_item ON production_completion_orders(wo_complete_item_id) WHERE wo_complete_item_id IS NOT NULL",
    ):
        cur.execute(statement)


def fetch_missing(cur, limit):
    cur.execute(
        """
        SELECT COUNT(*) AS value
        FROM wo_complete_items wc
        WHERE NOT EXISTS (
            SELECT 1
            FROM production_completion_orders pc
            WHERE pc.wo_complete_item_id=wc.id
        )
        """
    )
    count = int((cur.fetchone() or {}).get("value") or 0)
    cur.execute(
        """
        SELECT wc.id, wo.wo_no, wc.wo_id, wc.product_id, wc.qty, wc.complete_date,
               wo.project_code, wo.serial_no, wo.warehouse_id
        FROM wo_complete_items wc
        LEFT JOIN work_orders wo ON wo.id=wc.wo_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM production_completion_orders pc
            WHERE pc.wo_complete_item_id=wc.id
        )
        ORDER BY wc.id
        LIMIT %s
        """,
        (limit,),
    )
    return count, cur.fetchall()


def insert_missing(cur):
    cur.execute(
        """
        INSERT INTO production_completion_orders
            (completion_no, completion_date, work_order_id, product_id, quantity, failed_quantity,
             unit_cost, warehouse_id, location_id, lot_no, serial_no, project_code, status, remark,
             posted_at, wo_complete_item_id, created_at, updated_at)
        SELECT
            'PC-HIST-' || wc.id::text,
            COALESCE(wc.complete_date::date, CURRENT_DATE),
            wc.wo_id,
            wc.product_id,
            COALESCE(wc.qty,0),
            0,
            COALESCE(wc.unit_cost,0),
            wo.warehouse_id,
            NULL,
            NULL,
            wo.serial_no,
            wo.project_code,
            '已过账',
            '历史完工关联单；库存已由历史完工记录产生，本脚本不重复过账。',
            COALESCE(wc.complete_date::timestamp, NOW()),
            wc.id,
            NOW(),
            NOW()
        FROM wo_complete_items wc
        LEFT JOIN work_orders wo ON wo.id=wc.wo_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM production_completion_orders pc
            WHERE pc.wo_complete_item_id=wc.id
        )
          AND NOT EXISTS (
              SELECT 1
              FROM production_completion_orders pc
              WHERE pc.completion_no='PC-HIST-' || wc.id::text
          )
        """
    )
    return cur.rowcount


def main():
    args = parse_args()
    os.environ.setdefault("PG_PASSWORD", "admin")
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            ensure_schema(cur)
            missing, rows = fetch_missing(cur, args.limit)
            print("legacy_completion_backfill=ready" if args.apply else "legacy_completion_backfill=dry_run")
            print(f"legacy_completion_without_formal_doc={missing}")
            for row in rows:
                print(" | ".join(f"{key}={row.get(key)!r}" for key in row.keys()))
            if not args.apply:
                conn.rollback()
                return 1 if missing else 0
            inserted = insert_missing(cur)
            conn.commit()
            print(f"inserted_formal_completion_orders={inserted}")
            return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
