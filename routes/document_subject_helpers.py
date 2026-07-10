"""Document subject helpers: map document kinds to subject types and table names."""
def document_subject(kind):
    if kind == "quotation":
        return {
            "subject_type": "quotation",
            "table": "quotation_headers",
            "doc_no_field": "quote_no",
            "label": "报价单",
            "url_prefix": "/quotations",
        }
    if kind == "sales":
        return {
            "subject_type": "sales_order",
            "table": "sales_orders",
            "doc_no_field": "order_no",
            "label": "销售订单",
            "url_prefix": "/sales",
        }
    if kind == "purchase":
        return {
            "subject_type": "purchase_order",
            "table": "purchase_orders",
            "doc_no_field": "order_no",
            "label": "采购单",
            "url_prefix": "/purchase_order",
        }
    if kind == "purchase_receipt":
        return {
            "subject_type": "purchase_receipt",
            "table": "purchase_receipts",
            "doc_no_field": "receipt_no",
            "label": "采购入库",
            "url_prefix": "/purchase_receipts",
        }
    if kind == "sales_shipment":
        return {
            "subject_type": "sales_shipment",
            "table": "sales_shipments",
            "doc_no_field": "shipment_no",
            "label": "销售发货",
            "url_prefix": "/shipments",
        }
    if kind == "work_order":
        return {
            "subject_type": "work_order",
            "table": "work_orders",
            "doc_no_field": "wo_no",
            "label": "工单",
            "url_prefix": "/work-orders",
        }
    if kind == "quality_inspection":
        return {
            "subject_type": "quality_inspection",
            "table": "quality_inspection_records",
            "doc_no_field": "inspection_no",
            "label": "质量检验单",
            "url_prefix": "/production-enhance/quality-inspections",
        }
    if kind == "inventory_adjustment":
        return {
            "subject_type": "inventory_adjustment",
            "table": "inventory_adjustments",
            "doc_no_field": "adj_no",
            "label": "库存调整",
            "url_prefix": "/adjustments",
        }
    if kind == "inventory_transfer":
        return {
            "subject_type": "inventory_transfer",
            "table": "transfer_orders",
            "doc_no_field": "transfer_no",
            "label": "库存调拨",
            "url_prefix": "/transfers",
        }
    if kind == "inventory_check":
        return {
            "subject_type": "inventory_check",
            "table": "inventory_check_orders",
            "doc_no_field": "check_no",
            "label": "库存盘点",
            "url_prefix": "/inventory_checks",
        }
    if kind == "sales_return":
        return {
            "subject_type": "sales_return",
            "table": "sales_returns",
            "doc_no_field": "return_no",
            "label": "销售退货",
            "url_prefix": "/sales-returns",
        }
    if kind == "purchase_return":
        return {
            "subject_type": "purchase_return",
            "table": "purchase_returns",
            "doc_no_field": "return_no",
            "label": "采购退货",
            "url_prefix": "/purchase-returns",
        }
    if kind == "inventory_assembly":
        return {
            "subject_type": "inventory_assembly",
            "table": "inventory_assembly_orders",
            "doc_no_field": "assembly_no",
            "label": "组装单",
            "url_prefix": "/assembly-orders",
        }
    if kind == "inventory_disassembly":
        return {
            "subject_type": "inventory_disassembly",
            "table": "inventory_assembly_orders",
            "doc_no_field": "assembly_no",
            "label": "拆卸单",
            "url_prefix": "/disassembly-orders",
        }
    if kind == "service_card":
        return {
            "subject_type": "service_card",
            "table": "machine_service_cards",
            "doc_no_field": "cabinet_no",
            "label": "设备服务档案",
            "url_prefix": "/service-cards",
        }
    if kind == "service_order":
        return {
            "subject_type": "service_order",
            "table": "machine_service_orders",
            "doc_no_field": "order_no",
            "label": "服务单",
            "url_prefix": "/service-orders",
        }
    if kind == "service_rma":
        return {
            "subject_type": "service_rma",
            "table": "machine_service_rmas",
            "doc_no_field": "rma_no",
            "label": "RMA",
            "url_prefix": "/service-rmas",
        }
    if kind == "receivable":
        return {
            "subject_type": "receivable",
            "table": "customer_receivables",
            "doc_no_field": "source_no",
            "label": "应收",
            "url_prefix": "/receivables",
        }
    if kind == "customer_receipt":
        return {
            "subject_type": "customer_receipt",
            "table": "customer_receipts",
            "doc_no_field": "receipt_no",
            "label": "收款单",
            "url_prefix": "/customer-receipts",
        }
    if kind == "sales_invoice":
        return {
            "subject_type": "sales_invoice",
            "table": "sales_invoices",
            "doc_no_field": "invoice_no",
            "label": "销售发票登记",
            "url_prefix": "/sales-invoices",
        }
    if kind == "purchase_invoice":
        return {
            "subject_type": "purchase_invoice",
            "table": "purchase_invoices",
            "doc_no_field": "invoice_no",
            "label": "采购发票登记",
            "url_prefix": "/purchase-invoices",
        }
    if kind == "supplier_quote":
        return {
            "subject_type": "supplier_quote",
            "table": "supplier_quotes",
            "doc_no_field": "quote_no",
            "label": "供应商报价",
            "url_prefix": "/supplier-quotes",
        }
    if kind == "payable":
        return {
            "subject_type": "payable",
            "table": "supplier_payables",
            "doc_no_field": "doc_no",
            "label": "应付",
            "url_prefix": "/payables",
        }
    return None
