#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
应用发票管理增强迁移

此脚本执行以下操作：
1. 应用 20260616_002_finance_invoice_enhancement 迁移
2. 验证新字段和新表是否正确创建
3. 检查发票与应收应付关联表是否创建成功
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.app_runtime import connect_db
from services.schema_migrations import apply_schema_migrations, MIGRATIONS


def main():
    print("=" * 80)
    print("发票管理增强迁移")
    print("=" * 80)
    print()

    # 连接数据库
    print("连接数据库...")
    try:
        db_config = {
            "host": os.environ.get("PG_HOST", "localhost"),
            "port": int(os.environ.get("PG_PORT", "5432")),
            "database": os.environ.get("PG_DATABASE", "erp"),
            "user": os.environ.get("PG_USER", "postgres"),
            "password": os.environ.get("PG_PASSWORD", ""),
        }
        conn = connect_db(db_config, cursor_factory=None)
        cur = conn.cursor()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return 1

    # 查找目标迁移
    target_migration = None
    for version, sql in MIGRATIONS:
        if version == "20260616_002_finance_invoice_enhancement":
            target_migration = (version, sql)
            break

    if not target_migration:
        print("❌ 未找到迁移 20260616_002_finance_invoice_enhancement")
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
            import traceback
            traceback.print_exc()
            cur.close()
            conn.close()
            return 1

    print()
    print("验证新字段...")

    # 验证销售发票新字段
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'sales_invoices'
          AND column_name IN ('invoice_code', 'invoice_type', 'tax_rate', 'invoice_status',
                              'receivable_id', 'buyer_name', 'buyer_tax_no')
        ORDER BY column_name
    """)
    sales_invoice_cols = [row[0] for row in cur.fetchall()]
    print(f"✓ sales_invoices 表新字段数: {len(sales_invoice_cols)}")
    if len(sales_invoice_cols) < 5:
        print(f"  ⚠ 预期至少 7 个新字段，实际: {sales_invoice_cols}")

    # 验证采购发票新字段
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'purchase_invoices'
          AND column_name IN ('invoice_code', 'invoice_type', 'tax_rate', 'invoice_status',
                              'payable_id', 'seller_name', 'certification_status')
        ORDER BY column_name
    """)
    purchase_invoice_cols = [row[0] for row in cur.fetchall()]
    print(f"✓ purchase_invoices 表新字段数: {len(purchase_invoice_cols)}")
    if len(purchase_invoice_cols) < 5:
        print(f"  ⚠ 预期至少 7 个新字段，实际: {purchase_invoice_cols}")

    # 验证新表是否创建
    new_tables = [
        ('sales_invoice_items', '销售发票明细表'),
        ('purchase_invoice_items', '采购发票明细表'),
        ('sales_invoice_receivables', '销售发票应收关联表'),
        ('purchase_invoice_payables', '采购发票应付关联表')
    ]

    print()
    print("验证新表...")
    for table, desc in new_tables:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table,))
        exists = cur.fetchone()[0]
        status = "✓" if exists else "✗"
        print(f"{status} {desc} ({table}): {'已创建' if exists else '未创建'}")

    # 验证应收应付表是否有发票关联字段
    print()
    print("验证应收应付发票关联字段...")
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'customer_receivables' AND column_name = 'invoice_id'
    """)
    if cur.fetchone():
        print("✓ customer_receivables.invoice_id 已创建")
    else:
        print("✗ customer_receivables.invoice_id 未创建")

    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'supplier_payables' AND column_name = 'invoice_id'
    """)
    if cur.fetchone():
        print("✓ supplier_payables.invoice_id 已创建")
    else:
        print("✗ supplier_payables.invoice_id 未创建")

    # 检查现有发票数据
    print()
    print("检查现有发票数据...")

    cur.execute("SELECT COUNT(*) FROM sales_invoices")
    sales_invoice_count = cur.fetchone()[0]
    print(f"销售发票总数: {sales_invoice_count}")

    cur.execute("SELECT COUNT(*) FROM purchase_invoices")
    purchase_invoice_count = cur.fetchone()[0]
    print(f"采购发票总数: {purchase_invoice_count}")

    if sales_invoice_count > 0:
        cur.execute("""
            SELECT COUNT(*) FROM sales_invoices WHERE receivable_id IS NOT NULL
        """)
        linked_count = cur.fetchone()[0]
        print(f"  已关联应收单的销售发票: {linked_count}")

    if purchase_invoice_count > 0:
        cur.execute("""
            SELECT COUNT(*) FROM purchase_invoices WHERE payable_id IS NOT NULL
        """)
        linked_count = cur.fetchone()[0]
        print(f"  已关联应付单的采购发票: {linked_count}")

    cur.close()
    conn.close()

    print()
    print("=" * 80)
    print("✓ 发票管理增强迁移完成")
    print("=" * 80)
    print()
    print("下一步:")
    print("1. 开发销售发票审核后自动生成应收单的逻辑")
    print("2. 开发采购发票审核后自动生成应付单的逻辑")
    print("3. 开发三单匹配报表（订单-发货/入库-发票）")
    print("4. 开发发票勾稽报表")
    return 0


if __name__ == "__main__":
    sys.exit(main())
