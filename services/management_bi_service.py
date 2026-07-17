"""E-5: Management BI Cockpit Service.

Computes cross-module KPIs for the executive dashboard:
- Sales: order backlog, shipped amount, AR aging
- Production: WIP count, completion rate, overdue work orders
- Inventory: total valuation, turnover ratio, low stock alerts
- Finance: cash balance, AR/AP totals, cost trend
- Procurement: open PO count, pending receipts

This is a read-only reporting service. It does not write to any table.
All KPIs are computed from existing transactional tables via aggregate queries.
"""

from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


def _table_exists(query_fn, table_name):
    row = _safe_query_one(
        query_fn,
        "SELECT to_regclass(%s) AS table_ref",
        (table_name,),
    )
    return bool(row.get("table_ref"))


def _column_exists(query_fn, table_name, column_name):
    row = _safe_query_one(
        query_fn,
        """
        SELECT 1 AS exists_flag
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return bool(row.get("exists_flag"))


def _rollback_query_connection(query_fn):
    get_db = getattr(query_fn, "__self_get_db__", None)
    if not get_db:
        return
    try:
        conn = get_db()
        if conn and not conn.closed:
            conn.rollback()
    except Exception:
        logger.debug("failed to rollback BI query connection", exc_info=True)


def _safe_query(query_fn, sql, params=None):
    try:
        return query_fn(sql, params or ()) or []
    except Exception:
        _rollback_query_connection(query_fn)
        logger.warning("_safe_query failed", exc_info=True)
        return []


def _safe_query_one(query_fn, sql, params=None):
    try:
        return query_fn(sql, params or (), one=True) or {}
    except Exception:
        _rollback_query_connection(query_fn)
        logger.warning("_safe_query_one failed", exc_info=True)
        return {}


def _legacy_get_sales_kpis(query_fn):
    """Sales module KPIs."""
    today = date.today()
    month_start = today.replace(day=1)

    # Order backlog: open sales orders not yet fully shipped
    backlog = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS order_count,
               COALESCE(SUM(COALESCE(total_amount, 0)), 0) AS total_amount
        FROM sales_orders
        WHERE COALESCE(status, '') NOT IN ('已取消', 'cancelled', '已关闭', 'closed')
          AND COALESCE(status, '') IN ('已确认', 'confirmed', '待发货', 'pending', '草稿', 'draft', '')
        """,
    )

    # This month shipped amount
    shipped = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS shipment_count,
               COALESCE(SUM(COALESCE(shipped_amount, 0)), 0) AS total_amount
        FROM sales_shipments
        WHERE shipment_date >= %s
          AND COALESCE(status, '') NOT IN ('已取消', 'cancelled')
        """,
        (month_start,),
    )

    # AR aging summary
    ar_aging = _safe_query(
        query_fn,
        """
        SELECT
            CASE
                WHEN COALESCE(balance, 0) <= 0 THEN 'paid'
                WHEN due_date >= CURRENT_DATE THEN 'current'
                WHEN due_date >= CURRENT_DATE - INTERVAL '30 days' THEN 'overdue_30'
                WHEN due_date >= CURRENT_DATE - INTERVAL '60 days' THEN 'overdue_60'
                WHEN due_date >= CURRENT_DATE - INTERVAL '90 days' THEN 'overdue_90'
                ELSE 'overdue_90_plus'
            END AS bucket,
            COUNT(*) AS count,
            COALESCE(SUM(balance), 0) AS amount
        FROM receivables
        WHERE COALESCE(status, '') NOT IN ('已核销', 'settled', '已关闭', 'closed', 'voided')
        GROUP BY 1
        """,
    )

    return {
        "backlog_orders": int(backlog.get("order_count") or 0),
        "backlog_amount": float(backlog.get("total_amount") or 0),
        "month_shipments": int(shipped.get("shipment_count") or 0),
        "month_shipped_amount": float(shipped.get("total_amount") or 0),
        "ar_aging": [
            {"bucket": r.get("bucket"), "count": int(r.get("count") or 0), "amount": float(r.get("amount") or 0)}
            for r in ar_aging
        ],
    }


def _legacy_get_production_kpis(query_fn):
    """Production module KPIs."""
    # WIP work orders
    wip = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(quantity, 0) - COALESCE(completed_qty, 0)), 0) AS pending_qty
        FROM work_orders
        WHERE COALESCE(status, '') IN ('已下达', 'released', '生产中', 'in_progress', '待开工', 'pending')
        """,
    )

    # Completed this month
    today = date.today()
    month_start = today.replace(day=1)
    completed = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(completed_qty, 0)), 0) AS completed_qty
        FROM work_orders
        WHERE COALESCE(status, '') IN ('已完成', 'completed', '已关闭', 'closed')
          AND COALESCE(updated_at, created_at) >= %s
        """,
        (month_start,),
    )

    overdue_date_col = "planned_end_date" if _column_exists(query_fn, "work_orders", "planned_end_date") else "planned_start_date"
    # Overdue work orders (planned date < today and not completed)
    overdue = _safe_query_one(
        query_fn,
        f"""
        SELECT COUNT(*) AS count
        FROM work_orders
        WHERE COALESCE(status, '') NOT IN ('已完成', 'completed', '已关闭', 'closed', '已取消', 'cancelled')
          AND {overdue_date_col} IS NOT NULL
          AND {overdue_date_col} < %s
        """,
        (today,),
    )

    # Total work orders
    total = _safe_query_one(
        query_fn,
        "SELECT COUNT(*) AS count FROM work_orders",
    )

    completed_count = int(completed.get("count") or 0)
    total_count = int(total.get("count") or 0)
    completion_rate = (completed_count / total_count * 100) if total_count > 0 else 0

    return {
        "wip_count": int(wip.get("count") or 0),
        "wip_pending_qty": float(wip.get("pending_qty") or 0),
        "month_completed_count": completed_count,
        "month_completed_qty": float(completed.get("completed_qty") or 0),
        "overdue_count": int(overdue.get("count") or 0),
        "completion_rate": round(completion_rate, 1),
    }


def _legacy_get_inventory_kpis(query_fn):
    """Inventory module KPIs."""
    # Total inventory valuation
    valuation = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(DISTINCT product_id) AS sku_count,
               COALESCE(SUM(COALESCE(quantity, 0)), 0) AS total_qty,
               COALESCE(SUM(COALESCE(quantity, 0) * COALESCE(unit_cost, 0)), 0) AS total_value
        FROM inventory_balances
        WHERE COALESCE(quantity, 0) != 0
        """,
    )

    # Low stock alerts (products with stock below minimum)
    low_stock = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count
        FROM products p
        WHERE COALESCE(p.min_stock, 0) > 0
          AND COALESCE((SELECT SUM(quantity) FROM inventory_balances ib WHERE ib.product_id = p.id), 0) < p.min_stock
        """,
    )

    # Inventory transactions this month (turnover indicator)
    today = date.today()
    month_start = today.replace(day=1)
    tx_count = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(quantity, 0)), 0) AS total_qty
        FROM inventory_transactions
        WHERE transaction_date >= %s
        """,
        (month_start,),
    )

    return {
        "sku_count": int(valuation.get("sku_count") or 0),
        "total_qty": float(valuation.get("total_qty") or 0),
        "total_value": float(valuation.get("total_value") or 0),
        "low_stock_count": int(low_stock.get("count") or 0),
        "month_tx_count": int(tx_count.get("count") or 0),
        "month_tx_qty": float(tx_count.get("total_qty") or 0),
    }


def _legacy_get_finance_kpis(query_fn):
    """Finance module KPIs."""
    # Cash and bank balances
    cash = _safe_query_one(
        query_fn,
        """
        SELECT COALESCE(SUM(COALESCE(balance, 0)), 0) AS total_balance,
               COUNT(*) AS account_count
        FROM fund_accounts
        WHERE COALESCE(status, '') != 'disabled'
        """,
    )

    # AR total
    ar_total = _safe_query_one(
        query_fn,
        """
        SELECT COALESCE(SUM(COALESCE(balance, 0)), 0) AS total
        FROM receivables
        WHERE COALESCE(status, '') NOT IN ('已核销', 'settled', '已关闭', 'closed', 'voided')
        """,
    )

    # AP total
    ap_total = _safe_query_one(
        query_fn,
        """
        SELECT COALESCE(SUM(COALESCE(balance, 0)), 0) AS total
        FROM payables
        WHERE COALESCE(status, '') NOT IN ('已核销', 'settled', '已关闭', 'closed', 'voided')
        """,
    )

    # Vouchers this period
    today = date.today()
    month_start = today.replace(day=1)
    vouchers = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(total_debit, 0)), 0) AS total_amount
        FROM vouchers
        WHERE voucher_date >= %s
          AND COALESCE(status, '') NOT IN ('已作废', 'voided')
        """,
        (month_start,),
    )

    return {
        "cash_balance": float(cash.get("total_balance") or 0),
        "cash_account_count": int(cash.get("account_count") or 0),
        "ar_total": float(ar_total.get("total") or 0),
        "ap_total": float(ap_total.get("total") or 0),
        "net_cash_position": float(cash.get("total_balance") or 0) + float(ar_total.get("total") or 0) - float(ap_total.get("total") or 0),
        "month_voucher_count": int(vouchers.get("count") or 0),
        "month_voucher_amount": float(vouchers.get("total_amount") or 0),
    }


def _legacy_get_procurement_kpis(query_fn):
    """Procurement module KPIs."""
    # Open purchase orders
    open_pos = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(total_amount, 0)), 0) AS total_amount
        FROM purchase_orders
        WHERE COALESCE(status, '') NOT IN ('已取消', 'cancelled', '已关闭', 'closed', '已完成', 'completed')
        """,
    )

    # Pending receipts (PO not yet received)
    pending_receipts = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count
        FROM purchase_orders po
        WHERE COALESCE(po.status, '') NOT IN ('已取消', 'cancelled', '已关闭', 'closed', '已完成', 'completed')
          AND NOT EXISTS (
              SELECT 1 FROM purchase_receipts pr
              WHERE pr.purchase_order_id = po.id
                AND COALESCE(pr.status, '') NOT IN ('已取消', 'cancelled')
          )
        """,
    )

    # This month received
    today = date.today()
    month_start = today.replace(day=1)
    received = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count
        FROM purchase_receipts
        WHERE receipt_date >= %s
          AND COALESCE(status, '') NOT IN ('已取消', 'cancelled')
        """,
        (month_start,),
    )

    return {
        "open_po_count": int(open_pos.get("count") or 0),
        "open_po_amount": float(open_pos.get("total_amount") or 0),
        "pending_receipt_count": int(pending_receipts.get("count") or 0),
        "month_received_count": int(received.get("count") or 0),
    }


def get_sales_kpis(query_fn):
    """Sales module KPIs with optional-table guards."""
    today = date.today()
    month_start = today.replace(day=1)

    backlog = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS order_count,
               COALESCE(SUM(COALESCE(total_amount, 0)), 0) AS total_amount
        FROM sales_orders
        WHERE COALESCE(status, '') NOT IN ('已取消','已关闭','已作废','cancelled','canceled','closed','voided','void')
        """,
    )

    shipped = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS shipment_count,
               COALESCE(SUM(COALESCE(shipped_amount, 0)), 0) AS total_amount
        FROM sales_shipments
        WHERE shipment_date >= %s
          AND COALESCE(status, '') NOT IN ('已取消','已作废','cancelled','canceled','voided','void')
        """,
        (month_start,),
    )

    ar_aging = []
    if _table_exists(query_fn, "customer_receivables"):
        ar_aging = _safe_query(
            query_fn,
            """
            SELECT
                CASE
                    WHEN COALESCE(balance, 0) <= 0 THEN 'paid'
                    WHEN due_date >= CURRENT_DATE THEN 'current'
                    WHEN due_date >= CURRENT_DATE - INTERVAL '30 days' THEN 'overdue_30'
                    WHEN due_date >= CURRENT_DATE - INTERVAL '60 days' THEN 'overdue_60'
                    WHEN due_date >= CURRENT_DATE - INTERVAL '90 days' THEN 'overdue_90'
                    ELSE 'overdue_90_plus'
                END AS bucket,
                COUNT(*) AS count,
                COALESCE(SUM(balance), 0) AS amount
            FROM customer_receivables
            WHERE COALESCE(status, '') NOT IN ('已结清','已关闭','已作废','settled','closed','voided','void')
            GROUP BY 1
            """,
        )

    return {
        "backlog_orders": int(backlog.get("order_count") or 0),
        "backlog_amount": float(backlog.get("total_amount") or 0),
        "month_shipments": int(shipped.get("shipment_count") or 0),
        "month_shipped_amount": float(shipped.get("total_amount") or 0),
        "ar_aging": [
            {"bucket": r.get("bucket"), "count": int(r.get("count") or 0), "amount": float(r.get("amount") or 0)}
            for r in ar_aging
        ],
    }


def get_production_kpis(query_fn):
    """Production module KPIs with schema-compatible expressions."""
    today = date.today()
    month_start = today.replace(day=1)
    completed_expr = "COALESCE(completed_qty, 0)" if _column_exists(query_fn, "work_orders", "completed_qty") else "0"
    work_order_date_expr = "created_at"
    if _column_exists(query_fn, "work_orders", "updated_at"):
        work_order_date_expr = "COALESCE(updated_at, created_at)"

    wip = _safe_query_one(
        query_fn,
        f"""
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(quantity, 0) - {completed_expr}), 0) AS pending_qty
        FROM work_orders
        WHERE COALESCE(status, '') IN ('已下达','已开工','生产中','待生产','待处理','released','in_progress','pending')
        """,
    )

    completed = _safe_query_one(
        query_fn,
        f"""
        SELECT COUNT(*) AS count,
               COALESCE(SUM({completed_expr}), 0) AS completed_qty
        FROM work_orders
        WHERE COALESCE(status, '') IN ('已完工','已完成','已关闭','completed','closed')
          AND {work_order_date_expr} >= %s
        """,
        (month_start,),
    )

    overdue = {}
    overdue_date_col = None
    if _column_exists(query_fn, "work_orders", "planned_end_date"):
        overdue_date_col = "planned_end_date"
    elif _column_exists(query_fn, "work_orders", "planned_start_date"):
        overdue_date_col = "planned_start_date"
    else:
        overdue_date_col = work_order_date_expr
    if overdue_date_col:
        overdue = _safe_query_one(
            query_fn,
            f"""
            SELECT COUNT(*) AS count
            FROM work_orders
            WHERE COALESCE(status, '') NOT IN ('已完工','已完成','已关闭','已取消','已作废','completed','closed','cancelled','canceled','voided','void')
              AND {overdue_date_col} IS NOT NULL
              AND {overdue_date_col} < %s
            """,
            (today,),
        )

    total = _safe_query_one(query_fn, "SELECT COUNT(*) AS count FROM work_orders")
    completed_count = int(completed.get("count") or 0)
    total_count = int(total.get("count") or 0)
    completion_rate = (completed_count / total_count * 100) if total_count > 0 else 0

    return {
        "wip_count": int(wip.get("count") or 0),
        "wip_pending_qty": float(wip.get("pending_qty") or 0),
        "month_completed_count": completed_count,
        "month_completed_qty": float(completed.get("completed_qty") or 0),
        "overdue_count": int(overdue.get("count") or 0),
        "completion_rate": round(completion_rate, 1),
    }


def get_inventory_kpis(query_fn):
    """Inventory module KPIs with optional-column guards."""
    valuation = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(DISTINCT product_id) AS sku_count,
               COALESCE(SUM(COALESCE(quantity, 0)), 0) AS total_qty,
               COALESCE(SUM(COALESCE(quantity, 0) * COALESCE(unit_cost, 0)), 0) AS total_value
        FROM inventory_balances
        WHERE COALESCE(quantity, 0) != 0
        """,
    )

    low_stock = {}
    if _column_exists(query_fn, "products", "min_stock"):
        low_stock = _safe_query_one(
            query_fn,
            """
            SELECT COUNT(*) AS count
            FROM products p
            WHERE COALESCE(p.min_stock, 0) > 0
              AND COALESCE((SELECT SUM(quantity) FROM inventory_balances ib WHERE ib.product_id = p.id), 0) < p.min_stock
            """,
        )

    today = date.today()
    month_start = today.replace(day=1)
    tx_count = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(quantity, 0)), 0) AS total_qty
        FROM inventory_transactions
        WHERE transaction_date >= %s
        """,
        (month_start,),
    )

    return {
        "sku_count": int(valuation.get("sku_count") or 0),
        "total_qty": float(valuation.get("total_qty") or 0),
        "total_value": float(valuation.get("total_value") or 0),
        "low_stock_count": int(low_stock.get("count") or 0),
        "month_tx_count": int(tx_count.get("count") or 0),
        "month_tx_qty": float(tx_count.get("total_qty") or 0),
    }


def get_finance_kpis(query_fn):
    """Finance module KPIs with optional-table guards."""
    cash = {}
    if _table_exists(query_fn, "cash_bank_accounts"):
        cash = _safe_query_one(
            query_fn,
            """
            SELECT COALESCE(SUM(COALESCE(current_balance, 0)), 0) AS total_balance,
                   COUNT(*) AS account_count
            FROM cash_bank_accounts
            WHERE COALESCE(status, '') NOT IN ('停用','禁用','disabled','inactive')
            """,
        )

    ar_total = {}
    if _table_exists(query_fn, "customer_receivables"):
        ar_total = _safe_query_one(
            query_fn,
            """
            SELECT COALESCE(SUM(COALESCE(balance, 0)), 0) AS total
            FROM customer_receivables
            WHERE COALESCE(status, '') NOT IN ('已结清','已关闭','已作废','settled','closed','voided','void')
            """,
        )

    ap_total = {}
    if _table_exists(query_fn, "supplier_payables"):
        ap_total = _safe_query_one(
            query_fn,
            """
            SELECT COALESCE(SUM(COALESCE(balance, 0)), 0) AS total
            FROM supplier_payables
            WHERE COALESCE(status, '') NOT IN ('已结清','已关闭','已作废','settled','closed','voided','void')
            """,
        )

    today = date.today()
    month_start = today.replace(day=1)
    vouchers = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(total_debit, 0)), 0) AS total_amount
        FROM vouchers
        WHERE voucher_date >= %s
          AND COALESCE(status, '') NOT IN ('已作废','作废','voided','void')
        """,
        (month_start,),
    )

    return {
        "cash_balance": float(cash.get("total_balance") or 0),
        "cash_account_count": int(cash.get("account_count") or 0),
        "ar_total": float(ar_total.get("total") or 0),
        "ap_total": float(ap_total.get("total") or 0),
        "net_cash_position": float(cash.get("total_balance") or 0) + float(ar_total.get("total") or 0) - float(ap_total.get("total") or 0),
        "month_voucher_count": int(vouchers.get("count") or 0),
        "month_voucher_amount": float(vouchers.get("total_amount") or 0),
    }


def get_procurement_kpis(query_fn):
    """Procurement module KPIs with optional-column guards."""
    open_pos = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count,
               COALESCE(SUM(COALESCE(total_amount, 0)), 0) AS total_amount
        FROM purchase_orders
        WHERE COALESCE(status, '') NOT IN ('已取消','已关闭','已完成','已收货','已作废','cancelled','canceled','closed','completed','voided','void')
        """,
    )

    pending_receipts = {}
    if _column_exists(query_fn, "purchase_receipts", "purchase_order_id"):
        pending_receipts = _safe_query_one(
            query_fn,
            """
            SELECT COUNT(*) AS count
            FROM purchase_orders po
            WHERE COALESCE(po.status, '') NOT IN ('已取消','已关闭','已完成','已收货','已作废','cancelled','canceled','closed','completed','voided','void')
              AND NOT EXISTS (
                  SELECT 1 FROM purchase_receipts pr
                  WHERE pr.purchase_order_id = po.id
                    AND COALESCE(pr.status, '') NOT IN ('已取消','已作废','cancelled','canceled','voided','void')
              )
            """,
        )

    today = date.today()
    month_start = today.replace(day=1)
    received = _safe_query_one(
        query_fn,
        """
        SELECT COUNT(*) AS count
        FROM purchase_receipts
        WHERE receipt_date >= %s
          AND COALESCE(status, '') NOT IN ('已取消','已作废','cancelled','canceled','voided','void')
        """,
        (month_start,),
    )

    return {
        "open_po_count": int(open_pos.get("count") or 0),
        "open_po_amount": float(open_pos.get("total_amount") or 0),
        "pending_receipt_count": int(pending_receipts.get("count") or 0),
        "month_received_count": int(received.get("count") or 0),
    }


def get_cockpit_kpis(query_fn):
    """Aggregate all module KPIs for the management cockpit."""
    return {
        "sales": get_sales_kpis(query_fn),
        "production": get_production_kpis(query_fn),
        "inventory": get_inventory_kpis(query_fn),
        "finance": get_finance_kpis(query_fn),
        "procurement": get_procurement_kpis(query_fn),
        "generated_at": date.today().isoformat(),
    }
