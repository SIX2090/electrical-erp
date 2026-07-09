"""Commercial dashboard adapters: sales, purchase, and receipt dashboard re-exports."""
from flask import request

from routes.purchase_receipt_routes import render_purchase_receipt_dashboard
from routes.purchase_routes import render_purchase_dashboard
from routes.sales_routes import render_sales_dashboard


def render_sales_dashboard_adapter(
    query_one,
    query_rows,
    as_decimal,
    status_label,
    filter_clean_rows,
    money_metric,
    qty_metric,
    back_url="/sales-orders",
    document_list=False,
    scope_clause="",
    scope_params=None,
):
    return render_sales_dashboard(
        query_one=query_one,
        query_rows=query_rows,
        as_decimal=as_decimal,
        status_label=status_label,
        filter_clean_rows=filter_clean_rows,
        money_metric=money_metric,
        qty_metric=qty_metric,
        request_args=request.args,
        back_url=back_url,
        document_list=document_list,
        scope_clause=scope_clause,
        scope_params=scope_params,
    )


def render_purchase_dashboard_adapter(
    query_one,
    query_rows,
    count_rows,
    as_decimal,
    status_label,
    filter_clean_rows,
    money_metric,
    qty_metric,
    purchase_suggestion_rows,
    back_url="/purchase-orders",
    document_list=False,
    scope_clause="",
    scope_params=None,
):
    return render_purchase_dashboard(
        query_one,
        query_rows,
        count_rows,
        as_decimal,
        status_label,
        filter_clean_rows,
        money_metric,
        qty_metric,
        purchase_suggestion_rows,
        request.args,
        back_url=back_url,
        document_list=document_list,
        scope_clause=scope_clause,
        scope_params=scope_params,
    )


def render_purchase_receipt_dashboard_adapter(query_one, query_rows, count_rows, qty_metric, money_metric):
    return render_purchase_receipt_dashboard(query_one, query_rows, count_rows, qty_metric, money_metric, request.args)
