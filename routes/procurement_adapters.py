"""Procurement adapters: re-export purchase requisition and engineering kitting renderers."""
from routes.procurement_routes import (
    render_engineering_kitting_dashboard,
    render_purchase_requisition_dashboard,
    render_purchase_requisition_detail,
    render_purchase_requisition_form,
    render_purchase_suggestions,
)
from routes.work_order_requisition_routes import render_work_order_requisition_dashboard


def render_engineering_kitting_dashboard_adapter(
    query_one,
    query_rows,
    count_rows,
    sum_value,
    qty_metric,
    columns,
    render_module_dashboard,
):
    return render_engineering_kitting_dashboard(
        query_one,
        query_rows,
        count_rows,
        sum_value,
        qty_metric,
        columns,
        render_module_dashboard,
    )


def render_purchase_suggestions_adapter(query_rows, as_decimal, qty_metric, money_metric):
    return render_purchase_suggestions(query_rows, as_decimal, qty_metric, money_metric)


def render_purchase_requisition_dashboard_adapter(
    query_rows,
    count_rows,
    sum_value,
    qty_metric,
    money_metric,
    columns,
    render_module_dashboard,
    back_url="/purchase_request",
):
    return render_purchase_requisition_dashboard(
        query_rows,
        count_rows,
        sum_value,
        qty_metric,
        money_metric,
        columns,
        render_module_dashboard,
        back_url,
    )


def render_purchase_requisition_form_adapter(
    product_options,
    query_rows,
    as_decimal,
    next_daily_doc_no,
):
    return render_purchase_requisition_form(
        product_options,
        query_rows,
        as_decimal,
        next_daily_doc_no,
    )


def render_purchase_requisition_detail_adapter(
    req_id,
    query_one,
    query_rows,
    as_decimal,
    qty_metric,
    money_metric,
    back_url="/purchase_request",
):
    return render_purchase_requisition_detail(
        req_id,
        query_one,
        query_rows,
        as_decimal,
        qty_metric,
        money_metric,
        back_url,
    )


def render_work_order_requisition_dashboard_adapter(query_rows):
    return render_work_order_requisition_dashboard(query_rows)
