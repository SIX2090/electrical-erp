from decimal import Decimal
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


def db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def count(cur, sql, params=()):
    cur.execute(sql, params)
    return int((cur.fetchone() or {}).get("value") or 0)


def ensure_assembly_docs(cur, baseline):
    project_code = baseline["project_code"]
    cabinet_no = baseline["cabinet_no"]
    assembly_no = f"ASM-{project_code}"
    disassembly_no = f"DIS-{project_code}"
    material_id = baseline["material1_id"]
    finished_id = baseline["finished_id"]
    warehouse_id = baseline["warehouse_id"]
    location_id = baseline["location_id"]

    cur.execute(
        """
        INSERT INTO inventory_assembly_orders
            (assembly_no, doc_type, doc_date, warehouse_id, location_id, product_id, quantity,
             unit_cost, lot_no, cabinet_no, project_code, status, remark, posted_at)
        VALUES (%s, 'assembly', CURRENT_DATE, %s, %s, %s, 1, 120000, '', %s, %s,
                '已过账', 'agent f assembly trace verification', NOW())
        ON CONFLICT DO NOTHING
        """,
        (assembly_no, warehouse_id, location_id, finished_id, cabinet_no, project_code),
    )
    assembly = one(cur, "SELECT id, assembly_no FROM inventory_assembly_orders WHERE assembly_no=%s AND doc_type='assembly'", (assembly_no,))
    cur.execute(
        """
        INSERT INTO inventory_assembly_items
            (order_id, product_id, quantity, unit_cost, lot_no, cabinet_no, line_role, remark,
             line_project_code, amount)
        SELECT %s, %s, 1, 100, '', %s, 'component', 'agent f assembly component',
               %s, 100
        WHERE NOT EXISTS (
            SELECT 1 FROM inventory_assembly_items WHERE order_id=%s AND product_id=%s
        )
        """,
        (assembly["id"], material_id, cabinet_no, project_code, assembly["id"], material_id),
    )
    for tx_type, product_id, qty, unit_cost in (("组装领料", material_id, Decimal("-1"), Decimal("100")), ("组装入库", finished_id, Decimal("1"), Decimal("120000"))):
        cur.execute(
            """
            INSERT INTO stock_transactions
                (transaction_date, transaction_type, product_id, quantity, unit_cost,
                 reference_no, lot_no, cabinet_no, project_code, remark, warehouse_id,
                 location_id, source_type, amount, source_doc_type, source_doc_no)
            SELECT CURRENT_DATE, %s, %s, %s, %s, %s, '', %s, %s,
                   'agent f assembly trace verification', %s, %s, 'inventory_assembly',
                   ABS(%s * %s), 'inventory_assembly', %s
            WHERE NOT EXISTS (
                SELECT 1 FROM stock_transactions
                WHERE reference_no=%s AND transaction_type=%s AND product_id=%s
            )
            """,
            (tx_type, product_id, qty, unit_cost, assembly_no, cabinet_no, project_code, warehouse_id, location_id, qty, unit_cost, assembly_no, assembly_no, tx_type, product_id),
        )

    cur.execute(
        """
        INSERT INTO inventory_assembly_orders
            (assembly_no, doc_type, doc_date, warehouse_id, location_id, product_id, quantity,
             unit_cost, lot_no, cabinet_no, project_code, status, remark, posted_at)
        VALUES (%s, 'disassembly', CURRENT_DATE, %s, %s, %s, 1, 120000, '', %s, %s,
                '已过账', 'agent f disassembly trace verification', NOW())
        ON CONFLICT DO NOTHING
        """,
        (disassembly_no, warehouse_id, location_id, finished_id, cabinet_no, project_code),
    )
    disassembly = one(cur, "SELECT id, assembly_no FROM inventory_assembly_orders WHERE assembly_no=%s AND doc_type='disassembly'", (disassembly_no,))
    cur.execute(
        """
        INSERT INTO inventory_assembly_items
            (order_id, product_id, quantity, unit_cost, lot_no, cabinet_no, line_role, remark,
             line_project_code, amount)
        SELECT %s, %s, 1, 100, '', %s, 'component', 'agent f disassembly component',
               %s, 100
        WHERE NOT EXISTS (
            SELECT 1 FROM inventory_assembly_items WHERE order_id=%s AND product_id=%s
        )
        """,
        (disassembly["id"], material_id, cabinet_no, project_code, disassembly["id"], material_id),
    )
    for tx_type, product_id, qty, unit_cost in (("拆卸出库", finished_id, Decimal("-1"), Decimal("120000")), ("拆卸入库", material_id, Decimal("1"), Decimal("100"))):
        cur.execute(
            """
            INSERT INTO stock_transactions
                (transaction_date, transaction_type, product_id, quantity, unit_cost,
                 reference_no, lot_no, cabinet_no, project_code, remark, warehouse_id,
                 location_id, source_type, amount, source_doc_type, source_doc_no)
            SELECT CURRENT_DATE, %s, %s, %s, %s, %s, '', %s, %s,
                   'agent f disassembly trace verification', %s, %s, 'inventory_disassembly',
                   ABS(%s * %s), 'inventory_disassembly', %s
            WHERE NOT EXISTS (
                SELECT 1 FROM stock_transactions
                WHERE reference_no=%s AND transaction_type=%s AND product_id=%s
            )
            """,
            (tx_type, product_id, qty, unit_cost, disassembly_no, cabinet_no, project_code, warehouse_id, location_id, qty, unit_cost, disassembly_no, disassembly_no, tx_type, product_id),
        )
    return assembly, disassembly


def ensure_schedule_doc(cur, baseline):
    project_code = baseline["project_code"]
    schedule_no = f"SCH-{project_code}"
    cur.execute(
        """
        INSERT INTO production_schedules
            (schedule_no, work_order_id, start_date, end_date, quantity,
             planned_start_date, planned_end_date, owner_role, responsible_person,
             blocked_reason, next_action, downstream_impact, dispatch_status, status, remark)
        SELECT %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', 1,
               CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', '生产计划', '生产主管',
               '', '按工单齐套后派工', '影响首台机装配调试', '待派工', 'scheduled',
               'agent f schedule query verification'
        WHERE NOT EXISTS (SELECT 1 FROM production_schedules WHERE schedule_no=%s)
        """,
        (schedule_no, baseline["work_order_id"], schedule_no),
    )
    return one(cur, "SELECT id, schedule_no FROM production_schedules WHERE schedule_no=%s", (schedule_no,))


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "agent-f-production-inventory")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_first_machine_values(TEMPLATE)
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    checks = []

    conn = connect_db(db_config())
    try:
        with conn.cursor() as cur:
            baseline = ensure_first_machine_production_inventory_baseline(cur, values)
            assembly, disassembly = ensure_assembly_docs(cur, baseline)
            schedule = ensure_schedule_doc(cur, baseline)
            conn.commit()
            checks.append(("work_order_baseline", bool(baseline.get("work_order_id")), baseline.get("work_order_id")))
            checks.append(("assembly_traceable", bool(assembly), assembly.get("assembly_no") if assembly else "missing"))
            checks.append(("disassembly_traceable", bool(disassembly), disassembly.get("assembly_no") if disassembly else "missing"))
            checks.append(("assembly_stock_flow", count(cur, "SELECT COUNT(*) AS value FROM stock_transactions WHERE project_code=%s AND cabinet_no=%s AND reference_no=%s", (project_code, cabinet_no, assembly.get("assembly_no") if assembly else "")) >= 2, assembly.get("assembly_no") if assembly else "missing"))
            checks.append(("disassembly_stock_flow", count(cur, "SELECT COUNT(*) AS value FROM stock_transactions WHERE project_code=%s AND cabinet_no=%s AND reference_no=%s", (project_code, cabinet_no, disassembly.get("assembly_no") if disassembly else "")) >= 2, disassembly.get("assembly_no") if disassembly else "missing"))
            checks.append(("production_schedule_query_source", bool(schedule), schedule.get("schedule_no") if schedule else "missing"))
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    login = client.post("/login", data={"username": "admin", "password": "admin"})
    checks.append(("admin_login", login.status_code == 302, login.status_code))
    if login.status_code == 302:
        for path, expected in [
            (f"/assembly-orders?keyword={project_code}", [project_code, cabinet_no, "ASM"]),
            (f"/disassembly-orders?keyword={project_code}", [project_code, cabinet_no, "DIS"]),
            (f"/transactions?keyword={project_code}", [project_code, cabinet_no, "组装", "拆卸"]),
            (f"/production-schedules?keyword={project_code}", [project_code, cabinet_no]),
        ]:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("agent_f_production_inventory_closure=ok" if not failures else "agent_f_production_inventory_closure=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"cabinet_no={cabinet_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
