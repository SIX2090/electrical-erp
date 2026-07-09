#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
应用财务应收应付增强迁移

此脚本执行以下操作：
1. 应用 20260616_001_finance_ar_ap_enhancement 迁移
2. 验证新字段是否正确添加
3. 检查现有收款单和付款单的 settled_amount 和 unapplied_amount 是否正确初始化
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db import get_db_connection
from services.schema_migrations import apply_schema_migrations, MIGRATIONS


def main():
    print("=" * 80)
    print("财务应收应付增强迁移")
    print("=" * 80)
    print()

    # 连接数据库
    print("连接数据库...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return 1

    # 查找目标迁移
    target_migration = None
    for version, sql in MIGRATIONS:
        if version == "20260616_001_finance_ar_ap_enhancement":
            target_migration = (version, sql)
            break

    if not target_migration:
        print("❌ 未找到迁移 20260616_001_finance_ar_ap_enhancement")
        cur.close()
        conn.close()
        return 1

    # 检查迁移是否已应用
    cur.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (target_migration[0],))
    if cur.fetchone():
        print(f"✓ 迁移 {target_migration[0]} 已经应用过")
    else:
        print(f"应用迁移 {target_migration[0]}...")
        try:
            applied = apply_schema_migrations(cur, [target_migration])
            conn.commit()
            if applied:
                print(f"✓ 迁移 {target_migration[0]} 应用成功")
            else:
                print(f"✓ 迁移 {target_migration[0]} 已存在，跳过")
        except Exception as e:
            conn.rollback()
            print(f"❌ 迁移应用失败: {e}")
            cur.close()
            conn.close()
            return 1

    print()
    print("验证新字段...")

    # 验证 customer_receipts 表字段
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'customer_receipts'
          AND column_name IN ('settled_amount', 'unapplied_amount')
        ORDER BY column_name
    """)
    receipt_columns = cur.fetchall()
    print(f"✓ customer_receipts 表新字段: {receipt_columns}")

    # 验证 supplier_payments 表字段
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'supplier_payments'
          AND column_name IN ('settled_amount', 'unapplied_amount')
        ORDER BY column_name
    """)
    payment_columns = cur.fetchall()
    print(f"✓ supplier_payments 表新字段: {payment_columns}")

    # 验证新表是否创建
    new_tables = [
        'customer_receivable_items',
        'supplier_payable_items',
        'finance_payment_requests',
        'finance_receivable_bills',
        'finance_payable_bills'
    ]

    for table in new_tables:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table,))
        exists = cur.fetchone()[0]
        status = "✓" if exists else "✗"
        print(f"{status} 表 {table}: {'已创建' if exists else '未创建'}")

    print()
    print("检查现有数据...")

    # 检查收款单统计
    cur.execute("""
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE settled_amount > 0) AS with_settled,
            COUNT(*) FILTER (WHERE unapplied_amount > 0) AS with_unapplied,
            SUM(COALESCE(settled_amount, 0)) AS total_settled,
            SUM(COALESCE(unapplied_amount, 0)) AS total_unapplied
        FROM customer_receipts
        WHERE status IN ('posted', 'confirmed', '已确认', '已审核')
    """)
    receipt_stats = cur.fetchone()
    print(f"收款单统计:")
    print(f"  总数: {receipt_stats[0]}")
    print(f"  有已核销金额: {receipt_stats[1]}")
    print(f"  有未核销金额: {receipt_stats[2]}")
    print(f"  已核销总额: {receipt_stats[3]}")
    print(f"  未核销总额: {receipt_stats[4]}")

    # 检查付款单统计
    cur.execute("""
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE settled_amount > 0) AS with_settled,
            COUNT(*) FILTER (WHERE unapplied_amount > 0) AS with_unapplied,
            SUM(COALESCE(settled_amount, 0)) AS total_settled,
            SUM(COALESCE(unapplied_amount, 0)) AS total_unapplied
        FROM supplier_payments
        WHERE status IN ('posted', 'confirmed', '已确认', '已审核')
    """)
    payment_stats = cur.fetchone()
    print(f"付款单统计:")
    print(f"  总数: {payment_stats[0]}")
    print(f"  有已核销金额: {payment_stats[1]}")
    print(f"  有未核销金额: {payment_stats[2]}")
    print(f"  已核销总额: {payment_stats[3]}")
    print(f"  未核销总额: {payment_stats[4]}")

    # 检查应收余额与已核销金额是否匹配
    cur.execute("""
        SELECT
            r.id,
            r.receipt_no,
            r.amount,
            r.settled_amount AS receipt_settled,
            COALESCE(SUM(s.applied_amount), 0) AS settlement_total
        FROM customer_receipts r
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id = r.id
        WHERE r.status IN ('posted', 'confirmed', '已确认', '已审核')
        GROUP BY r.id
        HAVING ABS(COALESCE(r.settled_amount, 0) - COALESCE(SUM(s.applied_amount), 0)) > 0.01
        LIMIT 5
    """)
    receipt_mismatches = cur.fetchall()
    if receipt_mismatches:
        print(f"⚠ 发现 {len(receipt_mismatches)} 条收款单 settled_amount 不匹配:")
        for row in receipt_mismatches:
            print(f"  {row[1]}: settled_amount={row[3]}, 实际核销={row[4]}")
    else:
        print(f"✓ 所有收款单 settled_amount 匹配")

    # 检查应付余额与已核销金额是否匹配
    cur.execute("""
        SELECT
            p.id,
            p.payment_no,
            p.amount,
            p.settled_amount AS payment_settled,
            COALESCE(SUM(s.applied_amount), 0) AS settlement_total
        FROM supplier_payments p
        LEFT JOIN supplier_payment_settlements s ON s.payment_id = p.id
        WHERE p.status IN ('posted', 'confirmed', '已确认', '已审核')
        GROUP BY p.id
        HAVING ABS(COALESCE(p.settled_amount, 0) - COALESCE(SUM(s.applied_amount), 0)) > 0.01
        LIMIT 5
    """)
    payment_mismatches = cur.fetchall()
    if payment_mismatches:
        print(f"⚠ 发现 {len(payment_mismatches)} 条付款单 settled_amount 不匹配:")
        for row in payment_mismatches:
            print(f"  {row[1]}: settled_amount={row[3]}, 实际核销={row[4]}")
    else:
        print(f"✓ 所有付款单 settled_amount 匹配")

    cur.close()
    conn.close()

    print()
    print("=" * 80)
    print("✓ 财务应收应付增强迁移完成")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
