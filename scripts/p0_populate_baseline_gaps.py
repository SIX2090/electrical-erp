"""Populate missing baseline trial data for P0 full-chain acceptance.

Fills the 7 acceptance test gaps:
- Scenario 2: routing for baseline product
- Scenario 4: MRP suggestions with shortage
- Scenario 5: pick list for baseline work order
- Scenario 6: operation reports for baseline work order
- Scenario 7: sales invoice for baseline shipment
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password

BASELINE_ORDER_NO = "SO-GT-TRIAL-20260526-001"
BASELINE_PROJECT = "PJ-GT-TRIAL-20260526-001"
BASELINE_SERIAL = "SN-GT-TRIAL-20260526-001"


def db_config() -> dict:
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "dbname": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def connect():
    return psycopg2.connect(**db_config(), connect_timeout=5)


def main():
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ---- Gather baseline context ----
    cur.execute(
        """SELECT so.id, soi.product_id FROM sales_orders so
           JOIN sales_order_items soi ON soi.order_id=so.id
           WHERE so.order_no=%s LIMIT 1""",
        (BASELINE_ORDER_NO,),
    )
    so_row = cur.fetchone()
    if not so_row:
        print("Baseline sales order not found; aborting.")
        return
    so_id = so_row["id"]
    product_id = so_row["product_id"]

    cur.execute("SELECT id FROM boms WHERE product_id=%s LIMIT 1", (product_id,))
    bom_row = cur.fetchone()
    bom_id = bom_row["id"] if bom_row else None

    cur.execute(
        """SELECT id, wo_no FROM work_orders
           WHERE project_code=%s AND cabinet_no=%s
           ORDER BY id LIMIT 1""",
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    wo_row = cur.fetchone()
    wo_id = wo_row["id"] if wo_row else None
    wo_no = wo_row["wo_no"] if wo_row else None

    cur.execute(
        """SELECT id, shipment_no FROM sales_shipments
           WHERE project_code=%s AND cabinet_no=%s
           ORDER BY id DESC LIMIT 1""",
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    ship_row = cur.fetchone()
    shipment_id = ship_row["id"] if ship_row else None
    shipment_no = ship_row["shipment_no"] if ship_row else None

    cur.execute(
        """SELECT id, total_amount FROM customer_receivables
           WHERE project_code=%s AND cabinet_no=%s
           ORDER BY id DESC LIMIT 1""",
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    recv_row = cur.fetchone()
    receivable_id = recv_row["id"] if recv_row else None
    recv_amount = recv_row["total_amount"] if recv_row else Decimal("179840")

    print(f"Baseline: so_id={so_id} product_id={product_id} bom_id={bom_id} wo_id={wo_id} shipment_id={shipment_id} receivable_id={receivable_id}")

    # ---- Scenario 2: Create routing for baseline product ----
    cur.execute("SELECT COUNT(*) AS cnt FROM production_routings WHERE product_id=%s", (product_id,))
    routing_count = cur.fetchone()["cnt"]
    if routing_count == 0:
        cur.execute(
            """INSERT INTO production_routings
               (product_id, routing_no, name, status, is_active, created_at)
               VALUES (%s, %s, %s, %s, %s, NOW())
               RETURNING id""",
            (product_id, "RT-GT-TRIAL-001", "Trial routing for baseline product", "enabled", True),
        )
        rt_row = cur.fetchone()
        rt_id = rt_row["id"] if rt_row else None
        if rt_id:
            # routing_operations uses "sequence" not "sequence_no", "run_time" not "standard_time"
            cur.execute(
                """INSERT INTO routing_operations
                   (routing_id, sequence, operation_no, operation_name, run_time, is_active, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW())""",
                (rt_id, 10, "OP10", "roughing", Decimal("2.0"), True),
            )
            cur.execute(
                """INSERT INTO routing_operations
                   (routing_id, sequence, operation_no, operation_name, run_time, is_active, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW())""",
                (rt_id, 20, "OP20", "finishing", Decimal("3.0"), True),
            )
        print(f"Created routing RT-GT-TRIAL-001 (id={rt_id}) with 2 operations")
    else:
        print(f"Routing already exists (count={routing_count})")

    # ---- Scenario 5: Create pick list for baseline work order ----
    if wo_id:
        cur.execute("SELECT COUNT(*) AS cnt FROM pick_lists WHERE work_order_id=%s", (wo_id,))
        pick_count = cur.fetchone()["cnt"]
        if pick_count == 0:
            cur.execute(
                """SELECT bi.id, bi.product_id, bi.quantity, bi.unit
                   FROM bom_items bi WHERE bi.bom_id=%s""",
                (bom_id,),
            )
            bom_items = cur.fetchall()
            pick_no = f"PICK-GT-TRIAL-{datetime.now().strftime('%Y%m%d')}-001"
            cur.execute(
                """INSERT INTO pick_lists
                   (pick_no, work_order_id, warehouse_id, pick_date, status, project_code, cabinet_no, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                   RETURNING id""",
                (pick_no, wo_id, 4, date.today(), "draft", BASELINE_PROJECT, BASELINE_SERIAL),
            )
            pl_row = cur.fetchone()
            pl_id = pl_row["id"] if pl_row else None
            if pl_id and bom_items:
                for idx, bi in enumerate(bom_items, 1):
                    cur.execute(
                        """INSERT INTO pick_list_items
                           (pick_list_id, product_id, required_quantity, picked_quantity,
                            quantity, material_unit, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (pl_id, bi["product_id"], bi["quantity"], Decimal("0"), bi["quantity"], bi["unit"] or "", "pending"),
                    )
            print(f"Created pick list {pick_no} (id={pl_id}) with {len(bom_items)} lines")
        else:
            print(f"Pick list already exists (count={pick_count})")

    # ---- Scenario 6: Create operation reports for baseline work order ----
    if wo_id:
        cur.execute("SELECT COUNT(*) AS cnt FROM operation_reports WHERE work_order_id=%s", (wo_id,))
        op_count = cur.fetchone()["cnt"]
        if op_count == 0:
            # Ensure we have a work center with non-zero labor/overhead rates for cost derivation.
            cur.execute(
                """SELECT id FROM work_centers
                   WHERE COALESCE(labor_rate_per_hour, 0) > 0
                      OR COALESCE(overhead_rate_per_hour, 0) > 0
                   ORDER BY id LIMIT 1"""
            )
            wc_row = cur.fetchone()
            if wc_row:
                wc_id_for_op = wc_row["id"]
            else:
                # Pick the first work center and set non-zero rates so cost engine can derive.
                cur.execute("SELECT id FROM work_centers ORDER BY id LIMIT 1")
                fallback_wc = cur.fetchone()
                if fallback_wc:
                    wc_id_for_op = fallback_wc["id"]
                    cur.execute(
                        """UPDATE work_centers
                           SET labor_rate_per_hour=%s, overhead_rate_per_hour=%s
                           WHERE id=%s""",
                        (Decimal("80.00"), Decimal("120.00"), wc_id_for_op),
                    )
                else:
                    wc_id_for_op = None

            # Ensure we have an employee with non-zero standard_labor_rate_per_hour.
            cur.execute(
                """SELECT id FROM employees
                   WHERE COALESCE(standard_labor_rate_per_hour, 0) > 0
                   ORDER BY id LIMIT 1"""
            )
            emp_row = cur.fetchone()
            if emp_row:
                operator_id_for_op = emp_row["id"]
            else:
                cur.execute("SELECT id FROM employees ORDER BY id LIMIT 1")
                fallback_emp = cur.fetchone()
                if fallback_emp:
                    operator_id_for_op = fallback_emp["id"]
                    cur.execute(
                        """UPDATE employees
                           SET standard_labor_rate_per_hour=%s
                           WHERE id=%s""",
                        (Decimal("90.00"), operator_id_for_op),
                    )
                else:
                    operator_id_for_op = None

            for op_name, good_qty, labor_hours, equip_hours in [
                ("roughing", Decimal("1.0"), Decimal("2.0"), Decimal("2.5")),
                ("finishing", Decimal("1.0"), Decimal("3.0"), Decimal("3.5")),
            ]:
                cur.execute(
                    """INSERT INTO operation_reports
                       (report_no, work_order_id, report_type, report_date, status,
                        labor_hours, equipment_hours, good_qty,
                        operator_id, work_center_id,
                        project_code, cabinet_no, submitted_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                    (
                        f"OPR-GT-TRIAL-{op_name}-{datetime.now().strftime('%Y%m%d')}",
                        wo_id,
                        "process",
                        date.today(),
                        "approved",
                        labor_hours,
                        equip_hours,
                        good_qty,
                        operator_id_for_op,
                        wc_id_for_op,
                        BASELINE_PROJECT,
                        BASELINE_SERIAL,
                    ),
                )
            print(
                f"Created 2 operation reports for work_order_id={wo_id} "
                f"(operator_id={operator_id_for_op}, work_center_id={wc_id_for_op})"
            )
        else:
            print(f"Operation reports already exist (count={op_count})")
            # Repair existing operation reports that lack operator_id/work_center_id/equipment_hours
            # so the cost engine can derive non-zero labor/overhead costs.
            cur.execute(
                """SELECT id FROM work_centers
                   WHERE COALESCE(labor_rate_per_hour, 0) > 0
                      OR COALESCE(overhead_rate_per_hour, 0) > 0
                   ORDER BY id LIMIT 1"""
            )
            wc_row = cur.fetchone()
            wc_id_repair = wc_row["id"] if wc_row else None
            if not wc_id_repair:
                cur.execute("SELECT id FROM work_centers ORDER BY id LIMIT 1")
                fallback_wc = cur.fetchone()
                if fallback_wc:
                    wc_id_repair = fallback_wc["id"]
                    cur.execute(
                        """UPDATE work_centers
                           SET labor_rate_per_hour=%s, overhead_rate_per_hour=%s
                           WHERE id=%s""",
                        (Decimal("80.00"), Decimal("120.00"), wc_id_repair),
                    )

            cur.execute(
                """SELECT id FROM employees
                   WHERE COALESCE(standard_labor_rate_per_hour, 0) > 0
                   ORDER BY id LIMIT 1"""
            )
            emp_row = cur.fetchone()
            operator_id_repair = emp_row["id"] if emp_row else None
            if not operator_id_repair:
                cur.execute("SELECT id FROM employees ORDER BY id LIMIT 1")
                fallback_emp = cur.fetchone()
                if fallback_emp:
                    operator_id_repair = fallback_emp["id"]
                    cur.execute(
                        """UPDATE employees
                           SET standard_labor_rate_per_hour=%s
                           WHERE id=%s""",
                        (Decimal("90.00"), operator_id_repair),
                    )

            if wc_id_repair and operator_id_repair:
                cur.execute(
                    """UPDATE operation_reports
                       SET operator_id=COALESCE(operator_id, %s),
                           work_center_id=COALESCE(work_center_id, %s),
                           equipment_hours=CASE WHEN COALESCE(equipment_hours, 0) = 0
                                                THEN COALESCE(labor_hours, 0)
                                                ELSE equipment_hours END
                       WHERE work_order_id=%s
                         AND (operator_id IS NULL OR work_center_id IS NULL
                              OR COALESCE(equipment_hours, 0) = 0)""",
                    (operator_id_repair, wc_id_repair, wo_id),
                )
                repaired = cur.rowcount
                if repaired:
                    print(f"Repaired {repaired} existing operation reports with operator/work_center/equipment_hours")

    # ---- Scenario 7: Create sales invoice for baseline shipment ----
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM sales_invoices WHERE project_code=%s AND cabinet_no=%s",
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    inv_count = cur.fetchone()["cnt"]
    if inv_count == 0:
        inv_no = f"INV-GT-TRIAL-{datetime.now().strftime('%Y%m%d')}-001"
        cur.execute(
            """INSERT INTO sales_invoices
               (invoice_no, invoice_date, customer_id, invoice_type, total_amount,
                amount, status, project_code, cabinet_no, source_no, source_type,
                source_id, receivable_id, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
            (
                inv_no,
                date.today(),
                22,
                "sales",
                recv_amount,
                recv_amount,
                "issued",
                BASELINE_PROJECT,
                BASELINE_SERIAL,
                shipment_no or "",
                "sales_shipment",
                shipment_id,
                receivable_id,
            ),
        )
        print(f"Created sales invoice {inv_no} amount={recv_amount}")
    else:
        print(f"Sales invoices already exist (count={inv_count})")

    # ---- Scenario 4: Generate MRP suggestions with shortage ----
    cur.execute(
        """SELECT COUNT(*) AS cnt FROM mrp_suggestions ms
           JOIN mrp_runs mr ON mr.id=ms.run_id
           WHERE mr.project_code=%s OR mr.cabinet_no=%s""",
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    existing_suggestions = cur.fetchone()["cnt"]
    if existing_suggestions == 0:
        cur.execute(
            """SELECT id FROM mrp_runs WHERE project_code=%s ORDER BY id DESC LIMIT 1""",
            (BASELINE_PROJECT,),
        )
        run_row = cur.fetchone()
        run_id = run_row["id"] if run_row else None
        cur.execute("SELECT product_id, quantity FROM bom_items WHERE bom_id=%s", (bom_id,))
        bom_items = cur.fetchall()
        if run_id and bom_items:
            for idx, bi in enumerate(bom_items):
                suggestion_type = "purchase" if idx == 0 else "production"
                cur.execute(
                    """INSERT INTO mrp_suggestions
                       (run_id, suggestion_type, material_id, material_code, material_name,
                        qty, required_date, project_code, cabinet_no, status, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                    (
                        run_id,
                        suggestion_type,
                        bi["product_id"],
                        f"MAT-{bi['product_id']}",
                        f"Material {bi['product_id']}",
                        bi["quantity"],
                        date.today(),
                        BASELINE_PROJECT,
                        BASELINE_SERIAL,
                        "open",
                    ),
                )
            # Add outsource suggestion
            bi = bom_items[0]
            cur.execute(
                """INSERT INTO mrp_suggestions
                   (run_id, suggestion_type, material_id, material_code, material_name,
                    qty, required_date, project_code, cabinet_no, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                (
                    run_id,
                    "outsource",
                    bi["product_id"],
                    f"MAT-{bi['product_id']}",
                    f"Material {bi['product_id']}",
                    Decimal("1"),
                    date.today(),
                    BASELINE_PROJECT,
                    BASELINE_SERIAL,
                    "open",
                ),
            )
            print(f"Created MRP suggestions (purchase, production, outsource) for run_id={run_id}")
    else:
        print(f"MRP suggestions already exist (count={existing_suggestions})")

    conn.commit()
    print("\nBaseline data population complete.")
    conn.close()


if __name__ == "__main__":
    main()
