"""Unified inventory posting entry points for receipt and issue operations.

All business modules that need to modify inventory must call these functions
to ensure atomic transaction handling and consistent updates to
inventory_balances, batch_tracking, and stock_transactions.
"""
from services.inventory_service import inventory_inbound_weighted_avg, inventory_outbound
from services.structured_logger import business_logger


def post_inventory_receipt(
    query_db,
    execute_db,
    product_id,
    quantity,
    unit_cost,
    tx_date,
    tx_type,
    reference_no="",
    remark="",
    warehouse_id=None,
    location_id=None,
    lot_no="",
    serial_no="",
    project_code="",
    source_type="",
    source_doc_no="",
    source_line_no="",
):
    """Post an inventory inbound receipt using weighted-average cost."""
    result = inventory_inbound_weighted_avg(
        query_db,
        execute_db,
        product_id,
        quantity,
        unit_cost,
        "",
        reference_no,
        remark,
        tx_date,
        tx_type,
        lot_no,
        serial_no,
        warehouse_id=warehouse_id,
        location_id=location_id,
        project_code=project_code,
        source_type=source_type,
        source_doc_no=source_doc_no or reference_no,
        source_line_no=source_line_no,
    )
    business_logger.log_event(
        "inventory_receipt",
        "stock_transaction",
        result.get("tx_id") if isinstance(result, dict) else None,
        product_id=product_id,
        quantity=str(quantity),
        unit_cost=str(unit_cost),
        tx_type=tx_type,
        reference_no=reference_no,
        warehouse_id=warehouse_id,
        lot_no=lot_no,
        serial_no=serial_no,
        project_code=project_code,
        source_type=source_type,
        source_doc_no=source_doc_no or reference_no,
        source_line_no=source_line_no,
    )
    return result


def post_inventory_issue(
    query_db,
    execute_db,
    product_id,
    quantity,
    tx_date,
    tx_type,
    reference_no="",
    remark="",
    unit_cost=0,
    warehouse_id=None,
    location_id=None,
    lot_no="",
    serial_no="",
    project_code="",
    source_type="",
    source_doc_no="",
    source_line_no="",
):
    """Post an inventory outbound issue using weighted-average cost."""
    result = inventory_outbound(
        query_db,
        execute_db,
        product_id,
        quantity,
        "",
        reference_no,
        remark,
        tx_date,
        tx_type,
        lot_no,
        serial_no,
        unit_cost=unit_cost,
        warehouse_id=warehouse_id,
        location_id=location_id,
        project_code=project_code,
        source_type=source_type,
        source_doc_no=source_doc_no or reference_no,
        source_line_no=source_line_no,
    )
    business_logger.log_event(
        "inventory_issue",
        "stock_transaction",
        result.get("tx_id") if isinstance(result, dict) else None,
        product_id=product_id,
        quantity=str(quantity),
        tx_type=tx_type,
        reference_no=reference_no,
        warehouse_id=warehouse_id,
        lot_no=lot_no,
        serial_no=serial_no,
        project_code=project_code,
        source_type=source_type,
        source_doc_no=source_doc_no or reference_no,
        source_line_no=source_line_no,
    )
    return result
