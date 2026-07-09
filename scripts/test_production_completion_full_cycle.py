from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


PREFIX = "CODX-PC"


def db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return next(iter(row.values()), None)


def has_column(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return bool(cur.fetchone())


def ensure_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS production_completion_orders (
            id SERIAL PRIMARY KEY,
            completion_no VARCHAR(120) UNIQUE NOT NULL
        )
        """
    )
    for statement in (
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
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT '草稿'",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS remark TEXT",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS reverse_posted_at TIMESTAMP",
        "ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS wo_complete_item_id INTEGER",
        "ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80)",
        "ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120)",
        "ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS reverse_posted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS reverse_posted_at TIMESTAMP",
    ):
        cur.execute(statement)


def cleanup(cur):
    if has_column(cur, "stock_transactions", "source_doc_no"):
        cur.execute(
            """
            DELETE FROM stock_transactions
            WHERE reference_no LIKE %s OR source_doc_no LIKE %s
            """,
            (f"{PREFIX}%", f"{PREFIX}%"),
        )
    else:
        cur.execute("DELETE FROM stock_transactions WHERE reference_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM wo_complete_items WHERE source_doc_no LIKE %s OR lot_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%"))
    cur.execute("DELETE FROM production_completion_orders WHERE completion_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM quality_inspection_records WHERE inspection_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM wo_material_items WHERE wo_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    cur.execute("DELETE FROM work_orders WHERE wo_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM inventory_balances WHERE product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    cur.execute("DELETE FROM inventory WHERE product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    cur.execute("DELETE FROM batch_tracking WHERE product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    cur.execute("DELETE FROM products WHERE code LIKE %s", (f"{PREFIX}%",))


def create_test_data(cur):
    cur.execute(
        """
        INSERT INTO products (code, name, category, specification, unit, standard_price)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (f"{PREFIX}-FG", "完工测试成品", "产成品", "test", "台", 120),
    )
    product_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO products (code, name, category, specification, unit, standard_price)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (f"{PREFIX}-MAT", "完工测试材料", "原材料", "test", "件", 10),
    )
    material_id = cur.fetchone()["id"]
    warehouse_id = scalar(cur, "SELECT id FROM warehouses ORDER BY id LIMIT 1")
    location_id = scalar(cur, "SELECT id FROM locations WHERE warehouse_id=%s ORDER BY id LIMIT 1", (warehouse_id,)) if warehouse_id else None
    cur.execute(
        """
        INSERT INTO work_orders
            (wo_no, wo_date, product_id, warehouse_id, location_id, quantity, status,
             project_code, serial_no, planned_start_date, planned_end_date, remark)
        VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '1 day', %s)
        RETURNING id
        """,
        (
            f"{PREFIX}-WO-001",
            product_id,
            warehouse_id,
            location_id,
            1,
            "生产中",
            f"{PREFIX}-PROJECT",
            f"{PREFIX}-SN",
            "production completion full-cycle test",
        ),
    )
    work_order_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO wo_material_items
            (wo_id, product_id, required_qty, issued_qty, returned_qty, unit_cost, remark)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (work_order_id, material_id, 1, 1, 0, 10, "completion gate satisfied by test issue"),
    )
    cur.execute(
        """
        INSERT INTO quality_inspection_records
            (inspection_no, product_id, inspection_type, inspection_date, sample_size,
             passed_quantity, failed_quantity, inspection_result, status, source_document_type,
             source_document_id, project_code, serial_no, conclusion)
        VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            f"{PREFIX}-QI-001",
            product_id,
            "final",
            1,
            1,
            0,
            "pass",
            "completed",
            "work_order",
            work_order_id,
            f"{PREFIX}-PROJECT",
            f"{PREFIX}-SN",
            "test quality release",
        ),
    )
    return product_id, warehouse_id, location_id, work_order_id


def main() -> int:
    os.environ.setdefault("INVENTORY_SECRET_KEY", "production-completion-full-cycle-test")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    checks = []
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cleanup(cur)
            product_id, warehouse_id, location_id, work_order_id = create_test_data(cur)
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"

        response = client.post(
            "/production-completions/new",
            data={
                "work_order_id": str(work_order_id),
                "completion_date": date.today().isoformat(),
                "quantity": "1",
                "failed_quantity": "0",
                "unit_cost": "120",
                "warehouse_id": str(warehouse_id or ""),
                "location_id": str(location_id or ""),
                "lot_no": f"{PREFIX}-LOT",
                "serial_no": f"{PREFIX}-SN",
                "remark": "完工入库全流程测试",
                "save_action": "draft",
            },
            follow_redirects=False,
        )
        checks.append(("create_draft_redirect", response.status_code in {302, 303}, response.status_code))

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM production_completion_orders WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (work_order_id,))
            doc = cur.fetchone() or {}
            doc_id = doc.get("id")
            checks.append(("draft_created", bool(doc_id) and doc.get("status") == "草稿", doc.get("status")))
            if doc_id:
                cur.execute("UPDATE production_completion_orders SET completion_no=%s WHERE id=%s", (f"{PREFIX}-DOC-001", doc_id))
        conn.commit()
    finally:
        conn.close()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"
        response = client.post(f"/production-completions/{doc_id}/submit", follow_redirects=False)
        checks.append(("submit_redirect", response.status_code in {302, 303}, response.status_code))
        response = client.post(f"/production-completions/{doc_id}/post", follow_redirects=False)
        checks.append(("post_redirect", response.status_code in {302, 303}, response.status_code))

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM production_completion_orders WHERE id=%s", (doc_id,))
            doc = cur.fetchone() or {}
            checks.append(("posted_status", doc.get("status") == "已过账", doc.get("status")))
            checks.append(("legacy_linked", bool(doc.get("wo_complete_item_id")), doc.get("wo_complete_item_id")))
            legacy_qty = scalar(cur, "SELECT COALESCE(SUM(qty),0) FROM wo_complete_items WHERE source_doc_no=%s", (f"{PREFIX}-DOC-001",))
            checks.append(("legacy_qty", legacy_qty == 1, legacy_qty))
            stock_qty = scalar(cur, "SELECT COALESCE(SUM(quantity),0) FROM stock_transactions WHERE reference_no=%s", (f"{PREFIX}-DOC-001",))
            checks.append(("stock_qty", stock_qty == 1, stock_qty))
            balance_qty = scalar(cur, "SELECT COALESCE(SUM(quantity),0) FROM inventory_balances WHERE product_id=%s", (product_id,))
            checks.append(("balance_qty", balance_qty == 1, balance_qty))
            wo_status = scalar(cur, "SELECT status FROM work_orders WHERE id=%s", (work_order_id,))
            checks.append(("work_order_completed", wo_status == "已完工", wo_status))
        conn.commit()
    finally:
        conn.close()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"
        response = client.post(f"/production-completions/{doc_id}/reverse", follow_redirects=False)
        checks.append(("reverse_redirect", response.status_code in {302, 303}, response.status_code))

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            reversed_status = scalar(cur, "SELECT status FROM production_completion_orders WHERE id=%s", (doc_id,))
            checks.append(("reversed_status", reversed_status == "已反过账", reversed_status))
            legacy_qty_after = scalar(cur, "SELECT COALESCE(SUM(qty),0) FROM wo_complete_items WHERE source_doc_no=%s", (f"{PREFIX}-DOC-001",))
            checks.append(("legacy_qty_after_reverse", legacy_qty_after == 0, legacy_qty_after))
            stock_qty_after = scalar(cur, "SELECT COALESCE(SUM(quantity),0) FROM stock_transactions WHERE reference_no=%s", (f"{PREFIX}-DOC-001",))
            checks.append(("stock_qty_after_reverse", stock_qty_after == 0, stock_qty_after))
            balance_qty_after = scalar(cur, "SELECT COALESCE(SUM(quantity),0) FROM inventory_balances WHERE product_id=%s", (product_id,))
            checks.append(("balance_qty_after_reverse", balance_qty_after == 0, balance_qty_after))
        conn.commit()
    finally:
        conn.close()

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("production_completion_full_cycle=ok" if not failures else "production_completion_full_cycle=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
