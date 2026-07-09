"""Inventory material adapters: re-export inventory adjustment and transfer renderers."""
from flask import request

from routes.inventory_routes import (
    render_inventory_adjustment_detail,
    render_inventory_adjustment_form,
    render_inventory_balance_dashboard,
    render_inventory_balance_detail,
    render_inventory_check_detail,
    render_inventory_check_form,
    render_inventory_dashboard,
    render_inventory_document_print,
    render_inventory_movement_form,
    render_inventory_transfer_detail,
    render_inventory_transfer_form,
    render_stock_transaction_dashboard,
)
from routes.material_master_routes import render_material_dashboard


def render_inventory_dashboard_adapter(query_rows, query_one):
    return render_inventory_dashboard(query_rows, query_one)


def render_inventory_balance_dashboard_adapter(query_rows, back_url="/inventory/detail", title="库存明细"):
    return render_inventory_balance_dashboard(query_rows, back_url, title)


def render_stock_transaction_dashboard_adapter(query_rows, filter_clean_rows, clean_display_text):
    return render_stock_transaction_dashboard(query_rows, filter_clean_rows, clean_display_text)


def render_material_dashboard_adapter(
    query_rows,
    count_rows,
    filter_clean_rows,
    clean_display_text,
    status_label,
    back_url="/material",
):
    return render_material_dashboard(
        query_rows,
        count_rows,
        filter_clean_rows,
        clean_display_text,
        status_label,
        request.args,
        back_url,
    )


def render_inventory_balance_detail_adapter(query_one, query_rows, balance_id, back_url="/inventory/detail"):
    return render_inventory_balance_detail(query_one, query_rows, balance_id, back_url)


def render_inventory_adjustment_detail_adapter(
    adjustment_id,
    query_one,
    query_rows,
    as_decimal,
    document_attachments,
    document_activity_logs,
    load_custom_payload,
    back_url="/adjustments",
):
    return render_inventory_adjustment_detail(
        adjustment_id,
        query_one,
        query_rows,
        as_decimal,
        document_attachments,
        document_activity_logs,
        load_custom_payload,
        back_url,
    )


def render_inventory_transfer_detail_adapter(
    transfer_id,
    query_one,
    query_rows,
    ensure_transfer_item_table,
    document_attachments,
    document_activity_logs,
    load_custom_payload,
    back_url="/transfers",
):
    return render_inventory_transfer_detail(
        transfer_id,
        query_one,
        query_rows,
        ensure_transfer_item_table,
        document_attachments,
        document_activity_logs,
        load_custom_payload,
        back_url,
    )


def render_inventory_check_detail_adapter(
    check_id,
    query_one,
    query_rows,
    ensure_inventory_check_item_table,
    document_attachments,
    document_activity_logs,
    load_custom_payload,
    back_url="/inventory_checks",
):
    return render_inventory_check_detail(
        check_id,
        query_one,
        query_rows,
        ensure_inventory_check_item_table,
        document_attachments,
        document_activity_logs,
        load_custom_payload,
        back_url,
    )


def render_inventory_document_print_adapter(
    doc_type,
    record_id,
    query_one,
    query_rows,
    as_decimal,
    ensure_transfer_item_table,
    ensure_inventory_check_item_table,
):
    return render_inventory_document_print(
        doc_type,
        record_id,
        query_one,
        query_rows,
        as_decimal,
        ensure_transfer_item_table,
        ensure_inventory_check_item_table,
    )


def render_inventory_movement_form_adapter(
    direction,
    query_rows,
    next_doc_no,
    product_options,
    clean_rows,
    movement_kind=None,
):
    return render_inventory_movement_form(direction, query_rows, next_doc_no, product_options, clean_rows, movement_kind)


def render_inventory_adjustment_form_adapter(query_rows, product_options, clean_rows, order=None, items=None, action_url="/adjustments/new", mode="new"):
    return render_inventory_adjustment_form(query_rows, product_options, clean_rows, order, items, action_url, mode)


def render_inventory_transfer_form_adapter(query_rows, product_options, clean_rows, order=None, items=None, action_url="/transfers/new", mode="new"):
    return render_inventory_transfer_form(query_rows, product_options, clean_rows, order, items, action_url, mode)


def render_inventory_check_form_adapter(query_rows, product_options, clean_rows, order=None, items=None, action_url="/inventory_checks/new", mode="new"):
    return render_inventory_check_form(query_rows, product_options, clean_rows, order, items, action_url, mode)
