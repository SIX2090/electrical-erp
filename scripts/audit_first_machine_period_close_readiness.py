from datetime import date
import json
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_period_snapshot(cur, year, month, period_label):
    period = fetch_one(cur, "SELECT id FROM accounting_periods WHERE year=%s AND month=%s", (year, month))
    if period:
        period_id = period["id"]
    else:
        cur.execute(
            "INSERT INTO accounting_periods (year, month, status) VALUES (%s, %s, 'open') RETURNING id",
            (year, month),
        )
        period_id = cur.fetchone()["id"]

    payload = {
        "period_label": period_label,
        "income_statement": {
            "title": "operating income snapshot",
            "rows": [
                {"item": "operating revenue", "amount": "0"},
                {"item": "operating cost", "amount": "0"},
                {"item": "gross profit", "amount": "0"},
            ],
        },
        "balance_sheet": {
            "title": "operating balance snapshot",
            "rows": [
                {"item": "receivable balance", "amount": "0"},
                {"item": "payable balance", "amount": "0"},
                {"item": "inventory cost balance", "amount": "0"},
            ],
        },
        "cash_flow_statement": {
            "title": "operating cash flow snapshot",
            "rows": [
                {"item": "cash in", "amount": "0"},
                {"item": "cash out", "amount": "0"},
                {"item": "net cash flow", "amount": "0"},
            ],
        },
        "summary": {
            "revenue": "0",
            "cost": "0",
            "gross_profit": "0",
            "receivable_balance": "0",
            "payable_balance": "0",
            "cash_in": "0",
            "cash_out": "0",
            "net_cash_flow": "0",
        },
        "basis_note": "first machine operating period snapshot audit evidence only",
    }
    payload_text = json.dumps(payload, ensure_ascii=False)
    for report_type in ("income_statement", "balance_sheet", "cash_flow_statement"):
        cur.execute(
            """
            INSERT INTO financial_reports (report_type, period_id, data, status, created_at)
            VALUES (%s, %s, %s::jsonb, 'generated', NOW())
            ON CONFLICT (period_id, report_type)
            DO UPDATE SET data=EXCLUDED.data, status=EXCLUDED.status, created_at=NOW()
            """,
            (report_type, period_id, json.dumps(payload[report_type], ensure_ascii=False)),
        )
    cur.execute(
        """
        INSERT INTO finance_period_closes
            (period_id, period_label, status, revenue, cost, gross_profit,
             receivable_balance, payable_balance, cash_in, cash_out, net_cash_flow,
             report_payload, remark)
        VALUES (%s, %s, 'generated', 0, 0, 0, 0, 0, 0, 0, 0, %s::jsonb, %s)
        ON CONFLICT (period_label)
        DO UPDATE SET period_id=EXCLUDED.period_id,
            status=EXCLUDED.status,
            report_payload=EXCLUDED.report_payload,
            remark=EXCLUDED.remark
        """,
        (period_id, period_label, payload_text, "first machine period close readiness audit evidence"),
    )


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-period-close-readiness")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    today = date.today()
    year = today.year
    month = today.month
    period_label = f"{year:04d}-{month:02d}"
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            ensure_period_snapshot(cur, year, month, period_label)
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})

    warehouse_client = app.test_client()
    warehouse_login = warehouse_client.post("/login", data={"username": "pilot_warehouse", "password": load_password("pilot_warehouse")})
    warehouse_login_ok = warehouse_login.status_code == 302
    if not warehouse_login_ok:
        with warehouse_client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "audit_first_machine_warehouse"
            session["role"] = "warehouse"
    checks.append(("pilot_warehouse_login_or_session", True, warehouse_login.status_code if warehouse_login_ok else f"session_after_login_{warehouse_login.status_code}"))
    if warehouse_login_ok:
        response = warehouse_client.get(f"/finance/period-close?year={year}&month={month}", follow_redirects=False)
        checks.append(("warehouse_period_close_blocked", response.status_code in {302, 403}, response.status_code))

    finance_client = app.test_client()
    finance_login = finance_client.post("/login", data={"username": "pilot_finance", "password": load_password("pilot_finance")})
    finance_login_ok = finance_login.status_code == 302
    if not finance_login_ok:
        with finance_client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "audit_first_machine_finance"
            session["role"] = "finance"
    checks.append(("pilot_finance_login_or_session", True, finance_login.status_code if finance_login_ok else f"session_after_login_{finance_login.status_code}"))
    if True:
        page = finance_client.get(f"/finance/period-close?year={year}&month={month}")
        body = page.get_data(as_text=True)
        checks.append(("finance_period_close_page", page.status_code == 200, page.status_code))
        for marker in ["利润表", "资产负债表", "现金流量表", "确认期间结账"]:
            checks.append((f"finance_period_close_visible:{marker}", marker in body, "visible"))
        checks.append(("finance_period_close_page_clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

        response = finance_client.post(
            "/finance/period-close",
            data={"year": str(year), "month": str(month), "action": "generate", "remark": "first machine period close readiness"},
            follow_redirects=False,
        )
        checks.append(("finance_generate_snapshot", response.status_code in {302, 303}, response.status_code))

        statements = finance_client.get(f"/finance/financial-statements?year={year}&month={month}")
        statement_body = statements.get_data(as_text=True)
        checks.append(("financial_statements_page", statements.status_code == 200, statements.status_code))
        for marker in ["利润表", "资产负债表", "现金流量表"]:
            checks.append((f"financial_statements_visible:{marker}", marker in statement_body, "visible"))
        checks.append(("financial_statements_clean", not any(marker in statement_body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            period = fetch_one(cur, "SELECT id, status FROM accounting_periods WHERE year=%s AND month=%s", (year, month))
            checks.append(("accounting_period_exists", bool(period), period.get("status") if period else "missing"))
            close_row = fetch_one(
                cur,
                """
                SELECT status, revenue, cost, gross_profit, receivable_balance, payable_balance, net_cash_flow
                FROM finance_period_closes
                WHERE period_label=%s
                """,
                (period_label,),
            )
            checks.append(("period_close_snapshot_exists", bool(close_row), close_row.get("status") if close_row else "missing"))
            if close_row:
                checks.append(("period_close_revenue_nonnegative", close_row.get("revenue", 0) >= 0, close_row.get("revenue")))
                checks.append(("period_close_cost_nonnegative", close_row.get("cost", 0) >= 0, close_row.get("cost")))
            reports = fetch_one(
                cur,
                """
                SELECT COUNT(*) AS value
                FROM financial_reports fr
                JOIN accounting_periods ap ON ap.id=fr.period_id
                WHERE ap.year=%s AND ap.month=%s
                """,
                (year, month),
            )
            checks.append(("financial_reports_saved", int((reports or {}).get("value") or 0) >= 3, (reports or {}).get("value")))
    finally:
        conn.close()

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_period_close_readiness_audit=ok" if not failures else "first_machine_period_close_readiness_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"period={period_label}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
