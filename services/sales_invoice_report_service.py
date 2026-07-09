"""Read-only sales invoice and tax invoice report services.

Boundary:
- Read-only queries only.
- No schema changes.
- No invoice confirmation, tax declaration, receivable posting, or voucher logic.
"""
from decimal import Decimal


CANCELLED_STATUSES = ("cancelled", "voided", "已作废", "已红冲")


def _money(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _fmt_money(value):
    return f"{_money(value):,.2f}"


def _blank_to_none(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _normalize_filters(filters=None):
    filters = filters or {}
    return {
        "date_start": _blank_to_none(filters.get("date_start")),
        "date_end": _blank_to_none(filters.get("date_end")),
        "customer_id": _blank_to_none(filters.get("customer_id")),
        "customer_name": _blank_to_none(filters.get("customer_name")),
        "project_code": _blank_to_none(filters.get("project_code")),
        "serial_no": _blank_to_none(filters.get("serial_no")),
        "status": _blank_to_none(filters.get("status")),
        "invoice_type": _blank_to_none(filters.get("invoice_type")),
        "source_no": _blank_to_none(filters.get("source_no")),
        "group_by": _blank_to_none(filters.get("group_by")) or "customer",
    }


def _add_invoice_filters(where, params, filters, alias="si"):
    if filters.get("date_start"):
        where.append(f"{alias}.invoice_date >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where.append(f"{alias}.invoice_date <= %s")
        params.append(filters["date_end"])
    if filters.get("customer_id"):
        where.append(f"{alias}.customer_id = %s")
        params.append(filters["customer_id"])
    if filters.get("customer_name"):
        where.append("c.name ILIKE %s")
        params.append(f"%{filters['customer_name']}%")
    if filters.get("project_code"):
        where.append(f"{alias}.project_code ILIKE %s")
        params.append(f"%{filters['project_code']}%")
    if filters.get("serial_no"):
        where.append(f"{alias}.serial_no ILIKE %s")
        params.append(f"%{filters['serial_no']}%")
    if filters.get("status"):
        where.append(f"{alias}.status = %s")
        params.append(filters["status"])
    if filters.get("invoice_type"):
        where.append(f"{alias}.invoice_type = %s")
        params.append(filters["invoice_type"])
    if filters.get("source_no"):
        where.append(f"{alias}.source_no ILIKE %s")
        params.append(f"%{filters['source_no']}%")


def _invoice_columns(extra_columns=None):
    columns = [
        {"key": "invoice_no", "label": "发票号", "url_key": "invoice_url"},
        {"key": "invoice_date", "label": "开票日期"},
        {"key": "customer_name", "label": "客户"},
        {"key": "invoice_type", "label": "发票类型"},
        {"key": "source_no", "label": "来源单号"},
        {"key": "project_code", "label": "项目号"},
        {"key": "serial_no", "label": "机号"},
        {"key": "amount", "label": "不含税金额", "align": "right", "format": "money"},
        {"key": "tax_amount", "label": "税额", "align": "right", "format": "money"},
        {"key": "amount_with_tax", "label": "含税金额", "align": "right", "format": "money"},
        {"key": "tax_rate_display", "label": "税率"},
        {"key": "status", "label": "状态"},
    ]
    if extra_columns:
        columns.extend(extra_columns)
    return columns


def _summary_from_rows(rows, label="发票"):
    amount = sum((_money(row.get("amount")) for row in rows), Decimal("0"))
    tax_amount = sum((_money(row.get("tax_amount")) for row in rows), Decimal("0"))
    amount_with_tax = sum((_money(row.get("amount_with_tax")) for row in rows), Decimal("0"))
    return {
        "row_count": len(rows),
        "document_label": label,
        "amount": _fmt_money(amount),
        "tax_amount": _fmt_money(tax_amount),
        "amount_with_tax": _fmt_money(amount_with_tax),
        "amount_basis": "amount=不含税金额，tax_amount=税额，amount_with_tax=含税金额；若 amount_with_tax 为空，按 amount + tax_amount 只读补算展示。",
    }


def _decorate_invoice_rows(rows):
    for row in rows:
        row["invoice_url"] = f"/sales-invoices/{row['id']}" if row.get("id") else ""
        amount = _money(row.get("amount"))
        tax_amount = _money(row.get("tax_amount"))
        if amount > 0 and tax_amount > 0:
            row["tax_rate_display"] = f"{(tax_amount / amount * 100):.2f}%"
        else:
            row["tax_rate_display"] = "-"
        if not row.get("invoice_type"):
            row["invoice_type"] = "销售发票"
    return rows


def query_invoice_execution_detail(query_db, filters=None):
    """Sales order to invoice execution detail.

    Expected invoice amount uses sales_orders.amount_with_tax.
    Invoiced amount uses sales_invoices.amount_with_tax, with amount + tax_amount as read-only fallback.
    """
    filters = _normalize_filters(filters)
    where = ["COALESCE(so.status, '') NOT IN %s"]
    params = [CANCELLED_STATUSES]

    if filters.get("date_start"):
        where.append("so.order_date >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where.append("so.order_date <= %s")
        params.append(filters["date_end"])
    if filters.get("customer_id"):
        where.append("so.customer_id = %s")
        params.append(filters["customer_id"])
    if filters.get("customer_name"):
        where.append("c.name ILIKE %s")
        params.append(f"%{filters['customer_name']}%")
    if filters.get("project_code"):
        where.append("so.project_code ILIKE %s")
        params.append(f"%{filters['project_code']}%")
    if filters.get("serial_no"):
        where.append("so.serial_no ILIKE %s")
        params.append(f"%{filters['serial_no']}%")
    if filters.get("status"):
        where.append("so.status = %s")
        params.append(filters["status"])

    sql = f"""
        WITH invoice_by_order AS (
            SELECT
                COALESCE(
                    si.order_id,
                    CASE WHEN si.source_type = 'sales_order' THEN si.source_id END,
                    so_by_no.id
                ) AS order_id,
                COUNT(si.id) AS invoice_count,
                MIN(si.invoice_date) AS first_invoice_date,
                MAX(si.invoice_date) AS last_invoice_date,
                STRING_AGG(si.invoice_no, ', ' ORDER BY si.invoice_date, si.invoice_no) AS invoice_nos,
                SUM(COALESCE(si.amount, 0)) AS amount,
                SUM(COALESCE(si.tax_amount, 0)) AS tax_amount,
                SUM(COALESCE(NULLIF(si.amount_with_tax, 0), COALESCE(si.amount, 0) + COALESCE(si.tax_amount, 0))) AS amount_with_tax
            FROM sales_invoices si
            LEFT JOIN sales_orders so_by_no ON so_by_no.order_no = si.source_no
            WHERE COALESCE(si.status, '') NOT IN %s
            GROUP BY COALESCE(
                si.order_id,
                CASE WHEN si.source_type = 'sales_order' THEN si.source_id END,
                so_by_no.id
            )
        )
        SELECT
            so.id AS order_id,
            so.order_no,
            so.order_date,
            c.name AS customer_name,
            so.project_code,
            so.serial_no,
            so.status AS order_status,
            COALESCE(so.amount_with_tax, so.total_amount, 0) AS expected_amount_with_tax,
            COALESCE(so.tax_amount, 0) AS expected_tax_amount,
            COALESCE(inv.invoice_count, 0) AS invoice_count,
            inv.first_invoice_date,
            inv.last_invoice_date,
            inv.invoice_nos,
            COALESCE(inv.amount, 0) AS invoiced_amount,
            COALESCE(inv.tax_amount, 0) AS invoiced_tax_amount,
            COALESCE(inv.amount_with_tax, 0) AS invoiced_amount_with_tax,
            GREATEST(COALESCE(so.amount_with_tax, so.total_amount, 0) - COALESCE(inv.amount_with_tax, 0), 0) AS uninvoiced_amount_with_tax,
            CASE
                WHEN COALESCE(so.amount_with_tax, so.total_amount, 0) <= 0 THEN '无金额'
                WHEN COALESCE(inv.amount_with_tax, 0) <= 0 THEN '未开票'
                WHEN COALESCE(inv.amount_with_tax, 0) >= COALESCE(so.amount_with_tax, so.total_amount, 0) THEN '已开票'
                ELSE '部分开票'
            END AS invoice_execution_status
        FROM sales_orders so
        LEFT JOIN customers c ON c.id = so.customer_id
        LEFT JOIN invoice_by_order inv ON inv.order_id = so.id
        WHERE {" AND ".join(where)}
        ORDER BY so.order_date DESC NULLS LAST, so.order_no DESC
    """

    rows = query_db(sql, tuple([CANCELLED_STATUSES] + params))
    for row in rows:
        row["order_url"] = f"/sales/{row['order_id']}" if row.get("order_id") else ""
    summary = {
        "row_count": len(rows),
        "document_label": "销售订单",
        "expected_amount_with_tax": _fmt_money(sum((_money(row.get("expected_amount_with_tax")) for row in rows), Decimal("0"))),
        "invoiced_amount_with_tax": _fmt_money(sum((_money(row.get("invoiced_amount_with_tax")) for row in rows), Decimal("0"))),
        "uninvoiced_amount_with_tax": _fmt_money(sum((_money(row.get("uninvoiced_amount_with_tax")) for row in rows), Decimal("0"))),
        "amount_basis": "应开票金额使用 sales_orders.amount_with_tax；已开票金额使用 sales_invoices.amount_with_tax，空值按 amount + tax_amount 展示。",
    }
    columns = [
        {"key": "order_no", "label": "销售订单号", "url_key": "order_url"},
        {"key": "order_date", "label": "订单日期"},
        {"key": "customer_name", "label": "客户"},
        {"key": "project_code", "label": "项目号"},
        {"key": "serial_no", "label": "机号"},
        {"key": "order_status", "label": "订单状态"},
        {"key": "expected_amount_with_tax", "label": "应开票含税金额", "align": "right", "format": "money"},
        {"key": "invoiced_amount_with_tax", "label": "已开票含税金额", "align": "right", "format": "money"},
        {"key": "invoiced_tax_amount", "label": "已开票税额", "align": "right", "format": "money"},
        {"key": "uninvoiced_amount_with_tax", "label": "未开票含税金额", "align": "right", "format": "money"},
        {"key": "invoice_count", "label": "发票张数", "align": "right"},
        {"key": "invoice_nos", "label": "发票号"},
        {"key": "last_invoice_date", "label": "最近开票日期"},
        {"key": "invoice_execution_status", "label": "开票状态"},
    ]
    return {"filters": filters, "summary": summary, "columns": columns, "rows": rows}


def query_invoice_summary(query_db, filters=None):
    """Sales invoice summary grouped by customer/project/serial/invoice_type/status/month."""
    filters = _normalize_filters(filters)
    group_by = filters.get("group_by") if filters.get("group_by") in {"customer", "project", "serial", "invoice_type", "status", "month"} else "customer"
    group_expr = {
        "customer": "COALESCE(c.name, '未指定客户')",
        "project": "COALESCE(NULLIF(si.project_code, ''), '未指定项目')",
        "serial": "COALESCE(NULLIF(si.serial_no, ''), '未指定机号')",
        "invoice_type": "COALESCE(NULLIF(si.invoice_type, ''), '销售发票')",
        "status": "COALESCE(NULLIF(si.status, ''), '未指定状态')",
        "month": "TO_CHAR(si.invoice_date, 'YYYY-MM')",
    }[group_by]

    where = ["COALESCE(si.status, '') NOT IN %s"]
    params = [CANCELLED_STATUSES]
    _add_invoice_filters(where, params, filters, "si")

    sql = f"""
        SELECT
            {group_expr} AS group_name,
            COUNT(si.id) AS invoice_count,
            COUNT(DISTINCT si.customer_id) AS customer_count,
            MIN(si.invoice_date) AS first_invoice_date,
            MAX(si.invoice_date) AS last_invoice_date,
            SUM(COALESCE(si.amount, 0)) AS amount,
            SUM(COALESCE(si.tax_amount, 0)) AS tax_amount,
            SUM(COALESCE(NULLIF(si.amount_with_tax, 0), COALESCE(si.amount, 0) + COALESCE(si.tax_amount, 0))) AS amount_with_tax
        FROM sales_invoices si
        LEFT JOIN customers c ON c.id = si.customer_id
        WHERE {" AND ".join(where)}
        GROUP BY {group_expr}
        ORDER BY amount_with_tax DESC, group_name
    """
    rows = query_db(sql, tuple(params))
    summary = _summary_from_rows(rows, "汇总行")
    summary["group_by"] = group_by
    columns = [
        {"key": "group_name", "label": "汇总项目"},
        {"key": "invoice_count", "label": "发票张数", "align": "right"},
        {"key": "customer_count", "label": "客户数", "align": "right"},
        {"key": "first_invoice_date", "label": "最早开票日期"},
        {"key": "last_invoice_date", "label": "最近开票日期"},
        {"key": "amount", "label": "不含税金额", "align": "right", "format": "money"},
        {"key": "tax_amount", "label": "税额", "align": "right", "format": "money"},
        {"key": "amount_with_tax", "label": "含税金额", "align": "right", "format": "money"},
    ]
    return {"filters": filters, "summary": summary, "columns": columns, "rows": rows}


def query_tax_registration_detail(query_db, filters=None):
    """Sales tax invoice registration detail.

    There is no separate statutory tax table in the approved boundary, so this report
    reads tax information from sales_invoices only.
    """
    filters = _normalize_filters(filters)
    where = ["COALESCE(si.status, '') NOT IN %s"]
    params = [CANCELLED_STATUSES]
    _add_invoice_filters(where, params, filters, "si")

    sql = f"""
        SELECT
            si.id,
            si.invoice_no,
            si.invoice_date,
            c.name AS customer_name,
            COALESCE(NULLIF(si.invoice_type, ''), '销售发票') AS invoice_type,
            si.source_type,
            si.source_no,
            si.project_code,
            si.serial_no,
            COALESCE(si.amount, 0) AS amount,
            COALESCE(si.tax_amount, 0) AS tax_amount,
            COALESCE(NULLIF(si.amount_with_tax, 0), COALESCE(si.amount, 0) + COALESCE(si.tax_amount, 0)) AS amount_with_tax,
            COALESCE(NULLIF(si.status, ''), '未指定状态') AS status,
            si.remark
        FROM sales_invoices si
        LEFT JOIN customers c ON c.id = si.customer_id
        WHERE {" AND ".join(where)}
        ORDER BY si.invoice_date DESC NULLS LAST, si.invoice_no DESC
    """
    rows = _decorate_invoice_rows(query_db(sql, tuple(params)))
    return {
        "filters": filters,
        "summary": _summary_from_rows(rows, "税票登记"),
        "columns": _invoice_columns([{"key": "remark", "label": "备注"}]),
        "rows": rows,
    }


def query_tax_summary(query_db, filters=None):
    """Sales tax invoice summary grouped by tax rate display and invoice type."""
    filters = _normalize_filters(filters)
    where = ["COALESCE(si.status, '') NOT IN %s"]
    params = [CANCELLED_STATUSES]
    _add_invoice_filters(where, params, filters, "si")

    sql = f"""
        WITH base AS (
            SELECT
                COALESCE(NULLIF(si.invoice_type, ''), '销售发票') AS invoice_type,
                CASE
                    WHEN COALESCE(si.amount, 0) > 0 AND COALESCE(si.tax_amount, 0) > 0
                    THEN ROUND((si.tax_amount / si.amount * 100)::numeric, 2)::text || '%%'
                    ELSE '-'
                END AS tax_rate_display,
                COALESCE(si.amount, 0) AS amount,
                COALESCE(si.tax_amount, 0) AS tax_amount,
                COALESCE(NULLIF(si.amount_with_tax, 0), COALESCE(si.amount, 0) + COALESCE(si.tax_amount, 0)) AS amount_with_tax
            FROM sales_invoices si
            LEFT JOIN customers c ON c.id = si.customer_id
            WHERE {" AND ".join(where)}
        )
        SELECT
            invoice_type,
            tax_rate_display,
            COUNT(*) AS invoice_count,
            SUM(amount) AS amount,
            SUM(tax_amount) AS tax_amount,
            SUM(amount_with_tax) AS amount_with_tax
        FROM base
        GROUP BY invoice_type, tax_rate_display
        ORDER BY invoice_type, tax_rate_display
    """
    rows = query_db(sql, tuple(params))
    return {
        "filters": filters,
        "summary": _summary_from_rows(rows, "税票汇总"),
        "columns": [
            {"key": "invoice_type", "label": "发票类型"},
            {"key": "tax_rate_display", "label": "税率"},
            {"key": "invoice_count", "label": "发票张数", "align": "right"},
            {"key": "amount", "label": "不含税金额", "align": "right", "format": "money"},
            {"key": "tax_amount", "label": "税额", "align": "right", "format": "money"},
            {"key": "amount_with_tax", "label": "含税金额", "align": "right", "format": "money"},
        ],
        "rows": rows,
    }


REPORT_QUERIES = {
    "invoice-execution-detail": query_invoice_execution_detail,
    "invoice-summary": query_invoice_summary,
    "tax-registration-detail": query_tax_registration_detail,
    "tax-summary": query_tax_summary,
}


REPORT_TITLES = {
    "invoice-execution-detail": "销售开票执行明细",
    "invoice-summary": "销售发票汇总表",
    "tax-registration-detail": "销售税票登记表",
    "tax-summary": "销售税票汇总表",
}


def build_sales_invoice_report(query_db, report_key, filters=None):
    """Build a uniform report context for Flask routes."""
    if report_key not in REPORT_QUERIES:
        raise ValueError(f"Unknown sales invoice report: {report_key}")
    report = REPORT_QUERIES[report_key](query_db, filters)
    report["title"] = REPORT_TITLES[report_key]
    report["report_key"] = report_key
    return report
