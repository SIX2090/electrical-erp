"""
应用财务模块补充表迁移脚本
Migration: 20260616_006 - 补充财务模块缺失的核心表
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from services.env_config import get_pg_password

# 直接导入迁移模块
import importlib.util
spec = importlib.util.spec_from_file_location(
    "migration_20260616_006",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "migrations", "20260616_006_finance_missing_tables.py")
)
migration_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration_module)

get_migration_info = migration_module.get_migration_info
get_sql_statements = migration_module.get_sql_statements


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


def apply_migration():
    """应用数据库迁移"""

    # 获取迁移信息
    info = get_migration_info()

    print("=" * 80)
    print(f"应用迁移: {info['id']}")
    print(f"迁移名称: {info['name']}")
    print(f"迁移描述: {info['description']}")
    print("=" * 80)
    print()

    # 连接数据库
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("[OK] 数据库连接成功")
        print()
    except Exception as e:
        print(f"[ERROR] 数据库连接失败: {e}")
        return False

    # 获取SQL语句
    sql_statements = get_sql_statements()
    print(f"开始应用迁移...")
    print(f"共 {len(sql_statements)} 条SQL语句")
    print()

    # 执行SQL语句
    success_count = 0
    failed_count = 0

    for i, sql in enumerate(sql_statements, 1):
        # 跳过空语句
        if not sql.strip():
            continue

        try:
            # 显示执行进度（简化显示）
            sql_preview = sql.strip().split('\n')[0][:60]
            print(f"[{i}/{len(sql_statements)}] 执行: {sql_preview}...", end='')

            cursor.execute(sql)
            conn.commit()

            print(" [OK]")
            success_count += 1

        except Exception as e:
            print(f" [ERROR]")
            print(f"    错误: {e}")
            failed_count += 1

            # 如果是关键SQL失败，选择是否继续
            if "CREATE TABLE" in sql.upper() or "ALTER TABLE" in sql.upper():
                print("    这是一个关键操作，是否继续? (y/n): ", end='')
                choice = input().strip().lower()
                if choice != 'y':
                    print("    迁移已中止")
                    cursor.close()
                    conn.close()
                    return False

    # 关闭连接
    cursor.close()
    conn.close()

    # 输出结果
    print()
    print("=" * 80)
    print("迁移执行完成")
    print("=" * 80)
    print(f"成功: {success_count} 条")
    print(f"失败: {failed_count} 条")
    print()

    if failed_count == 0:
        print("[SUCCESS] 迁移应用成功！")
        print()
        print("创建的表:")
        print("  - gl_account_balances (科目余额表)")
        print("  - project_cost_ledger (项目成本台账)")
        print("  - cabinet_cost_ledger (柜号成本台账)")
        print("  - inventory_costing (存货核算表)")
        print("  - inventory_transactions (库存交易明细表)")
        print()
        print("下一步:")
        print("  1. 手动将迁移标记为已应用")
        print("  2. 修复代码中的BUG（query_db/execute_db混用等）")
        print("  3. 测试财务功能")
        return True
    else:
        print("[WARNING] 部分SQL执行失败，请检查错误信息")
        return False


def rollback_migration():
    """回滚迁移（删除创建的表）"""

    print("=" * 80)
    print("回滚迁移: 20260616_006")
    print("=" * 80)
    print()
    print("[WARNING] 这将删除以下表及其所有数据:")
    print("  - gl_account_balances")
    print("  - project_cost_ledger")
    print("  - cabinet_cost_ledger")
    print("  - inventory_costing")
    print("  - inventory_transactions")
    print()
    print("是否继续? (yes/no): ", end='')

    choice = input().strip().lower()
    if choice != 'yes':
        print("回滚已取消")
        return False

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 删除表
        rollback_sql = [
            "DROP TABLE IF EXISTS inventory_transactions CASCADE",
            "DROP TABLE IF EXISTS inventory_costing CASCADE",
            "DROP TABLE IF EXISTS cabinet_cost_ledger CASCADE",
            "DROP TABLE IF EXISTS project_cost_ledger CASCADE",
            "DROP TABLE IF EXISTS gl_account_balances CASCADE",
        ]

        for sql in rollback_sql:
            print(f"执行: {sql}")
            cursor.execute(sql)
            conn.commit()

        cursor.close()
        conn.close()

        print()
        print("[SUCCESS] 回滚成功")
        return True

    except Exception as e:
        print(f"[ERROR] 回滚失败: {e}")
        return False


if __name__ == "__main__":
    import sys

    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        apply_migration()
