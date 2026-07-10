import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, get_db_config
from services.app_runtime import connect_db


FINANCE_MENU_REQUIRED = {
    "/finance/receipts/new",
    "/finance/payments/new",
    "/finance/receivables",
    "/finance/receipts",
    "/finance/payables",
    "/finance/payments",
    "/finance/sales-invoices",
    "/finance/purchase-invoices",
    "/finance/cash-bank/accounts",
    "/finance/bank-journal",
    "/finance/cash-journal",
    "/finance/period-close",
    "/finance/financial-statements",
    "/finance/vouchers",
}

FINANCE_MENU_FORBIDDEN = {
    "/service-orders",
    "/assembly-orders",
    "/disassembly-orders",
    "/work-orders",
    "/finance/accounts",
    "/finance/assets",
}

FINANCE_REQUIRED_MARKERS = {
    "/finance/vouchers": ("\u51ed\u8bc1\u8349\u7a3f", "\u53ea\u8bfb", "\u6765\u6e90\u8ffd\u6eaf", "\u4e0d\u63d0\u4f9b\u8fc7\u8d26"),
    "/finance/financial-statements": ("\u7ecf\u8425\u8d22\u52a1\u5feb\u7167", "\u52fe\u7a3d\u5173\u7cfb", "\u94bb\u53d6\u5e94\u6536\u5e94\u4ed8\u62a5\u8868", "\u4e0d\u662f\u5b8c\u6574\u6cd5\u5b9a"),
    "/finance/period-close": ("\u7ed3\u8d26\u524d\u68c0\u67e5\u9879", "\u5e94\u6536\u6838\u9500\u68c0\u67e5", "\u5e93\u5b58\u6210\u672c\u68c0\u67e5", "\u7ecf\u8425\u8d22\u52a1\u5feb\u7167"),
}

FINANCE_CATALOG_BOUNDARY = {
    "/finance/accounts": "internal",
    "/finance/assets": "hidden",
    "/finance/vouchers": "readonly",
    "/finance/financial-statements": "readonly",
}


def scalar(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    return dict(row) if row else {}


def main():
    findings = []
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    with app.test_client() as client:
        client.post("/login", data={"username": "admin", "password": "admin"})
        for path in sorted(FINANCE_MENU_REQUIRED):
            response = client.get(path)
            if response.status_code >= 400:
                findings.append(("finance_route", path, f"HTTP {response.status_code}"))
            body = response.get_data(as_text=True)
            for marker in FINANCE_REQUIRED_MARKERS.get(path, ()):
                if marker not in body:
                    findings.append(("finance_page_marker", path, f"missing {marker}"))
        finance_menu = (ROOT / "templates" / "base.html").read_text(encoding="utf-8", errors="ignore")
        marker = "{% if see_all or role == 'finance' %}"
        start = finance_menu.find(marker)
        end = finance_menu.find("{% if see_all %}", start)
        block = finance_menu[start:end] if start >= 0 and end > start else finance_menu
        for path in FINANCE_MENU_REQUIRED:
            if path not in block:
                findings.append(("finance_menu", path, "missing from finance menu"))
        for path in FINANCE_MENU_FORBIDDEN:
            if path in block:
                findings.append(("finance_menu", path, "forbidden finance menu exposure"))
        route_catalog = (ROOT / "routes" / "route_catalog.py").read_text(encoding="utf-8", errors="ignore")
        for path, classification in FINANCE_CATALOG_BOUNDARY.items():
            if f'"{path}"' not in route_catalog or f'"classification": "{classification}"' not in route_catalog:
                findings.append(("finance_route_catalog", path, f"missing {classification} classification"))

    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            checks = {
                "customer_receipt_settlements": "SELECT COUNT(*) AS value FROM customer_receipt_settlements",
                "supplier_payment_settlements": "SELECT COUNT(*) AS value FROM supplier_payment_settlements",
                "cash_bank_journal_entries": "SELECT COUNT(*) AS value FROM cash_bank_journal_entries",
                "supplier_payables_trace_columns": "SELECT COUNT(*) AS value FROM information_schema.columns WHERE table_name='supplier_payables' AND column_name IN ('project_code','cabinet_no')",
                "customer_receivables_trace_columns": "SELECT COUNT(*) AS value FROM information_schema.columns WHERE table_name='customer_receivables' AND column_name IN ('project_code','cabinet_no')",
                "purchase_invoices_table": "SELECT COUNT(*) AS value FROM information_schema.tables WHERE table_name='purchase_invoices'",
                "test_receivable_partners": """
                    SELECT COUNT(*) AS value
                    FROM customer_receivables cr
                    LEFT JOIN customers c ON c.id=cr.customer_id
                    WHERE COALESCE(c.name,'') LIKE '测试%%'
                       OR COALESCE(c.name,'') LIKE '售后%%'
                       OR COALESCE(c.name,'') LIKE 'Delete Customer%%'
                """,
                "test_payable_partners": """
                    SELECT COUNT(*) AS value
                    FROM supplier_payables sp
                    LEFT JOIN suppliers s ON s.id=sp.supplier_id
                    WHERE COALESCE(s.name,'') LIKE '测试%%'
                       OR COALESCE(s.name,'') ILIKE 'CF supplier%%'
                       OR COALESCE(s.name,'') ILIKE 'Delete%%'
                """,
            }
            results = {}
            for name, sql in checks.items():
                try:
                    results[name] = scalar(cur, sql).get("value", 0)
                except Exception as exc:
                    findings.append(("finance_data", name, type(exc).__name__))
            if results.get("supplier_payables_trace_columns", 0) < 2:
                findings.append(("finance_data", "supplier_payables", "missing project/cabinet trace columns"))
            if results.get("customer_receivables_trace_columns", 0) < 2:
                findings.append(("finance_data", "customer_receivables", "missing project/cabinet trace columns"))
            if results.get("purchase_invoices_table", 0) < 1:
                findings.append(("finance_data", "purchase_invoices", "table missing"))
            if results.get("cash_bank_journal_entries", 0) < 1:
                findings.append(("finance_data", "cash_bank_journal_entries", "no cash/bank journal rows"))
            if results.get("customer_receipt_settlements", 0) < 1:
                findings.append(("finance_data", "customer_receipt_settlements", "no receipt settlement rows"))

    print("finance_phase1_audit=" + ("ok" if not findings else "failed"))
    for item in findings:
        print(" | ".join(item))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
