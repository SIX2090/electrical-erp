"""Business partner adapter functions re-exported from business_partner_routes."""
from flask import request

from routes.business_partner_routes import (
    render_customer_dashboard,
    render_customer_detail,
    render_supplier_dashboard,
    render_supplier_detail,
)


def render_customer_dashboard_adapter(
    query_rows,
    count_rows,
    sum_value,
    money_metric,
    render_dashboard,
    columns,
    back_url="/customer",
):
    return render_customer_dashboard(
        query_rows,
        count_rows,
        sum_value,
        money_metric,
        render_dashboard,
        columns,
        request.args,
        back_url,
    )


def render_supplier_dashboard_adapter(
    query_rows,
    count_rows,
    sum_value,
    money_metric,
    qty_metric,
    render_dashboard,
    columns,
    back_url="/supplier",
):
    return render_supplier_dashboard(
        query_rows,
        count_rows,
        sum_value,
        money_metric,
        qty_metric,
        render_dashboard,
        columns,
        request.args,
        back_url,
    )


def render_customer_detail_adapter(customer_id, query_one, query_rows, money_metric, columns, back_url="/customer"):
    return render_customer_detail(customer_id, query_one, query_rows, money_metric, columns, back_url)


def render_supplier_detail_adapter(
    supplier_id,
    query_one,
    query_rows,
    money_metric,
    qty_metric,
    columns,
    back_url="/supplier",
):
    return render_supplier_detail(supplier_id, query_one, query_rows, money_metric, qty_metric, columns, back_url)
