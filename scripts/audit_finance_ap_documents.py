from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


VISIBLE_AP_ROUTES = [
    "/finance/payments",
    "/finance/payments/new",
    "/finance/advance-payments",
    "/finance/advance-payments/new",
    "/finance/payment-refunds",
    "/finance/payment-refunds/new",
    "/finance/advance-payment-refunds",
    "/finance/advance-payment-refunds/new",
    "/finance/other-expenses",
    "/finance/other-expenses/new",
    "/finance/other-expense-refunds",
    "/finance/other-expense-refunds/new",
]

HIDDEN_HIGH_RISK_ROUTES = [
    "/supplier-payment-requests",
    "/supplier-payment-requests/new",
    "/finance/fund-transfers",
    "/finance/fund-transfers/new",
]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    base_html = read_text("templates/base.html")
    finance_routes = read_text("routes/finance_routes.py")
    permissions = read_text("services/pilot_permissions.py")
    classification = read_text("MENU_ROLLOUT_CLASSIFICATION.md")
    migrations = read_text("services/schema_migrations.py")

    findings = []
    for route in VISIBLE_AP_ROUTES:
        if route not in base_html:
            findings.append(("menu", route, "missing from finance navigation"))
        if route not in permissions:
            findings.append(("permissions", route, "missing from pilot permissions"))
        if route not in classification:
            findings.append(("classification", route, "missing rollout classification"))
        if route not in finance_routes:
            findings.append(("route", route, "missing route/config exposure"))

    for route in HIDDEN_HIGH_RISK_ROUTES:
        if route in base_html:
            findings.append(("menu", route, "high-risk AP route exposed in navigation"))
        if route not in classification or "| `hidden` |" not in classification[classification.find(route):classification.find(route) + 220]:
            findings.append(("classification", route, "high-risk AP route is not classified hidden"))

    required_migration_terms = [
        "payment_kind",
        "fund_direction",
        "supplier_payment_lines",
        "idx_supplier_payments_kind_date",
    ]
    for term in required_migration_terms:
        if term not in migrations:
            findings.append(("migration", term, "missing AP document kind or line migration"))

    if "AP_PAYMENT_DOCUMENT_TYPES" not in finance_routes:
        findings.append(("config", "AP_PAYMENT_DOCUMENT_TYPES", "missing AP document type configuration"))
    if "register_ap_payment_document_routes" not in finance_routes:
        findings.append(("routes", "register_ap_payment_document_routes", "missing AP document route factory"))
    if "supplier_payment_lines" not in finance_routes:
        findings.append(("detail", "supplier_payment_lines", "missing AP fund line persistence/detail usage"))

    if findings:
        print("AP document audit failed:")
        for area, item, message in findings:
            print(f"- [{area}] {item}: {message}")
        raise SystemExit(1)

    print("AP document audit passed.")


if __name__ == "__main__":
    main()
