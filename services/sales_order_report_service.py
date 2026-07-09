"""Read-only sales order report queries."""
from decimal import Decimal


CLOSED_STATUSES = ("已关闭", "已作废", "已取消", "closed", "void", "voided", "cancelled", "canceled")


REPORT_TITLES = {
    "summary": "销售汇总表",
    "order_execution_summary": "销售订单执行汇总",
    "customer_open_order_analysis": "客户未交订单分析",
    "project_serial_open_order_analysis": "项目/机号未交订单分析",
}


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _rate(numerator, denominator):
    denominator = _decimal(denominator)
    if denominator <= 0:
        return "0.0%"
    return f"{(_decimal(numerator) / denominator * 100):.1f}%"


def _money(value):
    return f"{_decimal(value):,.2f}"


def _clean_filters(filters):
    filters = filters or {}
    return {
        "date_start": (filters.get("date_start") or "").strip(),
        "date_end": (filters.get("date_end") or "").strip(),
        "customer_name": (filters.get("customer_name") or "").strip(),
        "project_code": (filters.get("project_code") or "").strip(),
        "serial_no": (filters.get("serial_no") or "").strip(),
        "status": (filters.get("status") or "").strip(),
        "group_by": (filters.get("group_by") or "").strip(),
    }


def _append_order_filters(where, params, filters):
    if filters["date_start"]:
        where.append("so.order_date >= %s")
        params.append(filters["date_start"])
    if filters["date_end"]:
        where.append("so.order_date <= %s")
        params.append(filters["date_end"])
    if filters["customer_name"]:
        where.append("c.name ILIKE %s")
        params.append(f"%{filters['customer_name']}%")
    if filters["project_code"]:
        where.append("so.project_code ILIKE %s")
        params.append(f"%{filters['project_code']}%")
    if filters["serial_no"]:
        where.append("so.serial_no ILIKE %s")
        params.append(f"%{filters['serial_no']}%")
    if filters["status"]:
        where.append("so.status = %s")
        params.append(filters["status"])


def _base_order_execution_cte():
    closed_placeholders = ", ".join(["%s"] * len(CLOSED_STATUSES))
    return f"""
        WITH order_lines AS (
            SELECT
                order_id,
                COUNT(*) AS line_count,
                SUM(COALESCE(quantity, 0)) AS order_qty,
                SUM(COALESCE(shipped_qty, 0)) AS shipped_qty,
                SUM(GREATEST(COALESCE(quantity, 0) - COALESCE(shipped_qty, 0), 0)) AS open_qty,
                SUM(COALESCE(amount_with_tax, amount, 0)) AS line_amount
            FROM sales_order_items
            GROUP BY order_id
        ),
        shipments AS (
            SELECT
                order_id,
                COUNT(*) AS shipment_count,
                SUM(COALESCE(amount_with_tax, shipped_amount, 0)) AS shipped_amount
            FROM sales_shipments
            WHERE COALESCE(status, '') NOT IN ({closed_placeholders})
            GROUP BY order_id
        ),
        invoices AS (
            SELECT
                COALESCE(order_id, CASE WHEN source_type = 'sales_order' THEN source_id END) AS order_id,
                COUNT(*) AS invoice_count,
                SUM(COALESCE(amount_with_tax, total_amount, amount, 0)) AS invoiced_amount
            FROM sales_invoices
            WHERE COALESCE(status, '') NOT IN ({closed_placeholders})
              AND COALESCE(order_id, CASE WHEN source_type = 'sales_order' THEN source_id END) IS NOT NULL
            GROUP BY COALESCE(order_id, CASE WHEN source_type = 'sales_order' THEN source_id END)
        ),
        receivables AS (
            SELECT
                source_id AS order_id,
                COUNT(*) AS receivable_count,
                SUM(COALESCE(total_amount, expected_amount, 0)) AS receivable_amount,
                SUM(COALESCE(received_amount, confirmed_amount, 0)) AS received_amount,
                SUM(COALESCE(balance, 0)) AS receivable_balance
            FROM customer_receivables
            WHERE source_type = 'sales_order'
            GROUP BY source_id
        ),
        order_base AS (
            SELECT
                so.id,
                so.order_no,
                so.order_date,
                so.delivery_date,
                so.status,
                c.id AS customer_id,
                c.name AS customer_name,
                so.project_code,
                so.serial_no,
                COALESCE(ol.line_count, 0) AS line_count,
                COALESCE(ol.order_qty, 0) AS order_qty,
                COALESCE(ol.shipped_qty, 0) AS shipped_qty,
                COALESCE(ol.open_qty, 0) AS open_qty,
                COALESCE(so.amount_with_tax, so.total_amount, ol.line_amount, 0) AS order_amount,
                COALESCE(sh.shipment_count, 0) AS shipment_count,
                COALESCE(sh.shipped_amount, so.shipped_amount, 0) AS shipped_amount,
                COALESCE(inv.invoice_count, 0) AS invoice_count,
                COALESCE(inv.invoiced_amount, 0) AS invoiced_amount,
                COALESCE(ar.receivable_amount, 0) AS receivable_amount,
                COALESCE(ar.received_amount, 0) AS received_amount,
                COALESCE(ar.receivable_balance, 0) AS receivable_balance,
                CASE
                    WHEN so.delivery_date < CURRENT_DATE
                     AND COALESCE(ol.open_qty, 0) > 0
                    THEN CURRENT_DATE - so.delivery_date
                    ELSE 0
                END AS overdue_days,
                CASE
                    WHEN COALESCE(ol.open_qty, 0) <= 0 THEN '已交清'
                    WHEN so.delivery_date < CURRENT_DATE THEN '逾期未交'
                    WHEN COALESCE(ol.shipped_qty, 0) > 0 THEN '部分发货'
                    ELSE '待发货'
                END AS execution_status
            FROM sales_orders so
            LEFT JOIN customers c ON c.id = so.customer_id
            LEFT JOIN order_lines ol ON ol.order_id = so.id
            LEFT JOIN shipments sh ON sh.order_id = so.id
            LEFT JOIN invoices inv ON inv.order_id = so.id
            LEFT JOIN receivables ar ON ar.order_id = so.id
        )
    """


def _base_params():
    return list(CLOSED_STATUSES) + list(CLOSED_STATUSES)


def _summarize(rows):
    total_order_amount = sum(_decimal(row.get("order_amount")) for row in rows)
    total_shipped_amount = sum(_decimal(row.get("shipped_amount")) for row in rows)
    total_open_amount = sum(_decimal(row.get("open_amount")) for row in rows)
    total_open_qty = sum(_decimal(row.get("open_qty")) for row in rows)
    overdue_count = sum(1 for row in rows if _decimal(row.get("overdue_open_qty")) > 0 or _decimal(row.get("overdue_days")) > 0)
    return {
        "order_count": len(rows),
        "total_order_amount": _money(total_order_amount),
        "total_shipped_amount": _money(total_shipped_amount),
        "total_open_amount": _money(total_open_amount),
        "total_open_qty": f"{total_open_qty:,.2f}",
        "shipment_rate": _rate(total_shipped_amount, total_order_amount),
        "overdue_count": overdue_count,
    }


def _decorate_rows(rows):
    for row in rows:
        order_amount = _decimal(row.get("order_amount"))
        shipped_amount = _decimal(row.get("shipped_amount"))
        open_qty = _decimal(row.get("open_qty"))
        order_qty = _decimal(row.get("order_qty"))
        row["open_amount"] = max(order_amount - shipped_amount, Decimal("0"))
        row["shipment_rate"] = _rate(shipped_amount, order_amount)
        row["open_qty_rate"] = _rate(open_qty, order_qty)
        row["order_url"] = f"/sales/{row['id']}" if row.get("id") else ""
        row["customer_url"] = f"/customer?id={row['customer_id']}" if row.get("customer_id") else ""
    return rows


def query_sales_summary(query_db, filters=None):
    filters = _clean_filters(filters)
    where = ["1=1"]
    params = _base_params()
    _append_order_filters(where, params, filters)

    group_by = filters.get("group_by") or "customer"
    dimensions = {
        "customer": ("customer_id, customer_name, NULL::varchar AS project_code, NULL::varchar AS serial_no", "customer_id, customer_name", "customer_name"),
        "project": ("MIN(customer_id) AS customer_id, MIN(customer_name) AS customer_name, project_code, NULL::varchar AS serial_no", "project_code", "project_code"),
        "serial": ("MIN(customer_id) AS customer_id, MIN(customer_name) AS customer_name, NULL::varchar AS project_code, serial_no", "serial_no", "serial_no"),
    }
    select_expr, group_expr, order_expr = dimensions.get(group_by, dimensions["customer"])
    sql = f"""
        {_base_order_execution_cte()}
        SELECT
            MIN(id) AS id,
            {select_expr},
            COUNT(*) AS order_count,
            SUM(order_qty) AS order_qty,
            SUM(shipped_qty) AS shipped_qty,
            SUM(open_qty) AS open_qty,
            SUM(order_amount) AS order_amount,
            SUM(shipped_amount) AS shipped_amount,
            SUM(invoiced_amount) AS invoiced_amount,
            SUM(received_amount) AS received_amount,
            SUM(receivable_balance) AS receivable_balance,
            SUM(CASE WHEN overdue_days > 0 THEN open_qty ELSE 0 END) AS overdue_open_qty,
            MAX(overdue_days) AS max_overdue_days
        FROM order_base
        WHERE {" AND ".join(where)}
        GROUP BY {group_expr}
        ORDER BY {order_expr} NULLS LAST
        LIMIT 500
    """
    rows = _decorate_rows(query_db(sql, tuple(params)))
    columns = [
        {"key": "customer_name", "label": "客户", "url_key": "customer_url"},
        {"key": "project_code", "label": "项目号"},
        {"key": "serial_no", "label": "机号"},
        {"key": "order_count", "label": "订单数", "align": "right"},
        {"key": "order_qty", "label": "订单数量", "align": "right", "format": "qty"},
        {"key": "shipped_qty", "label": "已发数量", "align": "right", "format": "qty"},
        {"key": "open_qty", "label": "未交数量", "align": "right", "format": "qty"},
        {"key": "order_amount", "label": "销售含税金额", "align": "right", "format": "money"},
        {"key": "shipped_amount", "label": "已发货含税金额", "align": "right", "format": "money"},
        {"key": "open_amount", "label": "未交含税金额", "align": "right", "format": "money"},
        {"key": "shipment_rate", "label": "发货率", "align": "right"},
        {"key": "receivable_balance", "label": "应收余额", "align": "right", "format": "money"},
        {"key": "max_overdue_days", "label": "最大逾期天数", "align": "right"},
    ]
    return {"title": REPORT_TITLES["summary"], "filters": filters, "summary": _summarize(rows), "columns": columns, "rows": rows}


def query_order_execution_summary(query_db, filters=None):
    filters = _clean_filters(filters)
    where = ["1=1"]
    params = _base_params()
    _append_order_filters(where, params, filters)
    sql = f"""
        {_base_order_execution_cte()}
        SELECT *
        FROM order_base
        WHERE {" AND ".join(where)}
        ORDER BY order_date DESC NULLS LAST, order_no DESC
        LIMIT 500
    """
    rows = _decorate_rows(query_db(sql, tuple(params)))
    columns = [
        {"key": "order_no", "label": "销售订单号", "url_key": "order_url"},
        {"key": "order_date", "label": "订单日期"},
        {"key": "customer_name", "label": "客户", "url_key": "customer_url"},
        {"key": "project_code", "label": "项目号"},
        {"key": "serial_no", "label": "机号"},
        {"key": "status", "label": "订单状态"},
        {"key": "execution_status", "label": "执行状态"},
        {"key": "delivery_date", "label": "交付日期"},
        {"key": "order_qty", "label": "订单数量", "align": "right", "format": "qty"},
        {"key": "shipped_qty", "label": "已发数量", "align": "right", "format": "qty"},
        {"key": "open_qty", "label": "未交数量", "align": "right", "format": "qty"},
        {"key": "order_amount", "label": "订单含税金额", "align": "right", "format": "money"},
        {"key": "shipped_amount", "label": "发货含税金额", "align": "right", "format": "money"},
        {"key": "open_amount", "label": "未交含税金额", "align": "right", "format": "money"},
        {"key": "shipment_rate", "label": "发货率", "align": "right"},
        {"key": "invoiced_amount", "label": "已开票含税金额", "align": "right", "format": "money"},
        {"key": "received_amount", "label": "已收款金额", "align": "right", "format": "money"},
        {"key": "receivable_balance", "label": "应收余额", "align": "right", "format": "money"},
        {"key": "overdue_days", "label": "逾期天数", "align": "right"},
    ]
    return {"title": REPORT_TITLES["order_execution_summary"], "filters": filters, "summary": _summarize(rows), "columns": columns, "rows": rows}


def query_customer_open_order_analysis(query_db, filters=None):
    filters = _clean_filters(filters)
    where = [
        "open_qty > 0",
        "COALESCE(status, '') NOT IN %s",
    ]
    params = _base_params()
    _append_order_filters(where, params, filters)
    params.append(tuple(CLOSED_STATUSES))
    sql = f"""
        {_base_order_execution_cte()}
        SELECT
            MIN(id) AS id,
            customer_id,
            customer_name,
            COUNT(*) AS order_count,
            SUM(order_qty) AS order_qty,
            SUM(shipped_qty) AS shipped_qty,
            SUM(open_qty) AS open_qty,
            SUM(order_amount) AS order_amount,
            SUM(shipped_amount) AS shipped_amount,
            SUM(order_amount - shipped_amount) AS open_amount,
            SUM(CASE WHEN overdue_days > 0 THEN open_qty ELSE 0 END) AS overdue_open_qty,
            COUNT(*) FILTER (WHERE overdue_days > 0) AS overdue_order_count,
            COUNT(*) FILTER (WHERE shipped_qty > 0 AND open_qty > 0) AS partial_shipped_count,
            MAX(overdue_days) AS max_overdue_days
        FROM order_base
        WHERE {" AND ".join(where)}
        GROUP BY customer_id, customer_name
        ORDER BY overdue_open_qty DESC, open_amount DESC, customer_name NULLS LAST
        LIMIT 500
    """
    rows = _decorate_rows(query_db(sql, tuple(params)))
    columns = [
        {"key": "customer_name", "label": "客户", "url_key": "customer_url"},
        {"key": "order_count", "label": "未交订单数", "align": "right"},
        {"key": "partial_shipped_count", "label": "部分发货订单数", "align": "right"},
        {"key": "overdue_order_count", "label": "逾期订单数", "align": "right"},
        {"key": "open_qty", "label": "未交数量", "align": "right", "format": "qty"},
        {"key": "overdue_open_qty", "label": "逾期未交数量", "align": "right", "format": "qty"},
        {"key": "open_amount", "label": "未交含税金额", "align": "right", "format": "money"},
        {"key": "open_qty_rate", "label": "未交数量占比", "align": "right"},
        {"key": "max_overdue_days", "label": "最大逾期天数", "align": "right"},
    ]
    return {"title": REPORT_TITLES["customer_open_order_analysis"], "filters": filters, "summary": _summarize(rows), "columns": columns, "rows": rows}


def query_project_serial_open_order_analysis(query_db, filters=None):
    filters = _clean_filters(filters)
    where = [
        "open_qty > 0",
        "COALESCE(status, '') NOT IN %s",
    ]
    params = _base_params()
    _append_order_filters(where, params, filters)
    params.append(tuple(CLOSED_STATUSES))
    sql = f"""
        {_base_order_execution_cte()}
        SELECT
            MIN(id) AS id,
            MIN(customer_id) AS customer_id,
            MIN(customer_name) AS customer_name,
            project_code,
            serial_no,
            COUNT(*) AS order_count,
            SUM(order_qty) AS order_qty,
            SUM(shipped_qty) AS shipped_qty,
            SUM(open_qty) AS open_qty,
            SUM(order_amount) AS order_amount,
            SUM(shipped_amount) AS shipped_amount,
            SUM(order_amount - shipped_amount) AS open_amount,
            SUM(CASE WHEN overdue_days > 0 THEN open_qty ELSE 0 END) AS overdue_open_qty,
            COUNT(*) FILTER (WHERE overdue_days > 0) AS overdue_order_count,
            MAX(overdue_days) AS max_overdue_days,
            CASE
                WHEN MAX(overdue_days) >= 30 THEN '高风险'
                WHEN MAX(overdue_days) > 0 THEN '逾期'
                WHEN SUM(shipped_qty) > 0 THEN '部分发货'
                ELSE '待发货'
            END AS delivery_risk
        FROM order_base
        WHERE {" AND ".join(where)}
        GROUP BY project_code, serial_no
        ORDER BY max_overdue_days DESC, open_amount DESC, project_code NULLS LAST, serial_no NULLS LAST
        LIMIT 500
    """
    rows = _decorate_rows(query_db(sql, tuple(params)))
    columns = [
        {"key": "project_code", "label": "项目号"},
        {"key": "serial_no", "label": "机号"},
        {"key": "customer_name", "label": "客户", "url_key": "customer_url"},
        {"key": "order_count", "label": "未交订单数", "align": "right"},
        {"key": "open_qty", "label": "未交数量", "align": "right", "format": "qty"},
        {"key": "overdue_open_qty", "label": "逾期未交数量", "align": "right", "format": "qty"},
        {"key": "open_amount", "label": "未交含税金额", "align": "right", "format": "money"},
        {"key": "max_overdue_days", "label": "最大逾期天数", "align": "right"},
        {"key": "delivery_risk", "label": "交付风险"},
    ]
    return {"title": REPORT_TITLES["project_serial_open_order_analysis"], "filters": filters, "summary": _summarize(rows), "columns": columns, "rows": rows}
