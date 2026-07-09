from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


DELETED_WORKBENCH_ROOTS = {
    "/after-sale",
    "/system_settings",
}

LEGACY_REDIRECTS = {
    "/purchase_order": "/purchase-orders",
}

ACCESS_CASES = {
    "pilot_admin": {
        "allowed": ["/users", "/permissions/roles", "/finance/period-close", "/adjustments/new"],
        "forbidden": [],
    },
    "pilot_sales": {
        "allowed": [
            "/projects",
            "/sales-orders",
            "/shipments",
            "/quotations",
            "/sales-returns",
            "/sales-invoices",
            "/receivables",
            "/customer-receipts",
        ],
        "forbidden": ["/users", "/adjustments/new"],
    },
    "pilot_purchase": {
        "allowed": ["/engineering/technical-confirmations", "/engineering/technical-confirmations/new", "/engineering/drawings", "/engineering/drawings/new", "/work-centers", "/purchase_request", "/purchase-orders", "/purchase_receipts", "/subcontract"],
        "forbidden": ["/users", "/finance/period-close"],
    },
    "pilot_warehouse": {
        "allowed": ["/inventory/detail", "/transactions", "/adjustments/new"],
        "forbidden": ["/users", "/finance/period-close"],
    },
    "pilot_production": {
        "allowed": ["/engineering/technical-confirmations", "/engineering/technical-confirmations/new", "/engineering/drawings", "/engineering/drawings/new", "/work-orders", "/work-orders/new", "/engineering/kitting", "/production-enhance/mrp-requirements", "/procurement/suggestions", "/requisition", "/production-schedules"],
        "forbidden": ["/users", "/finance/period-close", "/adjustments/new"],
    },
    "pilot_service": {
        "allowed": ["/service-cards", "/service-orders", "/service-rmas"],
        "forbidden": ["/users", "/finance/period-close", "/adjustments/new"],
    },
    "pilot_finance": {
        "allowed": ["/receivables", "/payables", "/finance/period-close", "/finance/financial-statements"],
        "forbidden": ["/users", "/adjustments/new"],
    },
}


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-access-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    passwords = load_passwords()
    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000})
    failures = []

    for username, checks in ACCESS_CASES.items():
        password = passwords.get(username)
        if not password:
            failures.append(f"{username}: missing password handoff")
            continue
        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password})
        if login.status_code != 302:
            failures.append(f"{username}: login returned {login.status_code}")
            continue

        for path in checks["allowed"]:
            response = client.get(path)
            if response.status_code >= 400:
                failures.append(f"{username}: expected allowed {path}, got {response.status_code}")
        for path in checks["forbidden"]:
            response = client.get(path)
            if response.status_code != 403:
                failures.append(f"{username}: expected forbidden {path}, got {response.status_code}")
        for path in sorted(DELETED_WORKBENCH_ROOTS):
            response = client.get(path)
            if response.status_code != 404:
                failures.append(f"{username}: expected deleted workbench {path} to return 404, got {response.status_code}")
        for path, target in sorted(LEGACY_REDIRECTS.items()):
            response = client.get(path, follow_redirects=False)
            if response.status_code not in {301, 302, 303, 308} or response.headers.get("Location") != target:
                failures.append(f"{username}: expected legacy redirect {path} to {target}, got {response.status_code} {response.headers.get('Location')}")

    if failures:
        print("trial_access_audit=failed")
        for item in failures:
            print(item)
        return 1
    print("trial_access_audit=ok")
    print(f"checked_users={len(ACCESS_CASES)}")
    checked_paths = sum(len(case["allowed"]) + len(case["forbidden"]) for case in ACCESS_CASES.values())
    checked_paths += len(ACCESS_CASES) * len(DELETED_WORKBENCH_ROOTS)
    checked_paths += len(ACCESS_CASES) * len(LEGACY_REDIRECTS)
    print(f"checked_paths={checked_paths}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
