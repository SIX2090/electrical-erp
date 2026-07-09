from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


VISIBLE_AR_ROUTES = [
    "/finance/receipts",
    "/finance/receipts/new",
    "/finance/advance-receipts",
    "/finance/advance-receipts/new",
    "/finance/receipt-refunds",
    "/finance/receipt-refunds/new",
    "/finance/advance-receipt-refunds",
    "/finance/advance-receipt-refunds/new",
    "/finance/other-income",
    "/finance/other-income/new",
    "/finance/other-income-refunds",
    "/finance/other-income-refunds/new",
    "/finance/receivables/pending-collections",
    "/finance/receivables/merged-collections",
    "/finance/receivable-bills",
]

HIDDEN_BAD_DEBT_ROUTES = [
    "/finance/receivables/bad-debt-accruals",
    "/finance/receivables/bad-debt-losses",
]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    base_html = read_text("templates/base.html")
    finance_routes = read_text("routes/finance_routes.py")
    permissions = read_text("services/pilot_permissions.py")
    classification = read_text("MENU_ROLLOUT_CLASSIFICATION.md")

    findings = []
    for route in VISIBLE_AR_ROUTES:
        if route not in base_html:
            findings.append(("menu", route, "missing from finance navigation"))
        if route not in permissions:
            findings.append(("permissions", route, "missing from pilot permissions"))
        if route not in classification:
            findings.append(("classification", route, "missing rollout classification"))

    for route in VISIBLE_AR_ROUTES:
        if route not in finance_routes:
            findings.append(("routes", route, "missing route registration or renderer"))

    for route in HIDDEN_BAD_DEBT_ROUTES:
        if route in base_html:
            findings.append(("bad_debt_boundary", route, "hidden bad-debt route exposed in navigation"))
        if f"| `{route}` |" not in classification or "`hidden`" not in classification:
            findings.append(("bad_debt_boundary", route, "hidden classification missing"))

    if "receipt_kind" not in finance_routes:
        findings.append(("schema_flow", "customer_receipts.receipt_kind", "AR document type filter missing"))
    if "fund_direction" not in finance_routes:
        findings.append(("schema_flow", "customer_receipts.fund_direction", "fund direction handling missing"))
    if "settlement_enabled" not in finance_routes or "settlement_enabled" not in read_text("templates/finance_funds_form.html"):
        findings.append(("entry_boundary", "settlement_enabled", "non-settlement AR documents cannot hide settlement grid"))

    if findings:
        print("finance_ar_documents_audit=FAIL")
        for area, route, message in findings:
            print(f"{area}: {route}: {message}")
        raise SystemExit(1)

    print("finance_ar_documents_audit=PASS")
    print(f"visible_ar_routes={len(VISIBLE_AR_ROUTES)}")
    print(f"hidden_bad_debt_routes={len(HIDDEN_BAD_DEBT_ROUTES)}")


if __name__ == "__main__":
    main()
