from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import (
    ensure_first_machine_production_inventory_baseline,
    load_first_machine_values,
)


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-inventory-trace")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_first_machine_values(TEMPLATE)
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    material_codes = [values["material_code_1"], values.get("material_code_2") or ""]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            ensure_first_machine_production_inventory_baseline(cur, values)
            conn.commit()
            cur.execute(
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(ib.quantity), 0) AS qty
                FROM inventory_balances ib
                JOIN products p ON p.id=ib.product_id
                WHERE ib.cabinet_no=%s
                  AND p.code IN (%s, %s)
                  AND COALESCE(ib.quantity, 0) > 0
                """,
                (cabinet_no, material_codes[0], material_codes[1]),
            )
            balance = cur.fetchone() or {}
            checks.append(("inventory_balance_by_serial", int(balance.get("lines") or 0) >= 1, balance.get("lines")))
            checks.append(("inventory_balance_qty_positive", balance.get("qty", 0) > 0, balance.get("qty")))

            cur.execute(
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(st.quantity), 0) AS qty
                FROM stock_transactions st
                JOIN products p ON p.id=st.product_id
                WHERE st.project_code=%s
                  AND st.cabinet_no=%s
                  AND p.code IN (%s, %s)
                  AND st.transaction_type='采购入库'
                """,
                (project_code, cabinet_no, material_codes[0], material_codes[1]),
            )
            tx = cur.fetchone() or {}
            checks.append(("stock_transactions_by_project_cabinet", int(tx.get("lines") or 0) >= 1, tx.get("lines")))
            checks.append(("stock_transaction_qty_positive", tx.get("qty", 0) > 0, tx.get("qty")))

            cur.execute(
                """
                SELECT COUNT(*) AS lines
                FROM purchase_receipts pr
                JOIN purchase_receipt_items pri ON pri.receipt_id=pr.id
                JOIN products p ON p.id=pri.product_id
                WHERE pr.project_code=%s
                  AND pr.cabinet_no=%s
                  AND p.code IN (%s, %s)
                """,
                (project_code, cabinet_no, material_codes[0], material_codes[1]),
            )
            receipt_lines = int((cur.fetchone() or {}).get("lines") or 0)
            checks.append(("receipt_lines_trace_to_materials", receipt_lines >= 1, receipt_lines))
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "admin", "password": "admin"})
    checks.append(("admin_login", login.status_code == 302, login.status_code))
    if login.status_code == 302:
        page_expectations = [
            (f"/inventory?keyword={cabinet_no}", [cabinet_no, material_codes[0]]),
            (f"/inventory/detail?keyword={cabinet_no}", [cabinet_no, material_codes[0]]),
            (f"/transactions?keyword={project_code}", [project_code, cabinet_no, material_codes[0]]),
            (f"/transactions?keyword={cabinet_no}", [project_code, cabinet_no, material_codes[0]]),
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
    print("first_machine_inventory_trace_audit=ok" if not failures else "first_machine_inventory_trace_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"cabinet_no={cabinet_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
