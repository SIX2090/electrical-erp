from __future__ import annotations

import csv
import os
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


def db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def load_values():
    values = {
        "project_code": "PJ-GT-TRIAL-20260526-001",
        "serial_no": "SN-GT-TRIAL-20260526-001",
        "product_code": "GT-RD-TRIAL-001",
        "bom_no": "BOM-GT-TRIAL-001",
        "sales_qty": "1",
        "material_code_1": "GT-MAT-TRIAL-001",
        "material_qty_1": "2",
        "material_code_2": "GT-MAT-TRIAL-002",
        "material_qty_2": "1",
        "warehouse_code": "GT-PILOT-WH",
    }
    if TEMPLATE.exists():
        with TEMPLATE.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                field = (row.get("field") or "").strip()
                actual = (row.get("actual") or "").strip()
                if field and actual:
                    values[field] = actual
    return values


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return next(iter(row.values())) if row else None


def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_product(cur, code, name, unit="pcs", price="10"):
    row = fetch_one(cur, "SELECT id FROM products WHERE code=%s", (code,))
    if row:
        return row["id"]
    cur.execute(
        """
        INSERT INTO products (code, name, category, unit, standard_price)
        VALUES (%s, %s, 'trial', %s, %s)
        RETURNING id
        """,
        (code, name, unit, price),
    )
    return cur.fetchone()["id"]


def ensure_warehouse(cur, code):
    row = fetch_one(cur, "SELECT id FROM warehouses WHERE code=%s OR name=%s ORDER BY id LIMIT 1", (code, code))
    if row:
        return row["id"]
    cur.execute("INSERT INTO warehouses (code, name) VALUES (%s, %s) RETURNING id", (code, code))
    return cur.fetchone()["id"]


def ensure_bom(cur, bom_no, product_id, material_lines):
    bom = fetch_one(cur, "SELECT id FROM boms WHERE bom_no=%s ORDER BY id DESC LIMIT 1", (bom_no,))
    if bom:
        bom_id = bom["id"]
    else:
        cur.execute(
            """
            INSERT INTO boms (bom_no, product_id, version, status, created_at)
            VALUES (%s, %s, 'A', 'approved', NOW())
            RETURNING id
            """,
            (bom_no, product_id),
        )
        bom_id = cur.fetchone()["id"]
    for material_id, qty in material_lines:
        exists = scalar(cur, "SELECT COUNT(*) FROM bom_items WHERE bom_id=%s AND product_id=%s", (bom_id, material_id))
        if not exists:
            cur.execute(
                """
                INSERT INTO bom_items (bom_id, product_id, quantity, unit, remark)
                VALUES (%s, %s, %s, 'pcs', 'first machine trial material')
                """,
                (bom_id, material_id, qty),
            )
    return bom_id


def ensure_stock(cur, product_id, warehouse_id, serial_no, qty):
    qty = Decimal(str(qty))
    row = fetch_one(
        cur,
        """
        SELECT id, quantity
        FROM inventory_balances
        WHERE product_id=%s AND COALESCE(warehouse_id,0)=COALESCE(%s,0)
          AND COALESCE(serial_no,'')=%s
        ORDER BY id LIMIT 1
        """,
        (product_id, warehouse_id, serial_no),
    )
    if row:
        if row["quantity"] < qty:
            cur.execute("UPDATE inventory_balances SET quantity=%s, unit_cost=10, updated_at=NOW() WHERE id=%s", (qty, row["id"]))
        return
    cur.execute(
        """
        INSERT INTO inventory_balances
            (product_id, warehouse_id, quantity, unit_cost, serial_no, updated_at)
        VALUES (%s, %s, %s, 10, %s, NOW())
        """,
        (product_id, warehouse_id, qty, serial_no),
    )


def ensure_work_order(cur, values, product_id, bom_id, warehouse_id, material_lines):
    project_code = values["project_code"]
    serial_no = values["serial_no"]
    row = fetch_one(
        cur,
        """
        SELECT id, wo_no
        FROM work_orders
        WHERE project_code=%s AND serial_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, serial_no),
    )
    if row:
        wo_id = row["id"]
        cur.execute("UPDATE work_orders SET warehouse_id=%s, bom_id=COALESCE(bom_id,%s) WHERE id=%s", (warehouse_id, bom_id, wo_id))
    else:
        cur.execute(
            """
            INSERT INTO work_orders
                (wo_no, wo_date, product_id, bom_id, warehouse_id, quantity, status,
                 planned_start_date, planned_end_date, project_code, serial_no, remark)
            VALUES
                ('WO-GT-TRIAL-20260526-001', CURRENT_DATE, %s, %s, %s, %s, 'new',
                 CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', %s, %s, 'first machine trial work order')
            RETURNING id, wo_no
            """,
            (product_id, bom_id, warehouse_id, values["sales_qty"], project_code, serial_no),
        )
        row = cur.fetchone()
        wo_id = row["id"]
    for material_id, required_qty in material_lines:
        exists = scalar(cur, "SELECT COUNT(*) FROM wo_material_items WHERE wo_id=%s AND product_id=%s", (wo_id, material_id))
        if not exists:
            cur.execute(
                """
                INSERT INTO wo_material_items (wo_id, product_id, required_qty, issued_qty, returned_qty, unit_cost, remark)
                VALUES (%s, %s, %s, 0, 0, 10, 'first machine issue demand')
                """,
                (wo_id, material_id, required_qty),
            )
    return row


def prepare_data(cur, values):
    warehouse_id = ensure_warehouse(cur, values["warehouse_code"])
    product_id = ensure_product(cur, values["product_code"], "First machine trial product", "set", "100")
    material_1_id = ensure_product(cur, values["material_code_1"], "First machine key material 1")
    material_lines = [(material_1_id, values["material_qty_1"])]
    ensure_stock(cur, material_1_id, warehouse_id, values["serial_no"], "20")
    if values.get("material_code_2"):
        material_2_id = ensure_product(cur, values["material_code_2"], "First machine key material 2")
        material_lines.append((material_2_id, values.get("material_qty_2") or "1"))
        ensure_stock(cur, material_2_id, warehouse_id, values["serial_no"], "20")
    bom_id = ensure_bom(cur, values["bom_no"], product_id, material_lines)
    return ensure_work_order(cur, values, product_id, bom_id, warehouse_id, material_lines), material_lines


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_values()
    checks = []
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            work_order, material_lines = prepare_data(cur, values)
            checks.append(("work_order_ready", bool(work_order), work_order.get("wo_no") if work_order else "missing"))
            cur.execute(
                "SELECT COUNT(*) AS lines, COALESCE(SUM(required_qty),0) AS required_qty, COALESCE(SUM(issued_qty),0) AS issued_qty FROM wo_material_items WHERE wo_id=%s",
                (work_order["id"],),
            )
            before = cur.fetchone() or {}
            checks.append(("material_lines_ready", int(before.get("lines") or 0) >= 1, before.get("lines")))
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit_first_machine"
        session["role"] = "admin"
    response = client.post(f"/work-orders/{work_order['id']}/issue-materials", data={"remark": "first machine issue"}, follow_redirects=False)
    checks.append(("issue_route_redirect", response.status_code in {302, 303}, response.status_code))

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(required_qty),0) AS required_qty, COALESCE(SUM(issued_qty),0) AS issued_qty FROM wo_material_items WHERE wo_id=%s",
                (work_order["id"],),
            )
            issued = cur.fetchone() or {}
            checks.append(("issued_qty_positive", issued.get("issued_qty", 0) > 0, issued.get("issued_qty")))
            checks.append(("issued_not_over_required", issued.get("issued_qty", 0) <= issued.get("required_qty", 0), f"{issued.get('issued_qty')}/{issued.get('required_qty')}"))
            cur.execute(
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(ABS(quantity)),0) AS qty
                FROM stock_transactions
                WHERE reference_no=%s
                   OR source_doc_no=%s
                """,
                (work_order["wo_no"], work_order["wo_no"]),
            )
            tx = cur.fetchone() or {}
            checks.append(("stock_transaction_recorded", int(tx.get("lines") or 0) >= 1, tx.get("lines")))
            checks.append(("stock_transaction_qty_positive", tx.get("qty", 0) > 0, tx.get("qty")))
    finally:
        conn.close()

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_work_order_issue_audit=ok" if not failures else "first_machine_work_order_issue_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={values['project_code']}")
    print(f"serial_no={values['serial_no']}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
