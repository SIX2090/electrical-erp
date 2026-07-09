from __future__ import annotations

import os
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from werkzeug.datastructures import MultiDict


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_HOST", "127.0.0.1")
os.environ.setdefault("PG_PORT", "5432")
os.environ.setdefault("PG_DATABASE", "wms")
os.environ.setdefault("PG_USER", "wms_user")
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "phase5-delivery-outsourcing-service-verification")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app  # noqa: E402
from routes.project_routes import _project_axis_events  # noqa: E402
from services.app_runtime import connect_db  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402


PREFIX = "VERIFY-P5-LOOP"


def db_config():
    return {
        "host": os.environ["PG_HOST"],
        "port": int(os.environ["PG_PORT"]),
        "database": os.environ["PG_DATABASE"],
        "user": os.environ["PG_USER"],
        "password": get_pg_password(),
    }


def dec(value) -> Decimal:
    return Decimal(str(value or 0))


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return next(iter(row.values()), None) if row else None


def one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def columns(cur, table):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def has_table(cur, table):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return bool(cur.fetchone())


def insert_dynamic(cur, table, values):
    cols = columns(cur, table)
    filtered = {key: value for key, value in values.items() if key in cols}
    names = list(filtered)
    placeholders = ",".join(["%s"] * len(names))
    cur.execute(
        f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders}) RETURNING id",
        [filtered[name] for name in names],
    )
    return cur.fetchone()["id"]


def delete_if_table(cur, table, where_sql, params=()):
    if has_table(cur, table):
        cur.execute(f"DELETE FROM {table} WHERE {where_sql}", params)


def seed_initial_inventory(cur, product_id, qty, unit_cost, warehouse_id, location_id, project_code, serial_no, suffix):
    amount = qty * unit_cost
    insert_dynamic(
        cur,
        "inventory_balances",
        {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "location_id": location_id,
            "quantity": qty,
            "unit_cost": unit_cost,
            "amount": amount,
            "lot_no": "",
            "project_code": project_code,
            "serial_no": serial_no,
            "status": "available",
        },
    )
    inventory_id = scalar(cur, "SELECT id FROM inventory WHERE product_id=%s ORDER BY id LIMIT 1", (product_id,))
    if inventory_id:
        cur.execute(
            """
            UPDATE inventory
            SET quantity=COALESCE(quantity,0)+%s,
                unit_cost=%s,
                location=%s
            WHERE id=%s
            """,
            (qty, unit_cost, "Phase5 verification opening stock", inventory_id),
        )
    else:
        insert_dynamic(
            cur,
            "inventory",
            {
                "product_id": product_id,
                "quantity": qty,
                "unit_cost": unit_cost,
                "location": "Phase5 verification opening stock",
                "reorder_level": Decimal("0"),
            },
        )
    insert_dynamic(
        cur,
        "batch_tracking",
        {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "location_id": location_id,
            "lot_no": "",
            "serial_no": serial_no,
            "project_code": project_code,
            "quantity_in": qty,
            "quantity_out": Decimal("0"),
            "quantity_available": qty,
            "unit_cost": unit_cost,
            "source_order_no": f"{PREFIX}-OPEN-{suffix}",
            "status": "available",
        },
    )
    insert_dynamic(
        cur,
        "stock_transactions",
        {
            "transaction_date": date.today(),
            "transaction_type": "opening_balance",
            "product_id": product_id,
            "quantity": qty,
            "unit_cost": unit_cost,
            "amount": amount,
            "warehouse_id": warehouse_id,
            "location_id": location_id,
            "lot_no": "",
            "serial_no": serial_no,
            "project_code": project_code,
            "reference_no": f"{PREFIX}-OPEN-{suffix}",
            "source_doc_no": f"{PREFIX}-OPEN-{suffix}",
            "source_type": "phase5_verifier",
            "remark": PREFIX,
        },
    )


def reconcile_fixture_batch_tracking(cur):
    cur.execute(
        """
        WITH desired AS (
            SELECT ib.product_id,
                   COALESCE(ib.warehouse_id, 0) AS warehouse_id,
                   COALESCE(ib.location_id, 0) AS location_id,
                   COALESCE(ib.lot_no, '') AS lot_no,
                   COALESCE(ib.serial_no, '') AS serial_no,
                   COALESCE(ib.project_code, '') AS project_code,
                   SUM(COALESCE(ib.quantity, 0)) AS quantity,
                   CASE WHEN COALESCE(SUM(ib.quantity),0) <> 0
                       THEN COALESCE(SUM(ib.quantity * COALESCE(ib.unit_cost,0)) / NULLIF(SUM(ib.quantity),0),0)
                       ELSE COALESCE(MAX(ib.unit_cost),0)
                   END AS unit_cost
            FROM inventory_balances ib
            JOIN products p ON p.id=ib.product_id
            WHERE p.code LIKE %s
            GROUP BY ib.product_id, COALESCE(ib.warehouse_id, 0), COALESCE(ib.location_id, 0),
                     COALESCE(ib.lot_no, ''), COALESCE(ib.serial_no, ''), COALESCE(ib.project_code, '')
        ),
        existing AS (
            SELECT DISTINCT ON (bt.product_id, COALESCE(bt.warehouse_id, 0), COALESCE(bt.location_id, 0),
                                COALESCE(bt.lot_no, ''), COALESCE(bt.serial_no, ''), COALESCE(bt.project_code, ''))
                   bt.id, bt.product_id,
                   COALESCE(bt.warehouse_id, 0) AS warehouse_id,
                   COALESCE(bt.location_id, 0) AS location_id,
                   COALESCE(bt.lot_no, '') AS lot_no,
                   COALESCE(bt.serial_no, '') AS serial_no,
                   COALESCE(bt.project_code, '') AS project_code
            FROM batch_tracking bt
            JOIN products p ON p.id=bt.product_id
            WHERE p.code LIKE %s
            ORDER BY bt.product_id, COALESCE(bt.warehouse_id, 0), COALESCE(bt.location_id, 0),
                     COALESCE(bt.lot_no, ''), COALESCE(bt.serial_no, ''), COALESCE(bt.project_code, ''), bt.id
        )
        UPDATE batch_tracking bt
        SET quantity_available=desired.quantity,
            quantity_in=GREATEST(desired.quantity, 0),
            quantity_out=0,
            unit_cost=desired.unit_cost,
            updated_at=CURRENT_TIMESTAMP
        FROM desired
        JOIN existing
          ON existing.product_id IS NOT DISTINCT FROM desired.product_id
         AND existing.warehouse_id=desired.warehouse_id
         AND existing.location_id=desired.location_id
         AND existing.lot_no=desired.lot_no
         AND existing.serial_no=desired.serial_no
         AND existing.project_code=desired.project_code
        WHERE bt.id=existing.id
        """,
        (f"{PREFIX}%", f"{PREFIX}%"),
    )
    cur.execute(
        """
        INSERT INTO batch_tracking
            (product_id, warehouse_id, location_id, lot_no, serial_no, project_code,
             quantity_in, quantity_out, quantity_available, unit_cost, source_order_no, status)
        SELECT desired.product_id,
               NULLIF(desired.warehouse_id, 0),
               NULLIF(desired.location_id, 0),
               desired.lot_no,
               desired.serial_no,
               desired.project_code,
               GREATEST(desired.quantity, 0),
               0,
               desired.quantity,
               desired.unit_cost,
               %s,
               'available'
        FROM (
            SELECT ib.product_id,
                   COALESCE(ib.warehouse_id, 0) AS warehouse_id,
                   COALESCE(ib.location_id, 0) AS location_id,
                   COALESCE(ib.lot_no, '') AS lot_no,
                   COALESCE(ib.serial_no, '') AS serial_no,
                   COALESCE(ib.project_code, '') AS project_code,
                   SUM(COALESCE(ib.quantity, 0)) AS quantity,
                   CASE WHEN COALESCE(SUM(ib.quantity),0) <> 0
                       THEN COALESCE(SUM(ib.quantity * COALESCE(ib.unit_cost,0)) / NULLIF(SUM(ib.quantity),0),0)
                       ELSE COALESCE(MAX(ib.unit_cost),0)
                   END AS unit_cost
            FROM inventory_balances ib
            JOIN products p ON p.id=ib.product_id
            WHERE p.code LIKE %s
            GROUP BY ib.product_id, COALESCE(ib.warehouse_id, 0), COALESCE(ib.location_id, 0),
                     COALESCE(ib.lot_no, ''), COALESCE(ib.serial_no, ''), COALESCE(ib.project_code, '')
        ) desired
        WHERE NOT EXISTS (
            SELECT 1
            FROM batch_tracking bt
            WHERE bt.product_id IS NOT DISTINCT FROM desired.product_id
              AND COALESCE(bt.warehouse_id, 0)=desired.warehouse_id
              AND COALESCE(bt.location_id, 0)=desired.location_id
              AND COALESCE(bt.lot_no, '')=desired.lot_no
              AND COALESCE(bt.serial_no, '')=desired.serial_no
              AND COALESCE(bt.project_code, '')=desired.project_code
        )
        """,
        (f"{PREFIX}-BATCH-RECON", f"{PREFIX}%"),
    )


def cleanup(cur):
    like = f"{PREFIX}%"
    delete_if_table(cur, "machine_service_rmas", "project_code LIKE %s OR serial_no LIKE %s OR rma_no LIKE %s", (like, like, like))
    delete_if_table(cur, "machine_service_order_items", "order_id IN (SELECT id FROM machine_service_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "machine_service_order_checklists", "order_id IN (SELECT id FROM machine_service_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "machine_service_orders", "project_code LIKE %s OR serial_no LIKE %s OR order_no LIKE %s", (like, like, like))
    delete_if_table(cur, "machine_service_acceptance_checks", "project_code LIKE %s OR serial_no LIKE %s", (like, like))
    delete_if_table(cur, "machine_service_cards", "project_code LIKE %s OR serial_no LIKE %s", (like, like))
    delete_if_table(cur, "supplier_payables", "project_code LIKE %s OR serial_no LIKE %s OR doc_no LIKE %s", (like, like, like))
    delete_if_table(
        cur,
        "supplier_payables",
        "supplier_id IN (SELECT id FROM suppliers WHERE name LIKE %s)",
        (f"{PREFIX} supplier%",),
    )
    delete_if_table(cur, "customer_receivables", "project_code LIKE %s OR serial_no LIKE %s OR source_no LIKE %s", (like, like, like))
    delete_if_table(cur, "subcontract_receive_lines", "project_code LIKE %s OR serial_no LIKE %s OR receive_id IN (SELECT id FROM subcontract_receive_orders WHERE subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s))", (like, like, like, like))
    delete_if_table(cur, "subcontract_receive_orders", "subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "subcontract_issue_lines", "project_code LIKE %s OR serial_no LIKE %s OR issue_id IN (SELECT id FROM subcontract_issue_orders WHERE subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s))", (like, like, like, like))
    delete_if_table(cur, "subcontract_issue_orders", "subcontract_order_id IN (SELECT id FROM subcontract_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "subcontract_orders", "project_code LIKE %s OR serial_no LIKE %s OR order_no LIKE %s", (like, like, like))
    delete_if_table(cur, "work_order_cost_lines", "work_order_id IN (SELECT id FROM work_orders WHERE project_code LIKE %s OR serial_no LIKE %s) OR source_no LIKE %s", (like, like, like))
    delete_if_table(cur, "work_order_costs", "work_order_id IN (SELECT id FROM work_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "stock_transactions", "reference_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (like, like, like))
    delete_if_table(cur, "sales_shipment_items", "shipment_id IN (SELECT id FROM sales_shipments WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "sales_shipments", "project_code LIKE %s OR serial_no LIKE %s OR shipment_no LIKE %s", (like, like, like))
    delete_if_table(cur, "sales_order_items", "order_id IN (SELECT id FROM sales_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "sales_orders", "project_code LIKE %s OR serial_no LIKE %s OR order_no LIKE %s", (like, like, like))
    delete_if_table(cur, "wo_material_items", "wo_id IN (SELECT id FROM work_orders WHERE project_code LIKE %s OR serial_no LIKE %s)", (like, like))
    delete_if_table(cur, "work_orders", "project_code LIKE %s OR serial_no LIKE %s OR wo_no LIKE %s", (like, like, like))
    delete_if_table(cur, "machine_serial_masters", "project_code LIKE %s OR serial_no LIKE %s", (like, like))
    delete_if_table(cur, "project_masters", "project_code LIKE %s OR source_order_no LIKE %s", (like, like))
    delete_if_table(cur, "inventory_balances", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (like,))
    delete_if_table(cur, "inventory", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (like,))
    delete_if_table(cur, "batch_tracking", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (like,))
    delete_if_table(cur, "products", "code LIKE %s", (like,))
    delete_if_table(cur, "customers", "name LIKE %s", (f"{PREFIX} customer%",))
    delete_if_table(cur, "suppliers", "name LIKE %s", (f"{PREFIX} supplier%",))


def ensure_warehouse(cur):
    warehouse_id = scalar(cur, "SELECT id FROM warehouses ORDER BY id LIMIT 1")
    if not warehouse_id:
        warehouse_id = insert_dynamic(cur, "warehouses", {"code": f"{PREFIX}-WH", "name": "Phase5 verification warehouse", "status": "enabled"})
    location_id = None
    if has_table(cur, "locations"):
        location_id = scalar(cur, "SELECT id FROM locations WHERE warehouse_id=%s ORDER BY id LIMIT 1", (warehouse_id,))
        if not location_id:
            location_id = insert_dynamic(cur, "locations", {"warehouse_id": warehouse_id, "code": f"{PREFIX}-LOC", "name": "Phase5 verification location", "is_active": True})
    return warehouse_id, location_id


def prepare_fixture():
    suffix = str(int(time.time() * 1000))
    project_code = f"{PREFIX}-PRJ-{suffix}"
    serial_no = f"{PREFIX}-SN-{suffix}"
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cleanup(cur)
            warehouse_id, location_id = ensure_warehouse(cur)
            customer_id = insert_dynamic(
                cur,
                "customers",
                {
                    "code": f"{PREFIX}-CUST-{suffix}",
                    "name": f"{PREFIX} customer {suffix}",
                    "status": "enabled",
                    "address": "Phase5 verification install address",
                },
            )
            supplier_id = insert_dynamic(
                cur,
                "suppliers",
                {
                    "code": f"{PREFIX}-SUP-{suffix}",
                    "name": f"{PREFIX} supplier {suffix}",
                    "status": "enabled",
                },
            )
            fg_id = insert_dynamic(
                cur,
                "products",
                {
                    "code": f"{PREFIX}-FG-{suffix}",
                    "name": "Phase5 delivery finished good",
                    "category": "finished_good",
                    "specification": "P5-FG",
                    "unit": "set",
                    "standard_price": Decimal("800"),
                    "unit_cost": Decimal("500"),
                    "status": "enabled",
                },
            )
            subcontract_product_id = insert_dynamic(
                cur,
                "products",
                {
                    "code": f"{PREFIX}-SUB-{suffix}",
                    "name": "Phase5 outsourced spindle part",
                    "category": "semi_finished",
                    "specification": "P5-SUB",
                    "unit": "pcs",
                    "standard_price": Decimal("120"),
                    "unit_cost": Decimal("90"),
                    "status": "enabled",
                },
            )
            spare_id = insert_dynamic(
                cur,
                "products",
                {
                    "code": f"{PREFIX}-SPARE-{suffix}",
                    "name": "Phase5 service spare",
                    "category": "spare_part",
                    "specification": "P5-SP",
                    "unit": "pcs",
                    "standard_price": Decimal("40"),
                    "unit_cost": Decimal("25"),
                    "status": "enabled",
                },
            )
            project_id = insert_dynamic(
                cur,
                "project_masters",
                {
                    "project_code": project_code,
                    "project_name": f"{PREFIX} project {suffix}",
                    "customer_id": customer_id,
                    "product_family": "Phase5 verification",
                    "machine_model": "P5-FG",
                    "source_order_no": f"{PREFIX}-SO-{suffix}",
                    "owner_name": "Phase5 verifier",
                    "planned_delivery_date": date.today(),
                    "status": "enabled",
                    "remark": PREFIX,
                },
            )
            insert_dynamic(
                cur,
                "machine_serial_masters",
                {
                    "serial_no": serial_no,
                    "project_id": project_id,
                    "project_code": project_code,
                    "customer_id": customer_id,
                    "product_id": fg_id,
                    "product_family": "Phase5 verification",
                    "machine_model": "P5-FG",
                    "production_stage": "verification",
                    "service_status": "pending",
                    "status": "enabled",
                    "remark": PREFIX,
                },
            )
            work_order_id = insert_dynamic(
                cur,
                "work_orders",
                {
                    "wo_no": f"{PREFIX}-WO-{suffix}",
                    "wo_date": date.today(),
                    "product_id": fg_id,
                    "quantity": Decimal("1"),
                    "status": "in_progress",
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "project_code": project_code,
                    "serial_no": serial_no,
                    "planned_start_date": date.today(),
                    "planned_end_date": date.today(),
                    "remark": PREFIX,
                },
            )
            for product_id, qty in ((fg_id, Decimal("3")), (subcontract_product_id, Decimal("10")), (spare_id, Decimal("5"))):
                seed_initial_inventory(
                    cur,
                    product_id,
                    qty,
                    Decimal("100"),
                    warehouse_id,
                    location_id,
                    project_code,
                    serial_no,
                    suffix,
                )
            seed_initial_inventory(
                cur,
                fg_id,
                Decimal("3"),
                Decimal("100"),
                warehouse_id,
                None,
                project_code,
                serial_no,
                suffix,
            )
            seed_initial_inventory(
                cur,
                subcontract_product_id,
                Decimal("10"),
                Decimal("100"),
                warehouse_id,
                None,
                project_code,
                serial_no,
                suffix,
            )
            conn.commit()
    finally:
        conn.close()
    return {
        "customer_id": customer_id,
        "supplier_id": supplier_id,
        "fg_id": fg_id,
        "subcontract_product_id": subcontract_product_id,
        "spare_id": spare_id,
        "work_order_id": work_order_id,
        "warehouse_id": warehouse_id,
        "location_id": location_id,
        "project_code": project_code,
        "serial_no": serial_no,
    }


def login_admin(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["role"] = "admin"
        session["username"] = "admin"


def add_check(checks, name, ok, detail=""):
    checks.append((name, bool(ok), "" if detail is None else str(detail)))


def latest_id(sql, params=()):
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            return scalar(cur, sql, params)
    finally:
        conn.close()


def run_sales_delivery_loop(client, fixture):
    response = client.post(
        "/sales/new",
        data=MultiDict([
            ("customer_id", str(fixture["customer_id"])),
            ("order_date", date.today().isoformat()),
            ("delivery_date", date.today().isoformat()),
            ("warehouse_id", str(fixture["warehouse_id"])),
            ("project_code", fixture["project_code"]),
            ("serial_no", fixture["serial_no"]),
            ("remark", "phase5 sales_delivery_loop"),
            ("status", "pending"),
            ("product_id[]", str(fixture["fg_id"])),
            ("quantity[]", "1"),
            ("unit_price[]", "800"),
            ("tax_rate[]", "13"),
            ("lot_no[]", ""),
            ("source_line_no[]", ""),
        ]),
        follow_redirects=True,
    )
    order_id = latest_id(
        "SELECT id FROM sales_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
        (fixture["project_code"], fixture["serial_no"]),
    )
    submit = client.post(f"/sales/{order_id}/submit", follow_redirects=True)
    audit = client.post(f"/sales/{order_id}/audit", follow_redirects=True)
    ship = client.post(
        "/shipments/new",
        data={
            "sales_order_id": str(order_id),
            "shipment_date": date.today().isoformat(),
            "warehouse_id": str(fixture["warehouse_id"]),
            "remark": "phase5 sales_delivery_loop shipment",
        },
        follow_redirects=True,
    )
    shipment_id = latest_id(
        "SELECT id FROM sales_shipments WHERE order_id=%s ORDER BY id DESC LIMIT 1",
        (order_id,),
    )
    service_card_id = latest_id(
        "SELECT id FROM machine_service_cards WHERE sales_order_id=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
        (order_id, fixture["serial_no"]),
    )
    return {
        "create_response": response,
        "submit_response": submit,
        "audit_response": audit,
        "ship_response": ship,
        "sales_order_id": order_id,
        "shipment_id": shipment_id,
        "service_card_id": service_card_id,
    }


def run_outsourcing_loop(client, fixture):
    create_order = client.post(
        "/subcontract/new",
        data={
            "supplier_id": str(fixture["supplier_id"]),
            "order_date": date.today().isoformat(),
            "required_date": date.today().isoformat(),
            "project_code": fixture["project_code"],
            "serial_no": fixture["serial_no"],
            "remark": "phase5 outsourcing_loop",
            "product_id[]": [str(fixture["subcontract_product_id"])],
            "quantity[]": ["2"],
            "unit_price[]": ["120"],
            "process_name[]": ["outsourced machining"],
            "warehouse[]": [str(fixture["warehouse_id"])],
            "location[]": [str(fixture["location_id"] or "")],
            "lot_no[]": [""],
            "line_project_code[]": [fixture["project_code"]],
            "line_serial_no[]": [fixture["serial_no"]],
        },
        follow_redirects=True,
    )
    subcontract_order_id = latest_id(
        "SELECT id FROM subcontract_orders WHERE project_code=%s AND serial_no=%s ORDER BY id DESC LIMIT 1",
        (fixture["project_code"], fixture["serial_no"]),
    )
    issue = client.post(
        "/subcontract_issue/new",
        data={
            "subcontract_order_id": str(subcontract_order_id),
            "date": date.today().isoformat(),
            "quantity": "2",
            "warehouse_id": str(fixture["warehouse_id"]),
            "location_id": str(fixture["location_id"] or ""),
            "lot_no": "",
            "remark": "phase5 outsourcing_loop issue",
        },
        follow_redirects=True,
    )
    issue_id = latest_id(
        "SELECT id FROM subcontract_issue_orders WHERE subcontract_order_id=%s ORDER BY id DESC LIMIT 1",
        (subcontract_order_id,),
    )
    issue_submit = client.post(f"/subcontract_issue/{issue_id}/submit", follow_redirects=True)
    issue_audit = client.post(f"/subcontract_issue/{issue_id}/audit", follow_redirects=True)
    receive = client.post(
        "/subcontract_receive/new",
        data={
            "subcontract_order_id": str(subcontract_order_id),
            "date": date.today().isoformat(),
            "quantity": "2",
            "scrap_quantity": "0",
            "warehouse_id": str(fixture["warehouse_id"]),
            "location_id": str(fixture["location_id"] or ""),
            "lot_no": "",
            "remark": "phase5 outsourcing_loop receive",
        },
        follow_redirects=True,
    )
    receive_id = latest_id(
        "SELECT id FROM subcontract_receive_orders WHERE subcontract_order_id=%s ORDER BY id DESC LIMIT 1",
        (subcontract_order_id,),
    )
    receive_submit = client.post(f"/subcontract_receive/{receive_id}/submit", follow_redirects=True)
    receive_audit = client.post(f"/subcontract_receive/{receive_id}/audit", follow_redirects=True)
    return {
        "create_order_response": create_order,
        "issue_response": issue,
        "issue_submit_response": issue_submit,
        "issue_audit_response": issue_audit,
        "receive_response": receive,
        "receive_submit_response": receive_submit,
        "receive_audit_response": receive_audit,
        "subcontract_order_id": subcontract_order_id,
        "issue_id": issue_id,
        "receive_id": receive_id,
    }


def run_service_loop(client, fixture, service_card_id):
    acceptance = client.post(
        "/service-acceptance/new",
        data={
            "service_card_id": str(service_card_id),
            "check_date": date.today().isoformat(),
            "checklist_type": "安装验收",
            "item_name": "phase5 installation acceptance",
            "result": "通过",
            "project_code": fixture["project_code"],
            "serial_no": fixture["serial_no"],
            "remark": "phase5 service_loop acceptance",
        },
        follow_redirects=True,
    )
    acceptance_id = latest_id(
        "SELECT id FROM machine_service_acceptance_checks WHERE service_card_id=%s ORDER BY id DESC LIMIT 1",
        (service_card_id,),
    )
    service_order = client.post(
        "/service-orders/new",
        data={
            "service_card_id": str(service_card_id),
            "service_date": date.today().isoformat(),
            "service_type": "售后服务",
            "issue_summary": "phase5 service_loop issue",
            "billing_type": "保内",
            "fault_category": "verification",
            "warehouse_id": str(fixture["warehouse_id"]),
            "location_id": str(fixture["location_id"] or ""),
            "project_code": fixture["project_code"],
            "serial_no": fixture["serial_no"],
            "remark": "phase5 service_loop order",
        },
        follow_redirects=True,
    )
    service_order_id = latest_id(
        "SELECT id FROM machine_service_orders WHERE service_card_id=%s ORDER BY id DESC LIMIT 1",
        (service_card_id,),
    )
    handle = client.post(
        f"/service-orders/{service_order_id}/handle",
        data={
            "check_item": "phase5 service check",
            "result": "已完成",
            "solution": "verified service workflow",
            "fault_cause": "verification",
            "labor_cost": "10",
            "travel_cost": "5",
            "parts_cost": "0",
            "execution_note": "phase5 service_loop handled",
        },
        follow_redirects=True,
    )
    rma = client.post(
        "/service-rmas/new",
        data={
            "order_id": str(service_order_id),
            "rma_date": date.today().isoformat(),
            "warranty_scope": "保内",
            "responsibility_type": "待判定",
            "return_factory_required": "on",
            "fault_summary": "phase5 service_loop RMA",
            "diagnosis": "pending verification diagnosis",
            "product_id": str(fixture["spare_id"]),
            "quantity": "1",
            "unit_cost": "25",
            "warehouse_id": str(fixture["warehouse_id"]),
            "location_id": str(fixture["location_id"] or ""),
            "project_code": fixture["project_code"],
            "serial_no": fixture["serial_no"],
            "remark": "phase5 service_loop rma",
        },
        follow_redirects=True,
    )
    rma_id = latest_id(
        "SELECT id FROM machine_service_rmas WHERE order_id=%s ORDER BY id DESC LIMIT 1",
        (service_order_id,),
    )
    diagnose = client.post(
        f"/service-rmas/{rma_id}/diagnose",
        data={
            "diagnosis": "phase5 diagnosis complete",
            "responsibility_type": "保内",
            "warranty_scope": "保内",
            "fault_summary": "phase5 service_loop RMA",
        },
        follow_redirects=True,
    )
    claim = client.post(
        f"/service-rmas/{rma_id}/claim",
        data={
            "internal_claim_amount": "0",
            "supplier_claim_amount": "30",
            "claim_status": "索赔中",
            "claim_note": "phase5 claim",
        },
        follow_redirects=True,
    )
    recover = client.post(
        f"/service-rmas/{rma_id}/recover",
        data={
            "supplier_recovered_amount": "30",
            "claim_note": "phase5 recovered",
        },
        follow_redirects=True,
    )
    close = client.post(
        f"/service-rmas/{rma_id}/close",
        data={"remark": "phase5 closed"},
        follow_redirects=True,
    )
    return {
        "acceptance_response": acceptance,
        "service_order_response": service_order,
        "handle_response": handle,
        "rma_response": rma,
        "diagnose_response": diagnose,
        "claim_response": claim,
        "recover_response": recover,
        "close_response": close,
        "acceptance_id": acceptance_id,
        "service_order_id": service_order_id,
        "rma_id": rma_id,
    }


def project_event_types(sales_order_id):
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            order = one(cur, "SELECT * FROM sales_orders WHERE id=%s", (sales_order_id,))

            def query_rows(sql, params=()):
                with conn.cursor() as inner:
                    inner.execute(sql, params)
                    return inner.fetchall()

            events = _project_axis_events(query_rows, order, limit=200)
            return {event.get("event_type") for event in events}, events
    finally:
        conn.close()


def main() -> int:
    checks = []
    fixture = prepare_fixture()
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})

    with app.test_client() as client:
        login_admin(client)
        sales = run_sales_delivery_loop(client, fixture)
        outsourcing = run_outsourcing_loop(client, fixture)
        service = run_service_loop(client, fixture, sales["service_card_id"])

    for name, response in (
        ("sales_create_page_ok", sales["create_response"]),
        ("sales_submit_page_ok", sales["submit_response"]),
        ("sales_audit_page_ok", sales["audit_response"]),
        ("sales_ship_page_ok", sales["ship_response"]),
        ("subcontract_create_page_ok", outsourcing["create_order_response"]),
        ("subcontract_issue_page_ok", outsourcing["issue_response"]),
        ("subcontract_issue_submit_ok", outsourcing["issue_submit_response"]),
        ("subcontract_issue_audit_ok", outsourcing["issue_audit_response"]),
        ("subcontract_receive_page_ok", outsourcing["receive_response"]),
        ("subcontract_receive_submit_ok", outsourcing["receive_submit_response"]),
        ("subcontract_receive_audit_ok", outsourcing["receive_audit_response"]),
        ("service_acceptance_page_ok", service["acceptance_response"]),
        ("service_order_page_ok", service["service_order_response"]),
        ("service_order_handle_ok", service["handle_response"]),
        ("service_rma_page_ok", service["rma_response"]),
        ("service_rma_diagnose_ok", service["diagnose_response"]),
        ("service_rma_claim_ok", service["claim_response"]),
        ("service_rma_recover_ok", service["recover_response"]),
        ("service_rma_close_ok", service["close_response"]),
    ):
        add_check(checks, name, response.status_code == 200, response.status_code)

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            reconcile_fixture_batch_tracking(cur)
            conn.commit()
            shipment_count = scalar(cur, "SELECT COUNT(*) FROM sales_shipments WHERE order_id=%s", (sales["sales_order_id"],))
            shipment_lines = scalar(cur, "SELECT COUNT(*) FROM sales_shipment_items WHERE shipment_id=%s", (sales["shipment_id"],))
            receivable_count = scalar(cur, "SELECT COUNT(*) FROM customer_receivables WHERE source_type='sales_order' AND source_id=%s AND project_code=%s AND serial_no=%s", (sales["sales_order_id"], fixture["project_code"], fixture["serial_no"]))
            sales_stock = scalar(cur, "SELECT COUNT(*) FROM stock_transactions WHERE reference_no IN (SELECT shipment_no FROM sales_shipments WHERE id=%s) AND project_code=%s AND serial_no=%s", (sales["shipment_id"], fixture["project_code"], fixture["serial_no"]))
            service_card_count = scalar(cur, "SELECT COUNT(*) FROM machine_service_cards WHERE id=%s AND project_code=%s AND serial_no=%s", (sales["service_card_id"], fixture["project_code"], fixture["serial_no"]))

            issue_stock = scalar(cur, "SELECT COUNT(*) FROM stock_transactions WHERE transaction_type='subcontract_issue' AND serial_no=%s", (fixture["serial_no"],))
            receive_stock = scalar(cur, "SELECT COUNT(*) FROM stock_transactions WHERE transaction_type='subcontract_receive' AND serial_no=%s", (fixture["serial_no"],))
            payable_count = scalar(cur, "SELECT COUNT(*) FROM supplier_payables WHERE doc_type='subcontract_receive' AND doc_id=%s AND project_code=%s AND serial_no=%s", (outsourcing["receive_id"], fixture["project_code"], fixture["serial_no"]))
            cost = one(cur, "SELECT subcontract_cost, total_cost FROM work_order_costs WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (fixture["work_order_id"],)) or {}
            cost_lines = scalar(cur, "SELECT COUNT(*) FROM work_order_cost_lines WHERE work_order_id=%s AND source_type=%s", (fixture["work_order_id"], "委外成本"))

            acceptance_count = scalar(cur, "SELECT COUNT(*) FROM machine_service_acceptance_checks WHERE id=%s AND project_code=%s AND serial_no=%s", (service["acceptance_id"], fixture["project_code"], fixture["serial_no"]))
            service_order_count = scalar(cur, "SELECT COUNT(*) FROM machine_service_orders WHERE id=%s AND service_card_id=%s AND project_code=%s AND serial_no=%s", (service["service_order_id"], sales["service_card_id"], fixture["project_code"], fixture["serial_no"]))
            rma_count = scalar(cur, "SELECT COUNT(*) FROM machine_service_rmas WHERE id=%s AND order_id=%s AND project_code=%s AND serial_no=%s", (service["rma_id"], service["service_order_id"], fixture["project_code"], fixture["serial_no"]))

            event_types, events = project_event_types(sales["sales_order_id"])

            add_check(checks, "sales_delivery_loop_shipment_created", shipment_count >= 1 and shipment_lines >= 1, f"shipments={shipment_count}, lines={shipment_lines}")
            add_check(checks, "sales_delivery_loop_receivable_trace", receivable_count >= 1, receivable_count)
            add_check(checks, "sales_delivery_loop_stock_posted", sales_stock >= 1, sales_stock)
            add_check(checks, "sales_delivery_loop_service_card_created", service_card_count >= 1, service_card_count)
            add_check(checks, "outsourcing_loop_issue_stock_posted", issue_stock >= 1, issue_stock)
            add_check(checks, "outsourcing_loop_receive_stock_posted", receive_stock >= 1, receive_stock)
            add_check(checks, "outsourcing_loop_payable_created", payable_count >= 1, payable_count)
            add_check(checks, "outsourcing_loop_work_order_cost", dec(cost.get("subcontract_cost")) > 0 and cost_lines >= 1, f"subcontract_cost={cost.get('subcontract_cost')}, lines={cost_lines}")
            add_check(checks, "service_loop_acceptance_created", acceptance_count >= 1, acceptance_count)
            add_check(checks, "service_loop_order_created", service_order_count >= 1, service_order_count)
            add_check(checks, "service_loop_rma_created", rma_count >= 1, rma_count)
            expected_events = {
                "sales_shipment",
                "customer_receivable",
                "subcontract_issue",
                "subcontract_receive",
                "supplier_payable",
                "work_order_cost",
                "service_card",
                "service_acceptance",
                "service_order",
                "service_rma",
            }
            missing = sorted(expected_events - event_types)
            add_check(checks, "project_machine_ledger_phase5_events", not missing, f"missing={missing}, events={len(events)}")
    finally:
        conn.close()

    failed = False
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: {detail}")
        failed = failed or not ok
    if not failed:
        print(
            "phase5_delivery_outsourcing_service_loops=ok "
            f"sales_order_id={sales['sales_order_id']} "
            f"subcontract_order_id={outsourcing['subcontract_order_id']} "
            f"service_order_id={service['service_order_id']} "
            f"rma_id={service['rma_id']}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
