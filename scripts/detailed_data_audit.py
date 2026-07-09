from __future__ import annotations

import os
import sys
from pathlib import Path

from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402


TABLE_CHECKS = [
    ("production_completion_orders", "production_completion_orders"),
    ("wo_complete_items", "legacy_work_order_completion_items"),
    ("operation_reports", "operation_reports"),
    ("work_order_processes", "work_order_processes"),
    ("quality_inspection_records", "quality_inspection_records"),
    ("mrp_requirements", "mrp_requirements"),
    ("purchase_requisitions", "purchase_requisitions"),
    ("purchase_orders", "purchase_orders"),
    ("purchase_receipts", "purchase_receipts"),
    ("sales_orders", "sales_orders"),
    ("sales_shipments", "sales_shipments"),
    ("stock_transactions", "stock_transactions"),
    ("inventory_balances", "inventory_balances"),
]

DOC_TYPE_CHECKS = [
    ("pick_lists", "production_issue", "production_issue"),
    ("pick_lists", "production_return", "production_return"),
]


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


def table_count(cur, table_name, where_clause=None, params=()):
    if not table_exists(cur, table_name):
        return None
    sql = f'SELECT COUNT(*) AS count FROM "{table_name}"'
    if where_clause:
        sql += f" WHERE {where_clause}"
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return int(row.get("count") or 0)


def main():
    print("postgres_data_audit=running")
    findings = []
    with connect_db(get_db_config(), cursor_factory=RealDictCursor) as conn, conn.cursor() as cur:
        for table, label in TABLE_CHECKS:
            count = table_count(cur, table)
            if count is None:
                findings.append(f"missing_table:{table}")
                print(f"missing | {label}")
            else:
                print(f"ok | {label} | rows={count}")

        for table, doc_type, label in DOC_TYPE_CHECKS:
            count = table_count(cur, table, "doc_type = %s", (doc_type,))
            if count is None:
                findings.append(f"missing_table:{table}")
                print(f"missing | {label} | source_table={table}")
            else:
                cur.execute(f'SELECT COUNT(*) AS count FROM "{table}" WHERE doc_type = %s', (doc_type,))
                row = cur.fetchone() or {}
                print(f"ok | {label} | source_table={table} | rows={int(row.get('count') or 0)}")

        dirty_status_count = table_count(cur, "work_orders", "status IN ('???', '') OR status IS NULL")
        if dirty_status_count is None:
            findings.append("missing_table:work_orders")
            print("missing | work_orders")
        else:
            print(f"ok | work_orders_dirty_status | rows={dirty_status_count}")
            if dirty_status_count:
                findings.append(f"dirty_work_order_status:{dirty_status_count}")

        if table_exists(cur, "work_orders"):
            cur.execute(
                """
                SELECT COALESCE(status, 'NULL') AS status, COUNT(*) AS count
                FROM work_orders
                GROUP BY status
                ORDER BY count DESC, status
                """
            )
            for row in cur.fetchall():
                print(f"status | work_orders | {row['status']} | rows={row['count']}")

    if findings:
        print("postgres_data_audit=failed")
        for finding in findings:
            print(f"failed | {finding}")
        return 1
    print("postgres_data_audit=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
