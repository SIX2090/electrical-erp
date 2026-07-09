from __future__ import annotations

import os
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[1]


CONSTRAINTS = [
    ("sales_orders", "fk_sales_orders_customer_id_customers_not_valid"),
    ("sales_order_items", "fk_sales_order_items_order_id_sales_orders_not_valid"),
    ("purchase_orders", "fk_purchase_orders_supplier_id_suppliers_not_valid"),
    ("purchase_order_items", "fk_purchase_order_items_order_id_purchase_orders_not_valid"),
    ("stock_transactions", "fk_stock_transactions_product_id_products_not_valid"),
    ("work_orders", "fk_work_orders_product_id_products_not_valid"),
]


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=os.environ.get("PG_PORT", "5432"),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=os.environ.get("PG_PASSWORD", ""),
        connect_timeout=5,
        client_encoding="UTF8",
    )


def main() -> int:
    validated = []
    with connect() as conn:
        with conn.cursor() as cur:
            for table, constraint in CONSTRAINTS:
                cur.execute(
                    """
                    SELECT convalidated
                    FROM pg_constraint
                    WHERE conname=%s
                    """,
                    (constraint,),
                )
                row = cur.fetchone()
                if not row:
                    validated.append((table, constraint, "missing"))
                    continue
                if row[0]:
                    validated.append((table, constraint, "already_validated"))
                    continue
                cur.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")
                validated.append((table, constraint, "validated"))
        conn.commit()

    report = ROOT / "logs" / "core_fk_validation_report.csv"
    report.parent.mkdir(exist_ok=True)
    report.write_text(
        "table,constraint,status\n"
        + "\n".join(f"{table},{constraint},{status}" for table, constraint, status in validated)
        + "\n",
        encoding="utf-8",
    )
    print("core_fk_validation=ok")
    print(f"report={report}")
    for table, constraint, status in validated:
        print(f"{status} | {table} | {constraint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
