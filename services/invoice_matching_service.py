# -*- coding: utf-8 -*-
"""
发票三单匹配服务

提供销售侧和采购侧的三单匹配查询：
- 销售侧：销售订单 → 发货单 → 销售发票
- 采购侧：采购订单 → 入库单 → 采购发票
"""

from decimal import Decimal


def query_sales_three_way_match(query_db, filters=None):
    """
    查询销售三单匹配（订单-发货-发票）

    返回字段：
    - 订单信息：order_no, order_date, customer_name, product_code, product_name
    - 订单数量和金额：order_qty, order_amount
    - 发货数量和金额：delivery_qty, delivery_amount
    - 开票数量和金额：invoice_qty, invoice_amount
    - 未开票数量和金额：uninvoiced_qty, uninvoiced_amount
    - 差异状态：match_status（正常/超开票/欠开票/未发货）
    """
    filters = filters or {}
    where_clauses = ["so.status != '已作废'"]
    params = []

    # 筛选条件
    if filters.get("customer_id"):
        where_clauses.append("so.customer_id = %s")
        params.append(filters["customer_id"])

    if filters.get("order_no"):
        where_clauses.append("so.order_no ILIKE %s")
        params.append(f"%{filters['order_no']}%")

    if filters.get("project_code"):
        where_clauses.append("so.project_code ILIKE %s")
        params.append(f"%{filters['project_code']}%")

    if filters.get("cabinet_no"):
        where_clauses.append("so.cabinet_no ILIKE %s")
        params.append(f"%{filters['cabinet_no']}%")

    if filters.get("start_date"):
        where_clauses.append("so.order_date >= %s")
        params.append(filters["start_date"])

    if filters.get("end_date"):
        where_clauses.append("so.order_date <= %s")
        params.append(filters["end_date"])

    if filters.get("match_status"):
        # 根据匹配状态筛选（在查询后过滤）
        pass

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    sql = f"""
    SELECT
        so.id AS order_id,
        so.order_no,
        so.order_date,
        so.customer_id,
        c.name AS customer_name,
        so.project_code,
        so.cabinet_no,
        soi.id AS order_item_id,
        soi.product_id,
        soi.product_code,
        soi.product_name,
        soi.specification,
        soi.unit,
        soi.quantity AS order_qty,
        soi.unit_price AS order_price,
        soi.amount AS order_amount,

        -- 发货信息（按订单行汇总）
        COALESCE(SUM(doi.quantity), 0) AS delivery_qty,
        COALESCE(SUM(doi.amount), 0) AS delivery_amount,

        -- 开票信息（按订单行汇总）
        COALESCE(SUM(sii.quantity), 0) AS invoice_qty,
        COALESCE(SUM(sii.amount_with_tax), 0) AS invoice_amount,

        -- 未开票数量和金额
        COALESCE(SUM(doi.quantity), 0) - COALESCE(SUM(sii.quantity), 0) AS uninvoiced_qty,
        COALESCE(SUM(doi.amount), 0) - COALESCE(SUM(sii.amount_with_tax), 0) AS uninvoiced_amount,

        -- 发货单信息（最新一条）
        MAX(d.delivery_no) AS latest_delivery_no,
        MAX(d.delivery_date) AS latest_delivery_date,

        -- 发票信息（最新一条）
        MAX(si.invoice_no) AS latest_invoice_no,
        MAX(si.invoice_date) AS latest_invoice_date

    FROM sales_orders so
    JOIN sales_order_items soi ON soi.sales_order_id = so.id
    LEFT JOIN customers c ON c.id = so.customer_id
    LEFT JOIN delivery_orders d ON d.source_type = 'sales_order' AND d.source_id = so.id AND d.status != '已作废'
    LEFT JOIN delivery_order_items doi ON doi.delivery_id = d.id AND doi.product_id = soi.product_id
    LEFT JOIN sales_invoice_items sii ON sii.sales_order_id = so.id AND sii.item_code = soi.product_code
    LEFT JOIN sales_invoices si ON si.id = sii.invoice_id AND si.status != '已作废'

    WHERE {where_sql}
    GROUP BY so.id, soi.id, c.id
    ORDER BY so.order_date DESC, so.order_no, soi.line_no
    """

    sql = f"""
    WITH shipment_lines AS (
        SELECT
            ss.order_id,
            ssi.product_id,
            SUM(COALESCE(ssi.quantity, 0)) AS delivery_qty,
            SUM(COALESCE(ssi.amount_with_tax, ssi.amount, 0)) AS delivery_amount,
            MAX(ss.shipment_no) AS latest_delivery_no,
            MAX(ss.shipment_date) AS latest_delivery_date
        FROM sales_shipment_items ssi
        JOIN sales_shipments ss ON ssi.shipment_id = ss.id
        GROUP BY ss.order_id, ssi.product_id
    ),
    invoice_lines AS (
        SELECT
            sii.sales_order_id AS order_id,
            sii.product_id,
            SUM(COALESCE(sii.quantity, 0)) AS invoice_qty,
            SUM(COALESCE(sii.amount_with_tax, sii.amount, 0)) AS invoice_amount,
            MAX(si.invoice_no) AS latest_invoice_no,
            MAX(si.invoice_date) AS latest_invoice_date
        FROM sales_invoice_items sii
        JOIN sales_invoices si ON si.id = sii.invoice_id
        WHERE COALESCE(si.invoice_type, '') <> 'red'
        GROUP BY sii.sales_order_id, sii.product_id
    )
    SELECT
        so.id AS order_id,
        so.order_no,
        so.order_date,
        so.customer_id,
        c.name AS customer_name,
        so.project_code,
        so.cabinet_no,
        soi.id AS order_item_id,
        soi.product_id,
        COALESCE(soi.material_code, p.code, '') AS product_code,
        COALESCE(soi.material_name, p.name, '') AS product_name,
        COALESCE(soi.material_spec, p.specification, '') AS specification,
        COALESCE(soi.material_unit, p.unit, '') AS unit,
        COALESCE(soi.quantity, 0) AS order_qty,
        COALESCE(soi.unit_price, 0) AS order_price,
        COALESCE(soi.amount_with_tax, soi.amount, 0) AS order_amount,
        COALESCE(sl.delivery_qty, 0) AS delivery_qty,
        COALESCE(sl.delivery_amount, 0) AS delivery_amount,
        COALESCE(il.invoice_qty, 0) AS invoice_qty,
        COALESCE(il.invoice_amount, 0) AS invoice_amount,
        COALESCE(sl.delivery_qty, 0) - COALESCE(il.invoice_qty, 0) AS uninvoiced_qty,
        COALESCE(sl.delivery_amount, 0) - COALESCE(il.invoice_amount, 0) AS uninvoiced_amount,
        sl.latest_delivery_no,
        sl.latest_delivery_date,
        il.latest_invoice_no,
        il.latest_invoice_date
    FROM sales_orders so
    JOIN sales_order_items soi ON soi.order_id = so.id
    LEFT JOIN customers c ON c.id = so.customer_id
    LEFT JOIN products p ON p.id = soi.product_id
    LEFT JOIN shipment_lines sl ON sl.order_id = so.id AND sl.product_id = soi.product_id
    LEFT JOIN invoice_lines il ON il.order_id = so.id AND il.product_id = soi.product_id
    WHERE {where_sql}
    ORDER BY so.order_date DESC, so.order_no, soi.id
    """

    rows = query_db(sql, params)

    # 计算匹配状态
    for row in rows:
        delivery_qty = Decimal(row.get("delivery_qty") or 0)
        invoice_qty = Decimal(row.get("invoice_qty") or 0)
        uninvoiced_qty = Decimal(row.get("uninvoiced_qty") or 0)
        order_qty = Decimal(row.get("order_qty") or 0)

        if delivery_qty == 0:
            row["match_status"] = "未发货"
        elif invoice_qty == 0:
            row["match_status"] = "未开票"
        elif invoice_qty > delivery_qty:
            row["match_status"] = "超开票"
        elif uninvoiced_qty > 0:
            row["match_status"] = "部分开票"
        else:
            row["match_status"] = "已开票"

    # 根据匹配状态筛选
    if filters.get("match_status"):
        status_filter = filters["match_status"]
        rows = [r for r in rows if r.get("match_status") == status_filter]

    return rows


def query_purchase_three_way_match(query_db, filters=None):
    """
    查询采购三单匹配（订单-入库-发票）

    返回字段：
    - 订单信息：order_no, order_date, supplier_name, product_code, product_name
    - 订单数量和金额：order_qty, order_amount
    - 入库数量和金额：receipt_qty, receipt_amount
    - 到票数量和金额：invoice_qty, invoice_amount
    - 未到票数量和金额：unreceived_invoice_qty, unreceived_invoice_amount
    - 差异状态：match_status（正常/超到票/欠到票/未入库）
    """
    filters = filters or {}
    where_clauses = ["po.status != '已作废'"]
    params = []

    # 筛选条件
    if filters.get("supplier_id"):
        where_clauses.append("po.supplier_id = %s")
        params.append(filters["supplier_id"])

    if filters.get("order_no"):
        where_clauses.append("po.order_no ILIKE %s")
        params.append(f"%{filters['order_no']}%")

    if filters.get("project_code"):
        where_clauses.append("po.project_code ILIKE %s")
        params.append(f"%{filters['project_code']}%")

    if filters.get("cabinet_no"):
        where_clauses.append("po.cabinet_no ILIKE %s")
        params.append(f"%{filters['cabinet_no']}%")

    if filters.get("start_date"):
        where_clauses.append("po.order_date >= %s")
        params.append(filters["start_date"])

    if filters.get("end_date"):
        where_clauses.append("po.order_date <= %s")
        params.append(filters["end_date"])

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    sql = f"""
    SELECT
        po.id AS order_id,
        po.order_no,
        po.order_date,
        po.supplier_id,
        s.name AS supplier_name,
        po.project_code,
        po.cabinet_no,
        poi.id AS order_item_id,
        poi.product_id,
        poi.product_code,
        poi.product_name,
        poi.specification,
        poi.unit,
        poi.quantity AS order_qty,
        poi.unit_price AS order_price,
        poi.amount AS order_amount,

        -- 入库信息（按订单行汇总）
        COALESCE(SUM(pri.quantity), 0) AS receipt_qty,
        COALESCE(SUM(pri.amount), 0) AS receipt_amount,

        -- 到票信息（按订单行汇总）
        COALESCE(SUM(pii.quantity), 0) AS invoice_qty,
        COALESCE(SUM(pii.amount_with_tax), 0) AS invoice_amount,

        -- 未到票数量和金额
        COALESCE(SUM(pri.quantity), 0) - COALESCE(SUM(pii.quantity), 0) AS unreceived_invoice_qty,
        COALESCE(SUM(pri.amount), 0) - COALESCE(SUM(pii.amount_with_tax), 0) AS unreceived_invoice_amount,

        -- 入库单信息（最新一条）
        MAX(pr.receipt_no) AS latest_receipt_no,
        MAX(pr.receipt_date) AS latest_receipt_date,

        -- 发票信息（最新一条）
        MAX(pi.invoice_no) AS latest_invoice_no,
        MAX(pi.invoice_date) AS latest_invoice_date

    FROM purchase_orders po
    JOIN purchase_order_items poi ON poi.purchase_order_id = po.id
    LEFT JOIN suppliers s ON s.id = po.supplier_id
    LEFT JOIN purchase_receipts pr ON pr.source_type = 'purchase_order' AND pr.source_id = po.id AND pr.status != '已作废'
    LEFT JOIN purchase_receipt_items pri ON pri.receipt_id = pr.id AND pri.product_id = poi.product_id
    LEFT JOIN purchase_invoice_items pii ON pii.purchase_order_id = po.id AND pii.item_code = poi.product_code
    LEFT JOIN purchase_invoices pi ON pi.id = pii.invoice_id AND pi.status != '已作废'

    WHERE {where_sql}
    GROUP BY po.id, poi.id, s.id
    ORDER BY po.order_date DESC, po.order_no, poi.line_no
    """

    sql = f"""
    WITH receipt_lines AS (
        SELECT
            pr.order_id,
            pri.product_id,
            SUM(COALESCE(pri.quantity, 0)) AS receipt_qty,
            SUM(COALESCE(pri.amount_with_tax, COALESCE(pri.quantity, 0) * COALESCE(pri.unit_cost, 0), 0)) AS receipt_amount,
            MAX(pr.receipt_no) AS latest_receipt_no,
            MAX(pr.receipt_date) AS latest_receipt_date
        FROM purchase_receipt_items pri
        JOIN purchase_receipts pr ON pri.receipt_id = pr.id
        GROUP BY pr.order_id, pri.product_id
    ),
    invoice_lines AS (
        SELECT
            pii.purchase_order_id AS order_id,
            pii.product_id,
            SUM(COALESCE(pii.quantity, 0)) AS invoice_qty,
            SUM(COALESCE(pii.amount_with_tax, pii.amount, 0)) AS invoice_amount,
            MAX(pi.invoice_no) AS latest_invoice_no,
            MAX(pi.invoice_date) AS latest_invoice_date
        FROM purchase_invoice_items pii
        JOIN purchase_invoices pi ON pi.id = pii.invoice_id
        WHERE COALESCE(pi.invoice_type, '') <> 'red'
        GROUP BY pii.purchase_order_id, pii.product_id
    )
    SELECT
        po.id AS order_id,
        po.order_no,
        po.order_date,
        po.supplier_id,
        s.name AS supplier_name,
        po.project_code,
        po.cabinet_no,
        poi.id AS order_item_id,
        poi.product_id,
        COALESCE(poi.material_code, p.code, '') AS product_code,
        COALESCE(poi.material_name, p.name, '') AS product_name,
        COALESCE(poi.material_spec, p.specification, '') AS specification,
        COALESCE(poi.material_unit, p.unit, '') AS unit,
        COALESCE(poi.quantity, 0) AS order_qty,
        COALESCE(poi.unit_price, 0) AS order_price,
        COALESCE(poi.amount_with_tax, poi.amount, 0) AS order_amount,
        COALESCE(rl.receipt_qty, 0) AS receipt_qty,
        COALESCE(rl.receipt_amount, 0) AS receipt_amount,
        COALESCE(il.invoice_qty, 0) AS invoice_qty,
        COALESCE(il.invoice_amount, 0) AS invoice_amount,
        COALESCE(rl.receipt_qty, 0) - COALESCE(il.invoice_qty, 0) AS unreceived_invoice_qty,
        COALESCE(rl.receipt_amount, 0) - COALESCE(il.invoice_amount, 0) AS unreceived_invoice_amount,
        rl.latest_receipt_no,
        rl.latest_receipt_date,
        il.latest_invoice_no,
        il.latest_invoice_date
    FROM purchase_orders po
    JOIN purchase_order_items poi ON poi.order_id = po.id
    LEFT JOIN suppliers s ON s.id = po.supplier_id
    LEFT JOIN products p ON p.id = poi.product_id
    LEFT JOIN receipt_lines rl ON rl.order_id = po.id AND rl.product_id = poi.product_id
    LEFT JOIN invoice_lines il ON il.order_id = po.id AND il.product_id = poi.product_id
    WHERE {where_sql}
    ORDER BY po.order_date DESC, po.order_no, poi.id
    """

    rows = query_db(sql, params)

    # 计算匹配状态
    for row in rows:
        receipt_qty = Decimal(row.get("receipt_qty") or 0)
        invoice_qty = Decimal(row.get("invoice_qty") or 0)
        unreceived_qty = Decimal(row.get("unreceived_invoice_qty") or 0)
        order_qty = Decimal(row.get("order_qty") or 0)

        if receipt_qty == 0:
            row["match_status"] = "未入库"
        elif invoice_qty == 0:
            row["match_status"] = "未到票"
        elif invoice_qty > receipt_qty:
            row["match_status"] = "超到票"
        elif unreceived_qty > 0:
            row["match_status"] = "部分到票"
        else:
            row["match_status"] = "已到票"

    # 根据匹配状态筛选
    if filters.get("match_status"):
        status_filter = filters["match_status"]
        rows = [r for r in rows if r.get("match_status") == status_filter]

    return rows


def query_uninvoiced_sales(query_db, filters=None):
    """
    查询未开票销售明细

    返回已发货但未开票（或部分开票）的销售订单明细
    """
    rows = query_sales_three_way_match(query_db, filters)
    # 只返回未开票数量 > 0 的记录
    return [r for r in rows if Decimal(r.get("uninvoiced_qty") or 0) > 0]


def query_unreceived_purchase_invoice(query_db, filters=None):
    """
    查询未到票采购明细

    返回已入库但未到票（或部分到票）的采购订单明细
    """
    rows = query_purchase_three_way_match(query_db, filters)
    # 只返回未到票数量 > 0 的记录
    return [r for r in rows if Decimal(r.get("unreceived_invoice_qty") or 0) > 0]
