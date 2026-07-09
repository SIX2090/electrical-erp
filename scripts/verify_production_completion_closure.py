from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


PREFIX = "VERIFY-PC"
PROJECT_CODE = f"{PREFIX}-PROJECT"
SERIAL_NO = f"{PREFIX}-SN"
LOT_NO = f"{PREFIX}-LOT"
EXPECTED_QTY = Decimal("1")


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


def has_table(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return bool(cur.fetchone())


def has_column(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
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
    statements = (
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
    )
    for statement in statements:
        cur.execute(statement)


def delete_if_table(cur, table: str, where_sql: str, params=()):
    if has_table(cur, table):
        cur.execute(f"DELETE FROM {table} WHERE {where_sql}", params)


def cleanup(cur):
    if has_table(cur, "stock_transactions"):
        if has_column(cur, "stock_transactions", "source_doc_no"):
            cur.execute(
                """
                DELETE FROM stock_transactions
                WHERE reference_no LIKE %s OR source_doc_no LIKE %s OR lot_no LIKE %s OR serial_no LIKE %s
                """,
                (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"),
            )
        else:
            cur.execute(
                "DELETE FROM stock_transactions WHERE reference_no LIKE %s OR lot_no LIKE %s OR serial_no LIKE %s",
                (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"),
            )
    delete_if_table(cur, "wo_complete_items", "source_doc_no LIKE %s OR lot_no LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "production_completion_orders", "completion_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "quality_inspection_records", "inspection_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "wo_material_items", "wo_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "work_order_processes", "work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "mrp_requirements", "work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s) OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "work_orders", "wo_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "inventory_balances", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "inventory", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "batch_tracking", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "products", "code LIKE %s", (f"{PREFIX}%",))


def ensure_warehouse(cur):
    warehouse_id = scalar(cur, "SELECT id FROM warehouses ORDER BY id LIMIT 1")
    if not warehouse_id:
        cur.execute(
            """
            INSERT INTO warehouses (code, name)
            VALUES (%s, %s)
            RETURNING id
            """,
            (f"{PREFIX}-WH", "验证仓库"),
        )
        warehouse_id = cur.fetchone()["id"]
    location_id = None
    if has_table(cur, "locations"):
        location_id = scalar(cur, "SELECT id FROM locations WHERE warehouse_id=%s ORDER BY id LIMIT 1", (warehouse_id,))
        if not location_id:
            cur.execute(
                """
                INSERT INTO locations (warehouse_id, code, name, is_active)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id
                """,
                (warehouse_id, f"{PREFIX}-LOC", "验证库位"),
            )
            location_id = cur.fetchone()["id"]
    return warehouse_id, location_id


def ensure_trace_master(cur):
    project_id = None
    if has_table(cur, "project_masters") and has_column(cur, "project_masters", "project_code"):
        cur.execute(
            """
            INSERT INTO project_masters (project_code, project_name, status, remark)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_code) DO UPDATE
            SET updated_at=CURRENT_TIMESTAMP
            RETURNING id
            """,
            (PROJECT_CODE, "VERIFY-PC trace fixture", "ready", "production completion verification trace reference"),
        )
        row = cur.fetchone()
        project_id = row["id"] if row else None
    if has_table(cur, "machine_serial_masters") and has_column(cur, "machine_serial_masters", "serial_no"):
        values = {
            "serial_no": SERIAL_NO,
            "project_id": project_id,
            "project_code": PROJECT_CODE,
            "product_family": "verification",
            "machine_model": "trace-fixture",
            "production_stage": "verification",
            "status": "enabled",
            "remark": "production completion verification trace reference",
        }
        cols = [name for name in values if has_column(cur, "machine_serial_masters", name)]
        assignments = [f"{name}=EXCLUDED.{name}" for name in cols if name != "serial_no"]
        cur.execute(
            f"""
            INSERT INTO machine_serial_masters ({','.join(cols)})
            VALUES ({','.join(['%s'] * len(cols))})
            ON CONFLICT (serial_no) DO UPDATE
            SET {','.join(assignments) if assignments else 'serial_no=EXCLUDED.serial_no'}, updated_at=CURRENT_TIMESTAMP
            """,
            [values[name] for name in cols],
        )


def create_product(cur, code: str, name: str, category: str, unit: str, price: Decimal):
    cur.execute(
        """
        INSERT INTO products (code, name, category, specification, unit, standard_price)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (code, name, category, "closure-spec", unit, price),
    )
    return cur.fetchone()["id"]


def create_test_data(cur):
    ensure_trace_master(cur)
    product_id = create_product(cur, f"{PREFIX}-FG", "完工闭环验证成品", "产成品", "台", Decimal("120"))
    material_id = create_product(cur, f"{PREFIX}-MAT", "完工闭环验证材料", "原材料", "件", Decimal("10"))
    warehouse_id, location_id = ensure_warehouse(cur)
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
            EXPECTED_QTY,
            "生产中",
            PROJECT_CODE,
            SERIAL_NO,
            "production completion closure verification",
        ),
    )
    work_order_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO wo_material_items
            (wo_id, product_id, required_qty, issued_qty, returned_qty, unit_cost, remark)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (work_order_id, material_id, EXPECTED_QTY, EXPECTED_QTY, 0, Decimal("10"), "verification issue completed"),
    )
    if has_table(cur, "quality_inspection_records"):
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
                EXPECTED_QTY,
                EXPECTED_QTY,
                0,
                "pass",
                "completed",
                "work_order",
                work_order_id,
                PROJECT_CODE,
                SERIAL_NO,
                "verification quality release",
            ),
        )
    return product_id, warehouse_id, location_id, work_order_id


def add_check(checks, name: str, passed: bool, detail):
    checks.append((name, bool(passed), "" if detail is None else str(detail)))


def dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def assert_redirect(checks, name: str, response):
    add_check(checks, name, response.status_code in {302, 303}, f"status_code={response.status_code} location={response.headers.get('Location')}")


def stock_sum_sql(cur):
    if has_column(cur, "stock_transactions", "source_doc_no"):
        return """
            SELECT COALESCE(SUM(quantity),0)
            FROM stock_transactions
            WHERE reference_no=%s OR source_doc_no=%s
        """
    return """
        SELECT COALESCE(SUM(quantity),0)
        FROM stock_transactions
        WHERE reference_no=%s
    """


def main() -> int:
    os.environ.setdefault("INVENTORY_SECRET_KEY", "production-completion-closure-verification")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    checks = []
    data_issues = []

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
                "quantity": str(EXPECTED_QTY),
                "failed_quantity": "0",
                "unit_cost": "120",
                "warehouse_id": str(warehouse_id or ""),
                "location_id": str(location_id or ""),
                "lot_no": LOT_NO,
                "serial_no": SERIAL_NO,
                "remark": "完工闭环验证",
                "save_action": "draft",
            },
            follow_redirects=False,
        )
        assert_redirect(checks, "create_draft_redirect", response)

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM production_completion_orders WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (work_order_id,))
            doc = cur.fetchone() or {}
            doc_id = doc.get("id")
            completion_no = doc.get("completion_no")
            add_check(checks, "draft_created", bool(doc_id), f"id={doc_id} no={completion_no}")
            add_check(checks, "draft_status", doc.get("status") == "草稿", doc.get("status"))
            add_check(checks, "trace_project_copied", doc.get("project_code") == PROJECT_CODE, doc.get("project_code"))
            add_check(checks, "trace_serial_copied", doc.get("serial_no") == SERIAL_NO, doc.get("serial_no"))
        conn.commit()
    finally:
        conn.close()

    if not doc_id:
        print("production_completion_closure=failed")
        print("checked_items=0")
        print("failed | draft_created | completion document was not created")
        return 1

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"
        response = client.post(f"/production-completions/{doc_id}/submit", follow_redirects=False)
        assert_redirect(checks, "submit_redirect", response)
        response = client.post(f"/production-completions/{doc_id}/post", follow_redirects=False)
        assert_redirect(checks, "post_redirect", response)

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM production_completion_orders WHERE id=%s", (doc_id,))
            doc = cur.fetchone() or {}
            completion_no = doc.get("completion_no")
            add_check(checks, "posted_status", doc.get("status") == "已过账", doc.get("status"))
            add_check(checks, "posted_timestamp", bool(doc.get("posted_at")), doc.get("posted_at"))
            add_check(checks, "legacy_linked", bool(doc.get("wo_complete_item_id")), doc.get("wo_complete_item_id"))
            cur.execute("SELECT * FROM wo_complete_items WHERE source_doc_no=%s ORDER BY id DESC LIMIT 1", (completion_no,))
            legacy = cur.fetchone() or {}
            add_check(checks, "legacy_source_doc_type", legacy.get("source_doc_type") == "production_completion", legacy.get("source_doc_type"))
            add_check(checks, "legacy_qty", dec(legacy.get("qty")) == EXPECTED_QTY, legacy.get("qty"))
            add_check(checks, "legacy_trace_serial", legacy.get("serial_no") == SERIAL_NO, legacy.get("serial_no"))
            stock_qty = scalar(cur, stock_sum_sql(cur), (completion_no, completion_no))
            add_check(checks, "posted_stock_net_qty", dec(stock_qty) == EXPECTED_QTY, stock_qty)
            tx_type = scalar(cur, "SELECT transaction_type FROM stock_transactions WHERE reference_no=%s ORDER BY id DESC LIMIT 1", (completion_no,))
            add_check(checks, "posted_stock_tx_type", tx_type == "工单完工入库", tx_type)
            balance_qty = scalar(
                cur,
                """
                SELECT COALESCE(SUM(quantity),0)
                FROM inventory_balances
                WHERE product_id=%s AND COALESCE(project_code,'')=%s AND COALESCE(serial_no,'')=%s
                """,
                (product_id, PROJECT_CODE, SERIAL_NO),
            )
            add_check(checks, "posted_inventory_balance", dec(balance_qty) == EXPECTED_QTY, balance_qty)
            wo_status = scalar(cur, "SELECT status FROM work_orders WHERE id=%s", (work_order_id,))
            add_check(checks, "work_order_marked_complete", wo_status in {"已完工", "已完成", "completed"}, wo_status)
            for column in ("completed_qty", "complete_qty", "finished_qty"):
                if has_column(cur, "work_orders", column):
                    qty = scalar(cur, f"SELECT COALESCE({column},0) FROM work_orders WHERE id=%s", (work_order_id,))
                    add_check(checks, f"work_order_{column}", dec(qty) == EXPECTED_QTY, qty)
    finally:
        conn.close()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"
        response = client.post(f"/production-completions/{doc_id}/reverse", follow_redirects=False)
        assert_redirect(checks, "reverse_redirect", response)

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM production_completion_orders WHERE id=%s", (doc_id,))
            doc = cur.fetchone() or {}
            completion_no = doc.get("completion_no")
            add_check(checks, "reversed_status", doc.get("status") == "已反过账", doc.get("status"))
            add_check(checks, "reversed_timestamp", bool(doc.get("reverse_posted_at")), doc.get("reverse_posted_at"))
            legacy_qty_after = scalar(cur, "SELECT COALESCE(SUM(qty),0) FROM wo_complete_items WHERE source_doc_no=%s", (completion_no,))
            add_check(checks, "legacy_qty_reversed", dec(legacy_qty_after) == 0, legacy_qty_after)
            legacy_reversed = scalar(cur, "SELECT COALESCE(bool_or(reverse_posted), FALSE) FROM wo_complete_items WHERE source_doc_no=%s", (completion_no,))
            add_check(checks, "legacy_reverse_flag", bool(legacy_reversed), legacy_reversed)
            stock_qty_after = scalar(cur, stock_sum_sql(cur), (completion_no, completion_no))
            add_check(checks, "stock_net_qty_reversed", dec(stock_qty_after) == 0, stock_qty_after)
            reverse_tx = scalar(cur, "SELECT transaction_type FROM stock_transactions WHERE reference_no=%s ORDER BY id DESC LIMIT 1", (completion_no,))
            add_check(checks, "reverse_stock_tx_type", reverse_tx == "完工入库反过账", reverse_tx)
            balance_qty_after = scalar(
                cur,
                """
                SELECT COALESCE(SUM(quantity),0)
                FROM inventory_balances
                WHERE product_id=%s AND COALESCE(project_code,'')=%s AND COALESCE(serial_no,'')=%s
                """,
                (product_id, PROJECT_CODE, SERIAL_NO),
            )
            add_check(checks, "inventory_balance_reversed", dec(balance_qty_after) == 0, balance_qty_after)
            wo_status_after = scalar(cur, "SELECT status FROM work_orders WHERE id=%s", (work_order_id,))
            add_check(checks, "work_order_reopened_after_reverse", wo_status_after not in {"已完工", "已完成", "completed"}, wo_status_after)
            if wo_status_after in {"已完工", "已完成", "completed"}:
                data_issues.append(f"work order remained final after reverse: {wo_status_after}")
    finally:
        conn.close()

    failures = [check for check in checks if not check[1]]
    print(f"production_completion_closure={'ok' if not failures else 'failed'}")
    print(f"checked_items={len(checks)}")
    for name, passed, detail in checks:
        print(f"{'ok' if passed else 'failed'} | {name} | {detail}")
    print(f"data_issues={len(data_issues)}")
    for issue in data_issues:
        print(f"data_issue | {issue}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
