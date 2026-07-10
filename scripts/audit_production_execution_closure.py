from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


PREFIX = "CODX-PEX"


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


def cleanup(cur):
    cur.execute("DELETE FROM operation_reports WHERE report_no LIKE %s OR project_code LIKE %s", (f"{PREFIX}%", f"{PREFIX}%"))
    cur.execute("DELETE FROM production_schedules WHERE schedule_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM process_operations WHERE remark LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM work_order_processes WHERE work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    cur.execute("DELETE FROM work_orders WHERE wo_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM routing_operations WHERE operation_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM production_routings WHERE routing_no LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM products WHERE code LIKE %s", (f"{PREFIX}%",))
    cur.execute("DELETE FROM work_centers WHERE code LIKE %s", (f"{PREFIX}%",))


def create_fixture(cur):
    cur.execute("ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS routing_operation_id INTEGER")
    cur.execute("ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS owner_role VARCHAR(120)")
    cur.execute("ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS downstream_impact TEXT")
    cur.execute("ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS wip_quantity NUMERIC(14,4) DEFAULT 0")
    cur.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_wip_qty NUMERIC(14,4) DEFAULT 0")
    cur.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS downstream_impact TEXT")
    cur.execute("ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS downstream_impact TEXT")
    cur.execute("ALTER TABLE production_schedules ALTER COLUMN start_date DROP NOT NULL")
    cur.execute("ALTER TABLE production_schedules ALTER COLUMN end_date DROP NOT NULL")
    cur.execute("ALTER TABLE production_schedules DROP CONSTRAINT IF EXISTS production_schedules_status_check")
    cur.execute(
        """
        ALTER TABLE production_schedules ADD CONSTRAINT production_schedules_status_check
        CHECK (status IS NULL OR status IN ('scheduled','dispatched','rescheduled','paused','completed','cancelled'))
        """
    )
    cur.execute("ALTER TABLE work_order_processes DROP CONSTRAINT IF EXISTS work_order_processes_status_check")
    cur.execute(
        """
        ALTER TABLE work_order_processes ADD CONSTRAINT work_order_processes_status_check
        CHECK (status IS NULL OR status IN ('not_started','ready','in_progress','paused','rework_pending','scrap_pending','completed','cancelled'))
        """
    )
    cur.execute(
        """
        INSERT INTO products (code, name, category, specification, unit, standard_price)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (f"{PREFIX}-FG", "生产执行审计成品", "产成品", "machine-tool", "台", 100),
    )
    product_id = cur.fetchone()["id"]
    cur.execute("INSERT INTO work_centers (code, name) VALUES (%s, %s) RETURNING id", (f"{PREFIX}-WC", "生产执行审计工作中心"))
    work_center_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO production_routings (product_id, routing_no, name, revision, is_active) VALUES (%s,%s,%s,%s,TRUE) RETURNING id",
        (product_id, f"{PREFIX}-RT", "生产执行审计工艺路线", "A"),
    )
    routing_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO work_orders
            (wo_no, wo_date, product_id, quantity, status, project_code, cabinet_no, planned_start_date, planned_end_date, remark)
        VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '2 day', %s)
        RETURNING id
        """,
        (f"{PREFIX}-WO-001", product_id, 5, "生产中", f"{PREFIX}-PROJECT", f"{PREFIX}-SN", "production execution closure audit"),
    )
    work_order_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO routing_operations (routing_id, sequence, operation_no, operation_name, work_center_id)
        VALUES (%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (routing_id, 10, f"{PREFIX}-OP10", "精加工", work_center_id),
    )
    routing_operation_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO work_order_processes
            (work_order_id, process_operation_id, routing_operation_id, sequence_no, operation_no, operation_name, work_center_id,
             planned_quantity, actual_quantity, good_quantity, rework_quantity, scrap_quantity, status)
        VALUES (%s,%s,%s,10,%s,%s,%s,5,0,0,0,0,'not_started')
        RETURNING id
        """,
        (work_order_id, routing_operation_id, routing_operation_id, f"{PREFIX}-OP10", "精加工", work_center_id),
    )
    process_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO production_schedules
            (schedule_no, work_order_id, work_order_process_id, routing_operation_id, work_center_id,
             planned_start_date, planned_end_date, quantity, dispatch_status, status, responsible_person,
             blocked_reason, next_action, downstream_impact, remark)
        VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,CURRENT_DATE + INTERVAL '1 day',5,'已派工','dispatched',%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            f"{PREFIX}-SCH-001",
            work_order_id,
            process_id,
            routing_operation_id,
            work_center_id,
            "班组长A",
            "待首件确认",
            "完成首件后连续报工",
            "影响后续装配和完工入库",
            "production execution dispatch audit",
        ),
    )
    schedule_id = cur.fetchone()["id"]
    return work_order_id, process_id, schedule_id


def post_report(client, work_order_id, process_id, report_type, good="0", rework="0", scrap="0"):
    response = client.post(
        "/production/operation-reports/new",
        data={
            "work_order_id": str(work_order_id),
            "work_order_process_id": str(process_id),
            "report_type": report_type,
            "good_qty": good,
            "rework_qty": rework,
            "scrap_qty": scrap,
            "labor_hours": "1",
            "equipment_hours": "1",
            "blocked_reason": "audit blocked reason" if report_type in {"pause", "rework", "scrap"} else "",
            "next_action": "audit next action",
            "downstream_impact": "audit downstream impact",
            "remark": "production execution closure audit",
        },
        follow_redirects=False,
    )
    if response.status_code not in {302, 303}:
        return None, response.status_code
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM operation_reports WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (work_order_id,))
            report_id = (cur.fetchone() or {}).get("id")
    finally:
        conn.close()
    response = client.post(f"/production/operation-reports/{report_id}/audit", follow_redirects=False)
    return report_id, response.status_code


def main() -> int:
    os.environ.setdefault("INVENTORY_SECRET_KEY", "production-execution-closure-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cleanup(cur)
            work_order_id, process_id, schedule_id = create_fixture(cur)
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    checks = []
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"
        for path, expected in (
            ("/production-schedules", "生产排程"),
            (f"/production-schedules/{schedule_id}", "派工"),
            ("/production/execution-wip", "生产执行在制"),
            ("/production/capacity-load", "产能负荷"),
        ):
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"page_{path}", response.status_code == 200 and expected in body, response.status_code))
        for report_type, good, rework, scrap in (
            ("start", "0", "0", "0"),
            ("pause", "0", "0", "0"),
            ("complete", "3", "0", "0"),
            ("rework", "0", "1", "0"),
            ("scrap", "0", "0", "1"),
        ):
            report_id, status_code = post_report(client, work_order_id, process_id, report_type, good, rework, scrap)
            checks.append((f"audit_{report_type}", bool(report_id) and status_code in {302, 303}, status_code))

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, good_quantity, rework_quantity, scrap_quantity, wip_quantity, blocked_reason, next_action, downstream_impact FROM work_order_processes WHERE id=%s", (process_id,))
            process = cur.fetchone() or {}
            checks.append(("process_status_exception", process.get("status") in {"rework_pending", "scrap_pending"}, process.get("status")))
            checks.append(("process_good_qty", str(process.get("good_quantity")) == "3.0000", process.get("good_quantity")))
            checks.append(("process_rework_qty", str(process.get("rework_quantity")) == "1.0000", process.get("rework_quantity")))
            checks.append(("process_scrap_qty", str(process.get("scrap_quantity")) == "1.0000", process.get("scrap_quantity")))
            checks.append(("process_wip_qty", str(process.get("wip_quantity")) == "1.0000", process.get("wip_quantity")))
            checks.append(("process_boundary_fields", bool(process.get("blocked_reason") and process.get("next_action") and process.get("downstream_impact")), process))
            cur.execute("SELECT operation_wip_qty, operation_rework_qty, operation_scrap_qty, downstream_impact FROM work_orders WHERE id=%s", (work_order_id,))
            work_order = cur.fetchone() or {}
            checks.append(("work_order_wip", str(work_order.get("operation_wip_qty")) == "1.0000", work_order.get("operation_wip_qty")))
            checks.append(("work_order_rework", str(work_order.get("operation_rework_qty")) == "1.0000", work_order.get("operation_rework_qty")))
            checks.append(("work_order_scrap", str(work_order.get("operation_scrap_qty")) == "1.0000", work_order.get("operation_scrap_qty")))
            checks.append(("work_order_downstream_impact", bool(work_order.get("downstream_impact")), work_order.get("downstream_impact")))
        conn.commit()
    finally:
        conn.close()

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("production_execution_closure=ok" if not failures else "production_execution_closure=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
