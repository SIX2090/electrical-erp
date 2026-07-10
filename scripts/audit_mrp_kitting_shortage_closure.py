from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "erp_auditor"))

from config import DB_CONFIG


@dataclass
class Finding:
    code: str
    detail: str


def db_config() -> dict:
    return {
        "host": os.environ.get("PG_HOST") or os.environ.get("DB_HOST") or DB_CONFIG.get("host", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT") or os.environ.get("DB_PORT") or DB_CONFIG.get("port", 5432)),
        "dbname": os.environ.get("PG_DATABASE") or os.environ.get("DB_NAME") or DB_CONFIG.get("dbname", "wms"),
        "user": os.environ.get("PG_USER") or os.environ.get("DB_USER") or DB_CONFIG.get("user", "wms_user"),
        "password": os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD") or DB_CONFIG.get("password", ""),
    }


def connect():
    return psycopg2.connect(**db_config(), cursor_factory=RealDictCursor, connect_timeout=5)


def scalar(cur, sql: str, params=()):
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return next(iter(row.values()), 0)


def table_exists(cur, table: str) -> bool:
    return bool(scalar(cur, "SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",)))


def report(findings: list[Finding]) -> int:
    if findings:
        print("mrp_kitting_shortage_closure=failed")
        for finding in findings:
            print(f"{finding.code}: {finding.detail}")
        return 1
    print("mrp_kitting_shortage_closure=ok")
    return 0


def main() -> int:
    findings: list[Finding] = []
    with connect() as conn, conn.cursor() as cur:
        required_tables = [
            "mrp_requirements",
            "products",
            "purchase_requisitions",
            "purchase_requisition_items",
            "purchase_orders",
            "purchase_order_items",
        ]
        for table in required_tables:
            if not table_exists(cur, table):
                findings.append(Finding("missing_table", table))
        if findings:
            return report(findings)

        shortage_rows = scalar(
            cur,
            "SELECT COUNT(*) FROM mrp_requirements WHERE COALESCE(shortage_quantity, 0) > 0",
        )
        trace_rows = scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM mrp_requirements
            WHERE COALESCE(shortage_quantity, 0) > 0
              AND (COALESCE(project_code, '') <> '' OR COALESCE(cabinet_no, '') <> '')
            """,
        )
        covered_rows = scalar(
            cur,
            """
            WITH req AS (
                SELECT pri.product_id,
                       COALESCE(NULLIF(pri.project_code, ''), '-') AS project_code,
                       COALESCE(NULLIF(pri.cabinet_no, ''), '-') AS cabinet_no,
                       SUM(GREATEST(COALESCE(pri.quantity, 0), 0)) AS requested_qty
                FROM purchase_requisition_items pri
                LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
                WHERE COALESCE(pr.status, '') NOT IN ('已作废','作废','cancelled','canceled','rejected','已驳回','已完成','已关闭','completed','closed')
                GROUP BY pri.product_id, COALESCE(NULLIF(pri.project_code, ''), '-'), COALESCE(NULLIF(pri.cabinet_no, ''), '-')
            ),
            po AS (
                SELECT poi.product_id,
                       COALESCE(NULLIF(po.project_code, ''), '-') AS project_code,
                       COALESCE(NULLIF(po.cabinet_no, ''), '-') AS cabinet_no,
                       SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)) AS pending_po_qty
                FROM purchase_order_items poi
                LEFT JOIN purchase_orders po ON po.id=poi.order_id
                WHERE COALESCE(po.status, '') NOT IN ('已作废','作废','cancelled','canceled','rejected','已驳回','已完成','已关闭','completed','closed')
                GROUP BY poi.product_id, COALESCE(NULLIF(po.project_code, ''), '-'), COALESCE(NULLIF(po.cabinet_no, ''), '-')
            )
            SELECT COUNT(*)
            FROM mrp_requirements mr
            LEFT JOIN req ON req.product_id=mr.product_id
                AND req.project_code=COALESCE(NULLIF(mr.project_code, ''), '-')
                AND req.cabinet_no=COALESCE(NULLIF(mr.cabinet_no, ''), '-')
            LEFT JOIN po ON po.product_id=mr.product_id
                AND po.project_code=COALESCE(NULLIF(mr.project_code, ''), '-')
                AND po.cabinet_no=COALESCE(NULLIF(mr.cabinet_no, ''), '-')
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
              AND COALESCE(req.requested_qty, 0) + COALESCE(po.pending_po_qty, 0) > 0
            """,
        )

        cur.execute(
            """
            SELECT mr.id, mr.supply_mode, mr.shortage_quantity,
                   COALESCE(p.default_supplier_name, '') AS default_supplier_name,
                   COALESCE(sp.supplier_id, 0) AS supplier_id,
                   COALESCE(sp.lead_time_days, p.purchase_lead_days, 0) AS lead_time_days
            FROM mrp_requirements mr
            LEFT JOIN products p ON p.id=mr.product_id
            LEFT JOIN LATERAL (
                SELECT supplier_id, lead_time_days
                FROM supplier_prices sp
                WHERE sp.product_id=mr.product_id AND COALESCE(sp.is_active, TRUE)=TRUE
                ORDER BY COALESCE(sp.is_primary, FALSE) DESC, sp.effective_date DESC NULLS LAST, sp.id DESC
                LIMIT 1
            ) sp ON TRUE
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
            LIMIT 200
            """
        )
        rows = cur.fetchall()
        actionable = []
        owner_routed = []
        eta_ready = []
        for row in rows:
            supply_mode = (row.get("supply_mode") or "").strip().lower()
            if supply_mode in {"subcontract", "outsourcing", "委外", "外协", "alternative", "substitute", "替代"}:
                owner_routed.append(row)
                continue
            if row.get("supplier_id") or row.get("default_supplier_name"):
                actionable.append(row)
            if row.get("lead_time_days"):
                eta_ready.append(row)

        if shortage_rows <= 0:
            findings.append(Finding("no_mrp_shortage_rows", "No open shortage row is available to audit."))
        if shortage_rows > 0 and trace_rows <= 0:
            findings.append(Finding("no_project_or_cabinet_trace", "Open shortages have no project or cabinet trace axis."))
        if shortage_rows > 0 and not actionable and covered_rows <= 0:
            findings.append(Finding("no_actionable_purchase_shortage", "No shortage row can become a purchase suggestion."))
        if shortage_rows > 0 and not eta_ready and covered_rows <= 0:
            findings.append(Finding("no_eta_basis", "No shortage row has supplier or material lead-time basis for expected arrival."))

        print(f"mrp_shortage_rows={shortage_rows}")
        print(f"trace_rows={trace_rows}")
        print(f"covered_rows={covered_rows}")
        print(f"actionable_purchase_rows={len(actionable)}")
        print(f"owner_routed_non_purchase_rows={len(owner_routed)}")
        print(f"eta_basis_rows={len(eta_ready)}")
    return report(findings)


if __name__ == "__main__":
    raise SystemExit(main())
