from __future__ import annotations

import argparse
import importlib.util
import os
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "erp_auditor" / "config.py"
PREFIX = "VERIFY-SUB-CLOSURE"
STALE_DAYS = 30
DETAIL_LIMIT = 50
VOID_STATUSES = ("void", "voided", "cancelled", "canceled", "已作废", "已取消")
POSTED_STATUSES = ("audited", "posted", "completed", "已审核", "已过账", "已完成")


def load_db_config() -> dict:
    spec = importlib.util.spec_from_file_location("erp_auditor_config", CONFIG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load database config from {CONFIG_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cfg = dict(module.DB_CONFIG)
    cfg["host"] = os.environ.get("PG_HOST") or os.environ.get("DB_HOST") or cfg.get("host")
    cfg["port"] = int(os.environ.get("PG_PORT") or os.environ.get("DB_PORT") or cfg.get("port") or 5432)
    cfg["dbname"] = os.environ.get("PG_DATABASE") or os.environ.get("DB_NAME") or cfg.get("dbname")
    cfg["user"] = os.environ.get("PG_USER") or os.environ.get("DB_USER") or cfg.get("user")
    cfg["password"] = os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD") or cfg.get("password")
    return cfg


def connect():
    return psycopg2.connect(cursor_factory=RealDictCursor, **load_db_config())


def fetch_all(cur, sql: str, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def scalar(cur, sql: str, params=()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return int(row.get("value") or 0)


def table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS table_name", (table_name,))
    row = cur.fetchone() or {}
    return bool(row.get("table_name"))


def columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def insert_dynamic(cur, table_name: str, values: dict):
    available = columns(cur, table_name)
    filtered = {key: value for key, value in values.items() if key in available}
    names = list(filtered)
    placeholders = ",".join(["%s"] * len(names))
    cur.execute(
        f"INSERT INTO {table_name} ({','.join(names)}) VALUES ({placeholders}) RETURNING id",
        [filtered[name] for name in names],
    )
    return cur.fetchone()["id"]


def delete_if_table(cur, table_name: str, where_sql: str, params=()):
    if table_exists(cur, table_name):
        cur.execute(f"DELETE FROM {table_name} WHERE {where_sql}", params)


def delete_product_dependents(cur, code_like: str):
    product_filter = "product_id IN (SELECT id FROM products WHERE code LIKE %s)"
    for table_name in ("batch_tracking", "inventory_balances", "inventory"):
        if table_exists(cur, table_name) and "product_id" in columns(cur, table_name):
            delete_if_table(cur, table_name, product_filter, (code_like,))


def fixture_warehouse_id(cur) -> int:
    if not table_exists(cur, "warehouses"):
        raise RuntimeError("Cannot run subcontract closure verification: warehouses table is missing")
    where_sql = ""
    if "status" in columns(cur, "warehouses"):
        where_sql = "WHERE COALESCE(status, '') NOT IN ('disabled', '停用')"
    cur.execute(f"SELECT id FROM warehouses {where_sql} ORDER BY id LIMIT 1")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Cannot run subcontract closure verification: no active warehouse is available")
    return row["id"]


def ensure_trace_master(cur, project_code: str, serial_no: str):
    project_id = None
    if table_exists(cur, "project_masters") and "project_code" in columns(cur, "project_masters"):
        cur.execute(
            """
            INSERT INTO project_masters (project_code, project_name, status, remark)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_code) DO UPDATE
            SET updated_at=CURRENT_TIMESTAMP
            RETURNING id
            """,
            (project_code, f"{PREFIX} trace fixture", "ready", "subcontract closure verification trace reference"),
        )
        row = cur.fetchone()
        project_id = row["id"] if row else None
    if table_exists(cur, "machine_serial_masters") and "serial_no" in columns(cur, "machine_serial_masters"):
        values = {
            "serial_no": serial_no,
            "project_id": project_id,
            "project_code": project_code,
            "product_family": "verification",
            "machine_model": "trace-fixture",
            "production_stage": "verification",
            "status": "enabled",
            "remark": "subcontract closure verification trace reference",
        }
        insert_columns = [name for name in values if name in columns(cur, "machine_serial_masters")]
        assignments = [f"{name}=EXCLUDED.{name}" for name in insert_columns if name != "serial_no"]
        cur.execute(
            f"""
            INSERT INTO machine_serial_masters ({','.join(insert_columns)})
            VALUES ({','.join(['%s'] * len(insert_columns))})
            ON CONFLICT (serial_no) DO UPDATE
            SET {','.join(assignments) if assignments else 'serial_no=EXCLUDED.serial_no'}, updated_at=CURRENT_TIMESTAMP
            """,
            [values[name] for name in insert_columns],
        )


def require_tables(cur, findings: list[dict]) -> bool:
    required = (
        "subcontract_orders",
        "subcontract_issue_orders",
        "subcontract_issue_lines",
        "subcontract_receive_orders",
        "subcontract_receive_lines",
        "stock_transactions",
        "supplier_payables",
        "products",
        "suppliers",
    )
    missing = [table for table in required if not table_exists(cur, table)]
    for table in missing:
        findings.append({"code": "SUB-SCHEMA-MISSING", "severity": "error", "detail": f"required table missing: {table}"})
    return not missing


def add_rows(findings: list[dict], code: str, severity: str, rows, fields, suggestion: str = ""):
    for row in rows:
        detail = " | ".join(f"{field}={row.get(field)!r}" for field in fields)
        findings.append({"code": code, "severity": severity, "detail": detail, "suggestion": suggestion})


def cleanup_fixture(cur):
    like = f"{PREFIX}%"
    delete_if_table(cur, "supplier_payables", "doc_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (like, like, like))
    delete_if_table(cur, "stock_transactions", "reference_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (like, like, like))
    delete_product_dependents(cur, like)
    delete_if_table(cur, "subcontract_receive_lines", "project_code LIKE %s OR serial_no LIKE %s", (like, like))
    delete_if_table(cur, "subcontract_receive_orders", "receive_no LIKE %s OR subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like, like))
    delete_if_table(cur, "subcontract_issue_lines", "project_code LIKE %s OR serial_no LIKE %s", (like, like))
    delete_if_table(cur, "subcontract_issue_orders", "issue_no LIKE %s OR subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like, like))
    delete_if_table(cur, "subcontract_orders", "order_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (like, like, like))
    delete_if_table(cur, "products", "code LIKE %s", (like,))
    if "code" in columns(cur, "suppliers"):
        delete_if_table(cur, "suppliers", "name LIKE %s OR code LIKE %s", (like, like))
    else:
        delete_if_table(cur, "suppliers", "name LIKE %s", (like,))
    phase5_like = "VERIFY-P5-LOOP%"
    delete_if_table(
        cur,
        "supplier_payables",
        "doc_type IN ('subcontract_order','subcontract_receive','subcontract_receipt') AND (project_code LIKE %s OR serial_no LIKE %s)",
        (phase5_like, phase5_like),
    )
    delete_if_table(
        cur,
        "stock_transactions",
        "COALESCE(transaction_type, source_type, source_doc_type, '') IN ('subcontract_issue','subcontract_receive','outsourcing_issue','outsourcing_receive') AND (project_code LIKE %s OR serial_no LIKE %s)",
        (phase5_like, phase5_like),
    )
    delete_if_table(
        cur,
        "subcontract_receive_lines",
        "project_code LIKE %s OR serial_no LIKE %s OR receive_id IN (SELECT id FROM subcontract_receive_orders WHERE subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s))",
        (phase5_like, phase5_like, phase5_like, phase5_like),
    )
    delete_if_table(
        cur,
        "subcontract_receive_orders",
        "subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s)",
        (phase5_like, phase5_like),
    )
    delete_if_table(
        cur,
        "subcontract_issue_lines",
        "project_code LIKE %s OR serial_no LIKE %s OR issue_id IN (SELECT id FROM subcontract_issue_orders WHERE subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s))",
        (phase5_like, phase5_like, phase5_like, phase5_like),
    )
    delete_if_table(
        cur,
        "subcontract_issue_orders",
        "subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s)",
        (phase5_like, phase5_like),
    )
    delete_if_table(cur, "subcontract_orders", "project_code LIKE %s OR serial_no LIKE %s", (phase5_like, phase5_like))


def ensure_fixture(cur):
    cleanup_fixture(cur)
    suffix = str(int(time.time() * 1000))
    warehouse_id = fixture_warehouse_id(cur)
    supplier_id = insert_dynamic(
        cur,
        "suppliers",
        {"code": f"{PREFIX}-SUP-{suffix}", "name": f"{PREFIX} processor {suffix}", "status": "enabled"},
    )
    product_code = f"{PREFIX}-MAT-{suffix}"
    product_id = insert_dynamic(
        cur,
        "products",
        {
            "code": product_code,
            "name": "Subcontract closure verification material",
            "specification": "SUB-CLOSURE",
            "unit": "pcs",
            "category": "semi_finished",
            "standard_price": Decimal("80"),
            "unit_cost": Decimal("50"),
            "status": "enabled",
        },
    )

    def create_chain(tag: str, ordered: Decimal, issued: Decimal, received: Decimal, scrap: Decimal, short: Decimal):
        project_code = f"{PREFIX}-PRJ-{tag}-{suffix}"
        serial_no = f"{PREFIX}-SN-{tag}-{suffix}"
        order_no = f"{PREFIX}-OS-{tag}-{suffix}"
        issue_no = f"{PREFIX}-OSI-{tag}-{suffix}"
        receive_no = f"{PREFIX}-OSR-{tag}-{suffix}"
        open_qty = max(ordered - received - scrap - short, Decimal("0"))
        ensure_trace_master(cur, project_code, serial_no)
        order_id = insert_dynamic(
            cur,
            "subcontract_orders",
            {
                "order_no": order_no,
                "order_date": date.today(),
                "supplier_id": supplier_id,
                "product_id": product_id,
                "quantity": ordered,
                "unit_price": Decimal("80"),
                "total_amount": ordered * Decimal("80"),
                "project_code": project_code,
                "serial_no": serial_no,
                "status": "partial_received" if open_qty else "completed",
                "arrival_status": "partial_received" if open_qty else "completed",
                "received_qty": received,
                "shortage_qty": open_qty,
                "process_name": "outsourced machining",
                "material_code": product_code,
                "material_name": "Subcontract closure verification material",
                "material_spec": "SUB-CLOSURE",
                "material_unit": "pcs",
                "remark": f"{PREFIX} {tag}",
            },
        )
        issue_id = insert_dynamic(
            cur,
            "subcontract_issue_orders",
            {
                "issue_no": issue_no,
                "date": date.today(),
                "subcontract_order_id": order_id,
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "status": "audited",
                "total_quantity": issued,
                "posted": True,
                "posted_at": date.today(),
                "remark": f"{PREFIX} {tag} issue",
            },
        )
        insert_dynamic(
            cur,
            "subcontract_issue_lines",
            {
                "issue_id": issue_id,
                "subcontract_order_id": order_id,
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "material_code": product_code,
                "material_name": "Subcontract closure verification material",
                "material_spec": "SUB-CLOSURE",
                "unit": "pcs",
                "quantity": issued,
                "project_code": project_code,
                "serial_no": serial_no,
                "remark": f"{PREFIX} {tag} issue line",
            },
        )
        receive_id = insert_dynamic(
            cur,
            "subcontract_receive_orders",
            {
                "receive_no": receive_no,
                "date": date.today(),
                "subcontract_order_id": order_id,
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "status": "audited",
                "total_quantity": received,
                "total_scrap": scrap,
                "scrap_qty": scrap,
                "short_qty": short,
                "posted": True,
                "posted_at": date.today(),
                "remark": f"{PREFIX} {tag} receive",
            },
        )
        insert_dynamic(
            cur,
            "subcontract_receive_lines",
            {
                "receive_id": receive_id,
                "subcontract_order_id": order_id,
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "material_code": product_code,
                "material_name": "Subcontract closure verification material",
                "material_spec": "SUB-CLOSURE",
                "unit": "pcs",
                "quantity": received,
                "scrap_quantity": scrap,
                "project_code": project_code,
                "serial_no": serial_no,
                "remark": f"{PREFIX} {tag} receive line",
            },
        )
        for doc_no, tx_type, qty in ((issue_no, "subcontract_issue", -issued), (receive_no, "subcontract_receive", received)):
            insert_dynamic(
                cur,
                "stock_transactions",
                {
                    "transaction_date": date.today(),
                    "transaction_type": tx_type,
                    "source_type": tx_type,
                    "source_doc_type": tx_type,
                    "source_doc_no": doc_no,
                    "reference_no": doc_no,
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": qty,
                    "unit_cost": Decimal("50"),
                    "amount": qty * Decimal("50"),
                    "project_code": project_code,
                    "serial_no": serial_no,
                    "remark": f"{PREFIX} {tag}",
                },
            )
        net_stock_qty = received - issued
        if net_stock_qty:
            insert_dynamic(
                cur,
                "stock_transactions",
                {
                    "transaction_date": date.today(),
                    "transaction_type": "inventory_balance_reconciliation",
                    "source_type": "inventory_balance_reconciliation",
                    "source_doc_type": "inventory_balance_reconciliation",
                    "source_doc_no": f"{PREFIX}-RECON-{tag}-{suffix}",
                    "reference_no": f"{PREFIX}-RECON-{tag}-{suffix}",
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": -net_stock_qty,
                    "unit_cost": Decimal("0"),
                    "amount": Decimal("0"),
                    "project_code": project_code,
                    "serial_no": serial_no,
                    "remark": f"{PREFIX} fixture balance reconciliation",
                },
            )
        insert_dynamic(
            cur,
            "supplier_payables",
            {
                "supplier_id": supplier_id,
                "doc_type": "subcontract_receive",
                "doc_id": receive_id,
                "doc_no": receive_no,
                "doc_date": date.today(),
                "amount": received * Decimal("80"),
                "paid_amount": Decimal("0"),
                "balance": received * Decimal("80"),
                "status": "unpaid",
                "project_code": project_code,
                "serial_no": serial_no,
                "finance_remark": f"{PREFIX} payable from receive",
            },
        )

    create_chain("SHORTSCRAP", Decimal("3"), Decimal("3"), Decimal("2"), Decimal("0.5"), Decimal("0.5"))
    create_chain("OPENWIP", Decimal("2"), Decimal("2"), Decimal("1"), Decimal("0"), Decimal("0"))


def collect_findings(cur) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    metrics = {
        "orders_checked": 0,
        "issues_checked": 0,
        "receives_checked": 0,
        "closure_sample_orders": 0,
        "scrap_receipt_rows": 0,
        "short_receipt_rows": 0,
        "wip_rows": 0,
        "negative_wip_rows": 0,
        "stale_wip_rows": 0,
    }
    if not require_tables(cur, findings):
        return findings, metrics

    active_filter = "('void','voided','cancelled','canceled','已作废','已取消')"
    metrics["orders_checked"] = scalar(cur, "SELECT COUNT(*) AS value FROM subcontract_orders")
    metrics["issues_checked"] = scalar(cur, "SELECT COUNT(*) AS value FROM subcontract_issue_orders")
    metrics["receives_checked"] = scalar(cur, "SELECT COUNT(*) AS value FROM subcontract_receive_orders")
    metrics["closure_sample_orders"] = scalar(cur, "SELECT COUNT(*) AS value FROM subcontract_orders WHERE order_no LIKE %s", (f"{PREFIX}%",))
    metrics["scrap_receipt_rows"] = scalar(cur, "SELECT COUNT(*) AS value FROM subcontract_receive_orders WHERE COALESCE(total_scrap,0)+COALESCE(scrap_qty,0) > 0")
    metrics["short_receipt_rows"] = scalar(cur, "SELECT COUNT(*) AS value FROM subcontract_receive_orders WHERE COALESCE(short_qty,0) > 0")

    orphan_rows = fetch_all(
        cur,
        f"""
        SELECT so.id, so.order_no, so.status, so.order_date, so.supplier_id
        FROM subcontract_orders so
        WHERE COALESCE(so.status,'') NOT IN {active_filter}
          AND NOT EXISTS (
            SELECT 1 FROM subcontract_issue_orders sio
            WHERE sio.subcontract_order_id=so.id AND COALESCE(sio.status,'') NOT IN {active_filter}
          )
          AND NOT EXISTS (
            SELECT 1 FROM subcontract_receive_orders sro
            WHERE sro.subcontract_order_id=so.id AND COALESCE(sro.status,'') NOT IN {active_filter}
          )
        ORDER BY so.order_date NULLS FIRST, so.id
        """,
    )
    add_rows(findings, "SUB-ORPHAN", "error", orphan_rows, ("id", "order_no", "status", "order_date", "supplier_id"), "Confirm whether the subcontract order should be voided, issued, or closed.")

    issue_no_receive_rows = fetch_all(
        cur,
        f"""
        SELECT sio.id, sio.issue_no, sio.date, sio.subcontract_order_id, sio.supplier_id, sio.total_quantity
        FROM subcontract_issue_orders sio
        WHERE COALESCE(sio.status,'') NOT IN {active_filter}
          AND COALESCE(sio.source_type,'') <> 'subcontract_opening'
          AND NOT EXISTS (
              SELECT 1 FROM subcontract_receive_orders sro
              WHERE sro.subcontract_order_id=sio.subcontract_order_id
                AND COALESCE(sro.status,'') NOT IN {active_filter}
          )
        ORDER BY sio.date NULLS FIRST, sio.id
        """,
    )
    add_rows(findings, "SUB-ISSUE-NO-RECEIVE", "error", issue_no_receive_rows, ("id", "issue_no", "date", "subcontract_order_id", "supplier_id", "total_quantity"), "Follow up processor return, scrap/short receipt, or close WIP after approval.")

    issue_stock_missing_rows = fetch_all(
        cur,
        """
        SELECT sio.id, sio.issue_no, sio.status, sio.posted, sio.date
        FROM subcontract_issue_orders sio
        WHERE (COALESCE(sio.posted, FALSE)=TRUE OR COALESCE(sio.status,'') = ANY(%s))
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.reference_no=sio.issue_no
                AND COALESCE(st.transaction_type, st.source_type, st.source_doc_type, '') IN ('subcontract_issue','outsourcing_issue')
          )
        ORDER BY sio.date NULLS FIRST, sio.id
        """,
        (list(POSTED_STATUSES),),
    )
    add_rows(findings, "SUB-ISSUE-STK-MISSING", "error", issue_stock_missing_rows, ("id", "issue_no", "status", "posted", "date"), "Repost the subcontract issue through the document action or a reviewed repair script.")

    receive_stock_missing_rows = fetch_all(
        cur,
        """
        SELECT sro.id, sro.receive_no, sro.status, sro.posted, sro.date
        FROM subcontract_receive_orders sro
        WHERE (COALESCE(sro.posted, FALSE)=TRUE OR COALESCE(sro.status,'') = ANY(%s))
          AND COALESCE(sro.total_quantity,0) > 0
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.reference_no=sro.receive_no
                AND COALESCE(st.transaction_type, st.source_type, st.source_doc_type, '') IN ('subcontract_receive','outsourcing_receive')
          )
        ORDER BY sro.date NULLS FIRST, sro.id
        """,
        (list(POSTED_STATUSES),),
    )
    add_rows(findings, "SUB-RECEIVE-STK-MISSING", "error", receive_stock_missing_rows, ("id", "receive_no", "status", "posted", "date"), "Repost the subcontract receipt through the document action or a reviewed repair script.")

    receive_no_payable_rows = fetch_all(
        cur,
        f"""
        SELECT sro.id, sro.receive_no, sro.date, sro.subcontract_order_id, sro.supplier_id, sro.total_quantity
        FROM subcontract_receive_orders sro
        WHERE COALESCE(sro.status,'') NOT IN {active_filter}
          AND COALESCE(sro.total_quantity, 0) > 0
          AND NOT EXISTS (
              SELECT 1 FROM supplier_payables sp
              WHERE sp.doc_type IN ('subcontract_receive','subcontract_receipt')
                AND (sp.doc_id=sro.id OR sp.doc_no=sro.receive_no)
          )
        ORDER BY sro.date NULLS FIRST, sro.id
        """,
    )
    add_rows(findings, "SUB-RECEIVE-NO-PAYABLE", "error", receive_no_payable_rows, ("id", "receive_no", "date", "subcontract_order_id", "supplier_id", "total_quantity"), "Generate a supplier_payables record from the reviewed subcontract receipt amount.")

    wip_rows = fetch_all(
        cur,
        f"""
        WITH issue AS (
            SELECT sio.supplier_id, sil.product_id, MIN(sio.date) AS first_issue_date,
                   SUM(COALESCE(sil.quantity, 0)) AS issued_qty
            FROM subcontract_issue_lines sil
            JOIN subcontract_issue_orders sio ON sio.id=sil.issue_id
            WHERE COALESCE(sio.status,'') NOT IN {active_filter}
            GROUP BY sio.supplier_id, sil.product_id
        ),
        receive AS (
            SELECT sro.supplier_id, srl.product_id, MAX(sro.date) AS last_receive_date,
                   SUM(COALESCE(srl.quantity, 0)) AS received_qty,
                   SUM(COALESCE(srl.scrap_quantity, 0)) AS scrap_qty,
                   SUM(COALESCE(sro.short_qty, 0)) AS short_qty
            FROM subcontract_receive_lines srl
            JOIN subcontract_receive_orders sro ON sro.id=srl.receive_id
            WHERE COALESCE(sro.status,'') NOT IN {active_filter}
            GROUP BY sro.supplier_id, srl.product_id
        )
        SELECT COALESCE(issue.supplier_id, receive.supplier_id) AS supplier_id,
               COALESCE(issue.product_id, receive.product_id) AS product_id,
               s.name AS processor_name, p.code AS product_code, p.name AS product_name,
               issue.first_issue_date, receive.last_receive_date,
               COALESCE(issue.issued_qty, 0) AS issued_qty,
               COALESCE(receive.received_qty, 0) AS received_qty,
               COALESCE(receive.scrap_qty, 0) AS scrap_qty,
               COALESCE(receive.short_qty, 0) AS short_qty,
               COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) - COALESCE(receive.scrap_qty, 0) - COALESCE(receive.short_qty, 0) AS wip_qty,
               GREATEST(CURRENT_DATE - COALESCE(issue.first_issue_date, CURRENT_DATE), 0) AS days_outstanding
        FROM issue
        FULL OUTER JOIN receive
          ON COALESCE(issue.supplier_id, 0)=COALESCE(receive.supplier_id, 0)
         AND COALESCE(issue.product_id, 0)=COALESCE(receive.product_id, 0)
        LEFT JOIN suppliers s ON s.id=COALESCE(issue.supplier_id, receive.supplier_id)
        LEFT JOIN products p ON p.id=COALESCE(issue.product_id, receive.product_id)
        WHERE COALESCE(issue.issued_qty, 0) - COALESCE(receive.received_qty, 0) - COALESCE(receive.scrap_qty, 0) - COALESCE(receive.short_qty, 0) <> 0
        ORDER BY wip_qty ASC, issue.first_issue_date NULLS FIRST
        """,
    )
    metrics["wip_rows"] = len(wip_rows)
    negative_wip = [row for row in wip_rows if row.get("wip_qty") is not None and row["wip_qty"] < 0]
    stale_wip = [row for row in wip_rows if row.get("wip_qty") is not None and row["wip_qty"] > 0 and int(row.get("days_outstanding") or 0) > STALE_DAYS]
    metrics["negative_wip_rows"] = len(negative_wip)
    metrics["stale_wip_rows"] = len(stale_wip)
    add_rows(findings, "SUB-WIP-NEGATIVE", "error", negative_wip, ("supplier_id", "processor_name", "product_id", "product_code", "issued_qty", "received_qty", "scrap_qty", "short_qty", "wip_qty"), "Received, scrap, and short-closed quantity exceed issued quantity.")
    add_rows(findings, "SUB-WIP-STALE", "error", stale_wip, ("supplier_id", "processor_name", "product_id", "product_code", "first_issue_date", "issued_qty", "received_qty", "scrap_qty", "short_qty", "wip_qty", "days_outstanding"), "Follow up processor WIP or close short receipt/scrap through an approved document.")

    if metrics["orders_checked"] <= 0:
        findings.append({"code": "SUB-NO-DATA", "severity": "error", "detail": "orders_checked=0", "suggestion": "Run the verifier with fixture seeding enabled or create a real subcontract order, issue, and receipt."})
    if metrics["closure_sample_orders"] < 2:
        findings.append({"code": "SUB-FIXTURE-MISSING", "severity": "error", "detail": f"closure_sample_orders={metrics['closure_sample_orders']}", "suggestion": "Verifier needs one short/scrap closed sample and one open WIP sample."})
    if metrics["scrap_receipt_rows"] <= 0:
        findings.append({"code": "SUB-SCRAP-NOT-PROVED", "severity": "error", "detail": "scrap_receipt_rows=0", "suggestion": "Create or seed a subcontract receipt with scrap quantity."})
    if metrics["short_receipt_rows"] <= 0:
        findings.append({"code": "SUB-SHORT-NOT-PROVED", "severity": "error", "detail": "short_receipt_rows=0", "suggestion": "Create or seed a subcontract receipt with short receipt quantity."})
    return findings, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify subcontract order, issue, receipt, scrap/short, payable, stock posting, and WIP closure.")
    parser.add_argument("--no-fixture", action="store_true", help="Do not seed the controlled subcontract verification fixture.")
    args = parser.parse_args()

    with connect() as conn, conn.cursor() as cur:
        if not args.no_fixture:
            ensure_fixture(cur)
            conn.commit()
        findings, metrics = collect_findings(cur)

    error_count = sum(1 for item in findings if item["severity"] == "error")
    warning_count = sum(1 for item in findings if item["severity"] == "warning")
    print("subcontract_closure_verification=ok" if error_count == 0 else "subcontract_closure_verification=failed")
    for key, value in metrics.items():
        print(f"{key}={value}")
    print(f"errors={error_count}")
    print(f"warnings={warning_count}")

    grouped: dict[str, int] = {}
    for item in findings:
        grouped[item["code"]] = grouped.get(item["code"], 0) + 1
    for code in sorted(grouped):
        print(f"{code}={grouped[code]}")

    for item in findings[:DETAIL_LIMIT]:
        print(f"{item['severity']} | {item['code']} | {item['detail']}")
        if item.get("suggestion"):
            print(f"repair_suggestion | {item['code']} | {item['suggestion']}")
    if len(findings) > DETAIL_LIMIT:
        print(f"output_limited={DETAIL_LIMIT} of {len(findings)} findings")
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
