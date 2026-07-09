from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "erp_auditor" / "config.py"


def load_db_config() -> dict:
    spec = importlib.util.spec_from_file_location("erp_auditor_config", CONFIG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load database config from {CONFIG_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cfg = dict(module.DB_CONFIG)
    cfg["host"] = os.environ.get("PG_HOST") or os.environ.get("DB_HOST") or cfg.get("host")
    cfg["port"] = int(os.environ.get("PG_PORT") or os.environ.get("DB_PORT") or cfg.get("port") or 5432)
    cfg["dbname"] = os.environ.get("PG_DATABASE") or os.environ.get("DB_NAME") or cfg.get("dbname")
    cfg["user"] = os.environ.get("PG_USER") or os.environ.get("DB_USER") or cfg.get("user")
    cfg["password"] = os.environ.get("PG_PASSWORD") or os.environ.get("DB_PASSWORD") or cfg.get("password")
    return cfg


def connect():
    return psycopg2.connect(cursor_factory=RealDictCursor, **load_db_config())


VOID_STATUSES = ("void", "voided", "cancelled", "canceled")


def fetch_count(cur, sql: str, params=()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return int(row.get("value") or 0)


def orphan_where() -> str:
    return """
        NOT EXISTS (
            SELECT 1 FROM subcontract_issue_orders sio
            WHERE sio.subcontract_order_id=so.id
              AND COALESCE(sio.status,'') NOT IN %s
        )
        AND NOT EXISTS (
            SELECT 1 FROM subcontract_receive_orders sro
            WHERE sro.subcontract_order_id=so.id
              AND COALESCE(sro.status,'') NOT IN %s
        )
    """


def collect_plan(cur) -> dict[str, int]:
    void_statuses = tuple(VOID_STATUSES)
    zero_orphans = fetch_count(
        cur,
        f"""
        SELECT COUNT(*) AS value
        FROM subcontract_orders so
        WHERE {orphan_where()}
          AND COALESCE(so.quantity,0)=0
          AND COALESCE(so.total_amount,0)=0
          AND so.product_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM supplier_payables sp
              WHERE sp.doc_type='subcontract_order'
                AND sp.doc_id=so.id
                AND (COALESCE(sp.amount,0)<>0 OR COALESCE(sp.balance,0)<>0)
          )
        """,
        (void_statuses, void_statuses),
    )
    audit_orphans = fetch_count(
        cur,
        f"""
        SELECT COUNT(*) AS value
        FROM subcontract_orders so
        LEFT JOIN suppliers s ON s.id=so.supplier_id
        LEFT JOIN products p ON p.id=so.product_id
        WHERE {orphan_where()}
          AND so.status='draft'
          AND COALESCE(so.remark,'') LIKE 'FULLSYS-AUDIT%%'
          AND COALESCE(s.name,'')='route approval supplier'
          AND COALESCE(p.code,'') LIKE 'RM-IMP-%%'
        """,
        (void_statuses, void_statuses),
    )
    trial_issue_headers = fetch_count(
        cur,
        """
        SELECT COUNT(*) AS value
        FROM subcontract_issue_orders sio
        WHERE sio.issue_no='OSI-GT-TRIAL-20260526-001'
          AND NOT EXISTS (SELECT 1 FROM subcontract_issue_lines sil WHERE sil.issue_id=sio.id)
        """,
    )
    trial_receive_headers = fetch_count(
        cur,
        """
        SELECT COUNT(*) AS value
        FROM subcontract_receive_orders sro
        WHERE sro.receive_no='OSR-GT-TRIAL-20260526-001'
          AND NOT EXISTS (SELECT 1 FROM subcontract_receive_lines srl WHERE srl.receive_id=sro.id)
        """,
    )
    trial_issue_stock = fetch_count(
        cur,
        """
        SELECT COUNT(*) AS value
        FROM subcontract_issue_orders sio
        WHERE sio.issue_no='OSI-GT-TRIAL-20260526-001'
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.reference_no=sio.issue_no AND st.transaction_type='subcontract_issue'
          )
        """,
    )
    trial_receive_stock = fetch_count(
        cur,
        """
        SELECT COUNT(*) AS value
        FROM subcontract_receive_orders sro
        WHERE sro.receive_no='OSR-GT-TRIAL-20260526-001'
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.reference_no=sro.receive_no AND st.transaction_type='subcontract_receive'
          )
        """,
    )
    trial_receive_payables = fetch_count(
        cur,
        """
        SELECT COUNT(*) AS value
        FROM subcontract_receive_orders sro
        JOIN subcontract_orders so ON so.id=sro.subcontract_order_id
        WHERE sro.receive_no='OSR-GT-TRIAL-20260526-001'
          AND COALESCE(sro.total_quantity,0)>0
          AND COALESCE(sro.supplier_id, so.supplier_id) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM supplier_payables sp
              WHERE sp.doc_type IN ('subcontract_receive','subcontract_receipt')
                AND (sp.doc_id=sro.id OR sp.doc_no=sro.receive_no)
          )
        """,
    )
    return {
        "zero_orphans_to_void": zero_orphans,
        "audit_orphans_to_void": audit_orphans,
        "trial_issue_headers_to_fill": trial_issue_headers,
        "trial_receive_headers_to_fill": trial_receive_headers,
        "trial_issue_stock_to_post": trial_issue_stock,
        "trial_receive_stock_to_post": trial_receive_stock,
        "trial_receive_payables_to_create": trial_receive_payables,
    }


def void_zero_orphans(cur) -> int:
    void_statuses = tuple(VOID_STATUSES)
    cur.execute(
        f"""
        UPDATE subcontract_orders so
        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE {orphan_where()}
          AND COALESCE(so.quantity,0)=0
          AND COALESCE(so.total_amount,0)=0
          AND so.product_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM supplier_payables sp
              WHERE sp.doc_type='subcontract_order'
                AND sp.doc_id=so.id
                AND (COALESCE(sp.amount,0)<>0 OR COALESCE(sp.balance,0)<>0)
          )
        """,
        (void_statuses, void_statuses),
    )
    return cur.rowcount


def void_audit_orphans(cur) -> int:
    void_statuses = tuple(VOID_STATUSES)
    cur.execute(
        f"""
        WITH targets AS (
            SELECT so.id
            FROM subcontract_orders so
            LEFT JOIN suppliers s ON s.id=so.supplier_id
            LEFT JOIN products p ON p.id=so.product_id
            WHERE {orphan_where()}
              AND so.status='draft'
              AND COALESCE(so.remark,'') LIKE 'FULLSYS-AUDIT%%'
              AND COALESCE(s.name,'')='route approval supplier'
              AND COALESCE(p.code,'') LIKE 'RM-IMP-%%'
        ),
        updated_orders AS (
            UPDATE subcontract_orders so
            SET status='cancelled', updated_at=CURRENT_TIMESTAMP
            FROM targets
            WHERE so.id=targets.id
            RETURNING so.id
        )
        UPDATE supplier_payables sp
        SET status='void',
            balance=0,
            finance_remark=CONCAT(COALESCE(sp.finance_remark,''), E'\nVoided with generated audit subcontract order.'),
            next_follow_up_date=NULL
        FROM updated_orders
        WHERE sp.doc_type='subcontract_order' AND sp.doc_id=updated_orders.id
        """,
        (void_statuses, void_statuses),
    )
    return cur.rowcount


def ensure_trial_lines(cur) -> tuple[int, int]:
    cur.execute(
        """
        INSERT INTO subcontract_issue_lines
            (issue_id, subcontract_order_id, product_id, material_code, material_name,
             material_spec, unit, quantity, warehouse_id, location_id, lot_no,
             project_code, serial_no, remark)
        SELECT sio.id, so.id, so.product_id, so.material_code, so.material_name,
               so.material_spec, so.material_unit, sio.total_quantity,
               sio.warehouse_id, sio.location_id, so.lot_no, so.project_code,
               so.serial_no, 'reconstructed trial line'
        FROM subcontract_issue_orders sio
        JOIN subcontract_orders so ON so.id=sio.subcontract_order_id
        WHERE sio.issue_no='OSI-GT-TRIAL-20260526-001'
          AND so.product_id IS NOT NULL
          AND COALESCE(sio.total_quantity,0)>0
          AND NOT EXISTS (SELECT 1 FROM subcontract_issue_lines sil WHERE sil.issue_id=sio.id)
        """
    )
    issue_count = cur.rowcount
    cur.execute(
        """
        INSERT INTO subcontract_receive_lines
            (receive_id, subcontract_order_id, product_id, material_code, material_name,
             material_spec, unit, quantity, scrap_quantity, warehouse_id, location_id,
             lot_no, project_code, serial_no, remark)
        SELECT sro.id, so.id, so.product_id, so.material_code, so.material_name,
               so.material_spec, so.material_unit, sro.total_quantity,
               COALESCE(sro.total_scrap,0), sro.warehouse_id, sro.location_id,
               so.lot_no, so.project_code, so.serial_no, 'reconstructed trial line'
        FROM subcontract_receive_orders sro
        JOIN subcontract_orders so ON so.id=sro.subcontract_order_id
        WHERE sro.receive_no='OSR-GT-TRIAL-20260526-001'
          AND so.product_id IS NOT NULL
          AND COALESCE(sro.total_quantity,0)>0
          AND NOT EXISTS (SELECT 1 FROM subcontract_receive_lines srl WHERE srl.receive_id=sro.id)
        """
    )
    receive_count = cur.rowcount
    return issue_count, receive_count


def adjust_inventory(cur, product_id: int, delta, unit_cost, reference_no: str, tx_type: str, tx_date, remark: str) -> None:
    cur.execute("SELECT id, quantity, unit_cost FROM inventory WHERE product_id=%s ORDER BY id LIMIT 1", (product_id,))
    inv = cur.fetchone()
    if inv:
        new_qty = (inv.get("quantity") or 0) + delta
        cur.execute("UPDATE inventory SET quantity=%s WHERE id=%s", (new_qty, inv["id"]))
    else:
        cur.execute(
            "INSERT INTO inventory (product_id, quantity, unit_cost, location, reorder_level) VALUES (%s,%s,%s,%s,0)",
            (product_id, delta, unit_cost, ""),
        )

    cur.execute(
        """
        SELECT id, quantity
        FROM inventory_balances
        WHERE product_id=%s
          AND COALESCE(lot_no,'')=''
          AND COALESCE(serial_no,'')=''
          AND COALESCE(project_code,'')=''
        ORDER BY id LIMIT 1
        """,
        (product_id,),
    )
    balance = cur.fetchone()
    if balance:
        cur.execute(
            "UPDATE inventory_balances SET quantity=COALESCE(quantity,0)+%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (delta, balance["id"]),
        )
    else:
        cur.execute(
            """
            INSERT INTO inventory_balances
                (product_id, warehouse_id, location_id, lot_no, serial_no, project_code,
                 quantity, locked_qty, unit_cost, updated_at)
            VALUES (%s,NULL,NULL,'','','',%s,0,%s,CURRENT_TIMESTAMP)
            """,
            (product_id, delta, unit_cost),
        )

    cur.execute(
        """
        INSERT INTO stock_transactions
            (transaction_date, transaction_type, product_id, quantity, unit_cost,
             reference_no, lot_no, serial_no, project_code, location, remark,
             warehouse_id, location_id, source_type, source_doc_type, source_doc_no)
        VALUES (%s,%s,%s,%s,%s,%s,'','','','',%s,NULL,NULL,%s,%s,%s)
        """,
        (tx_date, tx_type, product_id, delta, unit_cost, reference_no, remark, tx_type, tx_type, reference_no),
    )


def post_trial_stock(cur) -> tuple[int, int]:
    cur.execute(
        """
        SELECT sio.issue_no, sio.date, sil.product_id, sil.quantity, COALESCE(inv.unit_cost,0) AS unit_cost
        FROM subcontract_issue_orders sio
        JOIN subcontract_issue_lines sil ON sil.issue_id=sio.id
        LEFT JOIN inventory inv ON inv.product_id=sil.product_id
        WHERE sio.issue_no='OSI-GT-TRIAL-20260526-001'
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.reference_no=sio.issue_no AND st.transaction_type='subcontract_issue'
          )
        """
    )
    issue_rows = cur.fetchall()
    for row in issue_rows:
        adjust_inventory(
            cur,
            row["product_id"],
            -row["quantity"],
            row["unit_cost"],
            row["issue_no"],
            "subcontract_issue",
            row["date"],
            "reconstructed trial subcontract issue",
        )
    cur.execute(
        """
        SELECT sro.receive_no, sro.date, srl.product_id, srl.quantity, COALESCE(inv.unit_cost,0) AS unit_cost
        FROM subcontract_receive_orders sro
        JOIN subcontract_receive_lines srl ON srl.receive_id=sro.id
        LEFT JOIN inventory inv ON inv.product_id=srl.product_id
        WHERE sro.receive_no='OSR-GT-TRIAL-20260526-001'
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.reference_no=sro.receive_no AND st.transaction_type='subcontract_receive'
          )
        """
    )
    receive_rows = cur.fetchall()
    for row in receive_rows:
        adjust_inventory(
            cur,
            row["product_id"],
            row["quantity"],
            row["unit_cost"],
            row["receive_no"],
            "subcontract_receive",
            row["date"],
            "reconstructed trial subcontract receive",
        )
    if issue_rows:
        cur.execute(
            """
            UPDATE subcontract_issue_orders
            SET posted=TRUE, posted_at=COALESCE(posted_at,CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP
            WHERE issue_no='OSI-GT-TRIAL-20260526-001'
            """
        )
    if receive_rows:
        cur.execute(
            """
            UPDATE subcontract_receive_orders
            SET posted=TRUE, posted_at=COALESCE(posted_at,CURRENT_TIMESTAMP), updated_at=CURRENT_TIMESTAMP
            WHERE receive_no='OSR-GT-TRIAL-20260526-001'
            """
        )
    return len(issue_rows), len(receive_rows)


def create_trial_receive_payables(cur) -> int:
    cur.execute(
        """
        INSERT INTO supplier_payables
            (supplier_id, doc_type, doc_id, doc_no, doc_date, amount, paid_amount,
             balance, status, finance_remark, project_code, serial_no, cost_object_id)
        SELECT COALESCE(sro.supplier_id, so.supplier_id),
               'subcontract_receive',
               sro.id,
               sro.receive_no,
               sro.date,
               COALESCE(sro.total_quantity,0) * COALESCE(so.unit_price,0),
               0,
               COALESCE(sro.total_quantity,0) * COALESCE(so.unit_price,0),
               'unpaid',
               CONCAT('Reconstructed payable for reviewed subcontract receive ', COALESCE(so.order_no,'')),
               COALESCE(so.project_code, ''),
               COALESCE(so.serial_no, ''),
               so.cost_object_id
        FROM subcontract_receive_orders sro
        JOIN subcontract_orders so ON so.id=sro.subcontract_order_id
        WHERE sro.receive_no='OSR-GT-TRIAL-20260526-001'
          AND COALESCE(sro.total_quantity,0)>0
          AND COALESCE(sro.supplier_id, so.supplier_id) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM supplier_payables sp
              WHERE sp.doc_type IN ('subcontract_receive','subcontract_receipt')
                AND (sp.doc_id=sro.id OR sp.doc_no=sro.receive_no)
          )
        """
    )
    return cur.rowcount


def apply_repair(cur) -> dict[str, int]:
    zero_orphans = void_zero_orphans(cur)
    audit_payables = void_audit_orphans(cur)
    issue_lines, receive_lines = ensure_trial_lines(cur)
    issue_stock, receive_stock = post_trial_stock(cur)
    receive_payables = create_trial_receive_payables(cur)
    return {
        "zero_orphans_voided": zero_orphans,
        "audit_payables_voided": audit_payables,
        "trial_issue_lines_inserted": issue_lines,
        "trial_receive_lines_inserted": receive_lines,
        "trial_issue_stock_posted": issue_stock,
        "trial_receive_stock_posted": receive_stock,
        "trial_receive_payables_created": receive_payables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair reviewed subcontract closure demo/audit data.")
    parser.add_argument("--apply", action="store_true", help="Apply the repair. Without this flag only prints the plan.")
    args = parser.parse_args()

    with connect() as conn, conn.cursor() as cur:
        plan = collect_plan(cur)
        print("repair_subcontract_closure_mode=apply" if args.apply else "repair_subcontract_closure_mode=dry_run")
        for key, value in plan.items():
            print(f"{key}={value}")
        if not args.apply:
            conn.rollback()
            return 0
        result = apply_repair(cur)
        conn.commit()
        for key, value in result.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
