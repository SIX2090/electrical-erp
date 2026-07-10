"""Read-only sales receivable and collection report services."""
from decimal import Decimal


def _money(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _filters(args=None):
    args = args or {}
    getter = args.get if hasattr(args, "get") else lambda key, default=None: default
    return {
        "date_start": (getter("date_start") or getter("start_date") or "").strip(),
        "date_end": (getter("date_end") or getter("end_date") or "").strip(),
        "customer_name": (getter("customer_name") or getter("customer") or "").strip(),
        "project_code": (getter("project_code") or getter("project") or "").strip(),
        "cabinet_no": (getter("cabinet_no") or "").strip(),
        "source_no": (getter("source_no") or "").strip(),
        "status": (getter("status") or "").strip(),
        "only_overdue": (getter("only_overdue") or "").strip(),
        "only_open": (getter("only_open") or "").strip(),
        "only_unapplied": (getter("only_unapplied") or "").strip(),
        "limit": _safe_limit(getter("limit") or getter("page_size") or 300),
    }


def _safe_limit(value):
    try:
        return max(1, min(int(value), 1000))
    except Exception:
        return 300


def _append_common_filters(where, params, filters, date_alias):
    if filters.get("date_start"):
        where.append(f"{date_alias} >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where.append(f"{date_alias} <= %s")
        params.append(filters["date_end"])
    if filters.get("customer_name"):
        where.append("c.name ILIKE %s")
        params.append(f"%{filters['customer_name']}%")
    if filters.get("project_code"):
        where.append("COALESCE(cr.project_code, r.project_code, so.project_code, ss.project_code, '') ILIKE %s")
        params.append(f"%{filters['project_code']}%")
    if filters.get("cabinet_no"):
        where.append("COALESCE(cr.cabinet_no, r.cabinet_no, so.cabinet_no, ss.cabinet_no, '') ILIKE %s")
        params.append(f"%{filters['cabinet_no']}%")
    if filters.get("source_no"):
        where.append("COALESCE(cr.source_no, r.source_no, so.order_no, ss.shipment_no, r.receipt_no, '') ILIKE %s")
        params.append(f"%{filters['source_no']}%")
    if filters.get("status"):
        where.append("COALESCE(r.status, cr.status, '') = %s")
        params.append(filters["status"])


def _aging_bucket_expr(alias="cr"):
    return f"""
        CASE
            WHEN {alias}.due_date IS NULL OR {alias}.due_date >= CURRENT_DATE THEN '未到期'
            WHEN CURRENT_DATE - {alias}.due_date <= 30 THEN '1-30天'
            WHEN CURRENT_DATE - {alias}.due_date <= 60 THEN '31-60天'
            WHEN CURRENT_DATE - {alias}.due_date <= 90 THEN '61-90天'
            WHEN CURRENT_DATE - {alias}.due_date <= 180 THEN '91-180天'
            ELSE '180天以上'
        END
    """


def query_receivable_collection_detail(query_rows, args=None):
    """Sales collection execution detail.

    Basis: receipt settlement rows are preferred. Receipts without settlement rows
    are still shown as customer receipt records, linked to receivables only when
    an existing direct receipt-to-receivable reference is available.
    """
    filters = _filters(args)
    where = []
    params = []
    _append_common_filters(where, params, filters, "r.receipt_date")
    if filters.get("only_unapplied"):
        where.append("COALESCE(r.unapplied_amount, r.amount, 0) > 0")
    where_sql = " AND ".join(where) if where else "1=1"

    sql = f"""
        WITH receipt_base AS (
            SELECT
                r.id AS receipt_id,
                r.receipt_no,
                r.receipt_date,
                r.customer_id,
                r.amount AS receipt_amount,
                r.unapplied_amount,
                r.payment_method,
                r.bank_account,
                r.status AS receipt_status,
                r.source_type AS receipt_source_type,
                r.source_id AS receipt_source_id,
                r.source_no AS receipt_source_no,
                r.receivable_id AS direct_receivable_id,
                r.project_code AS receipt_project_code,
                r.cabinet_no AS receipt_cabinet_no
            FROM customer_receipts r
        ),
        settlement_rows AS (
            SELECT
                rb.receipt_id,
                rb.receipt_no,
                rb.receipt_date,
                rb.customer_id,
                rb.receipt_amount,
                rb.unapplied_amount,
                rb.payment_method,
                rb.bank_account,
                rb.receipt_status,
                s.id AS settlement_id,
                s.applied_amount AS collection_amount,
                cr.id AS receivable_id,
                cr.source_type,
                cr.source_id,
                cr.source_no,
                cr.receivable_date,
                cr.due_date,
                cr.total_amount AS receivable_amount,
                cr.received_amount,
                cr.balance,
                cr.status AS receivable_status,
                cr.project_code,
                cr.cabinet_no,
                '应收核销关联' AS collection_basis
            FROM receipt_base rb
            JOIN customer_receipt_settlements s ON s.receipt_id = rb.receipt_id
            LEFT JOIN customer_receivables cr ON cr.id = s.receivable_id
        ),
        direct_rows AS (
            SELECT
                rb.receipt_id,
                rb.receipt_no,
                rb.receipt_date,
                rb.customer_id,
                rb.receipt_amount,
                rb.unapplied_amount,
                rb.payment_method,
                rb.bank_account,
                rb.receipt_status,
                NULL::INTEGER AS settlement_id,
                rb.receipt_amount AS collection_amount,
                cr.id AS receivable_id,
                cr.source_type,
                cr.source_id,
                COALESCE(cr.source_no, rb.receipt_source_no) AS source_no,
                cr.receivable_date,
                cr.due_date,
                cr.total_amount AS receivable_amount,
                cr.received_amount,
                cr.balance,
                cr.status AS receivable_status,
                COALESCE(cr.project_code, rb.receipt_project_code) AS project_code,
                COALESCE(cr.cabinet_no, rb.receipt_cabinet_no) AS cabinet_no,
                CASE
                    WHEN cr.id IS NULL THEN '客户收款记录'
                    ELSE '收款单直接关联应收'
                END AS collection_basis
            FROM receipt_base rb
            LEFT JOIN customer_receivables cr
              ON cr.id = rb.direct_receivable_id
              OR (rb.receipt_source_type = 'customer_receivable' AND cr.id = rb.receipt_source_id)
            WHERE NOT EXISTS (
                SELECT 1
                FROM customer_receipt_settlements s
                WHERE s.receipt_id = rb.receipt_id
            )
        ),
        combined AS (
            SELECT * FROM settlement_rows
            UNION ALL
            SELECT * FROM direct_rows
        )
        SELECT
            combined.receipt_id,
            combined.receipt_no,
            combined.receipt_date,
            c.name AS customer_name,
            combined.source_no AS receivable_source_no,
            so.order_no,
            ss.shipment_no,
            combined.receivable_date,
            combined.due_date,
            combined.receivable_amount,
            combined.received_amount,
            combined.balance AS receivable_balance,
            combined.receipt_amount,
            combined.collection_amount,
            combined.unapplied_amount,
            combined.payment_method,
            combined.bank_account,
            combined.project_code,
            combined.cabinet_no,
            combined.receipt_status,
            combined.receivable_status,
            combined.collection_basis,
            CASE
                WHEN combined.due_date IS NULL OR combined.due_date >= CURRENT_DATE THEN 0
                ELSE CURRENT_DATE - combined.due_date
            END AS overdue_days,
            {_aging_bucket_expr("combined")} AS aging_bucket
        FROM combined
        LEFT JOIN customers c ON c.id = combined.customer_id
        LEFT JOIN sales_orders so
          ON combined.source_type = 'sales_order' AND so.id = combined.source_id
        LEFT JOIN sales_shipments ss
          ON combined.source_type = 'sales_shipment' AND ss.id = combined.source_id
        LEFT JOIN customer_receivables cr ON cr.id = combined.receivable_id
        LEFT JOIN customer_receipts r ON r.id = combined.receipt_id
        WHERE {where_sql}
        ORDER BY combined.receipt_date DESC NULLS LAST, combined.receipt_id DESC, combined.settlement_id NULLS LAST
        LIMIT %s
    """
    rows = query_rows(sql, tuple(params + [filters["limit"]]))
    for row in rows:
        row["receipt_url"] = f"/customer-receipts/{row['receipt_id']}" if row.get("receipt_id") else ""
        row["receivable_url"] = f"/receivables/{row['receivable_id']}" if row.get("receivable_id") else ""

    unique_receipts = {}
    for row in rows:
        receipt_id = row.get("receipt_id")
        if receipt_id is not None and receipt_id not in unique_receipts:
            unique_receipts[receipt_id] = row

    summary = {
        "row_count": len(rows),
        "receipt_amount": sum(_money(row.get("receipt_amount")) for row in unique_receipts.values()),
        "collection_amount": sum(_money(row.get("collection_amount")) for row in rows),
        "unapplied_amount": sum(_money(row.get("unapplied_amount")) for row in unique_receipts.values()),
        "open_balance": sum(_money(row.get("receivable_balance")) for row in rows),
    }
    return {
        "filters": filters,
        "summary": summary,
        "columns": collection_detail_columns(),
        "rows": rows,
    }


def query_customer_ranking(query_rows, args=None):
    """Customer ranking by open delivery and open receivable balance."""
    filters = _filters(args)
    where = []
    params = []
    if filters.get("date_start"):
        where.append("so.order_date >= %s")
        params.append(filters["date_start"])
    if filters.get("date_end"):
        where.append("so.order_date <= %s")
        params.append(filters["date_end"])
    if filters.get("customer_name"):
        where.append("c.name ILIKE %s")
        params.append(f"%{filters['customer_name']}%")
    if filters.get("project_code"):
        where.append("COALESCE(so.project_code, '') ILIKE %s")
        params.append(f"%{filters['project_code']}%")
    if filters.get("cabinet_no"):
        where.append("COALESCE(so.cabinet_no, '') ILIKE %s")
        params.append(f"%{filters['cabinet_no']}%")
    if filters.get("status"):
        where.append("COALESCE(so.status, '') = %s")
        params.append(filters["status"])
    where_sql = " AND ".join(where) if where else "1=1"
    having = []
    if filters.get("only_open"):
        having.append("(SUM(open_delivery_amount) > 0 OR SUM(open_receivable_balance) > 0)")
    if filters.get("only_overdue"):
        having.append("(SUM(overdue_order_count) > 0 OR SUM(overdue_receivable_count) > 0)")
    having_sql = f"HAVING {' AND '.join(having)}" if having else ""

    sql = f"""
        WITH shipped AS (
            SELECT
                ss.order_id,
                SUM(COALESCE(ss.amount_with_tax, ss.shipped_amount, 0)) AS shipped_amount,
                COUNT(*) AS shipment_count
            FROM sales_shipments ss
            WHERE ss.order_id IS NOT NULL
            GROUP BY ss.order_id
        ),
        receivable AS (
            SELECT
                customer_id,
                SUM(COALESCE(total_amount, 0)) AS receivable_amount,
                SUM(COALESCE(received_amount, 0)) AS received_amount,
                SUM(COALESCE(balance, 0)) AS open_receivable_balance,
                COUNT(*) FILTER (WHERE COALESCE(balance, 0) > 0) AS open_receivable_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(balance, 0) > 0
                      AND due_date IS NOT NULL
                      AND due_date < CURRENT_DATE
                ) AS overdue_receivable_count,
                MAX(CASE
                    WHEN COALESCE(balance, 0) > 0 AND due_date IS NOT NULL AND due_date < CURRENT_DATE
                    THEN CURRENT_DATE - due_date
                    ELSE 0
                END) AS max_receivable_overdue_days
            FROM customer_receivables
            GROUP BY customer_id
        ),
        order_base AS (
            SELECT
                so.id,
                so.customer_id,
                COALESCE(so.amount_with_tax, so.total_amount, 0) AS order_amount,
                COALESCE(shipped.shipped_amount, so.shipped_amount, 0) AS shipped_amount,
                GREATEST(
                    COALESCE(so.amount_with_tax, so.total_amount, 0)
                    - COALESCE(shipped.shipped_amount, so.shipped_amount, 0),
                    0
                ) AS open_delivery_amount,
                CASE
                    WHEN so.delivery_date IS NOT NULL
                     AND so.delivery_date < CURRENT_DATE
                     AND GREATEST(
                         COALESCE(so.amount_with_tax, so.total_amount, 0)
                         - COALESCE(shipped.shipped_amount, so.shipped_amount, 0),
                         0
                     ) > 0
                    THEN 1
                    ELSE 0
                END AS overdue_order_count,
                CASE
                    WHEN so.delivery_date IS NOT NULL
                     AND so.delivery_date < CURRENT_DATE
                     AND GREATEST(
                         COALESCE(so.amount_with_tax, so.total_amount, 0)
                         - COALESCE(shipped.shipped_amount, so.shipped_amount, 0),
                         0
                     ) > 0
                    THEN CURRENT_DATE - so.delivery_date
                    ELSE 0
                END AS delivery_overdue_days
            FROM sales_orders so
            LEFT JOIN customers c ON c.id = so.customer_id
            LEFT JOIN shipped ON shipped.order_id = so.id
            WHERE {where_sql}
        ),
        customer_orders AS (
            SELECT
                customer_id,
                COUNT(*) AS order_count,
                SUM(order_amount) AS order_amount,
                SUM(shipped_amount) AS shipped_amount,
                SUM(open_delivery_amount) AS open_delivery_amount,
                SUM(overdue_order_count) AS overdue_order_count,
                MAX(delivery_overdue_days) AS max_delivery_overdue_days
            FROM order_base
            GROUP BY customer_id
        ),
        base AS (
            SELECT
                c.id AS customer_id,
                c.name AS customer_name,
                COALESCE(co.order_count, 0) AS order_count,
                COALESCE(co.order_amount, 0) AS order_amount,
                COALESCE(co.shipped_amount, 0) AS shipped_amount,
                COALESCE(co.open_delivery_amount, 0) AS open_delivery_amount,
                COALESCE(co.overdue_order_count, 0) AS overdue_order_count,
                COALESCE(co.max_delivery_overdue_days, 0) AS max_delivery_overdue_days,
                COALESCE(ar.receivable_amount, 0) AS receivable_amount,
                COALESCE(ar.received_amount, 0) AS received_amount,
                COALESCE(ar.open_receivable_balance, 0) AS open_receivable_balance,
                COALESCE(ar.open_receivable_count, 0) AS open_receivable_count,
                COALESCE(ar.overdue_receivable_count, 0) AS overdue_receivable_count,
                COALESCE(ar.max_receivable_overdue_days, 0) AS max_receivable_overdue_days
            FROM customers c
            LEFT JOIN customer_orders co ON co.customer_id = c.id
            LEFT JOIN receivable ar ON ar.customer_id = c.id
            WHERE COALESCE(co.order_count, 0) > 0 OR COALESCE(ar.open_receivable_balance, 0) > 0
        )
        SELECT
            customer_id,
            customer_name,
            order_count,
            order_amount,
            shipped_amount,
            open_delivery_amount,
            overdue_order_count,
            max_delivery_overdue_days,
            receivable_amount,
            received_amount,
            open_receivable_balance,
            open_receivable_count,
            overdue_receivable_count,
            max_receivable_overdue_days,
            open_delivery_amount + open_receivable_balance AS total_open_amount,
            CASE
                WHEN overdue_receivable_count > 0 THEN '逾期未收'
                WHEN overdue_order_count > 0 THEN '逾期未交'
                WHEN open_receivable_balance > 0 THEN '待回款'
                WHEN open_delivery_amount > 0 THEN '待交付'
                ELSE '正常'
            END AS risk_status,
            CASE
                WHEN overdue_receivable_count > 0 THEN '跟进逾期应收'
                WHEN overdue_order_count > 0 THEN '跟进逾期交付'
                WHEN open_receivable_balance > 0 THEN '跟进收款'
                WHEN open_delivery_amount > 0 THEN '跟进发货'
                ELSE '持续观察'
            END AS next_action
        FROM base
        GROUP BY
            customer_id, customer_name, order_count, order_amount, shipped_amount,
            open_delivery_amount, overdue_order_count, max_delivery_overdue_days,
            receivable_amount, received_amount, open_receivable_balance,
            open_receivable_count, overdue_receivable_count, max_receivable_overdue_days
        {having_sql}
        ORDER BY total_open_amount DESC, overdue_receivable_count DESC, overdue_order_count DESC, customer_name
        LIMIT %s
    """
    rows = query_rows(sql, tuple(params + [filters["limit"]]))
    for row in rows:
        row["customer_url"] = f"/customer/{row['customer_id']}" if row.get("customer_id") else ""

    summary = {
        "row_count": len(rows),
        "order_amount": sum(_money(row.get("order_amount")) for row in rows),
        "open_delivery_amount": sum(_money(row.get("open_delivery_amount")) for row in rows),
        "open_receivable_balance": sum(_money(row.get("open_receivable_balance")) for row in rows),
        "total_open_amount": sum(_money(row.get("total_open_amount")) for row in rows),
        "overdue_customer_count": sum(
            1
            for row in rows
            if int(row.get("overdue_order_count") or 0) > 0
            or int(row.get("overdue_receivable_count") or 0) > 0
        ),
    }
    return {
        "filters": filters,
        "summary": summary,
        "columns": customer_ranking_columns(),
        "rows": rows,
    }


def collection_detail_columns():
    return [
        {"key": "receipt_no", "label": "收款单号", "url_key": "receipt_url"},
        {"key": "receipt_date", "label": "收款日期"},
        {"key": "customer_name", "label": "客户"},
        {"key": "collection_basis", "label": "收款口径"},
        {"key": "receivable_source_no", "label": "应收来源单号", "url_key": "receivable_url"},
        {"key": "order_no", "label": "销售订单"},
        {"key": "shipment_no", "label": "发货单"},
        {"key": "project_code", "label": "项目号"},
        {"key": "cabinet_no", "label": "柜号"},
        {"key": "receivable_amount", "label": "应收金额", "format": "money", "align": "right"},
        {"key": "collection_amount", "label": "本次收款/核销金额", "format": "money", "align": "right"},
        {"key": "received_amount", "label": "应收已收金额", "format": "money", "align": "right"},
        {"key": "receivable_balance", "label": "未收余额", "format": "money", "align": "right"},
        {"key": "unapplied_amount", "label": "未核销收款", "format": "money", "align": "right"},
        {"key": "due_date", "label": "到期日"},
        {"key": "overdue_days", "label": "逾期天数", "align": "right"},
        {"key": "aging_bucket", "label": "账龄区间"},
        {"key": "payment_method", "label": "收款方式"},
        {"key": "receipt_status", "label": "收款状态"},
    ]


def customer_ranking_columns():
    return [
        {"key": "customer_name", "label": "客户", "url_key": "customer_url"},
        {"key": "order_count", "label": "订单数", "align": "right"},
        {"key": "order_amount", "label": "订单金额", "format": "money", "align": "right"},
        {"key": "shipped_amount", "label": "已发货金额", "format": "money", "align": "right"},
        {"key": "open_delivery_amount", "label": "未交金额", "format": "money", "align": "right"},
        {"key": "receivable_amount", "label": "应收金额", "format": "money", "align": "right"},
        {"key": "received_amount", "label": "已收金额", "format": "money", "align": "right"},
        {"key": "open_receivable_balance", "label": "未收余额", "format": "money", "align": "right"},
        {"key": "total_open_amount", "label": "未交/未收合计", "format": "money", "align": "right"},
        {"key": "open_receivable_count", "label": "未清应收笔数", "align": "right"},
        {"key": "overdue_order_count", "label": "逾期未交单数", "align": "right"},
        {"key": "overdue_receivable_count", "label": "逾期未收笔数", "align": "right"},
        {"key": "max_delivery_overdue_days", "label": "最长交付逾期", "align": "right"},
        {"key": "max_receivable_overdue_days", "label": "最长收款逾期", "align": "right"},
        {"key": "risk_status", "label": "风险状态"},
        {"key": "next_action", "label": "下一步"},
    ]


def build_sales_receivable_report(query_rows, report_key, args=None):
    if report_key == "receivable-collection-detail":
        report = query_receivable_collection_detail(query_rows, args)
        report["title"] = "销售收款执行明细"
        report["basis_note"] = "收款口径：按应收核销关联优先；无法关联到应收时，仅作为客户收款记录展示。"
        return report
    if report_key == "customer-ranking":
        report = query_customer_ranking(query_rows, args)
        report["title"] = "客户未交/未收排行"
        report["basis_note"] = "排行口径：未交金额按销售订单金额减已发货金额；未收余额按应收余额汇总。"
        return report
    raise ValueError(f"Unsupported sales receivable report: {report_key}")
