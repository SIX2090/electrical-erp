# -*- coding: utf-8 -*-
"""
应用财务模块第四期 Schema 迁移
存货核算与成本管理

使用方法:
    python scripts/apply_finance_inventory_costing_schema.py
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import psycopg2
from psycopg2.extras import RealDictCursor
from services.env_config import get_pg_password
import os


def get_db_connection():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        database=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor
    )


def check_migration_applied(conn, migration_id):
    """检查迁移是否已应用"""
    with conn.cursor() as cur:
        # 确保 schema_migrations 表存在
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                migration_id VARCHAR(255) UNIQUE NOT NULL,
                migration_name VARCHAR(255),
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute(
            "SELECT id FROM schema_migrations WHERE migration_id = %s",
            (migration_id,)
        )
        return cur.fetchone() is not None


def record_migration(conn, migration_id, migration_name):
    """记录迁移"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO schema_migrations (migration_id, migration_name)
            VALUES (%s, %s)
            ON CONFLICT (migration_id) DO NOTHING
            """,
            (migration_id, migration_name)
        )


def apply_migration():
    """应用迁移"""
    # 导入迁移模块
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "migration",
        BASE_DIR / "migrations" / "20260616_004_finance_inventory_costing.py"
    )
    migration_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_module)

    MIGRATION_ID = migration_module.MIGRATION_ID
    MIGRATION_NAME = migration_module.MIGRATION_NAME
    get_migration_sql = migration_module.get_migration_sql

    print(f"=" * 80)
    print(f"应用迁移: {MIGRATION_ID}")
    print(f"迁移名称: {MIGRATION_NAME}")
    print(f"=" * 80)

    conn = get_db_connection()

    try:
        # 检查是否已应用
        if check_migration_applied(conn, MIGRATION_ID):
            print(f"\n⚠️  迁移 {MIGRATION_ID} 已经应用过，跳过")
            return

        print(f"\n开始应用迁移...")

        # 获取SQL语句
        sql_statements = get_migration_sql()

        print(f"共 {len(sql_statements)} 条SQL语句\n")

        # 执行每条SQL
        for idx, sql in enumerate(sql_statements, 1):
            sql_preview = sql.strip()[:100].replace('\n', ' ')
            print(f"[{idx}/{len(sql_statements)}] 执行: {sql_preview}...")

            with conn.cursor() as cur:
                cur.execute(sql)

        # 记录迁移
        record_migration(conn, MIGRATION_ID, MIGRATION_NAME)

        # 提交事务
        conn.commit()

        print(f"\n✅ 迁移应用成功！")
        print(f"\n创建的表:")
        print(f"  - inventory_costing (存货成本核算表)")
        print(f"  - project_cost_ledger (项目成本台账)")
        print(f"  - serial_cost_ledger (机号成本台账)")
        print(f"  - project_revenue_ledger (项目收入台账)")

        print(f"\n扩展的表:")
        print(f"  - products (新增: current_cost, standard_cost, last_purchase_cost, cost_method)")
        print(f"  - inventory_transactions (新增: unit_cost, total_cost, avg_cost_after)")

        print(f"\n创建的索引: 16个")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 迁移应用失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


def verify_migration():
    """验证迁移"""
    print(f"\n" + "=" * 80)
    print(f"验证迁移结果")
    print(f"=" * 80)

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # 验证表是否创建
            tables = [
                'inventory_costing',
                'project_cost_ledger',
                'serial_cost_ledger',
                'project_revenue_ledger'
            ]

            print(f"\n检查表...")
            for table in tables:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt
                    FROM information_schema.tables
                    WHERE table_name = %s
                    """,
                    (table,)
                )
                result = cur.fetchone()
                if result['cnt'] > 0:
                    print(f"  ✅ {table}")
                else:
                    print(f"  ❌ {table} - 未找到")

            # 验证 products 表字段
            print(f"\n检查 products 表字段...")
            product_columns = [
                'current_cost',
                'standard_cost',
                'last_purchase_cost',
                'cost_method'
            ]

            for column in product_columns:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt
                    FROM information_schema.columns
                    WHERE table_name = 'products' AND column_name = %s
                    """,
                    (column,)
                )
                result = cur.fetchone()
                if result['cnt'] > 0:
                    print(f"  ✅ products.{column}")
                else:
                    print(f"  ❌ products.{column} - 未找到")

            # 验证 inventory_transactions 表字段
            print(f"\n检查 inventory_transactions 表字段...")
            transaction_columns = [
                'unit_cost',
                'total_cost',
                'avg_cost_after'
            ]

            for column in transaction_columns:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt
                    FROM information_schema.columns
                    WHERE table_name = 'inventory_transactions' AND column_name = %s
                    """,
                    (column,)
                )
                result = cur.fetchone()
                if result['cnt'] > 0:
                    print(f"  ✅ inventory_transactions.{column}")
                else:
                    print(f"  ❌ inventory_transactions.{column} - 未找到")

            # 验证索引
            print(f"\n检查索引...")
            indexes = [
                'idx_inventory_costing_product',
                'idx_inventory_costing_date',
                'idx_project_cost_project',
                'idx_serial_cost_serial',
                'idx_project_revenue_project'
            ]

            for index in indexes:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt
                    FROM pg_indexes
                    WHERE indexname = %s
                    """,
                    (index,)
                )
                result = cur.fetchone()
                if result['cnt'] > 0:
                    print(f"  ✅ {index}")
                else:
                    print(f"  ❌ {index} - 未找到")

            print(f"\n✅ 验证完成")

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        conn.close()


if __name__ == '__main__':
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║   财务模块第四期 - 存货核算与成本管理 Schema 迁移           ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    apply_migration()
    verify_migration()

    print(f"\n" + "=" * 80)
    print(f"迁移完成！")
    print(f"=" * 80)
    print(f"\n下一步:")
    print(f"  1. 开发存货核算服务 (services/inventory_costing_service.py)")
    print(f"  2. 开发项目成本服务 (services/project_cost_service.py)")
    print(f"  3. 开发机号成本服务 (services/serial_cost_service.py)")
    print(f"\n")
