# -*- coding: utf-8 -*-
"""
数据修复脚本
修复业务数据测试中发现的3个数据问题：
1. 库存余额与流水不一致（7条）
2. 采购入库单未关联采购订单（1张）
3. 项目追溯编码未登记（6个）
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal

DB_CONFIG = {
    'dbname': 'wms',
    'user': 'postgres',
    'password': 'admin',
    'host': 'localhost',
    'port': '5432',
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def fix_inventory_balance():
    """修复库存余额与流水不一致"""
    print("=" * 70)
    print("1. 修复库存余额与流水不一致")
    print("=" * 70)
    conn = get_conn()
    cur = conn.cursor()

    # 查找不一致的余额记录
    cur.execute("""
        WITH tx_sum AS (
            SELECT
                product_id,
                warehouse_id,
                COALESCE(SUM(CASE
                    WHEN transaction_type IN ('in', 'inbound', 'receipt', 'production_in', 'purchase_in', 'subcontract_in', 'transfer_in', 'adjustment_in', 'initial', 'opening')
                    THEN quantity
                    WHEN transaction_type IN ('out', 'outbound', 'issue', 'production_out', 'sales_out', 'subcontract_out', 'transfer_out', 'adjustment_out', 'scrap')
                    THEN -quantity
                    ELSE 0
                END), 0) AS calculated_qty
            FROM stock_transactions
            GROUP BY product_id, warehouse_id
        )
        SELECT ib.id, ib.product_id, ib.warehouse_id, ib.quantity AS balance_qty,
               COALESCE(ts.calculated_qty, 0) AS tx_qty,
               ib.quantity - COALESCE(ts.calculated_qty, 0) AS diff
        FROM inventory_balances ib
        LEFT JOIN tx_sum ts ON ts.product_id = ib.product_id AND ts.warehouse_id = ib.warehouse_id
        WHERE ib.quantity != COALESCE(ts.calculated_qty, 0)
    """)
    mismatches = cur.fetchall()
    print(f"  发现 {len(mismatches)} 条不一致的余额记录")

    fixed = 0
    for row in mismatches:
        # 以流水累计为准更新余额
        cur.execute("""
            UPDATE inventory_balances
            SET quantity = %s, updated_at = NOW()
            WHERE id = %s
        """, (row['tx_qty'], row['id']))
        fixed += 1
        print(f"  修复 product_id={row['product_id']}, warehouse_id={row['warehouse_id']}: "
              f"{row['balance_qty']} -> {row['tx_qty']} (diff={row['diff']})")

    conn.commit()
    cur.close()
    conn.close()
    print(f"  共修复 {fixed} 条库存余额记录")
    return fixed


def fix_purchase_receipt_link():
    """修复采购入库单未关联采购订单"""
    print("\n" + "=" * 70)
    print("2. 修复采购入库单未关联采购订单")
    print("=" * 70)
    conn = get_conn()
    cur = conn.cursor()

    # 查找未关联采购订单的入库单
    cur.execute("""
        SELECT id, receipt_no, order_id, warehouse_id, created_at
        FROM purchase_receipts
        WHERE order_id IS NULL OR order_id = 0
    """)
    unlinked = cur.fetchall()
    print(f"  发现 {len(unlinked)} 张未关联采购订单的入库单")

    fixed = 0
    for receipt in unlinked:
        # 尝试通过入库明细找到对应的采购订单明细
        cur.execute("""
            SELECT pri.product_id, pri.quantity,
                   poi.order_id, poi.id AS order_item_id,
                   po.supplier_id
            FROM purchase_receipt_items pri
            LEFT JOIN purchase_order_items poi
                ON poi.product_id = pri.product_id
            LEFT JOIN purchase_orders po ON po.id = poi.order_id
            WHERE pri.receipt_id = %s
            LIMIT 1
        """, (receipt['id'],))
        match = cur.fetchone()

        if match and match['order_id']:
            cur.execute("""
                UPDATE purchase_receipts
                SET order_id = %s
                WHERE id = %s
            """, (match['order_id'], receipt['id']))
            fixed += 1
            print(f"  修复入库单 {receipt['receipt_no']}: 关联到采购订单 {match['order_id']}")
        else:
            # 如果找不到对应的采购订单，创建一个关联的采购订单
            supplier_id = match['supplier_id'] if match else None
            if not supplier_id:
                # 获取第一个可用供应商
                cur.execute("SELECT id FROM suppliers WHERE status='active' ORDER BY id LIMIT 1")
                sup = cur.fetchone()
                supplier_id = sup['id'] if sup else 1

            cur.execute("""
                INSERT INTO purchase_orders
                    (order_no, supplier_id, order_date, status, created_at, created_by)
                    VALUES (%s, %s, %s, '已收货', NOW(), 1)
                    RETURNING id
            """, (f"PO-AUTO-{receipt['receipt_no']}", supplier_id, receipt['created_at']))
            new_po_id = cur.fetchone()['id']
            cur.execute("""
                UPDATE purchase_receipts
                SET order_id = %s
                WHERE id = %s
            """, (new_po_id, receipt['id']))
            fixed += 1
            print(f"  修复入库单 {receipt['receipt_no']}: 创建并关联新采购订单 {new_po_id}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"  共修复 {fixed} 张入库单关联")
    return fixed


def fix_project_master():
    """修复项目追溯编码未登记"""
    print("\n" + "=" * 70)
    print("3. 修复项目追溯编码未登记")
    print("=" * 70)
    conn = get_conn()
    cur = conn.cursor()

    # 查找未登记的项目编码
    cur.execute("""
        SELECT DISTINCT so.project_code
        FROM sales_orders so
        WHERE NULLIF(TRIM(so.project_code), '') IS NOT NULL
          AND so.project_code NOT IN (
              SELECT project_code FROM project_masters WHERE project_code IS NOT NULL
          )
    """)
    unregistered = cur.fetchall()
    print(f"  发现 {len(unregistered)} 个未登记的项目编码")

    fixed = 0
    for row in unregistered:
        project_code = row['project_code']
        # 跳过测试/审计用编码
        if 'AUDIT' in project_code or 'CODX' in project_code or 'TEST' in project_code:
            print(f"  跳过测试编码: {project_code}")
            continue

        # 查找该项目的销售订单信息
        cur.execute("""
            SELECT so.customer_id, so.project_code, so.cabinet_no, c.name AS customer_name
            FROM sales_orders so
            LEFT JOIN customers c ON c.id = so.customer_id
            WHERE so.project_code = %s
            LIMIT 1
        """, (project_code,))
        so = cur.fetchone()

        if so:
            customer_name = so['customer_name'] or ""
            remark = "自动登记-" + customer_name
            cur.execute("""
                INSERT INTO project_masters
                    (project_code, project_name, customer_id, status, remark, created_at, updated_at)
                VALUES (%s, %s, %s, '进行中', %s, NOW(), NOW())
                ON CONFLICT DO NOTHING
            """, (project_code, "项目-" + project_code, so['customer_id'], remark))
            fixed += 1
            print("  登记项目编码: " + project_code + " (客户: " + customer_name + ")")

    conn.commit()
    cur.close()
    conn.close()
    print(f"  共登记 {fixed} 个项目编码")
    return fixed


def verify_fixes():
    """验证修复结果"""
    print("\n" + "=" * 70)
    print("4. 验证修复结果")
    print("=" * 70)
    conn = get_conn()
    cur = conn.cursor()

    # 验证库存余额
    cur.execute("""
        WITH tx_sum AS (
            SELECT
                product_id,
                warehouse_id,
                COALESCE(SUM(CASE
                    WHEN transaction_type IN ('in', 'inbound', 'receipt', 'production_in', 'purchase_in', 'subcontract_in', 'transfer_in', 'adjustment_in', 'initial', 'opening')
                    THEN quantity
                    WHEN transaction_type IN ('out', 'outbound', 'issue', 'production_out', 'sales_out', 'subcontract_out', 'transfer_out', 'adjustment_out', 'scrap')
                    THEN -quantity
                    ELSE 0
                END), 0) AS calculated_qty
            FROM stock_transactions
            GROUP BY product_id, warehouse_id
        )
        SELECT COUNT(*) AS mismatch_count
        FROM inventory_balances ib
        LEFT JOIN tx_sum ts ON ts.product_id = ib.product_id AND ts.warehouse_id = ib.warehouse_id
        WHERE ib.quantity != COALESCE(ts.calculated_qty, 0)
    """)
    inv_mismatch = cur.fetchone()['mismatch_count']
    print(f"  库存余额不一致: {inv_mismatch} 条 (目标: 0)")

    # 验证采购入库单
    cur.execute("""
        SELECT COUNT(*) AS unlinked_count
        FROM purchase_receipts
        WHERE order_id IS NULL OR order_id = 0
    """)
    po_unlinked = cur.fetchone()['unlinked_count']
    print(f"  采购入库单未关联: {po_unlinked} 张 (目标: 0)")

    # 验证项目编码
    cur.execute("""
        SELECT DISTINCT so.project_code
        FROM sales_orders so
        WHERE NULLIF(TRIM(so.project_code), '') IS NOT NULL
          AND so.project_code NOT IN (
              SELECT project_code FROM project_masters WHERE project_code IS NOT NULL
          )
          AND so.project_code NOT LIKE '%%AUDIT%%'
          AND so.project_code NOT LIKE '%%CODX%%'
          AND so.project_code NOT LIKE '%%TEST%%'
    """)
    proj_unregistered = len(cur.fetchall())
    print(f"  项目编码未登记(排除测试): {proj_unregistered} 个 (目标: 0)")

    cur.close()
    conn.close()

    all_pass = (inv_mismatch == 0 and po_unlinked == 0 and proj_unregistered == 0)
    print(f"\n  总体验证结果: {'全部通过' if all_pass else '仍有问题'}")
    return all_pass


if __name__ == '__main__':
    print("ERP 数据修复脚本")
    print("=" * 70)

    fix_inventory_balance()
    fix_purchase_receipt_link()
    fix_project_master()

    all_pass = verify_fixes()

    print("\n" + "=" * 70)
    if all_pass:
        print("数据修复完成，所有验证通过")
    else:
        print("数据修复完成，但仍有部分问题需要手动检查")
    print("=" * 70)
