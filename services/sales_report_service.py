"""Read-only sales report query services."""
from decimal import Decimal
from datetime import datetime


AGING_BUCKETS = ("未到期", "1-30天", "31-60天", "61-90天", "91-180天", "180天以上")
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


def as_decimal_safe(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def calculate_aging_days(due_date):
    if not due_date:
        return 0
    try:
        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
        delta = datetime.now().date() - due_date
        return max(0, delta.days)
    except Exception:
        return 0


def get_aging_range(days):
    if days <= 0:
        return "未到期"
    if days <= 30:
        return "1-30天"
    if days <= 60:
        return "31-60天"
    if days <= 90:
        return "61-90天"
    if days <= 180:
        return "91-180天"
    return "180天以上"


def _add_common_filters(where_clauses, params, table_alias, filters):
    if filters.get("customer_name"):
        where_clauses.append("c.name ILIKE %s")
        params.append(f"%{filters['customer_name']}%")
    if filters.get("customer_id"):
        where_clauses.append(f"{table_alias}.customer_id = %s")
        params.append(filters["customer_id"])
    if filters.get("project_code"):
        where_clauses.append(f"{table_alias}.project_code ILIKE %s")
        params.append(f"%{filters['project_code']}%")
    if filters.get("serial_no"):
        where_clauses.append(f"{table_alias}.serial_no ILIKE %s")
        params.append(f"%{filters['serial_no']}%")


def query_sales_order_execution_detail(query_db, filters=None):
    """Sales order to shipment, invoice, receipt execution detail."""
    filters = filters or {}
    where_clauses = ["1=1"]
    params = []

    if filters.get("date_start"):
        where_clauses.append("so.order_date >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where_clauses.append("so.order_date <= %s")
        params.append(filters["date_end"])
    _add_common_filters(where_clauses, params, "so", filters)
    if filters.get("status"):
        where_clauses.append("so.status = %s")
        params.append(filters["status"])

    sql = f"""
        WITH order_qty AS (
            SELECT order_id, SUM(COALESCE(quantity, 0)) AS order_qty
            FROM sales_order_items
            GROUP BY order_id
        ),
        shipment_line_amount AS (
            SELECT
                ss.id AS shipment_id,
                ss.order_id,
                SUM(COALESCE(ssi.quantity, 0)) AS shipped_qty,
                SUM(COALESCE(ssi.amount_with_tax, ssi.amount, 0)) AS line_amount
            FROM sales_shipments ss
            LEFT JOIN sales_shipment_items ssi ON ss.id = ssi.shipment_id
            WHERE COALESCE(ss.status, '') NOT IN %s
            GROUP BY ss.id, ss.order_id
        ),
        shipped AS (
            SELECT
                ss.order_id,
                SUM(COALESCE(sla.shipped_qty, 0)) AS shipped_qty,
                SUM(
                    CASE
                        WHEN COALESCE(sla.line_amount, 0) > 0 THEN COALESCE(sla.line_amount, 0)
                        ELSE COALESCE(ss.amount_with_tax, ss.shipped_amount, 0)
                    END
                ) AS shipped_amount
            FROM sales_shipments ss
            LEFT JOIN shipment_line_amount sla ON sla.shipment_id = ss.id
            WHERE COALESCE(ss.status, '') NOT IN %s
            GROUP BY ss.order_id
        ),
        invoiced AS (
            SELECT
                COALESCE(order_id, CASE WHEN source_type = 'sales_order' THEN source_id END) AS order_id,
                SUM(COALESCE(amount_with_tax, total_amount, amount, 0)) AS invoiced_amount
            FROM sales_invoices
            WHERE COALESCE(status, '') NOT IN %s
              AND COALESCE(order_id, CASE WHEN source_type = 'sales_order' THEN source_id END) IS NOT NULL
            GROUP BY COALESCE(order_id, CASE WHEN source_type = 'sales_order' THEN source_id END)
        ),
        received AS (
            SELECT
                ar.source_id AS order_id,
                SUM(COALESCE(cr.amount, 0)) AS received_amount
            FROM customer_receipts cr
            JOIN customer_receivables ar
              ON ar.id = cr.receivable_id
              OR (cr.source_type = 'customer_receivable' AND ar.id = cr.source_id)
            WHERE ar.source_type = 'sales_order'
              AND COALESCE(cr.status, '') NOT IN %s
            GROUP BY ar.source_id
        )
        SELECT
            so.id,
            so.order_no,
            so.order_date,
            c.name AS customer_name,
            so.project_code,
            so.serial_no,
            so.status,
            so.delivery_date,
            COALESCE(so.amount_with_tax, so.total_amount, 0) AS order_amount,
            COALESCE(so.tax_amount, 0) AS order_tax_amount,
            COALESCE(shipped.shipped_qty, 0) AS shipped_qty,
            COALESCE(shipped.shipped_amount, so.shipped_amount, 0) AS shipped_amount,
            GREATEST(COALESCE(so.amount_with_tax, so.total_amount, 0) - COALESCE(shipped.shipped_amount, so.shipped_amount, 0), 0) AS unshipped_amount,
            COALESCE(invoiced.invoiced_amount, 0) AS invoiced_amount,
            GREATEST(COALESCE(shipped.shipped_amount, so.shipped_amount, 0) - COALESCE(invoiced.invoiced_amount, 0), 0) AS uninvoiced_amount,
            COALESCE(received.received_amount, 0) AS received_amount,
            GREATEST(COALESCE(so.amount_with_tax, so.total_amount, 0) - COALESCE(received.received_amount, 0), 0) AS unreceived_amount,
            CASE
                WHEN so.delivery_date < CURRENT_DATE
                 AND COALESCE(shipped.shipped_qty, 0) < COALESCE(order_qty.order_qty, 0)
                THEN CURRENT_DATE - so.delivery_date
                ELSE 0
            END AS overdue_days,
            so.remark
        FROM sales_orders so
        LEFT JOIN customers c ON so.customer_id = c.id
        LEFT JOIN order_qty ON so.id = order_qty.order_id
        LEFT JOIN shipped ON so.id = shipped.order_id
        LEFT JOIN invoiced ON so.id = invoiced.order_id
        LEFT JOIN received ON so.id = received.order_id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY so.order_date DESC, so.order_no DESC
    """

    rows = query_db(sql, (VOID_STATUSES, VOID_STATUSES, VOID_STATUSES, VOID_STATUSES, *params))
    for row in rows:
        order_amt = as_decimal_safe(row.get("order_amount"))
        shipped_amt = as_decimal_safe(row.get("shipped_amount"))
        row["shipment_rate"] = f"{(shipped_amt / order_amt * 100):.1f}%" if order_amt > 0 else "0%"
        row["is_overdue"] = row.get("overdue_days", 0) > 0
        row["order_url"] = f"/sales/{row['id']}"
    return rows


def query_receivable_aging_analysis(query_db, filters=None):
    """Open customer receivable aging detail."""
    filters = filters or {}
    where_clauses = ["COALESCE(cr.balance, 0) > 0"]
    params = []
    _add_common_filters(where_clauses, params, "cr", filters)

    range_map = {
        "not_due": "cr.due_date >= CURRENT_DATE",
        "1_30": "cr.due_date < CURRENT_DATE AND cr.due_date >= CURRENT_DATE - 30",
        "31_60": "cr.due_date < CURRENT_DATE - 30 AND cr.due_date >= CURRENT_DATE - 60",
        "61_90": "cr.due_date < CURRENT_DATE - 60 AND cr.due_date >= CURRENT_DATE - 90",
        "91_180": "cr.due_date < CURRENT_DATE - 90 AND cr.due_date >= CURRENT_DATE - 180",
        "over_180": "cr.due_date < CURRENT_DATE - 180",
    }
    if filters.get("aging_range") in range_map:
        where_clauses.append(range_map[filters["aging_range"]])

    sql = f"""
        SELECT
            cr.id,
            COALESCE(cr.source_no, 'AR-' || cr.id::text) AS receivable_no,
            c.name AS customer_name,
            c.id AS customer_id,
            cr.project_code,
            cr.serial_no,
            cr.source_type,
            cr.source_no,
            cr.receivable_date AS source_date,
            cr.due_date,
            COALESCE(cr.total_amount, cr.expected_amount, 0) AS original_amount,
            COALESCE(cr.received_amount, cr.confirmed_amount, 0) AS received_amount,
            COALESCE(cr.balance, 0) AS balance,
            CASE
                WHEN cr.due_date IS NULL OR cr.due_date >= CURRENT_DATE THEN 0
                ELSE CURRENT_DATE - cr.due_date
            END AS aging_days,
            CASE
                WHEN cr.due_date IS NULL OR cr.due_date >= CURRENT_DATE THEN '未到期'
                WHEN CURRENT_DATE - cr.due_date <= 30 THEN '1-30天'
                WHEN CURRENT_DATE - cr.due_date <= 60 THEN '31-60天'
                WHEN CURRENT_DATE - cr.due_date <= 90 THEN '61-90天'
                WHEN CURRENT_DATE - cr.due_date <= 180 THEN '91-180天'
                ELSE '180天以上'
            END AS aging_range,
            cr.remark
        FROM customer_receivables cr
        LEFT JOIN customers c ON cr.customer_id = c.id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY
            CASE WHEN cr.due_date < CURRENT_DATE THEN 0 ELSE 1 END,
            cr.due_date ASC NULLS LAST,
            cr.balance DESC
    """

    rows = query_db(sql, tuple(params))
    for row in rows:
        days = row.get("aging_days", 0)
        if days > 180:
            row["risk_level"] = "高风险"
            row["risk_class"] = "danger"
        elif days > 90:
            row["risk_level"] = "中风险"
            row["risk_class"] = "warning"
        elif days > 0:
            row["risk_level"] = "低风险"
            row["risk_class"] = "info"
        else:
            row["risk_level"] = "正常"
            row["risk_class"] = "success"
        row["receivable_url"] = f"/receivables/{row['id']}"
        row["customer_url"] = f"/customer?id={row['customer_id']}" if row.get("customer_id") else ""
    return rows


def query_project_serial_sales_tracking(query_db, filters=None):
    """Project/serial sales order trace across shipment, receivable, and service cards."""
    filters = filters or {}
    where_clauses = ["(NULLIF(so.project_code, '') IS NOT NULL OR NULLIF(so.serial_no, '') IS NOT NULL)"]
    params = []
    _add_common_filters(where_clauses, params, "so", filters)

    sql = f"""
        WITH shipped AS (
            SELECT order_id, COUNT(*) AS shipment_count, SUM(COALESCE(amount_with_tax, shipped_amount, 0)) AS shipped_amount
            FROM sales_shipments
            WHERE COALESCE(status, '') NOT IN ('cancelled', 'voided', '已作废', '已取消')
            GROUP BY order_id
        ),
        receivable AS (
            SELECT source_id AS order_id, SUM(COALESCE(balance, 0)) AS receivable_balance
            FROM customer_receivables
            WHERE source_type = 'sales_order' AND COALESCE(balance, 0) > 0
            GROUP BY source_id
        ),
        service_by_order AS (
            SELECT sales_order_id AS order_id, COUNT(DISTINCT id) AS service_card_count
            FROM machine_service_cards
            WHERE sales_order_id IS NOT NULL
            GROUP BY sales_order_id
        ),
        service_by_trace AS (
            SELECT project_code, serial_no, COUNT(DISTINCT id) AS service_card_count
            FROM machine_service_cards
            GROUP BY project_code, serial_no
        )
        SELECT
            so.project_code,
            so.serial_no,
            c.name AS customer_name,
            so.order_no,
            so.order_date,
            COALESCE(so.amount_with_tax, so.total_amount, 0) AS order_amount,
            so.status AS order_status,
            COALESCE(shipped.shipment_count, 0) AS shipment_count,
            COALESCE(shipped.shipped_amount, so.shipped_amount, 0) AS shipped_amount,
            COALESCE(receivable.receivable_balance, 0) AS receivable_balance,
            COALESCE(service_by_order.service_card_count, service_by_trace.service_card_count, 0) AS service_card_count,
            so.id AS order_id
        FROM sales_orders so
        LEFT JOIN customers c ON so.customer_id = c.id
        LEFT JOIN shipped ON so.id = shipped.order_id
        LEFT JOIN receivable ON so.id = receivable.order_id
        LEFT JOIN service_by_order ON so.id = service_by_order.order_id
        LEFT JOIN service_by_trace
          ON so.project_code IS NOT DISTINCT FROM service_by_trace.project_code
         AND so.serial_no IS NOT DISTINCT FROM service_by_trace.serial_no
        WHERE {" AND ".join(where_clauses)}
        ORDER BY so.project_code, so.serial_no, so.order_date DESC
    """

    rows = query_db(sql, tuple(params))
    for row in rows:
        row["order_url"] = f"/sales/{row['order_id']}"
    return rows


def query_shipped_unsettled_detail(query_db, filters=None):
    """Shipments with uninvoiced or unreceived balance."""
    filters = filters or {}
    where_clauses = ["COALESCE(ss.status, '') NOT IN ('cancelled', 'voided', '已作废', '已取消')"]
    params = []

    if filters.get("date_start"):
        where_clauses.append("ss.shipment_date >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where_clauses.append("ss.shipment_date <= %s")
        params.append(filters["date_end"])
    _add_common_filters(where_clauses, params, "ss", filters)

    unsettled_filter = ""
    if filters.get("unsettled_type") == "uninvoiced":
        unsettled_filter = "AND uninvoiced_amount > 0"
    elif filters.get("unsettled_type") == "unreceived":
        unsettled_filter = "AND unreceived_amount > 0"

    sql = f"""
        WITH invoiced AS (
            SELECT
                CASE
                    WHEN source_type = 'sales_shipment' THEN source_id
                    ELSE NULL
                END AS shipment_id,
                source_no,
                SUM(COALESCE(amount_with_tax, total_amount, amount, 0)) AS invoiced_amount
            FROM sales_invoices
            WHERE COALESCE(status, '') NOT IN ('cancelled', 'voided', '已作废', '已取消')
            GROUP BY
                CASE WHEN source_type = 'sales_shipment' THEN source_id ELSE NULL END,
                source_no
        ),
        received AS (
            SELECT
                ar.source_id AS shipment_id,
                SUM(COALESCE(cr.amount, 0)) AS received_amount
            FROM customer_receipts cr
            JOIN customer_receivables ar
              ON ar.id = cr.receivable_id
              OR (cr.source_type = 'customer_receivable' AND ar.id = cr.source_id)
            WHERE ar.source_type = 'sales_shipment'
              AND COALESCE(cr.status, '') NOT IN ('cancelled', 'voided', '已作废', '已取消')
            GROUP BY ar.source_id
        ),
        base AS (
            SELECT
                ss.id,
                ss.shipment_no,
                ss.shipment_date,
                c.name AS customer_name,
                so.order_no,
                ss.project_code,
                ss.serial_no,
                COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) AS shipped_amount,
                COALESCE(inv_by_id.invoiced_amount, inv_by_no.invoiced_amount, 0) AS invoiced_amount,
                GREATEST(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) - COALESCE(inv_by_id.invoiced_amount, inv_by_no.invoiced_amount, 0), 0) AS uninvoiced_amount,
                COALESCE(received.received_amount, 0) AS received_amount,
                GREATEST(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0) - COALESCE(received.received_amount, 0), 0) AS unreceived_amount,
                CASE WHEN ss.shipment_date IS NULL THEN 0 ELSE CURRENT_DATE - ss.shipment_date END AS aging_days
            FROM sales_shipments ss
            LEFT JOIN customers c ON ss.customer_id = c.id
            LEFT JOIN sales_orders so ON ss.order_id = so.id
            LEFT JOIN invoiced inv_by_id ON ss.id = inv_by_id.shipment_id
            LEFT JOIN invoiced inv_by_no ON ss.shipment_no = inv_by_no.source_no
            LEFT JOIN received ON ss.id = received.shipment_id
            WHERE {" AND ".join(where_clauses)}
        )
        SELECT *,
            CASE
                WHEN unreceived_amount > 0 AND aging_days >= 180 THEN '长期未收款'
                WHEN uninvoiced_amount > 0 AND aging_days >= 90 THEN '长期未开票'
                WHEN unreceived_amount > 0 THEN '未收款'
                WHEN uninvoiced_amount > 0 THEN '未开票'
                ELSE '正常'
            END AS alert_status
        FROM base
        WHERE (uninvoiced_amount > 0 OR unreceived_amount > 0)
        {unsettled_filter}
        ORDER BY shipment_date ASC NULLS LAST, shipment_no
    """

    rows = query_db(sql, tuple(params))
    for row in rows:
        row["shipment_url"] = f"/shipments/{row['id']}"
    return rows
