from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]


FK_CHECKS = [
    (
        "fk_sales_orders_customer_id_customers_not_valid",
        """
        SELECT COUNT(*) AS value
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE so.customer_id IS NOT NULL AND c.id IS NULL
        """,
    ),
    (
        "fk_sales_order_items_order_id_sales_orders_not_valid",
        """
        SELECT COUNT(*) AS value
        FROM sales_order_items soi
        LEFT JOIN sales_orders so ON so.id=soi.order_id
        WHERE soi.order_id IS NOT NULL AND so.id IS NULL
        """,
    ),
    (
        "fk_purchase_orders_supplier_id_suppliers_not_valid",
        """
        SELECT COUNT(*) AS value
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        WHERE po.supplier_id IS NOT NULL AND s.id IS NULL
        """,
    ),
    (
        "fk_purchase_order_items_order_id_purchase_orders_not_valid",
        """
        SELECT COUNT(*) AS value
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.id=poi.order_id
        WHERE poi.order_id IS NOT NULL AND po.id IS NULL
        """,
    ),
    (
        "fk_stock_transactions_product_id_products_not_valid",
        """
        SELECT COUNT(*) AS value
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        WHERE st.product_id IS NOT NULL AND p.id IS NULL
        """,
    ),
    (
        "fk_work_orders_product_id_products_not_valid",
        """
        SELECT COUNT(*) AS value
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        WHERE wo.product_id IS NOT NULL AND p.id IS NULL
        """,
    ),
]


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=os.environ.get("PG_PORT", "5432"),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=os.environ.get("PG_PASSWORD", ""),
        cursor_factory=RealDictCursor,
        connect_timeout=5,
        client_encoding="UTF8",
    )


def main() -> int:
    rows = []
    with connect() as conn:
        with conn.cursor() as cur:
            for constraint, sql in FK_CHECKS:
                cur.execute(sql)
                value = int((cur.fetchone() or {}).get("value") or 0)
                rows.append((constraint, value))

    report = ROOT / "logs" / "fk_validation_readiness.csv"
    report.parent.mkdir(exist_ok=True)
    report.write_text(
        "constraint,orphan_count\n"
        + "\n".join(f"{constraint},{count}" for constraint, count in rows)
        + "\n",
        encoding="utf-8",
    )
    failed = [(constraint, count) for constraint, count in rows if count]
    if failed:
        print("fk_validation_readiness=blocked")
        for constraint, count in failed:
            print(f"blocked | {constraint} | orphan_count={count}")
        print(f"report={report}")
        return 1
    print("fk_validation_readiness=ok")
    print(f"report={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
