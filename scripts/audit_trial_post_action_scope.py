from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


PROJECT_CODE = "PJ-GT-TRIAL-20260526-001"
SERIAL_NO = "SN-GT-TRIAL-20260526-001"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def table_exists(cur, table_name):
    cur.execute("SELECT to_regclass(%s) AS table_name", (table_name,))
    row = cur.fetchone() or {}
    return bool(row.get("table_name"))


def fetch_optional_id(cur, table_name):
    if not table_exists(cur, table_name):
        return None
    row = fetch_one(cur, f"SELECT id FROM {table_name} ORDER BY id DESC LIMIT 1")
    return row["id"] if row else None


def load_trial_ids():
    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            sales_order = fetch_one(
                cur,
                "SELECT id FROM sales_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (PROJECT_CODE, SERIAL_NO),
            )
            purchase_order = fetch_one(
                cur,
                "SELECT id FROM purchase_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (PROJECT_CODE, SERIAL_NO),
            )
            work_order = fetch_one(
                cur,
                "SELECT id FROM work_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (PROJECT_CODE, SERIAL_NO),
            )
            service_order = fetch_one(
                cur,
                "SELECT id FROM machine_service_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (PROJECT_CODE, SERIAL_NO),
            )
            receivable = fetch_one(
                cur,
                "SELECT id FROM customer_receivables WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (PROJECT_CODE, SERIAL_NO),
            )
            payable = fetch_one(
                cur,
                """
                SELECT sp.id
                FROM supplier_payables sp
                JOIN purchase_orders po ON po.id=sp.doc_id AND sp.doc_type='purchase_order'
                WHERE po.project_code=%s AND po.serial_no=%s
                ORDER BY sp.id DESC
                LIMIT 1
                """,
                (PROJECT_CODE, SERIAL_NO),
            )
            adjustment_id = fetch_optional_id(cur, "inventory_adjustments")
            transfer_id = fetch_optional_id(cur, "transfer_orders")
            inventory_check_id = fetch_optional_id(cur, "inventory_check_orders")
    finally:
        conn.close()

    return {
        "sales": sales_order["id"] if sales_order else None,
        "purchase": purchase_order["id"] if purchase_order else None,
        "work_order": work_order["id"] if work_order else None,
        "service_order": service_order["id"] if service_order else None,
        "receivable": receivable["id"] if receivable else None,
        "payable": payable["id"] if payable else None,
        "adjustment": adjustment_id,
        "transfer": transfer_id,
        "inventory_check": inventory_check_id,
    }


def build_cases(ids):
    warehouse_allowed = []
    if ids["adjustment"]:
        warehouse_allowed.append(("POST", f"/adjustments/{ids['adjustment']}/notes"))
    if ids["transfer"]:
        warehouse_allowed.append(("POST", f"/transfers/{ids['transfer']}/notes"))
    if ids["inventory_check"]:
        warehouse_allowed.append(("POST", f"/inventory_checks/{ids['inventory_check']}/notes"))
    if not warehouse_allowed:
        warehouse_allowed.append(("POST", "/adjustments/new"))

    return {
        "pilot_sales": {
            "allowed": [
                ("POST", f"/sales/{ids['sales']}/notes"),
                ("POST", f"/receivables/{ids['receivable']}/notes"),
                ("POST", f"/service-orders/{ids['service_order']}/notes"),
            ],
            "forbidden": [("POST", f"/purchase_order/{ids['purchase']}/notes"), ("POST", f"/work-orders/{ids['work_order']}/notes")],
        },
        "pilot_purchase": {
            "allowed": [("POST", f"/purchase_order/{ids['purchase']}/notes"), ("POST", f"/payables/{ids['payable']}/notes")],
            "forbidden": [("POST", f"/sales/{ids['sales']}/notes"), ("POST", f"/work-orders/{ids['work_order']}/notes"), ("POST", f"/service-orders/{ids['service_order']}/notes")],
        },
        "pilot_warehouse": {
            "allowed": warehouse_allowed,
            "forbidden": [("POST", f"/sales/{ids['sales']}/notes"), ("POST", f"/purchase_order/{ids['purchase']}/notes"), ("POST", f"/service-orders/{ids['service_order']}/notes")],
        },
        "pilot_production": {
            "allowed": [("POST", f"/work-orders/{ids['work_order']}/notes")],
            "forbidden": [("POST", f"/sales/{ids['sales']}/notes"), ("POST", f"/purchase_order/{ids['purchase']}/notes"), ("POST", f"/service-orders/{ids['service_order']}/notes")],
        },
        "pilot_service": {
            "allowed": [("POST", f"/service-orders/{ids['service_order']}/notes")],
            "forbidden": [("POST", f"/sales/{ids['sales']}/notes"), ("POST", f"/purchase_order/{ids['purchase']}/notes"), ("POST", f"/work-orders/{ids['work_order']}/notes")],
        },
        "pilot_finance": {
            "allowed": [("POST", f"/receivables/{ids['receivable']}/notes"), ("POST", f"/payables/{ids['payable']}/notes")],
            "forbidden": [("POST", f"/sales/{ids['sales']}/notes"), ("POST", f"/purchase_order/{ids['purchase']}/notes"), ("POST", f"/work-orders/{ids['work_order']}/notes"), ("POST", f"/service-orders/{ids['service_order']}/notes")],
        },
    }


def request_path(client, method, path, username):
    data = {"note": f"trial post scope audit {username}"}
    if path == "/adjustments/new":
        data = {}
    if method == "POST":
        return client.post(path, data=data, follow_redirects=False)
    return client.get(path, follow_redirects=False)


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-post-action-scope")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    ids = load_trial_ids()
    required = ["sales", "purchase", "work_order", "service_order", "receivable", "payable"]
    missing = [name for name in required if not ids.get(name)]
    checks = [(f"trial_id:{name}", bool(ids.get(name)), ids.get(name) or "missing") for name in required]
    if missing:
        print("trial_post_action_scope_audit=failed")
        print(f"checked_items={len(checks)}")
        for name, ok, detail in checks:
            print(f"{'ok' if ok else 'failed'} | bootstrap | {name} | {detail}")
        return 1

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    passwords = load_passwords()
    cases = build_cases(ids)

    for username, role_cases in cases.items():
        password = passwords.get(username)
        if not password:
            checks.append((username, False, "missing password handoff"))
            continue
        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append((f"{username}:login", login.status_code == 302, login.status_code))
        if login.status_code != 302:
            continue
        for method, path in role_cases["allowed"]:
            response = request_path(client, method, path, username)
            checks.append((f"{username}:allow {method} {path}", response.status_code in {302, 303}, response.status_code))
        for method, path in role_cases["forbidden"]:
            response = request_path(client, method, path, username)
            checks.append((f"{username}:forbid {method} {path}", response.status_code == 403, response.status_code))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("trial_post_action_scope_audit=ok" if not failures else "trial_post_action_scope_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={PROJECT_CODE}")
    print(f"serial_no={SERIAL_NO}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
