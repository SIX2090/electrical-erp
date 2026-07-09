from __future__ import annotations

import os
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_HOST", "127.0.0.1")
os.environ.setdefault("PG_PORT", "5432")
os.environ.setdefault("PG_DATABASE", "wms")
os.environ.setdefault("PG_USER", "wms_user")
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "phase4-production-loop-verification")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app  # noqa: E402
from services.app_runtime import connect_db  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402


PREFIX = "VERIFY-P4-PROD"


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
            "lot_no": "",
            "serial_no": serial_no,
            "project_code": project_code,
            "quantity": qty,
            "locked_qty": Decimal("0"),
            "unit_cost": unit_cost,
            "amount": amount,
        },
    )
    insert_dynamic(
        cur,
        "inventory",
        {
            "product_id": product_id,
            "quantity": qty,
            "unit_cost": unit_cost,
            "location": "Phase4 verification opening stock",
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
            "source_type": "phase4_verifier",
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
    delete_if_table(cur, "stock_transactions", "reference_no LIKE %s OR source_doc_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "work_order_cost_lines", "work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s) OR source_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "work_order_costs", "work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "wo_complete_items", "wo_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s) OR source_doc_no LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "production_completion_orders", "completion_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "pick_list_items", "pick_list_id IN (SELECT id FROM pick_lists WHERE doc_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s)", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "pick_lists", "doc_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "quality_inspection_records", "inspection_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "wo_material_items", "wo_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "work_order_processes", "work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "mrp_requirements", "work_order_id IN (SELECT id FROM work_orders WHERE wo_no LIKE %s) OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "work_orders", "wo_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "sales_order_items", "order_id IN (SELECT id FROM sales_orders WHERE order_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s)", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "sales_orders", "order_no LIKE %s OR project_code LIKE %s OR serial_no LIKE %s", (f"{PREFIX}%", f"{PREFIX}%", f"{PREFIX}%"))
    delete_if_table(cur, "inventory_balances", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "inventory", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "batch_tracking", "product_id IN (SELECT id FROM products WHERE code LIKE %s)", (f"{PREFIX}%",))
    delete_if_table(cur, "products", "code LIKE %s", (f"{PREFIX}%",))


def ensure_warehouse(cur):
    warehouse_id = scalar(cur, "SELECT id FROM warehouses ORDER BY id LIMIT 1")
    if not warehouse_id:
        warehouse_id = insert_dynamic(cur, "warehouses", {"code": f"{PREFIX}-WH", "name": "Phase4 verification warehouse", "status": "enabled"})
    location_id = None
    if has_table(cur, "locations"):
        location_id = scalar(cur, "SELECT id FROM locations WHERE warehouse_id=%s ORDER BY id LIMIT 1", (warehouse_id,))
        if not location_id:
            location_id = insert_dynamic(cur, "locations", {"warehouse_id": warehouse_id, "code": f"{PREFIX}-LOC", "name": "Phase4 verification location", "is_active": True})
    return warehouse_id, location_id


def ensure_customer(cur):
    if not has_table(cur, "customers"):
        return None
    customer_id = scalar(cur, "SELECT id FROM customers WHERE name=%s ORDER BY id LIMIT 1", ("Phase4 production loop customer",))
    if customer_id:
        return customer_id
    return insert_dynamic(
        cur,
        "customers",
        {
            "code": f"{PREFIX}-CUST",
            "name": "Phase4 production loop customer",
            "status": "enabled",
        },
    )


def prepare_fixture():
    suffix = str(int(time.time() * 1000))
    project_code = f"{PREFIX}-PRJ-{suffix}"
    serial_no = f"{PREFIX}-SN-{suffix}"
    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            cleanup(cur)
            warehouse_id, location_id = ensure_warehouse(cur)
            customer_id = ensure_customer(cur)
            fg_id = insert_dynamic(
                cur,
                "products",
                {
                    "code": f"{PREFIX}-FG-{suffix}",
                    "name": "Phase4 production loop finished good",
                    "category": "finished_good",
                    "specification": "P4-FG",
                    "unit": "set",
                    "standard_price": Decimal("120"),
                    "unit_cost": Decimal("120"),
                    "status": "enabled",
                },
            )
            material_id = insert_dynamic(
                cur,
                "products",
                {
                    "code": f"{PREFIX}-MAT-{suffix}",
                    "name": "Phase4 production loop material",
                    "category": "raw_material",
                    "specification": "P4-MAT",
                    "unit": "pcs",
                    "standard_price": Decimal("10"),
                    "unit_cost": Decimal("10"),
                    "status": "enabled",
                },
            )
            sales_order_id = insert_dynamic(
                cur,
                "sales_orders",
                {
                    "order_no": f"{PREFIX}-SO-{suffix}",
                    "order_date": date.today(),
                    "customer_id": customer_id,
                    "status": "submitted",
                    "total_amount": Decimal("500"),
                    "shipped_amount": Decimal("0"),
                    "project_code": project_code,
                    "serial_no": serial_no,
                    "warehouse_id": warehouse_id,
                    "remark": PREFIX,
                },
            )
            insert_dynamic(
                cur,
                "sales_order_items",
                {
                    "order_id": sales_order_id,
                    "product_id": fg_id,
                    "quantity": Decimal("1"),
                    "shipped_qty": Decimal("0"),
                    "unit_price": Decimal("500"),
                    "amount": Decimal("500"),
                    "line_project_code": project_code,
                    "line_serial_no": serial_no,
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
            material_item_id = insert_dynamic(
                cur,
                "wo_material_items",
                {
                    "wo_id": work_order_id,
                    "product_id": material_id,
                    "required_qty": Decimal("2"),
                    "issued_qty": Decimal("0"),
                    "returned_qty": Decimal("0"),
                    "unit_cost": Decimal("10"),
                    "amount": Decimal("20"),
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "material_code": f"{PREFIX}-MAT-{suffix}",
                    "material_name": "Phase4 production loop material",
                    "material_spec": "P4-MAT",
                    "material_unit": "pcs",
                    "source_line_no": "P4-MAT-L1",
                    "line_project_code": project_code,
                    "line_serial_no": serial_no,
                },
            )
            seed_initial_inventory(
                cur,
                material_id,
                Decimal("10"),
                Decimal("10"),
                warehouse_id,
                location_id,
                project_code,
                serial_no,
                suffix,
            )
            insert_dynamic(
                cur,
                "quality_inspection_records",
                {
                    "inspection_no": f"{PREFIX}-QI-{suffix}",
                    "product_id": fg_id,
                    "inspection_type": "final",
                    "inspection_date": date.today(),
                    "sample_size": Decimal("1"),
                    "passed_quantity": Decimal("1"),
                    "failed_quantity": Decimal("0"),
                    "inspection_result": "pass",
                    "status": "completed",
                    "source_document_type": "work_order",
                    "source_document_id": work_order_id,
                    "project_code": project_code,
                    "serial_no": serial_no,
                    "conclusion": "phase4 verification release",
                },
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "sales_order_id": sales_order_id,
        "work_order_id": work_order_id,
        "material_item_id": material_item_id,
        "material_id": material_id,
        "fg_id": fg_id,
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


def post_pick(client, path, fixture, quantity):
    return client.post(
        path,
        data={
            "work_order_id": str(fixture["work_order_id"]),
            "doc_date": date.today().isoformat(),
            "warehouse_id": str(fixture["warehouse_id"]),
            "location_id": str(fixture["location_id"] or ""),
            "remark": "phase4 production loop verification",
            "item_id[]": [str(fixture["material_item_id"])],
            "quantity[]": [str(quantity)],
            "line_warehouse_id[]": [str(fixture["warehouse_id"])],
            "line_location_id[]": [str(fixture["location_id"] or "")],
            "lot_no[]": [""],
            "save_action": "post",
        },
        follow_redirects=True,
    )


def add_check(checks, name, ok, detail):
    checks.append((name, bool(ok), "" if detail is None else str(detail)))


def main() -> int:
    checks = []
    fixture = prepare_fixture()
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})

    with app.test_client() as client:
        login_admin(client)
        issue_response = post_pick(client, "/production-issues/new", fixture, Decimal("2"))
        return_response = post_pick(client, "/production-returns/new", fixture, Decimal("1"))
        supplement_response = post_pick(client, "/production-issues/new", fixture, Decimal("1"))
        completion_response = client.post(
            "/production-completions/new",
            data={
                "work_order_id": str(fixture["work_order_id"]),
                "completion_date": date.today().isoformat(),
                "quantity": "1",
                "failed_quantity": "0",
                "unit_cost": "120",
                "warehouse_id": str(fixture["warehouse_id"]),
                "location_id": str(fixture["location_id"] or ""),
                "lot_no": f"{PREFIX}-LOT",
                "serial_no": fixture["serial_no"],
                "remark": "phase4 production loop verification",
                "save_action": "post",
            },
            follow_redirects=True,
        )
        ledger_response = client.get(f"/api/project-machine-ledger/order/{fixture['sales_order_id']}/production-closure")

    add_check(checks, "issue_page_post_ok", issue_response.status_code == 200, issue_response.status_code)
    add_check(checks, "return_page_post_ok", return_response.status_code == 200, return_response.status_code)
    add_check(checks, "supplement_page_post_ok", supplement_response.status_code == 200, supplement_response.status_code)
    add_check(checks, "completion_page_post_ok", completion_response.status_code == 200, completion_response.status_code)
    add_check(checks, "production_closure_api_ok", ledger_response.status_code == 200, ledger_response.status_code)
    ledger_payload = ledger_response.get_json(silent=True) or {}

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            reconcile_fixture_batch_tracking(cur)
            conn.commit()
            material = one(cur, "SELECT required_qty, issued_qty, returned_qty FROM wo_material_items WHERE id=%s", (fixture["material_item_id"],)) or {}
            material_balance = scalar(
                cur,
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM inventory_balances
                WHERE product_id=%s AND warehouse_id=%s
            """,
                (fixture["material_id"], fixture["warehouse_id"]),
            )
            finished_balance = scalar(
                cur,
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM inventory_balances
                WHERE product_id=%s AND warehouse_id=%s
                  AND COALESCE(project_code, '')=%s AND COALESCE(serial_no, '')=%s
            """,
                (fixture["fg_id"], fixture["warehouse_id"], fixture["project_code"], fixture["serial_no"]),
            )
            completion_qty = scalar(cur, "SELECT COALESCE(SUM(qty), 0) FROM wo_complete_items WHERE wo_id=%s", (fixture["work_order_id"],))
            cost = one(cur, "SELECT * FROM work_order_costs WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (fixture["work_order_id"],)) or {}
            cost_lines = one(
                cur,
                """
                SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount
                FROM work_order_cost_lines
                WHERE work_order_id=%s
            """,
                (fixture["work_order_id"],),
            ) or {}
            event_counts = one(
                cur,
                """
                SELECT
                  COUNT(*) FILTER (WHERE st.transaction_type IN ('生产领料','工单领料')) AS issue_tx,
                  COUNT(*) FILTER (WHERE st.transaction_type IN ('生产退料','工单退料')) AS return_tx,
                  COUNT(*) FILTER (WHERE st.transaction_type='工单完工入库') AS completion_tx
                FROM stock_transactions st
                WHERE st.project_code=%s OR st.serial_no=%s
            """,
                (fixture["project_code"], fixture["serial_no"]),
            ) or {}
            issue_doc = one(cur, "SELECT status FROM pick_lists WHERE doc_type='production_issue' AND work_order_id=%s ORDER BY id DESC LIMIT 1", (fixture["work_order_id"],)) or {}
            return_doc = one(cur, "SELECT status FROM pick_lists WHERE doc_type='production_return' AND work_order_id=%s ORDER BY id DESC LIMIT 1", (fixture["work_order_id"],)) or {}
            completion_doc = one(cur, "SELECT status, posted_at FROM production_completion_orders WHERE work_order_id=%s ORDER BY id DESC LIMIT 1", (fixture["work_order_id"],)) or {}
    finally:
        conn.close()

    add_check(checks, "issue_doc_posted", bool(issue_doc), issue_doc.get("status"))
    add_check(checks, "return_doc_posted", bool(return_doc), return_doc.get("status"))
    add_check(checks, "completion_doc_posted", bool(completion_doc.get("posted_at")), completion_doc.get("status"))
    add_check(checks, "wo_material_issued_qty", dec(material.get("issued_qty")) == Decimal("3"), material.get("issued_qty"))
    add_check(checks, "wo_material_returned_qty", dec(material.get("returned_qty")) == Decimal("1"), material.get("returned_qty"))
    add_check(checks, "material_inventory_balance", dec(material_balance) == Decimal("8"), material_balance)
    add_check(checks, "completion_qty", dec(completion_qty) == Decimal("1"), completion_qty)
    add_check(checks, "finished_inventory_balance", dec(finished_balance) == Decimal("1"), finished_balance)
    add_check(checks, "work_order_cost_total", dec(cost.get("total_cost")) == Decimal("20.00"), cost.get("total_cost"))
    add_check(checks, "work_order_cost_lines", int(cost_lines.get("count") or 0) >= 3, cost_lines.get("count"))
    add_check(checks, "stock_issue_event", int(event_counts.get("issue_tx") or 0) >= 1, event_counts.get("issue_tx"))
    add_check(checks, "stock_return_event", int(event_counts.get("return_tx") or 0) >= 1, event_counts.get("return_tx"))
    add_check(checks, "stock_completion_event", int(event_counts.get("completion_tx") or 0) >= 1, event_counts.get("completion_tx"))
    ledger_counts = ledger_payload.get("counts") or {}
    add_check(checks, "ledger_found", ledger_payload.get("found") is True, ledger_payload.get("found"))
    add_check(checks, "ledger_status_closed_or_ready", ledger_payload.get("status") == "closed_or_ready", ledger_payload.get("status"))
    add_check(checks, "ledger_issue_docs", int(ledger_counts.get("issue_doc_count") or 0) >= 1, ledger_counts.get("issue_doc_count"))
    add_check(checks, "ledger_return_docs", int(ledger_counts.get("return_doc_count") or 0) >= 1, ledger_counts.get("return_doc_count"))
    add_check(checks, "ledger_completion_docs", int(ledger_counts.get("completion_doc_count") or 0) >= 1, ledger_counts.get("completion_doc_count"))
    add_check(checks, "ledger_cost_lines", int(ledger_counts.get("cost_line_count") or 0) >= 3, ledger_counts.get("cost_line_count"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("phase4_production_loop=ok" if not failures else "phase4_production_loop=failed")
    print(f"sales_order_id={fixture['sales_order_id']}")
    print(f"work_order_id={fixture['work_order_id']}")
    print(f"project_code={fixture['project_code']}")
    print(f"serial_no={fixture['serial_no']}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
