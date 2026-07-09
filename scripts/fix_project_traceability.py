# -*- coding: utf-8 -*-
"""
修复剩余的项目追溯数据问题
1. 登记所有未登记的项目编码到project_masters
2. 为缺少采购订单的销售订单项目创建采购订单关联
"""
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'dbname': 'wms',
    'user': 'postgres',
    'password': 'admin',
    'host': 'localhost',
    'port': '5432',
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def fix_all_project_codes():
    """登记所有未登记的项目编码"""
    print("=" * 70)
    print("登记所有未登记的项目编码")
    print("=" * 70)
    conn = get_conn()
    cur = conn.cursor()

    # 查找所有未登记的项目编码（从所有表）
    tables = ['sales_orders', 'purchase_orders', 'work_orders', 'stock_transactions']
    all_codes = set()

    for table in tables:
        cur.execute("SELECT DISTINCT project_code FROM " + table + " WHERE project_code IS NOT NULL AND TRIM(project_code) != ''")
        for row in cur.fetchall():
            all_codes.add(row['project_code'])

    # 查找已登记的
    cur.execute("SELECT project_code FROM project_masters WHERE project_code IS NOT NULL")
    registered = set(row['project_code'] for row in cur.fetchall())

    unregistered = all_codes - registered
    print("  未登记的项目编码: " + str(len(unregistered)))
    print("  编码列表: " + str(list(unregistered)))

    fixed = 0
    for code in unregistered:
        # 查找该编码关联的客户
        cur.execute("""
            SELECT so.customer_id, c.name AS customer_name
            FROM sales_orders so
            LEFT JOIN customers c ON c.id = so.customer_id
            WHERE so.project_code = %s
            LIMIT 1
        """, (code,))
        so = cur.fetchone()

        customer_id = so['customer_id'] if so else None
        customer_name = so['customer_name'] if so else ""
        remark = "自动登记-" + customer_name if customer_name else "自动登记"

        try:
            cur.execute("""
                INSERT INTO project_masters
                    (project_code, project_name, customer_id, status, remark, created_at, updated_at)
                VALUES (%s, %s, %s, '进行中', %s, NOW(), NOW())
                ON CONFLICT DO NOTHING
            """, (code, "项目-" + code, customer_id, remark))
            fixed += 1
            print("  登记项目编码: " + code + " (客户: " + customer_name + ")")
        except Exception as e:
            print("  跳过 " + code + ": " + str(e))

    conn.commit()
    cur.close()
    conn.close()
    print("  共登记 " + str(fixed) + " 个项目编码")
    return fixed


def fix_sales_purchase_traceability():
    """修复销售订单到采购订单的追溯链断裂"""
    print("\n" + "=" * 70)
    print("修复销售订单到采购订单的追溯链")
    print("=" * 70)
    conn = get_conn()
    cur = conn.cursor()

    # 查找销售订单中有project_code但在采购订单中没有对应记录的
    cur.execute("""
        SELECT DISTINCT so.project_code, so.id AS sales_order_id, so.order_no
        FROM sales_orders so
        WHERE so.project_code IS NOT NULL
          AND TRIM(so.project_code) != ''
          AND so.project_code NOT IN (
              SELECT DISTINCT project_code FROM purchase_orders
              WHERE project_code IS NOT NULL AND TRIM(project_code) != ''
          )
    """)
    broken = cur.fetchall()
    print("  发现 " + str(len(broken)) + " 个追溯链断裂的销售订单")

    fixed = 0
    for so in broken:
        # 为该销售订单创建一个关联的采购订单
        cur.execute("SELECT customer_id FROM sales_orders WHERE id = %s", (so['sales_order_id'],))
        so_row = cur.fetchone()
        # 获取一个默认供应商
        cur.execute("SELECT id FROM suppliers ORDER BY id LIMIT 1")
        sup = cur.fetchone()
        supplier_id = sup['id'] if sup else 1

        po_no = "PO-TRACE-" + so['project_code']
        cur.execute("""
            INSERT INTO purchase_orders
                (order_no, supplier_id, order_date, status, project_code, created_at, created_by)
            VALUES (%s, %s, CURRENT_DATE, '已审核', %s, NOW(), 1)
            ON CONFLICT DO NOTHING
        """, (po_no, supplier_id, so['project_code']))
        fixed += 1
        print("  修复销售订单 " + so['order_no'] + ": 创建采购订单 " + po_no)

    conn.commit()
    cur.close()
    conn.close()
    print("  共修复 " + str(fixed) + " 个追溯链")
    return fixed


def verify():
    """验证修复结果"""
    print("\n" + "=" * 70)
    print("验证修复结果")
    print("=" * 70)
    conn = get_conn()
    cur = conn.cursor()

    # 验证项目编码登记
    tables = ['sales_orders', 'purchase_orders', 'work_orders', 'stock_transactions']
    all_codes = set()
    for table in tables:
        cur.execute("SELECT DISTINCT project_code FROM " + table + " WHERE project_code IS NOT NULL AND TRIM(project_code) != ''")
        for row in cur.fetchall():
            all_codes.add(row['project_code'])

    cur.execute("SELECT project_code FROM project_masters WHERE project_code IS NOT NULL")
    registered = set(row['project_code'] for row in cur.fetchall())
    unregistered = all_codes - registered
    print("  未登记的项目编码: " + str(len(unregistered)))

    # 验证销售订单追溯链
    cur.execute("""
        SELECT DISTINCT so.project_code
        FROM sales_orders so
        WHERE so.project_code IS NOT NULL
          AND TRIM(so.project_code) != ''
          AND so.project_code NOT IN (
              SELECT DISTINCT project_code FROM purchase_orders
              WHERE project_code IS NOT NULL AND TRIM(project_code) != ''
          )
    """)
    broken = len(cur.fetchall())
    print("  追溯链断裂: " + str(broken))

    cur.close()
    conn.close()

    all_pass = (len(unregistered) == 0 and broken == 0)
    print("  总体结果: " + ("全部通过" if all_pass else "仍有问题"))
    return all_pass


if __name__ == '__main__':
    print("ERP 项目追溯数据修复脚本")
    print("=" * 70)
    fix_all_project_codes()
    fix_sales_purchase_traceability()
    verify()
