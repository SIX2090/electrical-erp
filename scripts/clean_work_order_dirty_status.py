from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


def db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def main() -> int:
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE work_orders
                SET status=%s,
                    blocked_reason=%s
                WHERE status IN (%s, %s, %s)
                   OR status IS NULL
                """,
                ("待处理", "状态数据异常，需人工确认", "???", "？？？", ""),
            )
            changed = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"work_order_dirty_status_cleaned={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
