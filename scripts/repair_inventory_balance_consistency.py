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
    "cabinet_no",
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
        "cabinet_no",
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
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity, 0)) AS balance_qty,
                   CASE WHEN COALESCE(SUM(quantity),0) <> 0
                       THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                       ELSE COALESCE(MAX(unit_cost),0)
                   END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ),
        batch AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity_available, 0)) AS batch_qty,
                   COUNT(*) AS batch_rows
            FROM batch_tracking
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        )
        SELECT COALESCE(d.product_id, b.product_id) AS product_id,
               COALESCE(d.warehouse_id, b.warehouse_id) AS warehouse_id,
               COALESCE(d.location_id, b.location_id) AS location_id,
               COALESCE(d.lot_no, b.lot_no) AS lot_no,
               COALESCE(d.cabinet_no, b.cabinet_no) AS cabinet_no,
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
         AND b.cabinet_no=d.cabinet_no
         AND b.project_code=d.project_code
        WHERE COALESCE(b.batch_qty, 0) <> COALESCE(d.balance_qty, 0)
           OR COALESCE(b.batch_rows, 0) > 1
        ORDER BY ABS(COALESCE(b.batch_qty, 0) - COALESCE(d.balance_qty, 0)) DESC,
                 product_id, warehouse_id, location_id, lot_no, cabinet_no, project_code
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
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity, 0)) AS balance_qty
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ),
        batch AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity_available, 0)) AS batch_qty,
                   COUNT(*) AS batch_rows
            FROM batch_tracking
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        )
        SELECT COUNT(*) AS mismatch_dimensions
        FROM desired d
        FULL OUTER JOIN batch b
          ON b.product_id IS NOT DISTINCT FROM d.product_id
         AND b.warehouse_id=d.warehouse_id
         AND b.location_id=d.location_id
         AND b.lot_no=d.lot_no
         AND b.cabinet_no=d.cabinet_no
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
                COALESCE(cabinet_no, '') AS cabinet_no,
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
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ),
        balance AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(cabinet_no, '') AS cabinet_no,
                COALESCE(project_code, '') AS project_code,
                SUM(COALESCE(quantity, 0)) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        )
        SELECT COALESCE(tx.product_id, balance.product_id) AS product_id,
               COALESCE(tx.warehouse_id, balance.warehouse_id) AS warehouse_id,
               COALESCE(tx.location_id, balance.location_id) AS location_id,
               COALESCE(tx.lot_no, balance.lot_no) AS lot_no,
               COALESCE(tx.cabinet_no, balance.cabinet_no) AS cabinet_no,
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
         AND tx.cabinet_no=balance.cabinet_no
         AND tx.project_code=balance.project_code
        WHERE ABS(COALESCE(tx.stock_transaction_qty, 0) - COALESCE(balance.balance_qty, 0)) > %s
        ORDER BY ABS(COALESCE(tx.stock_transaction_qty, 0) - COALESCE(balance.balance_qty, 0)) DESC,
                 product_id, warehouse_id, location_id, lot_no, cabinet_no, project_code
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
                COALESCE(cabinet_no, '') AS cabinet_no,
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
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ),
        balance AS (
            SELECT product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity, 0)) AS balance_qty
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        )
        SELECT COUNT(*) AS mismatch_dimensions
        FROM tx
        FULL OUTER JOIN balance
          ON tx.product_id IS NOT DISTINCT FROM balance.product_id
         AND tx.warehouse_id=balance.warehouse_id
         AND tx.location_id=balance.location_id
         AND tx.lot_no=balance.lot_no
         AND tx.cabinet_no=balance.cabinet_no
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

-- batch_tracking is treated as a lot/cabinet derived balance from inventory_balances:
-- update quantity_available on one canonical batch row, zero duplicate/current orphan rows,
-- and insert missing lot/cabinet dimensions only.

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
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ),
        batch AS (
            SELECT id, product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(cabinet_no, '') AS cabinet_no,
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
             AND b.cabinet_no=d.cabinet_no
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
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code,
                   SUM(COALESCE(quantity, 0)) AS balance_qty,
                   CASE WHEN COALESCE(SUM(quantity),0) <> 0
                       THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                       ELSE COALESCE(MAX(unit_cost),0)
                   END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ),
        ranked AS (
            SELECT id, product_id,
                   COALESCE(warehouse_id, 0) AS warehouse_id,
                   COALESCE(location_id, 0) AS location_id,
                   COALESCE(lot_no, '') AS lot_no,
                   COALESCE(cabinet_no, '') AS cabinet_no,
                   COALESCE(project_code, '') AS project_code,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                                    COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
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
             AND d.cabinet_no=r.cabinet_no
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
            (lot_no, product_id, warehouse_id, location_id, cabinet_no, project_code,
             quantity_in, quantity_out, quantity_available, unit_cost, source_order_no,
             status, created_at, updated_at)
        SELECT COALESCE(d.lot_no, ''),
               d.product_id, NULLIF(d.warehouse_id, 0), NULLIF(d.location_id, 0),
               NULLIF(d.cabinet_no, ''), NULLIF(d.project_code, ''),
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
         AND r.cabinet_no=d.cabinet_no
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
                COALESCE(cabinet_no, '') AS cabinet_no,
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
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ),
        balance AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(cabinet_no, '') AS cabinet_no,
                COALESCE(project_code, '') AS project_code,
                SUM(COALESCE(quantity, 0)) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost
            FROM inventory_balances
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        )
        SELECT COUNT(*) AS diff_count
        FROM tx
        FULL OUTER JOIN balance
          ON tx.product_id IS NOT DISTINCT FROM balance.product_id
         AND tx.warehouse_id=balance.warehouse_id
         AND tx.location_id=balance.location_id
         AND tx.lot_no=balance.lot_no
         AND tx.cabinet_no=balance.cabinet_no
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


def repair_inventory_balance_project_code(cur):
    """Fix inventory_balances rows with empty project_code by merging them into
    rows with the correct project_code derived from stock_transactions.

    This addresses data setup scripts that create inventory_balances without
    project_code while the corresponding stock_transactions have one. The fix
    updates/merges inventory_balances rows (the authoritative balance source)
    rather than inserting fake stock_transaction reconciliation rows.
    """
    cur.execute(
        """
        SELECT ib.id, ib.product_id, ib.warehouse_id, ib.location_id,
               ib.lot_no, ib.cabinet_no, ib.quantity, ib.unit_cost
        FROM inventory_balances ib
        WHERE COALESCE(ib.project_code, '') = ''
          AND COALESCE(ib.cabinet_no, '') <> ''
          AND COALESCE(ib.quantity, 0) <> 0
        """
    )
    orphan_rows = cur.fetchall()
    merged = 0
    for row in orphan_rows:
        cur.execute(
            """
            SELECT COALESCE(project_code, '') AS project_code
            FROM stock_transactions
            WHERE product_id=%s
              AND COALESCE(cabinet_no, '')=%s
              AND COALESCE(project_code, '') <> ''
            GROUP BY project_code
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """,
            (row["product_id"], row["cabinet_no"]),
        )
        result = cur.fetchone()
        if not result:
            continue
        target_project_code = result["project_code"]
        cur.execute(
            """
            SELECT id, quantity FROM inventory_balances
            WHERE product_id=%s
              AND COALESCE(warehouse_id, 0) = COALESCE(%s, 0)
              AND COALESCE(location_id, 0) = COALESCE(%s, 0)
              AND COALESCE(lot_no, '') = COALESCE(%s, '')
              AND COALESCE(cabinet_no, '') = COALESCE(%s, '')
              AND project_code=%s
            """,
            (row["product_id"], row["warehouse_id"], row["location_id"],
             row["lot_no"], row["cabinet_no"], target_project_code),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE inventory_balances SET quantity=quantity+%s, updated_at=NOW() WHERE id=%s",
                (row["quantity"], existing["id"]),
            )
            cur.execute("DELETE FROM inventory_balances WHERE id=%s", (row["id"],))
        else:
            cur.execute(
                "UPDATE inventory_balances SET project_code=%s, updated_at=NOW() WHERE id=%s",
                (target_project_code, row["id"]),
            )
        merged += 1
    return merged


def repair_inventory_balance_from_stock_transactions(cur):
    """Create missing inventory_balances rows for dimensions where stock_transactions
    exist but no inventory_balances row exists. This fixes trial data setup scripts
    that create stock movements without updating the authoritative balance table.

    Unlike repair_stock_transactions (which is report-only), this function fixes
    the authoritative inventory_balances table to reflect the ledger reality.
    """
    cur.execute(
        """
        WITH tx AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(cabinet_no, '') AS cabinet_no,
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
                ) AS tx_qty,
                CASE WHEN SUM(
                    CASE
                        WHEN COALESCE(transaction_type,'') IN (
                            'sales_outbound', 'outbound', 'issue', 'shipment',
                            'subcontract_issue', 'quality_hold_transfer_out',
                            '售后备件出库', '手工出库', '调拨出库', '销售出库',
                            '工单领料', '工单补料', '生产领料', '组装领料', '拆卸出库'
                        ) THEN -ABS(COALESCE(quantity,0))
                        ELSE COALESCE(quantity,0)
                    END
                ) <> 0
                    THEN COALESCE(SUM(
                        CASE
                            WHEN COALESCE(transaction_type,'') IN (
                                'sales_outbound', 'outbound', 'issue', 'shipment',
                                'subcontract_issue', 'quality_hold_transfer_out',
                                '售后备件出库', '手工出库', '调拨出库', '销售出库',
                                '工单领料', '工单补料', '生产领料', '组装领料', '拆卸出库'
                            ) THEN -ABS(COALESCE(quantity,0)) * COALESCE(unit_cost,0)
                            ELSE COALESCE(quantity,0) * COALESCE(unit_cost,0)
                        END
                    ) / NULLIF(SUM(
                        CASE
                            WHEN COALESCE(transaction_type,'') IN (
                                'sales_outbound', 'outbound', 'issue', 'shipment',
                                'subcontract_issue', 'quality_hold_transfer_out',
                                '售后备件出库', '手工出库', '调拨出库', '销售出库',
                                '工单领料', '工单补料', '生产领料', '组装领料', '拆卸出库'
                            ) THEN -ABS(COALESCE(quantity,0))
                            ELSE COALESCE(quantity,0)
                        END
                    ), 0), 0)
                    ELSE COALESCE(MAX(unit_cost), 0)
                END AS tx_unit_cost
            FROM stock_transactions
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        )
        SELECT tx.product_id, tx.warehouse_id, tx.location_id, tx.lot_no,
               tx.cabinet_no, tx.project_code, tx.tx_qty, tx.tx_unit_cost
        FROM tx
        LEFT JOIN inventory_balances ib
          ON ib.product_id IS NOT DISTINCT FROM tx.product_id
         AND COALESCE(ib.warehouse_id, 0) = tx.warehouse_id
         AND COALESCE(ib.location_id, 0) = tx.location_id
         AND COALESCE(ib.lot_no, '') = tx.lot_no
         AND COALESCE(ib.cabinet_no, '') = tx.cabinet_no
         AND COALESCE(ib.project_code, '') = tx.project_code
        WHERE ib.id IS NULL
          AND ABS(tx.tx_qty) > %s
        """,
        (QTY_TOLERANCE,),
    )
    missing_rows = cur.fetchall()
    inserted = 0
    for row in missing_rows:
        wh_id = row["warehouse_id"] if row["warehouse_id"] else None
        loc_id = row["location_id"] if row["location_id"] else None
        cur.execute(
            """
            INSERT INTO inventory_balances
                (product_id, warehouse_id, location_id, lot_no, cabinet_no,
                 project_code, quantity, locked_qty, unit_cost, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, NOW())
            """,
            (
                row["product_id"],
                wh_id,
                loc_id,
                row["lot_no"] if row["lot_no"] else None,
                row["cabinet_no"] if row["cabinet_no"] else None,
                row["project_code"] if row["project_code"] else None,
                row["tx_qty"],
                row["tx_unit_cost"],
            ),
        )
        inserted += 1
    return inserted


def repair_inventory_balance_qty_sync(cur):
    """Update existing inventory_balances rows where quantity doesn't match
    the stock_transaction ledger sum. Only updates rows where the absolute
    difference exceeds the tolerance. Backs up before/after to the audit table.
    """
    run_id = f"inventory_balance_repair:{os.getpid()}"
    cur.execute(
        """
        WITH tx AS (
            SELECT
                product_id,
                COALESCE(warehouse_id, 0) AS warehouse_id,
                COALESCE(location_id, 0) AS location_id,
                COALESCE(lot_no, '') AS lot_no,
                COALESCE(cabinet_no, '') AS cabinet_no,
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
                ) AS tx_qty
            FROM stock_transactions
            GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                     COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        )
        SELECT ib.id, ib.product_id, ib.warehouse_id, ib.location_id,
               ib.lot_no, ib.cabinet_no, ib.project_code, ib.quantity, tx.tx_qty
        FROM inventory_balances ib
        INNER JOIN tx
          ON tx.product_id IS NOT DISTINCT FROM ib.product_id
         AND tx.warehouse_id = COALESCE(ib.warehouse_id, 0)
         AND tx.location_id = COALESCE(ib.location_id, 0)
         AND tx.lot_no = COALESCE(ib.lot_no, '')
         AND tx.cabinet_no = COALESCE(ib.cabinet_no, '')
         AND tx.project_code = COALESCE(ib.project_code, '')
        WHERE ABS(COALESCE(ib.quantity, 0) - COALESCE(tx.tx_qty, 0)) > %s
        """,
        (QTY_TOLERANCE,),
    )
    mismatch_rows = cur.fetchall()
    updated = 0
    for row in mismatch_rows:
        cur.execute(
            "INSERT INTO inventory_balance_repair_audit (run_id, table_name, row_id, action, before_data, created_at) VALUES (%s, %s, %s, %s, %s, NOW())",
            (run_id, "inventory_balances", row["id"], "qty_sync",
             f'{{"old_qty": {row["quantity"]}, "new_qty": {row["tx_qty"]}}}',),
        )
        cur.execute(
            "UPDATE inventory_balances SET quantity=%s, updated_at=NOW() WHERE id=%s",
            (row["tx_qty"], row["id"]),
        )
        updated += 1
    return updated


def run_apply(conn, cur):
    run_id = f"inventory_balance_repair:{os.getpid()}"
    ensure_audit_table(cur)
    legacy_backups = backup_legacy_inventory(cur, run_id)
    batch_backups = backup_batch_tracking(cur, run_id)
    legacy_inserts = repair_legacy_inventory(cur)
    batch_inserts = repair_batch_tracking(cur)
    project_code_fixes = repair_inventory_balance_project_code(cur)
    # Rebuild derived summaries after project_code repair so they reflect the
    # corrected inventory_balances dimensions.
    if project_code_fixes:
        legacy_inserts = repair_legacy_inventory(cur)
        batch_inserts = repair_batch_tracking(cur)
    # Create missing inventory_balances rows from stock_transactions before
    # checking stock_transaction consistency.
    balance_from_tx = repair_inventory_balance_from_stock_transactions(cur)
    if balance_from_tx:
        legacy_inserts = repair_legacy_inventory(cur)
        batch_inserts = repair_batch_tracking(cur)
    # Sync existing balance quantities to match stock_transaction ledger.
    qty_sync_rows = repair_inventory_balance_qty_sync(cur)
    if qty_sync_rows:
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
    print(f"project_code_repair_rows={project_code_fixes}")
    print(f"balance_from_transaction_rows={balance_from_tx}")
    print(f"balance_qty_sync_rows={qty_sync_rows}")
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
