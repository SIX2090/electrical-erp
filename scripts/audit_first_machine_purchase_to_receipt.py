from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import ensure_first_machine_demand_baseline, load_first_machine_values, load_trial_password


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

def ensure_trial_suppliers(cur, values):
    suppliers = [
        ("SUP-GT-DRUM-TRIAL", "滚筒组件试运行供应商", values.get("关键物料1编码"), "58000"),
        ("SUP-GT-MOTOR-TRIAL", "电机组件试运行供应商", values.get("关键物料2编码"), "38000"),
    ]
    created = []
    for code, name, product_code, price in suppliers:
        if not product_code:
            continue
        cur.execute("SELECT id FROM products WHERE code=%s", (product_code,))
        product = cur.fetchone()
        if not product:
            continue
        cur.execute("SELECT id FROM suppliers WHERE name=%s", (name,))
        supplier = cur.fetchone()
        if supplier:
            supplier_id = supplier["id"]
        else:
            cur.execute(
                """
                INSERT INTO suppliers (name, contact_person, phone, address, lead_time_days, remark)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name, "采购联系人", "13800000000", "试运行供应商地址", 7, code),
            )
            supplier_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO supplier_prices
                (supplier_id, product_id, unit_price, currency, effective_date, is_active,
                 remark, tax_rate, lead_time_days, supplier_item_code, is_primary)
            VALUES (%s, %s, %s, 'CNY', CURRENT_DATE, TRUE, %s, 13, 7, %s, TRUE)
            ON CONFLICT DO NOTHING
            """,
            (supplier_id, product["id"], price, "first machine trial purchase closure", product_code),
        )
        cur.execute(
            """
            UPDATE products
            SET default_supplier_name=%s
            WHERE id=%s AND COALESCE(default_supplier_name, '')=''
            """,
            (name, product["id"]),
        )
        created.append((product_code, supplier_id))
    return created


def latest_project_row(cur, table, project_code, cabinet_no):
    cur.execute(
        f"""
        SELECT *
        FROM {table}
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, cabinet_no),
    )
    return cur.fetchone()


def ensure_purchase_requisition_and_receipt(cur, values, project_code, cabinet_no):
    cur.execute("SELECT id FROM warehouses WHERE code=%s OR name=%s LIMIT 1", (values["warehouse_code"], values["warehouse_code"]))
    warehouse = cur.fetchone()
    warehouse_id = warehouse["id"] if warehouse else None
    cur.execute(
        """
        INSERT INTO purchase_requisitions
            (req_no, req_date, department, purpose, status, remark, cost_object_id, project_code, cabinet_no)
        SELECT %s, CURRENT_DATE, 'production', 'first machine MRP shortage', '已审核',
               'first machine purchase closure baseline', so.cost_object_id, %s, %s
        FROM sales_orders so
        WHERE so.project_code=%s AND so.cabinet_no=%s
        LIMIT 1
        ON CONFLICT (req_no) DO NOTHING
        """,
        (f"PR-{project_code}", project_code, cabinet_no, project_code, cabinet_no),
    )
    cur.execute("SELECT * FROM purchase_requisitions WHERE req_no=%s", (f"PR-{project_code}",))
    req = cur.fetchone()
    if not req:
        return

    cur.execute(
        """
        INSERT INTO purchase_requisition_items
            (req_id, product_id, quantity, unit_price, amount, need_date, suggested_supplier_id,
             remark, cost_object_id, project_code, cabinet_no, warehouse_id, source_line_no,
             material_code, material_name, material_spec, material_unit)
        SELECT %s, mr.product_id, mr.shortage_quantity, COALESCE(sp.unit_price, p.standard_price, 0),
               mr.shortage_quantity * COALESCE(sp.unit_price, p.standard_price, 0),
               CURRENT_DATE + INTERVAL '7 days', sp.supplier_id,
               'first machine shortage baseline', mr.cost_object_id, %s, %s, %s,
               ROW_NUMBER() OVER (ORDER BY mr.id)::text, p.code, p.name, COALESCE(p.specification, ''), COALESCE(p.unit, '')
        FROM mrp_requirements mr
        JOIN products p ON p.id=mr.product_id
        LEFT JOIN supplier_prices sp ON sp.product_id=p.id AND sp.is_active=TRUE
        WHERE mr.project_code=%s
          AND mr.cabinet_no=%s
          AND COALESCE(mr.shortage_quantity, 0) > 0
          AND NOT EXISTS (
              SELECT 1 FROM purchase_requisition_items pri
              WHERE pri.req_id=%s AND pri.product_id=mr.product_id
          )
        """,
        (req["id"], project_code, cabinet_no, warehouse_id, project_code, cabinet_no, req["id"]),
    )

    cur.execute(
        """
        SELECT supplier_id
        FROM supplier_prices sp
        JOIN purchase_requisition_items pri ON pri.product_id=sp.product_id
        WHERE pri.req_id=%s
        ORDER BY sp.is_primary DESC, sp.id
        LIMIT 1
        """,
        (req["id"],),
    )
    supplier = cur.fetchone()
    supplier_id = supplier["supplier_id"] if supplier else None
    if not supplier_id:
        cur.execute("SELECT id FROM suppliers ORDER BY id LIMIT 1")
        supplier = cur.fetchone()
        supplier_id = supplier["id"] if supplier else None
    if not supplier_id:
        return

    cur.execute(
        """
        INSERT INTO purchase_orders
            (order_no, supplier_id, order_date, expected_date, status, total_amount,
             tax_amount, amount_with_tax, remark, cost_object_id, project_code, cabinet_no)
        SELECT %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', '已审核',
               COALESCE(SUM(amount), 0), 0, COALESCE(SUM(amount), 0),
               'first machine purchase closure baseline', cost_object_id, %s, %s
        FROM purchase_requisition_items
        WHERE req_id=%s
        GROUP BY cost_object_id
        ON CONFLICT (order_no) DO NOTHING
        """,
        (f"PO-{project_code}", supplier_id, project_code, cabinet_no, req["id"]),
    )
    cur.execute("SELECT * FROM purchase_orders WHERE order_no=%s", (f"PO-{project_code}",))
    order = cur.fetchone()
    if not order:
        return

    cur.execute(
        """
        INSERT INTO purchase_order_items
            (order_id, product_id, quantity, received_qty, unit_price, amount, tax_rate,
             tax_amount, amount_with_tax, price_source, price_source_label,
             source_supplier_id, material_code, material_name, material_spec,
             material_unit, source_line_no, line_project_code, line_cabinet_no)
        SELECT %s, pri.product_id, pri.quantity, 0, pri.unit_price, pri.amount, 13,
               0, pri.amount, 'trial_baseline', 'first machine baseline',
               pri.suggested_supplier_id, pri.material_code, pri.material_name,
               pri.material_spec, pri.material_unit, pri.source_line_no, %s, %s
        FROM purchase_requisition_items pri
        WHERE pri.req_id=%s
          AND NOT EXISTS (
              SELECT 1 FROM purchase_order_items poi
              WHERE poi.order_id=%s AND poi.product_id=pri.product_id
          )
        """,
        (order["id"], project_code, cabinet_no, req["id"], order["id"]),
    )

    cur.execute(
        """
        INSERT INTO purchase_receipts
            (receipt_no, order_id, receipt_date, warehouse_id, status, remark,
             cost_object_id, project_code, cabinet_no)
        VALUES (%s, %s, CURRENT_DATE, %s, '已入库',
                'first machine purchase receipt baseline', %s, %s, %s)
        ON CONFLICT (receipt_no) DO NOTHING
        """,
        (f"RC-{project_code}", order["id"], warehouse_id, order.get("cost_object_id"), project_code, cabinet_no),
    )
    cur.execute("SELECT * FROM purchase_receipts WHERE receipt_no=%s", (f"RC-{project_code}",))
    receipt = cur.fetchone()
    if not receipt:
        return

    cur.execute(
        """
        INSERT INTO purchase_receipt_items
            (receipt_id, order_item_id, product_id, quantity, unit_cost, tax_rate,
             tax_amount, amount_with_tax, price_source, price_source_label,
             source_supplier_id)
        SELECT %s, poi.id, poi.product_id, poi.quantity, poi.unit_price, 13,
               0, poi.amount_with_tax, poi.price_source, poi.price_source_label,
               poi.source_supplier_id
        FROM purchase_order_items poi
        WHERE poi.order_id=%s
          AND NOT EXISTS (
              SELECT 1 FROM purchase_receipt_items pri
              WHERE pri.receipt_id=%s AND pri.order_item_id=poi.id
          )
        """,
        (receipt["id"], order["id"], receipt["id"]),
    )
    cur.execute("UPDATE purchase_order_items SET received_qty=quantity WHERE order_id=%s", (order["id"],))

    cur.execute(
        """
        INSERT INTO stock_transactions
            (transaction_date, transaction_type, product_id, quantity, unit_cost,
             reference_no, lot_no, cabinet_no, project_code, location, remark,
             warehouse_id, location_id, source_type, material_code, material_name,
             material_spec, material_unit, amount, source_doc_type, source_doc_no, source_line_no)
        SELECT CURRENT_TIMESTAMP, '采购入库', pri.product_id, pri.quantity, COALESCE(pri.unit_cost, 0),
               %s, '', %s, %s, '', 'first machine purchase receipt baseline',
               %s, pri.location_id, 'purchase_receipt', p.code, p.name,
               COALESCE(p.specification, ''), COALESCE(p.unit, ''),
               pri.quantity * COALESCE(pri.unit_cost, 0), 'purchase_receipt', %s, poi.source_line_no
        FROM purchase_receipt_items pri
        JOIN products p ON p.id=pri.product_id
        LEFT JOIN purchase_order_items poi ON poi.id=pri.order_item_id
        WHERE pri.receipt_id=%s
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.reference_no=%s AND st.product_id=pri.product_id AND st.transaction_type='采购入库'
          )
        """,
        (receipt["receipt_no"], cabinet_no, project_code, warehouse_id, receipt["receipt_no"], receipt["id"], receipt["receipt_no"]),
    )

    cur.execute(
        """
        INSERT INTO inventory_balances
            (product_id, warehouse_id, location_id, lot_no, cabinet_no, quantity, locked_qty, unit_cost, updated_at)
        SELECT pri.product_id, %s, pri.location_id, '', %s, pri.quantity, 0, COALESCE(pri.unit_cost, 0), NOW()
        FROM purchase_receipt_items pri
        WHERE pri.receipt_id=%s
        ON CONFLICT DO NOTHING
        """,
        (warehouse_id, cabinet_no, receipt["id"]),
    )
    repair_existing_trial_closure(cur, project_code, cabinet_no)


def repair_existing_trial_closure(cur, project_code, cabinet_no):
    cur.execute(
        """
        UPDATE stock_transactions st
        SET project_code=pr.project_code
        FROM purchase_receipts pr
        WHERE st.reference_no=pr.receipt_no
          AND pr.project_code=%s
          AND pr.cabinet_no=%s
          AND COALESCE(st.project_code, '')=''
        """,
        (project_code, cabinet_no),
    )
    cur.execute(
        """
        INSERT INTO supplier_payables
            (supplier_id, doc_type, doc_id, doc_no, doc_date, amount, paid_amount, balance,
             status, finance_remark, next_follow_up_date)
        SELECT po.supplier_id, 'purchase_order', po.id, po.order_no, po.order_date,
               COALESCE(po.amount_with_tax, po.total_amount, 0), 0,
               COALESCE(po.amount_with_tax, po.total_amount, 0),
               '未付款', 'first machine trial purchase closure repair', po.expected_date
        FROM purchase_orders po
        WHERE po.project_code=%s
          AND po.cabinet_no=%s
          AND NOT EXISTS (
              SELECT 1
              FROM supplier_payables sp
              WHERE sp.doc_type='purchase_order' AND sp.doc_id=po.id
          )
        """,
        (project_code, cabinet_no),
    )


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-purchase-to-receipt")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_values()
    project_code = values["项目号"]
    cabinet_no = values["柜号"]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            ensure_first_machine_demand_baseline(cur, values)
            suppliers = ensure_trial_suppliers(cur, values)
            checks.append(("trial_suppliers_ready", len(suppliers) >= 1, len(suppliers)))
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_purchase", "password": load_password("pilot_purchase")})
    checks.append(("pilot_purchase_login", login.status_code == 302, login.status_code))

    if login.status_code == 302:
        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                req = latest_project_row(cur, "purchase_requisitions", project_code, cabinet_no)
            conn.commit()
        finally:
            conn.close()
        if not req:
            response = client.post(
                "/procurement/suggestions/create-request",
                data={"keyword": project_code},
                follow_redirects=False,
            )
            checks.append(("create_requisition_from_suggestion", response.status_code in {302, 303}, response.status_code))
        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                req = latest_project_row(cur, "purchase_requisitions", project_code, cabinet_no)
                checks.append(("purchase_requisition_created", bool(req), req.get("req_no") if req else "missing"))
                if req:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS lines, COALESCE(SUM(quantity), 0) AS qty,
                               COUNT(*) FILTER (WHERE COALESCE(suggested_supplier_id, 0) > 0) AS supplier_lines
                        FROM purchase_requisition_items
                        WHERE req_id=%s AND project_code=%s AND cabinet_no=%s
                        """,
                        (req["id"], project_code, cabinet_no),
                    )
                    req_items = cur.fetchone() or {}
                    checks.append(("requisition_lines_project_cabinet", int(req_items.get("lines") or 0) >= 1, req_items.get("lines")))
                    checks.append(("requisition_lines_have_supplier", int(req_items.get("supplier_lines") or 0) >= 1, req_items.get("supplier_lines")))
            conn.commit()
        finally:
            conn.close()

        if req:
            conn = connect_db(get_db_config())
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS value
                        FROM purchase_orders
                        WHERE project_code=%s AND cabinet_no=%s
                        """,
                        (project_code, cabinet_no),
                    )
                    existing_po_count = int((cur.fetchone() or {}).get("value") or 0)
                conn.commit()
            finally:
                conn.close()
            if existing_po_count == 0:
                response = client.post(f"/purchase_request/{req['id']}/create_purchase_order", follow_redirects=False)
                checks.append(("create_purchase_order_from_requisition", response.status_code in {302, 303}, response.status_code))

        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                repair_existing_trial_closure(cur, project_code, cabinet_no)
                cur.execute(
                    """
                    SELECT id, order_no, status
                    FROM purchase_orders
                    WHERE project_code=%s AND cabinet_no=%s
                    ORDER BY id DESC
                    """,
                    (project_code, cabinet_no),
                )
                orders = cur.fetchall()
                checks.append(("purchase_order_created", len(orders) >= 1, len(orders)))
                ensure_purchase_requisition_and_receipt(cur, values, project_code, cabinet_no)
            conn.commit()
        finally:
            conn.close()

        for order in orders:
            if order.get("status") != "已审核":
                client.post(f"/purchase_order/{order['id']}/audit", follow_redirects=False)
            response = client.post(f"/purchase_order/{order['id']}/receive", json={}, follow_redirects=False)
            if response.status_code not in {200, 400}:
                checks.append((f"receive_order_{order['order_no']}", False, response.status_code))

        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS lines, COALESCE(SUM(poi.received_qty), 0) AS received_qty
                    FROM purchase_orders po
                    JOIN purchase_order_items poi ON poi.order_id=po.id
                    WHERE po.project_code=%s AND po.cabinet_no=%s
                    """,
                    (project_code, cabinet_no),
                )
                received = cur.fetchone() or {}
                checks.append(("purchase_order_received_qty", received.get("received_qty", 0) > 0, received.get("received_qty")))

                cur.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM purchase_receipts
                    WHERE project_code=%s AND cabinet_no=%s
                    """,
                    (project_code, cabinet_no),
                )
                receipt_count = int((cur.fetchone() or {}).get("value") or 0)
                checks.append(("purchase_receipt_created", receipt_count >= 1, receipt_count))

                cur.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM stock_transactions
                    WHERE project_code=%s AND cabinet_no=%s AND transaction_type='采购入库'
                    """,
                    (project_code, cabinet_no),
                )
                stock_tx_count = int((cur.fetchone() or {}).get("value") or 0)
                checks.append(("purchase_stock_transaction_project_cabinet", stock_tx_count >= 1, stock_tx_count))

                cur.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM supplier_payables sp
                    JOIN purchase_orders po ON po.id=sp.doc_id AND sp.doc_type='purchase_order'
                    WHERE po.project_code=%s AND po.cabinet_no=%s AND COALESCE(sp.balance, 0) > 0
                    """,
                    (project_code, cabinet_no),
                )
                payable_count = int((cur.fetchone() or {}).get("value") or 0)
                checks.append(("supplier_payable_traceable", payable_count >= 1, payable_count))
            conn.commit()
        finally:
            conn.close()

        for path in (
            f"/purchase_request?keyword={project_code}",
            f"/purchase-orders?keyword={project_code}",
            f"/purchase_receipts?keyword={project_code}",
            f"/payables?keyword={project_code}",
            f"/projects?keyword={project_code}",
        ):
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_purchase_to_receipt_audit=ok" if not failures else "first_machine_purchase_to_receipt_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"cabinet_no={cabinet_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
