import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def login_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "finance-voucher-preview-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_finance", "password": login_password("pilot_finance")})
    findings = []
    if login.status_code not in {302, 303}:
        findings.append(f"login_failed status={login.status_code}")

    response = client.get("/finance/vouchers/generate")
    body = response.get_data(as_text=True)
    required_tokens = [
        "Voucher Generation Preview",
        "Read-only voucher source preview",
        "Pending Voucher Sources",
        "Generated Voucher Sources",
        "Voucher Rule",
        "does not create vouchers",
        "does not post",
    ]
    for token in required_tokens:
        if token not in body:
            findings.append(f"missing_token={token}")
    blocked_tokens = ["button type=\"submit\"", "form method=\"post\"", "Auto Generate Now"]
    for token in blocked_tokens:
        if token in body:
            findings.append(f"write_action_present={token}")
    if response.status_code != 200:
        findings.append(f"bad_status={response.status_code}")
    if any(marker in body for marker in ["???", "\ufffd"]):
        findings.append("dirty_text_marker_present")

    if findings:
        print("finance_voucher_generation_preview_audit=fail")
        for finding in findings:
            print(finding)
        return 1
    print("finance_voucher_generation_preview_audit=ok")
    print(f"checked_tokens={len(required_tokens)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
