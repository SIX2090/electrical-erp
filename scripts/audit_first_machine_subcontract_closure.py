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
        "product_code": "GT-RD-TRIAL-001",
        "material_code": "MAT-GT-DRUM-TRIAL-001",
    }
    if not TEMPLATE.exists():
        return values
    with TEMPLATE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            actual = (row[1] or "").strip()
            if not actual:
                continue
            if actual.startswith("PJ-GT-"):
                values["project_code"] = actual
            elif actual.startswith("SN-GT-"):
                values["serial_no"] = actual
            elif actual.startswith("GT-") and "TRIAL" in actual:
                values["product_code"] = actual
            elif actual.startswith("MAT-GT-") and "TRIAL" in actual and values["material_code"] == "MAT-GT-DRUM-TRIAL-001":
                values["material_code"] = actual
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


def ensure_supplier(cur):
    supplier = fetch_one(cur, "SELECT id FROM suppliers WHERE remark=%s OR name=%s LIMIT 1", ("first-machine-subcontractor", "First Machine Trial Outsource Processor"))
    if supplier:
        return supplier["id"]
    cur.execute(
        """
        INSERT INTO suppliers (name, contact_person, phone, address, lead_time_days, remark)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        ("First Machine Trial Outsource Processor", "trial processor", "13800000000", "trial outsource site", 5, "first-machine-subcontractor"),
    )
    return cur.fetchone()["id"]


def ensure_subcontract_order(cur, values):
    project_code = values["project_code"]
    serial_no = values["serial_no"]
    order = fetch_one(
        cur,
        """
        SELECT *
        FROM subcontract_orders
        WHERE project_code=%s AND serial_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, serial_no),
    )
    if order:
        return order

    product = fetch_one(cur, "SELECT id, standard_price FROM products WHERE code=%s", (values["material_code"],))
    if not product:
        product = fetch_one(cur, "SELECT id, standard_price FROM products WHERE code=%s", (values["product_code"],))
    if not product:
        raise RuntimeError("missing subcontract product")
    supplier_id = ensure_supplier(cur)
    work_order = fetch_one(
        cur,
        """
        SELECT id, warehouse_id, cost_object_id
        FROM work_orders
        WHERE project_code=%s AND serial_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, serial_no),
    )
    unit_price = product.get("standard_price") or 800
    if unit_price <= 0:
        unit_price = 800
    cur.execute(
        """
        INSERT INTO subcontract_orders
            (order_no, supplier_id, order_date, required_date, status, total_amount,
             tax_amount, total_tax_amount, remark, parent_work_order_id, warehouse_id,
             cost_object_id, project_code, serial_no, product_id, quantity, unit_price,
             updated_at)
        VALUES
            (%s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '5 days', %s, %s,
             0, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            "OS-GT-TRIAL-20260526-001",
            supplier_id,
            "released",
            unit_price,
            unit_price,
            "first machine subcontract closure",
            work_order.get("id") if work_order else None,
            work_order.get("warehouse_id") if work_order else None,
            work_order.get("cost_object_id") if work_order else None,
            project_code,
            serial_no,
            product["id"],
            unit_price,
        ),
    )
    return cur.fetchone()


def ensure_issue(cur, order):
    issue = fetch_one(
        cur,
        """
        SELECT *
        FROM subcontract_issue_orders
        WHERE subcontract_order_id=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (order["id"],),
    )
    if issue:
        return issue
    cur.execute(
        """
        INSERT INTO subcontract_issue_orders
            (issue_no, date, subcontract_order_id, supplier_id, status, total_quantity,
             remark, operator_id, updated_at)
        VALUES
            (%s, CURRENT_DATE, %s, %s, %s, %s, %s, NULL, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        ("OSI-GT-TRIAL-20260526-001", order["id"], order.get("supplier_id"), "completed", order.get("quantity") or 1, "first machine subcontract issue"),
    )
    issue = cur.fetchone()
    cur.execute("UPDATE subcontract_orders SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s", ("released", order["id"]))
    return issue


def ensure_receive(cur, order):
    receive = fetch_one(
        cur,
        """
        SELECT *
        FROM subcontract_receive_orders
        WHERE subcontract_order_id=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (order["id"],),
    )
    if receive:
        return receive
    cur.execute(
        """
        INSERT INTO subcontract_receive_orders
            (receive_no, date, subcontract_order_id, supplier_id, status, total_quantity,
             total_scrap, remark, operator_id, updated_at)
        VALUES
            (%s, CURRENT_DATE, %s, %s, %s, %s, 0, %s, NULL, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        ("OSR-GT-TRIAL-20260526-001", order["id"], order.get("supplier_id"), "completed", order.get("quantity") or 1, "first machine subcontract receive"),
    )
    receive = cur.fetchone()
    cur.execute("UPDATE subcontract_orders SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s", ("completed", order["id"]))
    return receive


def ensure_payable(cur, order):
    payable = fetch_one(
        cur,
        """
        SELECT *
        FROM supplier_payables
        WHERE doc_type='subcontract_order' AND doc_id=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (order["id"],),
    )
    amount = order.get("total_amount") or (order.get("quantity") or 1) * (order.get("unit_price") or 0)
    if payable:
        cur.execute(
            """
            UPDATE supplier_payables
            SET supplier_id=%s, doc_no=%s, amount=%s,
                balance=GREATEST(%s - COALESCE(paid_amount, 0), 0),
                finance_remark=COALESCE(finance_remark, %s)
            WHERE id=%s
            """,
            (order["supplier_id"], order["order_no"], amount, amount, "first machine subcontract payable", payable["id"]),
        )
        return payable
    cur.execute(
        """
        INSERT INTO supplier_payables
            (supplier_id, doc_type, doc_id, doc_no, doc_date, amount, paid_amount,
             balance, status, finance_remark, next_follow_up_date)
        VALUES
            (%s, 'subcontract_order', %s, %s, COALESCE(%s, CURRENT_DATE), %s, 0,
             %s, %s, %s, %s)
        RETURNING *
        """,
        (
            order["supplier_id"],
            order["id"],
            order["order_no"],
            order.get("order_date"),
            amount,
            amount,
            "unpaid",
            "first machine subcontract payable",
            order.get("required_date"),
        ),
    )
    return cur.fetchone()


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-subcontract-closure")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_trial_values()
    project_code = values["project_code"]
    serial_no = values["serial_no"]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            order = ensure_subcontract_order(cur, values)
            issue = ensure_issue(cur, order)
            receive = ensure_receive(cur, order)
            payable = ensure_payable(cur, order)
            checks.append(("subcontract_order_ready", bool(order), order.get("order_no") if order else "missing"))
            checks.append(("subcontract_issue_ready", bool(issue), issue.get("issue_no") if issue else "missing"))
            checks.append(("subcontract_receive_ready", bool(receive), receive.get("receive_no") if receive else "missing"))
            checks.append(("subcontract_payable_ready", bool(payable), payable.get("doc_no") if payable else "missing"))
        conn.commit()
    finally:
        conn.close()

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sc.id, sc.order_no, sc.project_code, sc.serial_no,
                       COALESCE(sc.quantity, 0) AS ordered_qty,
                       COALESCE(issue_sum.issued_qty, 0) AS issued_qty,
                       COALESCE(receive_sum.received_qty, 0) AS received_qty,
                       COALESCE(receive_sum.scrap_qty, 0) AS scrap_qty,
                       COALESCE(payable_sum.payable_amount, 0) AS payable_amount,
                       COALESCE(payable_sum.payable_balance, 0) AS payable_balance
                FROM subcontract_orders sc
                LEFT JOIN LATERAL (
                    SELECT COALESCE(SUM(total_quantity), 0) AS issued_qty
                    FROM subcontract_issue_orders sio
                    WHERE sio.subcontract_order_id=sc.id
                ) issue_sum ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COALESCE(SUM(total_quantity), 0) AS received_qty,
                           COALESCE(SUM(total_scrap), 0) AS scrap_qty
                    FROM subcontract_receive_orders sro
                    WHERE sro.subcontract_order_id=sc.id
                ) receive_sum ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COALESCE(SUM(amount), 0) AS payable_amount,
                           COALESCE(SUM(balance), 0) AS payable_balance
                    FROM supplier_payables sp
                    WHERE sp.doc_type='subcontract_order'
                      AND (sp.doc_id=sc.id OR sp.doc_no=sc.order_no)
                ) payable_sum ON TRUE
                WHERE sc.project_code=%s AND sc.serial_no=%s
                ORDER BY sc.id DESC
                LIMIT 1
                """,
                (project_code, serial_no),
            )
            summary = cur.fetchone() or {}
            checks.append(("subcontract_trace_project_serial", bool(summary), summary.get("order_no") if summary else "missing"))
            checks.append(("subcontract_issued_qty_positive", summary.get("issued_qty", 0) > 0, summary.get("issued_qty")))
            checks.append(("subcontract_received_qty_positive", summary.get("received_qty", 0) > 0, summary.get("received_qty")))
            checks.append(("subcontract_payable_amount_positive", summary.get("payable_amount", 0) > 0, summary.get("payable_amount")))
            checks.append(("subcontract_payable_balance_traceable", summary.get("payable_balance", 0) >= 0, summary.get("payable_balance")))

            checks.append(
                (
                    "subcontract_issue_linked",
                    count_rows(
                        cur,
                        """
                        SELECT COUNT(*) AS value
                        FROM subcontract_issue_orders sio
                        JOIN subcontract_orders sc ON sc.id=sio.subcontract_order_id
                        WHERE sc.project_code=%s AND sc.serial_no=%s
                        """,
                        (project_code, serial_no),
                    )
                    >= 1,
                    "project/serial",
                )
            )
            checks.append(
                (
                    "subcontract_receive_linked",
                    count_rows(
                        cur,
                        """
                        SELECT COUNT(*) AS value
                        FROM subcontract_receive_orders sro
                        JOIN subcontract_orders sc ON sc.id=sro.subcontract_order_id
                        WHERE sc.project_code=%s AND sc.serial_no=%s
                        """,
                        (project_code, serial_no),
                    )
                    >= 1,
                    "project/serial",
                )
            )
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_purchase", "password": load_password("pilot_purchase")})
    checks.append(("pilot_purchase_login", login.status_code == 302, login.status_code))
    if login.status_code == 302:
        project_detail_path = None
        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                sales_order = fetch_one(
                    cur,
                    """
                    SELECT id
                    FROM sales_orders
                    WHERE project_code=%s AND serial_no=%s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (project_code, serial_no),
                )
                if sales_order:
                    project_detail_path = f"/projects/{sales_order['id']}"
        finally:
            conn.close()
        page_expectations = [
            (f"/subcontract?keyword={project_code}", [project_code, serial_no, "OS-GT-TRIAL-20260526-001"]),
            (f"/subcontract_issue?keyword=OS-GT-TRIAL-20260526-001", ["OS-GT-TRIAL-20260526-001"]),
            (f"/subcontract_receive?keyword=OS-GT-TRIAL-20260526-001", ["OS-GT-TRIAL-20260526-001"]),
            (f"/payables?keyword=OS-GT-TRIAL-20260526-001", ["OS-GT-TRIAL-20260526-001"]),
            (f"/projects?keyword={project_code}", [project_code, serial_no]),
        ]
        if project_detail_path:
            page_expectations.append((project_detail_path, [project_code, serial_no, "OS-GT-TRIAL-20260526-001"]))
        else:
            checks.append(("project_detail_found", False, "missing sales order"))
        for path, expected in page_expectations:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_subcontract_closure_audit=ok" if not failures else "first_machine_subcontract_closure_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"serial_no={serial_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
