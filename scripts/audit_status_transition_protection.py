from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("INVENTORY_SECRET_KEY", "status-transition-protection-audit")

from app import create_app  # noqa: E402
from services.app_runtime import connect_db  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402


AUDIT_PREFIX = "STATUS-AUDIT-20260603"


def db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def scalar(cur, sql, params=()):
    row = fetch_one(cur, sql, params)
    if not row:
        return None
    return next(iter(row.values()))


def login_admin(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "status_audit"
        session["role"] = "admin"


def source_contract_checks():
    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    finance = (ROOT / "routes" / "finance_routes.py").read_text(encoding="utf-8")
    checks = []

    def check(name, ok, detail):
        checks.append((name, bool(ok), detail))

    for token in [
        "def _order_downstream_execution(kind, order_id):",
        '"已提交": {"", "待提交", "草稿", "draft", "pending"}',
        '"已审核": {"已提交", "submitted"}',
        'if current_status in terminal_statuses:',
        'action in {"unaudit", "void"} and (executed_qty > 0 or downstream_count > 0)',
        'action == "close" and current_status not in',
    ]:
        check(f"sales_purchase_guard:{token[:45]}", token in registry, token)
    for token in [
        "SELECT status FROM inventory_adjustments WHERE id=%s FOR UPDATE",
        "SELECT status FROM transfer_orders WHERE id=%s FOR UPDATE",
        "SELECT status FROM inventory_check_orders WHERE id=%s FOR UPDATE",
        "SELECT status FROM inventory_assembly_orders WHERE id=%s AND doc_type=%s FOR UPDATE",
    ]:
        check(f"inventory_double_post_guard:{token[:45]}", token in registry, token)
    for token in [
        'status == "audited"',
        "not row.get(\"posted\")",
        "reverse_posted_at=CURRENT_TIMESTAMP",
        "已审核单据需先反审核",
    ]:
        check(f"subcontract_reverse_guard:{token[:45]}", token in registry, token)
    for token in [
        "def _funds_action_flags(doc):",
        '"can_edit": _is_draft_funds_status(status) and settled_amount <= 0',
        '"can_reverse_settlement": settled_amount > 0 and not _is_final_funds_status(status)',
        "post_customer_receipt_reverse_settlement",
        "post_supplier_payment_reverse_settlement",
    ]:
        check(f"finance_settlement_guard:{token[:45]}", token in finance, token)
    return checks


def make_sales_order(cur, status, suffix, customer_id):
    order_no = f"{AUDIT_PREFIX}-SO-{suffix}"
    row = fetch_one(
        cur,
        """
        INSERT INTO sales_orders
            (order_no, order_date, customer_id, status, total_amount, shipped_amount, remark)
        VALUES (%s, CURRENT_DATE, %s, %s, 0, 0, %s)
        RETURNING id, order_no
        """,
        (order_no, customer_id, status, AUDIT_PREFIX),
    )
    return row["id"]


def make_purchase_order(cur, status, suffix, supplier_id):
    order_no = f"{AUDIT_PREFIX}-PO-{suffix}"
    row = fetch_one(
        cur,
        """
        INSERT INTO purchase_orders
            (order_no, order_date, supplier_id, status, total_amount, received_amount, remark)
        VALUES (%s, CURRENT_DATE, %s, %s, 0, 0, %s)
        RETURNING id, order_no
        """,
        (order_no, supplier_id, status, AUDIT_PREFIX),
    )
    return row["id"]


def cleanup(cur):
    cur.execute(
        """
        DELETE FROM sales_order_items
        WHERE order_id IN (SELECT id FROM sales_orders WHERE remark=%s)
        """,
        (AUDIT_PREFIX,),
    )
    cur.execute("DELETE FROM sales_orders WHERE remark=%s", (AUDIT_PREFIX,))
    cur.execute(
        """
        DELETE FROM purchase_order_items
        WHERE order_id IN (SELECT id FROM purchase_orders WHERE remark=%s)
        """,
        (AUDIT_PREFIX,),
    )
    cur.execute("DELETE FROM purchase_orders WHERE remark=%s", (AUDIT_PREFIX,))


def runtime_transition_checks():
    checks = []
    conn = connect_db(db_config())
    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    try:
        with conn.cursor() as cur:
            cleanup(cur)
            product_id = scalar(cur, "SELECT id FROM products ORDER BY id LIMIT 1")
            customer_id = scalar(cur, "SELECT id FROM customers ORDER BY id LIMIT 1")
            supplier_id = scalar(cur, "SELECT id FROM suppliers ORDER BY id LIMIT 1")
            missing_master = [
                name
                for name, value in (("product", product_id), ("customer", customer_id), ("supplier", supplier_id))
                if not value
            ]
            if missing_master:
                checks.append(("runtime:master_data", False, "missing " + ",".join(missing_master)))
                conn.commit()
                return checks

            sales_closed_id = make_sales_order(cur, "已关闭", "CLOSED", customer_id)
            purchase_closed_id = make_purchase_order(cur, "已关闭", "CLOSED", supplier_id)
            sales_audited_id = make_sales_order(cur, "已审核", "EXEC", customer_id)
            purchase_audited_id = make_purchase_order(cur, "已审核", "EXEC", supplier_id)
            cur.execute(
                """
                INSERT INTO sales_order_items
                    (order_id, product_id, quantity, shipped_qty, unit_price, amount)
                VALUES (%s, %s, 1, 1, 0, 0)
                """,
                (sales_audited_id, product_id),
            )
            cur.execute(
                """
                INSERT INTO purchase_order_items
                    (order_id, product_id, quantity, received_qty, unit_price, amount)
                VALUES (%s, %s, 1, 1, 0, 0)
                """,
                (purchase_audited_id, product_id),
            )
            conn.commit()

            with app.test_client() as client:
                login_admin(client)
                cases = [
                    ("sales_closed_submit_blocked", f"/sales/{sales_closed_id}/submit", "sales_orders", sales_closed_id, "已关闭"),
                    ("purchase_closed_submit_blocked", f"/purchase_order/{purchase_closed_id}/submit", "purchase_orders", purchase_closed_id, "已关闭"),
                    ("sales_executed_unaudit_blocked", f"/sales/{sales_audited_id}/unaudit", "sales_orders", sales_audited_id, "已审核"),
                    ("purchase_executed_unaudit_blocked", f"/purchase_order/{purchase_audited_id}/unaudit", "purchase_orders", purchase_audited_id, "已审核"),
                ]
                for name, path, table, record_id, expected_status in cases:
                    response = client.post(path, data={}, follow_redirects=False)
                    current_status = scalar(cur, f"SELECT status FROM {table} WHERE id=%s", (record_id,))
                    checks.append((name, response.status_code in {302, 303} and current_status == expected_status, f"{response.status_code}:{current_status}"))
    except Exception:
        conn.rollback()
        raise
    finally:
        with conn.cursor() as cur:
            cleanup(cur)
        conn.commit()
        conn.close()
    return checks


def main():
    checks = []
    checks.extend(source_contract_checks())
    checks.extend(runtime_transition_checks())
    failures = [row for row in checks if not row[1]]
    print("status_transition_protection_audit=ok" if not failures else "status_transition_protection_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
