"""Read-only sales shipment report services.

This module is intentionally side-effect free. It only queries existing sales
shipment, order, invoice, receivable, and product data.
"""
from decimal import Decimal, InvalidOperation


VOID_STATUSES = (
    "cancelled",
    "canceled",
    "voided",
    "void",
    "已作废",
    "已取消",
    "作废",
    "取消",
)


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value):
    return f"{_decimal(value):,.2f}"


def _qty(value):
    number = _decimal(value)
    return f"{number:,.3f}".rstrip("0").rstrip(".")


def _percent(numerator, denominator):
    denominator = _decimal(denominator)
    if denominator <= 0:
        return "0%"
    return f"{(_decimal(numerator) / denominator * Decimal('100')):.1f}%"


def _clean_filters(filters):
    return {key: (value.strip() if isinstance(value, str) else value) for key, value in (filters or {}).items()}


def _add_text_filter(where, params, expression, value):
    if value:
        where.append(f"{expression} ILIKE %s")
        params.append(f"%{value}%")


def _add_common_shipment_filters(where, params, filters, date_expression="ss.shipment_date"):
    if filters.get("date_start"):
        where.append(f"{date_expression} >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where.append(f"{date_expression} <= %s")
        params.append(filters["date_end"])
    if filters.get("customer_id"):
        where.append("COALESCE(ss.customer_id, so.customer_id) = %s")
        params.append(filters["customer_id"])
    _add_text_filter(where, params, "c.name", filters.get("customer_name"))
    _add_text_filter(where, params, "COALESCE(ss.project_code, so.project_code)", filters.get("project_code"))
    _add_text_filter(where, params, "COALESCE(ss.cabinet_no, so.cabinet_no)", filters.get("cabinet_no"))
    _add_text_filter(where, params, "COALESCE(ss.shipment_no, '')", filters.get("shipment_no"))
    _add_text_filter(where, params, "COALESCE(so.order_no, ss.source_no, '')", filters.get("order_no"))
    if filters.get("status"):
        where.append("ss.status = %s")
        params.append(filters["status"])


def _add_product_filter(where, params, filters):
    keyword = filters.get("product_keyword")
    if keyword:
        where.append(
            "(p.code ILIKE %s OR p.name ILIKE %s OR p.specification ILIKE %s)"
        )
        pattern = f"%{keyword}%"
        params.extend([pattern, pattern, pattern])


def _base_filter_state(filters, report_type):
    return {
        "report_type": report_type,
        "date_start": filters.get("date_start") or "",
        "date_end": filters.get("date_end") or "",
        "customer_id": filters.get("customer_id") or "",
        "customer_name": filters.get("customer_name") or "",
        "product_keyword": filters.get("product_keyword") or "",
        "project_code": filters.get("project_code") or "",
        "cabinet_no": filters.get("cabinet_no") or "",
        "shipment_no": filters.get("shipment_no") or "",
        "order_no": filters.get("order_no") or "",
        "status": filters.get("status") or "",
        "only_open": filters.get("only_open") or "",
    }


def _columns(*pairs):
    return [{"key": key, "label": label, **extra} for key, label, extra in pairs]


def _status_text(value):
    return value or "未定"


def query_shipment_execution_detail(query_db, filters=None):
    """Sales shipment execution line detail.

    Basis: shipment line quantity and amount. Invoice/receivable amounts are
    aggregated at shipment document level and repeated on each shipment line for
    traceability; summary totals de-duplicate by shipment id.
    """
    filters = _clean_filters(filters)
    where = ["COALESCE(ss.status, '') NOT IN %s"]
    where_params = [VOID_STATUSES]
    _add_common_shipment_filters(where, where_params, filters)
    _add_product_filter(where, where_params, filters)

    sql = f"""
        WITH invoice_by_shipment AS (
            SELECT
                ss.id AS shipment_id,
                SUM(COALESCE(si.amount_with_tax, si.total_amount, si.amount, 0)) AS invoiced_amount,
                MAX(si.invoice_date) AS last_invoice_date
            FROM sales_shipments ss
            JOIN sales_invoices si
              ON (si.source_type IN ('sales_shipment', 'shipment') AND si.source_id = ss.id)
              OR NULLIF(si.source_no, '') = ss.shipment_no
            WHERE COALESCE(si.status, '') NOT IN %s
            GROUP BY ss.id
        ),
        receivable_by_shipment AS (
            SELECT
                ss.id AS shipment_id,
                SUM(COALESCE(cr.total_amount, cr.expected_amount, 0)) AS receivable_amount,
                SUM(COALESCE(cr.received_amount, cr.confirmed_amount, 0)) AS received_amount,
                SUM(COALESCE(cr.balance, 0)) AS receivable_balance,
                MAX(cr.due_date) AS due_date
            FROM sales_shipments ss
            LEFT JOIN sales_orders so ON so.id = ss.order_id
            JOIN customer_receivables cr
              ON (cr.source_type IN ('sales_shipment', 'shipment') AND cr.source_id = ss.id)
              OR NULLIF(cr.source_no, '') = ss.shipment_no
            GROUP BY ss.id
        ),
        receivable_by_order AS (
            SELECT
                so.id AS order_id,
                SUM(COALESCE(cr.total_amount, cr.expected_amount, 0)) AS order_receivable_amount,
                SUM(COALESCE(cr.received_amount, cr.confirmed_amount, 0)) AS order_received_amount,
                SUM(COALESCE(cr.balance, 0)) AS order_receivable_balance
            FROM sales_orders so
            JOIN customer_receivables cr
              ON (cr.source_type IN ('sales_order', 'order') AND cr.source_id = so.id)
              OR NULLIF(cr.source_no, '') = so.order_no
            GROUP BY so.id
        )
        SELECT
            ss.id AS shipment_id,
            ss.shipment_no,
            ss.shipment_date,
            ss.status,
            ss.signoff_status,
            ss.logistics_provider,
            ss.logistics_no,
            COALESCE(ss.inventory_posted, FALSE) AS inventory_posted,
            so.id AS order_id,
            COALESCE(so.order_no, ss.source_no) AS order_no,
            so.order_date,
            so.delivery_date,
            c.name AS customer_name,
            COALESCE(ss.project_code, so.project_code) AS project_code,
            COALESCE(ss.cabinet_no, so.cabinet_no) AS cabinet_no,
            ssi.id AS line_id,
            p.code AS product_code,
            p.name AS product_name,
            p.specification,
            p.unit,
            COALESCE(ssi.quantity, 0) AS shipped_qty,
            COALESCE(ssi.unit_price, ssi.unit_cost, 0) AS unit_price,
            COALESCE(ssi.amount, COALESCE(ssi.quantity, 0) * COALESCE(ssi.unit_price, ssi.unit_cost, 0)) AS line_amount,
            COALESCE(ssi.tax_amount, 0) AS line_tax_amount,
            COALESCE(ssi.amount_with_tax, ssi.amount, COALESCE(ssi.quantity, 0) * COALESCE(ssi.unit_price, ssi.unit_cost, 0)) AS line_amount_with_tax,
            COALESCE(ssi.cost_amount, 0) AS line_cost_amount,
            COALESCE(ss.shipped_amount, 0) AS shipment_amount,
            COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) AS shipment_amount_with_tax,
            COALESCE(inv.invoiced_amount, 0) AS invoiced_amount,
            GREATEST(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) - COALESCE(inv.invoiced_amount, 0), 0) AS uninvoiced_amount,
            COALESCE(ar.receivable_amount, 0) AS receivable_amount,
            COALESCE(ar.received_amount, 0) AS received_amount,
            COALESCE(ar.receivable_balance, 0) AS receivable_balance,
            COALESCE(order_ar.order_receivable_amount, 0) AS order_receivable_reference_amount,
            COALESCE(order_ar.order_received_amount, 0) AS order_received_reference_amount,
            COALESCE(order_ar.order_receivable_balance, 0) AS order_receivable_reference_balance,
            ar.due_date,
            CASE
                WHEN so.delivery_date IS NOT NULL AND ss.shipment_date IS NOT NULL
                THEN ss.shipment_date - so.delivery_date
                ELSE 0
            END AS delivery_delay_days,
            CASE
                WHEN ar.due_date IS NOT NULL AND ar.due_date < CURRENT_DATE
                     AND COALESCE(ar.receivable_balance, 0) > 0
                THEN CURRENT_DATE - ar.due_date
                ELSE 0
            END AS receivable_overdue_days
        FROM sales_shipments ss
        LEFT JOIN sales_orders so ON so.id = ss.order_id
        LEFT JOIN customers c ON c.id = COALESCE(ss.customer_id, so.customer_id)
        LEFT JOIN sales_shipment_items ssi ON ssi.shipment_id = ss.id
        LEFT JOIN products p ON p.id = ssi.product_id
        LEFT JOIN invoice_by_shipment inv ON inv.shipment_id = ss.id
        LEFT JOIN receivable_by_shipment ar ON ar.shipment_id = ss.id
        LEFT JOIN receivable_by_order order_ar ON order_ar.order_id = so.id
        WHERE {" AND ".join(where)}
        ORDER BY ss.shipment_date DESC NULLS LAST, ss.shipment_no DESC, ssi.id
        LIMIT 1000
    """
    rows = [dict(row) for row in query_db(sql, (VOID_STATUSES, *where_params))]
    for row in rows:
        row["status_label"] = _status_text(row.get("status"))
        row["shipment_url"] = f"/shipments/{row['shipment_id']}" if row.get("shipment_id") else ""
        row["order_url"] = f"/sales/{row['order_id']}" if row.get("order_id") else ""
        row["invoice_rate"] = _percent(row.get("invoiced_amount"), row.get("shipment_amount_with_tax"))
        row["receipt_rate"] = _percent(row.get("received_amount"), row.get("shipment_amount_with_tax"))
        row["execution_note"] = "已过账" if row.get("inventory_posted") else "未见库存过账标记"

    shipment_totals = {}
    for row in rows:
        shipment_id = row.get("shipment_id")
        if shipment_id not in shipment_totals:
            shipment_totals[shipment_id] = row
    line_amount = sum(_decimal(row.get("line_amount_with_tax")) for row in rows)
    line_cost = sum(_decimal(row.get("line_cost_amount")) for row in rows)
    shipment_amount = sum(_decimal(row.get("shipment_amount_with_tax")) for row in shipment_totals.values())
    invoiced_amount = sum(_decimal(row.get("invoiced_amount")) for row in shipment_totals.values())
    received_amount = sum(_decimal(row.get("received_amount")) for row in shipment_totals.values())
    summary = {
        "shipment_count": len(shipment_totals),
        "line_count": len(rows),
        "total_shipped_qty": _qty(sum(_decimal(row.get("shipped_qty")) for row in rows)),
        "line_amount_with_tax": _money(line_amount),
        "shipment_amount_with_tax": _money(shipment_amount),
        "line_cost_amount": _money(line_cost),
        "invoiced_amount": _money(invoiced_amount),
        "uninvoiced_amount": _money(max(shipment_amount - invoiced_amount, Decimal("0"))),
        "received_amount": _money(received_amount),
        "unreceived_amount": _money(max(shipment_amount - received_amount, Decimal("0"))),
        "order_receivable_reference_amount": _money(
            sum(_decimal(row.get("order_receivable_reference_amount")) for row in shipment_totals.values())
        ),
        "cost_basis": "成本金额仅取 sales_shipment_items.cost_amount；为空时不从库存表补算。",
    }
    columns = _columns(
        ("shipment_no", "发货单号", {"url_key": "shipment_url"}),
        ("shipment_date", "发货日期", {}),
        ("order_no", "销售订单", {"url_key": "order_url"}),
        ("customer_name", "客户", {}),
        ("project_code", "项目号", {}),
        ("cabinet_no", "柜号", {}),
        ("product_code", "物料编码", {}),
        ("product_name", "物料名称", {}),
        ("specification", "规格型号", {}),
        ("unit", "单位", {}),
        ("shipped_qty", "发货数量", {"align": "right", "format": "qty"}),
        ("unit_price", "单价", {"align": "right", "format": "money"}),
        ("line_amount_with_tax", "行含税金额", {"align": "right", "format": "money"}),
        ("line_cost_amount", "行成本金额", {"align": "right", "format": "money"}),
        ("shipment_amount_with_tax", "发货单含税金额", {"align": "right", "format": "money"}),
        ("invoiced_amount", "已开票金额", {"align": "right", "format": "money"}),
        ("uninvoiced_amount", "未开票金额", {"align": "right", "format": "money"}),
        ("received_amount", "已收款金额", {"align": "right", "format": "money"}),
        ("receivable_balance", "应收余额", {"align": "right", "format": "money"}),
        ("order_receivable_reference_amount", "订单级应收参考", {"align": "right", "format": "money"}),
        ("order_receivable_reference_balance", "订单级余额参考", {"align": "right", "format": "money"}),
        ("delivery_delay_days", "交付偏差天数", {"align": "right"}),
        ("status_label", "发货状态", {}),
        ("execution_note", "库存影响", {}),
    )
    return {
        "filters": _base_filter_state(filters, "shipment_execution_detail"),
        "summary": summary,
        "columns": columns,
        "rows": rows,
    }


def query_shipped_goods_detail(query_db, filters=None):
    """Issued goods detail using shipment-to-invoice settlement basis.

    A shipment is treated as issued goods until matched sales invoices cover the
    shipment amount. Because existing sales invoices have no product lines, line
    settlement is allocated by each shipment line's amount ratio.
    """
    filters = _clean_filters(filters)
    where = ["COALESCE(ss.status, '') NOT IN %s"]
    where_params = [VOID_STATUSES]
    _add_common_shipment_filters(where, where_params, filters)
    _add_product_filter(where, where_params, filters)
    if filters.get("only_open"):
        where.append("GREATEST(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) - COALESCE(inv.invoiced_amount, 0), 0) > 0")

    sql = f"""
        WITH invoice_by_shipment AS (
            SELECT
                ss.id AS shipment_id,
                SUM(COALESCE(si.amount_with_tax, si.total_amount, si.amount, 0)) AS invoiced_amount,
                MAX(si.invoice_date) AS last_invoice_date,
                STRING_AGG(DISTINCT si.invoice_no, ', ' ORDER BY si.invoice_no) AS invoice_nos
            FROM sales_shipments ss
            JOIN sales_invoices si
              ON (si.source_type IN ('sales_shipment', 'shipment') AND si.source_id = ss.id)
              OR NULLIF(si.source_no, '') = ss.shipment_no
            WHERE COALESCE(si.status, '') NOT IN %s
            GROUP BY ss.id
        )
        SELECT
            ss.id AS shipment_id,
            ss.shipment_no,
            ss.shipment_date,
            COALESCE(inv.last_invoice_date, NULL) AS settlement_date,
            COALESCE(inv.invoice_nos, '') AS settlement_no,
            so.id AS order_id,
            COALESCE(so.order_no, ss.source_no) AS order_no,
            c.name AS customer_name,
            COALESCE(ss.project_code, so.project_code) AS project_code,
            COALESCE(ss.cabinet_no, so.cabinet_no) AS cabinet_no,
            p.code AS product_code,
            p.name AS product_name,
            p.specification,
            p.unit,
            COALESCE(ssi.quantity, 0) AS shipped_qty,
            COALESCE(ssi.amount_with_tax, ssi.amount, COALESCE(ssi.quantity, 0) * COALESCE(ssi.unit_price, ssi.unit_cost, 0)) AS shipped_line_amount,
            COALESCE(ssi.cost_amount, 0) AS shipped_cost_amount,
            COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) AS shipment_amount_with_tax,
            COALESCE(inv.invoiced_amount, 0) AS settled_amount,
            CASE
                WHEN COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) > 0
                THEN LEAST(
                    COALESCE(ssi.amount_with_tax, ssi.amount, 0),
                    COALESCE(ssi.amount_with_tax, ssi.amount, 0)
                    * COALESCE(inv.invoiced_amount, 0)
                    / COALESCE(NULLIF(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0), 0), 1)
                )
                ELSE 0
            END AS line_settled_amount,
            GREATEST(
                COALESCE(ssi.amount_with_tax, ssi.amount, 0)
                - CASE
                    WHEN COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) > 0
                    THEN LEAST(
                        COALESCE(ssi.amount_with_tax, ssi.amount, 0),
                        COALESCE(ssi.amount_with_tax, ssi.amount, 0)
                        * COALESCE(inv.invoiced_amount, 0)
                        / COALESCE(NULLIF(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0), 0), 1)
                    )
                    ELSE 0
                  END,
                0
            ) AS line_open_amount,
            CASE
                WHEN COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) > 0
                THEN COALESCE(ssi.quantity, 0)
                     * LEAST(COALESCE(inv.invoiced_amount, 0), COALESCE(ss.amount_with_tax, ss.shipped_amount, 0))
                     / COALESCE(NULLIF(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0), 0), 1)
                ELSE 0
            END AS settled_qty_basis,
            ss.status
        FROM sales_shipments ss
        LEFT JOIN sales_orders so ON so.id = ss.order_id
        LEFT JOIN customers c ON c.id = COALESCE(ss.customer_id, so.customer_id)
        LEFT JOIN sales_shipment_items ssi ON ssi.shipment_id = ss.id
        LEFT JOIN products p ON p.id = ssi.product_id
        LEFT JOIN invoice_by_shipment inv ON inv.shipment_id = ss.id
        WHERE {" AND ".join(where)}
        ORDER BY ss.shipment_date DESC NULLS LAST, ss.shipment_no DESC, ssi.id
        LIMIT 1000
    """
    rows = [dict(row) for row in query_db(sql, (VOID_STATUSES, *where_params))]
    for row in rows:
        row["shipment_url"] = f"/shipments/{row['shipment_id']}" if row.get("shipment_id") else ""
        row["order_url"] = f"/sales/{row['order_id']}" if row.get("order_id") else ""
        row["open_qty_basis"] = max(_decimal(row.get("shipped_qty")) - _decimal(row.get("settled_qty_basis")), Decimal("0"))
        row["status_label"] = _status_text(row.get("status"))
        row["settlement_basis_note"] = "按发货金额比例分摊开票结转"

    summary = {
        "line_count": len(rows),
        "shipment_count": len({row.get("shipment_id") for row in rows if row.get("shipment_id")}),
        "total_shipped_qty": _qty(sum(_decimal(row.get("shipped_qty")) for row in rows)),
        "total_shipped_amount": _money(sum(_decimal(row.get("shipped_line_amount")) for row in rows)),
        "total_settled_amount": _money(sum(_decimal(row.get("line_settled_amount")) for row in rows)),
        "total_open_amount": _money(sum(_decimal(row.get("line_open_amount")) for row in rows)),
        "total_cost_amount": _money(sum(_decimal(row.get("shipped_cost_amount")) for row in rows)),
        "settlement_basis": "发出商品结转按销售发票匹配到发货单的含税金额分摊；发票无行项目，数量结转为金额比例口径。",
    }
    columns = _columns(
        ("shipment_no", "发货单号", {"url_key": "shipment_url"}),
        ("shipment_date", "发货日期", {}),
        ("settlement_date", "结转日期", {}),
        ("settlement_no", "结转单号", {}),
        ("order_no", "销售订单", {"url_key": "order_url"}),
        ("customer_name", "客户", {}),
        ("project_code", "项目号", {}),
        ("cabinet_no", "柜号", {}),
        ("product_code", "物料编码", {}),
        ("product_name", "物料名称", {}),
        ("specification", "规格型号", {}),
        ("unit", "单位", {}),
        ("shipped_qty", "本期发出数量", {"align": "right", "format": "qty"}),
        ("shipped_line_amount", "本期发出金额", {"align": "right", "format": "money"}),
        ("settled_qty_basis", "本期结转数量口径", {"align": "right", "format": "qty"}),
        ("line_settled_amount", "本期结转金额", {"align": "right", "format": "money"}),
        ("open_qty_basis", "未结数量口径", {"align": "right", "format": "qty"}),
        ("line_open_amount", "未结金额", {"align": "right", "format": "money"}),
        ("shipped_cost_amount", "发货成本金额", {"align": "right", "format": "money"}),
        ("status_label", "发货状态", {}),
        ("settlement_basis_note", "结转口径", {}),
    )
    return {
        "filters": _base_filter_state(filters, "shipped_goods_detail"),
        "summary": summary,
        "columns": columns,
        "rows": rows,
    }


def query_shipped_goods_summary(query_db, filters=None):
    """Issued goods summary by product.

    The summary uses the same settlement basis as shipped goods detail and
    groups by product/project/cabinet/customer when filter values are present.
    """
    detail = query_shipped_goods_detail(query_db, filters)
    buckets = {}
    for row in detail["rows"]:
        key = (
            row.get("product_code") or "",
            row.get("product_name") or "",
            row.get("specification") or "",
            row.get("unit") or "",
            row.get("customer_name") or "",
            row.get("project_code") or "",
            row.get("cabinet_no") or "",
        )
        bucket = buckets.setdefault(
            key,
            {
                "product_code": row.get("product_code"),
                "product_name": row.get("product_name"),
                "specification": row.get("specification"),
                "unit": row.get("unit"),
                "customer_name": row.get("customer_name"),
                "project_code": row.get("project_code"),
                "cabinet_no": row.get("cabinet_no"),
                "shipment_count": 0,
                "period_shipped_qty": Decimal("0"),
                "period_shipped_amount": Decimal("0"),
                "period_settled_qty_basis": Decimal("0"),
                "period_settled_amount": Decimal("0"),
                "ending_open_qty_basis": Decimal("0"),
                "ending_open_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
            },
        )
        bucket["shipment_count"] += 1
        bucket["period_shipped_qty"] += _decimal(row.get("shipped_qty"))
        bucket["period_shipped_amount"] += _decimal(row.get("shipped_line_amount"))
        bucket["period_settled_qty_basis"] += _decimal(row.get("settled_qty_basis"))
        bucket["period_settled_amount"] += _decimal(row.get("line_settled_amount"))
        bucket["ending_open_qty_basis"] += _decimal(row.get("open_qty_basis"))
        bucket["ending_open_amount"] += _decimal(row.get("line_open_amount"))
        bucket["cost_amount"] += _decimal(row.get("shipped_cost_amount"))

    rows = sorted(
        buckets.values(),
        key=lambda item: (_decimal(item.get("ending_open_amount")), _decimal(item.get("period_shipped_amount"))),
        reverse=True,
    )
    summary = {
        "product_count": len(rows),
        "shipment_line_count": detail["summary"]["line_count"],
        "total_shipped_qty": _qty(sum(_decimal(row.get("period_shipped_qty")) for row in rows)),
        "total_shipped_amount": _money(sum(_decimal(row.get("period_shipped_amount")) for row in rows)),
        "total_settled_amount": _money(sum(_decimal(row.get("period_settled_amount")) for row in rows)),
        "total_open_amount": _money(sum(_decimal(row.get("ending_open_amount")) for row in rows)),
        "total_cost_amount": _money(sum(_decimal(row.get("cost_amount")) for row in rows)),
        "settlement_basis": detail["summary"]["settlement_basis"],
    }
    columns = _columns(
        ("product_code", "物料编码", {}),
        ("product_name", "物料名称", {}),
        ("specification", "规格型号", {}),
        ("unit", "基本单位", {}),
        ("customer_name", "客户", {}),
        ("project_code", "项目号", {}),
        ("cabinet_no", "柜号", {}),
        ("shipment_count", "发货行数", {"align": "right"}),
        ("period_shipped_qty", "本期发出数量", {"align": "right", "format": "qty"}),
        ("period_shipped_amount", "本期发出金额", {"align": "right", "format": "money"}),
        ("period_settled_qty_basis", "本期结转数量口径", {"align": "right", "format": "qty"}),
        ("period_settled_amount", "本期结转金额", {"align": "right", "format": "money"}),
        ("ending_open_qty_basis", "期末未结数量口径", {"align": "right", "format": "qty"}),
        ("ending_open_amount", "期末未结金额", {"align": "right", "format": "money"}),
        ("cost_amount", "发货成本金额", {"align": "right", "format": "money"}),
    )
    return {
        "filters": detail["filters"] | {"report_type": "shipped_goods_summary"},
        "summary": summary,
        "columns": columns,
        "rows": rows,
    }


REPORT_BUILDERS = {
    "shipment_execution_detail": query_shipment_execution_detail,
    "shipped_goods_detail": query_shipped_goods_detail,
    "shipped_goods_summary": query_shipped_goods_summary,
}


def build_sales_shipment_report(query_db, report_type, filters=None):
    """Build one Agent 2 sales shipment report payload."""
    builder = REPORT_BUILDERS.get(report_type)
    if not builder:
        raise ValueError(f"Unsupported sales shipment report type: {report_type}")
    return builder(query_db, filters)
