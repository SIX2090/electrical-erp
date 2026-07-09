from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return int(row.get("value") or 0)


def main() -> int:
    findings = []
    with connect() as conn, conn.cursor() as cur:
        pending_issue_posted = scalar(
            cur,
            """
            SELECT COUNT(*) AS value
            FROM subcontract_issue_orders sio
            JOIN stock_transactions st ON st.reference_no=sio.issue_no
            WHERE COALESCE(sio.status,'') IN ('pending','submitted')
              AND COALESCE(st.transaction_type,'') IN ('subcontract_issue','委外发料')
            """,
        )
        pending_receive_posted = scalar(
            cur,
            """
            SELECT COUNT(*) AS value
            FROM subcontract_receive_orders sro
            JOIN stock_transactions st ON st.reference_no=sro.receive_no
            WHERE COALESCE(sro.status,'') IN ('pending','submitted')
              AND COALESCE(st.transaction_type,'') IN ('subcontract_receive','委外收货')
            """,
        )
        audited_issue_missing = scalar(
            cur,
            """
            SELECT COUNT(*) AS value
            FROM subcontract_issue_orders sio
            WHERE COALESCE(sio.status,'')='audited'
              AND NOT EXISTS (
                  SELECT 1 FROM stock_transactions st
                  WHERE st.reference_no=sio.issue_no
                    AND COALESCE(st.transaction_type,'') IN ('subcontract_issue','委外发料')
              )
            """,
        )
        audited_receive_missing = scalar(
            cur,
            """
            SELECT COUNT(*) AS value
            FROM subcontract_receive_orders sro
            WHERE COALESCE(sro.status,'')='audited'
              AND NOT EXISTS (
                  SELECT 1 FROM stock_transactions st
                  WHERE st.reference_no=sro.receive_no
                    AND COALESCE(st.transaction_type,'') IN ('subcontract_receive','委外收货')
              )
            """,
        )
    if pending_issue_posted:
        findings.append(f"pending/submitted subcontract issue already posted inventory: {pending_issue_posted}")
    if pending_receive_posted:
        findings.append(f"pending/submitted subcontract receive already posted inventory: {pending_receive_posted}")
    if audited_issue_missing:
        findings.append(f"audited subcontract issue missing inventory transaction: {audited_issue_missing}")
    if audited_receive_missing:
        findings.append(f"audited subcontract receive missing inventory transaction: {audited_receive_missing}")
    print("subcontract_posting_rule=save_pending_no_inventory,audit_posts_inventory")
    print(f"pending_issue_posted={pending_issue_posted}")
    print(f"pending_receive_posted={pending_receive_posted}")
    print(f"audited_issue_missing={audited_issue_missing}")
    print(f"audited_receive_missing={audited_receive_missing}")
    print(f"findings={len(findings)}")
    for finding in findings:
        print(f"finding | {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
