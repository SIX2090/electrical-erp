from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")


def _route_body(source: str) -> str:
    match = re.search(
        r"def finance_business_exceptions\(\):(?P<body>.*?)(?=\n    @app\.|\n    def |\n    class |\ndef |\Z)",
        source,
        re.S,
    )
    return match.group("body") if match else ""


def main() -> int:
    findings: list[str] = []
    source = (ROOT / "routes" / "finance_routes.py").read_text(encoding="utf-8", errors="ignore")
    body = _route_body(source)
    if "return render_business_exceptions_report()" not in body:
        findings.append("finance_business_exceptions route does not render the business exception report")
    if "return render_closing_checks_report()" in body:
        findings.append("finance_business_exceptions route still renders closing checks")
    if "def render_business_exceptions_report" not in source:
        findings.append("render_business_exceptions_report is missing")

    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "audit"
            session["role"] = "admin"
        response = client.get("/finance/business-exceptions")
        text = response.get_data(as_text=True)
    if response.status_code != 200:
        findings.append(f"/finance/business-exceptions returned HTTP {response.status_code}")

    required_tokens = [
        "\u4e1a\u52a1\u8d22\u52a1\u5f02\u5e38",
        "\u903e\u671f\u5e94\u6536\u9884\u8b66",
        "\u903e\u671f\u5e94\u4ed8\u9884\u8b66",
        "\u672a\u5f00\u7968\u9500\u552e",
        "\u672a\u5230\u7968\u91c7\u8d2d",
        "\u5b58\u8d27\u4e0e\u603b\u8d26\u5bf9\u8d26",
        "\u9879\u76ee\u8d44\u91d1\u5360\u7528",
    ]
    for token in required_tokens:
        if token not in text:
            findings.append(f"business exception page missing token: {token}")

    if findings:
        print("finance_business_exceptions_audit=failed")
        for finding in findings:
            print(finding)
        return 1
    print("finance_business_exceptions_audit=ok")
    print(f"checked_tokens={len(required_tokens)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
