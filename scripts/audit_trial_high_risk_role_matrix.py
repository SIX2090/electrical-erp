from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


HIGH_RISK_FORBIDDEN_CASES = {
    "pilot_sales": [
        ("POST", "/users/add"),
        ("POST", "/system/apply-mechanical-defaults"),
        ("GET", "/adjustments/new"),
        ("GET", "/finance/period-close"),
        ("POST", "/material/1/delete"),
        ("POST", "/sales/1/void"),
    ],
    "pilot_purchase": [
        ("POST", "/users/add"),
        ("POST", "/system/apply-mechanical-defaults"),
        ("GET", "/finance/period-close"),
        ("POST", "/material/1/delete"),
        ("POST", "/purchase_order/1/void"),
    ],
    "pilot_warehouse": [
        ("POST", "/users/add"),
        ("POST", "/system/apply-mechanical-defaults"),
        ("GET", "/finance/period-close"),
        ("POST", "/warehouse/1/delete"),
        ("POST", "/adjustments/1/attachments/1/delete"),
    ],
    "pilot_production": [
        ("POST", "/users/add"),
        ("POST", "/system/apply-mechanical-defaults"),
        ("GET", "/adjustments/new"),
        ("GET", "/finance/period-close"),
        ("POST", "/work-orders/1/attachments/1/delete"),
        ("POST", "/sales/1/void"),
    ],
    "pilot_service": [
        ("POST", "/users/add"),
        ("POST", "/system/apply-mechanical-defaults"),
        ("GET", "/adjustments/new"),
        ("GET", "/finance/period-close"),
        ("POST", "/service-orders/1/attachments/1/delete"),
        ("POST", "/sales/1/void"),
    ],
    "pilot_finance": [
        ("POST", "/users/add"),
        ("POST", "/system/apply-mechanical-defaults"),
        ("GET", "/adjustments/new"),
        ("POST", "/payables/1/attachments/1/delete"),
        ("POST", "/sales/1/void"),
    ],
}

SAFE_ALLOWED_CASES = {
    "pilot_admin": [("GET", "/users"), ("GET", "/permissions/roles"), ("GET", "/finance/period-close")],
    "pilot_warehouse": [("GET", "/adjustments/new")],
    "pilot_finance": [("GET", "/finance/period-close"), ("GET", "/finance/financial-statements")],
}


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def request_path(client, method, path):
    if method == "POST":
        return client.post(path, data={}, follow_redirects=False)
    return client.get(path, follow_redirects=False)


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-high-risk-role-matrix")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    passwords = load_passwords()
    checks = []

    users = sorted(set(HIGH_RISK_FORBIDDEN_CASES) | set(SAFE_ALLOWED_CASES))
    for username in users:
        password = passwords.get(username)
        if not password:
            checks.append((username, "login", False, "missing password handoff"))
            continue
        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append((username, "login", login.status_code == 302, login.status_code))
        if login.status_code != 302:
            continue

        for method, path in HIGH_RISK_FORBIDDEN_CASES.get(username, []):
            response = request_path(client, method, path)
            checks.append((username, f"forbid {method} {path}", response.status_code == 403, response.status_code))

        for method, path in SAFE_ALLOWED_CASES.get(username, []):
            response = request_path(client, method, path)
            checks.append((username, f"allow {method} {path}", response.status_code < 400, response.status_code))

    failures = [(user, name, detail) for user, name, ok, detail in checks if not ok]
    print("trial_high_risk_role_matrix_audit=ok" if not failures else "trial_high_risk_role_matrix_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"checked_users={len(users)}")
    for user, name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {user} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
