import os
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _env():
    os.environ.setdefault("PG_HOST", "127.0.0.1")
    os.environ.setdefault("PG_PORT", "5432")
    os.environ.setdefault("PG_DATABASE", "wms")
    os.environ.setdefault("PG_USER", "wms_user")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "production-pick-return-closure-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")


def _connect():
    from services.app_runtime import connect_db
    from services.env_config import get_pg_password

    return connect_db(
        {
            "host": os.environ["PG_HOST"],
            "port": int(os.environ["PG_PORT"]),
            "database": os.environ["PG_DATABASE"],
            "user": os.environ["PG_USER"],
            "password": get_pg_password(),
        }
    )


def _scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def _one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def _columns(cur, table):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def _insert_dynamic(cur, table, values):
    cols = _columns(cur, table)
    filtered = {key: value for key, value in values.items() if key in cols}
    names = list(filtered)
    placeholders = ",".join(["%s"] * len(names))
    cur.execute(
        f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders}) RETURNING id",
        [filtered[name] for name in names],
    )
    return cur.fetchone()["id"]


def _login_client(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["role"] = "admin"
        session["username"] = "admin"


def _prepare_fixture():
    suffix = str(int(time.time() * 1000))
    material_code = f"AUDIT-PR-MAT-{suffix}"
    warehouse_code = f"APR{suffix[-8:]}"
    wo_no = f"AUDIT-PR-WO-{suffix}"
    conn = _connect()
    try:
        with conn.cursor() as cur:
            product_id = _insert_dynamic(
                cur,
                "products",
                {
                    "code": material_code,
                    "name": "审计领退料物料",
                    "specification": "AUDIT",
                    "unit": "件",
                    "category": "生产用料",
                    "status": "启用",
                    "unit_cost": Decimal("10"),
                },
            )
            warehouse_id = _insert_dynamic(
                cur,
                "warehouses",
                {
                    "code": warehouse_code,
                    "name": "审计领退料仓",
                    "status": "启用",
                },
            )
            wo_id = _insert_dynamic(
                cur,
                "work_orders",
                {
                    "wo_no": wo_no,
                    "wo_date": "2026-06-03",
                    "product_id": product_id,
                    "quantity": Decimal("1"),
                    "status": "投产",
                    "warehouse_id": warehouse_id,
                    "project_code": "AUDIT-PRJ",
                    "serial_no": "AUDIT-SN",
                    "production_type": "整机生产",
                },
            )
            material_item_id = _insert_dynamic(
                cur,
                "wo_material_items",
                {
                    "wo_id": wo_id,
                    "product_id": product_id,
                    "required_qty": Decimal("5"),
                    "issued_qty": Decimal("0"),
                    "returned_qty": Decimal("0"),
                    "unit_cost": Decimal("10"),
                    "amount": Decimal("50"),
                    "warehouse_id": warehouse_id,
                    "material_code": material_code,
                    "material_name": "审计领退料物料",
                    "material_spec": "AUDIT",
                    "material_unit": "件",
                    "source_line_no": "AUDIT-L1",
                    "line_project_code": "AUDIT-PRJ",
                    "line_serial_no": "AUDIT-SN",
                },
            )
            cur.execute(
                """
                INSERT INTO inventory_balances
                    (product_id, warehouse_id, location_id, lot_no, serial_no, project_code, quantity, locked_qty, unit_cost, updated_at)
                VALUES (%s,%s,NULL,'','AUDIT-SN','AUDIT-PRJ',10,0,10,NOW())
                """,
                (product_id, warehouse_id),
            )
            cur.execute(
                """
                INSERT INTO inventory (product_id, quantity, unit_cost, location, reorder_level)
                VALUES (%s,10,10,'',0)
                """,
                (product_id,),
            )
            cur.execute(
                """
                INSERT INTO batch_tracking
                    (lot_no, product_id, warehouse_id, location_id, serial_no, project_code,
                     quantity_in, quantity_out, quantity_available, unit_cost, source_order_no, status, created_at, updated_at)
                VALUES ('', %s, %s, NULL, 'AUDIT-SN', 'AUDIT-PRJ', 10, 0, 10, 10, %s, 'derived', NOW(), NOW())
                """,
                (product_id, warehouse_id, wo_no),
            )
            cur.execute(
                """
                INSERT INTO stock_transactions
                    (transaction_date, transaction_type, product_id, quantity, unit_cost, reference_no,
                     lot_no, serial_no, project_code, location, remark, warehouse_id, location_id,
                     source_doc_type, source_doc_no, source_line_no, amount)
                VALUES ('2026-06-03', 'audit_opening_balance', %s, 10, 10, %s,
                        '', 'AUDIT-SN', 'AUDIT-PRJ', '', 'audit production pick return opening balance',
                        %s, NULL, 'audit_opening_balance', %s, 'AUDIT-L1', 100)
                """,
                (product_id, wo_no, warehouse_id, wo_no),
            )
        conn.commit()
        return {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "wo_id": wo_id,
            "material_item_id": material_item_id,
        }
    finally:
        conn.close()


def _post_pick(client, path, fixture, quantity):
    return client.post(
        path,
        data={
            "work_order_id": str(fixture["wo_id"]),
            "doc_date": "2026-06-03",
            "warehouse_id": str(fixture["warehouse_id"]),
            "remark": "audit production pick return closure",
            "item_id[]": [str(fixture["material_item_id"])],
            "quantity[]": [str(quantity)],
            "line_warehouse_id[]": [str(fixture["warehouse_id"])],
            "line_location_id[]": [""],
            "lot_no[]": [""],
            "save_action": "post",
        },
        follow_redirects=True,
    )


def _doc_id(cur, doc_type, wo_id):
    cur.execute(
        """
        SELECT id, doc_no
        FROM pick_lists
        WHERE doc_type=%s AND work_order_id=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (doc_type, wo_id),
    )
    return cur.fetchone()


def main():
    _env()
    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        _login_client(client)
        client.get("/production-issues")
        fixture = _prepare_fixture()
        issue_response = _post_pick(client, "/production-issues/new", fixture, Decimal("3"))
        return_response = _post_pick(client, "/production-returns/new", fixture, Decimal("1"))

    conn = _connect()
    try:
        with conn.cursor() as cur:
            issue_doc = _doc_id(cur, "production_issue", fixture["wo_id"])
            return_doc = _doc_id(cur, "production_return", fixture["wo_id"])
            material = _one(cur, "SELECT required_qty, issued_qty, returned_qty FROM wo_material_items WHERE id=%s", (fixture["material_item_id"],))
            balance_qty = _scalar(
                cur,
                """
                SELECT COALESCE(SUM(quantity),0)
                FROM inventory_balances
                WHERE product_id=%s AND warehouse_id=%s
                """,
                (fixture["product_id"], fixture["warehouse_id"]),
            )
            issue_tx_qty = _scalar(
                cur,
                "SELECT COALESCE(SUM(quantity),0) FROM stock_transactions WHERE source_doc_type='production_issue' AND source_doc_no=%s",
                (issue_doc["doc_no"] if issue_doc else "",),
            )
            return_tx_qty = _scalar(
                cur,
                "SELECT COALESCE(SUM(quantity),0) FROM stock_transactions WHERE source_doc_type='production_return' AND source_doc_no=%s",
                (return_doc["doc_no"] if return_doc else "",),
            )
            issue_status = _scalar(cur, "SELECT status FROM pick_lists WHERE id=%s", (issue_doc["id"],)) if issue_doc else None
            return_status = _scalar(cur, "SELECT status FROM pick_lists WHERE id=%s", (return_doc["id"],)) if return_doc else None

        checks = [
            ("issue_page_post_ok", issue_response.status_code == 200, issue_response.status_code),
            ("return_page_post_ok", return_response.status_code == 200, return_response.status_code),
            ("issue_doc_posted", issue_status == "completed", issue_status),
            ("return_doc_posted", return_status == "completed", return_status),
            ("wo_issued_qty_updated", Decimal(material["issued_qty"]) == Decimal("3"), material["issued_qty"]),
            ("wo_returned_qty_updated", Decimal(material["returned_qty"]) == Decimal("1"), material["returned_qty"]),
            ("inventory_balance_reconciled", Decimal(balance_qty) == Decimal("8"), balance_qty),
            ("issue_stock_transaction_deducted", Decimal(issue_tx_qty) == Decimal("-3"), issue_tx_qty),
            ("return_stock_transaction_reversed", Decimal(return_tx_qty) == Decimal("1"), return_tx_qty),
        ]
    finally:
        conn.close()

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("production_pick_return_closure_audit=ok" if not failures else "production_pick_return_closure_audit=failed")
    print(f"work_order_id={fixture['wo_id']}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
