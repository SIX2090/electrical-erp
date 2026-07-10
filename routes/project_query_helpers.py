"""Project query helpers: build kit summary, finance summary, and items-without-BOM metrics."""
from decimal import Decimal


def build_kit_summary(rows, no_bom_items=None, *, as_decimal, qty_metric):
    rows = list(rows or [])
    shortage_count = sum(1 for row in rows if as_decimal(row.get("shortage_qty")) > 0)
    stock_shortage_count = sum(1 for row in rows if as_decimal(row.get("stock_shortage_qty")) > 0)
    pending_count = sum(1 for row in rows if as_decimal(row.get("pending_purchase_qty")) > 0)
    shortage_qty = sum((as_decimal(row.get("shortage_qty")) for row in rows), Decimal("0"))
    return {
        "total_count": len(rows),
        "ok_count": max(len(rows) - shortage_count, 0),
        "shortage_count": shortage_count,
        "stock_shortage_count": stock_shortage_count,
        "pending_count": pending_count,
        "shortage_qty": qty_metric(shortage_qty),
        "no_bom_count": len(no_bom_items or []),
    }


def project_kit_rows(order_id, project_code=None, cabinet_no=None, cost_object_id=None, *, safe_rows):
    return safe_rows(
        """
        WITH sales_items AS (
            SELECT soi.id AS sales_item_id, soi.product_id AS parent_product_id,
                   COALESCE(soi.quantity, 0) AS parent_qty,
                   parent.code AS parent_code, parent.name AS parent_name
            FROM sales_order_items soi
            LEFT JOIN products parent ON parent.id=soi.product_id
            WHERE soi.order_id=%s
        ),
        chosen_boms AS (
            SELECT si.*, b.id AS bom_id, b.bom_no
            FROM sales_items si
            LEFT JOIN LATERAL (
                SELECT id, bom_no
                FROM boms
                WHERE product_id=si.parent_product_id
                ORDER BY CASE
                    WHEN COALESCE(status, '') IN ('active', 'Active', 'enabled') THEN 0
                    ELSE 1
                END, id DESC
                LIMIT 1
            ) b ON TRUE
        ),
        component_rows AS (
            SELECT cb.sales_item_id, cb.parent_code, cb.parent_name, cb.parent_qty,
                   cb.bom_id, cb.bom_no, bi.product_id,
                   p.code AS product_code, p.name AS product_name, p.specification,
                   COALESCE(bi.unit, p.unit, '') AS unit,
                   COALESCE(bi.quantity, 0) AS qty_per,
                   COALESCE(bi.loss_rate, 0) AS loss_rate,
                   COALESCE(cb.parent_qty, 0)
                     * COALESCE(bi.quantity, 0)
                     * (1 + COALESCE(bi.loss_rate, 0) / 100.0) AS required_qty
            FROM chosen_boms cb
            JOIN bom_items bi ON bi.bom_id=cb.bom_id
            LEFT JOIN products p ON p.id=bi.product_id
            WHERE COALESCE(bi.is_optional, FALSE)=FALSE
        ),
        stock AS (
            SELECT product_id,
                   COALESCE(SUM(quantity), 0) AS stock_qty,
                   COALESCE(SUM(locked_qty), 0) AS locked_qty
            FROM inventory_balances
            GROUP BY product_id
        ),
        pending AS (
            SELECT poi.product_id,
                   COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0) AS pending_purchase_qty
            FROM purchase_order_items poi
            LEFT JOIN purchase_orders po ON po.id=poi.order_id
            WHERE GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0) > 0
              AND (
                    (%s IS NULL AND %s IS NULL AND %s IS NULL)
                    OR (%s IS NOT NULL AND po.cost_object_id=%s)
                    OR (%s IS NOT NULL AND po.project_code=%s)
                    OR (%s IS NOT NULL AND po.cabinet_no=%s)
              )
            GROUP BY poi.product_id
        )
        SELECT MIN(cr.sales_item_id) AS id,
               cr.product_id,
               cr.product_code, cr.product_name, cr.specification, cr.unit,
               STRING_AGG(DISTINCT NULLIF(CONCAT_WS(' ', cr.parent_code, cr.parent_name), ''), ' / ') AS parent_name,
               STRING_AGG(DISTINCT cr.bom_no, ', ') AS bom_no,
               SUM(cr.required_qty) AS required_qty,
               COALESCE(stock.stock_qty, 0) AS stock_qty,
               COALESCE(stock.locked_qty, 0) AS locked_qty,
               GREATEST(COALESCE(stock.stock_qty, 0)-COALESCE(stock.locked_qty, 0), 0) AS available_qty,
               COALESCE(pending.pending_purchase_qty, 0) AS pending_purchase_qty,
               GREATEST(SUM(cr.required_qty)-GREATEST(COALESCE(stock.stock_qty, 0)-COALESCE(stock.locked_qty, 0), 0), 0) AS stock_shortage_qty,
               GREATEST(
                   SUM(cr.required_qty)
                   - GREATEST(COALESCE(stock.stock_qty, 0)-COALESCE(stock.locked_qty, 0), 0)
                   - COALESCE(pending.pending_purchase_qty, 0),
                   0
               ) AS shortage_qty,
               CASE
                   WHEN SUM(cr.required_qty) <= GREATEST(COALESCE(stock.stock_qty, 0)-COALESCE(stock.locked_qty, 0), 0) THEN 'stock_ready'
                   WHEN SUM(cr.required_qty) <= GREATEST(COALESCE(stock.stock_qty, 0)-COALESCE(stock.locked_qty, 0), 0) + COALESCE(pending.pending_purchase_qty, 0) THEN 'pending_purchase'
                   ELSE 'need_purchase'
               END AS kit_status
        FROM component_rows cr
        LEFT JOIN stock ON stock.product_id=cr.product_id
        LEFT JOIN pending ON pending.product_id=cr.product_id
        GROUP BY cr.product_id, cr.product_code, cr.product_name, cr.specification, cr.unit,
                 stock.stock_qty, stock.locked_qty, pending.pending_purchase_qty
        ORDER BY shortage_qty DESC, stock_shortage_qty DESC, cr.product_code
        LIMIT 120
        """,
        (
            order_id,
            cost_object_id,
            project_code,
            cabinet_no,
            cost_object_id,
            cost_object_id,
            project_code,
            project_code,
            cabinet_no,
            cabinet_no,
        ),
    )


def project_items_without_bom(order_id, *, safe_rows):
    return safe_rows(
        """
        SELECT soi.id, p.code AS product_code, p.name AS product_name,
               p.specification, soi.quantity, COALESCE(p.unit, '') AS unit
        FROM sales_order_items soi
        LEFT JOIN products p ON p.id=soi.product_id
        LEFT JOIN LATERAL (
            SELECT id
            FROM boms
            WHERE product_id=soi.product_id
            ORDER BY id DESC
            LIMIT 1
        ) b ON TRUE
        WHERE soi.order_id=%s AND b.id IS NULL
        ORDER BY soi.id
        """,
        (order_id,),
    )


def project_finance_summary(order, project_code=None, cabinet_no=None, cost_object_id=None, *, safe_one, as_decimal):
    if not order:
        return {}
    order_id = order.get("id")
    sales = safe_one(
        """
        SELECT COALESCE(SUM(total_amount), 0) AS sales_amount,
               COALESCE(SUM(shipped_amount), 0) AS shipped_amount
        FROM sales_orders
        WHERE id=%s
           OR (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND cabinet_no=%s)
        """,
        (order_id, cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    receivable = safe_one(
        """
        SELECT COALESCE(SUM(total_amount), 0) AS receivable_amount,
               COALESCE(SUM(received_amount), 0) AS received_amount,
               COALESCE(SUM(balance), 0) AS receivable_balance
        FROM customer_receivables
        WHERE source_id=%s
           OR (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND cabinet_no=%s)
        """,
        (order_id, cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    purchase = safe_one(
        """
        SELECT COALESCE(SUM(COALESCE(NULLIF(confirmed_amount, 0), amount, 0)), 0) AS purchase_amount,
               COALESCE(SUM(COALESCE(NULLIF(confirmed_amount, 0), amount, 0)), 0) AS purchase_received_amount
        FROM supplier_payables
        WHERE COALESCE(doc_type, source_type, '') IN ('purchase_receipt','purchase_invoice')
          AND ((%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND cabinet_no=%s))
        """,
        (cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    subcontract = safe_one(
        """
        SELECT COALESCE(SUM(COALESCE(NULLIF(confirmed_amount, 0), amount, 0)), 0) AS subcontract_amount
        FROM supplier_payables
        WHERE COALESCE(doc_type, source_type, '') IN ('subcontract_receive','subcontract_receive_order')
          AND ((%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND cabinet_no=%s))
        """,
        (cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    work_order_cost = safe_one(
        """
        SELECT COALESCE(SUM(woc.total_cost), 0) AS work_order_cost
        FROM work_order_costs woc
        LEFT JOIN work_orders wo ON wo.id=woc.work_order_id
        WHERE (%s IS NOT NULL AND woc.cost_object_id=%s)
           OR (%s IS NOT NULL AND wo.project_code=%s)
           OR (%s IS NOT NULL AND wo.cabinet_no=%s)
        """,
        (cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    purchase_payables = safe_one(
        """
        SELECT COALESCE(SUM(COALESCE(NULLIF(sp.confirmed_amount, 0), sp.amount, 0)), 0) AS payable_amount,
               COALESCE(SUM(sp.paid_amount), 0) AS paid_amount,
               COALESCE(SUM(sp.balance), 0) AS payable_balance
        FROM supplier_payables sp
        WHERE COALESCE(sp.doc_type, sp.source_type, '') IN ('purchase_receipt','purchase_invoice')
          AND ((%s IS NOT NULL AND sp.cost_object_id=%s)
           OR (%s IS NOT NULL AND sp.project_code=%s)
           OR (%s IS NOT NULL AND sp.cabinet_no=%s))
        """,
        (cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    service = safe_one(
        """
        SELECT COALESCE(SUM(total_cost), 0) AS service_cost
        FROM machine_service_orders
        WHERE (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND cabinet_no=%s)
        """,
        (cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    subcontract_payables = safe_one(
        """
        SELECT COALESCE(SUM(COALESCE(NULLIF(sp.confirmed_amount, 0), sp.amount, 0)), 0) AS payable_amount,
               COALESCE(SUM(sp.paid_amount), 0) AS paid_amount,
               COALESCE(SUM(sp.balance), 0) AS payable_balance
        FROM supplier_payables sp
        WHERE COALESCE(sp.doc_type, sp.source_type, '') IN ('subcontract_receive','subcontract_receive_order')
          AND ((%s IS NOT NULL AND sp.cost_object_id=%s)
           OR (%s IS NOT NULL AND sp.project_code=%s)
           OR (%s IS NOT NULL AND sp.cabinet_no=%s))
        """,
        (cost_object_id, cost_object_id, project_code, project_code, cabinet_no, cabinet_no),
    ) or {}
    sales_amount = as_decimal(sales.get("sales_amount"))
    purchase_amount = as_decimal(purchase.get("purchase_amount"))
    subcontract_amount = as_decimal(subcontract.get("subcontract_amount"))
    work_order_amount = as_decimal(work_order_cost.get("work_order_cost"))
    service_amount = as_decimal(service.get("service_cost"))
    total_cost = purchase_amount + subcontract_amount + work_order_amount + service_amount
    gross_profit = sales_amount - total_cost
    gross_margin = (gross_profit / sales_amount * Decimal("100")) if sales_amount else Decimal("0")
    return {
        "sales_amount": sales_amount,
        "shipped_amount": sales.get("shipped_amount", 0),
        "receivable_amount": receivable.get("receivable_amount", 0),
        "received_amount": receivable.get("received_amount", 0),
        "receivable_balance": receivable.get("receivable_balance", 0),
        "purchase_amount": purchase_amount,
        "purchase_received_amount": purchase.get("purchase_received_amount", 0),
        "subcontract_amount": subcontract_amount,
        "work_order_cost": work_order_amount,
        "service_cost": service_amount,
        "total_cost": total_cost,
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "payable_amount": as_decimal(purchase_payables.get("payable_amount")) + as_decimal(subcontract_payables.get("payable_amount")),
        "paid_amount": as_decimal(purchase_payables.get("paid_amount")) + as_decimal(subcontract_payables.get("paid_amount")),
        "payable_balance": as_decimal(purchase_payables.get("payable_balance")) + as_decimal(subcontract_payables.get("payable_balance")),
    }
