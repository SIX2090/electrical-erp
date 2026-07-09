from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


VISIBLE_ROUTES = [
    "/finance/reports/enterprise-income-expense-detail",
    "/finance/credit-management",
    "/finance/reports/account-aging-analysis",
    "/finance/reports/other-income-expense-detail",
    "/finance/reports/account-income-expense-detail",
    "/finance/reports/account-balance",
    "/finance/reports/payment-flow-summary",
    "/finance/reports/project-capital-occupation",
]


REPORT_CENTER_ROUTES = [
    "/finance/reports/enterprise-income-expense-detail",
    "/finance/reports/credit-management",
    "/finance/reports/account-aging-analysis",
    "/finance/reports/other-income-expense-detail",
    "/finance/reports/account-income-expense-detail",
    "/finance/reports/account-balance",
    "/finance/reports/cash-bank-balance",
    "/finance/reports/cash-bank-transactions",
    "/finance/reports/payment-flow-summary",
    "/finance/reports/project-capital-occupation",
]


FEATURE_PATHS = [
    "/finance/reports/enterprise-income-expense-detail",
    "/finance/credit-management",
    "/finance/reports/account-aging-analysis",
    "/finance/reports/other-income-expense-detail",
    "/finance/reports/account-income-expense-detail",
    "/finance/reports/account-balance",
    "/finance/reports/cash-bank-balance",
    "/finance/reports/cash-bank-transactions",
    "/finance/reports/payment-flow-summary",
    "/finance/reports/project-capital-occupation",
]


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
    report_routes = read_text("routes/report_routes.py")
    classification = read_text("MENU_ROLLOUT_CLASSIFICATION.md")

    from services.pilot_permissions import PILOT_PERMISSION_FEATURES, PILOT_PERMISSION_GROUPS

    features = {feature["path"]: feature for feature in PILOT_PERMISSION_FEATURES}
    finance_group = next(group for group in PILOT_PERMISSION_GROUPS if group["key"] == "finance")

    findings = []
    for route in VISIBLE_ROUTES:
        for area, source in (
            ("finance_routes", finance_routes),
            ("base_nav", base_html),
            ("workbench", workbench),
            ("permissions", permissions),
        ):
            if route not in source:
                findings.append((area, route, "missing visible fund-analysis route"))

    for route in REPORT_CENTER_ROUTES:
        if route not in finance_routes:
            findings.append(("finance_routes", route, "missing report route"))
        if route not in report_routes:
            findings.append(("report_center", route, "missing report center entry"))
        line = classification_line(classification, route)
        if not line:
            findings.append(("classification", route, "missing rollout classification"))
        elif "| report | `readonly` |" not in line:
            findings.append(("classification", route, "must be report / readonly"))

    for route in FEATURE_PATHS:
        if route not in finance_group["paths"]:
            findings.append(("permission_group", route, "missing from finance permission group"))
        feature = features.get(route)
        if not feature:
            findings.append(("permission_feature", route, "missing feature entry"))
            continue
        actions = set(feature.get("default_actions") or set())
        if actions != {"view", "export"}:
            findings.append(("permission_actions", route, f"must be view/export only, got {sorted(actions)}"))
        blocked = sorted(actions & WRITE_ACTIONS)
        if blocked:
            findings.append(("permission_actions", route, f"write actions exposed: {blocked}"))

    for token in (
        "render_enterprise_income_expense_detail_report",
        "render_credit_management_report",
        "render_account_aging_analysis_report",
        "render_other_income_expense_detail_report",
        "render_account_income_expense_detail_report",
        "render_fund_account_balance_report",
        "render_project_capital_occupation_report",
        "_fund_flow_rows",
    ):
        if token not in finance_routes:
            findings.append(("implementation", token, "missing fund-analysis implementation"))

    if "不在本页" not in finance_routes or "?export=csv" not in finance_routes:
        findings.append(("read_only_boundary", "fund_analysis", "missing report-only wording or export action"))

    if findings:
        print("finance_fund_analysis_audit=FAIL")
        for area, item, message in findings:
            print(f"{area}: {item}: {message}")
        raise SystemExit(1)

    print("finance_fund_analysis_audit=PASS")
    print(f"visible_routes={len(VISIBLE_ROUTES)} report_center_routes={len(REPORT_CENTER_ROUTES)}")
    print("default_actions=view,export")


if __name__ == "__main__":
    main()
