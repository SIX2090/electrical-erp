"""Order form routes: sales order and purchase order creation and editing forms."""
from flask import render_template, request


PRODUCT_OPTION_SQL = """
SELECT p.id, p.code, p.name, p.specification, p.unit, p.standard_price,
       COALESCE(pc.name, p.category, '') AS product_family,
       bom.bom_no AS default_bom_no,
       bom.version AS default_bom_version,
       COALESCE(p.batch_control, FALSE) AS batch_control,
       COALESCE(p.serial_control, FALSE) AS serial_control,
       COALESCE(p.inspection_required, FALSE) AS inspection_required,
       CONCAT_WS(' / ', NULLIF(p.code,''), NULLIF(p.name,''), NULLIF(p.specification,'')) AS display_name
FROM products p
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
WHERE COALESCE(p.status, '') NOT IN ('停用','disabled')
ORDER BY p.id DESC
LIMIT 3000
"""


def _option_rows(query_rows, sql, params=None):
    return query_rows(sql, params) if params is not None else query_rows(sql)


def _render_order_form(
    *,
    order_id,
    query_one,
    query_rows,
    product_options,
    load_document_custom_payload,
    document_type,
    order_table,
    item_table,
    partner_table,
    partner_label,
    partner_field,
    due_date_label,
    due_date_field,
    warehouse_label,
    title_new,
    title_edit,
    subtitle,
    back_url,
    action_new_url,
    action_edit_url,
):
    order = query_one(f"SELECT * FROM {order_table} WHERE id=%s", (order_id,)) if order_id else None
    items = (
        query_rows(f"SELECT * FROM {item_table} WHERE order_id=%s ORDER BY id", (order_id,))
        if order_id
        else []
    )
    warehouses = _option_rows(
        query_rows,
        """
        SELECT id, name, default_location_id
        FROM warehouses
        WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
        ORDER BY name
        LIMIT 200
        """,
    )
    if partner_field == "customer_id":
        partner_options = _option_rows(
            query_rows,
            """
            SELECT c.id, c.name, c.default_tax_rate, c.settlement_term_id, c.payment_term_id,
                   COALESCE(c.credit_limit, 0) AS credit_limit,
                   COALESCE(c.credit_used, 0) AS credit_used,
                   COALESCE(ar.open_balance, 0) AS receivable_balance,
                   COALESCE(open_orders.open_amount, 0) AS open_order_amount,
                   COALESCE(c.credit_used, 0) + COALESCE(ar.open_balance, 0) + COALESCE(open_orders.open_amount, 0) AS credit_exposure
            FROM customers c
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(balance), 0) AS open_balance
                FROM customer_receivables cr
                WHERE cr.customer_id=c.id AND COALESCE(cr.balance, 0) > 0
            ) ar ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(COALESCE(amount_with_tax,total_amount,0)), 0) AS open_amount
                FROM sales_orders so
                WHERE so.customer_id=c.id
                  AND COALESCE(so.status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')
            ) open_orders ON TRUE
            WHERE COALESCE(c.status, '启用') NOT IN ('停用','disabled','inactive')
            ORDER BY c.name
            LIMIT 300
            """,
        )
    else:
        partner_options = _option_rows(
            query_rows,
            f"""
            SELECT id, name, default_tax_rate, settlement_term_id, payment_term_id
            FROM {partner_table}
            WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
            ORDER BY name
            LIMIT 300
            """,
        )
    approval_records = []
    source_requests = []
    source_request = None
    if document_type == "sales_order" and order:
        approval_records = _option_rows(
            query_rows,
            """
            SELECT flow_type, reference_no, step_id, approver_id, action, comment, approved_at
            FROM approval_records
            WHERE flow_type='sales_order' AND reference_no=%s
            ORDER BY approved_at DESC NULLS LAST, id DESC
            LIMIT 10
            """,
            (order.get("order_no"),),
        )
    project_master_options = []
    cabinet_options = []
    if document_type == "sales_order":
        project_master_options = _option_rows(
            query_rows,
            """
            SELECT id, project_code, project_name, customer_id, product_family,
                   machine_model, status,
                   CONCAT_WS(' / ', NULLIF(project_code,''), NULLIF(project_name,'')) AS display_name
            FROM project_masters
            WHERE NULLIF(TRIM(COALESCE(project_code, '')), '') IS NOT NULL
              AND COALESCE(status, '') NOT IN ('停用','disabled','inactive')
            ORDER BY project_code
            LIMIT 500
            """,
        )
        cabinet_options = _option_rows(
            query_rows,
            """
            SELECT id, cabinet_no, project_id, project_code, customer_id, product_id,
                   product_family, machine_model, status,
                   CONCAT_WS(' / ', NULLIF(cabinet_no,''), NULLIF(project_code,''), NULLIF(machine_model,'')) AS display_name
            FROM cabinet_masters
            WHERE NULLIF(TRIM(COALESCE(cabinet_no, '')), '') IS NOT NULL
              AND COALESCE(status, '') NOT IN ('停用','disabled','inactive')
            ORDER BY cabinet_no
            LIMIT 1000
            """,
        )
    if document_type == "purchase_order" and not order:
        source_requests = _option_rows(
            query_rows,
            """
            SELECT pr.id, pr.req_no, pr.req_date, pr.department, pr.purpose, pr.project_code, pr.cabinet_no,
                   COUNT(pri.id) AS item_count,
                   COALESCE(SUM(GREATEST(COALESCE(pri.quantity,0)-COALESCE(po_items.ordered_qty,0),0)), 0) AS remaining_qty
            FROM purchase_requisitions pr
            JOIN purchase_requisition_items pri ON pri.req_id=pr.id
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(poi.quantity), 0) AS ordered_qty
                FROM purchase_order_items poi
                WHERE poi.source_line_no=CONCAT('PRITEM-', pri.id::text)
            ) po_items ON TRUE
            WHERE COALESCE(pr.status, '') IN ('已审核','approved','completed','已生成采购订单')
              AND COALESCE(pr.approval_status, 'approved')='approved'
            GROUP BY pr.id
            HAVING COALESCE(SUM(GREATEST(COALESCE(pri.quantity,0)-COALESCE(po_items.ordered_qty,0),0)), 0) > 0
            ORDER BY pr.id DESC
            LIMIT 200
            """,
        )
        source_request_id = (request.args.get("source_request_id") or request.args.get("purchase_request_id") or "").strip()
        if source_request_id.isdigit():
            source_request = query_one(
                """
                SELECT pr.id, pr.req_no, pr.req_date, pr.department, pr.purpose, pr.project_code, pr.cabinet_no,
                       MIN(pri.need_date) AS expected_date
                FROM purchase_requisitions pr
                LEFT JOIN purchase_requisition_items pri ON pri.req_id=pr.id
                WHERE pr.id=%s
                  AND COALESCE(pr.approval_status, 'approved')='approved'
                GROUP BY pr.id
                """,
                (int(source_request_id),),
            )
            if source_request:
                order = {
                    "supplier_id": None,
                    "order_date": None,
                    "expected_date": source_request.get("expected_date"),
                    "warehouse_id": None,
                    "project_code": source_request.get("project_code") or "",
                    "cabinet_no": source_request.get("cabinet_no") or "",
                    "remark": f"来源采购申请 {source_request.get('req_no')}",
                }
                items = query_rows(
                    """
                    SELECT pri.product_id,
                           GREATEST(COALESCE(pri.quantity,0)-COALESCE(po_items.ordered_qty,0),0) AS quantity,
                           COALESCE(pri.unit_price, 0) AS unit_price,
                           COALESCE(p.default_tax_rate, 13) AS tax_rate,
                           CONCAT('PRITEM-', pri.id::text) AS source_line_no,
                           pri.need_date AS expected_date,
                           pri.remark
                    FROM purchase_requisition_items pri
                    LEFT JOIN products p ON p.id=pri.product_id
                    LEFT JOIN LATERAL (
                        SELECT COALESCE(SUM(poi.quantity), 0) AS ordered_qty
                        FROM purchase_order_items poi
                        WHERE poi.source_line_no=CONCAT('PRITEM-', pri.id::text)
                    ) po_items ON TRUE
                    WHERE pri.req_id=%s
                      AND GREATEST(COALESCE(pri.quantity,0)-COALESCE(po_items.ordered_qty,0),0) > 0
                    ORDER BY pri.id
                    """,
                    (int(source_request_id),),
                )

    customers = partner_options if partner_field == "customer_id" else []
    suppliers = partner_options if partner_field == "supplier_id" else []

    return render_template(
        "order_form.html",
        title=title_edit if order_id else title_new,
        subtitle=subtitle,
        back_url=back_url,
        action_url=action_edit_url.format(order_id=order_id) if order_id else action_new_url,
        document_type=document_type,
        order_type=document_type,
        order_id=order_id,
        order=order,
        items=items,
        custom_fields_payload=load_document_custom_payload(document_type, order_id),
        products=product_options,
        product_options=product_options,
        warehouses=warehouses,
        warehouse_options=warehouses,
        customers=customers,
        suppliers=suppliers,
        partner_label=partner_label,
        partner_field=partner_field,
        partner_options=partner_options,
        approval_records=approval_records,
        source_requests=source_requests,
        source_request=source_request,
        project_master_options=project_master_options,
        cabinet_options=cabinet_options,
        due_date_label=due_date_label,
        due_date_field=due_date_field,
        warehouse_label=warehouse_label,
    )


def render_sales_order_form(order_id, query_one, query_rows, product_options, load_document_custom_payload):
    return _render_order_form(
        order_id=order_id,
        query_one=query_one,
        query_rows=query_rows,
        product_options=product_options,
        load_document_custom_payload=load_document_custom_payload,
        document_type="sales_order",
        order_table="sales_orders",
        item_table="sales_order_items",
        partner_table="customers",
        partner_label="客户",
        partner_field="customer_id",
        due_date_label="交货日期",
        due_date_field="delivery_date",
        warehouse_label="发货仓库",
        title_new="新增销售订单",
        title_edit="编辑销售订单",
        subtitle="维护销售订单基本信息和多行物料明细；保存后可提交、审核、发货和回款。",
        back_url="/sales-orders",
        action_new_url="/sales/new",
        action_edit_url="/sales/{order_id}/edit",
    )


def render_purchase_order_form(order_id, query_one, query_rows, product_options, load_document_custom_payload):
    return _render_order_form(
        order_id=order_id,
        query_one=query_one,
        query_rows=query_rows,
        product_options=product_options,
        load_document_custom_payload=load_document_custom_payload,
        document_type="purchase_order",
        order_table="purchase_orders",
        item_table="purchase_order_items",
        partner_table="suppliers",
        partner_label="供应商",
        partner_field="supplier_id",
        due_date_label="预计到货",
        due_date_field="expected_date",
        warehouse_label="收货仓库",
        title_new="新增采购订单",
        title_edit="编辑采购订单",
        subtitle="维护采购订单基本信息和多行物料明细；保存后可提交、审核、收货和付款。",
        back_url="/purchase-orders",
        action_new_url="/purchase_order/new",
        action_edit_url="/purchase_order/{order_id}/edit",
    )
