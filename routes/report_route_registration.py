"""Report route registration: register report center entry routes per business module."""
REPORT_ROUTE_KINDS = (
    ("sales", "/sales/reports", "sales_reports"),
    ("purchase", "/purchase/reports", "purchase_reports"),
    ("inventory", "/inventory/reports", "inventory_reports"),
    ("production", "/production/reports", "production_reports"),
    ("subcontract", "/subcontract/reports", "subcontract_reports"),
    ("finance", "/finance/reports", "finance_reports"),
    ("service", "/service/reports", "service_reports"),
)


def _has_rule(app, rule, methods=("GET",)):
    requested_methods = set(methods)
    for existing_rule in app.url_map.iter_rules():
        if existing_rule.rule == rule and requested_methods.issubset(existing_rule.methods):
            return True
    return False


def register_clean_report_routes(
    app,
    login_required,
    endpoint,
    report_sections,
    render_report_center,
    render_clean_module_report,
    render_clean_section_report,
    excluded_section_paths=None,
):
    """Register the read-only clean report center and section GET routes."""
    excluded_section_paths = set(excluded_section_paths or ())

    @app.get("/reports", endpoint="report_center")
    @login_required
    def report_center():
        return render_report_center()

    for report_kind, report_url, route_endpoint in REPORT_ROUTE_KINDS:
        if report_url in excluded_section_paths:
            continue
        if _has_rule(app, report_url):
            continue

        @app.get(report_url, endpoint=route_endpoint)
        @login_required
        def module_report(report_kind=report_kind):
            return render_clean_module_report(report_kind)

    for report_config in report_sections.values():
        for report_url, _report_title, _report_words in report_config["sections"]:
            if report_url in excluded_section_paths:
                continue
            if _has_rule(app, report_url):
                continue
            route_endpoint = endpoint("module_report_section", report_url)

            @app.get(report_url, endpoint=route_endpoint)
            @login_required
            def module_report_section(report_url=report_url):
                return render_clean_section_report(report_url)
