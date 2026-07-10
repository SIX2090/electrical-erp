from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import ensure_first_machine_production_inventory_baseline, load_first_machine_values


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-quality-closure")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_first_machine_values(TEMPLATE)
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            ensure_first_machine_production_inventory_baseline(cur, values)
            conn.commit()
            work_order = fetch_one(
                cur,
                """
                SELECT *
                FROM work_orders
                WHERE project_code=%s AND cabinet_no=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_code, cabinet_no),
            )
            checks.append(("work_order_ready", bool(work_order), work_order.get("wo_no") if work_order else "missing"))
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "admin", "password": "admin"})
    checks.append(("admin_login", login.status_code == 302, login.status_code))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            inspection = fetch_one(
                cur,
                """
                SELECT qi.*, wo.wo_no, p.code AS product_code
                FROM quality_inspection_records qi
                LEFT JOIN work_orders wo ON qi.source_document_type='work_order' AND wo.id=qi.source_document_id
                LEFT JOIN products p ON p.id=qi.product_id
                WHERE qi.project_code=%s AND qi.cabinet_no=%s
                ORDER BY qi.id DESC
                LIMIT 1
                """,
                (project_code, cabinet_no),
            )
            checks.append(("quality_record_traceable", bool(inspection), inspection.get("inspection_no") if inspection else "missing"))
            if inspection:
                checks.append(("quality_source_work_order", inspection.get("source_document_type") == "work_order", inspection.get("source_document_type")))
                checks.append(("quality_result_passed", (inspection.get("inspection_result") or "").lower() in {"pass", "passed"}, inspection.get("inspection_result")))
                checks.append(("quality_project_cabinet", inspection.get("project_code") == project_code and inspection.get("cabinet_no") == cabinet_no, "project/cabinet"))
    finally:
        conn.close()

    if login.status_code == 302 and work_order:
        page_expectations = [
            (f"/production-enhance/quality-inspections?keyword={project_code}", [project_code, cabinet_no, inspection["inspection_no"] if inspection else "QI"]),
            (f"/work-orders/{work_order['id']}", [project_code, cabinet_no, inspection["inspection_no"] if inspection else "QI"]),
            (f"/projects?keyword={project_code}", [project_code]),
        ]
        for path, expected in page_expectations:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_quality_closure_audit=ok" if not failures else "first_machine_quality_closure_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"cabinet_no={cabinet_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
