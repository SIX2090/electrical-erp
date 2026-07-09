"""Shipment module routes: shipment list, shipment form, and delivery tracking."""
from datetime import datetime
from decimal import Decimal

from flask import render_template

from .document_print_routes import build_template_grid_for_document


SHIPMENT_STATUS_LABELS = {
    "pending": "待确认",
    "draft": "草稿",
    "待审核": "待审核",
    "confirmed": "已确认",
    "已确认": "已确认",
    "已发货": "已发货",
    "closed": "已关闭",
    "已关闭": "已关闭",
    "cancelled": "已取消",
    "已取消": "已取消",
    "void": "已作废",
    "已作废": "已作废",
}


def shipment_status_label(status):
    return SHIPMENT_STATUS_LABELS.get((status or "").strip(), (status or "").strip() or "未定")


def shipment_next_action(shipment):
    status = (shipment.get("status") or "").strip()
    if status in {"已作废", "void", "cancelled", "已取消"}:
        return "保留追溯记录，停止后续应收和服务交接。"
    if status in {"已关闭", "closed"}:
        return "交付闭环已关闭，继续核对回款和服务记录。"
    if not shipment.get("order_id"):
        return "缺少来源销售订单，需先核对来源。"
    if not shipment.get("stock_txn_count"):
        return "核对库存出库流水，确认发货库存影响。"
    if not shipment.get("service_card_id"):
        return "补齐设备服务档案，安装和售后才能接续。"
    if shipment.get("receivable_balance") and shipment.get("receivable_balance") > 0:
        return "跟进应收余额，确认开票和回款计划。"
    return "发货、服务档案和应收已可追溯，可按业务情况关闭。"


def shipment_action_state(status):
    value = (status or "").strip()
    final_statuses = {"已关闭", "closed", "已作废", "void", "cancelled", "已取消"}
    posted_statuses = {"已发货", "已确认", "confirmed"}
    draft_statuses = {"", "草稿", "待提交", "待审核", "draft", "pending", "unposted"}
    return {
        "can_confirm": value not in posted_statuses | final_statuses,
        "can_unaudit": value in posted_statuses,
        "can_close": value not in final_statuses,
        "can_void": value not in final_statuses and value not in {"已关闭", "closed"},
        "can_delete": value in draft_statuses,
    }


def render_shipment_detail(
    shipment_id,
    query_one,
    query_rows,
    as_decimal,
    qty_metric,
    money_metric,
    document_attachments,
    document_activity_logs,
    back_url="/shipments",
):
    shipment = query_one(
        """
        SELECT ss.*, so.order_no, so.order_date, so.delivery_date, so.status AS order_status,
               so.amount_with_tax AS order_amount_with_tax, so.shipped_amount AS order_shipped_amount,
               c.name AS customer_name, c.contact_person, c.phone AS customer_phone, c.address AS customer_address,
               w.name AS warehouse_name, u.username AS operator_name,
               sc.id AS service_card_id, sc.status AS service_card_status, sc.machine_model,
               sc.install_address, sc.installation_date,
               COALESCE(st.stock_txn_count, 0) AS stock_txn_count,
               COALESCE(ar.receivable_amount, 0) AS receivable_amount,
               COALESCE(ar.received_amount, 0) AS received_amount,
               COALESCE(ar.receivable_balance, 0) AS receivable_balance
        FROM sales_shipments ss
        LEFT JOIN sales_orders so ON so.id=ss.order_id
        LEFT JOIN customers c ON c.id=COALESCE(ss.customer_id, so.customer_id)
        LEFT JOIN warehouses w ON w.id=ss.warehouse_id
        LEFT JOIN users u ON u.id=ss.operator_id
        LEFT JOIN machine_service_cards sc
          ON sc.sales_order_id=ss.order_id
         AND (sc.serial_no=ss.serial_no OR COALESCE(ss.serial_no, '')='')
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS stock_txn_count
            FROM stock_transactions st
            WHERE st.reference_no=ss.shipment_no OR st.source_doc_no=ss.shipment_no
        ) st ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(total_amount), 0) AS receivable_amount,
                   COALESCE(SUM(received_amount), 0) AS received_amount,
                   COALESCE(SUM(balance), 0) AS receivable_balance
            FROM customer_receivables cr
            WHERE cr.source_no IN (ss.shipment_no, so.order_no)
               OR (cr.source_type IN ('sales_shipment','shipment') AND cr.source_id=ss.id)
               OR (cr.source_type IN ('sales_order','order') AND cr.source_id=ss.order_id)
        ) ar ON TRUE
        WHERE ss.id=%s
        """,
        (shipment_id,),
    )
    if not shipment:
        return render_template("simple_detail.html", title="销售发货详情", row=None, back_url=back_url, labels={})

    project_code = shipment.get("project_code")
    serial_no = shipment.get("serial_no")
    receivable_params = (
        shipment.get("shipment_no"),
        shipment.get("order_no"),
        shipment.get("id"),
        shipment.get("order_id"),
    )
    shipment = dict(shipment)
    shipment["status_label"] = shipment_status_label(shipment.get("status"))

    items = query_rows(
        """
        SELECT ssi.*, p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(p.unit, '') AS product_unit,
               soi.quantity AS ordered_qty, soi.shipped_qty AS order_shipped_qty,
               soi.unit_price AS order_unit_price, l.code AS location_code, l.name AS location_name,
               w.name AS warehouse_name,
               COALESCE(ssi.amount, COALESCE(ssi.quantity, 0) * COALESCE(ssi.unit_price, ssi.unit_cost, soi.unit_price, 0)) AS line_amount
        FROM sales_shipment_items ssi
        LEFT JOIN sales_shipments ss ON ss.id=ssi.shipment_id
        LEFT JOIN products p ON p.id=ssi.product_id
        LEFT JOIN sales_order_items soi ON soi.id=ssi.order_item_id
        LEFT JOIN locations l ON l.id=ssi.location_id
        LEFT JOIN warehouses w ON w.id=COALESCE(
            ssi.warehouse_id,
            (SELECT ss2.warehouse_id FROM sales_shipments ss2 WHERE ss2.id=ssi.shipment_id)
        )
        WHERE ssi.shipment_id=%s
        ORDER BY ssi.id
        """,
        (shipment_id,),
    )
    total_qty = sum((as_decimal(row.get("quantity")) for row in items), Decimal("0"))
    total_amount = sum((as_decimal(row.get("line_amount")) for row in items), Decimal("0"))

    stock_transactions = query_rows(
        """
        SELECT st.id, st.transaction_date, st.transaction_type, p.code AS product_code,
               p.name AS product_name, st.quantity, st.unit_cost, st.reference_no,
               st.lot_no, st.serial_no, st.location
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        WHERE st.reference_no=%s OR st.source_doc_no=%s
        ORDER BY st.id DESC
        LIMIT 50
        """,
        (shipment.get("shipment_no"), shipment.get("shipment_no")),
    )
    receivables = query_rows(
        """
        SELECT id, source_no, receivable_date, total_amount, received_amount, balance, status
        FROM customer_receivables
        WHERE source_no IN (%s, %s)
           OR (source_type IN ('sales_shipment','shipment') AND source_id=%s)
           OR (source_type IN ('sales_order','order') AND source_id=%s)
        ORDER BY id DESC
        LIMIT 20
        """,
        receivable_params,
    )
    same_project_shipments = query_rows(
        """
        SELECT id, shipment_no, shipment_date, status
        FROM sales_shipments
        WHERE id<>%s AND ((%s IS NOT NULL AND project_code=%s) OR (%s IS NOT NULL AND serial_no=%s))
        ORDER BY id DESC
        LIMIT 20
        """,
        (shipment_id, project_code, project_code, serial_no, serial_no),
    )
    shipment["next_action"] = shipment_next_action(shipment)
    context = {
        "back_url": back_url,
        "shipment": shipment,
        "items": items,
        "metrics": [
            {"label": "发货数量", "value": qty_metric(total_qty), "hint": f"{len(items)} 行物料"},
            {"label": "发货未税金额", "value": money_metric(total_amount), "hint": "按发货明细汇总"},
            {"label": "应收余额", "value": money_metric(shipment.get("receivable_balance")), "hint": "来源销售订单/发货/项目机号"},
            {"label": "库存流水", "value": shipment.get("stock_txn_count") or 0, "hint": "销售出库影响记录"},
        ],
        "stock_transactions": stock_transactions,
        "receivables": receivables,
        "same_project_shipments": same_project_shipments,
        "attachments": document_attachments("sales_shipment", shipment_id),
        "activity_logs": document_activity_logs("sales_shipment", shipment),
        "print_url": f"/shipments/{shipment_id}/print",
        "action_prefix": "/shipments",
        "action_state": shipment_action_state(shipment.get("status")),
    }
    return render_template("shipment_detail.html", **context)


def render_shipment_print(shipment_id, query_one, query_rows, as_decimal):
    shipment = query_one(
        """
        SELECT ss.*, so.order_no, c.name AS customer_name, c.contact_person, c.phone AS customer_phone,
               w.name AS warehouse_name
        FROM sales_shipments ss
        LEFT JOIN sales_orders so ON so.id=ss.order_id
        LEFT JOIN customers c ON c.id=COALESCE(ss.customer_id, so.customer_id)
        LEFT JOIN warehouses w ON w.id=ss.warehouse_id
        WHERE ss.id=%s
        """,
        (shipment_id,),
    )
    if not shipment:
        return render_template("simple_detail.html", title="销售发货打印", row=None, back_url="/shipments", labels={})
    rows = query_rows(
        """
        SELECT p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(p.unit, '') AS unit, ssi.quantity,
               COALESCE(ssi.unit_price, ssi.unit_cost, 0) AS unit_price,
               COALESCE(ssi.amount, COALESCE(ssi.quantity, 0) * COALESCE(ssi.unit_price, ssi.unit_cost, 0)) AS amount,
               ssi.lot_no, l.code AS location_code, l.name AS location_name
        FROM sales_shipment_items ssi
        LEFT JOIN products p ON p.id=ssi.product_id
        LEFT JOIN locations l ON l.id=ssi.location_id
        WHERE ssi.shipment_id=%s
        ORDER BY ssi.id
        """,
        (shipment_id,),
    )
    for row in rows:
        row["location_display"] = row.get("location_code") or row.get("location_name") or ""
    doc = {
        "title": "销售发货单",
        "subtitle": "机床 ERP 单据打印",
        "number": shipment.get("shipment_no"),
        "number_label": "发货单号",
        "date": shipment.get("shipment_date"),
        "date_label": "发货日期",
        "status_label": shipment_status_label(shipment.get("status")),
        "info": [
            ("客户", shipment.get("customer_name")),
            ("联系人", shipment.get("contact_person")),
            ("电话", shipment.get("customer_phone")),
            ("来源销售订单", shipment.get("order_no") or shipment.get("source_no")),
            ("仓库", shipment.get("warehouse_name")),
            ("项目号", shipment.get("project_code")),
            ("机号", shipment.get("serial_no")),
        ],
        "columns": [
            ("product_code", "物料编码", ""),
            ("product_name", "物料名称", ""),
            ("specification", "规格", ""),
            ("unit", "单位", "center"),
            ("quantity", "数量", "right"),
            ("unit_price", "单价", "right money"),
            ("amount", "未税金额", "right money"),
            ("location_display", "库位", ""),
            ("lot_no", "批号", ""),
        ],
        "rows": rows,
        "total_quantity": sum((as_decimal(row.get("quantity")) for row in rows), Decimal("0")),
        "total_amount": sum((as_decimal(row.get("amount")) for row in rows), Decimal("0")),
        "remark": shipment.get("remark"),
        "signatures": ["制单", "销售", "仓库", "客户", "财务"],
        "print_time": datetime.now(),
        "back_url": f"/shipments/{shipment_id}",
    }
    doc["partner_name"] = shipment.get("customer_name")
    doc["contact_person"] = shipment.get("contact_person")
    doc["partner_phone"] = shipment.get("customer_phone")
    doc["project_code"] = shipment.get("project_code")
    doc["serial_no"] = shipment.get("serial_no")
    doc["warehouse_name"] = shipment.get("warehouse_name")
    template_grid = build_template_grid_for_document("shipment", doc, query_one)
    return render_template("document_print.html", doc=doc, template_grid=template_grid)
