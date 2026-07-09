"""Warehouse master adapters: re-export warehouse and location dashboard/detail renderers."""
from flask import request

from routes.warehouse_master_routes import (
    render_location_dashboard,
    render_location_detail,
    render_warehouse_dashboard,
    render_warehouse_detail,
)


def render_warehouse_dashboard_adapter(
    query_rows,
    query_one,
    count_rows,
    render_dashboard,
    columns,
    back_url="/warehouse",
):
    return render_warehouse_dashboard(
        query_rows,
        query_one,
        count_rows,
        render_dashboard,
        columns,
        request.args,
        back_url,
    )


def render_location_dashboard_adapter(
    query_rows,
    query_one,
    count_rows,
    render_dashboard,
    columns,
    back_url="/locations",
):
    return render_location_dashboard(
        query_rows,
        query_one,
        count_rows,
        render_dashboard,
        columns,
        request.args,
        back_url,
    )


def render_location_detail_adapter(location_id, query_one, query_rows, columns, qty_metric, money_metric, back_url="/locations"):
    return render_location_detail(location_id, query_one, query_rows, columns, qty_metric, money_metric, back_url)


def render_warehouse_detail_adapter(warehouse_id, query_one, query_rows, count_rows, back_url="/warehouse"):
    return render_warehouse_detail(warehouse_id, query_one, query_rows, count_rows, back_url)
