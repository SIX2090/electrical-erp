from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


REPORT_ROUTES = [
    "/finance/reports/receivable-detail",
    "/finance/reports/payable-detail",
    "/finance/reports/receivable-summary",
    "/finance/reports/payable-summary",
    "/finance/reports/payment-request-statistics",
    "/finance/reports/receivable-warning",
    "/finance/reports/payable-warning",
    "/finance/reports/bad-debt-reserve-balance",
]


FEATURE_KEYS = {
    "/finance/reports/receivable-detail": "finance_receivable_detail_report",
    "/finance/reports/payable-detail": "finance_payable_detail_report",
    "/finance/reports/receivable-summary": "finance_receivable_summary_report",
    "/finance/reports/payable-summary": "finance_payable_summary_report",
    "/finance/reports/payment-request-statistics": "finance_payment_request_statistics_report",
    "/finance/reports/receivable-warning": "finance_receivable_warning_report",
    "/finance/reports/payable-warning": "finance_payable_warning_report",
    "/finance/reports/bad-debt-reserve-balance": "finance_bad_debt_reserve_balance_report",
}


WRITE_ACTIONS = {"create", "edit", "audit", "delete", "operate", "print"}


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def classification_line(source, route):
    marker = f"| `{route}` |"
    for line in source.splitlines():
        if line.startswith(marker):
            return line
    return ""


def main():
    finance_routes = read_text("routes/finance_routes.py")
    base_html = read_text("templates/base.html")
    workbench = read_text("templates/finance_ar_ap_workbench.html")
    permissions = read_text("services/pilot_permissions.py")
    classification = read_text("MENU_ROLLOUT_CLASSIFICATION.md")
    report_routes = read_text("routes/report_routes.py")
    template = read_text("templates/finance_counterparty_tools.html")

    from services.pilot_permissions import PILOT_PERMISSION_FEATURES, PILOT_PERMISSION_GROUPS

    features = {feature["path"]: feature for feature in PILOT_PERMISSION_FEATURES}
    finance_group = next(group for group in PILOT_PERMISSION_GROUPS if group["key"] == "finance")

    findings = []
    for route in REPORT_ROUTES:
        for area, source in (
            ("finance_routes", finance_routes),
            ("base_nav", base_html),
            ("workbench", workbench),
            ("permissions", permissions),
            ("report_center", report_routes),
        ):
            if route not in source:
                findings.append((area, route, "missing report route"))

        line = classification_line(classification, route)
        if not line:
            findings.append(("classification", route, "missing rollout classification"))
        elif "| report | `readonly` |" not in line:
            findings.append(("classification", route, "must be report / readonly"))

        if route not in finance_group["paths"]:
            findings.append(("permission_group", route, "missing from finance permission group"))

        feature = features.get(route)
        if not feature:
            findings.append(("permission_feature", route, "missing feature entry"))
            continue
        if feature.get("key") != FEATURE_KEYS[route]:
            findings.append(("permission_feature", route, "unexpected feature key"))
        actions = set(feature.get("default_actions") or set())
        if actions != {"view", "export"}:
            findings.append(("permission_actions", route, f"must be view/export only, got {sorted(actions)}"))
        blocked = sorted(actions & WRITE_ACTIONS)
        if blocked:
            findings.append(("permission_actions", route, f"write actions exposed: {blocked}"))

    for token in (
        "render_receivable_detail_report",
        "render_payable_detail_report",
        "render_receivable_summary_report",
        "render_payable_summary_report",
        "render_payment_request_statistics_report",
        "render_receivable_warning_report",
        "render_payable_warning_report",
        "render_bad_debt_reserve_balance_report",
        "_bad_debt_rate",
        "supplier_payables",
    ):
        if token not in finance_routes:
            findings.append(("implementation", token, "missing report implementation token"))

    if "actions=[" not in finance_routes or "?export=csv" not in finance_routes:
        findings.append(("implementation", "_render_finance_report", "missing read-only report action surface"))

    for forbidden in ("/new", "submit", "audit", "post", "void", "delete"):
        if f"href=\"{forbidden}" in template or f"action=\"{forbidden}" in template:
            findings.append(("template", forbidden, "write route exposed in report template"))

    if findings:
        print("finance_counterparty_reports_audit=FAIL")
        for area, item, message in findings:
            print(f"{area}: {item}: {message}")
        raise SystemExit(1)

    print("finance_counterparty_reports_audit=PASS")
    print(f"report_routes={len(REPORT_ROUTES)}")
    print("default_actions=view,export")


if __name__ == "__main__":
    main()
