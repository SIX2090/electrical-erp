from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password


OUT_PATH = ROOT / "logs" / "purchase_request_downpush_readiness.json"


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH ordered AS (
                SELECT poi.product_id,
                       COALESCE(NULLIF(po.project_code, ''), '-') AS project_code,
                       COALESCE(NULLIF(po.serial_no, ''), '-') AS serial_no,
                       SUM(COALESCE(poi.quantity, 0)) AS ordered_qty
                FROM purchase_order_items poi
                LEFT JOIN purchase_orders po ON po.id=poi.order_id
                WHERE COALESCE(po.status, '') NOT IN ('已作废', '作废', 'cancelled', '已关闭')
                GROUP BY poi.product_id, COALESCE(NULLIF(po.project_code, ''), '-'), COALESCE(NULLIF(po.serial_no, ''), '-')
            ),
            line_state AS (
                SELECT pr.id AS req_id,
                       pr.req_no,
                       pr.status,
                       pri.id AS line_id,
                       p.code AS product_code,
                       p.name AS product_name,
                       COALESCE(pri.suggested_supplier_id, 0) AS suggested_supplier_id,
                       COALESCE(s.name, '') AS supplier_name,
                       COALESCE(pri.quantity, 0) AS request_qty,
                       COALESCE(ordered.ordered_qty, 0) AS ordered_qty,
                       GREATEST(COALESCE(pri.quantity, 0)-COALESCE(ordered.ordered_qty, 0), 0) AS remaining_qty
                FROM purchase_requisitions pr
                JOIN purchase_requisition_items pri ON pri.req_id=pr.id
                LEFT JOIN products p ON p.id=pri.product_id
                LEFT JOIN suppliers s ON s.id=pri.suggested_supplier_id
                LEFT JOIN ordered ON ordered.product_id=pri.product_id
                    AND ordered.project_code=COALESCE(NULLIF(pri.project_code, ''), '-')
                    AND ordered.serial_no=COALESCE(NULLIF(pri.serial_no, ''), '-')
                WHERE COALESCE(pr.status, '') IN ('已审核', 'approved')
            )
            SELECT req_id,
                   req_no,
                   status,
                   COUNT(*) AS line_count,
                   SUM(CASE WHEN remaining_qty > 0 THEN 1 ELSE 0 END) AS pending_lines,
                   SUM(CASE WHEN remaining_qty > 0 AND suggested_supplier_id <= 0 THEN 1 ELSE 0 END) AS missing_supplier_lines,
                   SUM(remaining_qty) AS remaining_qty,
                   STRING_AGG(
                       CASE WHEN remaining_qty > 0 AND suggested_supplier_id <= 0
                            THEN COALESCE(product_code, line_id::text)
                            ELSE NULL
                       END,
                       ', ' ORDER BY line_id
                   ) AS missing_supplier_materials
            FROM line_state
            GROUP BY req_id, req_no, status
            HAVING SUM(CASE WHEN remaining_qty > 0 THEN 1 ELSE 0 END) > 0
            ORDER BY missing_supplier_lines DESC, req_id DESC
            """
        )
        rows = [dict(row) for row in cur.fetchall()]

    readiness = [
        dict(
            row,
            blocked_reason="",
            owner="采购",
            next_action=(
                "可生成采购订单草稿；审核前补齐供应商"
                if int(row.get("missing_supplier_lines") or 0) > 0
                else "可生成采购订单"
            ),
            audit_before_approve=(
                "采购订单审核前必须补齐供应商"
                if int(row.get("missing_supplier_lines") or 0) > 0
                else ""
            ),
        )
        for row in rows
    ]
    OUT_PATH.write_text(json.dumps(readiness, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    blocked_count = sum(1 for row in readiness if row["blocked_reason"])
    missing_supplier_count = sum(1 for row in readiness if int(row.get("missing_supplier_lines") or 0) > 0)
    print(f"readiness_output={OUT_PATH}")
    print(f"approved_pending_requests={len(readiness)}")
    print(f"blocked_missing_supplier={blocked_count}")
    print(f"audit_before_approve_missing_supplier={missing_supplier_count}")
    for row in readiness[:20]:
        print(
            " | ".join(
                [
                    str(row.get("req_no")),
                    f"pending_lines={row.get('pending_lines')}",
                    f"missing_supplier_lines={row.get('missing_supplier_lines')}",
                    row.get("next_action") or "ready",
                ]
            )
        )
    return 1 if blocked_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
