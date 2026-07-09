"""
财务模块修复 - 阶段 3：补齐数据库表
通过 schema_migrations.py 添加缺失的财务表
"""
import os
import shutil
from datetime import datetime

def backup_file(filepath):
    """备份文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✓ 已备份: {backup_path}")
    return backup_path

def add_migration_to_schema():
    """在 schema_migrations.py 末尾添加财务表迁移"""
    filepath = "services/schema_migrations.py"

    # 备份
    backup_file(filepath)

    # 读取文件
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已经添加过
    if "20260617_001_finance_missing_tables" in content:
        print("⚠ 迁移已存在，跳过添加")
        return

    # 查找 MIGRATIONS 列表的结束位置
    # 找到最后一个 ),
    import re

    # 查找 MIGRATIONS = [ ... ]
    match = re.search(r'MIGRATIONS\s*=\s*\[(.*)\]', content, re.DOTALL)
    if not match:
        print("✗ 错误: 无法找到 MIGRATIONS 列表")
        return

    migrations_content = match.group(1)

    # 找到最后一个完整的迁移元组
    last_migration_end = migrations_content.rfind("),")

    if last_migration_end == -1:
        print("✗ 错误: 无法找到迁移列表结束位置")
        return

    # 准备新的迁移内容
    new_migration = '''
    (
        "20260617_001_finance_missing_tables",
        """
        -- 1. 会计科目表
        CREATE TABLE IF NOT EXISTS chart_of_accounts (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) UNIQUE NOT NULL,
            name VARCHAR(160) NOT NULL,
            account_type VARCHAR(80),
            parent_id INTEGER REFERENCES chart_of_accounts(id),
            is_leaf BOOLEAN DEFAULT TRUE,
            balance_direction VARCHAR(20) DEFAULT 'debit',
            status VARCHAR(50) DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 2. 总账科目余额表
        CREATE TABLE IF NOT EXISTS gl_account_balances (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            beginning_balance NUMERIC(16, 2) DEFAULT 0,
            debit_amount NUMERIC(16, 2) DEFAULT 0,
            credit_amount NUMERIC(16, 2) DEFAULT 0,
            ending_balance NUMERIC(16, 2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (account_id, period_year, period_month)
        );
        CREATE INDEX IF NOT EXISTS idx_gl_account_balances_period
            ON gl_account_balances(period_year, period_month);

        -- 3. 凭证分录表
        CREATE TABLE IF NOT EXISTS voucher_entries (
            id SERIAL PRIMARY KEY,
            voucher_id INTEGER NOT NULL,
            line_no INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            debit_amount NUMERIC(16, 2) DEFAULT 0,
            credit_amount NUMERIC(16, 2) DEFAULT 0,
            summary TEXT,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            partner_type VARCHAR(50),
            partner_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_voucher_entries_voucher
            ON voucher_entries(voucher_id);

        -- 4. 期末结账记录表
        CREATE TABLE IF NOT EXISTS period_closing (
            id SERIAL PRIMARY KEY,
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            closing_date DATE,
            status VARCHAR(50) DEFAULT 'open',
            revenue NUMERIC(16, 2) DEFAULT 0,
            cost NUMERIC(16, 2) DEFAULT 0,
            gross_profit NUMERIC(16, 2) DEFAULT 0,
            closed_by INTEGER,
            closed_at TIMESTAMP,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (period_year, period_month)
        );
        CREATE INDEX IF NOT EXISTS idx_period_closing_period
            ON period_closing(period_year, period_month);

        -- 5. 项目成本台账
        CREATE TABLE IF NOT EXISTS project_cost_ledger (
            id SERIAL PRIMARY KEY,
            project_code VARCHAR(120) NOT NULL,
            project_name VARCHAR(255),
            cost_date DATE NOT NULL,
            cost_type VARCHAR(80),
            source_type VARCHAR(80),
            source_no VARCHAR(120),
            description TEXT,
            cost_amount NUMERIC(16, 2) DEFAULT 0,
            quantity NUMERIC(14, 3),
            unit_cost NUMERIC(16, 4),
            department_id INTEGER,
            employee_id INTEGER,
            recorded_by INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_project
            ON project_cost_ledger(project_code);
        CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_date
            ON project_cost_ledger(cost_date);

        -- 6. 序列号成本台账
        CREATE TABLE IF NOT EXISTS serial_cost_ledger (
            id SERIAL PRIMARY KEY,
            serial_no VARCHAR(120) NOT NULL,
            cost_date DATE NOT NULL,
            cost_type VARCHAR(80),
            source_type VARCHAR(80),
            source_no VARCHAR(120),
            description TEXT,
            cost_amount NUMERIC(16, 2) DEFAULT 0,
            quantity NUMERIC(14, 3),
            unit_cost NUMERIC(16, 4),
            project_code VARCHAR(120),
            recorded_by INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_serial_cost_ledger_serial
            ON serial_cost_ledger(serial_no);
        CREATE INDEX IF NOT EXISTS idx_serial_cost_ledger_date
            ON serial_cost_ledger(cost_date);

        -- 7. 库存成本计算表
        CREATE TABLE IF NOT EXISTS inventory_costing (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL,
            costing_date DATE NOT NULL,
            costing_method VARCHAR(50) DEFAULT 'weighted_avg',
            unit_cost NUMERIC(16, 4) DEFAULT 0,
            quantity NUMERIC(14, 3) DEFAULT 0,
            total_cost NUMERIC(16, 2) DEFAULT 0,
            warehouse_id INTEGER,
            location_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_product
            ON inventory_costing(product_id);

        -- 8. 库存交易明细表
        CREATE TABLE IF NOT EXISTS inventory_transactions (
            id SERIAL PRIMARY KEY,
            transaction_date DATE NOT NULL,
            product_id INTEGER NOT NULL,
            transaction_type VARCHAR(80),
            quantity NUMERIC(14, 3) DEFAULT 0,
            unit_cost NUMERIC(16, 4) DEFAULT 0,
            amount NUMERIC(16, 2) DEFAULT 0,
            warehouse_id INTEGER,
            location_id INTEGER,
            reference_no VARCHAR(120),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_transactions_date
            ON inventory_transactions(transaction_date);
        CREATE INDEX IF NOT EXISTS idx_inventory_transactions_product
            ON inventory_transactions(product_id);

        -- 9. 财务报表日志
        CREATE TABLE IF NOT EXISTS financial_report_log (
            id SERIAL PRIMARY KEY,
            report_type VARCHAR(80) NOT NULL,
            period_year INTEGER,
            period_month INTEGER,
            generated_by INTEGER,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            report_data JSONB,
            remark TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_financial_report_log_type
            ON financial_report_log(report_type);
        """,
    ),'''

    # 插入新迁移
    insert_pos = match.start(1) + last_migration_end + 2  # +2 for "),
    new_content = content[:insert_pos] + new_migration + content[insert_pos:]

    # 写回文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✓ 已添加迁移: 20260617_001_finance_missing_tables")
    print(f"✓ {filepath} 修复完成")

def main():
    print("=" * 80)
    print("财务模块修复 - 阶段 3：补齐数据库表")
    print("=" * 80)
    print()

    # 检查当前目录
    if not os.path.exists("services/schema_migrations.py"):
        print("✗ 错误: 找不到 services/schema_migrations.py，请在 ERP 项目根目录运行")
        return 1

    print("⚠ 警告: 此操作将修改数据库结构")
    print("⚠ 强烈建议先备份数据库:")
    print("   .venv\\Scripts\\python.exe scripts\\pg_backup.py --output backups\\pre_finance_fix_20260617.dump")
    print()

    response = input("是否继续? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("已取消")
        return 0

    print()
    print("开始添加迁移...")
    print()

    try:
        add_migration_to_schema()
        print()
        print("=" * 80)
        print("✓ 阶段 3 修复完成")
        print("=" * 80)
        print()
        print("下一步:")
        print("1. 重启 ERP 应用以应用迁移: restart_erp.cmd")
        print("   或手动触发: .venv\\Scripts\\python.exe -c \"from app import create_app; create_app()\"")
        print("2. 运行验证: .venv\\Scripts\\python.exe diagnose_finance_tables.py")
        print("   预期: 所有 9 张表显示 ✓")
        return 0
    except Exception as e:
        print(f"\n✗ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
