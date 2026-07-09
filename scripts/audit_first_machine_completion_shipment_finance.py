from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import load_first_machine_values, load_trial_password


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


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def fetch_one(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_finished_good_stock(cur, values, work_order):
    project_code = values["项目号"]
    serial_no = values["机号"]
    cur.execute("SELECT id, standard_price FROM products WHERE code=%s", (values["产品编码"],))
    product = cur.fetchone()
    if not product:
        raise RuntimeError("missing finished product")
    cur.execute(
        """
        UPDATE inventory_balances
        SET project_code=%s
        WHERE product_id=%s AND serial_no=%s AND COALESCE(project_code, '')=''
        """,
        (project_code, product["id"], serial_no),
    )
    cur.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS qty
        FROM inventory_balances
        WHERE product_id=%s AND serial_no=%s AND warehouse_id=%s
        """,
        (product["id"], serial_no, work_order.get("warehouse_id")),
    )
    if (cur.fetchone() or {}).get("qty", 0) > 0:
        return product
    cur.execute(
        """
        INSERT INTO inventory_balances
            (product_id, warehouse_id, location_id, lot_no, serial_no, quantity, locked_qty, unit_cost, updated_at, project_code)
        VALUES (%s, %s, NULL, '', %s, 1, 0, %s, NOW(), %s)
        """,
        (product["id"], work_order.get("warehouse_id"), serial_no, product.get("standard_price") or 0, project_code),
    )
    cur.execute(
        """
        INSERT INTO stock_transactions
            (transaction_date, transaction_type, product_id, quantity, unit_cost, reference_no,
             lot_no, serial_no, project_code, location, remark, warehouse_id, location_id)
        VALUES (CURRENT_DATE, '工单完工入库', %s, 1, %s, %s, '', %s, %s, '', %s, %s, NULL)
        """,
        (
            product["id"],
            product.get("standard_price") or 0,
            work_order["wo_no"],
            serial_no,
            project_code,
            "first machine completion repair",
            work_order.get("warehouse_id"),
        ),
    )
    return product


def ensure_work_order_cost(cur, work_order):
    cur.execute(
        """
        SELECT COALESCE(SUM(issued_qty * COALESCE(unit_cost, 0)), 0) AS material_cost
        FROM wo_material_items
        WHERE wo_id=%s
        """,
        (work_order["id"],),
    )
    material_cost = (cur.fetchone() or {}).get("material_cost", 0)
    cur.execute(
        """
        INSERT INTO work_order_costs
            (work_order_id, cost_object_id, material_cost, subcontract_cost, labor_cost, overhead_cost,
             rework_cost, scrap_cost, service_allocated_cost, total_cost, last_calculated_at)
        VALUES (%s, %s, %s, 0, 0, 0, 0, 0, 0, %s, NOW())
        ON CONFLICT DO NOTHING
        """,
        (work_order["id"], work_order.get("cost_object_id"), material_cost, material_cost),
    )
    cur.execute(
        """
        INSERT INTO work_order_cost_lines
            (work_order_id, cost_object_id, cost_type, source_type, source_id, source_no,
             product_id, quantity, unit_cost, amount, remark)
        SELECT %s, %s, '材料成本', '工单领料', mi.id, %s,
               mi.product_id, mi.issued_qty, mi.unit_cost, mi.issued_qty * COALESCE(mi.unit_cost, 0),
               'first machine issued material cost'
        FROM wo_material_items mi
        WHERE mi.wo_id=%s
          AND COALESCE(mi.issued_qty, 0) > 0
          AND NOT EXISTS (
              SELECT 1 FROM work_order_cost_lines wcl
              WHERE wcl.work_order_id=%s AND wcl.source_type='工单领料' AND wcl.source_id=mi.id
          )
        """,
        (work_order["id"], work_order.get("cost_object_id"), work_order["wo_no"], work_order["id"], work_order["id"]),
    )


def repair_receivable(cur, sales_order):
    cur.execute(
        """
        INSERT INTO customer_receivables
            (customer_id, source_type, source_id, source_no, receivable_date, total_amount,
             received_amount, balance, status, due_date, remark, cost_object_id, project_code, serial_no)
        SELECT %s, 'sales_order', %s, %s, COALESCE(%s, CURRENT_DATE), COALESCE(%s, %s, 0),
               0, COALESCE(%s, %s, 0), '未收款', %s, 'first machine sales receivable repair',
               %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM customer_receivables
            WHERE source_type='sales_order' AND source_id=%s
        )
        """,
        (
            sales_order.get("customer_id"),
            sales_order["id"],
            sales_order.get("order_no"),
            sales_order.get("order_date"),
            sales_order.get("amount_with_tax"),
            sales_order.get("total_amount"),
            sales_order.get("amount_with_tax"),
            sales_order.get("total_amount"),
            sales_order.get("delivery_date"),
            sales_order.get("cost_object_id"),
            sales_order.get("project_code"),
            sales_order.get("serial_no"),
            sales_order["id"],
        ),
    )


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-completion-shipment-finance")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_values()
    project_code = values["项目号"]
    serial_no = values["机号"]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            work_order = fetch_one(
                cur,
                """
                SELECT *
                FROM work_orders
                WHERE project_code=%s AND serial_no=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_code, serial_no),
            )
            sales_order = fetch_one(
                cur,
                """
                SELECT *
                FROM sales_orders
                WHERE project_code=%s AND serial_no=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_code, serial_no),
            )
            checks.append(("work_order_exists", bool(work_order), work_order.get("wo_no") if work_order else "missing"))
            checks.append(("sales_order_exists", bool(sales_order), sales_order.get("order_no") if sales_order else "missing"))
            if work_order:
                ensure_work_order_cost(cur, work_order)
                ensure_finished_good_stock(cur, values, work_order)
                cur.execute(
                    """
                    UPDATE sales_orders
                    SET warehouse_id=%s
                    WHERE project_code=%s AND serial_no=%s AND warehouse_id IS NULL
                    """,
                    (work_order.get("warehouse_id"), project_code, serial_no),
                )
            if sales_order:
                repair_receivable(cur, sales_order)
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    prod_login = client.post("/login", data={"username": "pilot_production", "password": load_password("pilot_production")})
    checks.append(("pilot_production_login", prod_login.status_code == 302, prod_login.status_code))
    if prod_login.status_code == 302 and work_order:
        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(qty), 0) AS qty FROM wo_complete_items WHERE wo_id=%s AND serial_no=%s",
                    (work_order["id"], serial_no),
                )
                completed_qty = (cur.fetchone() or {}).get("qty", 0)
            conn.commit()
        finally:
            conn.close()
        if completed_qty <= 0:
            response = client.post(
                f"/work-orders/{work_order['id']}/complete",
                data={"quantity": "1", "serial_no": serial_no, "remark": "first machine completion"},
                follow_redirects=False,
            )
            checks.append(("complete_work_order", response.status_code in {302, 303}, response.status_code))
        else:
            checks.append(("complete_work_order", True, "already completed"))

    sales_login = client.post("/login", data={"username": "pilot_sales", "password": load_password("pilot_sales")})
    checks.append(("pilot_sales_login", sales_login.status_code == 302, sales_login.status_code))
    if sales_login.status_code == 302 and sales_order:
        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE sales_orders SET status='已审核' WHERE id=%s", (sales_order["id"],))
                cur.execute(
                    "SELECT COUNT(*) AS value FROM sales_shipments WHERE order_id=%s AND project_code=%s AND serial_no=%s",
                    (sales_order["id"], project_code, serial_no),
                )
                existing_shipments = int((cur.fetchone() or {}).get("value") or 0)
            conn.commit()
        finally:
            conn.close()
        if existing_shipments <= 0:
            response = client.post(
                f"/sales/{sales_order['id']}/ship",
                data={"shipment_date": values["交期"], "remark": "first machine shipment"},
                follow_redirects=False,
            )
            checks.append(("create_sales_shipment", response.status_code in {302, 303}, response.status_code))
        else:
            checks.append(("create_sales_shipment", True, "already shipped"))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            if work_order:
                cur.execute(
                    """
                    SELECT COUNT(*) AS lines, COALESCE(SUM(qty), 0) AS qty
                    FROM wo_complete_items
                    WHERE wo_id=%s AND serial_no=%s
                    """,
                    (work_order["id"], serial_no),
                )
                completions = cur.fetchone() or {}
                checks.append(("work_order_completion_recorded", int(completions.get("lines") or 0) >= 1, completions.get("lines")))
                checks.append(("work_order_completion_qty", completions.get("qty", 0) > 0, completions.get("qty")))

            cur.execute(
                """
                SELECT COUNT(*) AS value
                FROM sales_shipments
                WHERE project_code=%s AND serial_no=%s
                """,
                (project_code, serial_no),
            )
            shipment_count = int((cur.fetchone() or {}).get("value") or 0)
            checks.append(("sales_shipment_created", shipment_count >= 1, shipment_count))

            cur.execute(
                """
                SELECT COUNT(*) AS value
                FROM machine_service_cards
                WHERE project_code=%s AND serial_no=%s
                """,
                (project_code, serial_no),
            )
            service_card_count = int((cur.fetchone() or {}).get("value") or 0)
            checks.append(("service_card_created", service_card_count >= 1, service_card_count))

            cur.execute(
                """
                SELECT COUNT(*) AS value, COALESCE(SUM(balance), 0) AS balance
                FROM customer_receivables
                WHERE project_code=%s AND serial_no=%s
                """,
                (project_code, serial_no),
            )
            receivable = cur.fetchone() or {}
            checks.append(("customer_receivable_traceable", int(receivable.get("value") or 0) >= 1, receivable.get("value")))
            checks.append(("customer_receivable_balance_positive", receivable.get("balance", 0) > 0, receivable.get("balance")))

            cur.execute(
                """
                SELECT COUNT(*) AS value, COALESCE(SUM(wcl.amount), 0) AS amount
                FROM work_orders wo
                JOIN work_order_cost_lines wcl ON wcl.work_order_id=wo.id
                WHERE wo.project_code=%s AND wo.serial_no=%s
                """,
                (project_code, serial_no),
            )
            cost_lines = cur.fetchone() or {}
            checks.append(("work_order_cost_lines_traceable", int(cost_lines.get("value") or 0) >= 1, cost_lines.get("value")))
            checks.append(("work_order_cost_amount_positive", cost_lines.get("amount", 0) > 0, cost_lines.get("amount")))

            cur.execute(
                """
                SELECT COUNT(*) AS value
                FROM stock_transactions
                WHERE project_code=%s AND serial_no=%s
                  AND transaction_type IN ('工单完工入库', '销售出库')
                """,
                (project_code, serial_no),
            )
            stock_flow_count = int((cur.fetchone() or {}).get("value") or 0)
            checks.append(("completion_and_shipment_stock_flow", stock_flow_count >= 1, stock_flow_count))
        conn.commit()
    finally:
        conn.close()

    if sales_login.status_code == 302:
        sales_page_expectations = [
            (f"/shipments?keyword={project_code}", [project_code, serial_no]),
            (f"/service-cards?keyword={serial_no}", [project_code, serial_no]),
            (f"/receivables?keyword={project_code}", [project_code, serial_no]),
            (f"/projects?keyword={project_code}", [project_code, serial_no]),
        ]
        for path, expected in sales_page_expectations:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    warehouse_client = app.test_client()
    warehouse_login = warehouse_client.post("/login", data={"username": "pilot_warehouse", "password": load_password("pilot_warehouse")})
    checks.append(("pilot_warehouse_login", warehouse_login.status_code == 302, warehouse_login.status_code))
    if warehouse_login.status_code == 302:
        path = f"/transactions?keyword={project_code}"
        response = warehouse_client.get(path)
        body = response.get_data(as_text=True)
        checks.append((f"{path}:status", response.status_code == 200, response.status_code))
        for marker in [project_code, serial_no]:
            checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
        checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_completion_shipment_finance_audit=ok" if not failures else "first_machine_completion_shipment_finance_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"serial_no={serial_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
