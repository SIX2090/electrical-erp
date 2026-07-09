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


CHECKS = [
    ("legacy_completion_rows", "SELECT COUNT(*) AS value FROM wo_complete_items"),
    ("formal_completion_rows", "SELECT COUNT(*) AS value FROM production_completion_orders"),
    (
        "posted_formal_without_legacy_link",
        """
        SELECT COUNT(*) AS value
        FROM production_completion_orders
        WHERE COALESCE(status,'') IN ('posted','已过账')
          AND wo_complete_item_id IS NULL
        """,
    ),
    (
        "posted_formal_without_stock_tx",
        """
        SELECT COUNT(*) AS value
        FROM production_completion_orders pc
        WHERE COALESCE(pc.status,'') IN ('posted','已过账')
          AND pc.completion_no NOT LIKE 'PC-HIST-%'
          AND NOT EXISTS (
              SELECT 1
              FROM stock_transactions st
              WHERE st.reference_no=pc.completion_no
                 OR st.source_doc_no=pc.completion_no
          )
        """,
    ),
    (
        "legacy_completion_without_formal_doc",
        """
        SELECT COUNT(*) AS value
        FROM wo_complete_items wc
        WHERE NOT EXISTS (
            SELECT 1
            FROM production_completion_orders pc
            WHERE pc.wo_complete_item_id=wc.id
        )
        """,
    ),
    (
        "history_wrapper_with_duplicate_stock_tx",
        """
        SELECT COUNT(*) AS value
        FROM production_completion_orders pc
        WHERE pc.wo_complete_item_id IS NOT NULL
          AND pc.completion_no LIKE 'PC-HIST-%'
          AND EXISTS (
              SELECT 1
              FROM stock_transactions st
              WHERE st.reference_no=pc.completion_no
                 OR st.source_doc_no=pc.completion_no
          )
        """,
    ),
    (
        "completion_stock_qty_mismatch",
        """
        SELECT COUNT(*) AS value
        FROM production_completion_orders pc
        JOIN (
            SELECT reference_no, COALESCE(SUM(quantity),0) AS stock_qty
            FROM stock_transactions
            WHERE transaction_type IN ('工单完工入库','production_completion')
            GROUP BY reference_no
        ) st ON st.reference_no=pc.completion_no
        WHERE COALESCE(pc.status,'') IN ('posted','已过账')
          AND pc.completion_no NOT LIKE 'PC-HIST-%'
          AND ABS(COALESCE(pc.quantity,0)-COALESCE(st.stock_qty,0)) > 0.0001
        """,
    ),
    (
        "completion_cost_source_missing",
        """
        SELECT COUNT(*) AS value
        FROM production_completion_orders pc
        LEFT JOIN work_order_costs woc ON woc.work_order_id=pc.work_order_id
        WHERE COALESCE(pc.status,'') IN ('posted','已过账')
          AND COALESCE(pc.unit_cost,0)=0
          AND COALESCE(woc.total_cost,0)=0
        """,
    ),
    ("dirty_work_order_status_rows", "SELECT COUNT(*) AS value FROM work_orders WHERE COALESCE(status,'') LIKE '%???%'"),
]

FAIL_ON_NONZERO = {
    "posted_formal_without_legacy_link",
    "posted_formal_without_stock_tx",
    "legacy_completion_without_formal_doc",
    "history_wrapper_with_duplicate_stock_tx",
    "work_orders_completed_qty_mismatch",
    "completion_stock_qty_mismatch",
    "completion_cost_source_missing",
    "dirty_work_order_status_rows",
}


def has_column(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return bool(cur.fetchone())


def main() -> int:
    conn = connect_db(db_config())
    failures = []
    try:
        with conn.cursor() as cur:
            print("production_completion_closure_audit=read_only")
            for name, sql in CHECKS:
                cur.execute(sql)
                row = cur.fetchone() or {}
                value = row.get("value", 0)
                print(f"{name}={value}")
                if name in FAIL_ON_NONZERO and value:
                    failures.append((name, value))

            if has_column(cur, "work_orders", "completed_qty"):
                cur.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM work_orders wo
                    JOIN (
                        SELECT wo_id, COALESCE(SUM(qty),0) AS completed_qty
                        FROM wo_complete_items
                        GROUP BY wo_id
                    ) wc ON wc.wo_id=wo.id
                    WHERE ABS(COALESCE(wo.completed_qty,0)-wc.completed_qty) > 0.0001
                    """
                )
                mismatch = (cur.fetchone() or {}).get("value", 0)
                print(f"work_orders_completed_qty_mismatch={mismatch}")
                if mismatch:
                    failures.append(("work_orders_completed_qty_mismatch", mismatch))
                stored_completed_expr = "COALESCE(wo.completed_qty,0)"
            else:
                print("work_orders_completed_qty_mismatch=skipped_no_completed_qty_column")
                stored_completed_expr = "0"

            cur.execute(
                f"""
                SELECT wo.id, wo.wo_no, wo.status, wo.quantity,
                       {stored_completed_expr} AS stored_completed_qty,
                       COALESCE(wc.completed_qty,0) AS legacy_completed_qty,
                       COALESCE(pc.formal_completed_qty,0) AS formal_completed_qty
                FROM work_orders wo
                LEFT JOIN (
                    SELECT wo_id, SUM(qty) AS completed_qty
                    FROM wo_complete_items
                    GROUP BY wo_id
                ) wc ON wc.wo_id=wo.id
                LEFT JOIN (
                    SELECT work_order_id, SUM(quantity) AS formal_completed_qty
                    FROM production_completion_orders
                    WHERE COALESCE(status,'') IN ('posted','已过账')
                    GROUP BY work_order_id
                ) pc ON pc.work_order_id=wo.id
                WHERE COALESCE(wc.completed_qty,0) > 0
                   OR COALESCE(pc.formal_completed_qty,0) > 0
                ORDER BY wo.id DESC
                LIMIT 20
                """
            )
            rows = cur.fetchall() or []
            print("sample_work_order_completion_rows:")
            for row in rows:
                print(
                    f"{row.get('id')}|{row.get('wo_no')}|{row.get('status')}|"
                    f"plan={row.get('quantity')}|stored={row.get('stored_completed_qty')}|"
                    f"legacy={row.get('legacy_completed_qty')}|formal={row.get('formal_completed_qty')}"
                )
    finally:
        conn.close()

    print(f"findings={len(failures)}")
    for name, value in failures:
        print(f"finding|{name}|{value}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
