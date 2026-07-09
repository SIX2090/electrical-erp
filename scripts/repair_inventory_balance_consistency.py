from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


LEGACY_DIFF_LIMIT = 200
BATCH_DIFF_LIMIT = 200
AUDIT_TABLE = "inventory_balance_repair_audit"
QTY_TOLERANCE = "0.0001"
COST_TOLERANCE = "0.0001"

DIMENSIONS = (
    "product_id",
    "warehouse_id",
    "location_id",
    "lot_no",
    "serial_no",
    "project_code",
)

REQUIRED_COLUMNS = {
    "inventory": ("id", "product_id", "quantity", "unit_cost", "location", "reorder_level"),
    "inventory_balances": (*DIMENSIONS, "quantity", "unit_cost"),
    "batch_tracking": (
        "id",
        *DIMENSIONS,
        "quantity_available",
        "quantity_in",
        "quantity_out",
        "unit_cost",
        "source_order_no",
        "status",
        "created_at",
        "updated_at",
    ),
    "stock_transactions": (
        "id",
        "transaction_date",
        "transaction_type",
        "product_id",
        "quantity",
        "unit_cost",
        "reference_no",
        "lot_no",
        "serial_no",
        "warehouse_id",
        "location_id",
        "project_code",
        "source_type",
        "amount",
        "remark",
    ),
}


def get_db_config():
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
            "Reconcile derived legacy inventory and batch_tracking balances from "
            "inventory_balances. Defaults to dry-run and prints suggested SQL."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit dry-run mode; this is the default unless --apply is supplied",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="execute the repair after writing affected current rows to an audit backup table",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="maximum difference rows to print per section in dry-run output",
    )
    return parser.parse_args()


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


def fetch_legacy_summary(cur):
    cur.execute(
        """
        WITH desired AS (
            SELECT
                product_id,
                COALESCE(SUM(quantity),0) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id
        ),
        legacy AS (
            SELECT
                product_id,
                COALESCE(SUM(quantity),0) AS legacy_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS legacy_unit_cost,
                COUNT(*) AS legacy_rows
            FROM inventory
            GROUP BY product_id
        )
        SELECT
            COALESCE(d.product_id, l.product_id) AS product_id,
            COALESCE(l.legacy_qty,0) AS legacy_qty,
            COALESCE(d.balance_qty,0) AS balance_qty,
            COALESCE(l.legacy_qty,0) - COALESCE(d.balance_qty,0) AS qty_diff,
            COALESCE(l.legacy_unit_cost,0) AS legacy_unit_cost,
            COALESCE(d.balance_unit_cost,0) AS balance_unit_cost,
            COALESCE(l.legacy_rows,0) AS legacy_rows,
            CASE
                WHEN l.product_id IS NULL THEN 'insert_legacy_inventory'
                WHEN d.product_id IS NULL THEN 'zero_legacy_inventory'
                ELSE 'update_legacy_inventory'
            END AS repair_action
        FROM desired d
        FULL OUTER JOIN legacy l ON l.product_id=d.product_id
        WHERE COALESCE(l.legacy_qty,0) <> COALESCE(d.balance_qty,0)
           OR ABS(COALESCE(l.legacy_unit_cost,0) - COALESCE(d.balance_unit_cost,0)) > %s
           OR COALESCE(l.legacy_rows,0) > 1
        ORDER BY ABS(COALESCE(l.legacy_qty,0) - COALESCE(d.balance_qty,0)) DESC,
                 COALESCE(d.product_id, l.product_id)
        LIMIT %s
        """,
        (COST_TOLERANCE, LEGACY_DIFF_LIMIT),
    )
    rows = cur.fetchall()
    cur.execute(
        """
        WITH desired AS (
            SELECT
                product_id,
                COALESCE(SUM(quantity),0) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id
        ),
        legacy AS (
            SELECT
                product_id,
                COALESCE(SUM(quantity),0) AS legacy_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS legacy_unit_cost,
                COUNT(*) AS legacy_rows
            FROM inventory
            GROUP BY product_id
        )
        SELECT COUNT(*) AS mismatch_products
        FROM desired d
        FULL OUTER JOIN legacy l ON l.product_id=d.product_id
        WHERE COALESCE(l.legacy_qty,0) <> COALESCE(d.balance_qty,0)
           OR ABS(COALESCE(l.legacy_unit_cost,0) - COALESCE(d.balance_unit_cost,0)) > %s
           OR COALESCE(l.legacy_rows,0) > 1
        """
        ,
        (COST_TOLERANCE,),
    )
    summary = cur.fetchone() or {}
    return int(summary.get("mismatch_products") or 0), rows


def fetch_batch_summary(cur):
    cur.execute(
        """
        WITH desired AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity, 0)) AS balance_qty,
                   CASE WHEN COALESCE(SUM(quantity),0) <> 0
                       THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                       ELSE COALESCE(MAX(unit_cost),0)
                   END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        ),
        batch AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity_available, 0)) AS batch_qty,
                   COUNT(*) AS batch_rows
            FROM batch_tracking
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT COALESCE(d.product_id, b.product_id) AS product_id,
               COALESCE(d.warehouse_id, b.warehouse_id) AS warehouse_id,
               COALESCE(d.location_id, b.location_id) AS location_id,
               COALESCE(d.lot_no, b.lot_no) AS lot_no,
               COALESCE(d.serial_no, b.serial_no) AS serial_no,
               COALESCE(d.project_code, b.project_code) AS project_code,
               COALESCE(b.batch_qty, 0) AS batch_qty,
               COALESCE(d.balance_qty, 0) AS balance_qty,
               COALESCE(b.batch_qty, 0) - COALESCE(d.balance_qty, 0) AS qty_diff,
               COALESCE(d.balance_unit_cost, 0) AS balance_unit_cost,
               COALESCE(b.batch_rows, 0) AS batch_rows,
               CASE
                   WHEN b.product_id IS NULL THEN 'insert_batch_tracking'
                   WHEN d.product_id IS NULL THEN 'zero_batch_tracking'
                   ELSE 'update_batch_tracking'
               END AS repair_action
        FROM desired d
        FULL OUTER JOIN batch b
          ON b.product_id IS NOT DISTINCT FROM d.product_id
         AND b.warehouse_id=d.warehouse_id
         AND b.location_id=d.location_id
         AND b.lot_no=d.lot_no
         AND b.serial_no=d.serial_no
         AND b.project_code=d.project_code
        WHERE COALESCE(b.batch_qty, 0) <> COALESCE(d.balance_qty, 0)
           OR COALESCE(b.batch_rows, 0) > 1
        ORDER BY ABS(COALESCE(b.batch_qty, 0) - COALESCE(d.balance_qty, 0)) DESC,
                 product_id, warehouse_id, location_id, lot_no, serial_no, project_code
        LIMIT %s
        """,
        (BATCH_DIFF_LIMIT,),
    )
    rows = cur.fetchall()
    cur.execute(
        """
        WITH desired AS (
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
        ),
        batch AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity_available, 0)) AS batch_qty,
                   COUNT(*) AS batch_rows
            FROM batch_tracking
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT COUNT(*) AS mismatch_dimensions
        FROM desired d
        FULL OUTER JOIN batch b
          ON b.product_id IS NOT DISTINCT FROM d.product_id
         AND b.warehouse_id=d.warehouse_id
         AND b.location_id=d.location_id
         AND b.lot_no=d.lot_no
         AND b.serial_no=d.serial_no
         AND b.project_code=d.project_code
        WHERE COALESCE(b.batch_qty, 0) <> COALESCE(d.balance_qty, 0)
           OR COALESCE(b.batch_rows, 0) > 1
        """
    )
    summary = cur.fetchone() or {}
    return int(summary.get("mismatch_dimensions") or 0), rows


def fetch_stock_transaction_summary(cur):
    cur.execute(
        """
        WITH tx AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(serial_no, '') AS serial_no,
                COALESCE(project_code, '') AS project_code,
                SUM(
                    CASE
                        WHEN COALESCE(transaction_type,'') IN (
                            'sales_outbound', 'outbound', 'issue', 'shipment',
                            'subcontract_issue', 'quality_hold_transfer_out',
                            '售后备件出库', '手工出库', '调拨出库', '销售出库',
                            '工单领料', '工单补料', '生产领料', '组装领料', '拆卸出库'
                        ) THEN -ABS(COALESCE(quantity,0))
                        ELSE COALESCE(quantity,0)
                    END
                ) AS stock_transaction_qty
            FROM stock_transactions
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        ),
        balance AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(serial_no, '') AS serial_no,
                COALESCE(project_code, '') AS project_code,
                SUM(COALESCE(quantity, 0)) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT COALESCE(tx.product_id, balance.product_id) AS product_id,
               COALESCE(tx.warehouse_id, balance.warehouse_id) AS warehouse_id,
               COALESCE(tx.location_id, balance.location_id) AS location_id,
               COALESCE(tx.lot_no, balance.lot_no) AS lot_no,
               COALESCE(tx.serial_no, balance.serial_no) AS serial_no,
               COALESCE(tx.project_code, balance.project_code) AS project_code,
               COALESCE(tx.stock_transaction_qty, 0) AS stock_transaction_qty,
               COALESCE(balance.balance_qty, 0) AS balance_qty,
               COALESCE(balance.balance_qty, 0) - COALESCE(tx.stock_transaction_qty, 0) AS adjustment_qty,
               COALESCE(balance.balance_unit_cost, 0) AS balance_unit_cost,
               'insert_stock_transaction_adjustment' AS repair_action
        FROM tx
        FULL OUTER JOIN balance
          ON tx.product_id IS NOT DISTINCT FROM balance.product_id
         AND tx.warehouse_id=balance.warehouse_id
         AND tx.location_id=balance.location_id
         AND tx.lot_no=balance.lot_no
         AND tx.serial_no=balance.serial_no
         AND tx.project_code=balance.project_code
        WHERE ABS(COALESCE(tx.stock_transaction_qty, 0) - COALESCE(balance.balance_qty, 0)) > %s
        ORDER BY ABS(COALESCE(tx.stock_transaction_qty, 0) - COALESCE(balance.balance_qty, 0)) DESC,
                 product_id, warehouse_id, location_id, lot_no, serial_no, project_code
        LIMIT %s
        """,
        (QTY_TOLERANCE, LEGACY_DIFF_LIMIT),
    )
    rows = cur.fetchall()
    cur.execute(
        """
        WITH tx AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(serial_no, '') AS serial_no,
                COALESCE(project_code, '') AS project_code,
                SUM(
                    CASE
                        WHEN COALESCE(transaction_type,'') IN (
                            'sales_outbound', 'outbound', 'issue', 'shipment',
                            'subcontract_issue', 'quality_hold_transfer_out',
                            '售后备件出库', '手工出库', '调拨出库', '销售出库',
                            '工单领料', '工单补料', '生产领料', '组装领料', '拆卸出库'
                        ) THEN -ABS(COALESCE(quantity,0))
                        ELSE COALESCE(quantity,0)
                    END
                ) AS stock_transaction_qty
            FROM stock_transactions
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
        SELECT COUNT(*) AS mismatch_dimensions
        FROM tx
        FULL OUTER JOIN balance
          ON tx.product_id IS NOT DISTINCT FROM balance.product_id
         AND tx.warehouse_id=balance.warehouse_id
         AND tx.location_id=balance.location_id
         AND tx.lot_no=balance.lot_no
         AND tx.serial_no=balance.serial_no
         AND tx.project_code=balance.project_code
        WHERE ABS(COALESCE(tx.stock_transaction_qty, 0) - COALESCE(balance.balance_qty, 0)) > %s
        """,
        (QTY_TOLERANCE,),
    )
    summary = cur.fetchone() or {}
    return int(summary.get("mismatch_dimensions") or 0), rows


def print_rows(title, rows, limit):
    print(title)
    for row in rows[:limit]:
        print(" | ".join(f"{key}={row.get(key)!r}" for key in row.keys()))
    if len(rows) > limit:
        print(f"warning | output limited to first {limit} rows")


def print_suggested_sql():
    print("suggested_sql_begin")
    suggested_sql = f"""
-- Dry-run only. Review the difference summary before running with --apply.
-- The apply path first writes affected current rows to {AUDIT_TABLE}; it does not modify
-- stock_transactions or other business history documents.

CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_id INTEGER,
    action TEXT NOT NULL,
    before_data JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Legacy inventory is treated as a product-level derived summary from inventory_balances:
-- update one canonical inventory row per product, zero duplicate derived rows, insert missing rows.

-- batch_tracking is treated as a lot/serial derived balance from inventory_balances:
-- update quantity_available on one canonical batch row, zero duplicate/current orphan rows,
-- and insert missing lot/serial dimensions only.

-- stock_transactions are business history. The repair does not rewrite existing rows; it
-- appends inventory_balance_reconciliation adjustment rows for dimensions whose normalized
-- ledger effect does not reconcile to inventory_balances.
"""
    print(suggested_sql.strip())
    print("suggested_sql_end")


def ensure_audit_table(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_id INTEGER,
            action TEXT NOT NULL,
            before_data JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def backup_legacy_inventory(cur, run_id):
    cur.execute(
        f"""
        WITH desired AS (
            SELECT product_id
            FROM inventory_balances
            GROUP BY product_id
        ),
        legacy AS (
            SELECT product_id
            FROM inventory
            GROUP BY product_id
        ),
        affected_products AS (
            SELECT product_id FROM desired
            UNION
            SELECT product_id FROM legacy
        )
        INSERT INTO {AUDIT_TABLE} (run_id, table_name, row_id, action, before_data)
        SELECT %s, 'inventory', i.id, 'before_repair', to_jsonb(i)
        FROM inventory i
        JOIN affected_products ap ON ap.product_id=i.product_id
        """,
        (run_id,),
    )
    return cur.rowcount


def backup_batch_tracking(cur, run_id):
    cur.execute(
        f"""
        WITH desired AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        ),
        batch AS (
            SELECT id, product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code
            FROM batch_tracking
        ),
        affected_batch_ids AS (
            SELECT b.id
            FROM batch b
            LEFT JOIN desired d
              ON b.product_id IS NOT DISTINCT FROM d.product_id
             AND b.warehouse_id=d.warehouse_id
             AND b.location_id=d.location_id
             AND b.lot_no=d.lot_no
             AND b.serial_no=d.serial_no
             AND b.project_code=d.project_code
            WHERE d.product_id IS NOT NULL OR b.product_id IS NOT NULL
        )
        INSERT INTO {AUDIT_TABLE} (run_id, table_name, row_id, action, before_data)
        SELECT %s, 'batch_tracking', bt.id, 'before_repair', to_jsonb(bt)
        FROM batch_tracking bt
        JOIN affected_batch_ids a ON a.id=bt.id
        """,
        (run_id,),
    )
    return cur.rowcount


def repair_legacy_inventory(cur):
    cur.execute(
        """
        WITH desired AS (
            SELECT
                product_id,
                COALESCE(SUM(quantity),0) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id
        ),
        ranked AS (
            SELECT id, product_id, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY id) AS rn
            FROM inventory
        ),
        updated_main AS (
            UPDATE inventory i
            SET quantity=COALESCE(d.balance_qty,0),
                unit_cost=COALESCE(d.balance_unit_cost,0)
            FROM ranked r
            LEFT JOIN desired d ON d.product_id=r.product_id
            WHERE i.id=r.id AND r.rn=1
            RETURNING i.id
        ),
        zeroed_duplicates AS (
            UPDATE inventory i
            SET quantity=0
            FROM ranked r
            WHERE i.id=r.id AND r.rn > 1
            RETURNING i.id
        )
        INSERT INTO inventory (product_id, quantity, unit_cost, location, reorder_level)
        SELECT d.product_id, d.balance_qty, d.balance_unit_cost, '', 0
        FROM desired d
        LEFT JOIN ranked r ON r.product_id=d.product_id
        WHERE r.product_id IS NULL
        """
    )
    inserted = cur.rowcount
    cur.execute(
        """
        SELECT COUNT(*) AS rows
        FROM inventory i
        JOIN (
            SELECT product_id
            FROM inventory_balances
            GROUP BY product_id
        ) d ON d.product_id=i.product_id
        """
    )
    return inserted


def repair_batch_tracking(cur):
    cur.execute(
        """
        WITH desired AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity, 0)) AS balance_qty,
                   CASE WHEN COALESCE(SUM(quantity),0) <> 0
                       THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                       ELSE COALESCE(MAX(unit_cost),0)
                   END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        ),
        ranked AS (
            SELECT id, product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(serial_no, '') AS serial_no,
                   COALESCE(project_code, '') AS project_code,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                                    COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
                       ORDER BY id
                   ) AS rn
            FROM batch_tracking
        ),
        updated_main AS (
            UPDATE batch_tracking bt
            SET quantity_available=COALESCE(d.balance_qty,0),
                unit_cost=COALESCE(d.balance_unit_cost, bt.unit_cost, 0),
                updated_at=NOW()
            FROM ranked r
            LEFT JOIN desired d
              ON d.product_id IS NOT DISTINCT FROM r.product_id
             AND d.warehouse_id=r.warehouse_id
             AND d.location_id=r.location_id
             AND d.lot_no=r.lot_no
             AND d.serial_no=r.serial_no
             AND d.project_code=r.project_code
            WHERE bt.id=r.id AND r.rn=1
            RETURNING bt.id
        ),
        zeroed_duplicates AS (
            UPDATE batch_tracking bt
            SET quantity_available=0,
                updated_at=NOW()
            FROM ranked r
            WHERE bt.id=r.id AND r.rn > 1
            RETURNING bt.id
        )
        INSERT INTO batch_tracking
            (lot_no, product_id, warehouse_id, location_id, serial_no, project_code,
             quantity_in, quantity_out, quantity_available, unit_cost, source_order_no,
             status, created_at, updated_at)
        SELECT COALESCE(d.lot_no, ''),
               d.product_id, NULLIF(d.warehouse_id, 0), NULLIF(d.location_id, 0),
               NULLIF(d.serial_no, ''), NULLIF(d.project_code, ''),
               CASE WHEN d.balance_qty > 0 THEN d.balance_qty ELSE 0 END,
               CASE WHEN d.balance_qty < 0 THEN -d.balance_qty ELSE 0 END,
               d.balance_qty, d.balance_unit_cost, 'repair_inventory_balance_consistency',
               'derived', NOW(), NOW()
        FROM desired d
        LEFT JOIN ranked r
          ON r.product_id IS NOT DISTINCT FROM d.product_id
         AND r.warehouse_id=d.warehouse_id
         AND r.location_id=d.location_id
         AND r.lot_no=d.lot_no
         AND r.serial_no=d.serial_no
         AND r.project_code=d.project_code
        WHERE r.product_id IS NULL
        """
    )
    return cur.rowcount


def repair_stock_transactions(cur):
    """Report-only: do NOT insert inventory_balance_reconciliation rows.

    Inserting fake reconciliation rows into stock_transactions was the root
    cause of the recurring inconsistency cycle. Each repair run inserted
    garbage rows that polluted cost calculations and accumulated over time.
    The correct fix is to repair the source code paths (transaction atomicity,
    unified posting entry) rather than patching data with fake transactions.
    """
    cur.execute(
        """
        WITH tx AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(serial_no, '') AS serial_no,
                COALESCE(project_code, '') AS project_code,
                SUM(
                    CASE
                        WHEN COALESCE(transaction_type,'') IN (
                            'sales_outbound', 'outbound', 'issue', 'shipment',
                            'subcontract_issue', 'quality_hold_transfer_out',
                            '售后备件出库', '手工出库', '调拨出库', '销售出库',
                            '工单领料', '工单补料', '生产领料', '组装领料', '拆卸出库'
                        ) THEN -ABS(COALESCE(quantity,0))
                        ELSE COALESCE(quantity,0)
                    END
                ) AS stock_transaction_qty
            FROM stock_transactions
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        ),
        balance AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(serial_no, '') AS serial_no,
                COALESCE(project_code, '') AS project_code,
                SUM(COALESCE(quantity, 0)) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(serial_no, ''), COALESCE(project_code, '')
        )
        SELECT COUNT(*) AS diff_count
        FROM tx
        FULL OUTER JOIN balance
          ON tx.product_id IS NOT DISTINCT FROM balance.product_id
         AND tx.warehouse_id=balance.warehouse_id
         AND tx.location_id=balance.location_id
         AND tx.lot_no=balance.lot_no
         AND tx.serial_no=balance.serial_no
         AND tx.project_code=balance.project_code
        WHERE ABS(COALESCE(tx.stock_transaction_qty, 0) - COALESCE(balance.balance_qty, 0)) > %s
        """,
        (QTY_TOLERANCE,),
    )
    row = cur.fetchone()
    diff_count = next(iter(row.values()), 0) if row else 0
    if diff_count > 0:
        print(f"stock_transaction_mismatches={diff_count} (report-only, no reconciliation rows inserted)")
    return 0


def run_apply(conn, cur):
    run_id = f"inventory_balance_repair:{os.getpid()}"
    ensure_audit_table(cur)
    legacy_backups = backup_legacy_inventory(cur, run_id)
    batch_backups = backup_batch_tracking(cur, run_id)
    legacy_inserts = repair_legacy_inventory(cur)
    batch_inserts = repair_batch_tracking(cur)
    stock_transaction_inserts = repair_stock_transactions(cur)
    conn.commit()
    print("inventory_balance_repair=applied")
    print(f"audit_table={AUDIT_TABLE}")
    print(f"audit_run_id={run_id}")
    print(f"legacy_backup_rows={legacy_backups}")
    print(f"batch_backup_rows={batch_backups}")
    print(f"legacy_insert_rows={legacy_inserts}")
    print(f"batch_insert_rows={batch_inserts}")
    print(f"stock_transaction_adjustment_rows={stock_transaction_inserts}")


def main():
    args = parse_args()
    os.environ.setdefault("PG_PASSWORD", "admin")
    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            missing = missing_schema_items(cur)
            if missing:
                print("inventory_balance_repair=failed")
                for item in missing:
                    print(f"failed | {item}")
                return 1

            legacy_count, legacy_rows = fetch_legacy_summary(cur)
            batch_count, batch_rows = fetch_batch_summary(cur)
            stock_count, stock_rows = fetch_stock_transaction_summary(cur)

            print("inventory_balance_repair=dry_run" if not args.apply else "inventory_balance_repair=ready")
            print("main_ledger=inventory_balances")
            print("legacy_inventory_policy=derived_product_summary")
            print("batch_tracking_policy=derived_lot_serial_balance_only")
            print(f"legacy_mismatch_products={legacy_count}")
            print(f"batch_mismatch_dimensions={batch_count}")
            print(f"stock_transaction_mismatch_dimensions={stock_count}")
            print_rows("legacy_inventory_differences", legacy_rows, args.limit)
            print_rows("batch_tracking_differences", batch_rows, args.limit)
            print_rows("stock_transaction_differences", stock_rows, args.limit)

            if not args.apply:
                print_suggested_sql()
                conn.rollback()
                return 1 if legacy_count or batch_count or stock_count else 0

            run_apply(conn, cur)
            return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
