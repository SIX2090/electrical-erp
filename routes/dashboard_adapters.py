"""Dashboard adapters: re-exports of module dashboard render functions."""
from flask import request

from routes.approval_routes import render_approval_pending, render_approval_record_detail
from routes.equipment_routes import render_equipment_dashboard
from routes.finance_routes import render_finance_dashboard, render_payable_detail, render_payable_list, render_receivable_detail, render_receivable_list
from routes.master_data_routes import render_master_data_dashboard
from routes.pending_routes import render_pending_documents
from routes.production_routes import render_production_dashboard, render_work_order_detail, render_work_order_list, render_work_order_operation_print
from routes.system_management_routes import render_system_dashboard


def render_pending_documents_adapter(query_rows, render_dashboard, columns):
    return render_pending_documents(query_rows, render_dashboard, columns)


def render_approval_pending_adapter(query_rows, count_rows, render_dashboard):
    return render_approval_pending(query_rows, count_rows, render_dashboard)


def render_approval_record_detail_adapter(record_id, query_one, back_url="/approval/pending"):
    return render_approval_record_detail(record_id, query_one, back_url)


def render_equipment_dashboard_adapter(query_rows, query_one, qty_metric, back_url="/equipment"):
    return render_equipment_dashboard(query_rows, query_one, qty_metric, request.args, back_url)


def render_master_data_dashboard_adapter(query_rows, count_rows, sum_value, money_metric, render_dashboard, columns):
    return render_master_data_dashboard(query_rows, count_rows, sum_value, money_metric, render_dashboard, columns)


def render_production_dashboard_adapter(query_rows, count_rows, columns, render_dashboard):
    return render_production_dashboard(query_rows, count_rows, columns, render_dashboard)


def render_work_order_list_adapter(query_rows, columns, scope_clause="", scope_params=()):
    return render_work_order_list(query_rows, columns, scope_clause=scope_clause, scope_params=scope_params)


def render_finance_dashboard_adapter(query_one, query_rows, count_rows, money_metric, columns, render_dashboard):
    return render_finance_dashboard(query_one, query_rows, count_rows, money_metric, columns, render_dashboard)


def render_payable_list_adapter(query_rows, money_metric):
    return render_payable_list(query_rows, money_metric)


def render_receivable_list_adapter(query_rows, money_metric):
    return render_receivable_list(query_rows, money_metric)


def render_system_dashboard_adapter(root_dir, query_rows, count_rows, backup_rows, columns, render_dashboard, clean_text=None):
    return render_system_dashboard(root_dir, query_rows, count_rows, backup_rows, columns, render_dashboard, clean_text)


def render_work_order_detail_adapter(
    work_order_id,
    query_one,
    query_rows,
    as_decimal,
    qty_metric,
    columns,
    document_attachments,
    document_activity_logs,
    project_kit_rows,
    build_kit_summary,
    product_options,
    warehouse_options,
    location_options,
    back_url="/work-orders",
):
    return render_work_order_detail(
        work_order_id,
        query_one,
        query_rows,
        as_decimal,
        qty_metric,
        columns,
        document_attachments,
        document_activity_logs,
        project_kit_rows,
        build_kit_summary,
        product_options,
        warehouse_options,
        location_options,
        back_url,
    )


def render_work_order_operation_print_adapter(kind, work_order_id, query_one, query_rows, as_decimal):
    return render_work_order_operation_print(kind, work_order_id, query_one, query_rows, as_decimal)


def render_receivable_detail_adapter(
    receivable_id,
    query_one,
    query_rows,
    money_metric,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/receivables",
):
    return render_receivable_detail(
        receivable_id,
        query_one,
        query_rows,
        money_metric,
        columns,
        document_attachments,
        document_activity_logs,
        back_url,
    )


def render_payable_detail_adapter(
    payable_id,
    query_one,
    query_rows,
    money_metric,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/payables",
):
    return render_payable_detail(
        payable_id,
        query_one,
        query_rows,
        money_metric,
        columns,
        document_attachments,
        document_activity_logs,
        back_url,
    )
