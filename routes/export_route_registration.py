"""Export route registration: register CSV/Excel/PDF export endpoints for master data."""
from collections.abc import Callable, Mapping, Sequence
from typing import Any


CsvResponseFactory = Callable[[Sequence[Mapping[str, Any]], str], Any]
EndpointFactory = Callable[[str, str], str]
LoginDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]
SelectRows = Callable[..., tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]]]
LogAction = Callable[[str, str, str], None] | None


EXPORT_ROUTES = [
    ("/export/inventory", "inventory", "inventory"),
    ("/export/payables", "supplier_payables", "payables"),
    ("/export/products", "products", "products"),
    ("/export/customers", "customers", "customers"),
    ("/export/suppliers", "suppliers", "suppliers"),
    ("/export/warehouses", "warehouses", "warehouses"),
    ("/export/locations", "locations", "locations"),
    ("/export/units", "units", "units"),
    ("/export/departments", "departments", "departments"),
    ("/export/employees", "employees", "employees"),
    ("/export/project-masters", "project_masters", "project_masters"),
    ("/export/cabinet-masters", "cabinet_masters", "cabinet_masters"),
    ("/export/product-categories", "product_categories", "product_categories"),
    ("/export/customer-categories", "customer_categories", "customer_categories"),
    ("/export/supplier-categories", "supplier_categories", "supplier_categories"),
    ("/export/warehouse-categories", "warehouse_categories", "warehouse_categories"),
    ("/export/purchase-orders", "purchase_orders", "purchase_orders"),
    ("/export/receivables", "customer_receivables", "receivables"),
    ("/export/sales-orders", "sales_orders", "sales_orders"),
    ("/export/purchase_request", "purchase_requisitions", "purchase_request"),
]


# Sensitive exports that contain business transaction data and must be
# (a) audit-logged with row counts and (b) filtered by the user's data scope.
# Each entry maps the export table to the field_map used by row_allowed().
SENSITIVE_EXPORTS = {
    "sales_orders": {"project": "project_code", "cabinet": "cabinet_no", "customer": "customer_id"},
    "purchase_orders": {"project": "project_code", "cabinet": "cabinet_no", "supplier": "supplier_id"},
    "customer_receivables": {"project": "project_code", "cabinet": "cabinet_no", "customer": "customer_id"},
    "supplier_payables": {"supplier": "supplier_id"},
    "purchase_requisitions": {"project": "project_code", "cabinet": "cabinet_no"},
}


def register_export_route(
    app,
    path: str,
    table: str,
    filename: str,
    login_required: LoginDecorator,
    endpoint: EndpointFactory,
    select_rows: SelectRows,
    csv_response: CsvResponseFactory,
    log_action: LogAction = None,
    scope_filter_fn: Callable[[str, Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]] | None = None,
) -> None:
    route_endpoint = endpoint("export", path)

    @app.get(path, endpoint=route_endpoint)
    @login_required
    def export_page(table=table, filename=filename):
        rows, _columns = select_rows(table, limit=1000)
        rows = list(rows)
        total_before = len(rows)
        # Apply data scope filtering for sensitive business documents.
        if scope_filter_fn is not None:
            rows = scope_filter_fn(table, rows)
        total_after = len(rows)
        # Audit log every export attempt, including how many rows the user
        # was authorised to see versus how many existed before filtering.
        if log_action is not None:
            try:
                remark = f"table={table} exported={total_after}"
                if total_before != total_after:
                    remark += f" filtered_from={total_before}"
                log_action("导出数据", filename, remark)
            except Exception:
                app.logger.exception("export audit log failed for %s", path)
        return csv_response(rows, filename)


def register_export_routes(
    app,
    routes: Sequence[tuple[str, str, str]],
    login_required: LoginDecorator,
    endpoint: EndpointFactory,
    select_rows: SelectRows,
    csv_response: CsvResponseFactory,
    log_action: LogAction = None,
    scope_filter_fn: Callable[[str, Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]] | None = None,
) -> None:
    for path, table, filename in routes:
        register_export_route(
            app,
            path,
            table,
            filename,
            login_required,
            endpoint,
            select_rows,
            csv_response,
            log_action=log_action,
            scope_filter_fn=scope_filter_fn,
        )
