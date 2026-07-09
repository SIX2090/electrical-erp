"""触发 P0 引擎实际运行，生成 MRP 运行记录和成本运行记录。

用于 P0 全链路验收的数据补全。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password
from services.mrp_engine import run_mrp
from services.cost_engine import run_cost_calculation


def db_config() -> dict:
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "dbname": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def make_db_helpers():
    conn = psycopg2.connect(**db_config(), connect_timeout=5)

    def query_one(sql, params=None):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None

    def query_rows(sql, params=None):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]

    def execute_db(sql, params=None):
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        cur.close()

    def execute_and_return(sql, params=None):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        row = cur.fetchone()
        conn.commit()
        cur.close()
        return dict(row) if row else None

    return conn, query_one, query_rows, execute_db, execute_and_return


def trigger_mrp_run():
    """通过工单触发 MRP 运算。"""
    print("=" * 60)
    print("触发 MRP 运算")
    print("=" * 60)
    conn, query_one, query_rows, execute_db, execute_and_return = make_db_helpers()
    try:
        result = run_mrp(
            query_one,
            query_rows,
            execute_db,
            execute_and_return,
            source_type="work_order",
            source_id=13,  # WO-GT-TRIAL-20260526-001
            project_code="PJ-GT-TRIAL-20260526-001",
            serial_no="SN-GT-TRIAL-20260526-001",
            created_by=1,
        )
        print(f"MRP 运算结果: {result}")
        return result
    except Exception as exc:
        print(f"MRP 运算失败: {exc}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()


def trigger_cost_run():
    """触发成本计算。"""
    print()
    print("=" * 60)
    print("触发成本归集")
    print("=" * 60)
    conn, query_one, query_rows, execute_db, execute_and_return = make_db_helpers()
    try:
        result = run_cost_calculation(
            query_one,
            query_rows,
            execute_db,
            execute_and_return,
            project_code="PJ-GT-TRIAL-20260526-001",
            serial_no="SN-GT-TRIAL-20260526-001",
            created_by=1,
        )
        print(f"成本归集结果: {result}")
        return result
    except Exception as exc:
        print(f"成本归集失败: {exc}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()


if __name__ == "__main__":
    mrp_result = trigger_mrp_run()
    cost_result = trigger_cost_run()
    print()
    print("=" * 60)
    print("P0 引擎触发完成")
    print(f"MRP: {'成功' if mrp_result and mrp_result.get('status') != 'error' else '失败/跳过'}")
    print(f"成本: {'成功' if cost_result and cost_result.get('status') != 'error' else '失败/跳过'}")
