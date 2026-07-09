#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
财务应收应付增强功能审计

审计内容：
1. Schema 完整性：新增表和字段是否存在
2. 数据完整性：settled_amount 和 unapplied_amount 是否正确计算
3. 核销一致性：核销明细总额是否与 settled_amount 匹配
4. 余额一致性：应收/应付余额是否与核销后余额匹配
5. 退款处理：退款单是否正确处理资金流水
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db import get_db_connection


def main():
    print("=" * 80)
    print("财务应收应付增强功能审计")
    print("=" * 80)
    print()

    conn = get_db_connection()
    cur = conn.cursor()

    issues = []
    warnings = []

    # 1. Schema 完整性检查
    print("1. Schema 完整性检查")
    print("-" * 80)

    # 检查 customer_receipts 必需字段
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'customer_receipts'
          AND column_name IN ('settled_amount', 'unapplied_amount')
    """)
    receipt_cols = [row[0] for row in cur.fetchall()]
    if 'settled_amount' not in receipt_cols:
        issues.append("customer_receipts 表缺少 settled_amount 字段")
    else:
        print("✓ customer_receipts.settled_amount 存在")

    if 'unapplied_amount' not in receipt_cols:
        issues.append("customer_receipts 表缺少 unapplied_amount 字段")
    else:
        print("✓ customer_receipts.unapplied_amount 存在")

    # 检查 supplier_payments 必需字段
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'supplier_payments'
          AND column_name IN ('settled_amount', 'unapplied_amount')
    """)
    payment_cols = [row[0] for row in cur.fetchall()]
    if 'settled_amount' not in payment_cols:
        issues.append("supplier_payments 表缺少 settled_amount 字段")
    else:
        print("✓ supplier_payments.settled_amount 存在")

    if 'unapplied_amount' not in payment_cols:
        issues.append("supplier_payments 表缺少 unapplied_amount 字段")
    else:
        print("✓ supplier_payments.unapplied_amount 存在")

    # 检查新表
    new_tables = {
        'customer_receivable_items': '应收明细表',
        'supplier_payable_items': '应付明细表',
        'finance_payment_requests': '付款申请单表',
        'finance_receivable_bills': '应收票据表',
        'finance_payable_bills': '应付票据表'
    }

    for table, desc in new_tables.items():
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables WHERE table_name = %s
            )
        """, (table,))
        if cur.fetchone()[0]:
            print(f"✓ {desc} ({table}) 已创建")
        else:
            warnings.append(f"{desc} ({table}) 未创建（可选功能）")

    print()

    # 2. 数据完整性检查
    print("2. 数据完整性检查")
    print("-" * 80)

    # 检查收款单 settled_amount 和 unapplied_amount 是否与 amount 匹配
    cur.execute("""
        SELECT
            COUNT(*) AS mismatch_count,
            SUM(ABS(amount - (COALESCE(settled_amount, 0) + COALESCE(unapplied_amount, 0)))) AS total_diff
        FROM customer_receipts
        WHERE status IN ('posted', 'confirmed', '已确认', '已审核')
          AND ABS(amount - (COALESCE(settled_amount, 0) + COALESCE(unapplied_amount, 0))) > 0.01
    """)
    receipt_mismatch = cur.fetchone()
    if receipt_mismatch[0] > 0:
        issues.append(f"发现 {receipt_mismatch[0]} 条收款单 amount != settled_amount + unapplied_amount，差异总额: {receipt_mismatch[1]}")
    else:
        print(f"✓ 所有收款单 amount = settled_amount + unapplied_amount")

    # 检查付款单
    cur.execute("""
        SELECT
            COUNT(*) AS mismatch_count,
            SUM(ABS(amount - (COALESCE(settled_amount, 0) + COALESCE(unapplied_amount, 0)))) AS total_diff
        FROM supplier_payments
        WHERE status IN ('posted', 'confirmed', '已确认', '已审核')
          AND ABS(amount - (COALESCE(settled_amount, 0) + COALESCE(unapplied_amount, 0))) > 0.01
    """)
    payment_mismatch = cur.fetchone()
    if payment_mismatch[0] > 0:
        issues.append(f"发现 {payment_mismatch[0]} 条付款单 amount != settled_amount + unapplied_amount，差异总额: {payment_mismatch[1]}")
    else:
        print(f"✓ 所有付款单 amount = settled_amount + unapplied_amount")

    print()

    # 3. 核销一致性检查
    print("3. 核销一致性检查")
    print("-" * 80)

    # 检查收款单 settled_amount 是否与核销明细总额匹配
    cur.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                r.id,
                r.receipt_no,
                COALESCE(r.settled_amount, 0) AS receipt_settled,
                COALESCE(SUM(s.applied_amount), 0) AS settlement_total
            FROM customer_receipts r
            LEFT JOIN customer_receipt_settlements s ON s.receipt_id = r.id
            WHERE r.status IN ('posted', 'confirmed', '已确认', '已审核')
            GROUP BY r.id
            HAVING ABS(COALESCE(r.settled_amount, 0) - COALESCE(SUM(s.applied_amount), 0)) > 0.01
        ) AS mismatches
    """)
    receipt_settlement_mismatch = cur.fetchone()[0]
    if receipt_settlement_mismatch > 0:
        issues.append(f"发现 {receipt_settlement_mismatch} 条收款单 settled_amount 与核销明细不匹配")
        # 显示前5条不匹配记录
        cur.execute("""
            SELECT
                r.id,
                r.receipt_no,
                r.settled_amount,
                COALESCE(SUM(s.applied_amount), 0) AS settlement_total
            FROM customer_receipts r
            LEFT JOIN customer_receipt_settlements s ON s.receipt_id = r.id
            WHERE r.status IN ('posted', 'confirmed', '已确认', '已审核')
            GROUP BY r.id
            HAVING ABS(COALESCE(r.settled_amount, 0) - COALESCE(SUM(s.applied_amount), 0)) > 0.01
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(f"  ⚠ {row[1]}: settled_amount={row[2]}, 核销明细总额={row[3]}")
    else:
        print(f"✓ 所有收款单 settled_amount 与核销明细匹配")

    # 检查付款单
    cur.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT
                p.id,
                p.payment_no,
                COALESCE(p.settled_amount, 0) AS payment_settled,
                COALESCE(SUM(s.applied_amount), 0) AS settlement_total
            FROM supplier_payments p
            LEFT JOIN supplier_payment_settlements s ON s.payment_id = p.id
            WHERE p.status IN ('posted', 'confirmed', '已确认', '已审核')
            GROUP BY p.id
            HAVING ABS(COALESCE(p.settled_amount, 0) - COALESCE(SUM(s.applied_amount), 0)) > 0.01
        ) AS mismatches
    """)
    payment_settlement_mismatch = cur.fetchone()[0]
    if payment_settlement_mismatch > 0:
        issues.append(f"发现 {payment_settlement_mismatch} 条付款单 settled_amount 与核销明细不匹配")
        cur.execute("""
            SELECT
                p.id,
                p.payment_no,
                p.settled_amount,
                COALESCE(SUM(s.applied_amount), 0) AS settlement_total
            FROM supplier_payments p
            LEFT JOIN supplier_payment_settlements s ON s.payment_id = p.id
            WHERE p.status IN ('posted', 'confirmed', '已确认', '已审核')
            GROUP BY p.id
            HAVING ABS(COALESCE(p.settled_amount, 0) - COALESCE(SUM(s.applied_amount), 0)) > 0.01
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(f"  ⚠ {row[1]}: settled_amount={row[2]}, 核销明细总额={row[3]}")
    else:
        print(f"✓ 所有付款单 settled_amount 与核销明细匹配")

    print()

    # 4. 余额一致性检查
    print("4. 余额一致性检查")
    print("-" * 80)

    # 检查应收余额是否正确
    cur.execute("""
        SELECT COUNT(*)
        FROM customer_receivables
        WHERE ABS(COALESCE(balance, 0) - (COALESCE(amount, 0) - COALESCE(received_amount, 0))) > 0.01
    """)
    receivable_balance_mismatch = cur.fetchone()[0]
    if receivable_balance_mismatch > 0:
        issues.append(f"发现 {receivable_balance_mismatch} 条应收账款余额不正确")
    else:
        print(f"✓ 所有应收账款余额正确")

    # 检查应付余额是否正确
    cur.execute("""
        SELECT COUNT(*)
        FROM supplier_payables
        WHERE ABS(COALESCE(balance, 0) - (COALESCE(amount, 0) - COALESCE(paid_amount, 0))) > 0.01
    """)
    payable_balance_mismatch = cur.fetchone()[0]
    if payable_balance_mismatch > 0:
        issues.append(f"发现 {payable_balance_mismatch} 条应付账款余额不正确")
    else:
        print(f"✓ 所有应付账款余额正确")

    print()

    # 5. 退款处理检查
    print("5. 退款处理检查")
    print("-" * 80)

    # 检查退款单是否正确生成负数资金流水
    cur.execute("""
        SELECT COUNT(*)
        FROM customer_receipts r
        JOIN cash_bank_journal_entries j ON j.source_type = 'customer_receipt' AND j.source_id = r.id
        WHERE r.receipt_kind IN ('receipt_refund', 'advance_refund', 'other_income_refund')
          AND r.status IN ('posted', 'confirmed', '已确认', '已审核')
          AND j.direction = 'out'
          AND j.amount < 0
    """)
    refund_flow_count = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM customer_receipts
        WHERE receipt_kind IN ('receipt_refund', 'advance_refund', 'other_income_refund')
          AND status IN ('posted', 'confirmed', '已确认', '已审核')
    """)
    total_refund_count = cur.fetchone()[0]

    if total_refund_count > 0:
        print(f"退款单总数: {total_refund_count}")
        print(f"已生成负数资金流水: {refund_flow_count}")
        if refund_flow_count < total_refund_count:
            warnings.append(f"{total_refund_count - refund_flow_count} 条退款单未生成负数资金流水")
        else:
            print(f"✓ 所有退款单已生成负数资金流水")
    else:
        print("暂无退款单数据")

    print()

    # 汇总结果
    print("=" * 80)
    print("审计结果汇总")
    print("=" * 80)
    print()

    if issues:
        print(f"❌ 发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print()

    if warnings:
        print(f"⚠ 发现 {len(warnings)} 个警告:")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. {warning}")
        print()

    if not issues and not warnings:
        print("✓ 所有检查通过，未发现问题")
        print()

    cur.close()
    conn.close()

    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
