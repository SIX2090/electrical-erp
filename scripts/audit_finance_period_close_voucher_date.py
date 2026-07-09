import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def login_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")


def main():
    findings = []
    finance_routes = (ROOT / "routes" / "finance_routes.py").read_text(encoding="utf-8")
    bad_tokens = [
        "FROM vouchers WHERE date >=",
        "FROM vouchers\\n        WHERE date >=",
        "vouchers WHERE date >=",
    ]
    for token in bad_tokens:
        if token in finance_routes:
            findings.append(f"bad_voucher_date_sql={token}")
    if "FROM vouchers WHERE voucher_date >= %s AND voucher_date < %s" not in finance_routes:
        findings.append("missing_voucher_date_period_check_sql")

    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "finance-period-close-voucher-date-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_finance", "password": login_password("pilot_finance")})
    if login.status_code not in {302, 303}:
        findings.append(f"login_failed status={login.status_code}")
    response = client.get("/finance/period-close")
    body = response.get_data(as_text=True)
    if response.status_code != 200:
        findings.append(f"period_close_bad_status={response.status_code}")
    if any(marker in body for marker in ["???", "\ufffd"]):
        findings.append("dirty_text_marker_present")
    if "voucher_date" in body:
        findings.append("internal_sql_field_leaked")

    if findings:
        print("finance_period_close_voucher_date_audit=fail")
        for finding in findings:
            print(finding)
        return 1
    print("finance_period_close_voucher_date_audit=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
