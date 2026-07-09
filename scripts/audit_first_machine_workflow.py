from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import ensure_first_machine_demand_baseline, load_first_machine_values, load_trial_passwords


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def load_values():
    return load_first_machine_values(TEMPLATE)


def load_passwords():
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def db_checks(values):
    checks = []
    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            ensure_first_machine_demand_baseline(cur, values)
            conn.commit()
            cur.execute(
                """
                SELECT so.id, so.order_no, c.name AS customer_name, so.project_code, so.serial_no,
                       so.status, so.total_amount, COUNT(soi.id) AS item_lines
                FROM sales_orders so
                LEFT JOIN customers c ON c.id=so.customer_id
                LEFT JOIN sales_order_items soi ON soi.order_id=so.id
                WHERE so.order_no=%s
                GROUP BY so.id, c.name
                """,
                (values["sales_order_no"],),
            )
            order = cur.fetchone()
            checks.append(("sales_order_exists", bool(order), order.get("order_no") if order else "missing"))
            if order:
                checks.append(("project_code_matches", order.get("project_code") == values["项目号"], order.get("project_code")))
                checks.append(("serial_no_matches", order.get("serial_no") == values["机号"], order.get("serial_no")))
                checks.append(("customer_matches", order.get("customer_name") == values["客户名称"], order.get("customer_name")))
                checks.append(("sales_item_lines", int(order.get("item_lines") or 0) > 0, order.get("item_lines")))
                order_id = order["id"]
            else:
                order_id = None

            cur.execute(
                """
                SELECT b.id, b.bom_no, b.version, b.status, COUNT(bi.id) AS item_lines
                FROM boms b
                LEFT JOIN bom_items bi ON bi.bom_id=b.id
                WHERE b.bom_no=%s
                GROUP BY b.id
                """,
                (values["BOM编号"],),
            )
            bom = cur.fetchone()
            checks.append(("bom_exists", bool(bom), bom.get("bom_no") if bom else "missing"))
            if bom:
                checks.append(("bom_version_matches", bom.get("version") == values["BOM版本"], bom.get("version")))
                checks.append(("bom_has_items", int(bom.get("item_lines") or 0) > 0, bom.get("item_lines")))

            cur.execute(
                """
                SELECT COUNT(*) AS value
                FROM products
                WHERE code IN (%s, %s, %s)
                """,
                (values["产品编码"], values["关键物料1编码"], values.get("关键物料2编码") or values["关键物料1编码"]),
            )
            product_count = int((cur.fetchone() or {}).get("value") or 0)
            checks.append(("product_and_materials_exist", product_count >= 3, product_count))

            if order_id:
                cur.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM sales_orders so
                    JOIN sales_order_items soi ON soi.order_id=so.id
                    JOIN boms b ON b.product_id=soi.product_id
                    JOIN bom_items bi ON bi.bom_id=b.id
                    WHERE so.id=%s
                    """,
                    (order_id,),
                )
                linked_bom_items = int((cur.fetchone() or {}).get("value") or 0)
                checks.append(("sales_order_links_to_bom_items", linked_bom_items > 0, linked_bom_items))
    finally:
        conn.close()
    return checks


def page_checks(values):
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-workflow-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    from app import create_app

    passwords = load_passwords()
    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000})
    cases = {
        "pilot_sales": [f"/projects?keyword={values['项目号']}", f"/projects?keyword={values['机号']}", "/sales-orders"],
        "pilot_purchase": ["/purchase_request", "/purchase-orders"],
        "pilot_warehouse": ["/inventory", "/transactions"],
        "pilot_production": ["/engineering/kitting", "/production-enhance/mrp-requirements", "/procurement/suggestions", "/work-orders", "/requisition"],
        "pilot_service": ["/service-cards", "/service-orders"],
        "pilot_finance": ["/finance", "/receivables", "/payables"],
    }
    checks = []
    markers = ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5", "\u5b2b\u6924"]
    for username, paths in cases.items():
        client = app.test_client()
        password = passwords.get(username)
        login = client.post("/login", data={"username": username, "password": password})
        checks.append((f"{username}_login", login.status_code == 302, login.status_code))
        if login.status_code != 302:
            continue
        for path in paths:
            response = client.get(path)
            body = response.get_data(as_text=True)
            clean = not any(marker in body for marker in markers)
            checks.append((f"{username}:{path}:status", response.status_code == 200, response.status_code))
            checks.append((f"{username}:{path}:clean", clean, "clean" if clean else "mojibake"))
        if username == "pilot_sales":
            response = client.get(f"/projects?keyword={values['项目号']}")
            body = response.get_data(as_text=True)
            checks.append(("pilot_sales_project_visible", values["项目号"] in body and values["机号"] in body, "project ledger"))
    return checks


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    values = load_values()
    checks = db_checks(values) + page_checks(values)
    failures = [(name, detail) for name, ok, detail in checks if not ok]

    print("first_machine_workflow_audit=ok" if not failures else "first_machine_workflow_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"sales_order={values.get('sales_order_no')}")
    print(f"project_code={values.get('项目号')}")
    print(f"serial_no={values.get('机号')}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
