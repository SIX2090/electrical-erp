from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


PREFIX = "CODX-OPR"


def db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return next(iter(row.values()), None)


def ensure_schema(cur):
    cur.execute("CREATE TABLE IF NOT EXISTS operation_reports (id SERIAL PRIMARY KEY)")
    for column_sql in (
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS report_no VARCHAR(80)",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS work_order_id INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS work_order_process_id INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS routing_operation_id INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS report_type VARCHAR(40)",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS report_date DATE",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT '草稿'",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS operator_id INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS work_center_id INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS start_time TIMESTAMP",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS end_time TIMESTAMP",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS labor_hours NUMERIC(14,2) DEFAULT 0",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS equipment_hours NUMERIC(14,2) DEFAULT 0",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS good_qty NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS rework_qty NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS scrap_qty NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS blocked_reason TEXT",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS next_action TEXT",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS project_code VARCHAR(120)",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS cabinet_no VARCHAR(120)",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS remark TEXT",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS submitted_by INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS audited_by INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS audited_at TIMESTAMP",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS voided_by INTEGER",
        "ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS sequence_no INTEGER",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS operation_no VARCHAR(80)",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS operation_name VARCHAR(160)",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS work_center_id INTEGER",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS planned_quantity NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS actual_quantity NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS good_quantity NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS rework_quantity NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS scrap_quantity NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS labor_hours NUMERIC(14,2) DEFAULT 0",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS equipment_hours NUMERIC(14,2) DEFAULT 0",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS status VARCHAR(80)",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS qc_status VARCHAR(80)",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS blocked_reason TEXT",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS next_action TEXT",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS started_at TIMESTAMP",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
        "ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
        "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_completed_qty NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_rework_qty NUMERIC(14,4) DEFAULT 0",
        "ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_scrap_qty NUMERIC(14,4) DEFAULT 0",
    ):
        cur.execute(column_sql)


def cleanup(cur):
    cur.execute("DELETE FROM operation_reports WHERE report_no LIKE %s OR project_code LIKE %s", (f"{PREFIX}%", f"{PREFIX}%"))
    cur.execute("DELETE FROM process_operations WHERE remark LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM work_order_processes WHERE work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    cur.execute("DELETE FROM work_orders WHERE wo_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM routing_operations WHERE operation_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM production_routings WHERE routing_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM products WHERE code LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM work_centers WHERE code LIKE %s", (f"{PREFIX}%",))


def create_test_data(cur):
    cur.execute(
        """
        INSERT INTO products (code, name, category, specification, unit, standard_price)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (f"{PREFIX}-FG", "工序报工测试成品", "产成品", "test", "台", 100),
    )
    product_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO work_centers (code, name) VALUES (%s, %s) RETURNING id",
        (f"{PREFIX}-WC", "工序报工测试工作中心"),
    )
    work_center_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO production_routings (product_id, routing_no, name, revision, is_active) VALUES (%s,%s,%s,%s,TRUE) RETURNING id",
        (product_id, f"{PREFIX}-RT", "工序报工测试工艺路线", "A"),
    )
    routing_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO work_orders
            (wo_no, wo_date, product_id, quantity, status, project_code, cabinet_no,
             planned_start_date, planned_end_date, remark)
        VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '1 day', %s)
        RETURNING id
        """,
        (f"{PREFIX}-WO-001", product_id, 2, "生产中", f"{PREFIX}-PROJECT", f"{PREFIX}-SN", "operation report full-cycle test"),
    )
    work_order_id = cur.fetchone()["id"]
    process_ids = []
    for sequence_no, operation_no, operation_name in ((10, "OP10", "粗加工"), (20, "OP20", "精加工")):
        cur.execute(
            """
            INSERT INTO routing_operations
                (routing_id, sequence, operation_no, operation_name, work_center_id)
            VALUES (%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (routing_id, sequence_no, f"{PREFIX}-{operation_no}", operation_name, work_center_id),
        )
        routing_operation_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO work_order_processes
                (work_order_id, process_operation_id, sequence_no, operation_no, operation_name, work_center_id,
                 planned_quantity, actual_quantity, good_quantity, rework_quantity, scrap_quantity, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,0,0,0,0,%s)
            RETURNING id
            """,
            (work_order_id, routing_operation_id, sequence_no, operation_no, operation_name, work_center_id, 2, "not_started"),
        )
        process_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO process_operations
                (work_order_process_id, assigned_date, quantity_to_process, completed_quantity, status, work_center_id, remark)
            VALUES (%s, CURRENT_DATE, %s, 0, %s, %s, %s)
            RETURNING id
            """,
            (process_id, 2, "assigned", work_center_id, f"{PREFIX} {operation_no}"),
        )
        process_ids.append(process_id)
    return work_order_id, process_ids


def create_and_audit_report(client, work_order_id, process_id, report_type, good="0", rework="0", scrap="0"):
    response = client.post(
        "/production/operation-reports/new",
        data={
            "work_order_id": str(work_order_id),
            "work_order_process_id": str(process_id),
            "report_type": report_type,
            "report_date": date.today().isoformat(),
            "labor_hours": "1.5",
            "equipment_hours": "1",
            "good_qty": good,
            "rework_qty": rework,
            "scrap_qty": scrap,
            "blocked_reason": "测试阻塞" if report_type in {"rework", "scrap"} else "",
            "next_action": "测试下一步",
            "remark": "工序报工全流程测试",
        },
        follow_redirects=False,
    )
    if response.status_code not in {302, 303}:
        return None, response.status_code
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM operation_reports WHERE work_order_id=%s AND work_order_process_id=%s ORDER BY id DESC LIMIT 1",
                (work_order_id, process_id),
            )
            report_id = (cur.fetchone() or {}).get("id")
    finally:
        conn.close()
    response = client.post(f"/production/operation-reports/{report_id}/audit", follow_redirects=False)
    return report_id, response.status_code


def main() -> int:
    os.environ.setdefault("INVENTORY_SECRET_KEY", "operation-report-full-cycle-test")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    checks = []
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cleanup(cur)
            work_order_id, process_ids = create_test_data(cur)
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"

        for process_id in process_ids:
            report_id, status_code = create_and_audit_report(client, work_order_id, process_id, "start")
            checks.append((f"start_audit_{process_id}", bool(report_id) and status_code in {302, 303}, status_code))
        report_id, status_code = create_and_audit_report(client, work_order_id, process_ids[0], "complete", good="2")
        checks.append(("op10_complete_audit", bool(report_id) and status_code in {302, 303}, status_code))
        repeat = client.post(f"/production/operation-reports/{report_id}/audit", follow_redirects=False)
        checks.append(("repeat_audit_not_double_counted", repeat.status_code in {302, 303}, repeat.status_code))
        report_id, status_code = create_and_audit_report(client, work_order_id, process_ids[1], "complete", good="2")
        checks.append(("op20_complete_audit", bool(report_id) and status_code in {302, 303}, status_code))
        report_id, status_code = create_and_audit_report(client, work_order_id, process_ids[1], "rework", rework="1")
        checks.append(("rework_audit", bool(report_id) and status_code in {302, 303}, status_code))
        report_id, status_code = create_and_audit_report(client, work_order_id, process_ids[1], "scrap", scrap="0.5")
        checks.append(("scrap_audit", bool(report_id) and status_code in {302, 303}, status_code))

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            report_count = scalar(cur, "SELECT COUNT(*) FROM operation_reports WHERE work_order_id=%s", (work_order_id,))
            checks.append(("operation_reports_created", report_count == 6, report_count))
            cur.execute("SELECT * FROM work_order_processes WHERE id=%s", (process_ids[0],))
            op10 = cur.fetchone() or {}
            checks.append(("op10_good_qty", op10.get("good_quantity") == 2, op10.get("good_quantity")))
            checks.append(("op10_no_double_count", op10.get("labor_hours") == 3, op10.get("labor_hours")))
            checks.append(("op10_status_completed", op10.get("status") == "completed", op10.get("status")))
            cur.execute("SELECT * FROM work_order_processes WHERE id=%s", (process_ids[1],))
            op20 = cur.fetchone() or {}
            checks.append(("op20_good_qty", op20.get("good_quantity") == 2, op20.get("good_quantity")))
            checks.append(("op20_rework_qty", op20.get("rework_quantity") == 1, op20.get("rework_quantity")))
            checks.append(("op20_scrap_qty", op20.get("scrap_quantity") == 0.5, op20.get("scrap_quantity")))
            checks.append(("op20_status_rework", op20.get("status") in {"rework_pending", "scrap_pending"}, op20.get("status")))
            cur.execute("SELECT operation_completed_qty, operation_rework_qty, operation_scrap_qty FROM work_orders WHERE id=%s", (work_order_id,))
            wo = cur.fetchone() or {}
            checks.append(("work_order_operation_completed_qty", wo.get("operation_completed_qty") == 2, wo.get("operation_completed_qty")))
            checks.append(("work_order_operation_rework_qty", wo.get("operation_rework_qty") == 1, wo.get("operation_rework_qty")))
            checks.append(("work_order_operation_scrap_qty", wo.get("operation_scrap_qty") == 0.5, wo.get("operation_scrap_qty")))
        conn.commit()
    finally:
        conn.close()

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("operation_report_full_cycle=ok" if not failures else "operation_report_full_cycle=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
