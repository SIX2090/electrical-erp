"""Read-only sales operation analysis report services."""
from datetime import date, timedelta
from decimal import Decimal


VOID_STATUSES = ("cancelled", "canceled", "voided", "void", "已作废", "已取消", "作废", "取消")


REPORT_META = {
    "price-execution-analysis": {
        "title": "销售价格执行分析",
        "subtitle": "按订单行对比报价价、客户价格和订单成交价，仅做销售经营分析。",
    },
    "delivery-delay-analysis": {
        "title": "销售交付逾期分析",
        "subtitle": "按销售订单计划交期、实际发货和未交数量识别交付风险。",
    },
    "operation-snapshot": {
        "title": "销售经营快照",
        "subtitle": "汇总订单、发货、开票、收款和未交事项，作为经营看板口径。",
    },
    "daily": {
        "title": "销售日报",
        "subtitle": "按日期汇总新增订单、发货、开票和收款金额。",
    },
    "project-cabinet-gross-margin": {
        "title": "项目/柜号销售毛利分析",
        "subtitle": "经营毛利/发货成本口径；成本不完整时标注成本未核准。",
    },
}


def as_decimal_safe(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _money(value):
    return f"{as_decimal_safe(value):,.2f}"


def _rate(numerator, denominator):
    denominator = as_decimal_safe(denominator)
    if denominator == 0:
        return "0.0%"
    return f"{(as_decimal_safe(numerator) / denominator * 100):.1f}%"


def _request_value(args, key, default=""):
    if not args:
        return default
    value = args.get(key, default) if hasattr(args, "get") else default
    return str(value or "").strip()


def build_filters(args=None):
    today = date.today()
    default_start = today - timedelta(days=30)
    return {
        "date_start": _request_value(args, "date_start", default_start.isoformat()),
        "date_end": _request_value(args, "date_end", today.isoformat()),
        "status": _request_value(args, "status"),
        "keyword": _request_value(args, "keyword") or _request_value(args, "q"),
        "project": _request_value(args, "project"),
        "customer_name": _request_value(args, "customer_name"),
        "product_name": _request_value(args, "product_name"),
    }


def _add_common_filters(where, params, filters, date_expr, text_exprs=(), status_expr=None, project_exprs=()):
    if filters.get("date_start"):
        where.append(f"{date_expr} >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where.append(f"{date_expr} <= %s")
        params.append(filters["date_end"])
    if filters.get("status") and status_expr:
        where.append(f"{status_expr} ILIKE %s")
        params.append(f"%{filters['status']}%")
    if filters.get("keyword") and text_exprs:
        where.append("(" + " OR ".join(f"{expr} ILIKE %s" for expr in text_exprs) + ")")
        params.extend([f"%{filters['keyword']}%"] * len(text_exprs))
    if filters.get("project") and project_exprs:
        where.append("(" + " OR ".join(f"{expr} ILIKE %s" for expr in project_exprs) + ")")
        params.extend([f"%{filters['project']}%"] * len(project_exprs))
    if filters.get("customer_name"):
        where.append("c.name ILIKE %s")
        params.append(f"%{filters['customer_name']}%")
    if filters.get("product_name"):
        where.append("p.name ILIKE %s")
        params.append(f"%{filters['product_name']}%")


def _where_clause(where):
    return "WHERE " + " AND ".join(where) if where else ""


def _summary(rows, mapping):
    return [
        {"label": label, "value": formatter(sum(as_decimal_safe(row.get(key)) for row in rows)), "hint": hint}
        for label, key, formatter, hint in mapping
    ]


def get_price_execution_analysis(query_db, args=None):
    filters = build_filters(args)
    where = ["COALESCE(so.status, '') NOT IN %s"]
    params = [VOID_STATUSES]
    _add_common_filters(
        where,
        params,
        filters,
        "so.order_date",
        ("so.order_no", "c.name", "p.code", "p.name", "so.project_code", "so.cabinet_no"),
        "so.status",
        ("so.project_code", "so.cabinet_no", "soi.line_project_code", "soi.line_cabinet_no"),
    )
    sql = f"""
        WITH latest_customer_price AS (
            SELECT DISTINCT ON (customer_id, product_id)
                   customer_id, product_id, unit_price AS customer_price
            FROM customer_quotes
            WHERE COALESCE(is_active, TRUE) = TRUE
              AND (valid_from IS NULL OR valid_from <= CURRENT_DATE)
              AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
            ORDER BY customer_id, product_id, valid_from DESC NULLS LAST, id DESC
        ),
        latest_quotation_price AS (
            SELECT DISTINCT ON (qh.customer_id, qi.product_id)
                   qh.customer_id, qi.product_id, qi.unit_price AS quotation_price, qh.quote_no
            FROM quotation_headers qh
            JOIN quotation_items qi ON qi.quotation_id = qh.id
            WHERE COALESCE(qh.status, '') NOT IN %s
            ORDER BY qh.customer_id, qi.product_id, qh.quote_date DESC NULLS LAST, qh.id DESC
        ),
        shipped_price AS (
            SELECT ss.order_id, ssi.order_item_id,
                   SUM(COALESCE(ssi.amount_with_tax, ssi.amount, 0)) / NULLIF(SUM(COALESCE(ssi.quantity, 0)), 0) AS shipped_unit_price,
                   SUM(COALESCE(ssi.amount_with_tax, ssi.amount, 0)) AS shipped_amount
            FROM sales_shipments ss
            JOIN sales_shipment_items ssi ON ssi.shipment_id = ss.id
            WHERE COALESCE(ss.status, '') NOT IN %s
            GROUP BY ss.order_id, ssi.order_item_id
        )
        SELECT
            so.id AS order_id,
            so.order_no,
            so.order_date,
            c.name AS customer_name,
            COALESCE(so.project_code, soi.line_project_code) AS project_code,
            COALESCE(so.cabinet_no, soi.line_cabinet_no) AS cabinet_no,
            p.code AS product_code,
            COALESCE(p.name, soi.material_name) AS product_name,
            p.specification,
            COALESCE(p.unit, soi.material_unit) AS unit,
            COALESCE(soi.quantity, 0) AS order_qty,
            COALESCE(quote.quotation_price, customer_price.customer_price, 0) AS reference_unit_price,
            quote.quote_no,
            COALESCE(soi.unit_price, 0) AS order_unit_price,
            COALESCE(shipped.shipped_unit_price, 0) AS shipped_unit_price,
            COALESCE(soi.amount_with_tax, soi.amount, 0) AS order_amount,
            COALESCE(shipped.shipped_amount, 0) AS shipped_amount,
            COALESCE(soi.unit_price, 0) - COALESCE(quote.quotation_price, customer_price.customer_price, 0) AS price_diff,
            CASE
                WHEN COALESCE(quote.quotation_price, customer_price.customer_price, 0) = 0 THEN 0
                ELSE (COALESCE(soi.unit_price, 0) - COALESCE(quote.quotation_price, customer_price.customer_price, 0))
                     / NULLIF(COALESCE(quote.quotation_price, customer_price.customer_price, 0), 0) * 100
            END AS price_diff_rate,
            CASE
                WHEN COALESCE(quote.quotation_price, customer_price.customer_price, 0) = 0 THEN '无参考价'
                WHEN COALESCE(soi.unit_price, 0) < COALESCE(quote.quotation_price, customer_price.customer_price, 0) THEN '低于参考价'
                WHEN COALESCE(soi.unit_price, 0) > COALESCE(quote.quotation_price, customer_price.customer_price, 0) THEN '高于参考价'
                ELSE '等于参考价'
            END AS price_status,
            so.status
        FROM sales_order_items soi
        JOIN sales_orders so ON so.id = soi.order_id
        LEFT JOIN customers c ON c.id = so.customer_id
        LEFT JOIN products p ON p.id = soi.product_id
        LEFT JOIN latest_customer_price customer_price
          ON customer_price.customer_id = so.customer_id AND customer_price.product_id = soi.product_id
        LEFT JOIN latest_quotation_price quote
          ON quote.customer_id = so.customer_id AND quote.product_id = soi.product_id
        LEFT JOIN shipped_price shipped
          ON shipped.order_id = so.id AND shipped.order_item_id = soi.id
        {_where_clause(where)}
        ORDER BY so.order_date DESC NULLS LAST, so.order_no DESC, soi.id
        LIMIT 500
    """
    rows = query_db(sql, (VOID_STATUSES, VOID_STATUSES, *params))
    for row in rows:
        row["order_url"] = f"/sales/{row.get('order_id')}"
        row["price_diff_rate_text"] = f"{as_decimal_safe(row.get('price_diff_rate')):.1f}%"
    return {
        "filters": filters,
        "summary": _summary(
            rows,
            (
                ("订单含税金额", "order_amount", _money, "当前筛选订单行含税金额"),
                ("发货含税金额", "shipped_amount", _money, "已发货行金额"),
                ("价格偏差合计", "price_diff", _money, "订单价 - 参考价"),
            ),
        ) + [{"label": "低价行数", "value": sum(1 for row in rows if row.get("price_status") == "低于参考价"), "hint": "低于报价或客户价"}],
        "columns": [
            {"key": "order_no", "label": "订单号", "url_key": "order_url"},
            {"key": "order_date", "label": "订单日期"},
            {"key": "customer_name", "label": "客户"},
            {"key": "project_code", "label": "项目号"},
            {"key": "cabinet_no", "label": "柜号"},
            {"key": "product_code", "label": "物料编码"},
            {"key": "product_name", "label": "物料名称"},
            {"key": "specification", "label": "规格"},
            {"key": "unit", "label": "单位"},
            {"key": "order_qty", "label": "订单数量", "align": "right"},
            {"key": "reference_unit_price", "label": "参考单价", "align": "right", "format": "money"},
            {"key": "order_unit_price", "label": "订单单价", "align": "right", "format": "money"},
            {"key": "shipped_unit_price", "label": "发货均价", "align": "right", "format": "money"},
            {"key": "price_diff", "label": "价差", "align": "right", "format": "money"},
            {"key": "price_diff_rate_text", "label": "价差率", "align": "right"},
            {"key": "price_status", "label": "价格状态"},
        ],
        "rows": rows,
    }


def get_delivery_delay_analysis(query_db, args=None):
    filters = build_filters(args)
    where = ["COALESCE(so.status, '') NOT IN %s"]
    params = [VOID_STATUSES]
    _add_common_filters(
        where,
        params,
        filters,
        "COALESCE(so.delivery_date, so.order_date)",
        ("so.order_no", "c.name", "so.project_code", "so.cabinet_no", "p.code", "p.name"),
        "so.status",
        ("so.project_code", "so.cabinet_no", "soi.line_project_code", "soi.line_cabinet_no"),
    )
    sql = f"""
        WITH order_qty AS (
            SELECT order_id, SUM(COALESCE(quantity, 0)) AS order_qty
            FROM sales_order_items
            GROUP BY order_id
        ),
        shipped AS (
            SELECT ss.order_id,
                   MAX(ss.shipment_date) AS last_shipment_date,
                   SUM(COALESCE(ssi.quantity, 0)) AS shipped_qty,
                   SUM(COALESCE(ssi.amount_with_tax, ssi.amount, 0)) AS shipped_amount
            FROM sales_shipments ss
            LEFT JOIN sales_shipment_items ssi ON ssi.shipment_id = ss.id
            WHERE COALESCE(ss.status, '') NOT IN %s
            GROUP BY ss.order_id
        ),
        first_item AS (
            SELECT DISTINCT ON (soi.order_id) soi.order_id, p.code AS product_code, p.name AS product_name
            FROM sales_order_items soi
            LEFT JOIN products p ON p.id = soi.product_id
            ORDER BY soi.order_id, soi.id
        )
        SELECT
            so.id AS order_id,
            so.order_no,
            so.order_date,
            so.delivery_date,
            shipped.last_shipment_date,
            c.name AS customer_name,
            so.project_code,
            so.cabinet_no,
            first_item.product_code,
            first_item.product_name,
            COALESCE(order_qty.order_qty, 0) AS order_qty,
            COALESCE(shipped.shipped_qty, 0) AS shipped_qty,
            GREATEST(COALESCE(order_qty.order_qty, 0) - COALESCE(shipped.shipped_qty, 0), 0) AS open_qty,
            COALESCE(so.amount_with_tax, so.total_amount, 0) AS order_amount,
            COALESCE(shipped.shipped_amount, so.shipped_amount, 0) AS shipped_amount,
            CASE
                WHEN so.delivery_date IS NULL THEN 0
                WHEN COALESCE(shipped.shipped_qty, 0) >= COALESCE(order_qty.order_qty, 0)
                     AND shipped.last_shipment_date > so.delivery_date
                THEN shipped.last_shipment_date - so.delivery_date
                WHEN COALESCE(shipped.shipped_qty, 0) < COALESCE(order_qty.order_qty, 0)
                     AND CURRENT_DATE > so.delivery_date
                THEN CURRENT_DATE - so.delivery_date
                ELSE 0
            END AS delay_days,
            CASE
                WHEN so.delivery_date IS NULL THEN '未维护交期'
                WHEN COALESCE(shipped.shipped_qty, 0) >= COALESCE(order_qty.order_qty, 0)
                     AND shipped.last_shipment_date <= so.delivery_date
                THEN '按期完成'
                WHEN COALESCE(shipped.shipped_qty, 0) >= COALESCE(order_qty.order_qty, 0) THEN '逾期完成'
                WHEN CURRENT_DATE > so.delivery_date THEN '逾期未交'
                ELSE '未到期'
            END AS delivery_status,
            so.status
        FROM sales_orders so
        LEFT JOIN customers c ON c.id = so.customer_id
        LEFT JOIN order_qty ON order_qty.order_id = so.id
        LEFT JOIN shipped ON shipped.order_id = so.id
        LEFT JOIN first_item ON first_item.order_id = so.id
        {_where_clause(where)}
        ORDER BY delay_days DESC, so.delivery_date ASC NULLS LAST, so.order_no
        LIMIT 500
    """
    rows = query_db(sql, (VOID_STATUSES, *params))
    for row in rows:
        row["order_url"] = f"/sales/{row.get('order_id')}"
        row["shipment_rate"] = _rate(row.get("shipped_qty"), row.get("order_qty"))
    delayed = [row for row in rows if as_decimal_safe(row.get("delay_days")) > 0]
    return {
        "filters": filters,
        "summary": [
            {"label": "订单数", "value": len(rows), "hint": "当前筛选订单"},
            {"label": "逾期订单数", "value": len(delayed), "hint": "逾期未交或逾期完成"},
            {"label": "未交数量", "value": f"{sum(as_decimal_safe(row.get('open_qty')) for row in rows):,.3f}", "hint": "订单数量 - 发货数量"},
            {"label": "逾期金额", "value": _money(sum(as_decimal_safe(row.get("order_amount")) for row in delayed)), "hint": "逾期订单金额"},
        ],
        "columns": [
            {"key": "order_no", "label": "订单号", "url_key": "order_url"},
            {"key": "order_date", "label": "订单日期"},
            {"key": "delivery_date", "label": "计划交期"},
            {"key": "last_shipment_date", "label": "末次发货"},
            {"key": "customer_name", "label": "客户"},
            {"key": "project_code", "label": "项目号"},
            {"key": "cabinet_no", "label": "柜号"},
            {"key": "order_qty", "label": "订单数量", "align": "right"},
            {"key": "shipped_qty", "label": "已发数量", "align": "right"},
            {"key": "open_qty", "label": "未交数量", "align": "right"},
            {"key": "shipment_rate", "label": "发货率", "align": "right"},
            {"key": "delay_days", "label": "逾期天数", "align": "right"},
            {"key": "delivery_status", "label": "交付状态"},
        ],
        "rows": rows,
    }


def get_operation_snapshot(query_db, args=None):
    filters = build_filters(args)
    date_start = filters["date_start"]
    date_end = filters["date_end"]
    params = (date_start, date_end)
    rows = query_db(
        """
        WITH order_data AS (
            SELECT COUNT(*) AS doc_count, COALESCE(SUM(COALESCE(amount_with_tax, total_amount, 0)), 0) AS amount
            FROM sales_orders
            WHERE order_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
        ),
        shipment_data AS (
            SELECT COUNT(*) AS doc_count, COALESCE(SUM(COALESCE(amount_with_tax, shipped_amount, 0)), 0) AS amount
            FROM sales_shipments
            WHERE shipment_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
        ),
        invoice_data AS (
            SELECT COUNT(*) AS doc_count, COALESCE(SUM(COALESCE(amount_with_tax, total_amount, amount, 0)), 0) AS amount
            FROM sales_invoices
            WHERE invoice_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
        ),
        receipt_data AS (
            SELECT COUNT(*) AS doc_count, COALESCE(SUM(COALESCE(amount, 0)), 0) AS amount
            FROM customer_receipts
            WHERE receipt_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
        ),
        open_order_data AS (
            SELECT COUNT(DISTINCT so.id) AS doc_count,
                   COALESCE(SUM(GREATEST(COALESCE(soi.quantity, 0) - COALESCE(soi.shipped_qty, 0), 0) * COALESCE(soi.unit_price, 0)), 0) AS amount
            FROM sales_orders so
            JOIN sales_order_items soi ON soi.order_id = so.id
            WHERE COALESCE(so.status, '') NOT IN %s
              AND GREATEST(COALESCE(soi.quantity, 0) - COALESCE(soi.shipped_qty, 0), 0) > 0
        )
        SELECT '新增订单' AS item, doc_count, amount, '销售订单含税金额口径' AS basis FROM order_data
        UNION ALL SELECT '销售发货', doc_count, amount, '销售发货含税金额口径' FROM shipment_data
        UNION ALL SELECT '销售开票', doc_count, amount, '销售发票含税金额口径' FROM invoice_data
        UNION ALL SELECT '销售收款', doc_count, amount, '客户收款单金额口径' FROM receipt_data
        UNION ALL SELECT '未交订单', doc_count, amount, '订单行未发货数量 * 订单单价' FROM open_order_data
        """,
        params + (VOID_STATUSES,) + params + (VOID_STATUSES,) + params + (VOID_STATUSES,) + params + (VOID_STATUSES,) + (VOID_STATUSES,),
    )
    for row in rows:
        row["amount_text"] = _money(row.get("amount"))
    return {
        "filters": filters,
        "summary": [
            {"label": row.get("item"), "value": row.get("amount_text"), "hint": f"{row.get('doc_count')} 单"}
            for row in rows
        ],
        "columns": [
            {"key": "item", "label": "经营项目"},
            {"key": "doc_count", "label": "单据数", "align": "right"},
            {"key": "amount", "label": "金额", "align": "right", "format": "money"},
            {"key": "basis", "label": "统计口径"},
        ],
        "rows": rows,
    }


def get_sales_daily(query_db, args=None):
    filters = build_filters(args)
    params = (filters["date_start"], filters["date_end"])
    rows = query_db(
        """
        WITH days AS (
            SELECT generate_series(%s::date, %s::date, interval '1 day')::date AS report_date
        ),
        orders AS (
            SELECT order_date AS report_date,
                   COUNT(*) AS order_count,
                   SUM(COALESCE(amount_with_tax, total_amount, 0)) AS order_amount
            FROM sales_orders
            WHERE order_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
            GROUP BY order_date
        ),
        shipments AS (
            SELECT shipment_date AS report_date,
                   COUNT(*) AS shipment_count,
                   SUM(COALESCE(amount_with_tax, shipped_amount, 0)) AS shipment_amount
            FROM sales_shipments
            WHERE shipment_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
            GROUP BY shipment_date
        ),
        invoices AS (
            SELECT invoice_date AS report_date,
                   COUNT(*) AS invoice_count,
                   SUM(COALESCE(amount_with_tax, total_amount, amount, 0)) AS invoice_amount
            FROM sales_invoices
            WHERE invoice_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
            GROUP BY invoice_date
        ),
        receipts AS (
            SELECT receipt_date AS report_date,
                   COUNT(*) AS receipt_count,
                   SUM(COALESCE(amount, 0)) AS receipt_amount
            FROM customer_receipts
            WHERE receipt_date BETWEEN %s AND %s AND COALESCE(status, '') NOT IN %s
            GROUP BY receipt_date
        )
        SELECT days.report_date,
               COALESCE(orders.order_count, 0) AS order_count,
               COALESCE(orders.order_amount, 0) AS order_amount,
               COALESCE(shipments.shipment_count, 0) AS shipment_count,
               COALESCE(shipments.shipment_amount, 0) AS shipment_amount,
               COALESCE(invoices.invoice_count, 0) AS invoice_count,
               COALESCE(invoices.invoice_amount, 0) AS invoice_amount,
               COALESCE(receipts.receipt_count, 0) AS receipt_count,
               COALESCE(receipts.receipt_amount, 0) AS receipt_amount
        FROM days
        LEFT JOIN orders ON orders.report_date = days.report_date
        LEFT JOIN shipments ON shipments.report_date = days.report_date
        LEFT JOIN invoices ON invoices.report_date = days.report_date
        LEFT JOIN receipts ON receipts.report_date = days.report_date
        ORDER BY days.report_date DESC
        """,
        params + params + (VOID_STATUSES,) + params + (VOID_STATUSES,) + params + (VOID_STATUSES,) + params + (VOID_STATUSES,),
    )
    return {
        "filters": filters,
        "summary": _summary(
            rows,
            (
                ("订单金额", "order_amount", _money, "期间新增订单"),
                ("发货金额", "shipment_amount", _money, "期间销售发货"),
                ("开票金额", "invoice_amount", _money, "期间销售开票"),
                ("收款金额", "receipt_amount", _money, "期间客户收款"),
            ),
        ),
        "columns": [
            {"key": "report_date", "label": "日期"},
            {"key": "order_count", "label": "订单数", "align": "right"},
            {"key": "order_amount", "label": "订单金额", "align": "right", "format": "money"},
            {"key": "shipment_count", "label": "发货单数", "align": "right"},
            {"key": "shipment_amount", "label": "发货金额", "align": "right", "format": "money"},
            {"key": "invoice_count", "label": "发票数", "align": "right"},
            {"key": "invoice_amount", "label": "开票金额", "align": "right", "format": "money"},
            {"key": "receipt_count", "label": "收款单数", "align": "right"},
            {"key": "receipt_amount", "label": "收款金额", "align": "right", "format": "money"},
        ],
        "rows": rows,
    }


def get_project_cabinet_gross_margin(query_db, args=None):
    filters = build_filters(args)
    where = ["COALESCE(ss.status, '') NOT IN %s"]
    params = [VOID_STATUSES]
    _add_common_filters(
        where,
        params,
        filters,
        "ss.shipment_date",
        ("ss.shipment_no", "so.order_no", "c.name", "p.code", "p.name", "ss.project_code", "ss.cabinet_no"),
        "ss.status",
        ("ss.project_code", "ss.cabinet_no", "so.project_code", "so.cabinet_no"),
    )
    sql = f"""
        SELECT
            COALESCE(NULLIF(ss.project_code, ''), NULLIF(so.project_code, ''), '(未填项目号)') AS project_code,
            COALESCE(NULLIF(ss.cabinet_no, ''), NULLIF(so.cabinet_no, ''), '(未填柜号)') AS cabinet_no,
            c.name AS customer_name,
            MIN(ss.shipment_date) AS first_shipment_date,
            MAX(ss.shipment_date) AS last_shipment_date,
            COUNT(DISTINCT so.id) AS order_count,
            COUNT(DISTINCT ss.id) AS shipment_count,
            SUM(COALESCE(ssi.quantity, 0)) AS shipped_qty,
            SUM(COALESCE(ssi.amount_with_tax, ssi.amount, 0)) AS sales_revenue,
            SUM(CASE
                WHEN COALESCE(ssi.cost_amount, 0) <> 0 THEN COALESCE(ssi.cost_amount, 0)
                WHEN COALESCE(ssi.unit_cost, 0) <> 0 THEN COALESCE(ssi.quantity, 0) * COALESCE(ssi.unit_cost, 0)
                ELSE 0
            END) AS shipment_cost,
            SUM(CASE WHEN COALESCE(ssi.cost_amount, 0) = 0 AND COALESCE(ssi.unit_cost, 0) = 0 THEN 1 ELSE 0 END) AS missing_cost_lines
        FROM sales_shipments ss
        JOIN sales_shipment_items ssi ON ssi.shipment_id = ss.id
        LEFT JOIN sales_orders so ON so.id = ss.order_id
        LEFT JOIN customers c ON c.id = ss.customer_id
        LEFT JOIN products p ON p.id = ssi.product_id
        {_where_clause(where)}
        GROUP BY
            COALESCE(NULLIF(ss.project_code, ''), NULLIF(so.project_code, ''), '(未填项目号)'),
            COALESCE(NULLIF(ss.cabinet_no, ''), NULLIF(so.cabinet_no, ''), '(未填柜号)'),
            c.name
        ORDER BY sales_revenue DESC, project_code, cabinet_no
        LIMIT 500
    """
    rows = query_db(sql, tuple(params))
    for row in rows:
        revenue = as_decimal_safe(row.get("sales_revenue"))
        cost = as_decimal_safe(row.get("shipment_cost"))
        row["gross_margin"] = revenue - cost
        row["gross_margin_rate"] = _rate(row["gross_margin"], revenue)
        row["cost_status"] = "成本未核准" if as_decimal_safe(row.get("missing_cost_lines")) > 0 else "成本已取发货行"
        row["cost_basis"] = "发货行 cost_amount；为空时使用 quantity * unit_cost"
    return {
        "filters": filters,
        "summary": [
            {"label": "销售收入", "value": _money(sum(as_decimal_safe(row.get("sales_revenue")) for row in rows)), "hint": "发货行销售金额"},
            {"label": "发货成本", "value": _money(sum(as_decimal_safe(row.get("shipment_cost")) for row in rows)), "hint": "发货行成本口径"},
            {"label": "经营毛利", "value": _money(sum(as_decimal_safe(row.get("gross_margin")) for row in rows)), "hint": "销售收入 - 发货成本"},
            {"label": "成本未核准项", "value": sum(1 for row in rows if row.get("cost_status") == "成本未核准"), "hint": "存在成本为空的项目/柜号"},
        ],
        "columns": [
            {"key": "project_code", "label": "项目号"},
            {"key": "cabinet_no", "label": "柜号"},
            {"key": "customer_name", "label": "客户"},
            {"key": "first_shipment_date", "label": "首发日期"},
            {"key": "last_shipment_date", "label": "末发日期"},
            {"key": "order_count", "label": "订单数", "align": "right"},
            {"key": "shipment_count", "label": "发货单数", "align": "right"},
            {"key": "shipped_qty", "label": "发货数量", "align": "right"},
            {"key": "sales_revenue", "label": "销售收入", "align": "right", "format": "money"},
            {"key": "shipment_cost", "label": "发货成本", "align": "right", "format": "money"},
            {"key": "gross_margin", "label": "经营毛利", "align": "right", "format": "money"},
            {"key": "gross_margin_rate", "label": "毛利率", "align": "right"},
            {"key": "cost_status", "label": "成本状态"},
            {"key": "cost_basis", "label": "成本口径"},
        ],
        "rows": rows,
    }


REPORT_BUILDERS = {
    "price-execution-analysis": get_price_execution_analysis,
    "delivery-delay-analysis": get_delivery_delay_analysis,
    "operation-snapshot": get_operation_snapshot,
    "daily": get_sales_daily,
    "project-cabinet-gross-margin": get_project_cabinet_gross_margin,
}


def get_sales_analysis_report(query_db, report_key, args=None):
    if report_key not in REPORT_BUILDERS:
        raise KeyError(f"Unknown sales analysis report: {report_key}")
    report = REPORT_BUILDERS[report_key](query_db, args)
    meta = REPORT_META[report_key]
    return {
        "key": report_key,
        "title": meta["title"],
        "subtitle": meta["subtitle"],
        "filters": report["filters"],
        "summary": report["summary"],
        "columns": report["columns"],
        "rows": report["rows"],
    }
