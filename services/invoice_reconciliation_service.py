# -*- coding: utf-8 -*-
"""
发票勾稽报表服务
检查发票与订单、发货/入库单之间的数据一致性
识别超开票、金额差异等异常情况
"""
from decimal import Decimal


def query_invoice_reconciliation(query_db, kind, filters=None):
    """
    发票勾稽报表查询

    Args:
        query_db: 数据库查询函数
        kind: 'sales' 或 'purchase'
        filters: 筛选条件字典

    Returns:
        list: 勾稽结果列表，包含差异标识
    """
    filters = filters or {}

    if kind == 'sales':
        return _query_sales_invoice_reconciliation(query_db, filters)
    elif kind == 'purchase':
        return _query_purchase_invoice_reconciliation(query_db, filters)
    else:
        return []


def _query_sales_invoice_reconciliation(query_db, filters):
    """
    销售发票勾稽查询
    比对：发票数量 vs 发货数量，发票金额 vs 订单金额
    """
    where_clauses = ["1=1"]
    params = []

    # 筛选条件
    if filters.get('customer_id'):
        where_clauses.append("so.customer_id = %s")
        params.append(filters['customer_id'])

    if filters.get('order_no'):
        where_clauses.append("so.order_no LIKE %s")
        params.append(f"%{filters['order_no']}%")

    if filters.get('project_code'):
        where_clauses.append("so.project_code = %s")
        params.append(filters['project_code'])

    if filters.get('serial_no'):
        where_clauses.append("so.serial_no = %s")
        params.append(filters['serial_no'])

    if filters.get('start_date'):
        where_clauses.append("so.order_date >= %s")
        params.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses.append("so.order_date <= %s")
        params.append(filters['end_date'])

    if filters.get('has_variance') == '1':
        # 只显示有差异的记录
        where_clauses.append("(quantity_variance != 0 OR amount_variance != 0)")

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    WITH order_lines AS (
        SELECT
            soi.order_id AS sales_order_id,
            soi.product_id,
            COALESCE(MAX(soi.material_code), MAX(p.code), '') AS item_code,
            COALESCE(MAX(soi.material_name), MAX(p.name), '') AS item_name,
            COALESCE(MAX(soi.material_spec), MAX(p.specification), '') AS specification,
            COALESCE(MAX(soi.material_unit), MAX(p.unit), '') AS unit,
            SUM(COALESCE(soi.quantity, 0)) AS order_qty,
            SUM(COALESCE(soi.amount_with_tax, soi.amount, 0)) AS order_amount
        FROM sales_order_items soi
        LEFT JOIN products p ON soi.product_id = p.id
        GROUP BY soi.order_id, soi.product_id
    ),
    shipment_lines AS (
        SELECT
            ss.order_id AS sales_order_id,
            ssi.product_id,
            SUM(COALESCE(ssi.quantity, 0)) AS delivery_qty
        FROM sales_shipment_items ssi
        JOIN sales_shipments ss ON ssi.shipment_id = ss.id
        GROUP BY ss.order_id, ssi.product_id
    ),
    invoice_lines AS (
        SELECT
            sii.sales_order_id,
            sii.product_id,
            SUM(COALESCE(sii.quantity, 0)) AS invoice_qty,
            SUM(COALESCE(sii.amount_with_tax, sii.amount, 0)) AS invoice_amount
        FROM sales_invoice_items sii
        JOIN sales_invoices si ON sii.invoice_id = si.id
        WHERE COALESCE(si.invoice_type, '') <> 'red'
        GROUP BY sii.sales_order_id, sii.product_id
    )
    SELECT
        so.id AS order_id,
        so.order_no,
        so.order_date,
        c.name AS customer_name,
        so.project_code,
        so.serial_no,
        ol.item_code,
        ol.item_name,
        ol.specification,
        ol.unit,
        COALESCE(ol.order_qty, 0) AS order_qty,
        COALESCE(sl.delivery_qty, 0) AS delivery_qty,
        COALESCE(il.invoice_qty, 0) AS invoice_qty,
        COALESCE(ol.order_amount, 0) AS order_amount,
        COALESCE(il.invoice_amount, 0) AS invoice_amount,
        COALESCE(il.invoice_qty, 0) - COALESCE(sl.delivery_qty, 0) AS quantity_variance,
        COALESCE(il.invoice_amount, 0) - COALESCE(ol.order_amount, 0) AS amount_variance,
        CASE
            WHEN COALESCE(il.invoice_qty, 0) > COALESCE(sl.delivery_qty, 0) THEN 'over_invoiced'
            WHEN COALESCE(il.invoice_qty, 0) < COALESCE(sl.delivery_qty, 0) THEN 'under_invoiced'
            WHEN COALESCE(il.invoice_amount, 0) - COALESCE(ol.order_amount, 0) > 1 THEN 'amount_over'
            WHEN COALESCE(ol.order_amount, 0) - COALESCE(il.invoice_amount, 0) > 1 THEN 'amount_under'
            ELSE 'normal'
        END AS variance_status
    FROM sales_orders so
    JOIN customers c ON so.customer_id = c.id
    LEFT JOIN order_lines ol ON so.id = ol.sales_order_id
    LEFT JOIN shipment_lines sl ON so.id = sl.sales_order_id AND ol.product_id = sl.product_id
    LEFT JOIN invoice_lines il ON so.id = il.sales_order_id AND ol.product_id = il.product_id
    WHERE {where_sql}
    ORDER BY so.order_date DESC, so.order_no, ol.item_code
    """

    rows = query_db(sql, tuple(params))

    # 转换 Decimal 为 float
    result = []
    for row in rows:
        result.append({
            'order_id': row['order_id'],
            'order_no': row['order_no'],
            'order_date': row['order_date'],
            'customer_name': row['customer_name'],
            'project_code': row['project_code'],
            'serial_no': row['serial_no'],
            'item_code': row['item_code'],
            'item_name': row['item_name'],
            'specification': row['specification'],
            'unit': row['unit'],
            'order_qty': float(row['order_qty']) if row['order_qty'] else 0,
            'delivery_qty': float(row['delivery_qty']) if row['delivery_qty'] else 0,
            'invoice_qty': float(row['invoice_qty']) if row['invoice_qty'] else 0,
            'order_amount': float(row['order_amount']) if row['order_amount'] else 0,
            'invoice_amount': float(row['invoice_amount']) if row['invoice_amount'] else 0,
            'quantity_variance': float(row['quantity_variance']) if row['quantity_variance'] else 0,
            'amount_variance': float(row['amount_variance']) if row['amount_variance'] else 0,
            'variance_status': row['variance_status']
        })

    return result


def _query_purchase_invoice_reconciliation(query_db, filters):
    """
    采购发票勾稽查询
    比对：发票数量 vs 入库数量，发票金额 vs 订单金额
    """
    where_clauses = ["1=1"]
    params = []

    # 筛选条件
    if filters.get('supplier_id'):
        where_clauses.append("po.supplier_id = %s")
        params.append(filters['supplier_id'])

    if filters.get('order_no'):
        where_clauses.append("po.order_no LIKE %s")
        params.append(f"%{filters['order_no']}%")

    if filters.get('project_code'):
        where_clauses.append("po.project_code = %s")
        params.append(filters['project_code'])

    if filters.get('serial_no'):
        where_clauses.append("po.serial_no = %s")
        params.append(filters['serial_no'])

    if filters.get('start_date'):
        where_clauses.append("po.order_date >= %s")
        params.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses.append("po.order_date <= %s")
        params.append(filters['end_date'])

    if filters.get('has_variance') == '1':
        where_clauses.append("(quantity_variance != 0 OR amount_variance != 0)")

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    WITH order_lines AS (
        -- 采购订单明细
        SELECT
            poi.purchase_order_id,
            poi.item_code,
            SUM(poi.quantity) AS order_qty,
            SUM(poi.amount) AS order_amount
        FROM purchase_order_items poi
        GROUP BY poi.purchase_order_id, poi.item_code
    ),
    receipt_lines AS (
        -- 入库明细
        SELECT
            pri.source_id AS purchase_order_id,
            pri.item_code,
            SUM(pri.quantity) AS receipt_qty
        FROM purchase_receipt_items pri
        JOIN purchase_receipts pr ON pri.receipt_id = pr.id
        WHERE pr.source_type = 'purchase_order'
        GROUP BY pri.source_id, pri.item_code
    ),
    invoice_lines AS (
        -- 发票明细
        SELECT
            pii.purchase_order_id,
            pii.item_code,
            SUM(pii.quantity) AS invoice_qty,
            SUM(pii.amount_with_tax) AS invoice_amount
        FROM purchase_invoice_items pii
        JOIN purchase_invoices pi ON pii.invoice_id = pi.id
        WHERE pi.status != '已红冲' AND pi.invoice_type != 'red'
        GROUP BY pii.purchase_order_id, pii.item_code
    )
    SELECT
        po.id AS order_id,
        po.order_no,
        po.order_date,
        s.name AS supplier_name,
        po.project_code,
        po.serial_no,
        ol.item_code,
        m.name AS item_name,
        m.specification,
        m.unit,
        COALESCE(ol.order_qty, 0) AS order_qty,
        COALESCE(rl.receipt_qty, 0) AS receipt_qty,
        COALESCE(il.invoice_qty, 0) AS invoice_qty,
        COALESCE(ol.order_amount, 0) AS order_amount,
        COALESCE(il.invoice_amount, 0) AS invoice_amount,

        -- 数量差异：发票数量 - 入库数量
        COALESCE(il.invoice_qty, 0) - COALESCE(rl.receipt_qty, 0) AS quantity_variance,

        -- 金额差异：发票金额 - 订单金额
        COALESCE(il.invoice_amount, 0) - COALESCE(ol.order_amount, 0) AS amount_variance,

        -- 差异状态
        CASE
            WHEN COALESCE(il.invoice_qty, 0) > COALESCE(rl.receipt_qty, 0) THEN '超到票'
            WHEN COALESCE(il.invoice_qty, 0) < COALESCE(rl.receipt_qty, 0) THEN '欠到票'
            WHEN COALESCE(il.invoice_amount, 0) - COALESCE(ol.order_amount, 0) > 1 THEN '金额超额'
            WHEN COALESCE(ol.order_amount, 0) - COALESCE(il.invoice_amount, 0) > 1 THEN '金额欠额'
            ELSE '正常'
        END AS variance_status

    FROM purchase_orders po
    JOIN suppliers s ON po.supplier_id = s.id
    LEFT JOIN order_lines ol ON po.id = ol.purchase_order_id
    LEFT JOIN receipt_lines rl ON po.id = rl.purchase_order_id AND ol.item_code = rl.item_code
    LEFT JOIN invoice_lines il ON po.id = il.purchase_order_id AND ol.item_code = il.item_code
    LEFT JOIN materials m ON ol.item_code = m.code
    WHERE {where_sql}
    ORDER BY po.order_date DESC, po.order_no, ol.item_code
    """

    sql = f"""
    WITH order_lines AS (
        SELECT
            poi.order_id AS purchase_order_id,
            poi.product_id,
            COALESCE(MAX(poi.material_code), MAX(p.code), '') AS item_code,
            COALESCE(MAX(poi.material_name), MAX(p.name), '') AS item_name,
            COALESCE(MAX(poi.material_spec), MAX(p.specification), '') AS specification,
            COALESCE(MAX(poi.material_unit), MAX(p.unit), '') AS unit,
            SUM(COALESCE(poi.quantity, 0)) AS order_qty,
            SUM(COALESCE(poi.amount_with_tax, poi.amount, 0)) AS order_amount
        FROM purchase_order_items poi
        LEFT JOIN products p ON poi.product_id = p.id
        GROUP BY poi.order_id, poi.product_id
    ),
    receipt_lines AS (
        SELECT
            pr.order_id AS purchase_order_id,
            pri.product_id,
            SUM(COALESCE(pri.quantity, 0)) AS receipt_qty
        FROM purchase_receipt_items pri
        JOIN purchase_receipts pr ON pri.receipt_id = pr.id
        GROUP BY pr.order_id, pri.product_id
    ),
    invoice_lines AS (
        SELECT
            pii.purchase_order_id,
            pii.product_id,
            SUM(COALESCE(pii.quantity, 0)) AS invoice_qty,
            SUM(COALESCE(pii.amount_with_tax, pii.amount, 0)) AS invoice_amount
        FROM purchase_invoice_items pii
        JOIN purchase_invoices pi ON pii.invoice_id = pi.id
        WHERE COALESCE(pi.invoice_type, '') <> 'red'
        GROUP BY pii.purchase_order_id, pii.product_id
    )
    SELECT
        po.id AS order_id,
        po.order_no,
        po.order_date,
        s.name AS supplier_name,
        po.project_code,
        po.serial_no,
        ol.item_code,
        ol.item_name,
        ol.specification,
        ol.unit,
        COALESCE(ol.order_qty, 0) AS order_qty,
        COALESCE(rl.receipt_qty, 0) AS receipt_qty,
        COALESCE(il.invoice_qty, 0) AS invoice_qty,
        COALESCE(ol.order_amount, 0) AS order_amount,
        COALESCE(il.invoice_amount, 0) AS invoice_amount,
        COALESCE(il.invoice_qty, 0) - COALESCE(rl.receipt_qty, 0) AS quantity_variance,
        COALESCE(il.invoice_amount, 0) - COALESCE(ol.order_amount, 0) AS amount_variance,
        CASE
            WHEN COALESCE(il.invoice_qty, 0) > COALESCE(rl.receipt_qty, 0) THEN 'over_invoiced'
            WHEN COALESCE(il.invoice_qty, 0) < COALESCE(rl.receipt_qty, 0) THEN 'under_invoiced'
            WHEN COALESCE(il.invoice_amount, 0) - COALESCE(ol.order_amount, 0) > 1 THEN 'amount_over'
            WHEN COALESCE(ol.order_amount, 0) - COALESCE(il.invoice_amount, 0) > 1 THEN 'amount_under'
            ELSE 'normal'
        END AS variance_status
    FROM purchase_orders po
    JOIN suppliers s ON po.supplier_id = s.id
    LEFT JOIN order_lines ol ON po.id = ol.purchase_order_id
    LEFT JOIN receipt_lines rl ON po.id = rl.purchase_order_id AND ol.product_id = rl.product_id
    LEFT JOIN invoice_lines il ON po.id = il.purchase_order_id AND ol.product_id = il.product_id
    WHERE {where_sql}
    ORDER BY po.order_date DESC, po.order_no, ol.item_code
    """

    rows = query_db(sql, tuple(params))

    # 转换 Decimal 为 float
    result = []
    for row in rows:
        result.append({
            'order_id': row['order_id'],
            'order_no': row['order_no'],
            'order_date': row['order_date'],
            'supplier_name': row['supplier_name'],
            'project_code': row['project_code'],
            'serial_no': row['serial_no'],
            'item_code': row['item_code'],
            'item_name': row['item_name'],
            'specification': row['specification'],
            'unit': row['unit'],
            'order_qty': float(row['order_qty']) if row['order_qty'] else 0,
            'receipt_qty': float(row['receipt_qty']) if row['receipt_qty'] else 0,
            'invoice_qty': float(row['invoice_qty']) if row['invoice_qty'] else 0,
            'order_amount': float(row['order_amount']) if row['order_amount'] else 0,
            'invoice_amount': float(row['invoice_amount']) if row['invoice_amount'] else 0,
            'quantity_variance': float(row['quantity_variance']) if row['quantity_variance'] else 0,
            'amount_variance': float(row['amount_variance']) if row['amount_variance'] else 0,
            'variance_status': row['variance_status']
        })

    return result


def get_invoice_reconciliation_summary(rows):
    """
    获取勾稽报表汇总统计

    Returns:
        dict: 汇总数据
    """
    total_records = len(rows)
    normal_count = sum(1 for r in rows if r.get('variance_status') in ('正常', 'normal'))
    variance_count = total_records - normal_count

    # 按差异状态分类统计
    status_counts = {}
    for row in rows:
        status = row.get('variance_status')
        status_counts[status] = status_counts.get(status, 0) + 1

    # 金额差异汇总
    total_amount_variance = sum(abs(r.get('amount_variance') or 0) for r in rows)

    return {
        'total_records': total_records,
        'normal_count': normal_count,
        'variance_count': variance_count,
        'variance_rate': f"{variance_count / total_records * 100:.1f}%" if total_records > 0 else "0%",
        'status_counts': status_counts,
        'total_amount_variance': total_amount_variance
    }
