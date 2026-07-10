from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "erp_auditor"))

from config import DB_CONFIG


COMPLETED_SERVICE_STATUSES = {"已完成", "已关闭", "closed", "completed"}
ZERO_COST_ALLOWED_BILLING_TYPES = {"合同内", "免费", "保内", "warranty", "contract", "free"}
VALID_SERVICE_STATUSES = {
    "",
    "待派工",
    "待执行",
    "处理中",
    "待结算",
    "待回访",
    "RMA处理中",
    "已完成",
    "已关闭",
    "closed",
    "completed",
}


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
    return psycopg2.connect(**db_config())


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table}",))
    return bool(cur.fetchone()["exists"])


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def fetch_scalar(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] if row and not isinstance(row, dict) else (row or {}).get("count", 0) or (row or {}).get("c", 0))


def repair_missing_card_cabinets(cur) -> int:
    cur.execute(
        """
        UPDATE machine_service_cards c
           SET cabinet_no = src.cabinet_no
          FROM (
                SELECT c.id AS card_id, COALESCE(NULLIF(s.cabinet_no, ''), NULLIF(so.cabinet_no, '')) AS cabinet_no
                  FROM machine_service_cards c
             LEFT JOIN sales_shipments s ON s.order_id=c.sales_order_id
             LEFT JOIN sales_orders so ON so.id=c.sales_order_id
                 WHERE COALESCE(c.cabinet_no, '')=''
                   AND COALESCE(NULLIF(s.cabinet_no, ''), NULLIF(so.cabinet_no, '')) IS NOT NULL
               ) src
         WHERE c.id=src.card_id
        """
    )
    return cur.rowcount


def repair_missing_service_cards_from_shipments(cur) -> int:
    if not table_exists(cur, "sales_shipments") or not table_exists(cur, "sales_shipment_items"):
        return 0
    cur.execute(
        """
        WITH candidates AS (
            SELECT DISTINCT ON (s.cabinet_no)
                   s.order_id AS sales_order_id,
                   COALESCE(NULLIF(s.project_code, ''), NULLIF(so.project_code, '')) AS project_code,
                   NULLIF(s.cabinet_no, '') AS cabinet_no,
                   COALESCE(s.customer_id, so.customer_id) AS customer_id,
                   so.cost_object_id,
                   s.shipment_date,
                   COALESCE(si.product_id, soi.product_id) AS product_id
              FROM sales_shipments s
         LEFT JOIN sales_orders so ON so.id=s.order_id
         LEFT JOIN sales_shipment_items si ON si.shipment_id=s.id
         LEFT JOIN sales_order_items soi ON soi.id=si.order_item_id OR soi.order_id=s.order_id
         LEFT JOIN machine_service_cards c
                ON COALESCE(c.cabinet_no, '')=COALESCE(s.cabinet_no, '')
             WHERE COALESCE(s.cabinet_no, '')<>''
               AND c.id IS NULL
               AND COALESCE(si.product_id, soi.product_id) IS NOT NULL
          ORDER BY s.cabinet_no, s.shipment_date NULLS LAST, s.id
        )
        INSERT INTO machine_service_cards (
            sales_order_id, cost_object_id, project_code, cabinet_no, product_id,
            customer_id, install_date, installation_date, status, remark
        )
        SELECT sales_order_id, cost_object_id, project_code, cabinet_no, product_id,
               customer_id, shipment_date, shipment_date, '已安装待验收',
               'Backfilled by verify_service_closure from posted sales shipment trace.'
          FROM candidates
        """
    )
    return cur.rowcount


def collect_findings(cur) -> list[Finding]:
    findings: list[Finding] = []

    if not table_exists(cur, "machine_service_cards"):
        return [Finding("SVC-TABLE-MISSING", "machine_service_cards is missing")]

    cur.execute(
        """
        SELECT id, sales_order_id, project_code
          FROM machine_service_cards
         WHERE COALESCE(cabinet_no, '')=''
         LIMIT 50
        """
    )
    for row in cur.fetchall():
        findings.append(Finding("SVC-CARD-NO-SERIAL", f"service_card_id={row['id']} sales_order_id={row['sales_order_id']} project_code={row['project_code'] or ''}"))

    cur.execute(
        """
        SELECT o.id, o.order_no, o.service_card_id
          FROM machine_service_orders o
     LEFT JOIN machine_service_cards c ON c.id=o.service_card_id
         WHERE o.service_card_id IS NULL OR c.id IS NULL
         LIMIT 50
        """
    )
    for row in cur.fetchall():
        findings.append(Finding("SVC-ORDER-NO-CARD", f"service_order_id={row['id']} order_no={row['order_no'] or ''} service_card_id={row['service_card_id']}"))

    cur.execute("SELECT DISTINCT COALESCE(status, '') AS status FROM machine_service_orders")
    for row in cur.fetchall():
        if row["status"] not in VALID_SERVICE_STATUSES:
            findings.append(Finding("SVC-STATUS-UNKNOWN", f"status={row['status']}"))

    cur.execute(
        """
        SELECT o.id, o.order_no, COALESCE(o.status, '') AS status
          FROM machine_service_orders o
     LEFT JOIN machine_service_order_items i ON i.order_id=o.id
         WHERE COALESCE(o.status, '') = ANY(%s)
      GROUP BY o.id, o.order_no, o.status, o.labor_cost, o.travel_cost, o.parts_cost, o.total_cost
        HAVING COALESCE(o.total_cost, 0)=0
           AND COALESCE(o.labor_cost, 0)=0
           AND COALESCE(o.travel_cost, 0)=0
           AND COALESCE(o.parts_cost, 0)=0
           AND COUNT(i.id)=0
           AND COALESCE(o.billing_type, '') <> ALL(%s)
         LIMIT 50
        """,
        (list(COMPLETED_SERVICE_STATUSES), list(ZERO_COST_ALLOWED_BILLING_TYPES)),
    )
    for row in cur.fetchall():
        findings.append(Finding("SVC-COST-MISSING", f"service_order_id={row['id']} order_no={row['order_no'] or ''} status={row['status']}"))

    if table_exists(cur, "sales_shipments"):
        cur.execute(
            """
            SELECT s.id, s.shipment_no, s.order_id, s.project_code, s.cabinet_no
              FROM sales_shipments s
         LEFT JOIN machine_service_cards c
                ON COALESCE(c.cabinet_no, '')=COALESCE(s.cabinet_no, '')
             WHERE COALESCE(s.cabinet_no, '')<>''
               AND c.id IS NULL
             LIMIT 50
            """
        )
        for row in cur.fetchall():
            findings.append(
                Finding(
                    "SVC-LIFECYCLE-BREAK",
                    f"shipment_id={row['id']} shipment_no={row['shipment_no'] or ''} order_id={row['order_id']} project_code={row['project_code'] or ''} cabinet_no={row['cabinet_no'] or ''} missing_service_card",
                )
            )

    cur.execute(
        """
        SELECT c.id, c.cabinet_no
          FROM machine_service_cards c
         WHERE NOT EXISTS (
               SELECT 1 FROM machine_service_orders o
                WHERE o.service_card_id=c.id OR COALESCE(o.cabinet_no, '')=COALESCE(c.cabinet_no, '')
         )
           AND NOT EXISTS (
               SELECT 1 FROM machine_service_acceptance_checks a
                WHERE a.service_card_id=c.id OR COALESCE(a.cabinet_no, '')=COALESCE(c.cabinet_no, '')
         )
           AND NOT EXISTS (
               SELECT 1 FROM machine_service_rmas r
                WHERE r.service_card_id=c.id OR COALESCE(r.cabinet_no, '')=COALESCE(c.cabinet_no, '')
         )
         LIMIT 50
        """
    )
    # A card can be newly installed and legitimately have no after-sale activity yet.
    # Keep this as informational output instead of a blocking finding.
    for row in cur.fetchall()[:10]:
        findings.append(Finding("SVC-CARD-NO-ACTIVITY-INFO", f"service_card_id={row['id']} cabinet_no={row['cabinet_no'] or ''}"))

    return findings


def main() -> int:
    os.environ.setdefault("PG_PASSWORD", "admin")
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if not table_exists(cur, "machine_service_cards"):
                print("service_closure=failed")
                print("SVC-TABLE-MISSING | machine_service_cards")
                return 1

            cabinet_repairs = repair_missing_card_cabinets(cur)
            card_repairs = repair_missing_service_cards_from_shipments(cur)
            conn.commit()

            findings = collect_findings(cur)

    blocking = [f for f in findings if not f.code.endswith("-INFO")]
    print("service_closure=ok" if not blocking else "service_closure=failed")
    print(f"repairs_applied.card_serial_backfill={cabinet_repairs}")
    print(f"repairs_applied.shipment_service_cards={card_repairs}")
    print(f"findings={len(findings)} blocking={len(blocking)}")
    for finding in findings:
        print(f"{finding.code} | {finding.detail}")
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
