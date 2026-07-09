"""Pending document routes: pending queue and exception list for workbench."""
def pending_doc_row(doc_type, doc_no, doc_date, partner, status, amount, detail_url, action):
    return {
        "doc_type": doc_type,
        "doc_no": doc_no,
        "doc_date": doc_date,
        "partner": partner,
        "status": status,
        "amount": amount,
        "action": action,
        "detail_url": detail_url,
    }


def build_pending_document_rows(query_rows):
    sales_to_submit = query_rows(
        """
        SELECT so.id, so.order_no, so.order_date, c.name AS partner, so.status, so.amount_with_tax
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE COALESCE(so.status,'') IN ('待发货','草稿','待提交','pending','draft')
        ORDER BY so.id DESC
        LIMIT 20
        """
    )
    purchase_to_submit = query_rows(
        """
        SELECT po.id, po.order_no, po.order_date, s.name AS partner, po.status, po.amount_with_tax
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        WHERE COALESCE(po.status,'') IN ('待收货','草稿','待提交','pending','draft')
        ORDER BY po.id DESC
        LIMIT 20
        """
    )
    sales_to_ship = query_rows(
        """
        SELECT so.id, so.order_no, so.order_date, c.name AS partner, so.status, so.amount_with_tax
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE COALESCE(so.status,'')='已审核'
        ORDER BY so.id DESC
        LIMIT 20
        """
    )
    purchase_to_receive = query_rows(
        """
        SELECT po.id, po.order_no, po.order_date, s.name AS partner, po.status, po.amount_with_tax
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        WHERE COALESCE(po.status,'')='已审核'
        ORDER BY po.id DESC
        LIMIT 20
        """
    )
    receivables = query_rows(
        """
        SELECT cr.id, COALESCE(cr.source_no, so.order_no) AS doc_no, cr.receivable_date AS doc_date,
               c.name AS partner, cr.status, cr.balance AS amount
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        LEFT JOIN sales_orders so ON so.id=cr.source_id AND cr.source_type='sales_order'
        WHERE COALESCE(cr.balance,0)>0
        ORDER BY cr.id DESC
        LIMIT 20
        """
    )
    payables = query_rows(
        """
        SELECT sp.id, COALESCE(sp.doc_no, po.order_no) AS doc_no, sp.doc_date,
               s.name AS partner, sp.status, sp.balance AS amount
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        LEFT JOIN purchase_orders po ON po.id=sp.doc_id AND sp.doc_type='purchase_order'
        WHERE COALESCE(sp.balance,0)>0
        ORDER BY sp.id DESC
        LIMIT 20
        """
    )
    shortages = query_rows(
        """
        SELECT mr.id, COALESCE(mr.requirement_date, CURRENT_DATE) AS doc_date,
               p.code || ' / ' || p.name AS partner, mr.status, mr.shortage_quantity
        FROM mrp_requirements mr
        LEFT JOIN products p ON p.id=mr.product_id
        WHERE COALESCE(mr.shortage_quantity,0)>0
        ORDER BY mr.id DESC
        LIMIT 20
        """
    )
    pending_rows = []
    pending_rows.extend(
        pending_doc_row("销售待提交/审核", r.get("order_no"), r.get("order_date"), r.get("partner"), r.get("status"), r.get("amount_with_tax"), f"/sales/{r.get('id')}", "提交/审核")
        for r in sales_to_submit
    )
    pending_rows.extend(
        pending_doc_row("采购待提交/审核", r.get("order_no"), r.get("order_date"), r.get("partner"), r.get("status"), r.get("amount_with_tax"), f"/purchase_order/{r.get('id')}", "提交/审核")
        for r in purchase_to_submit
    )
    pending_rows.extend(
        pending_doc_row("销售待发货", r.get("order_no"), r.get("order_date"), r.get("partner"), r.get("status"), r.get("amount_with_tax"), f"/sales/{r.get('id')}", "生成发货")
        for r in sales_to_ship
    )
    pending_rows.extend(
        pending_doc_row("采购待收货", r.get("order_no"), r.get("order_date"), r.get("partner"), r.get("status"), r.get("amount_with_tax"), f"/purchase_order/{r.get('id')}", "生成收货")
        for r in purchase_to_receive
    )
    pending_rows.extend(
        pending_doc_row("应收待回款", r.get("doc_no"), r.get("doc_date"), r.get("partner"), r.get("status"), r.get("amount"), f"/receivables/{r.get('id')}", "登记回款")
        for r in receivables
    )
    pending_rows.extend(
        pending_doc_row("应付待付款", r.get("doc_no"), r.get("doc_date"), r.get("partner"), r.get("status"), r.get("amount"), f"/payables/{r.get('id')}", "登记付款")
        for r in payables
    )
    pending_rows.extend(
        pending_doc_row("缺料待采购", f"MRP-{r.get('id')}", r.get("doc_date"), r.get("partner"), r.get("status"), r.get("shortage_quantity"), "/procurement/suggestions", "生成采购申请")
        for r in shortages
    )
    return {
        "rows": pending_rows[:120],
        "sales_to_ship": sales_to_ship,
        "purchase_to_receive": purchase_to_receive,
        "shortages": shortages,
    }


def render_pending_documents(query_rows, render_dashboard, columns):
    payload = build_pending_document_rows(query_rows)
    pending_rows = payload["rows"]
    return render_dashboard(
        title="待处理单据",
        subtitle="把今天需要处理的销售、采购、库存、生产和财务事项集中到一个页面。",
        metrics=[
            {"label": "待处理总数", "value": len(pending_rows), "hint": "下方列表合计"},
            {"label": "销售待发货", "value": len(payload["sales_to_ship"]), "hint": "已审核销售订单"},
            {"label": "采购待收货", "value": len(payload["purchase_to_receive"]), "hint": "已审核采购单"},
            {"label": "缺料待采购", "value": len(payload["shortages"]), "hint": "MRP 缺料行"},
        ],
        shortcuts=[
            {"label": "采购建议", "url": "/procurement/suggestions", "icon": "bi-clipboard-plus"},
            {"label": "项目/机号台账", "url": "/projects", "icon": "bi-kanban"},
            {"label": "库存明细", "url": "/inventory/detail", "icon": "bi-box-seam"},
        ],
        sections=[
            {
                "title": "待处理列表",
                "rows": pending_rows,
                "columns": columns(
                    ("doc_type", "类型"),
                    ("doc_no", "单号"),
                    ("doc_date", "日期"),
                    ("partner", "客户/供应商/物料"),
                    ("status", "状态"),
                    ("amount", "金额/数量"),
                    ("action", "建议动作"),
                ),
                "detail_base": "/",
            }
        ],
    )
