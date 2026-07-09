from pathlib import Path
import os
import sys

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
QTY_TOLERANCE = "0.0001"
COST_TOLERANCE = "0.0001"
DIFF_LIMIT = 200


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def table_exists(cur, table_name):
    cur.execute("SELECT to_regclass(%s) AS table_name", (table_name,))
    row = cur.fetchone() or {}
    return bool(row.get("table_name"))


def column_exists(cur, table_name, column_name):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """,
        (table_name, column_name),
    )
    return bool(cur.fetchone())


def normalized_dimension_select(alias, quantity_column, cost_column="unit_cost"):
    return f"""
        {alias}.product_id,
        COALESCE({alias}.warehouse_id, 0) AS warehouse_id,
        COALESCE({alias}.location_id, 0) AS location_id,
        COALESCE({alias}.lot_no, '') AS lot_no,
        COALESCE({alias}.serial_no, '') AS serial_no,
        COALESCE({alias}.project_code, '') AS project_code,
        SUM(COALESCE({alias}.{quantity_column}, 0)) AS quantity,
        CASE WHEN COALESCE(SUM({alias}.{quantity_column}),0) <> 0
            THEN COALESCE(SUM({alias}.{quantity_column} * COALESCE({alias}.{cost_column},0)) / NULLIF(SUM({alias}.{quantity_column}),0),0)
            ELSE COALESCE(MAX({alias}.{cost_column}),0)
        END AS unit_cost
    """


def print_rows(title, rows, keys):
    print(f"{title}={len(rows)}")
    for row in rows[:DIFF_LIMIT]:
        print("failed | " + " | ".join(f"{key}={row.get(key)!r}" for key in keys))
    if len(rows) > DIFF_LIMIT:
        print(f"warning | {title} output limited to first {DIFF_LIMIT} rows")


def fetch_negative_rows(cur):
    cur.execute(
        """
        SELECT
            ib.id,
            ib.product_id,
            p.code AS product_code,
            p.name AS product_name,
            COALESCE(ib.warehouse_id, 0) AS warehouse_id,
            COALESCE(ib.location_id, 0) AS location_id,
            COALESCE(ib.lot_no, '') AS lot_no,
            COALESCE(ib.serial_no, '') AS serial_no,
            COALESCE(ib.project_code, '') AS project_code,
            COALESCE(ib.quantity, 0) AS quantity
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        WHERE COALESCE(ib.quantity,0) < 0
        ORDER BY ib.quantity ASC, COALESCE(p.code, ''), ib.product_id, ib.id
        """
    )
    return cur.fetchall()


def fetch_legacy_mismatch_rows(cur):
    cur.execute(
        """
        WITH legacy AS (
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
        ),
        balances AS (
            SELECT
                product_id,
                COALESCE(SUM(quantity),0) AS balance_qty,
                CASE WHEN COALESCE(SUM(quantity),0) <> 0
                    THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                    ELSE COALESCE(MAX(unit_cost),0)
                END AS balance_unit_cost,
                COUNT(*) AS balance_rows
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT
            COALESCE(l.product_id, b.product_id) AS product_id,
            p.code AS product_code,
            p.name AS product_name,
            COALESCE(l.legacy_qty,0) AS legacy_qty,
            COALESCE(b.balance_qty,0) AS balance_qty,
            COALESCE(l.legacy_qty,0) - COALESCE(b.balance_qty,0) AS qty_diff,
            COALESCE(l.legacy_unit_cost,0) AS legacy_unit_cost,
            COALESCE(b.balance_unit_cost,0) AS balance_unit_cost,
            COALESCE(l.legacy_unit_cost,0) - COALESCE(b.balance_unit_cost,0) AS unit_cost_diff,
            COALESCE(l.legacy_rows,0) AS legacy_rows,
            COALESCE(b.balance_rows,0) AS balance_rows
        FROM legacy l
        FULL OUTER JOIN balances b ON b.product_id=l.product_id
        LEFT JOIN products p ON p.id=COALESCE(l.product_id, b.product_id)
        WHERE ABS(COALESCE(l.legacy_qty,0) - COALESCE(b.balance_qty,0)) > %s
           OR ABS(COALESCE(l.legacy_unit_cost,0) - COALESCE(b.balance_unit_cost,0)) > %s
           OR COALESCE(l.legacy_rows,0) > 1
           OR l.product_id IS NULL
           OR b.product_id IS NULL
        ORDER BY ABS(COALESCE(l.legacy_qty,0) - COALESCE(b.balance_qty,0)) DESC,
                 ABS(COALESCE(l.legacy_unit_cost,0) - COALESCE(b.balance_unit_cost,0)) DESC,
                 COALESCE(p.code, ''), COALESCE(l.product_id, b.product_id)
        LIMIT %s
        """,
        (QTY_TOLERANCE, COST_TOLERANCE, DIFF_LIMIT),
    )
    return cur.fetchall()


def fetch_batch_mismatch_rows(cur):
    cur.execute(
        f"""
        WITH batch AS (
            SELECT {normalized_dimension_select("bt", "quantity_available")}
            FROM batch_tracking bt
            GROUP BY bt.product_id, COALESCE(bt.warehouse_id, 0), COALESCE(bt.location_id, 0),
                     COALESCE(bt.lot_no, ''), COALESCE(bt.serial_no, ''), COALESCE(bt.project_code, '')
        ),
        balance AS (
            SELECT {normalized_dimension_select("ib", "quantity")}
            FROM inventory_balances ib
            GROUP BY ib.product_id, COALESCE(ib.warehouse_id, 0), COALESCE(ib.location_id, 0),
                     COALESCE(ib.lot_no, ''), COALESCE(ib.serial_no, ''), COALESCE(ib.project_code, '')
        )
        SELECT COALESCE(batch.product_id, balance.product_id) AS product_id,
               COALESCE(batch.warehouse_id, balance.warehouse_id) AS warehouse_id,
               COALESCE(batch.location_id, balance.location_id) AS location_id,
               COALESCE(batch.lot_no, balance.lot_no) AS lot_no,
               COALESCE(batch.serial_no, balance.serial_no) AS serial_no,
               COALESCE(batch.project_code, balance.project_code) AS project_code,
               COALESCE(batch.quantity, 0) AS batch_qty,
               COALESCE(balance.quantity, 0) AS balance_qty,
               COALESCE(batch.quantity, 0) - COALESCE(balance.quantity, 0) AS qty_diff,
               COALESCE(batch.unit_cost, 0) AS batch_unit_cost,
               COALESCE(balance.unit_cost, 0) AS balance_unit_cost
        FROM batch
        FULL OUTER JOIN balance
          ON batch.product_id IS NOT DISTINCT FROM balance.product_id
         AND batch.warehouse_id=balance.warehouse_id
         AND batch.location_id=balance.location_id
         AND batch.lot_no=balance.lot_no
         AND batch.serial_no=balance.serial_no
         AND batch.project_code=balance.project_code
        WHERE ABS(COALESCE(batch.quantity, 0) - COALESCE(balance.quantity, 0)) > %s
        ORDER BY ABS(COALESCE(batch.quantity, 0) - COALESCE(balance.quantity, 0)) DESC,
                 product_id, warehouse_id, location_id, lot_no, serial_no, project_code
        LIMIT %s
        """,
        (QTY_TOLERANCE, DIFF_LIMIT),
    )
    return cur.fetchall()


def fetch_stock_transaction_mismatch_rows(cur):
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
                ) AS tx_qty
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
                SUM(COALESCE(quantity, 0)) AS balance_qty
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
               COALESCE(tx.tx_qty, 0) AS stock_transaction_qty,
               COALESCE(balance.balance_qty, 0) AS balance_qty,
               COALESCE(tx.tx_qty, 0) - COALESCE(balance.balance_qty, 0) AS qty_diff
        FROM tx
        FULL OUTER JOIN balance
          ON tx.product_id IS NOT DISTINCT FROM balance.product_id
         AND tx.warehouse_id=balance.warehouse_id
         AND tx.location_id=balance.location_id
         AND tx.lot_no=balance.lot_no
         AND tx.serial_no=balance.serial_no
         AND tx.project_code=balance.project_code
        WHERE ABS(COALESCE(tx.tx_qty, 0) - COALESCE(balance.balance_qty, 0)) > %s
        ORDER BY ABS(COALESCE(tx.tx_qty, 0) - COALESCE(balance.balance_qty, 0)) DESC,
                 product_id, warehouse_id, location_id, lot_no, serial_no, project_code
        LIMIT %s
        """,
        (QTY_TOLERANCE, DIFF_LIMIT),
    )
    return cur.fetchall()


def fetch_work_order_stock_rows(cur):
    cur.execute(
        """
        SELECT
            wo.id AS work_order_id,
            wo.wo_no,
            wo.product_id,
            wo.project_code,
            wo.serial_no,
            COALESCE(wo.quantity,0) AS planned_qty,
            COALESCE(SUM(CASE WHEN st.transaction_type='工单领料' THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END),0) AS issued_qty,
            COALESCE(SUM(CASE WHEN st.transaction_type='工单退料' THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END),0) AS returned_qty,
            COALESCE(SUM(CASE WHEN st.transaction_type='工单完工入库' THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END),0) AS completed_in_qty
        FROM work_orders wo
        LEFT JOIN stock_transactions st
          ON st.reference_no=wo.wo_no
         AND st.transaction_type IN ('工单领料', '工单退料', '工单完工入库')
        GROUP BY wo.id, wo.wo_no, wo.product_id, wo.project_code, wo.serial_no, wo.quantity
        HAVING COALESCE(SUM(CASE WHEN st.transaction_type='工单领料' THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END),0) < 0
            OR COALESCE(SUM(CASE WHEN st.transaction_type='工单退料' THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END),0) < 0
            OR COALESCE(SUM(CASE WHEN st.transaction_type='工单完工入库' THEN ABS(COALESCE(st.quantity,0)) ELSE 0 END),0) < 0
        ORDER BY wo.id
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
            required_tables = ("inventory", "inventory_balances", "batch_tracking", "stock_transactions", "work_orders")
            missing = [name for name in required_tables if not table_exists(cur, name)]
            if missing:
                print("inventory_balance_consistency=failed")
                print(f"missing_tables={','.join(missing)}")
                print(f"findings={len(missing)}")
                return 1

            required_columns = [
                ("inventory_balances", "project_code"),
                ("batch_tracking", "project_code"),
                ("stock_transactions", "project_code"),
                ("stock_transactions", "warehouse_id"),
                ("stock_transactions", "location_id"),
            ]
            missing_columns = [
                f"{table}.{column}"
                for table, column in required_columns
                if not column_exists(cur, table, column)
            ]
            if missing_columns:
                print("inventory_balance_consistency=failed")
                for item in missing_columns:
                    print(f"failed | missing_column={item}")
                print(f"findings={len(missing_columns)}")
                return 1

            negative_rows = fetch_negative_rows(cur)
            legacy_rows = fetch_legacy_mismatch_rows(cur)
            batch_rows = fetch_batch_mismatch_rows(cur)
            stock_rows = fetch_stock_transaction_mismatch_rows(cur)
            work_order_rows = fetch_work_order_stock_rows(cur)
    finally:
        conn.close()

    findings = len(negative_rows) + len(legacy_rows) + len(batch_rows) + len(stock_rows) + len(work_order_rows)
    print("inventory_balance_consistency=ok" if findings == 0 else "inventory_balance_consistency=failed")
    print(f"findings={findings}")
    print_rows(
        "negative_balance_rows",
        negative_rows,
        ("id", "product_id", "product_code", "product_name", *DIMENSIONS[1:], "quantity"),
    )
    print_rows(
        "legacy_inventory_mismatch_rows",
        legacy_rows,
        ("product_id", "product_code", "product_name", "legacy_qty", "balance_qty", "qty_diff", "legacy_unit_cost", "balance_unit_cost", "unit_cost_diff", "legacy_rows", "balance_rows"),
    )
    print_rows(
        "batch_tracking_mismatch_rows",
        batch_rows,
        (*DIMENSIONS, "batch_qty", "balance_qty", "qty_diff", "batch_unit_cost", "balance_unit_cost"),
    )
    print_rows(
        "stock_transaction_mismatch_rows",
        stock_rows,
        (*DIMENSIONS, "stock_transaction_qty", "balance_qty", "qty_diff"),
    )
    print_rows(
        "work_order_stock_mismatch_rows",
        work_order_rows,
        ("work_order_id", "wo_no", "product_id", "project_code", "serial_no", "planned_qty", "issued_qty", "returned_qty", "completed_in_qty"),
    )
    if findings:
        print("repair_hint=run scripts/repair_inventory_balance_consistency.py --dry-run; use --apply only after reviewing affected derived summaries")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
