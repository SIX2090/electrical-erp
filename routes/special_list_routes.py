"""Read-only special list/detail dispatch helpers.

This module is intentionally dependency-injected.  The current registry module
owns the real render functions and database helpers, so future wiring can pass
those callables in without creating import cycles or touching POST workflows.
"""


def _renderer(renderers, name):
    if not renderers or name not in renderers:
        raise KeyError(f"missing special-list renderer: {name}")
    return renderers[name]


def status_display(value):
    text = str(value or "").strip()
    if not text:
        return "\u672a\u5b9a"
    labels = {
        "active": "\u542f\u7528",
        "inactive": "\u505c\u7528",
        "open": "\u672a\u5b8c\u6210",
        "planned": "\u5df2\u8ba1\u5212",
        "released": "\u5df2\u4e0b\u8fbe",
        "fulfilled": "\u5df2\u6ee1\u8db3",
        "generated": "\u5df2\u751f\u6210",
        "posted": "\u5df2\u8fc7\u8d26",
        "unpaid": "\u672a\u4ed8\u6b3e",
        "paid": "\u5df2\u4ed8\u6b3e",
        "pending": "\u5f85\u5904\u7406",
        "submitted": "\u5df2\u63d0\u4ea4",
        "audited": "\u5df2\u5ba1\u6838",
        "voided": "\u5df2\u4f5c\u5e9f",
        "draft": "\u8349\u7a3f",
        "closed": "\u5df2\u5173\u95ed",
        "completed": "\u5df2\u5b8c\u6210",
        "approved": "\u5df2\u5ba1\u6838",
        "confirmed": "\u5df2\u786e\u8ba4",
        "cancelled": "\u5df2\u53d6\u6d88",
        "canceled": "\u5df2\u53d6\u6d88",
        "void": "\u5df2\u4f5c\u5e9f",
        "issued": "\u5df2\u5f00\u7968",
        "running": "\u6267\u884c\u4e2d",
        "in_progress": "\u6267\u884c\u4e2d",
        "processing": "\u52a0\u5de5\u4e2d",
        "failed": "\u4e0d\u5408\u683c",
        "ng": "\u4e0d\u5408\u683c",
        "pass": "\u5408\u683c",
        "passed": "\u5408\u683c",
    }
    return labels.get(text.lower(), text)


SPECIAL_LIST_RENDERERS = {
    "data_health_dashboard": "_render_data_health_dashboard",
    "approval_pending": "_render_approval_pending",
    "equipment_dashboard": "_render_equipment_dashboard",
    "customer_dashboard": "_render_customer_dashboard",
    "supplier_dashboard": "_render_supplier_dashboard",
    "shipment_dashboard": "_render_shipment_dashboard",
    "warehouse_dashboard": "_render_warehouse_dashboard",
    "material_dashboard": "_render_material_dashboard",
    "location_dashboard": "_render_location_dashboard",
    "unit_dashboard": "_render_unit_dashboard",
    "department_dashboard": "_render_department_dashboard",
    "employee_dashboard": "_render_employee_dashboard",
    "category_dashboard": "_render_category_dashboard",
    "sales_dashboard": "_render_sales_dashboard",
    "purchase_dashboard": "_render_purchase_dashboard",
    "purchase_requisition_dashboard": "_render_purchase_requisition_dashboard",
    "work_order_requisition_dashboard": "_render_work_order_requisition_dashboard",
    "purchase_receipt_dashboard": "_render_purchase_receipt_dashboard",
    "inventory_dashboard": "_render_inventory_dashboard",
    "inventory_balance_dashboard": "_render_inventory_balance_dashboard",
    "stock_transaction_dashboard": "_render_stock_transaction_dashboard",
    "production_dashboard": "_render_production_dashboard",
    "work_order_list": "_render_work_order_list",
    "inventory_adjustment_list": "_render_inventory_adjustment_list",
    "inventory_transfer_list": "_render_inventory_transfer_list",
    "inventory_check_list": "_render_inventory_check_list",
    "receivable_list": "_render_receivable_list",
    "payable_list": "_render_payable_list",
    "after_sale_dashboard": "_render_after_sale_dashboard",
    "quality_inspection_dashboard": "_render_quality_inspection_dashboard",
    "service_order_dashboard": "_render_service_order_dashboard",
    "service_rma_dashboard": "_render_service_rma_dashboard",
    "subcontract_dashboard": "_render_subcontract_dashboard",
    "production_routing_list": "_render_production_routing_list",
    "work_center_list": "_render_work_center_list",
    "production_schedule_list": "_render_production_schedule_list",
}


SPECIAL_DETAIL_RENDERERS = {
    "customer_detail": "_render_customer_detail",
    "supplier_detail": "_render_supplier_detail",
    "warehouse_detail": "_render_warehouse_detail",
    "material_detail": "_render_material_detail",
    "location_detail": "_render_location_detail",
    "unit_detail": "_render_unit_detail",
    "department_detail": "_render_department_detail",
    "employee_detail": "_render_employee_detail",
    "category_detail": "_render_category_detail",
    "sales_order_detail": "_render_sales_order_detail",
    "shipment_detail": "_render_shipment_detail",
    "purchase_order_detail": "_render_purchase_order_detail",
    "quotation_detail": "_render_quotation_detail",
    "purchase_requisition_detail": "_render_purchase_requisition_detail",
    "purchase_receipt_detail": "_render_purchase_receipt_detail",
    "purchase_return_detail": "_render_purchase_return_detail",
    "sales_return_detail": "_render_sales_return_detail",
    "work_order_detail": "_render_work_order_detail",
    "quality_inspection_detail": "_render_quality_inspection_detail",
    "receivable_detail": "_render_receivable_detail",
    "payable_detail": "_render_payable_detail",
    "sales_invoice_detail": "_render_sales_invoice_detail",
    "purchase_invoice_detail": "_render_purchase_invoice_detail",
    "inventory_balance_detail": "_render_inventory_balance_detail",
    "inventory_adjustment_detail": "_render_inventory_adjustment_detail",
    "inventory_transfer_detail": "_render_inventory_transfer_detail",
    "inventory_check_detail": "_render_inventory_check_detail",
    "inventory_assembly_detail": "_render_inventory_assembly_detail_readonly",
    "inventory_disassembly_detail": "_render_inventory_disassembly_detail",
    "approval_record_detail": "_render_approval_record_detail",
    "service_card_detail": "_render_service_card_detail",
    "service_acceptance_detail": "_render_service_acceptance_detail",
    "service_order_detail": "_render_service_order_detail",
    "service_rma_detail": "_render_service_rma_detail",
        "production_routing_detail": "_render_production_routing_detail",
        "work_center_detail": "_render_work_center_detail",
        "subcontract_detail": "_render_subcontract_detail",
        "subcontract_issue_detail": "_render_subcontract_issue_detail",
        "subcontract_receive_detail": "_render_subcontract_receive_detail",
        "supplier_quote_detail": "_render_supplier_quote_detail",
    "work_order_requisition_detail": "_render_work_order_requisition_detail",
    "production_schedule_detail": "_render_production_schedule_detail",
    "finance_voucher_detail": "_render_finance_voucher_detail",
}


def _build_renderers(namespace, renderer_names):
    return {name: namespace[function_name] for name, function_name in renderer_names.items()}


def build_special_list_renderers(namespace):
    return _build_renderers(namespace, SPECIAL_LIST_RENDERERS)


def build_special_detail_renderers(namespace):
    return _build_renderers(namespace, SPECIAL_DETAIL_RENDERERS)


def render_special_list(
    table,
    path,
    title,
    renderers,
    category_types=None,
    category_kind_for_path=None,
):
    """Return a specialized read-only list/dashboard response, or None."""
    if path == "/system/data-health":
        return _renderer(renderers, "data_health_dashboard")()
    if path == "/approval/pending":
        return _renderer(renderers, "approval_pending")()
    if table == "equipment" and path in {"/equipment", "/production-enhance/equipment"}:
        return _renderer(renderers, "equipment_dashboard")(path)
    if table == "customers" and path in {"/customer", "/customers", "/business-partners"}:
        return _renderer(renderers, "customer_dashboard")(path)
    if table == "suppliers" and path in {"/supplier", "/suppliers"}:
        return _renderer(renderers, "supplier_dashboard")(path)
    if table == "warehouses" and path in {"/warehouse", "/warehouses"}:
        return _renderer(renderers, "warehouse_dashboard")(path)
    if table == "products" and path in {"/material", "/products"}:
        return _renderer(renderers, "material_dashboard")(path)
    if table == "locations" and path in {"/locations", "/location"}:
        return _renderer(renderers, "location_dashboard")(path)
    if table == "units" and path in {"/unit", "/units"}:
        return _renderer(renderers, "unit_dashboard")(path)
    if table == "departments" and path in {"/department", "/departments"}:
        return _renderer(renderers, "department_dashboard")(path)
    if table == "employees" and path in {"/employee", "/employees"}:
        return _renderer(renderers, "employee_dashboard")(path)

    category_kind = category_kind_for_path(path) if category_kind_for_path else None
    if category_kind and category_types and table == category_types[category_kind]["table"]:
        return _renderer(renderers, "category_dashboard")(category_kind, path)

    if table == "sales_orders" and path == "/sales-orders":
        return _renderer(renderers, "sales_dashboard")(path, document_list=True)
    if table == "sales_shipments" and path == "/shipments":
        return _renderer(renderers, "shipment_dashboard")()
    if table == "purchase_orders" and path == "/purchase-orders":
        return _renderer(renderers, "purchase_dashboard")(path, document_list=True)
    if table == "purchase_requisitions" and path in {"/purchase_request", "/purchase-requisitions"}:
        return _renderer(renderers, "purchase_requisition_dashboard")(path)
    if path == "/requisition":
        return _renderer(renderers, "work_order_requisition_dashboard")()
    if table == "purchase_receipts" and path == "/purchase_receipts":
        return _renderer(renderers, "purchase_receipt_dashboard")()
    if table == "customer_receivables" and path == "/receivables":
        return _renderer(renderers, "receivable_list")()
    if table == "supplier_payables" and path == "/payables":
        return _renderer(renderers, "payable_list")()
    if table == "inventory_balances" and path in {"/inventory/detail", "/inventory/summary"}:
        return _renderer(renderers, "inventory_balance_dashboard")(path, title)
    if table == "stock_transactions" and path == "/transactions":
        return _renderer(renderers, "stock_transaction_dashboard")()
    if table == "inventory_adjustments" and path == "/adjustments":
        return _renderer(renderers, "inventory_adjustment_list")()
    if table == "transfer_orders" and path in {"/transfers", "/stock_transfers"}:
        return _renderer(renderers, "inventory_transfer_list")()
    if table == "inventory_check_orders" and path == "/inventory_checks":
        return _renderer(renderers, "inventory_check_list")()
    if table == "work_orders" and path == "/work-orders":
        return _renderer(renderers, "work_order_list")()
    if table == "quality_inspection_records" and path == "/production-enhance/quality-inspections":
        return _renderer(renderers, "quality_inspection_dashboard")()
    if table == "machine_service_orders" and path == "/service-orders":
        return _renderer(renderers, "service_order_dashboard")()
    if table == "machine_service_rmas" and path == "/service-rmas":
        return _renderer(renderers, "service_rma_dashboard")()
    if table == "subcontract_orders" and path in {"/subcontract", "/subcontract-orders"}:
        return _renderer(renderers, "subcontract_dashboard")(path)
    if table == "production_routings" and path == "/production-routings":
        return _renderer(renderers, "production_routing_list")()
    if table == "work_centers" and path == "/work-centers":
        return _renderer(renderers, "work_center_list")()
    if table == "production_schedules" and path in {"/production-schedules", "/production-enhance/production-schedules"}:
        return _renderer(renderers, "production_schedule_list")(path)
    return None


def render_special_detail(
    table,
    record_id,
    title,
    back_url,
    renderers,
    category_types=None,
    category_kind_for_path=None,
):
    """Return a specialized read-only detail response, or None."""
    simple_detail_renderers = {
        "customers": "customer_detail",
        "suppliers": "supplier_detail",
        "warehouses": "warehouse_detail",
        "products": "material_detail",
        "locations": "location_detail",
        "units": "unit_detail",
        "departments": "department_detail",
        "employees": "employee_detail",
        "sales_orders": "sales_order_detail",
        "sales_shipments": "shipment_detail",
        "purchase_orders": "purchase_order_detail",
        "quotation_headers": "quotation_detail",
        "purchase_requisitions": "purchase_requisition_detail",
        "purchase_receipts": "purchase_receipt_detail",
        "purchase_returns": "purchase_return_detail",
        "sales_returns": "sales_return_detail",
        "work_orders": "work_order_detail",
        "quality_inspection_records": "quality_inspection_detail",
        "customer_receivables": "receivable_detail",
        "supplier_payables": "payable_detail",
        "sales_invoices": "sales_invoice_detail",
        "purchase_invoices": "purchase_invoice_detail",
        "inventory_balances": "inventory_balance_detail",
        "inventory_adjustments": "inventory_adjustment_detail",
        "transfer_orders": "inventory_transfer_detail",
        "inventory_check_orders": "inventory_check_detail",
        "approval_records": "approval_record_detail",
        "machine_service_cards": "service_card_detail",
        "machine_service_acceptance_checks": "service_acceptance_detail",
        "machine_service_orders": "service_order_detail",
        "machine_service_rmas": "service_rma_detail",
        "production_routings": "production_routing_detail",
        "work_centers": "work_center_detail",
        "subcontract_orders": "subcontract_detail",
        "subcontract_issue_orders": "subcontract_issue_detail",
        "subcontract_receive_orders": "subcontract_receive_detail",
        "supplier_quotes": "supplier_quote_detail",
        "pick_lists": "work_order_requisition_detail",
        "production_schedules": "production_schedule_detail",
        "vouchers": "finance_voucher_detail",
    }
    if table == "inventory_assembly_orders" and back_url == "/assembly-orders":
        return _renderer(renderers, "inventory_assembly_detail")(record_id, back_url)
    if table == "inventory_assembly_orders" and back_url == "/disassembly-orders":
        return _renderer(renderers, "inventory_disassembly_detail")(record_id, back_url)
    renderer_name = simple_detail_renderers.get(table)
    if renderer_name:
        return _renderer(renderers, renderer_name)(record_id, back_url)

    category_kind = category_kind_for_path(back_url) if category_kind_for_path else None
    if category_kind and category_types and table == category_types[category_kind]["table"]:
        return _renderer(renderers, "category_detail")(category_kind, record_id, back_url)
    return None


def service_order_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5173\u95ed", "\u5df2\u5b8c\u6210", "closed", "completed"}:
        return "\u5df2\u7ed3\u675f\uff0c\u4fdd\u7559\u67e5\u770b\u3001\u9644\u4ef6\u548c\u5907\u6ce8"
    if value in {"\u5f85\u6d3e\u5de5", "\u65b0\u5efa", "pending", ""}:
        return "\u6d3e\u5de5"
    if value in {"\u5df2\u6d3e\u5de5"}:
        return "\u5904\u7406\u670d\u52a1"
    if value in {"\u5904\u7406\u4e2d", "\u5df2\u5904\u7406"}:
        return "\u9a8c\u6536\u6216\u767b\u8bb0\u5907\u4ef6/\u8d39\u7528"
    if value in {"\u5df2\u9a8c\u6536"}:
        return "\u56de\u8bbf"
    if value in {"\u5df2\u56de\u8bbf"}:
        return "\u6536\u8d39\u6216\u5173\u95ed"
    return "\u67e5\u770b\u8be6\u60c5\u5e76\u6309\u72b6\u6001\u5904\u7406"


def service_order_data_source(row):
    text = " ".join(
        str(row.get(key) or "")
        for key in ("order_no", "issue_summary", "remark", "project_code", "serial_no")
    )
    return "\u6d4b\u8bd5/\u5ba1\u8ba1\u6570\u636e" if any(marker in text for marker in ("pytest", "PYTEST", "SVC-", "GT-TRIAL")) else "\u4e1a\u52a1\u6570\u636e"


def service_rma_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5173\u95ed", "closed"}:
        return "\u5df2\u5173\u95ed\uff0c\u4fdd\u7559\u67e5\u770b\u3001\u9644\u4ef6\u548c\u5907\u6ce8"
    if value in {"\u5f85\u8bca\u65ad", "\u65b0\u5efa", "pending", ""}:
        return "\u8bca\u65ad"
    if value in {"\u5df2\u8bca\u65ad"}:
        return "\u7d22\u8d54\u767b\u8bb0"
    if value in {"\u7d22\u8d54\u4e2d", "\u5df2\u7d22\u8d54"}:
        return "\u8ffd\u56de\u767b\u8bb0"
    if value in {"\u5df2\u8ffd\u56de"}:
        return "\u5173\u95ed"
    return "\u67e5\u770b\u8be6\u60c5\u5e76\u6309\u72b6\u6001\u5904\u7406"


def service_rma_data_source(row):
    text = " ".join(
        str(row.get(key) or "")
        for key in ("rma_no", "fault_summary", "remark", "project_code", "serial_no")
    )
    return "\u6d4b\u8bd5/\u5ba1\u8ba1\u6570\u636e" if any(marker in text for marker in ("pytest", "PYTEST", "RMA-PRJ", "RMA-SO-PRJ")) else "\u4e1a\u52a1\u6570\u636e"


def shipment_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u53d6\u6d88", "cancelled", "canceled"}:
        return "\u5df2\u53d6\u6d88\uff0c\u4fdd\u7559\u67e5\u770b\u548c\u8ffd\u6eaf"
    if value in {"\u5df2\u53d1\u8d27", "\u5df2\u5b8c\u6210", "shipped", "completed"}:
        return "\u786e\u8ba4\u56de\u6b3e\u548c\u5bf9\u8d26"
    if value in {"\u5f85\u53d1\u8d27", "\u65b0\u5efa", "pending", ""}:
        return "\u6838\u5bf9\u5e93\u5b58\u5e76\u53d1\u8d27"
    return "\u67e5\u770b\u53d1\u8d27\u660e\u7ec6\u5e76\u6309\u72b6\u6001\u5904\u7406"


def quote_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5931\u6548", "\u5df2\u4f5c\u5e9f", "cancelled", "expired"}:
        return "\u5df2\u7ed3\u675f\uff0c\u4fdd\u7559\u67e5\u770b\u548c\u590d\u7528"
    if value in {"\u5df2\u8f6c\u8ba2\u5355", "\u5df2\u6210\u4ea4", "converted", "won"}:
        return "\u8ddf\u8fdb\u8ba2\u5355\u4ea4\u4ed8"
    if value in {"\u5f85\u786e\u8ba4", "\u65b0\u5efa", "draft", "pending", ""}:
        return "\u5ba1\u6838\u4ef7\u683c\u5e76\u53d1\u9001\u5ba2\u6237"
    return "\u8ddf\u8fdb\u62a5\u4ef7\u786e\u8ba4"


def purchase_quote_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5931\u6548", "\u5df2\u4f5c\u5e9f", "cancelled", "expired"}:
        return "\u5df2\u7ed3\u675f\uff0c\u4fdd\u7559\u67e5\u770b\u548c\u6bd4\u4ef7"
    if value in {"\u5df2\u91c7\u7eb3", "\u5df2\u8f6c\u91c7\u8d2d", "accepted", "converted"}:
        return "\u8ddf\u8fdb\u91c7\u8d2d\u8ba2\u5355"
    if value in {"\u5f85\u6bd4\u4ef7", "\u5f85\u786e\u8ba4", "\u65b0\u5efa", "draft", "pending", ""}:
        return "\u6bd4\u4ef7\u5e76\u786e\u8ba4\u4f9b\u5e94\u5546"
    return "\u67e5\u770b\u62a5\u4ef7\u5e76\u6309\u72b6\u6001\u5904\u7406"


def return_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5b8c\u6210", "\u5df2\u5173\u95ed", "completed", "closed"}:
        return "\u5df2\u5b8c\u6210\uff0c\u6838\u5bf9\u9000\u8d27\u548c\u5f80\u6765"
    if value in {"\u5f85\u5165\u5e93", "\u5f85\u9000\u8d27", "\u65b0\u5efa", "pending", ""}:
        return "\u6838\u5bf9\u660e\u7ec6\u5e76\u5904\u7406\u5e93\u5b58"
    return "\u67e5\u770b\u9000\u8d27\u660e\u7ec6\u5e76\u6309\u72b6\u6001\u5904\u7406"


def settlement_next_step(status, settled_label):
    value = (status or "").strip()
    if value in {"\u5df2\u4f5c\u5e9f", "cancelled", "void"}:
        return "\u5df2\u4f5c\u5e9f\uff0c\u4fdd\u7559\u5bf9\u8d26\u8bb0\u5f55"
    if value in {"\u5df2\u5ba1\u6838", "\u5df2\u786e\u8ba4", "confirmed", "approved", "posted"}:
        return settled_label
    if value in {"\u65b0\u5efa", "\u8349\u7a3f", "draft", "pending", ""}:
        return "\u6838\u5bf9\u5f80\u6765\u5e76\u786e\u8ba4"
    return "\u67e5\u770b\u660e\u7ec6\u5e76\u6309\u72b6\u6001\u5904\u7406"


def invoice_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u7ea2\u51b2", "\u5df2\u4f5c\u5e9f", "cancelled", "void"}:
        return "\u5df2\u7ed3\u675f\uff0c\u4fdd\u7559\u53d1\u7968\u548c\u5bf9\u8d26\u8bb0\u5f55"
    if value in {"\u5df2\u5f00\u7968", "\u5df2\u786e\u8ba4", "issued", "confirmed", "posted"}:
        return "\u8ddf\u8fdb\u5f80\u6765\u6838\u9500"
    if value in {"\u5f85\u5f00\u7968", "\u65b0\u5efa", "\u8349\u7a3f", "draft", "pending", ""}:
        return "\u6838\u5bf9\u5355\u636e\u5e76\u5f00\u7968"
    return "\u67e5\u770b\u53d1\u7968\u660e\u7ec6\u5e76\u6309\u72b6\u6001\u5904\u7406"


def voucher_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u4f5c\u5e9f", "void", "cancelled"}:
        return "\u5df2\u4f5c\u5e9f\uff0c\u4fdd\u7559\u5ba1\u8ba1\u8bb0\u5f55"
    if value in {"\u5df2\u8fc7\u8d26", "\u5df2\u5ba1\u6838", "posted", "approved"}:
        return "\u5df2\u8fc7\u8d26\uff0c\u7528\u4e8e\u62a5\u8868\u548c\u5bf9\u8d26"
    if value in {"\u5f85\u5ba1\u6838", "\u65b0\u5efa", "\u8349\u7a3f", "draft", "pending", ""}:
        return "\u5ba1\u6838\u5e76\u8fc7\u8d26"
    return "\u67e5\u770b\u51ed\u8bc1\u660e\u7ec6\u5e76\u6309\u72b6\u6001\u5904\u7406"


def subcontract_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5173\u95ed", "\u5df2\u5b8c\u6210", "closed", "completed"}:
        return "\u5df2\u5b8c\u6210\uff0c\u6838\u5bf9\u53d1\u6599\u3001\u6536\u8d27\u548c\u5bf9\u8d26"
    if value in {"\u5f85\u53d1\u6599", "\u65b0\u5efa", "\u8349\u7a3f", "draft", "pending", ""}:
        return "\u5b89\u6392\u59d4\u5916\u53d1\u6599"
    if value in {"\u5df2\u53d1\u6599", "\u52a0\u5de5\u4e2d", "issued", "processing"}:
        return "\u8ddf\u8fdb\u59d4\u5916\u6536\u8d27"
    return "\u67e5\u770b\u59d4\u5916\u8ba2\u5355\u5e76\u6309\u72b6\u6001\u5904\u7406"


def quality_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5173\u95ed", "\u5df2\u5b8c\u6210", "closed", "completed"}:
        return "\u5df2\u5b8c\u6210\uff0c\u4fdd\u7559\u68c0\u9a8c\u8bb0\u5f55"
    if value in {"\u4e0d\u5408\u683c", "failed", "ng"}:
        return "\u542f\u52a8\u4e0d\u5408\u683c\u5904\u7406"
    if value in {"\u5f85\u68c0", "\u65b0\u5efa", "\u8349\u7a3f", "draft", "pending", ""}:
        return "\u6267\u884c\u68c0\u9a8c\u5e76\u5224\u5b9a"
    return "\u67e5\u770b\u8d28\u91cf\u68c0\u9a8c\u5e76\u6309\u72b6\u6001\u5904\u7406"


def service_acceptance_next_step(result):
    value = (result or "").strip()
    if value in {"\u5408\u683c", "\u901a\u8fc7", "pass", "passed"}:
        return "\u767b\u8bb0\u5ba2\u6237\u786e\u8ba4\u5e76\u8fdb\u5165\u56de\u8bbf"
    if value in {"\u4e0d\u5408\u683c", "\u672a\u901a\u8fc7", "fail", "failed"}:
        return "\u5b89\u6392\u6574\u6539\u5e76\u590d\u9a8c"
    return "\u5b8c\u6210\u5b89\u88c5\u9a8c\u6536\u5224\u5b9a"


def service_visit_next_step(result):
    value = (result or "").strip()
    if value in {"\u5df2\u5173\u95ed", "\u5df2\u5b8c\u6210", "\u6ee1\u610f", "closed", "completed"}:
        return "\u5df2\u5b8c\u6210\uff0c\u5f52\u6863\u670d\u52a1\u8bb0\u5f55"
    if value in {"\u9700\u8ddf\u8fdb", "\u4e0d\u6ee1\u610f", "follow_up", "open"}:
        return "\u751f\u6210\u8ddf\u8fdb\u4efb\u52a1"
    return "\u56de\u8bbf\u5ba2\u6237\u5e76\u8bb0\u5f55\u7ed3\u679c"


def inventory_balance_next_step(quantity):
    try:
        qty = float(quantity or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty < 0:
        return "\u8d1f\u5e93\u5b58\uff0c\u9700\u6838\u5bf9\u51fa\u5165\u5e93"
    if qty == 0:
        return "\u65e0\u5e93\u5b58\uff0c\u5173\u6ce8\u91c7\u8d2d\u6216\u9886\u6599\u9700\u6c42"
    return "\u67e5\u770b\u5e93\u5b58\u6d41\u6c34\u548c\u6279\u6b21"


def stock_transaction_next_step(transaction_type):
    value = (transaction_type or "").strip()
    if value in {"\u5165\u5e93", "in", "inbound", "purchase_receipt"}:
        return "\u6838\u5bf9\u5165\u5e93\u6765\u6e90\u548c\u6279\u6b21"
    if value in {"\u51fa\u5e93", "out", "outbound", "shipment", "issue"}:
        return "\u6838\u5bf9\u51fa\u5e93\u53bb\u5411\u548c\u7ed3\u5b58"
    if value in {"\u8c03\u62e8", "transfer"}:
        return "\u6838\u5bf9\u8c03\u51fa\u8c03\u5165\u4ed3\u5e93"
    return "\u67e5\u770b\u6765\u6e90\u5355\u636e\u548c\u5e93\u5b58\u5f71\u54cd"


def inventory_alert_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5904\u7406", "\u5df2\u5173\u95ed", "closed", "resolved"}:
        return "\u5df2\u5904\u7406\uff0c\u4fdd\u7559\u9884\u8b66\u8bb0\u5f55"
    if value in {"\u65b0\u5efa", "\u5f85\u5904\u7406", "open", "pending", ""}:
        return "\u8865\u8d27\u3001\u8c03\u62e8\u6216\u6838\u5bf9\u5b89\u5168\u5e93\u5b58"
    return "\u6839\u636e\u9884\u8b66\u72b6\u6001\u5904\u7406"


def batch_next_step(quantity):
    try:
        qty = float(quantity or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        return "\u6279\u6b21\u65e0\u53ef\u7528\u6570\u91cf\uff0c\u4ec5\u4fdd\u7559\u8ffd\u6eaf"
    return "\u67e5\u770b\u6279\u6b21\u6d41\u5411\u548c\u673a\u53f7\u8ffd\u6eaf"


def mrp_requirement_next_step(status):
    value = (status or "").strip()
    if value in {"已关闭", "已采购", "已处理", "closed", "resolved"}:
        return "已处理，到货或替代确认后回到齐套复核"
    if value in {"新建", "待处理", "open", "pending", ""}:
        return "进入缺料转采购，生成受控请购或采购建议"
    return "按缺料状态确认下一步，处理后再齐套复核"


def enhance_mrp_requirement_row(row):
    project_code = (row.get("project_code") or "").strip()
    serial_no = (row.get("serial_no") or "").strip()
    supply_mode = (row.get("supply_mode") or "").strip().lower()
    status = (row.get("status") or "").strip()
    try:
        shortage_qty = float(row.get("shortage_quantity") or 0)
    except (TypeError, ValueError):
        shortage_qty = 0

    row["source_work_order"] = row.get("work_order_no") or row.get("source_work_order") or row.get("source_no") or "待关联工单"
    row["trace_axis"] = " / ".join(part for part in (project_code, serial_no) if part) or "未指定"
    row["material_shortage"] = row.get("shortage_quantity") or row.get("shortage_qty") or 0
    row["purchase_request_link"] = "/procurement/suggestions"
    if status in {"fulfilled", "已满足", "已关闭", "已采购", "已处理"} or shortage_qty <= 0:
        row["owner_role"] = "生产计划"
        row["controlled_entry"] = "齐套复核"
        row["blocked_reason"] = "缺料已覆盖，待复核齐套"
    elif supply_mode in {"subcontract", "outsourcing", "委外", "外协"}:
        row["owner_role"] = "生产计划/委外采购"
        row["controlled_entry"] = "委外建议确认"
        row["blocked_reason"] = "需确认委外工序、发料和到货节点"
    elif supply_mode in {"alternative", "substitute", "替代"}:
        row["owner_role"] = "生产计划/技术"
        row["controlled_entry"] = "替代料确认"
        row["blocked_reason"] = "需先确认 BOM 替代料或技术放行"
    else:
        row["owner_role"] = "生产计划/采购/仓库"
        row["controlled_entry"] = "缺料转采购"
        row["blocked_reason"] = "需核对库存、在途采购和请购覆盖"
    row["downstream_impact"] = "影响工单齐套、领料、装配和交付"
    row["recheck_entry"] = "再齐套复核"
    return row


def schedule_next_step(status):
    value = (status or "").strip()
    if value in {"已完成", "已关闭", "completed", "closed"}:
        return "已完成，核对工单实绩和报工记录"
    if value in {"待派工", "新建", "计划", "planned", "pending", "scheduled", ""}:
        return "确认齐套、工作中心和负责人后派工"
    if value in {"已派工", "生产中", "running", "in_progress", "dispatched"}:
        return "跟踪报工进度和现场异常"
    if value in {"改期", "延期", "rescheduled"}:
        return "确认新计划日期、工作中心负荷和交付影响"
    if value in {"暂停", "受阻", "paused"}:
        return "解除堵点后恢复派工或重新排程"
    return "查看排程并按状态处理"


def enhance_production_schedule_row(row):
    status = (row.get("status") or "").strip()
    planned_start = row.get("planned_start_date") or row.get("start_date") or "-"
    planned_end = row.get("planned_end_date") or row.get("end_date") or "-"
    actual_start = row.get("actual_start_date") or row.get("actual_start") or "-"
    actual_end = row.get("actual_end_date") or row.get("actual_end") or "-"
    work_center_parts = [row.get("work_center_code"), row.get("work_center_name") or row.get("work_center_id")]
    source_parts = [row.get("wo_no") or row.get("work_order_id"), row.get("project_code"), row.get("serial_no")]
    row["planned_date_range"] = f"{planned_start} 至 {planned_end}"
    row["schedule_compare"] = f"计划 {planned_start} 至 {planned_end} / 实际 {actual_start} 至 {actual_end}"
    row["work_center_display"] = " / ".join(str(part) for part in work_center_parts if part) or "-"
    row["source_work_order"] = " / ".join(str(part) for part in source_parts if part) or "-"
    row["owner_role"] = row.get("owner_role") or "生产计划"
    row["responsible_person"] = row.get("responsible_person") or row.get("dispatched_to") or "-"
    row["dispatch_status"] = row.get("dispatch_status") or ("已派工" if row.get("dispatched_at") else "待派工")
    if status in {"已完成", "已关闭", "completed", "closed"}:
        row["blocked_reason"] = row.get("blocked_reason") or "无堵点，核对工单实绩和报工记录"
        row["next_action"] = row.get("next_action") or "核对工单实绩和成本归集"
    elif actual_start == "-" and status in {"待派工", "新建", "计划", "planned", "pending", "scheduled", ""}:
        row["blocked_reason"] = row.get("blocked_reason") or "等待齐套、工作中心负荷确认或派工"
        row["next_action"] = row.get("next_action") or "派工到负责人并确认计划日期"
    elif status in {"改期", "延期", "rescheduled"}:
        row["blocked_reason"] = row.get("blocked_reason") or "计划日期或工作中心负荷需要重新确认"
        row["next_action"] = row.get("next_action") or "确认新计划日期并同步下游交付影响"
    elif status in {"暂停", "受阻", "paused"}:
        row["blocked_reason"] = row.get("blocked_reason") or "存在现场、齐套、人员或设备堵点"
        row["next_action"] = row.get("next_action") or "解除堵点后恢复派工或重新排程"
    elif actual_start != "-" and actual_end == "-":
        row["blocked_reason"] = row.get("blocked_reason") or "生产中，需跟进报工进度和异常"
        row["next_action"] = row.get("next_action") or "登记或审核工序报工"
    else:
        row["blocked_reason"] = row.get("blocked_reason") or "按排程状态跟进"
        row["next_action"] = row.get("next_action") or schedule_next_step(status)
    row["downstream_impact"] = row.get("downstream_impact") or "影响工作中心负荷、现场开工和工序报工节奏"
    row["dispatch_action"] = "派工/改期"
    row["report_action"] = "报工"
    return row

def pick_list_next_step(status):
    value = (status or "").strip()
    if value in {"\u5df2\u5b8c\u6210", "\u5df2\u5173\u95ed", "completed", "closed"}:
        return "\u5df2\u9886\u6599\uff0c\u6838\u5bf9\u5de5\u5355\u6210\u672c"
    if value in {"\u5f85\u9886\u6599", "\u65b0\u5efa", "\u8349\u7a3f", "draft", "pending", ""}:
        return "\u6838\u5bf9\u5e93\u5b58\u5e76\u53d1\u6599"
    return "\u67e5\u770b\u9886\u6599\u660e\u7ec6\u5e76\u6309\u72b6\u6001\u5904\u7406"


def work_order_list_next_step(row):
    value = (row.get("status") or "").strip()
    if value in {"\u5df2\u5b8c\u6210", "\u5df2\u5b8c\u5de5", "\u5df2\u5173\u95ed", "completed", "closed"}:
        return "\u6838\u5bf9\u6210\u672c\u548c\u8d28\u68c0\u8bb0\u5f55"
    if value in {"\u751f\u4ea7\u4e2d", "\u52a0\u5de5", "\u88c5\u914d", "\u8c03\u8bd5", "running", "in_progress"}:
        return "\u8ddf\u8e2a\u8fdb\u5ea6\u3001\u59d4\u5916\u5230\u8d27\u548c\u5b8c\u5de5\u5165\u5e93"
    return "\u6838\u5bf9\u9f50\u5957\u5e76\u5b89\u6392\u9886\u6599"


def work_order_list_owner(row):
    value = (row.get("status") or "").strip()
    if value in {"\u5df2\u5b8c\u6210", "\u5df2\u5b8c\u5de5", "\u5df2\u5173\u95ed", "completed", "closed"}:
        return "\u751f\u4ea7/\u8d22\u52a1"
    return "\u751f\u4ea7/\u4ed3\u5e93"


def inventory_posting_next_step(row, posted_text):
    value = (row.get("status") or "").strip()
    if value in {"\u5f85\u8fc7\u8d26", "\u5f85\u5ba1\u6838", "\u8349\u7a3f", "draft", "pending", ""}:
        return "\u786e\u8ba4\u8fc7\u8d26"
    if value in {"\u5df2\u8fc7\u8d26", "posted", "completed", "\u5df2\u5b8c\u6210"}:
        return posted_text
    return "\u5904\u7406\u5355\u636e\u72b6\u6001"


DOCUMENT_LIST_CONFIG = {
    "/work-orders": {
        "subtitle": "\u751f\u4ea7\u5de5\u5355\u5217\u8868\uff0c\u4ec5\u5c55\u793a\u548c\u8ddf\u8fdb\u5df2\u6709\u5de5\u5355\uff1b\u65b0\u589e\u5de5\u5355\u8bf7\u4ece\u751f\u4ea7\u5355\u636e\u5165\u53e3\u8fdb\u5165\u3002",
        "columns": [("wo_no", "\u5de5\u5355"), ("wo_date", "\u65e5\u671f"), ("product_id", "\u7269\u6599"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("quantity", "\u6570\u91cf"), ("status", "\u5355\u636e\u72b6\u6001")],
        "next_step": work_order_list_next_step,
    },
    "/transfers": {
        "subtitle": "\u5e93\u5b58\u8c03\u62e8\u5355\u636e\u5217\u8868\uff0c\u6309\u8c03\u62e8\u5355\u53f7\u3001\u72b6\u6001\u548c\u5907\u6ce8\u5b9a\u4f4d\u8bb0\u5f55\u3002",
        "add_url": "/transfers/new",
        "columns": [("transfer_no", "\u8c03\u62e8\u5355"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "next_step": lambda row: inventory_posting_next_step(row, "\u67e5\u770b\u8c03\u62e8\u6d41\u6c34\u3001\u6253\u5370\u3001\u9644\u4ef6\u548c\u5907\u6ce8"),
        "bulk_doc_type": "transfer",
    },
    "/stock_transfers": {
        "subtitle": "\u5e93\u5b58\u8c03\u62e8\u5355\u636e\u5217\u8868\uff0c\u6309\u8c03\u62e8\u5355\u53f7\u3001\u72b6\u6001\u548c\u5907\u6ce8\u5b9a\u4f4d\u8bb0\u5f55\u3002",
        "add_url": "/transfers/new",
        "columns": [("transfer_no", "\u8c03\u62e8\u5355"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "detail_base": "/transfers",
        "next_step": lambda row: inventory_posting_next_step(row, "\u67e5\u770b\u8c03\u62e8\u6d41\u6c34\u3001\u6253\u5370\u3001\u9644\u4ef6\u548c\u5907\u6ce8"),
        "bulk_doc_type": "transfer",
    },
    "/adjustments": {
        "subtitle": "\u5e93\u5b58\u8c03\u6574\u5355\u636e\u5217\u8868\uff0c\u8c03\u6574\u539f\u56e0\u5fc5\u586b\uff1b\u672a\u5ba1\u6838/\u672a\u8fc7\u8d26\u8bb0\u5f55\u4e0d\u5f71\u54cd\u6b63\u5f0f\u7ed3\u5b58\uff0c\u9700\u6309\u72b6\u6001\u8ddf\u8fdb\u5ba1\u6279\u3002",
        "add_url": "/adjustments/new",
        "columns": [("adj_no", "\u8c03\u6574\u5355"), ("adj_date", "\u65e5\u671f"), ("adj_type", "\u7c7b\u578b"), ("diff_quantity", "\u6570\u91cf"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "next_step": lambda row: inventory_posting_next_step(row, "\u67e5\u770b\u5e93\u5b58\u66f4\u6b63\u6d41\u6c34\u3001\u6253\u5370\u3001\u9644\u4ef6\u548c\u5907\u6ce8"),
        "bulk_doc_type": "adjustment",
    },
    "/inventory_checks": {
        "subtitle": "\u5e93\u5b58\u76d8\u70b9\u5355\u636e\u5217\u8868\uff0c\u6309\u76d8\u70b9\u5355\u53f7\u3001\u72b6\u6001\u548c\u5907\u6ce8\u5b9a\u4f4d\u8bb0\u5f55\uff1b\u8be6\u60c5\u9875\u67e5\u770b\u76d8\u76c8\u3001\u76d8\u4e8f\u548c\u5dee\u5f02\u91d1\u989d\u5206\u6790\u3002",
        "add_url": "/inventory_checks/new",
        "columns": [("check_no", "\u76d8\u70b9\u5355"), ("check_date", "\u65e5\u671f"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "next_step": lambda row: "\u67e5\u770b\u76d8\u70b9\u5dee\u5f02\u3001\u6253\u5370\u3001\u9644\u4ef6\u548c\u5907\u6ce8",
        "bulk_doc_type": "check",
    },
    "/assembly-orders": {
        "subtitle": "\u7ec4\u88c5\u5355\u5217\u8868\uff0c\u6309\u5355\u53f7\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u548c\u72b6\u6001\u8ddf\u8fdb\u5b50\u4ef6\u51fa\u5e93\u4e0e\u4e3b\u4ef6\u5165\u5e93\u3002",
        "add_url": "/assembly-orders/new",
        "columns": [("assembly_no", "\u7ec4\u88c5\u5355"), ("doc_date", "\u65e5\u671f"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "detail_base": "/assembly-orders",
        "next_step": lambda row: inventory_posting_next_step(row, "\u67e5\u770b\u7ec4\u88c5\u660e\u7ec6\u3001\u5e93\u5b58\u6d41\u6c34\u548c\u5173\u95ed\u72b6\u6001"),
        "bulk_doc_type": "assembly",
    },
    "/disassembly-orders": {
        "subtitle": "\u62c6\u5378\u5355\u5217\u8868\uff0c\u6309\u5355\u53f7\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u548c\u72b6\u6001\u8ddf\u8fdb\u4e3b\u4ef6\u51fa\u5e93\u4e0e\u5b50\u4ef6\u5165\u5e93\u3002",
        "add_url": "/disassembly-orders/new",
        "columns": [("assembly_no", "\u62c6\u5378\u5355"), ("doc_date", "\u65e5\u671f"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "detail_base": "/disassembly-orders",
        "next_step": lambda row: inventory_posting_next_step(row, "\u67e5\u770b\u62c6\u5378\u660e\u7ec6\u3001\u5e93\u5b58\u6d41\u6c34\u548c\u5173\u95ed\u72b6\u6001"),
        "bulk_doc_type": "disassembly",
    },
    "/subcontract_issue": {
        "subtitle": "\u59d4\u5916\u53d1\u6599\u5355\u636e\u5217\u8868\uff0c\u6309\u53d1\u6599\u5355\u3001\u59d4\u5916\u5355\u3001\u52a0\u5de5\u5382\u5546\u3001\u7269\u6599\u548c\u72b6\u6001\u5b9a\u4f4d\u5f85\u53d1\u6599\u8bb0\u5f55\u3002",
        "add_url": "/subcontract_issue/new",
        "columns": [("issue_no", "\u53d1\u6599\u5355"), ("date", "\u65e5\u671f"), ("subcontract_order_id", "\u59d4\u5916\u5355"), ("supplier_id", "\u52a0\u5de5\u5382\u5546"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "next_step": lambda row: "\u5f85\u53d1\u6599" if row.get("status") in {"pending", "\u5f85\u53d1\u6599", "\u65b0\u5efa", ""} else "\u67e5\u770b\u53d1\u6599\u8bb0\u5f55\u3001\u6253\u5370\u548c\u8ffd\u6eaf",
    },
    "/subcontract_receive": {
        "subtitle": "\u59d4\u5916\u6536\u8d27\u5355\u636e\u5217\u8868\uff0c\u6309\u6536\u8d27\u5355\u3001\u59d4\u5916\u5355\u3001\u52a0\u5de5\u5382\u5546\u3001\u6536\u8d27\u6570\u91cf\u548c\u72b6\u6001\u5b9a\u4f4d\u5f85\u6536\u8d27\u8bb0\u5f55\u3002",
        "add_url": "/subcontract_receive/new",
        "columns": [("receive_no", "\u6536\u8d27\u5355"), ("date", "\u65e5\u671f"), ("subcontract_order_id", "\u59d4\u5916\u5355"), ("supplier_id", "\u52a0\u5de5\u5382\u5546"), ("total_quantity", "\u6536\u8d27\u6570\u91cf"), ("total_scrap", "\u62a5\u5e9f\u6570\u91cf"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: "\u5f85\u6536\u8d27" if row.get("status") in {"pending", "\u5f85\u6536\u8d27", "\u5f85\u5165\u5e93", "\u65b0\u5efa", ""} else "\u67e5\u770b\u6536\u8d27\u8bb0\u5f55\u3001\u6253\u5370\u548c\u8ffd\u6eaf",
    },
    "/service-orders": {
        "subtitle": "\u670d\u52a1\u5355\u5217\u8868\uff0c\u6309\u6d3e\u5de5\u3001\u5904\u7406\u3001\u9a8c\u6536\u3001\u56de\u8bbf\u3001\u6536\u8d39\u548c\u5173\u95ed\u63a8\u8fdb\u3002",
        "add_url": "/service-orders/new",
        "columns": [("order_no", "\u670d\u52a1\u5355"), ("service_date", "\u65e5\u671f"), ("service_type", "\u7c7b\u578b"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: service_order_next_step(row.get("status")),
        "data_source": service_order_data_source,
    },
    "/service-rmas": {
        "subtitle": "RMA\u5217\u8868\uff0c\u6309\u8bca\u65ad\u3001\u7d22\u8d54\u3001\u8ffd\u56de\u548c\u5173\u95ed\u63a8\u8fdb\u3002",
        "add_url": "/service-rmas/new",
        "columns": [("rma_no", "RMA"), ("rma_date", "\u65e5\u671f"), ("warranty_scope", "\u8d28\u4fdd"), ("responsibility_type", "\u8d23\u4efb"), ("claim_status", "\u7d22\u8d54"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: service_rma_next_step(row.get("status")),
        "data_source": service_rma_data_source,
    },
    "/service-cards": {
        "subtitle": "\u8bbe\u5907\u670d\u52a1\u6863\u6848\u5217\u8868\uff0c\u6309\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u5ba2\u6237\u548c\u8d28\u4fdd\u72b6\u6001\u8ffd\u8e2a\u552e\u540e\u95ed\u73af\u3002",
        "columns": [("card_no", "服务档案号"), ("serial_no", "\u673a\u53f7"), ("project_code", "\u9879\u76ee\u53f7"), ("customer_id", "\u5ba2\u6237"), ("machine_model", "\u673a\u578b"), ("install_date", "\u5b89\u88c5\u65e5\u671f"), ("warranty_end_date", "\u8d28\u4fdd\u5230\u671f"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: "\u8ddf\u8fdb\u5b89\u88c5\u9a8c\u6536\u3001\u670d\u52a1\u5355\u548cRMA\u95ed\u73af",
    },
    "/shipments": {
        "subtitle": "\u9500\u552e\u53d1\u8d27\u5355\u5217\u8868\uff0c\u6309\u53d1\u8d27\u5355\u3001\u9500\u552e\u5355\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u670d\u52a1\u6863\u6848\u548c\u72b6\u6001\u8ffd\u8e2a\u4ea4\u4ed8\u5230\u552e\u540e\u3002",
        "add_url": "/shipments/new",
        "columns": [("shipment_no", "\u53d1\u8d27\u5355"), ("order_no", "\u9500\u552e\u5355"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("shipment_date", "\u53d1\u8d27\u65e5\u671f"), ("service_card_status", "\u670d\u52a1\u6863\u6848"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: "\u751f\u6210\u6216\u8865\u9f50\u670d\u52a1\u6863\u6848" if not row.get("service_card_id") else shipment_next_step(row.get("status")),
    },
    "/quotations": {
        "subtitle": "\u62a5\u4ef7\u5355\u5217\u8868\uff0c\u6309\u5ba2\u6237\u3001\u6765\u6e90\u5355\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u673a\u578b\u3001\u91d1\u989d\u548c\u72b6\u6001\u8ddf\u8fdb\u8f6c\u8ba2\u5355\u3002",
        "add_url": "/quotations/new",
        "columns": [("quote_no", "\u62a5\u4ef7\u5355"), ("customer_id", "\u5ba2\u6237"), ("source_no", "\u6765\u6e90\u5355"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("machine_type", "\u673a\u578b"), ("quote_date", "\u62a5\u4ef7\u65e5\u671f"), ("valid_until", "\u6709\u6548\u671f"), ("amount_with_tax", "\u542b\u7a0e\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: quote_next_step(row.get("status")),
    },
    "/sales-forecasts": {
        "subtitle": "销售预测单入口，用于记录客户需求、预计项目/机号和预计金额；当前复用报价前置数据，不写库存、应收或生产需求。",
        "add_url": "/quotations/new",
        "detail_base": "/quotations",
        "columns": [("quote_no", "预测单"), ("customer_id", "客户"), ("source_no", "来源线索"), ("project_code", "项目号"), ("serial_no", "机号"), ("machine_type", "机型"), ("quote_date", "预测日期"), ("amount_with_tax", "预计含税金额"), ("status", "状态")],
        "next_step": lambda row: quote_next_step(row.get("status")),
    },
    "/sales-inquiries": {
        "subtitle": "询价单入口，用于承接客户询价并转报价；当前复用报价单据头和明细，不写库存、应收或财务数据。",
        "add_url": "/quotations/new",
        "detail_base": "/quotations",
        "columns": [("quote_no", "询价/报价单"), ("customer_id", "客户"), ("source_no", "询价来源"), ("project_code", "项目号"), ("serial_no", "机号"), ("machine_type", "机型"), ("quote_date", "单据日期"), ("valid_until", "有效期"), ("status", "状态")],
        "next_step": lambda row: quote_next_step(row.get("status")),
    },
    "/supplier-quotes": {
        "subtitle": "\u4f9b\u5e94\u5546\u62a5\u4ef7\u5217\u8868\uff0c\u6309\u4f9b\u5e94\u5546\u3001\u7269\u6599\u3001\u4ef7\u683c\u548c\u72b6\u6001\u8fdb\u884c\u6bd4\u4ef7\u3002",
        "columns": [("quote_no", "\u62a5\u4ef7\u5355"), ("supplier_id", "\u4f9b\u5e94\u5546"), ("quote_date", "\u62a5\u4ef7\u65e5\u671f"), ("valid_until", "\u6709\u6548\u671f"), ("total_amount", "\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: purchase_quote_next_step(row.get("status")),
    },
    "/sales-returns": {
        "subtitle": "\u9500\u552e\u9000\u8d27\u5355\u5217\u8868\uff0c\u6309\u9000\u8d27\u5355\u3001\u6765\u6e90\u9500\u552e\u5355\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u5ba2\u6237\u3001\u91d1\u989d\u548c\u72b6\u6001\u8ffd\u8e2a\u9000\u8d27\u5165\u5e93\u4e0e\u5bf9\u8d26\u3002",
        "add_url": "/sales-returns/new",
        "columns": [("return_no", "\u9000\u8d27\u5355"), ("source_order_no", "\u6765\u6e90\u9500\u552e\u5355"), ("source_no", "\u6765\u6e90\u5355"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("customer_id", "\u5ba2\u6237"), ("return_date", "\u9000\u8d27\u65e5\u671f"), ("amount_with_tax", "\u542b\u7a0e\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: return_next_step(row.get("status")),
        "bulk_doc_type": "sales_return",
    },
    "/sales-return-requests": {
        "subtitle": "销售退货申请列表，跟踪客户退货申请、来源单据、项目号/机号和处理状态；实际入库仍在销售退货单详情中过账。",
        "add_url": "/sales-returns/new",
        "detail_base": "/sales-returns",
        "columns": [("return_no", "退货申请"), ("source_order_no", "来源销售订单"), ("source_no", "来源单据"), ("project_code", "项目号"), ("serial_no", "机号"), ("customer_id", "客户"), ("return_date", "申请日期"), ("amount_with_tax", "含税金额"), ("status", "状态")],
        "next_step": lambda row: return_next_step(row.get("status")),
        "bulk_doc_type": "sales_return",
    },
    "/sales-exchange-requests": {
        "subtitle": "销售换货申请列表，先记录退入侧申请和原因；换出侧必须另走销售发货单，不在本页自动出库或核销。",
        "add_url": "/sales-returns/new",
        "detail_base": "/sales-returns",
        "columns": [("return_no", "换货申请"), ("source_order_no", "来源销售订单"), ("source_no", "来源单据"), ("project_code", "项目号"), ("serial_no", "机号"), ("customer_id", "客户"), ("return_date", "申请日期"), ("amount_with_tax", "退入含税金额"), ("status", "状态")],
        "next_step": lambda row: return_next_step(row.get("status")),
        "bulk_doc_type": "sales_return",
    },
    "/returns": {
        "subtitle": "\u9500\u552e\u9000\u8d27\u5355\u5217\u8868\uff0c\u6309\u9000\u8d27\u5355\u3001\u6765\u6e90\u9500\u552e\u5355\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u5ba2\u6237\u3001\u91d1\u989d\u548c\u72b6\u6001\u8ffd\u8e2a\u9000\u8d27\u5165\u5e93\u4e0e\u5bf9\u8d26\u3002",
        "columns": [("return_no", "\u9000\u8d27\u5355"), ("source_order_no", "\u6765\u6e90\u9500\u552e\u5355"), ("source_no", "\u6765\u6e90\u5355"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("customer_id", "\u5ba2\u6237"), ("return_date", "\u9000\u8d27\u65e5\u671f"), ("amount_with_tax", "\u542b\u7a0e\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "detail_base": "/sales-returns",
        "next_step": lambda row: return_next_step(row.get("status")),
        "bulk_doc_type": "sales_return",
    },
    "/purchase-returns": {
        "subtitle": "\u91c7\u8d2d\u9000\u8d27\u5355\u5217\u8868\uff0c\u6309\u9000\u8d27\u5355\u3001\u4f9b\u5e94\u5546\u3001\u91d1\u989d\u548c\u72b6\u6001\u8ffd\u8e2a\u9000\u8d27\u51fa\u5e93\u4e0e\u5bf9\u8d26\u3002",
        "columns": [("return_no", "\u9000\u8d27\u5355"), ("supplier_id", "\u4f9b\u5e94\u5546"), ("return_date", "\u9000\u8d27\u65e5\u671f"), ("total_amount", "\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: return_next_step(row.get("status")),
        "bulk_doc_type": "purchase_return",
    },
    "/customer-receipts": {
        "subtitle": "\u5ba2\u6237\u56de\u6b3e\u5355\u5217\u8868\uff0c\u6309\u5ba2\u6237\u3001\u6765\u6e90\u5355\u3001\u91d1\u989d\u548c\u72b6\u6001\u8ffd\u8e2a\u5e94\u6536\u6838\u9500\u3002",
        "columns": [("receipt_no", "\u6536\u6b3e/\u6536\u8d27\u5355\u53f7"), ("customer_id", "\u5ba2\u6237"), ("source_no", "\u6765\u6e90\u5355"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("receipt_date", "\u56de\u6b3e\u65e5\u671f"), ("amount", "\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: settlement_next_step(row.get("status"), "\u5df2\u786e\u8ba4\uff0c\u8ddf\u8fdb\u5e94\u6536\u6838\u9500"),
    },
    "/payments": {
        "subtitle": "\u4f9b\u5e94\u5546\u4ed8\u6b3e\u5355\u5217\u8868\uff0c\u6309\u4f9b\u5e94\u5546\u3001\u6765\u6e90\u5355\u3001\u91d1\u989d\u548c\u72b6\u6001\u8ffd\u8e2a\u5e94\u4ed8\u6838\u9500\u3002",
        "columns": [("payment_no", "\u4ed8\u6b3e\u5355"), ("supplier_id", "\u4f9b\u5e94\u5546"), ("source_no", "\u6765\u6e90\u5355"), ("payment_date", "\u4ed8\u6b3e\u65e5\u671f"), ("amount", "\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: settlement_next_step(row.get("status"), "\u5df2\u786e\u8ba4\uff0c\u8ddf\u8fdb\u5e94\u4ed8\u6838\u9500"),
    },
    "/sales-invoices": {
        "subtitle": "\u9500\u552e\u53d1\u7968\u767b\u8bb0\u5217\u8868\uff0c\u6309\u5ba2\u6237\u3001\u6765\u6e90\u9500\u552e\u5355\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u542b\u7a0e\u91d1\u989d\u548c\u72b6\u6001\u8ddf\u8fdb\u5f00\u7968\u4e0e\u5e94\u6536\u6838\u9500\uff1b\u4ec5\u9650\u8d22\u52a1\u4e00\u671f\u767b\u8bb0\u95ed\u73af\uff0c\u4e0d\u505a\u7a0e\u63a7\u3001\u7533\u62a5\u6216\u81ea\u52a8\u51ed\u8bc1\u3002",
        "add_url": "/sales-invoices/new",
        "columns": [("invoice_no", "\u53d1\u7968\u53f7"), ("customer_id", "\u5ba2\u6237"), ("source_no", "\u6765\u6e90\u5355"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("invoice_date", "\u5f00\u7968\u65e5\u671f"), ("amount_with_tax", "\u542b\u7a0e\u91d1\u989d"), ("tax_amount", "\u7a0e\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: invoice_next_step(row.get("status")),
    },
    "/sales-tax-registrations": {
        "subtitle": "销售税票登记列表，等同销售发票登记；仅做发票和应收核对，不做税控、纳税申报或自动凭证。",
        "add_url": "/sales-invoices/new",
        "detail_base": "/sales-invoices",
        "columns": [("invoice_no", "税票号"), ("customer_id", "客户"), ("source_no", "来源单"), ("project_code", "项目号"), ("serial_no", "机号"), ("invoice_date", "开票日期"), ("amount_with_tax", "含税金额"), ("tax_amount", "税额"), ("status", "状态")],
        "next_step": lambda row: invoice_next_step(row.get("status")),
    },
    "/sales-reconciliations": {
        "subtitle": "销售对等核销列表，按应收来源、已收、余额和状态做只读核对；实际收款和核销在客户收款单完成。",
        "detail_base": "/receivables",
        "columns": [("source_no", "来源单据"), ("project_code", "项目号"), ("serial_no", "机号"), ("customer_id", "客户"), ("total_amount", "应收金额"), ("received_amount", "已收金额"), ("balance", "未收余额"), ("status", "状态")],
        "next_step": lambda row: settlement_next_step(row.get("status"), "已核销，核对应收余额"),
    },
    "/purchase-invoices": {
        "subtitle": "\u91c7\u8d2d\u53d1\u7968\u767b\u8bb0\u5217\u8868\uff0c\u6309\u4f9b\u5e94\u5546\u3001\u6765\u6e90\u91c7\u8d2d/\u59d4\u5916\u5355\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u542b\u7a0e\u91d1\u989d\u548c\u72b6\u6001\u8ddf\u8fdb\u5230\u7968\u4e0e\u5e94\u4ed8\u6838\u9500\uff1b\u4ec5\u9650\u8d22\u52a1\u4e00\u671f\u767b\u8bb0\u95ed\u73af\uff0c\u4e0d\u505a\u7a0e\u63a7\u3001\u7533\u62a5\u6216\u81ea\u52a8\u51ed\u8bc1\u3002",
        "columns": [("invoice_no", "\u53d1\u7968\u53f7"), ("supplier_id", "\u4f9b\u5e94\u5546"), ("source_no", "\u6765\u6e90\u5355"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("invoice_date", "\u5f00\u7968\u65e5\u671f"), ("amount_with_tax", "\u542b\u7a0e\u91d1\u989d"), ("tax_amount", "\u7a0e\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: invoice_next_step(row.get("status")),
    },
    "/finance/vouchers": {
        "subtitle": "\u51ed\u8bc1\u5217\u8868\uff0c\u6309\u51ed\u8bc1\u53f7\u3001\u671f\u95f4\u3001\u91d1\u989d\u548c\u72b6\u6001\u8ddf\u8fdb\u5ba1\u6838\u8fc7\u8d26\u3002",
        "columns": [("voucher_no", "\u51ed\u8bc1\u53f7"), ("voucher_date", "\u51ed\u8bc1\u65e5\u671f"), ("period_label", "\u671f\u95f4"), ("amount", "\u91d1\u989d"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: voucher_next_step(row.get("status")),
    },
    "/subcontract": {
        "subtitle": "\u59d4\u5916\u8ba2\u5355\u5217\u8868\uff0c\u6309\u59d4\u5916\u5355\u3001\u4f9b\u5e94\u5546\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u548c\u72b6\u6001\u8ffd\u8e2a\u53d1\u6599\u4e0e\u6536\u8d27\u3002",
        "columns": [("order_no", "\u59d4\u5916\u5355"), ("supplier_id", "\u52a0\u5de5\u5382\u5546"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("status", "\u72b6\u6001")],
        "add_url": "/subcontract/new",
        "next_step": lambda row: subcontract_next_step(row.get("status")),
    },
    "/subcontract-orders": {
        "subtitle": "\u59d4\u5916\u8ba2\u5355\u5217\u8868\uff0c\u6309\u59d4\u5916\u5355\u3001\u4f9b\u5e94\u5546\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u548c\u72b6\u6001\u8ffd\u8e2a\u53d1\u6599\u4e0e\u6536\u8d27\u3002",
        "columns": [("order_no", "\u59d4\u5916\u5355"), ("supplier_id", "\u52a0\u5de5\u5382\u5546"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("status", "\u72b6\u6001")],
        "detail_base": "/subcontract",
        "add_url": "/subcontract/new",
        "next_step": lambda row: subcontract_next_step(row.get("status")),
    },
    "/production-enhance/quality-inspections": {
        "subtitle": "\u8d28\u91cf\u68c0\u9a8c\u5217\u8868\uff0c\u6309\u68c0\u9a8c\u5355\u3001\u6765\u6e90\u5355\u3001\u7269\u6599\u548c\u72b6\u6001\u8ddf\u8fdb\u68c0\u9a8c\u5224\u5b9a\u3002",
        "add_url": "/production-enhance/quality-inspections/new",
        "columns": [("inspection_no", "\u68c0\u9a8c\u5355"), ("source_no", "\u6765\u6e90\u5355"), ("product_id", "\u7269\u6599"), ("inspection_date", "\u68c0\u9a8c\u65e5\u671f"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: quality_next_step(row.get("status")),
    },
    "/service-acceptance": {
        "subtitle": "\u5b89\u88c5\u9a8c\u6536\u5217\u8868\uff0c\u6309\u9a8c\u6536\u65e5\u671f\u3001\u9879\u76ee\u3001\u68c0\u67e5\u9879\u548c\u7ed3\u679c\u8ffd\u8e2a\u5ba2\u6237\u786e\u8ba4\u3002",
        "add_url": "/service-acceptance/new",
        "columns": [("acceptance_no", "\u9a8c\u6536\u5355\u53f7"), ("check_date", "\u9a8c\u6536\u65e5\u671f"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("checklist_type", "\u7c7b\u578b"), ("item_name", "\u68c0\u67e5\u9879"), ("result", "\u7ed3\u679c")],
        "next_step": lambda row: service_acceptance_next_step(row.get("result")),
    },
    "/service-return-visits": {
        "subtitle": "\u552e\u540e\u56de\u8bbf\u5217\u8868\uff0c\u6309\u56de\u8bbf\u65e5\u671f\u3001\u6ee1\u610f\u5ea6\u3001\u7ed3\u679c\u548c\u4e0b\u4e00\u6b65\u8ffd\u8e2a\u5ba2\u6237\u95ed\u73af\u3002",
        "columns": [("visit_no", "回访单号"), ("visit_date", "\u56de\u8bbf\u65e5\u671f"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("satisfaction", "\u6ee1\u610f\u5ea6"), ("satisfaction_score", "\u6ee1\u610f\u5ea6\u8bc4\u5206"), ("result", "\u7ed3\u679c")],
        "next_step": lambda row: row.get("next_action") or service_visit_next_step(row.get("result")),
    },
    "/inventory/detail": {
        "subtitle": "\u5e93\u5b58\u660e\u7ec6\u67e5\u8be2\uff0c\u6309\u7269\u6599\u3001\u4ed3\u5e93\u3001\u5e93\u4f4d\u3001\u6279\u6b21\u548c\u673a\u53f7\u67e5\u770b\u53ef\u7528\u5e93\u5b58\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("warehouse_id", "\u4ed3\u5e93"), ("location_id", "\u5e93\u4f4d"), ("lot_no", "\u6279\u53f7"), ("serial_no", "\u673a\u53f7"), ("quantity", "\u6570\u91cf")],
        "next_step": lambda row: inventory_balance_next_step(row.get("quantity")),
    },
    "/inventory/summary": {
        "subtitle": "\u5e93\u5b58\u6c47\u603b\u67e5\u8be2\uff0c\u6309\u7269\u6599\u67e5\u770b\u7ed3\u5b58\u6570\u91cf\u548c\u5f02\u5e38\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("warehouse_id", "\u4ed3\u5e93"), ("quantity", "\u6570\u91cf")],
        "detail_base": "/inventory/detail",
        "next_step": lambda row: inventory_balance_next_step(row.get("quantity")),
    },
    "/inventory/aging": {
        "subtitle": "\u5e93\u5b58\u8d26\u9f84\u67e5\u8be2\uff0c\u6309\u7269\u6599\u3001\u6570\u91cf\u548c\u6700\u8fd1\u5165\u5e93\u65f6\u95f4\u8bc6\u522b\u5446\u6ede\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("warehouse_id", "\u4ed3\u5e93"), ("quantity", "\u6570\u91cf"), ("created_at", "\u5efa\u6863\u65f6\u95f4")],
        "detail_base": "/inventory/detail",
        "next_step": lambda row: inventory_balance_next_step(row.get("quantity")),
    },
    "/transactions": {
        "subtitle": "\u5e93\u5b58\u6d41\u6c34\u67e5\u8be2\uff0c\u6309\u7269\u6599\u3001\u6765\u6e90\u5355\u3001\u6279\u6b21\u548c\u673a\u53f7\u8ffd\u8e2a\u5e93\u5b58\u53d8\u52a8\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("transaction_type", "\u7c7b\u578b"), ("quantity", "\u6570\u91cf"), ("reference_no", "\u6765\u6e90\u5355"), ("lot_no", "\u6279\u53f7"), ("serial_no", "\u673a\u53f7"), ("created_at", "\u65f6\u95f4")],
        "next_step": lambda row: stock_transaction_next_step(row.get("transaction_type")),
    },
    "/inventory_alerts": {
        "subtitle": "\u5e93\u5b58\u9884\u8b66\u5217\u8868\uff0c\u6309\u7269\u6599\u3001\u9884\u8b66\u7c7b\u578b\u548c\u72b6\u6001\u8ddf\u8fdb\u8865\u8d27\u3001\u8c03\u62e8\u6216\u76d8\u70b9\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("alert_type", "\u9884\u8b66\u7c7b\u578b"), ("current_quantity", "\u5f53\u524d\u6570\u91cf"), ("threshold_quantity", "\u9608\u503c"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: inventory_alert_next_step(row.get("status")),
    },
    "/inventory/reorder-suggestions": {
        "subtitle": "\u8865\u8d27\u5efa\u8bae\u5217\u8868\uff0c\u6839\u636e\u5e93\u5b58\u9884\u8b66\u8ddf\u8fdb\u91c7\u8d2d\u3001\u8c03\u62e8\u6216\u5b89\u5168\u5e93\u5b58\u8c03\u6574\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("alert_type", "\u5efa\u8bae\u7c7b\u578b"), ("current_quantity", "\u5f53\u524d\u6570\u91cf"), ("threshold_quantity", "\u9608\u503c"), ("status", "\u72b6\u6001")],
        "detail_base": "/inventory_alerts",
        "next_step": lambda row: inventory_alert_next_step(row.get("status")),
    },
    "/batch/tracking": {
        "subtitle": "\u6279\u6b21\u8ffd\u8e2a\u67e5\u8be2\uff0c\u6309\u6279\u53f7\u3001\u673a\u53f7\u3001\u7269\u6599\u548c\u6570\u91cf\u8ffd\u6eaf\u6d41\u5411\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("project_code", "\u9879\u76ee\u53f7"), ("lot_no", "\u6279\u53f7"), ("serial_no", "\u673a\u53f7"), ("quantity_available", "\u53ef\u7528\u6570\u91cf"), ("warehouse_id", "\u4ed3\u5e93"), ("location_id", "\u5e93\u4f4d")],
        "next_step": lambda row: batch_next_step(row.get("quantity_available")),
    },
    "/batch_trace": {
        "subtitle": "\u6279\u6b21\u8ffd\u8e2a\u67e5\u8be2\uff0c\u6309\u6279\u53f7\u3001\u673a\u53f7\u3001\u7269\u6599\u548c\u6570\u91cf\u8ffd\u6eaf\u6d41\u5411\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("project_code", "\u9879\u76ee\u53f7"), ("lot_no", "\u6279\u53f7"), ("serial_no", "\u673a\u53f7"), ("quantity_available", "\u53ef\u7528\u6570\u91cf"), ("warehouse_id", "\u4ed3\u5e93"), ("location_id", "\u5e93\u4f4d")],
        "detail_base": "/batch/tracking",
        "next_step": lambda row: batch_next_step(row.get("quantity_available")),
    },
    "/inventory/expiry": {
        "subtitle": "\u5e93\u5b58\u6548\u671f\u67e5\u8be2\uff0c\u6309\u6279\u53f7\u3001\u7269\u6599\u548c\u6548\u671f\u8ffd\u8e2a\u4e34\u671f\u98ce\u9669\u3002",
        "columns": [("product_id", "\u7269\u6599"), ("lot_no", "\u6279\u53f7"), ("expiry_date", "\u6548\u671f"), ("quantity", "\u6570\u91cf")],
        "detail_base": "/batch/tracking",
        "next_step": lambda row: batch_next_step(row.get("quantity")),
    },
    "/production-enhance/mrp-requirements": {
        "subtitle": "MRP\u7f3a\u6599\u9700\u6c42\u67e5\u8be2\uff0c\u6309\u6765\u6e90\u5de5\u5355\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u548c\u7f3a\u6599\u6570\u91cf\u8ddf\u8fdb\u3002\u672c\u9875\u4ec5\u67e5\u8be2\u548c\u8df3\u8f6c\uff1b\u8bf7\u8d2d\u6216\u91c7\u8d2d\u5efa\u8bae\u7edf\u4e00\u8fdb\u5165\u53d7\u63a7\u7684\u7f3a\u6599\u8f6c\u91c7\u8d2d\u9875\uff0c\u5904\u7406\u540e\u518d\u56de\u5230\u9f50\u5957\u590d\u6838\u3002",
        "columns": [("source_work_order", "\u6765\u6e90\u5de5\u5355"), ("product_id", "\u7269\u6599"), ("project_code", "\u9879\u76ee\u53f7"), ("serial_no", "\u673a\u53f7"), ("shortage_quantity", "\u7f3a\u6599\u6570\u91cf"), ("controlled_entry", "\u53d7\u63a7\u5165\u53e3"), ("recheck_entry", "\u590d\u6838"), ("status", "\u72b6\u6001")],
        "next_step": lambda row: mrp_requirement_next_step(row.get("status")),
        "enhance": enhance_mrp_requirement_row,
        "extra_columns": [("owner_role", "\u8d23\u4efb"), ("blocked_reason", "\u5835\u70b9/\u6761\u4ef6"), ("downstream_impact", "\u4e0b\u6e38\u5f71\u54cd")],
    },
    "/production-schedules": {
        "subtitle": "\u751f\u4ea7\u6392\u7a0b\u53ea\u8bfb\u5217\u8868\uff0c\u6309\u5de5\u5355/\u5de5\u5e8f\u3001\u8ba1\u5212\u65e5\u671f\u3001\u5de5\u4f5c\u4e2d\u5fc3\u3001\u8d23\u4efb\u4eba\u3001\u5835\u70b9\u548c\u4e0b\u4e00\u6b65\u8ddf\u8fdb\u751f\u4ea7\u6267\u884c\uff1b\u672c\u9875\u4e0d\u65b0\u589e\u3001\u4e0d\u8fc7\u8d26\u3002\u6d3e\u5de5\u548c\u6539\u671f\u4ece\u8be6\u60c5\u9875\u53d7\u63a7\u52a8\u4f5c\u8fdb\u5165\u3002",
        "columns": [("schedule_no", "\u6392\u7a0b\u5355"), ("source_work_order", "\u5de5\u5355/\u9879\u76ee/\u673a\u53f7"), ("planned_date_range", "\u8ba1\u5212\u65e5\u671f"), ("work_center_display", "\u5de5\u4f5c\u4e2d\u5fc3"), ("owner_role", "\u8d23\u4efb"), ("dispatch_status", "\u6d3e\u5de5\u72b6\u6001"), ("responsible_person", "\u8d23\u4efb\u4eba"), ("blocked_reason", "\u5835\u70b9/\u6761\u4ef6"), ("next_action", "\u4e0b\u4e00\u6b65"), ("dispatch_action", "\u6d3e\u5de5/\u6539\u671f"), ("report_action", "\u4e0b\u6e38\u62a5\u5de5")],
        "detail_base": "/production-schedules",
        "next_step": lambda row: schedule_next_step(row.get("status")),
        "enhance": enhance_production_schedule_row,
    },
    "/production-enhance/production-schedules": {
        "subtitle": "\u751f\u4ea7\u6392\u7a0b\u53ea\u8bfb\u5217\u8868\uff0c\u6309\u5de5\u5355/\u5de5\u5e8f\u3001\u8ba1\u5212\u65e5\u671f\u3001\u5de5\u4f5c\u4e2d\u5fc3\u3001\u8d23\u4efb\u4eba\u3001\u5835\u70b9\u548c\u4e0b\u4e00\u6b65\u8ddf\u8fdb\u751f\u4ea7\u6267\u884c\uff1b\u672c\u9875\u4e0d\u65b0\u589e\u3001\u4e0d\u8c03\u5ea6\u3002\u6d3e\u5de5\u548c\u6539\u671f\u4ece\u8be6\u60c5\u9875\u53d7\u63a7\u52a8\u4f5c\u8fdb\u5165\u3002",
        "columns": [("schedule_no", "\u6392\u7a0b\u5355"), ("source_work_order", "\u5de5\u5355/\u9879\u76ee/\u673a\u53f7"), ("planned_date_range", "\u8ba1\u5212\u65e5\u671f"), ("work_center_display", "\u5de5\u4f5c\u4e2d\u5fc3"), ("owner_role", "\u8d23\u4efb"), ("dispatch_status", "\u6d3e\u5de5\u72b6\u6001"), ("responsible_person", "\u8d23\u4efb\u4eba"), ("blocked_reason", "\u5835\u70b9/\u6761\u4ef6"), ("next_action", "\u4e0b\u4e00\u6b65"), ("dispatch_action", "\u6d3e\u5de5/\u6539\u671f"), ("report_action", "\u4e0b\u6e38\u62a5\u5de5")],
        "detail_base": "/production-schedules",
        "next_step": lambda row: schedule_next_step(row.get("status")),
        "enhance": enhance_production_schedule_row,
    },
    "/requisition": {
        "subtitle": "\u5de5\u5355\u9886\u6599\u5217\u8868\uff0c\u6309\u9886\u6599\u5355\u3001\u5de5\u5355\u548c\u72b6\u6001\u8ddf\u8fdb\u53d1\u6599\u4e0e\u6210\u672c\u3002",
        "columns": [("pick_no", "\u9886\u6599\u5355"), ("work_order_id", "\u5de5\u5355"), ("status", "\u72b6\u6001"), ("remark", "\u5907\u6ce8")],
        "next_step": lambda row: pick_list_next_step(row.get("status")),
    },
}


DOCUMENT_LIST_TITLES = {
    "/transfers": "\u5e93\u5b58\u8c03\u62e8\u5217\u8868",
    "/adjustments": "\u5e93\u5b58\u8c03\u6574\u5217\u8868",
    "/inventory_checks": "\u5e93\u5b58\u76d8\u70b9\u5217\u8868",
    "/subcontract_issue": "\u59d4\u5916\u53d1\u6599\u5355\u5217\u8868",
    "/subcontract_receive": "\u59d4\u5916\u6536\u8d27\u5355\u5217\u8868",
    "/service-orders": "\u670d\u52a1\u5355\u5217\u8868",
    "/service-rmas": "RMA\u5217\u8868",
    "/service-cards": "\u8bbe\u5907\u670d\u52a1\u6863\u6848",
    "/shipments": "\u9500\u552e\u53d1\u8d27\u5217\u8868",
    "/quotations": "\u62a5\u4ef7\u5355\u5217\u8868",
    "/sales-forecasts": "销售预测单列表",
    "/sales-inquiries": "询价单列表",
    "/supplier-quotes": "\u4f9b\u5e94\u5546\u62a5\u4ef7\u5217\u8868",
    "/sales-returns": "\u9500\u552e\u9000\u8d27\u5217\u8868",
    "/sales-return-requests": "销售退货申请列表",
    "/sales-exchange-requests": "销售换货申请列表",
    "/returns": "\u9500\u552e\u9000\u8d27\u5217\u8868",
    "/purchase-returns": "\u91c7\u8d2d\u9000\u8d27\u5217\u8868",
    "/customer-receipts": "\u5ba2\u6237\u56de\u6b3e\u5217\u8868",
    "/payments": "\u4f9b\u5e94\u5546\u4ed8\u6b3e\u5217\u8868",
    "/sales-invoices": "\u9500\u552e\u53d1\u7968\u767b\u8bb0\u5217\u8868",
    "/sales-tax-registrations": "销售税票登记列表",
    "/sales-reconciliations": "销售对等核销列表",
    "/purchase-invoices": "\u91c7\u8d2d\u53d1\u7968\u767b\u8bb0\u5217\u8868",
    "/finance/vouchers": "\u51ed\u8bc1\u5217\u8868",
    "/subcontract": "\u59d4\u5916\u8ba2\u5355\u5217\u8868",
    "/subcontract-orders": "\u59d4\u5916\u8ba2\u5355\u5217\u8868",
    "/production-enhance/quality-inspections": "\u8d28\u91cf\u68c0\u9a8c\u5217\u8868",
    "/service-acceptance": "\u5b89\u88c5\u9a8c\u6536\u5217\u8868",
    "/service-return-visits": "\u552e\u540e\u56de\u8bbf\u5217\u8868",
    "/inventory/detail": "\u5e93\u5b58\u660e\u7ec6",
    "/inventory/summary": "\u5e93\u5b58\u6c47\u603b",
    "/inventory/aging": "\u5e93\u5b58\u8d26\u9f84",
    "/transactions": "\u5e93\u5b58\u6d41\u6c34",
    "/inventory_alerts": "\u5e93\u5b58\u9884\u8b66",
    "/inventory/reorder-suggestions": "\u8865\u8d27\u5efa\u8bae",
    "/batch/tracking": "\u6279\u6b21\u8ffd\u8e2a",
    "/batch_trace": "\u6279\u6b21\u8ffd\u8e2a",
    "/inventory/expiry": "\u5e93\u5b58\u6548\u671f",
    "/production-enhance/mrp-requirements": "MRP\u7f3a\u6599\u9700\u6c42",
    "/production-schedules": "\u751f\u4ea7\u6392\u7a0b",
    "/production-enhance/production-schedules": "\u751f\u4ea7\u6392\u7a0b",
    "/requisition": "\u5de5\u5355\u9886\u6599\u5217\u8868",
}


def apply_document_list_context(path, rows, columns, detail_base, columns_builder, add_url=None, subtitle=None):
    """Apply read-only compatibility list columns/actions for document-like pages."""
    config = DOCUMENT_LIST_CONFIG.get(path)
    if not config:
        return rows, columns, detail_base, add_url, subtitle

    selected_columns = config.get("columns")
    if selected_columns:
        columns = columns_builder(*selected_columns)
    detail_base = config.get("detail_base", detail_base)
    add_url = config.get("add_url", add_url)
    subtitle = config.get("subtitle", subtitle)

    next_step = config.get("next_step")
    data_source = config.get("data_source")
    enhance = config.get("enhance")
    if next_step:
        enhanced_rows = []
        for row in rows:
            item = dict(row)
            if enhance:
                item = enhance(item)
            item["next_step"] = next_step(item)
            if data_source:
                item["data_source"] = data_source(item)
            if "status" in item:
                item["status"] = status_display(item.get("status"))
            enhanced_rows.append(item)
        rows = enhanced_rows
        columns = list(columns) + [{"key": "next_step", "label": "\u4e0b\u4e00\u6b65"}]
        for extra_key, extra_label in config.get("extra_columns", []):
            columns = list(columns) + [{"key": extra_key, "label": extra_label}]
        if data_source:
            columns = list(columns) + [{"key": "data_source", "label": "\u6570\u636e\u6765\u6e90"}]
    bulk_actions = None
    if config.get("bulk_doc_type"):
        bulk_actions = {
            "endpoint": "/inventory/bulk-action",
            "doc_type": config["bulk_doc_type"],
            "return_url": path,
            "actions": [
                {"value": "post", "label": "\u6279\u91cf\u786e\u8ba4\u8fc7\u8d26", "class": "btn-primary"},
                {"value": "close", "label": "\u6279\u91cf\u5173\u95ed", "class": "btn-outline-secondary"},
                {"value": "cancel", "label": "\u6279\u91cf\u53d6\u6d88", "class": "btn-outline-danger"},
                {"value": "print", "label": "\u6279\u91cf\u6253\u5370/\u5bfc\u51fa\u63d0\u793a", "class": "btn-outline-primary"},
            ],
        }
    return rows, columns, detail_base, add_url, subtitle, bulk_actions


def document_list_title(path, fallback):
    return DOCUMENT_LIST_TITLES.get(path, fallback)


def has_document_list_config(path):
    return path in DOCUMENT_LIST_CONFIG



