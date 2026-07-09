from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


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

def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def count_rows(cur, sql, params=()):
    cur.execute(sql, params)
    return int((cur.fetchone() or {}).get("value") or 0)


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-lifecycle-ledger")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_trial_values()
    project_code = values["project_code"]
    serial_no = values["serial_no"]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            sales_order = fetch_one(
                cur,
                "SELECT id, order_no FROM sales_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
                (project_code, serial_no),
            )
            checks.append(("sales_order_axis", bool(sales_order), sales_order.get("order_no") if sales_order else "missing"))
            checks.append(("sales_items", count_rows(cur, "SELECT COUNT(*) AS value FROM sales_order_items WHERE order_id=%s", (sales_order["id"],)) >= 1 if sales_order else False, "lines"))
            checks.append(("bom_items", count_rows(cur, "SELECT COUNT(*) AS value FROM bom_items bi JOIN boms b ON b.id=bi.bom_id JOIN sales_order_items soi ON soi.product_id=b.product_id WHERE soi.order_id=%s", (sales_order["id"],)) >= 1 if sales_order else False, "bom"))
            checks.append(("mrp_requirements", count_rows(cur, "SELECT COUNT(*) AS value FROM mrp_requirements WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "mrp"))
            checks.append(("purchase_orders", count_rows(cur, "SELECT COUNT(*) AS value FROM purchase_orders WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "purchase"))
            checks.append(("purchase_receipts", count_rows(cur, "SELECT COUNT(*) AS value FROM purchase_receipts WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "receipt"))
            checks.append(("subcontract_orders", count_rows(cur, "SELECT COUNT(*) AS value FROM subcontract_orders WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "subcontract"))
            checks.append(("work_orders", count_rows(cur, "SELECT COUNT(*) AS value FROM work_orders WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "work_order"))
            checks.append(("work_order_costs", count_rows(cur, "SELECT COUNT(*) AS value FROM work_orders wo JOIN work_order_cost_lines wcl ON wcl.work_order_id=wo.id WHERE wo.project_code=%s AND wo.serial_no=%s", (project_code, serial_no)) >= 1, "cost"))
            checks.append(("quality_inspections", count_rows(cur, "SELECT COUNT(*) AS value FROM quality_inspection_records WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "quality"))
            checks.append(("stock_transactions", count_rows(cur, "SELECT COUNT(*) AS value FROM stock_transactions WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "stock_tx"))
            checks.append(("inventory_balances", count_rows(cur, "SELECT COUNT(*) AS value FROM inventory_balances WHERE serial_no=%s", (serial_no,)) >= 1, "balance"))
            checks.append(("shipments", count_rows(cur, "SELECT COUNT(*) AS value FROM sales_shipments WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "shipment"))
            checks.append(("service_cards", count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_cards WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "service_card"))
            checks.append(("service_orders", count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_orders WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "service_order"))
            checks.append(("service_rmas", count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_rmas WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "rma"))
            checks.append(("receivables", count_rows(cur, "SELECT COUNT(*) AS value FROM customer_receivables WHERE project_code=%s AND serial_no=%s", (project_code, serial_no)) >= 1, "ar"))
            checks.append(
                (
                    "payables",
                    count_rows(
                        cur,
                        """
                        SELECT COUNT(*) AS value
                        FROM supplier_payables sp
                        LEFT JOIN purchase_orders po ON sp.doc_type='purchase_order' AND po.id=sp.doc_id
                        LEFT JOIN subcontract_orders sc ON sp.doc_type='subcontract_order' AND sc.id=sp.doc_id
                        WHERE po.project_code=%s OR po.serial_no=%s OR sc.project_code=%s OR sc.serial_no=%s
                        """,
                        (project_code, serial_no, project_code, serial_no),
                    )
                    >= 1,
                    "ap",
                )
            )
            finance = fetch_one(
                cur,
                """
                SELECT
                    (SELECT COALESCE(SUM(total_amount),0) FROM sales_orders WHERE project_code=%s AND serial_no=%s) AS sales_amount,
                    (SELECT COALESCE(SUM(total_amount),0) FROM purchase_orders WHERE project_code=%s AND serial_no=%s) AS purchase_amount,
                    (SELECT COALESCE(SUM(total_amount),0) FROM subcontract_orders WHERE project_code=%s AND serial_no=%s) AS subcontract_amount,
                    (SELECT COALESCE(SUM(total_cost),0) FROM machine_service_orders WHERE project_code=%s AND serial_no=%s) AS service_cost,
                    (SELECT COALESCE(SUM(total_amount),0) FROM customer_receivables WHERE project_code=%s AND serial_no=%s) AS receivable_amount
                """,
                (project_code, serial_no, project_code, serial_no, project_code, serial_no, project_code, serial_no, project_code, serial_no),
            ) or {}
            checks.append(("finance_sales_positive", finance.get("sales_amount", 0) > 0, finance.get("sales_amount")))
            checks.append(("finance_cost_positive", (finance.get("purchase_amount", 0) + finance.get("subcontract_amount", 0) + finance.get("service_cost", 0)) > 0, "cost"))
            checks.append(("finance_receivable_positive", finance.get("receivable_amount", 0) > 0, finance.get("receivable_amount")))
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_admin", "password": load_password("pilot_admin")})
    checks.append(("pilot_admin_login", login.status_code == 302, login.status_code))
    if login.status_code == 302 and sales_order:
        page_expectations = [
            (f"/projects?keyword={project_code}", [project_code, serial_no, sales_order["order_no"]]),
            (
                f"/projects/{sales_order['id']}",
                [
                    project_code,
                    serial_no,
                    "BOM",
                    "OS-GT-TRIAL-20260526-001",
                    "WO-GT-TRIAL-20260526-001",
                    "QI",
                    "RMA",
                ],
            ),
        ]
        for path, expected in page_expectations:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_lifecycle_ledger_audit=ok" if not failures else "first_machine_lifecycle_ledger_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"serial_no={serial_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
