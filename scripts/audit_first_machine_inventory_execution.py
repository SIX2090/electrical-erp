import os
import sys
from pathlib import Path


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


def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def count_rows(cur, sql, params=()):
    cur.execute(sql, params)
    return int((cur.fetchone() or {}).get("value") or 0)


def select_stock(cur, cabinet_no):
    return fetch_one(
        cur,
        """
        SELECT ib.product_id, p.code AS product_code, ib.warehouse_id, ib.location_id,
               COALESCE(ib.lot_no, '') AS lot_no, ib.cabinet_no, ib.quantity, ib.unit_cost
        FROM inventory_balances ib
        JOIN products p ON p.id=ib.product_id
        WHERE ib.cabinet_no=%s AND COALESCE(ib.quantity, 0) > 0
        ORDER BY CASE WHEN ib.warehouse_id IS NOT NULL THEN 0 ELSE 1 END, ib.quantity DESC, ib.id
        LIMIT 1
        """,
        (cabinet_no,),
    )


def select_to_warehouse(cur, from_warehouse_id):
    row = fetch_one(cur, "SELECT id FROM warehouses WHERE id<>COALESCE(%s, -1) ORDER BY id LIMIT 1", (from_warehouse_id,))
    if row:
        return row["id"]
    row = fetch_one(cur, "SELECT id FROM warehouses ORDER BY id LIMIT 1")
    return row["id"] if row else None


def ensure_execution_docs(cur, stock, to_warehouse_id, project_code, cabinet_no):
    if not stock or not to_warehouse_id:
        return
    transfer_no = f"TO-{project_code}"
    check_no = f"IC-{project_code}"
    adj_no = f"IA-{project_code}"

    cur.execute(
        """
        INSERT INTO transfer_orders
            (transfer_no, transfer_date, from_warehouse_id, to_warehouse_id, status,
             remark, project_code, posted_at)
        VALUES (%s, CURRENT_DATE, %s, %s, '已过账',
                'first machine inventory execution transfer', %s, NOW())
        ON CONFLICT (transfer_no) DO NOTHING
        """,
        (transfer_no, stock.get("warehouse_id"), to_warehouse_id, project_code),
    )
    transfer = fetch_one(cur, "SELECT id, transfer_no FROM transfer_orders WHERE transfer_no=%s", (transfer_no,))
    if transfer:
        cur.execute(
            """
            INSERT INTO transfer_order_items
                (transfer_id, product_id, quantity, lot_no, cabinet_no, unit_cost, remark,
                 line_project_code, material_code, material_name, material_spec, material_unit, amount)
            SELECT %s, %s, 1, %s, %s, %s, 'first machine inventory execution transfer',
                   %s, p.code, p.name, COALESCE(p.specification, ''), COALESCE(p.unit, ''), %s
            FROM products p
            WHERE p.id=%s
              AND NOT EXISTS (
                  SELECT 1 FROM transfer_order_items WHERE transfer_id=%s AND product_id=%s
              )
            """,
            (
                transfer["id"],
                stock["product_id"],
                stock.get("lot_no") or "",
                cabinet_no,
                stock.get("unit_cost") or 0,
                project_code,
                stock.get("unit_cost") or 0,
                stock["product_id"],
                transfer["id"],
                stock["product_id"],
            ),
        )
        for tx_type, warehouse_id, qty in (("调拨出库", stock.get("warehouse_id"), -1), ("调拨入库", to_warehouse_id, 1)):
            cur.execute(
                """
                INSERT INTO stock_transactions
                    (transaction_date, transaction_type, product_id, quantity, unit_cost,
                     reference_no, lot_no, cabinet_no, project_code, remark, warehouse_id,
                     source_type, material_code, material_name, material_spec, material_unit,
                     amount, source_doc_type, source_doc_no)
                SELECT CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s,
                       'first machine inventory execution transfer', %s, 'inventory_transfer',
                       p.code, p.name, COALESCE(p.specification, ''), COALESCE(p.unit, ''),
                       ABS(%s * %s), 'inventory_transfer', %s
                FROM products p
                WHERE p.id=%s
                  AND NOT EXISTS (
                      SELECT 1 FROM stock_transactions
                      WHERE reference_no=%s AND transaction_type=%s AND product_id=%s
                  )
                """,
                (
                    tx_type,
                    stock["product_id"],
                    qty,
                    stock.get("unit_cost") or 0,
                    transfer_no,
                    stock.get("lot_no") or "",
                    cabinet_no,
                    project_code,
                    warehouse_id,
                    qty,
                    stock.get("unit_cost") or 0,
                    transfer_no,
                    stock["product_id"],
                    transfer_no,
                    tx_type,
                    stock["product_id"],
                ),
            )

    cur.execute(
        """
        INSERT INTO inventory_check_orders
            (check_no, warehouse_id, check_date, status, remark, posted_at, project_code)
        VALUES (%s, %s, CURRENT_DATE, '已过账', 'first machine inventory execution check', NOW(), %s)
        ON CONFLICT (check_no) DO NOTHING
        """,
        (check_no, to_warehouse_id, project_code),
    )
    check_order = fetch_one(cur, "SELECT id, check_no FROM inventory_check_orders WHERE check_no=%s", (check_no,))
    if check_order:
        cur.execute(
            """
            INSERT INTO inventory_check_order_items
                (check_id, product_id, book_qty, actual_qty, diff_qty, lot_no, cabinet_no, unit_cost, amount)
            SELECT %s, %s, 1, 1, 0, %s, %s, %s, 0
            WHERE NOT EXISTS (
                SELECT 1 FROM inventory_check_order_items WHERE check_id=%s AND product_id=%s
            )
            """,
            (check_order["id"], stock["product_id"], stock.get("lot_no") or "", cabinet_no, stock.get("unit_cost") or 0, check_order["id"], stock["product_id"]),
        )

    cur.execute(
        """
        INSERT INTO inventory_adjustments
            (adj_no, adj_date, product_id, diff_quantity, unit_cost, adj_type, status,
             lot_no, remark, project_code, warehouse_id, cabinet_no, line_project_code,
             material_code, material_name, material_spec, material_unit, posted_at, amount)
        SELECT %s, CURRENT_DATE, %s, 1, %s, 'execution_check', '生效', %s,
               'first machine inventory execution adjustment', %s, %s, %s, %s,
               p.code, p.name, COALESCE(p.specification, ''), COALESCE(p.unit, ''), NOW(), %s
        FROM products p
        WHERE p.id=%s
          AND NOT EXISTS (SELECT 1 FROM inventory_adjustments WHERE adj_no=%s)
        """,
        (
            adj_no,
            stock["product_id"],
            stock.get("unit_cost") or 0,
            stock.get("lot_no") or "",
            project_code,
            to_warehouse_id,
            cabinet_no,
            project_code,
            stock.get("unit_cost") or 0,
            stock["product_id"],
            adj_no,
        ),
    )
    cur.execute(
        """
        INSERT INTO stock_transactions
            (transaction_date, transaction_type, product_id, quantity, unit_cost,
             reference_no, lot_no, cabinet_no, project_code, remark, warehouse_id,
             source_type, material_code, material_name, material_spec, material_unit,
             amount, source_doc_type, source_doc_no)
        SELECT CURRENT_TIMESTAMP, '库存调整', %s, 1, %s, %s, %s, %s, %s,
               'first machine inventory execution adjustment', %s, 'inventory_adjustment',
               p.code, p.name, COALESCE(p.specification, ''), COALESCE(p.unit, ''),
               %s, 'inventory_adjustment', %s
        FROM products p
        WHERE p.id=%s
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions
              WHERE reference_no=%s AND transaction_type='库存调整' AND product_id=%s
          )
        """,
        (
            stock["product_id"],
            stock.get("unit_cost") or 0,
            adj_no,
            stock.get("lot_no") or "",
            cabinet_no,
            project_code,
            to_warehouse_id,
            stock.get("unit_cost") or 0,
            adj_no,
            stock["product_id"],
            adj_no,
            stock["product_id"],
        ),
    )


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-inventory-execution")
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
            stock = select_stock(cur, cabinet_no)
            checks.append(("stock_ready_for_execution", bool(stock), stock.get("product_code") if stock else "missing"))
            to_warehouse_id = select_to_warehouse(cur, stock.get("warehouse_id") if stock else None) if stock else None
            checks.append(("target_warehouse_ready", bool(to_warehouse_id), to_warehouse_id))
            ensure_execution_docs(cur, stock, to_warehouse_id, project_code, cabinet_no)
        conn.commit()
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
            transfer = fetch_one(cur, "SELECT id, transfer_no FROM transfer_orders WHERE project_code=%s AND remark=%s ORDER BY id DESC LIMIT 1", (project_code, "first machine inventory execution transfer"))
            inventory_check = fetch_one(cur, "SELECT id, check_no, status FROM inventory_check_orders WHERE project_code=%s AND remark=%s ORDER BY id DESC LIMIT 1", (project_code, "first machine inventory execution check"))
            adjustment = fetch_one(cur, "SELECT id, adj_no FROM inventory_adjustments WHERE project_code=%s AND remark=%s ORDER BY id DESC LIMIT 1", (project_code, "first machine inventory execution adjustment"))
            checks.append(("inventory_transfer_traceable", bool(transfer), transfer.get("transfer_no") if transfer else "missing"))
            checks.append(("inventory_check_traceable", bool(inventory_check), inventory_check.get("check_no") if inventory_check else "missing"))
            checks.append(("inventory_check_posted", bool(inventory_check) and inventory_check.get("status") == "已过账", inventory_check.get("status") if inventory_check else "missing"))
            checks.append(("inventory_adjustment_traceable", bool(adjustment), adjustment.get("adj_no") if adjustment else "missing"))
            checks.append(("transfer_stock_flow_recorded", count_rows(cur, "SELECT COUNT(*) AS value FROM stock_transactions WHERE project_code=%s AND cabinet_no=%s AND reference_no=%s", (project_code, cabinet_no, transfer.get("transfer_no") if transfer else "")) >= 2, transfer.get("transfer_no") if transfer else "missing"))
            checks.append(("check_stock_flow_recorded", count_rows(cur, "SELECT COUNT(*) AS value FROM inventory_check_order_items WHERE check_id=%s AND COALESCE(diff_qty,0)<>0", (inventory_check.get("id") if inventory_check else None,)) == 0, inventory_check.get("check_no") if inventory_check else "missing"))
            checks.append(("adjustment_stock_flow_recorded", count_rows(cur, "SELECT COUNT(*) AS value FROM stock_transactions WHERE project_code=%s AND cabinet_no=%s AND reference_no=%s", (project_code, cabinet_no, adjustment.get("adj_no") if adjustment else "")) >= 1, adjustment.get("adj_no") if adjustment else "missing"))
    finally:
        conn.close()

    if login.status_code == 302:
        page_expectations = [
            (f"/transfers?keyword={project_code}", [project_code]),
            (f"/inventory_checks?keyword={project_code}", [project_code]),
            (f"/adjustments?keyword={project_code}", [project_code, "IA"]),
            (f"/transactions?keyword={project_code}", [project_code, cabinet_no]),
            (f"/projects?keyword={project_code}", [project_code]),
        ]
        if transfer:
            page_expectations.append((f"/transfers/{transfer['id']}", [project_code, cabinet_no]))
        if inventory_check:
            page_expectations.append((f"/inventory_checks/{inventory_check['id']}", [project_code, cabinet_no]))
        for path, expected in page_expectations:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_inventory_execution_audit=ok" if not failures else "first_machine_inventory_execution_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"cabinet_no={cabinet_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
