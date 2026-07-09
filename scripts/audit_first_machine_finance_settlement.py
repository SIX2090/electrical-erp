from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def load_trial_values():
    values = {
        "project_code": "PJ-GT-TRIAL-20260526-001",
        "serial_no": "SN-GT-TRIAL-20260526-001",
    }
    if not TEMPLATE.exists():
        return values
    with TEMPLATE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            actual = (row[1] or "").strip()
            if actual.startswith("PJ-GT-"):
                values["project_code"] = actual
            elif actual.startswith("SN-GT-"):
                values["serial_no"] = actual
    return values


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-finance-settlement")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_trial_values()
    project_code = values["project_code"]
    serial_no = values["serial_no"]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            sales_order = fetch_one(
                cur,
                "SELECT * FROM sales_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (project_code, serial_no),
            )
            purchase_order = fetch_one(
                cur,
                "SELECT * FROM purchase_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (project_code, serial_no),
            )
            receivable_before = fetch_one(
                cur,
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(balance),0) AS balance
                FROM customer_receivables
                WHERE project_code=%s AND serial_no=%s
                """,
                (project_code, serial_no),
            )
            payable_before = fetch_one(
                cur,
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(sp.balance),0) AS balance
                FROM supplier_payables sp
                JOIN purchase_orders po ON po.id=sp.doc_id AND sp.doc_type='purchase_order'
                WHERE po.project_code=%s AND po.serial_no=%s
                """,
                (project_code, serial_no),
            )
            checks.append(("sales_order_ready", bool(sales_order), sales_order.get("order_no") if sales_order else "missing"))
            checks.append(("purchase_order_ready", bool(purchase_order), purchase_order.get("order_no") if purchase_order else "missing"))
            checks.append(("receivable_ready", int(receivable_before.get("lines") or 0) >= 1, receivable_before.get("balance")))
            checks.append(("purchase_payable_ready", int(payable_before.get("lines") or 0) >= 1, payable_before.get("balance")))
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_finance", "password": load_password("pilot_finance")})
    checks.append(("pilot_finance_login", login.status_code == 302, login.status_code))

    if login.status_code == 302 and sales_order and receivable_before.get("balance", 0) > 0:
        amount = min(receivable_before.get("balance", 0), 1000)
        response = client.post(
            f"/sales/{sales_order['id']}/receive-payment",
            data={"amount": str(amount), "payment_method": "bank", "remark": "first machine settlement audit"},
            follow_redirects=False,
        )
        checks.append(("customer_receipt_posted", response.status_code in {302, 303}, response.status_code))
    else:
        checks.append(("customer_receipt_posted", True, "no open receivable"))

    if login.status_code == 302 and purchase_order and payable_before.get("balance", 0) > 0:
        amount = min(payable_before.get("balance", 0), 1000)
        response = client.post(
            f"/purchase_order/{purchase_order['id']}/pay",
            data={"amount": str(amount), "payment_method": "bank", "remark": "first machine payment audit"},
            follow_redirects=False,
        )
        checks.append(("supplier_payment_posted", response.status_code in {302, 303}, response.status_code))
    else:
        checks.append(("supplier_payment_posted", True, "no open payable"))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            receivable_after = fetch_one(
                cur,
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(received_amount),0) AS received_amount,
                       COALESCE(SUM(balance),0) AS balance
                FROM customer_receivables
                WHERE project_code=%s AND serial_no=%s
                """,
                (project_code, serial_no),
            )
            receipt = fetch_one(
                cur,
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(r.amount),0) AS amount
                FROM customer_receipts r
                JOIN customer_receivables cr ON cr.customer_id=r.customer_id
                WHERE cr.project_code=%s AND cr.serial_no=%s
                """,
                (project_code, serial_no),
            )
            payable_after = fetch_one(
                cur,
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(sp.paid_amount),0) AS paid_amount,
                       COALESCE(SUM(sp.balance),0) AS balance
                FROM supplier_payables sp
                JOIN purchase_orders po ON po.id=sp.doc_id AND sp.doc_type='purchase_order'
                WHERE po.project_code=%s AND po.serial_no=%s
                """,
                (project_code, serial_no),
            )
            payment = fetch_one(
                cur,
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(pay.amount),0) AS amount
                FROM supplier_payments pay
                JOIN purchase_orders po ON po.supplier_id=pay.supplier_id
                WHERE po.project_code=%s AND po.serial_no=%s
                """,
                (project_code, serial_no),
            )
            checks.append(("receivable_received_amount_positive", receivable_after.get("received_amount", 0) > 0, receivable_after.get("received_amount")))
            checks.append(("customer_receipt_traceable", int(receipt.get("lines") or 0) >= 1, receipt.get("amount")))
            checks.append(("payable_paid_amount_positive", payable_after.get("paid_amount", 0) > 0, payable_after.get("paid_amount")))
            checks.append(("supplier_payment_traceable", int(payment.get("lines") or 0) >= 1, payment.get("amount")))
    finally:
        conn.close()

    if login.status_code == 302:
        page_expectations = [
            (f"/receivables?keyword={project_code}", [project_code, serial_no]),
            (f"/payables?keyword={purchase_order['order_no'] if purchase_order else project_code}", [purchase_order["order_no"] if purchase_order else "PO"]),
            (f"/finance?keyword={project_code}", []),
            (f"/projects?keyword={project_code}", [project_code, serial_no]),
        ]
        for path, expected in page_expectations:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_finance_settlement_audit=ok" if not failures else "first_machine_finance_settlement_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"serial_no={serial_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
