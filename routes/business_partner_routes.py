"""Business partner routes: customer and supplier list, detail, and filtering helpers."""
from flask import render_template

from .display_helpers import _clean_display_text, _filter_operator_rows


_CUSTOMER_NON_BUSINESS_MARKERS = (
    "test",
    "lifecycle",
    "accuracy",
    "multi line",
)


def _filter_customer_rows(rows):
    clean = []
    for row in rows or []:
        values = (
            row.get("name"),
            row.get("contact_person"),
            row.get("phone"),
            row.get("customer_level"),
        )
        text = " ".join(str(value or "").strip().lower() for value in values)
        if any(marker in text for marker in _CUSTOMER_NON_BUSINESS_MARKERS):
            continue
        clean.append(row)
    return clean


def _keyword_filter(alias, keyword):
    if not keyword:
        return "", ()
    clause = f"WHERE ({alias}.name ILIKE %s OR {alias}.contact_person ILIKE %s OR {alias}.phone ILIKE %s OR {alias}.address ILIKE %s)"
    return clause, tuple([f"%{keyword}%"] * 4)


def render_customer_dashboard(query_rows, count_rows, sum_value, money_metric, render_dashboard, columns, request_args, back_url="/customer"):
    keyword = (request_args.get("keyword") or request_args.get("q") or request_args.get("search") or "").strip()
    where_sql, params = _keyword_filter("c", keyword)
    metrics = [
        {"label": "客户数", "value": count_rows("customers"), "hint": "客户档案总数"},
        {"label": "有销售客户", "value": count_rows("customers", "id IN (SELECT DISTINCT customer_id FROM sales_orders WHERE customer_id IS NOT NULL)"), "hint": "已产生销售订单"},
        {"label": "应收余额", "value": money_metric(sum_value("customer_receivables", "balance")), "hint": "客户未回款"},
        {"label": "本月销售", "value": money_metric(sum_value("sales_orders", "total_amount", "order_date >= date_trunc('month', CURRENT_DATE)")), "hint": "本月销售订单金额"},
    ]
    shortcuts = []
    customers = query_rows(
        f"""
        SELECT c.id, c.name, c.contact_person, c.phone, c.address, c.customer_level,
               c.status, c.default_tax_rate, cc.name AS category_name,
               COALESCE(sales.order_count, 0) AS order_count,
               COALESCE(sales.sales_amount, 0) AS sales_amount,
               COALESCE(sales.open_order_count, 0) AS open_order_count,
               COALESCE(ar.receivable_balance, 0) AS receivable_balance,
               COALESCE(receipts.receipt_amount, 0) AS receipt_amount
        FROM customers c
        LEFT JOIN customer_categories cc ON cc.id=c.category_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS order_count,
                   COUNT(*) FILTER (WHERE COALESCE(status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')) AS open_order_count,
                   COALESCE(SUM(total_amount), 0) AS sales_amount
            FROM sales_orders so
            WHERE so.customer_id=c.id
        ) sales ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(balance), 0) AS receivable_balance
            FROM customer_receivables cr
            WHERE cr.customer_id=c.id
        ) ar ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(amount), 0) AS receipt_amount
            FROM customer_receipts r
            WHERE r.customer_id=c.id
        ) receipts ON TRUE
        {where_sql}
        ORDER BY COALESCE(ar.receivable_balance, 0) DESC, c.id DESC
        LIMIT 100
        """,
        params,
    )
    customers = _filter_operator_rows(customers, "name", "contact_person", "phone", "customer_level")
    customers = _filter_customer_rows(customers)
    for row in customers:
        for key in ("name", "contact_person", "phone", "customer_level"):
            row[key] = _clean_display_text(row.get(key))
        row["detail_url"] = f"/customer/{row.get('id')}"
        row["edit_url"] = f"/customer/{row.get('id')}/edit"
    return render_dashboard(
        "客户档案",
        "维护客户基础资料、分类、联系人、税率和信用信息；销售、发货、应收和回款回到对应业务模块。",
        metrics,
        shortcuts,
        [
            {
                "title": "客户档案",
                "rows": customers,
                "columns": columns(("name", "客户"), ("category_name", "分类"), ("status", "状态"), ("default_tax_rate", "税率%"), ("contact_person", "联系人"), ("phone", "电话"), ("customer_level", "等级"), ("order_count", "销售订单"), ("open_order_count", "未完单"), ("sales_amount", "销售额"), ("receivable_balance", "应收余额")),
                "detail_base": back_url,
                "detail_label": "客户详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/customer/new",
                "import_url": "/customer/import",
                "template_url": "/customer/download_template",
                "export_url": "/export/customers",
            },
        ],
    )


def render_supplier_dashboard(query_rows, count_rows, sum_value, money_metric, qty_metric, render_dashboard, columns, request_args, back_url="/supplier"):
    keyword = (request_args.get("keyword") or request_args.get("q") or request_args.get("search") or "").strip()
    where_sql, params = _keyword_filter("s", keyword)
    open_purchase_status_filter = "COALESCE(status, '') NOT IN ('已关闭','已作废','已取消','closed','completed','void','voided','cancelled','canceled')"
    metrics = [
        {"label": "供应商数", "value": count_rows("suppliers"), "hint": "供应商档案总数"},
        {"label": "有采购供应商", "value": count_rows("suppliers", "id IN (SELECT DISTINCT supplier_id FROM purchase_orders WHERE supplier_id IS NOT NULL)"), "hint": "已产生采购订单"},
        {"label": "应付余额", "value": money_metric(sum_value("supplier_payables", "balance")), "hint": "供应商未付款"},
        {"label": "采购未到", "value": qty_metric(sum_value("purchase_order_items poi JOIN purchase_orders po ON po.id=poi.order_id", "GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0)", open_purchase_status_filter)), "hint": "未关闭/未作废采购订单未收数量"},
    ]
    shortcuts = []
    suppliers = query_rows(
        f"""
        SELECT s.id, s.name, s.contact_person, s.phone, s.lead_time_days,
               s.status, s.default_tax_rate, s.is_outsourced_processor,
               sc.name AS category_name,
               COALESCE(po.order_count, 0) AS order_count,
               COALESCE(po.purchase_amount, 0) AS purchase_amount,
               COALESCE(po.pending_qty, 0) AS pending_qty,
               COALESCE(ap.payable_balance, 0) AS payable_balance,
               COALESCE(price_rows.price_count, 0) AS price_count
        FROM suppliers s
        LEFT JOIN supplier_categories sc ON sc.id=s.category_id
        LEFT JOIN LATERAL (
            SELECT COUNT(DISTINCT po.id) AS order_count,
                   COALESCE(SUM(COALESCE(poi.amount_with_tax, poi.amount, 0)), 0) AS purchase_amount,
                   COALESCE(SUM(GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0)) FILTER (WHERE COALESCE(po.status, '') NOT IN ('已关闭','已作废','已取消','closed','completed','void','voided','cancelled','canceled')), 0) AS pending_qty
            FROM purchase_orders po
            LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
            WHERE po.supplier_id=s.id
        ) po ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(balance), 0) AS payable_balance
            FROM supplier_payables sp
            WHERE sp.supplier_id=s.id
        ) ap ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS price_count
            FROM supplier_prices sp
            WHERE sp.supplier_id=s.id AND COALESCE(sp.is_active, TRUE)=TRUE
        ) price_rows ON TRUE
        {where_sql}
        ORDER BY COALESCE(po.pending_qty, 0) DESC, COALESCE(ap.payable_balance, 0) DESC, s.id DESC
        LIMIT 100
        """,
        params,
    )
    suppliers = _filter_operator_rows(suppliers, "name", "contact_person", "phone")
    for row in suppliers:
        row["processor_label"] = "是" if row.get("is_outsourced_processor") else "否"
        for key in ("name", "contact_person", "phone"):
            row[key] = _clean_display_text(row.get(key))
        row["detail_url"] = f"/supplier/{row.get('id')}"
        row["edit_url"] = f"/supplier/{row.get('id')}/edit"
    return render_dashboard(
        "供应商档案",
        "维护供应商和委外商基础资料、分类、税率、交期和联系人；采购、到货、价格和应付回到对应业务模块。",
        metrics,
        shortcuts,
        [
            {
                "title": "供应商档案",
                "rows": suppliers,
                "columns": columns(("name", "供应商"), ("category_name", "分类"), ("status", "状态"), ("processor_label", "委外商"), ("default_tax_rate", "税率%"), ("contact_person", "联系人"), ("phone", "电话"), ("lead_time_days", "交期天数"), ("order_count", "采购单"), ("pending_qty", "未到数量"), ("purchase_amount", "采购额"), ("payable_balance", "应付余额")),
                "detail_base": back_url,
                "detail_label": "供应商详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/supplier/new",
                "import_url": "/supplier/import",
                "template_url": "/supplier/download_template",
                "export_url": "/export/suppliers",
            },
        ],
    )


def render_customer_detail(customer_id, query_one, query_rows, money_metric, columns, back_url="/customer"):
    customer = query_one(
        """
        SELECT c.*, cc.name AS category_name,
               st.name AS settlement_term_name,
               pt.name AS payment_term_name
        FROM customers c
        LEFT JOIN customer_categories cc ON cc.id=c.category_id
        LEFT JOIN settlement_terms st ON st.id=c.settlement_term_id
        LEFT JOIN payment_terms pt ON pt.id=c.payment_term_id
        WHERE c.id=%s
        """,
        (customer_id,),
    )
    if not customer:
        return render_template("simple_detail.html", title="客户详情", row=None, back_url=back_url, labels={})
    sales_summary = query_one(
        """
        SELECT COUNT(*) AS order_count,
               COUNT(*) FILTER (WHERE COALESCE(status, '') NOT IN ('已发货','已关闭','已作废','closed','completed')) AS open_count,
               COALESCE(SUM(total_amount), 0) AS sales_amount,
               COALESCE(SUM(shipped_amount), 0) AS shipped_amount
        FROM sales_orders
        WHERE customer_id=%s
        """,
        (customer_id,),
    ) or {}
    receivable_summary = query_one(
        """
        SELECT COALESCE(SUM(total_amount), 0) AS total_amount,
               COALESCE(SUM(received_amount), 0) AS received_amount,
               COALESCE(SUM(balance), 0) AS balance
        FROM customer_receivables
        WHERE customer_id=%s
        """,
        (customer_id,),
    ) or {}
    context = {
        "kind": "customer",
        "title": "客户详情",
        "back_url": back_url,
        "delete_url": f"/customer/{customer_id}/delete",
        "partner": customer,
        "metrics": [
            {"label": "销售订单", "value": sales_summary.get("order_count", 0), "hint": f"未完 {sales_summary.get('open_count', 0)}"},
            {"label": "销售金额", "value": money_metric(sales_summary.get("sales_amount", 0)), "hint": "未税金额"},
            {"label": "应收余额", "value": money_metric(receivable_summary.get("balance", 0)), "hint": f"已收 {money_metric(receivable_summary.get('received_amount', 0))}"},
            {"label": "信用额度", "value": money_metric(customer.get("credit_limit")), "hint": f"已用 {money_metric(customer.get('credit_used'))}"},
        ],
        "info_rows": [
            ("联系人", customer.get("contact_person")),
            ("电话", customer.get("phone")),
            ("等级", customer.get("customer_level")),
            ("分类", customer.get("category_name")),
            ("状态", customer.get("status")),
            ("税号", customer.get("tax_no")),
            ("开票抬头", customer.get("invoice_title")),
            ("默认税率%", customer.get("default_tax_rate")),
            ("结算期限", customer.get("settlement_term_name")),
            ("收款条件", customer.get("payment_term_name")),
            ("地址", customer.get("address")),
            ("备注", customer.get("remark")),
        ],
        "sections": [
            {
                "title": "销售订单",
                "rows": query_rows(
                    """
                    SELECT id, order_no, order_date, project_code, serial_no, status, total_amount, shipped_amount, delivery_date
                    FROM sales_orders
                    WHERE customer_id=%s
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    (customer_id,),
                ),
                "columns": columns(("order_no", "销售订单"), ("order_date", "日期"), ("project_code", "项目号"), ("serial_no", "机号"), ("total_amount", "金额"), ("shipped_amount", "已发货"), ("delivery_date", "交期"), ("status", "状态")),
                "detail_base": "/sales",
            },
            {
                "title": "应收账款",
                "rows": query_rows(
                    """
                    SELECT id, source_no, receivable_date, due_date, total_amount, received_amount, balance, status
                    FROM customer_receivables
                    WHERE customer_id=%s
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    (customer_id,),
                ),
                "columns": columns(("source_no", "来源"), ("receivable_date", "日期"), ("due_date", "到期"), ("total_amount", "应收"), ("received_amount", "已收"), ("balance", "余额"), ("status", "状态")),
                "detail_base": "/receivables",
            },
            {
                "title": "客户回款",
                "rows": query_rows(
                    """
                    SELECT id, receipt_no, receipt_date, amount, payment_method, bank_account, remark
                    FROM customer_receipts
                    WHERE customer_id=%s
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    (customer_id,),
                ),
                "columns": columns(("receipt_no", "回款单"), ("receipt_date", "日期"), ("amount", "金额"), ("payment_method", "方式"), ("bank_account", "账户"), ("remark", "备注")),
            },
            {
                "title": "销售发货",
                "rows": query_rows(
                    """
                    SELECT ss.id, ss.shipment_no, ss.shipment_date, ss.project_code, ss.serial_no, ss.status, so.order_no
                    FROM sales_shipments ss
                    LEFT JOIN sales_orders so ON so.id=ss.order_id
                    WHERE so.customer_id=%s
                    ORDER BY ss.id DESC
                    LIMIT 50
                    """,
                    (customer_id,),
                ),
                "columns": columns(("shipment_no", "发货单"), ("shipment_date", "日期"), ("order_no", "销售订单"), ("project_code", "项目号"), ("serial_no", "机号"), ("status", "状态")),
            },
        ],
    }
    return render_template("partner_trace_detail.html", **context)


def render_supplier_detail(supplier_id, query_one, query_rows, money_metric, qty_metric, columns, back_url="/supplier"):
    supplier = query_one(
        """
        SELECT s.*, sc.name AS category_name,
               st.name AS settlement_term_name,
               pt.name AS payment_term_name
        FROM suppliers s
        LEFT JOIN supplier_categories sc ON sc.id=s.category_id
        LEFT JOIN settlement_terms st ON st.id=s.settlement_term_id
        LEFT JOIN payment_terms pt ON pt.id=s.payment_term_id
        WHERE s.id=%s
        """,
        (supplier_id,),
    )
    if not supplier:
        return render_template("simple_detail.html", title="供应商详情", row=None, back_url=back_url, labels={})
    purchase_summary = query_one(
        """
        SELECT COUNT(DISTINCT po.id) AS order_count,
               COALESCE(SUM(COALESCE(poi.amount_with_tax, poi.amount, 0)), 0) AS purchase_amount,
               COALESCE(SUM(GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0)) FILTER (WHERE COALESCE(po.status, '') NOT IN ('已关闭','已作废','已取消','closed','completed','void','voided','cancelled','canceled')), 0) AS pending_qty
        FROM purchase_orders po
        LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
        WHERE po.supplier_id=%s
        """,
        (supplier_id,),
    ) or {}
    payable_summary = query_one(
        """
        SELECT COALESCE(SUM(amount), 0) AS amount,
               COALESCE(SUM(paid_amount), 0) AS paid_amount,
               COALESCE(SUM(balance), 0) AS balance
        FROM supplier_payables
        WHERE supplier_id=%s
        """,
        (supplier_id,),
    ) or {}
    context = {
        "kind": "supplier",
        "title": "供应商详情",
        "back_url": back_url,
        "delete_url": f"/supplier/{supplier_id}/delete",
        "partner": supplier,
        "metrics": [
            {"label": "采购单", "value": purchase_summary.get("order_count", 0), "hint": "历史采购"},
            {"label": "采购金额", "value": money_metric(purchase_summary.get("purchase_amount", 0)), "hint": "明细金额汇总"},
            {"label": "采购未到", "value": qty_metric(purchase_summary.get("pending_qty", 0)), "hint": "未收数量"},
            {"label": "应付余额", "value": money_metric(payable_summary.get("balance", 0)), "hint": f"已付 {money_metric(payable_summary.get('paid_amount', 0))}"},
        ],
        "info_rows": [
            ("联系人", supplier.get("contact_person")),
            ("电话", supplier.get("phone")),
            ("交期天数", supplier.get("lead_time_days")),
            ("分类", supplier.get("category_name")),
            ("状态", supplier.get("status")),
            ("委外加工商", "是" if supplier.get("is_outsourced_processor") else "否"),
            ("税号", supplier.get("tax_no")),
            ("开票抬头", supplier.get("invoice_title")),
            ("默认税率%", supplier.get("default_tax_rate")),
            ("结算期限", supplier.get("settlement_term_name")),
            ("付款条件", supplier.get("payment_term_name")),
            ("地址", supplier.get("address")),
            ("备注", supplier.get("remark")),
        ],
        "sections": [
            {
                "title": "采购订单",
                "rows": query_rows(
                    """
                    SELECT id, order_no, order_date, expected_date, project_code, serial_no, status, amount_with_tax, received_amount
                    FROM purchase_orders
                    WHERE supplier_id=%s
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    (supplier_id,),
                ),
                "columns": columns(("order_no", "采购单"), ("order_date", "日期"), ("expected_date", "预计到货"), ("project_code", "项目号"), ("serial_no", "机号"), ("amount_with_tax", "含税金额"), ("received_amount", "已收"), ("status", "状态")),
                "detail_base": "/purchase_order",
            },
            {
                "title": "供应商价格",
                "rows": query_rows(
                    """
                    SELECT sp.id, p.code AS product_code, p.name AS product_name,
                           p.specification, p.unit, sp.unit_price,
                           sp.min_quantity, sp.lead_time_days, sp.supplier_item_code, sp.is_primary, sp.is_active
                    FROM supplier_prices sp
                    LEFT JOIN products p ON p.id=sp.product_id
                    WHERE sp.supplier_id=%s
                    ORDER BY COALESCE(sp.is_primary, FALSE) DESC, sp.id DESC
                    LIMIT 50
                    """,
                    (supplier_id,),
                ),
                "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("unit", "单位"), ("unit_price", "单价"), ("min_quantity", "起订量"), ("lead_time_days", "交期"), ("supplier_item_code", "供应商料号"), ("is_primary", "首选"), ("is_active", "有效")),
            },
            {
                "title": "应付账款",
                "rows": query_rows(
                    """
                    SELECT id, doc_no, doc_date, amount, paid_amount, balance, status, next_follow_up_date
                    FROM supplier_payables
                    WHERE supplier_id=%s
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    (supplier_id,),
                ),
                "columns": columns(("doc_no", "来源"), ("doc_date", "日期"), ("amount", "应付"), ("paid_amount", "已付"), ("balance", "余额"), ("next_follow_up_date", "跟进"), ("status", "状态")),
                "detail_base": "/payables",
            },
            {
                "title": "付款记录",
                "rows": query_rows(
                    """
                    SELECT id, payment_no, payment_date, amount, payment_method, bank_account, remark
                    FROM supplier_payments
                    WHERE supplier_id=%s
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    (supplier_id,),
                ),
                "columns": columns(("payment_no", "付款单"), ("payment_date", "日期"), ("amount", "金额"), ("payment_method", "方式"), ("bank_account", "账户"), ("remark", "备注")),
            },
        ],
    }
    return render_template("partner_trace_detail.html", **context)
