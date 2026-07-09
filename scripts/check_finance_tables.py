"""
检查财务模块所需的数据库表是否存在
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from services.env_config import get_pg_password


def get_db_connection():
    """获取数据库连接"""
    PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
    PG_PORT = int(os.environ.get("PG_PORT", "5432"))
    PG_DATABASE = os.environ.get("PG_DATABASE", "wms")
    PG_USER = os.environ.get("PG_USER", "wms_user")
    PG_PASSWORD = get_pg_password()

    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    )


def check_table_exists(cursor, table_name):
    """检查表是否存在"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = %s
        )
    """, (table_name,))
    return cursor.fetchone()[0]


def get_table_columns(cursor, table_name):
    """获取表的列信息"""
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return cursor.fetchall()


def main():
    """主函数"""

    # 财务模块需要的核心表
    required_tables = [
        # 核心凭证表
        ('vouchers', '凭证主表'),
        ('voucher_entries', '凭证分录表'),
        ('voucher_lines', '凭证分录表(备选名)'),

        # 会计科目表
        ('chart_of_accounts', '会计科目表'),
        ('gl_accounts', '总账科目表(备选名)'),

        # 余额表
        ('gl_account_balances', '科目余额表'),

        # 期末处理
        ('period_closing', '期末结账表'),
        ('accounting_periods', '会计期间表'),

        # 成本核算
        ('project_cost_ledger', '项目成本台账'),
        ('serial_cost_ledger', '机号成本台账'),
        ('inventory_costing', '存货核算表'),
        ('inventory_transactions', '库存交易明细表'),

        # 业务单据
        ('sales_invoices', '销售发票表'),
        ('purchase_invoices', '采购发票表'),
        ('customer_receipts', '客户收款表'),
        ('supplier_payments', '供应商付款表'),

        # 辅助核算
        ('cost_objects', '成本对象表'),
        ('financial_report_log', '财务报表生成日志'),
    ]

    print("=" * 80)
    print("检查财务模块数据库表")
    print("=" * 80)
    print()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        exists_tables = []
        missing_tables = []

        for table_name, description in required_tables:
            exists = check_table_exists(cursor, table_name)

            if exists:
                exists_tables.append((table_name, description))
                print(f"[EXISTS] {table_name:30} - {description}")
            else:
                missing_tables.append((table_name, description))
                print(f"[MISSING] {table_name:30} - {description}")

        print()
        print("=" * 80)
        print("统计结果")
        print("=" * 80)
        print(f"存在的表: {len(exists_tables)}")
        print(f"缺失的表: {len(missing_tables)}")
        print()

        if missing_tables:
            print("缺失的表清单:")
            for table_name, description in missing_tables:
                print(f"  - {table_name} ({description})")
            print()
            print("建议: 创建缺失表的迁移文件并执行")
        else:
            print("所有必需的表都已存在!")

        # 检查关键表的字段
        if check_table_exists(cursor, 'chart_of_accounts'):
            print()
            print("=" * 80)
            print("chart_of_accounts 表字段:")
            print("=" * 80)
            columns = get_table_columns(cursor, 'chart_of_accounts')
            for col_name, col_type, nullable in columns:
                print(f"  {col_name:30} {col_type:20} {'NULL' if nullable == 'YES' else 'NOT NULL'}")

        if check_table_exists(cursor, 'vouchers'):
            print()
            print("=" * 80)
            print("vouchers 表字段:")
            print("=" * 80)
            columns = get_table_columns(cursor, 'vouchers')
            for col_name, col_type, nullable in columns:
                print(f"  {col_name:30} {col_type:20} {'NULL' if nullable == 'YES' else 'NOT NULL'}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[ERROR] 检查失败: {e}")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
