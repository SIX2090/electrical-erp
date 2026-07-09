from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_trial_visible_navigation import ROLE_NAMES
from services.pilot_permissions import default_groups_for_role, pilot_paths_for_groups


ROLE_ALLOWED_NAV = {
    username: pilot_paths_for_groups(default_groups_for_role(role_name))
    for username, role_name in ROLE_NAMES.items()
}

DIRECT_SCOPE_PATHS = sorted({path for allowed_paths in ROLE_ALLOWED_NAV.values() for path in allowed_paths})
ROLE_DENIED_DIRECT_PATHS = {
    "pilot_purchase": {"/adjustments/new"},
    "pilot_production": {"/adjustments/new"},
}


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-direct-access-matrix")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    passwords = load_passwords()
    checks = []

    for username, allowed_paths in ROLE_ALLOWED_NAV.items():
        password = passwords.get(username)
        if not password:
            checks.append((username, "password handoff", False, "missing"))
            continue
        client = app.test_client()
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append((username, "login", login.status_code == 302, login.status_code))
        if login.status_code != 302:
            continue

        for path in DIRECT_SCOPE_PATHS:
            response = client.get(path, follow_redirects=False)
            should_allow = path in allowed_paths and path not in ROLE_DENIED_DIRECT_PATHS.get(username, set())
            ok = response.status_code < 400 if should_allow else response.status_code == 403
            expected = "allowed" if should_allow else "forbidden"
            checks.append((username, f"{expected} direct GET {path}", ok, response.status_code))

    failures = [(user, name, detail) for user, name, ok, detail in checks if not ok]
    print("trial_direct_access_matrix_audit=ok" if not failures else "trial_direct_access_matrix_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"checked_users={len(ROLE_ALLOWED_NAV)}")
    print(f"checked_paths={len(DIRECT_SCOPE_PATHS)}")
    for user, name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {user} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
