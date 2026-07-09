"""
财务模块表结构诊断脚本
检查当前数据库中存在的财务相关表和字段
"""
import psycopg2
import os

PG_HOST = "127.0.0.1"
PG_PORT = 5432
PG_DATABASE = "wms"
PG_USER = "wms_user"
PG_PASSWORD = os.environ.get("PG_PASSWORD", "admin")

def main():
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    )
    cur = conn.cursor()

    print("=" * 80)
    print("财务模块表结构诊断")
    print("=" * 80)

    # 检查财务相关表
    finance_tables = [
        'vouchers', 'voucher_lines', 'voucher_entries',
        'gl_accounts', 'gl_account_balances', 'chart_of_accounts',
        'period_closing', 'project_cost_ledger', 'serial_cost_ledger',
        'inventory_costing', 'inventory_transactions', 'financial_report_log',
        'sales_invoices', 'sales_invoice_items',
        'purchase_invoices', 'purchase_invoice_items',
        'customer_receipts', 'supplier_payments',
        'accounting_periods', 'finance_period_closes', 'financial_reports'
    ]

    print("\n1. 表存在性检查")
    print("-" * 80)
    existing_tables = []
    missing_tables = []

    for table in finance_tables:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=%s
            )
        """, (table,))
        exists = cur.fetchone()[0]
        if exists:
            existing_tables.append(table)
            print(f"✓ {table}")
        else:
            missing_tables.append(table)
            print(f"✗ {table} (缺失)")

    # 检查发票表字段
    print("\n2. 发票表字段检查")
    print("-" * 80)

    for table in ['sales_invoice_items', 'purchase_invoice_items']:
        if table in existing_tables:
            print(f"\n{table} 表字段:")
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name=%s
                ORDER BY ordinal_position
            """, (table,))
            columns = cur.fetchall()
            for col_name, col_type in columns:
                print(f"  - {col_name} ({col_type})")

            # 检查关键字段
            col_names = [c[0] for c in columns]
            if 'total_amount' in col_names:
                print(f"  ✓ 包含 total_amount 字段")
            else:
                print(f"  ✗ 缺少 total_amount 字段")

            if 'amount_with_tax' in col_names:
                print(f"  ✓ 包含 amount_with_tax 字段")
            else:
                print(f"  ✗ 缺少 amount_with_tax 字段")

    # 统计
    print("\n" + "=" * 80)
    print(f"总结: 存在 {len(existing_tables)} 张表, 缺失 {len(missing_tables)} 张表")
    if missing_tables:
        print(f"\n缺失的表: {', '.join(missing_tables)}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
