from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"
DIRTY_CODEPOINTS = {0xFFFD, 0x7487, 0x6434, 0x95C1, 0x9359}


DETAIL_CASES = [
    ("sales order detail", "sales_orders", "/sales/{id}", ("当前状态", "下一步", "物料明细")),
    ("purchase request detail", "purchase_requisitions", "/purchase_request/{id}", ("采购申请", "申请明细")),
    ("purchase order detail", "purchase_orders", "/purchase_order/{id}", ("当前状态", "下一步", "物料明细")),
    ("purchase receipt detail", "purchase_receipts", "/purchase_receipts/{id}", ("收货信息", "收货物料明细")),
    ("subcontract detail", "subcontract_orders", "/subcontract/{id}", ("委外", "项目", "机号")),
    ("work order detail", "work_orders", "/work-orders/{id}", ("当前状态", "基本信息", "领料需求")),
    ("shipment detail", "sales_shipments", "/shipments/{id}", ("销售发货", "项目号", "机号")),
    ("receivable detail", "customer_receivables", "/receivables/{id}", ("应收", "状态", "详情")),
    ("service card detail", "machine_service_cards", "/service-cards/{id}", ("设备服务档案", "项目号", "机号")),
    ("service order detail", "machine_service_orders", "/service-orders/{id}", ("服务单", "项目号", "机号")),
    ("service rma detail", "machine_service_rmas", "/service-rmas/{id}", ("RMA", "项目号", "机号")),
]


def has_dirty_text(text):
    return "???" in text or any(ord(ch) in DIRTY_CODEPOINTS for ch in text)


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def load_trial_values():
    values = {
        "project_code": "PJ-GT-TRIAL-20260526-001",
        "serial_no": "SN-GT-TRIAL-20260526-001",
    }
    if not TEMPLATE.exists():
        return values
    with TEMPLATE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            actual = (row[1] or "").strip()
            if actual.startswith("PJ-GT-"):
                values["project_code"] = actual
            elif actual.startswith("SN-GT-"):
                values["serial_no"] = actual
    return values


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def fetch_detail_ids(project_code, serial_no):
    ids = {}
    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            for _label, table, _path, _required in DETAIL_CASES:
                cur.execute(
                    f"""
                    SELECT id
                    FROM {table}
                    WHERE project_code=%s AND serial_no=%s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (project_code, serial_no),
                )
                row = cur.fetchone()
                ids[table] = row["id"] if row else None
    finally:
        conn.close()
    return ids


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-detail-runtime-text")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    values = load_trial_values()
    project_code = values["project_code"]
    serial_no = values["serial_no"]
    detail_ids = fetch_detail_ids(project_code, serial_no)

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    password = load_password("pilot_admin")
    checks = []

    login = client.post("/login", data={"username": "pilot_admin", "password": password}, follow_redirects=False)
    checks.append(("pilot_admin_login", login.status_code == 302, login.status_code))

    if login.status_code == 302:
        for label, table, path_template, required_markers in DETAIL_CASES:
            record_id = detail_ids.get(table)
            checks.append((f"{label}:record", bool(record_id), record_id or "missing"))
            if not record_id:
                continue
            path = path_template.format(id=record_id)
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{label}:status", response.status_code == 200, response.status_code))
            checks.append((f"{label}:project", project_code in body, "project visible"))
            checks.append((f"{label}:serial", serial_no in body, "serial visible"))
            for marker in required_markers:
                checks.append((f"{label}:operator_text:{marker}", marker in body, "visible"))
            checks.append((f"{label}:dirty_markers", not has_dirty_text(body), "clean" if not has_dirty_text(body) else "dirty"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_detail_runtime_text_audit=ok" if not failures else "first_machine_detail_runtime_text_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"serial_no={serial_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
