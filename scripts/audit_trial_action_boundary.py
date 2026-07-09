from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MISSING_ID = 999999999

ACTION_CASES = {
    "sales_submit": {
        "path": f"/sales/{MISSING_ID}/submit",
        "data": {},
        "allowed": {"pilot_sales", "pilot_admin"},
        "forbidden": {"pilot_purchase", "pilot_warehouse", "pilot_production", "pilot_service", "pilot_finance"},
        "allowed_status": {302, 303},
    },
    "sales_ship": {
        "path": f"/sales/{MISSING_ID}/ship",
        "data": {"shipment_date": "2026-05-26"},
        "allowed": {"pilot_sales", "pilot_admin"},
        "forbidden": {"pilot_purchase", "pilot_warehouse", "pilot_production", "pilot_service", "pilot_finance"},
        "allowed_status": {302, 303},
    },
    "purchase_submit": {
        "path": f"/purchase_order/{MISSING_ID}/submit",
        "data": {},
        "allowed": {"pilot_purchase", "pilot_admin"},
        "forbidden": {"pilot_sales", "pilot_warehouse", "pilot_production", "pilot_service", "pilot_finance"},
        "allowed_status": {302, 303},
    },
    "purchase_receive": {
        "path": f"/purchase_order/{MISSING_ID}/receive",
        "json": {},
        "allowed": {"pilot_purchase", "pilot_admin"},
        "forbidden": {"pilot_sales", "pilot_warehouse", "pilot_production", "pilot_service", "pilot_finance"},
        "allowed_status": {404},
    },
    "work_order_complete": {
        "path": f"/work-orders/{MISSING_ID}/complete",
        "data": {"quantity": "1", "serial_no": "SN-ACTION-BOUNDARY"},
        "allowed": {"pilot_production", "pilot_admin"},
        "forbidden": {"pilot_sales", "pilot_purchase", "pilot_warehouse", "pilot_service", "pilot_finance"},
        "allowed_status": {302, 303},
    },
    "service_dispatch": {
        "path": f"/service-orders/{MISSING_ID}/dispatch",
        "data": {"task_summary": "action boundary probe"},
        "allowed": {"pilot_service", "pilot_sales", "pilot_admin"},
        "forbidden": {"pilot_purchase", "pilot_warehouse", "pilot_production", "pilot_finance"},
        "allowed_status": {302, 303},
    },
    "finance_receive_payment": {
        "path": f"/sales/{MISSING_ID}/receive-payment",
        "data": {"amount": "1", "payment_method": "bank"},
        "allowed": {"pilot_finance", "pilot_admin"},
        "forbidden": {"pilot_sales", "pilot_purchase", "pilot_warehouse", "pilot_production", "pilot_service"},
        "allowed_status": {302, 303},
    },
    "finance_supplier_pay": {
        "path": f"/purchase_order/{MISSING_ID}/pay",
        "data": {"amount": "1", "payment_method": "bank"},
        "allowed": {"pilot_finance", "pilot_admin"},
        "forbidden": {"pilot_sales", "pilot_purchase", "pilot_warehouse", "pilot_production", "pilot_service"},
        "allowed_status": {302, 303},
    },
}


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def post_case(client, case):
    if "json" in case:
        return client.post(case["path"], json=case["json"], follow_redirects=False)
    return client.post(case["path"], data=case.get("data") or {}, follow_redirects=False)


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-action-boundary")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    passwords = load_passwords()
    users = sorted(
        {
            username
            for case in ACTION_CASES.values()
            for username in (set(case["allowed"]) | set(case["forbidden"]))
        }
    )
    checks = []

    clients = {}
    for username in users:
        password = passwords.get(username)
        if not password:
            checks.append((username, "login", False, "missing password handoff"))
            continue
        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append((username, "login", login.status_code == 302, login.status_code))
        if login.status_code == 302:
            clients[username] = client

    for action_name, case in ACTION_CASES.items():
        for username in sorted(case["allowed"]):
            client = clients.get(username)
            if not client:
                continue
            response = post_case(client, case)
            ok = response.status_code in case["allowed_status"]
            checks.append((username, f"allow {action_name} {case['path']}", ok, response.status_code))
        for username in sorted(case["forbidden"]):
            client = clients.get(username)
            if not client:
                continue
            response = post_case(client, case)
            checks.append((username, f"forbid {action_name} {case['path']}", response.status_code == 403, response.status_code))

    failures = [(user, name, detail) for user, name, ok, detail in checks if not ok]
    print("trial_action_boundary_audit=ok" if not failures else "trial_action_boundary_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"checked_actions={len(ACTION_CASES)}")
    print(f"probe_id={MISSING_ID}")
    for user, name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {user} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
