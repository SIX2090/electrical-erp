"""Order detail routes: sales order and purchase order detail page rendering."""
from flask import render_template


def render_sales_order_detail(
    order_id,
    query_one,
    query_rows,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/sales-orders",
):
    order = query_one(
        """
        SELECT so.*, c.name AS customer_name, c.contact_person, c.phone AS customer_phone,
               COALESCE(c.credit_limit, 0) AS credit_limit,
               COALESCE(c.credit_used, 0) AS credit_used,
               COALESCE(ar.open_balance, 0) AS receivable_balance,
               COALESCE(open_orders.open_amount, 0) AS open_order_amount,
               COALESCE(c.credit_used, 0) + COALESCE(ar.open_balance, 0) + COALESCE(open_orders.open_amount, 0) AS credit_exposure,
               w.name AS warehouse_name
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(balance), 0) AS open_balance
            FROM customer_receivables cr
            WHERE cr.customer_id=so.customer_id AND COALESCE(cr.balance, 0) > 0
        ) ar ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(COALESCE(amount_with_tax,total_amount,0)), 0) AS open_amount
            FROM sales_orders so_open
            WHERE so_open.customer_id=so.customer_id
              AND so_open.id<>so.id
              AND COALESCE(so_open.status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')
        ) open_orders ON TRUE
        LEFT JOIN warehouses w ON w.id=so.warehouse_id
        WHERE so.id=%s
        """,
        (order_id,),
    )
    if not order:
        return render_template("simple_detail.html", title="销售订单详情", row=None, back_url=back_url, labels={})

    project_code = order.get("project_code")
    cabinet_no = order.get("cabinet_no")
    cost_object_id = order.get("cost_object_id")
    context = {
        "doc_type": "销售订单",
        "doc_kind": "sales",
        "back_url": back_url,
        "order": order,
        "partner_label": "客户",
        "partner_name": order.get("customer_name"),
        "warehouses": query_rows("SELECT id, name FROM warehouses ORDER BY name LIMIT 200"),
        "items": query_rows(
            """
            SELECT soi.*, p.code AS product_code, p.name AS product_name,
                   p.specification, COALESCE(soi.lot_no, '') AS item_lot_no,
                   COALESCE(p.unit, '') AS product_unit,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required
            FROM sales_order_items soi
            LEFT JOIN products p ON p.id=soi.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            WHERE soi.order_id=%s
            ORDER BY soi.id
            """,
            (order_id,),
        ),
        "approval_records": query_rows(
            """
            SELECT id, flow_type, reference_no, step_id, approver_id, action, comment, approved_at
            FROM approval_records
            WHERE flow_type='sales_order' AND reference_no=%s
            ORDER BY approved_at DESC NULLS LAST, id DESC
            LIMIT 10
            """,
            (order.get("order_no"),),
        ),
        "related_sections": [
            {
                "title": "发货记录",
                "rows": query_rows(
                    """
                    SELECT id, shipment_no AS doc_no, shipment_date AS doc_date, status, remark
                    FROM sales_shipments
                    WHERE order_id=%s OR (%s IS NOT NULL AND project_code=%s) OR (%s IS NOT NULL AND cabinet_no=%s)
                    ORDER BY id DESC LIMIT 20
                    """,
                    (order_id, project_code, project_code, cabinet_no, cabinet_no),
                ),
                "columns": columns(("doc_no", "单号"), ("doc_date", "日期"), ("status", "状态"), ("remark", "备注")),
            },
            {
                "title": "应收回款",
                "rows": query_rows(
                    """
                    SELECT id, source_no AS doc_no, receivable_date AS doc_date, total_amount, received_amount, balance, status
                    FROM customer_receivables
                    WHERE source_id=%s OR source_no=%s OR (%s IS NOT NULL AND cost_object_id=%s)
                       OR (%s IS NOT NULL AND project_code=%s) OR (%s IS NOT NULL AND cabinet_no=%s)
                    ORDER BY id DESC LIMIT 20
                    """,
                    (
                        order_id,
                        order.get("order_no"),
                        cost_object_id,
                        cost_object_id,
                        project_code,
                        project_code,
                        cabinet_no,
                        cabinet_no,
                    ),
                ),
                "columns": columns(
                    ("doc_no", "来源"),
                    ("doc_date", "日期"),
                    ("total_amount", "应收"),
                    ("received_amount", "已收"),
                    ("balance", "余额"),
                    ("status", "状态"),
                ),
            },
        ],
        "attachments": document_attachments("sales", order_id),
        "activity_logs": document_activity_logs("sales", order),
    }
    return render_template("document_trace_detail.html", **context)


def render_purchase_order_detail(
    order_id,
    query_one,
    query_rows,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/purchase-orders",
):
    order = query_one(
        """
        SELECT po.*, s.name AS supplier_name, s.contact_person, s.phone AS supplier_phone,
               w.name AS warehouse_name
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        LEFT JOIN warehouses w ON w.id=po.warehouse_id
        WHERE po.id=%s
        """,
        (order_id,),
    )
    if not order:
        return render_template("simple_detail.html", title="采购订单详情", row=None, back_url=back_url, labels={})

    project_code = order.get("project_code")
    cabinet_no = order.get("cabinet_no")
    context = {
        "doc_type": "采购订单",
        "doc_kind": "purchase",
        "back_url": back_url,
        "order": order,
        "partner_label": "供应商",
        "partner_name": order.get("supplier_name"),
        "items": query_rows(
            """
            SELECT poi.*, p.code AS product_code, p.name AS product_name,
                   p.specification, COALESCE(poi.lot_no, '') AS item_lot_no,
                   COALESCE(p.unit, '') AS product_unit,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required,
                   GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) AS pending_receive_qty
            FROM purchase_order_items poi
            LEFT JOIN products p ON p.id=poi.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            WHERE poi.order_id=%s
            ORDER BY poi.id
            """,
            (order_id,),
        ),
        "related_sections": [
            {
                "title": "采购申请来源",
                "rows": query_rows(
                    """
                    SELECT pr.id, pr.req_no, pr.req_date, pr.status,
                           pri.project_code, pri.cabinet_no,
                           COUNT(pri.id) AS item_count,
                           COALESCE(SUM(pri.quantity), 0) AS quantity
                    FROM purchase_requisition_items pri
                    LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
                    WHERE pri.po_order_id=%s
                    GROUP BY pr.id, pri.project_code, pri.cabinet_no
                    ORDER BY pr.id DESC
                    LIMIT 20
                    """,
                    (order_id,),
                ),
                "columns": columns(
                    ("req_no", "申请单"),
                    ("req_date", "日期"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("item_count", "行数"),
                    ("quantity", "数量"),
                    ("status", "状态"),
                ),
            },
            {
                "title": "采购入库记录",
                "rows": query_rows(
                    """
                    SELECT id, receipt_no AS doc_no, receipt_date AS doc_date, status, remark
                    FROM purchase_receipts
                    WHERE order_id=%s OR (%s IS NOT NULL AND project_code=%s) OR (%s IS NOT NULL AND cabinet_no=%s)
                    ORDER BY id DESC LIMIT 20
                    """,
                    (order_id, project_code, project_code, cabinet_no, cabinet_no),
                ),
                "columns": columns(("doc_no", "单号"), ("doc_date", "日期"), ("status", "状态"), ("remark", "备注")),
            },
            {
                "title": "应付付款",
                "rows": query_rows(
                    """
                    SELECT id, doc_no, doc_date, amount, paid_amount, balance, status
                    FROM supplier_payables
                    WHERE doc_id=%s OR doc_no=%s OR (%s IS NOT NULL AND supplier_id=%s)
                    ORDER BY id DESC LIMIT 20
                    """,
                    (order_id, order.get("order_no"), order.get("supplier_id"), order.get("supplier_id")),
                ),
                "columns": columns(
                    ("doc_no", "来源"),
                    ("doc_date", "日期"),
                    ("amount", "应付"),
                    ("paid_amount", "已付"),
                    ("balance", "余额"),
                    ("status", "状态"),
                ),
            },
        ],
        "attachments": document_attachments("purchase", order_id),
        "activity_logs": document_activity_logs("purchase", order),
    }
    return render_template("document_trace_detail.html", **context)
