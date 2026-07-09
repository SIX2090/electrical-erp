from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


ROUTES = [
    "/finance/settlement-schemes",
    "/finance/settlement-runs",
    "/finance/manual-settlement",
    "/finance/smart-collections",
    "/finance/smart-payments",
    "/finance/reports/customer-vendor-matching-statement",
    "/finance/reports/statement-history",
    "/finance/statement-templates",
]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    finance_routes = read_text("routes/finance_routes.py")
    base_html = read_text("templates/base.html")
    workbench = read_text("templates/finance_ar_ap_workbench.html")
    permissions = read_text("services/pilot_permissions.py")
    registry = read_text("routes/registry.py")
    classification = read_text("MENU_ROLLOUT_CLASSIFICATION.md")
    report_routes = read_text("routes/report_routes.py")
    template = read_text("templates/finance_counterparty_tools.html")

    findings = []
    for route in ROUTES:
        for name, source in (
            ("finance_routes", finance_routes),
            ("base_nav", base_html),
            ("permissions", permissions),
            ("classification", classification),
        ):
            if route not in source:
                findings.append((name, route, "missing route exposure"))

    for route in ROUTES[:5]:
        if route not in workbench:
            findings.append(("workbench", route, "missing AR/AP workbench link"))

    for route in ROUTES:
        if route not in registry and route not in {"/finance/reports/statement-history", "/finance/statement-templates"}:
            findings.append(("registry", route, "missing role feature registry entry"))

    for route in ROUTES[5:7]:
        if route not in report_routes:
            findings.append(("report_center", route, "missing report center section"))

    required_tokens = [
        "render_auto_settlement_schemes",
        "render_auto_settlement_runs",
        "render_manual_settlement_console",
        "render_smart_collection_queue",
        "render_smart_payment_queue",
        "render_counterparty_matching_statement",
        "render_statement_history",
        "render_statement_templates",
        "不提供新增、审核、过账或自动改账动作",
    ]
    combined = finance_routes + template
    for token in required_tokens:
        if token not in combined:
            findings.append(("implementation", token, "missing controlled counterparty tool behavior"))

    if findings:
        print("finance counterparty tools audit failed:")
        for area, item, message in findings:
            print(f"- [{area}] {item}: {message}")
        raise SystemExit(1)

    print("finance counterparty tools audit passed.")


if __name__ == "__main__":
    main()
