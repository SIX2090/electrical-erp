"""Core read route registration re-exported from data_route_registration."""
from routes.data_route_registration import (
    data_route_detail_title,
    data_route_post_rejected_response,
    data_route_unavailable_subtitle,
    register_data_routes,
    register_report_routes,
)
from routes.export_route_registration import EXPORT_ROUTES, register_export_route, register_export_routes
from routes.report_render_helpers import (
    REPORT_SECTIONS,
    _render_clean_module_report,
    _render_clean_section_report,
    _render_report_center,
)
from routes.report_route_registration import register_clean_report_routes
from routes.route_catalog import (
    DATA_ROUTES,
    REPORT_PAGE_REDIRECTS,
    REPORT_ROUTES,
)
from routes.sales_report_routes import REAL_SALES_REPORT_PATHS
from routes.special_list_routes import document_list_title, has_document_list_config


def register_core_read_routes(
    app,
    login_required,
    endpoint,
    has_table,
    select_rows,
    csv_response,
    table_columns,
    apply_document_list_context,
    safe_one,
    render_special_list,
    render_special_detail,
    render_master_data_dashboard,
    render_finance_dashboard,
    render_system_dashboard,
    render_pending_documents,
    render_approval_pending,
    render_engineering_kitting_dashboard,
    render_data_health_dashboard,
    execute_db=None,
    log_action=None,
    export_scope_filter=None,
):
    special_report_renderers = {
        "/engineering/kitting": render_engineering_kitting_dashboard,
        "/system/data-health": render_data_health_dashboard,
    }

    formal_document_paths = {
        "/production-issues",
        "/production-returns",
        "/production/operation-reports",
    }
    data_routes = [
        route
        for route in DATA_ROUTES
        if route[0] not in {"/approval/pending", "/bom", "/engineering/kitting", "/permissions/roles", *formal_document_paths}
    ]

    register_data_routes(
        app,
        data_routes,
        REPORT_PAGE_REDIRECTS,
        has_table,
        login_required=login_required,
        endpoint=endpoint,
        render_special_list=render_special_list,
        select_rows=select_rows,
        special_report_renderers=special_report_renderers,
        table_columns=table_columns,
        apply_document_list_context=apply_document_list_context,
        has_document_list_config=has_document_list_config,
        render_special_detail=render_special_detail,
        safe_one=safe_one,
        document_list_title=document_list_title,
        unavailable_subtitle=data_route_unavailable_subtitle,
        detail_title=data_route_detail_title,
        post_rejected_response=data_route_post_rejected_response,
        execute_db=execute_db,
        log_action=log_action,
    )

    report_routes = [
        route
        for route in REPORT_ROUTES
        if route[0] not in REAL_SALES_REPORT_PATHS
        and route[0] != "/system/data-health/master/<check_key>"
    ]

    register_report_routes(
        app,
        report_routes,
        REPORT_PAGE_REDIRECTS,
        has_table,
        login_required,
        endpoint,
        select_rows,
        special_report_renderers,
    )

    register_export_routes(
        app,
        EXPORT_ROUTES,
        login_required,
        endpoint,
        select_rows,
        csv_response,
        log_action=log_action,
        scope_filter_fn=export_scope_filter,
    )

    register_export_route(
        app,
        "/category/export",
        "product_categories",
        "product_categories",
        login_required,
        endpoint,
        select_rows,
        csv_response,
        log_action=log_action,
        scope_filter_fn=export_scope_filter,
    )

    sales_report_section_paths = {
        report_path
        for report_path, _title, _words in REPORT_SECTIONS.get("sales", {}).get("sections", ())
    }
    unreleased_inventory_report_paths = {
        "/inventory/reports/expected-available-stock",
        "/inventory/reports/batch-status",
        "/inventory/reports/serial-trace",
        "/inventory/reports/serial-status",
        "/inventory/reports/transfer-difference",
        "/inventory/reports/idle-materials",
        "/inventory/reports/stock-aging",
        "/inventory/reports/check-difference-detail",
        "/inventory/reports/cost-ledger",
        "/inventory/reports/cost-detail",
        "/inventory/reports/project-serial-cost",
        "/inventory/reports/exceptions",
    }
    inventory_subcontract_report_paths = {
        "/inventory/reports/subcontract-wip",
        "/inventory/reports/subcontract-execution",
        "/inventory/reports/subcontract-inout-detail",
        "/inventory/reports/subcontract-variance",
        "/inventory/reports/subcontract-payable-reconcile",
    }
    production_redirect_report_paths = {
        "/production/reports/shortage",
        "/production/reports/work-order-detail",
    }

    register_clean_report_routes(
        app,
        login_required,
        endpoint,
        REPORT_SECTIONS,
        _render_report_center,
        _render_clean_module_report,
        _render_clean_section_report,
        excluded_section_paths=(
            sales_report_section_paths
            | REAL_SALES_REPORT_PATHS
            | unreleased_inventory_report_paths
            | inventory_subcontract_report_paths
            | production_redirect_report_paths
        ),
    )

    for report_path in inventory_subcontract_report_paths:

        @app.get(report_path, endpoint=endpoint("inventory_subcontract_report", report_path))
        @login_required
        def inventory_subcontract_report(report_path=report_path):
            return _render_clean_section_report(report_path)

    @app.get("/pending-documents", endpoint="pending_documents")
    @login_required
    def pending_documents():
        return render_pending_documents()

    @app.get("/approval/pending", endpoint="approval_pending_real")
    @login_required
    def approval_pending_real():
        return render_approval_pending()

    @app.get("/engineering/kitting", endpoint="engineering_kitting_real")
    @login_required
    def engineering_kitting_real():
        return render_engineering_kitting_dashboard()
