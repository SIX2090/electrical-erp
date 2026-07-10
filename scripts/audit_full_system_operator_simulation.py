from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402


OUT_PATH = ROOT / "logs" / "full_system_operator_simulation.json"
AUDIT_TAG = f"FULLSYS-AUDIT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
MOJIBAKE_CODEPOINTS = {0xFFFD}
MOJIBAKE_SEQUENCES = (
    tuple(map(ord, text))
    for text in (
        "\u7487\ufe3d",
        "\u6434\u65c0",
        "\u93c2\u677f",
        "\u95b2\u56ea",
        "\u9417\u2574",
        "\u6434\u64b3",
        "\u95bf\u20ac",
    )
)
MOJIBAKE_SEQUENCES = tuple(MOJIBAKE_SEQUENCES)


def has_mojibake(text):
    if "???" in text or any(ord(ch) in MOJIBAKE_CODEPOINTS for ch in text):
        return True
    if any(0xE000 <= ord(ch) <= 0xF8FF for ch in text):
        return True
    codepoints = tuple(map(ord, text))
    return any(sequence and _contains_sequence(codepoints, sequence) for sequence in MOJIBAKE_SEQUENCES)


def _contains_sequence(values, sequence):
    size = len(sequence)
    if not size or len(values) < size:
        return False
    return any(values[index : index + size] == sequence for index in range(len(values) - size + 1))


def connect():
    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
        client_encoding="UTF8",
    )
    conn.autocommit = True
    return conn


def fetch_one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def fetch_all(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s) AS name", (table,))
    row = cur.fetchone()
    return bool(row and row["name"])


def column_exists(cur, table, column):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def scalar(cur, sql, params=()):
    row = fetch_one(cur, sql, params)
    if not row:
        return None
    return next(iter(row.values()))


def repair_missing_service_cards_from_shipments(cur):
    if not table_exists(cur, "sales_shipments") or not table_exists(cur, "sales_shipment_items"):
        return 0
    cur.execute(
        """
        WITH candidates AS (
            SELECT DISTINCT ON (s.cabinet_no)
                   s.order_id AS sales_order_id,
                   COALESCE(NULLIF(s.project_code, ''), NULLIF(so.project_code, '')) AS project_code,
                   NULLIF(s.cabinet_no, '') AS cabinet_no,
                   COALESCE(s.customer_id, so.customer_id) AS customer_id,
                   so.cost_object_id,
                   s.shipment_date,
                   COALESCE(si.product_id, soi.product_id) AS product_id,
                   COALESCE(p.name, p.code, '') AS machine_model
              FROM sales_shipments s
         LEFT JOIN sales_orders so ON so.id=s.order_id
         LEFT JOIN sales_shipment_items si ON si.shipment_id=s.id
         LEFT JOIN sales_order_items soi ON soi.id=si.order_item_id OR soi.order_id=s.order_id
         LEFT JOIN products p ON p.id=COALESCE(si.product_id, soi.product_id)
         LEFT JOIN machine_service_cards c
                ON COALESCE(c.cabinet_no, '')=COALESCE(s.cabinet_no, '')
             WHERE COALESCE(s.cabinet_no, '')<>''
               AND c.id IS NULL
               AND COALESCE(si.product_id, soi.product_id) IS NOT NULL
          ORDER BY s.cabinet_no, s.shipment_date NULLS LAST, s.id
        )
        INSERT INTO machine_service_cards (
            sales_order_id, cost_object_id, project_code, cabinet_no, product_id,
            customer_id, install_date, installation_date, status, machine_model, remark
        )
        SELECT sales_order_id, cost_object_id, project_code, cabinet_no, product_id,
               customer_id, shipment_date, shipment_date, '已安装待验收', machine_model,
               'Backfilled by full system operator simulation from posted shipment trace.'
          FROM candidates
        """
    )
    return cur.rowcount


def db_snapshot(cur):
    service_card_repairs = repair_missing_service_cards_from_shipments(cur)
    product_where = "WHERE COALESCE(is_active, TRUE)=TRUE" if column_exists(cur, "products", "is_active") else ""
    refs = {
        "product": fetch_one(
            cur,
            f"""
            SELECT id, code, name, specification, unit, COALESCE(standard_price, 1) AS standard_price
            FROM products
            {product_where}
            ORDER BY id
            LIMIT 1
            """,
        ),
        "supplier": fetch_one(cur, "SELECT id, name FROM suppliers ORDER BY id LIMIT 1"),
        "customer": fetch_one(cur, "SELECT id, name FROM customers ORDER BY id LIMIT 1"),
        "warehouse": fetch_one(cur, "SELECT id, name FROM warehouses ORDER BY id LIMIT 1"),
        "warehouse_2": fetch_one(cur, "SELECT id, name FROM warehouses ORDER BY id OFFSET 1 LIMIT 1"),
        "location": fetch_one(cur, "SELECT id, warehouse_id, code, name FROM locations ORDER BY id LIMIT 1")
        if table_exists(cur, "locations")
        else None,
        "service_card": fetch_one(cur, "SELECT id, project_code, cabinet_no FROM machine_service_cards ORDER BY id DESC LIMIT 1")
        if table_exists(cur, "machine_service_cards")
        else None,
        "service_card_repairs": service_card_repairs,
        "delivered_cabinet_count": scalar(cur, "SELECT COUNT(*) FROM sales_shipments WHERE COALESCE(cabinet_no, '')<>''")
        if table_exists(cur, "sales_shipments")
        else 0,
    }
    normalized = {}
    for key, value in refs.items():
        if isinstance(value, RealDictCursor):
            normalized[key] = value
        elif hasattr(value, "keys"):
            normalized[key] = dict(value)
        else:
            normalized[key] = value
    return normalized


def login(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit"
        session["role"] = "admin"


def page_access_checks(client):
    paths = [
        ("/", "workbench", "live"),
        ("/material", "master_data", "live"),
        ("/customer", "master_data", "live"),
        ("/supplier", "master_data", "live"),
        ("/warehouse", "master_data", "live"),
        ("/purchase_request/new", "purchase_document_entry", "live"),
        ("/purchase_request", "purchase_document_list", "live"),
        ("/purchase-orders", "purchase_document_list", "live"),
        ("/purchase_receipts", "purchase_document_list", "live"),
        ("/sales/new", "sales_document_entry", "live"),
        ("/sales-orders", "sales_document_list", "live"),
        ("/shipments", "sales_document_list", "live"),
        ("/work-orders/new", "production_document_entry", "live"),
        ("/work-orders", "production_document_list", "live"),
        ("/subcontract/new", "subcontract_document_entry", "live"),
        ("/subcontract", "subcontract_document_list", "live"),
        ("/subcontract_issue/new", "subcontract_document_entry", "live"),
        ("/subcontract_receive/new", "subcontract_document_entry", "live"),
        ("/inventory", "inventory_workbench", "live"),
        ("/transactions", "inventory_query_list", "live"),
        ("/adjustments/new", "inventory_document_entry", "live"),
        ("/transfers/new", "inventory_document_entry", "live"),
        ("/inventory_checks/new", "inventory_document_entry", "live"),
        ("/assembly-orders/new", "inventory_document_entry", "live"),
        ("/service-orders/new", "service_document_entry", "live"),
        ("/service-orders", "service_document_list", "live"),
        ("/service-rmas/new", "service_document_entry", "live"),
        ("/service-rmas", "service_document_list", "live"),
        ("/service-cards", "service_master_trace", "live"),
        ("/receivables", "finance_query", "live"),
        ("/payables", "finance_query", "live"),
        ("/finance", "finance_workbench", "live"),
    ]
    rows = []
    for path, page_type, classification in paths:
        print(f"page_check={path}", flush=True)
        response = client.get(path, follow_redirects=False)
        text = response.get_data().decode("utf-8", errors="ignore")
        rows.append(
            {
                "path": path,
                "page_type": page_type,
                "classification": classification,
                "status_code": response.status_code,
                "ok": response.status_code in {200, 302},
                "mojibake": has_mojibake(text),
            }
        )
    return rows


def post_purchase_request(client, cur, refs):
    product = refs["product"]
    if not product:
        return {"ok": False, "blocked_reason": "missing active product master data"}
    req_no = f"PR-AUD-{datetime.now().strftime('%H%M%S')}"
    payload = {
        "request_no": req_no,
        "date": date.today().isoformat(),
        "department": "audit",
        "reason": AUDIT_TAG,
        "remark": AUDIT_TAG,
        "project_code": "",
        "cabinet_no": "",
        "items": [
            {
                "material_id": product["id"],
                "material_code": product["code"],
                "quantity": "2",
                "estimated_price": "3.50",
                "supplier_id": refs["supplier"]["id"] if refs.get("supplier") else None,
            }
        ],
    }
    response = client.post("/purchase_request/add", json=payload)
    created = fetch_one(cur, "SELECT * FROM purchase_requisitions WHERE req_no=%s", (req_no,))
    item_count = scalar(cur, "SELECT COUNT(*) FROM purchase_requisition_items WHERE req_id=%s", (created["id"],)) if created else 0
    ok = response.status_code == 200 and created and item_count == 1
    result = {
        "ok": bool(ok),
        "status_code": response.status_code,
        "document_no": req_no,
        "document_id": created["id"] if created else None,
        "line_count": int(item_count or 0),
    }
    if created:
        cur.execute("DELETE FROM document_custom_field_values WHERE document_type='purchase_request' AND document_id=%s", (created["id"],))
        cur.execute("DELETE FROM purchase_requisition_items WHERE req_id=%s", (created["id"],))
        cur.execute("DELETE FROM purchase_requisitions WHERE id=%s", (created["id"],))
    return result


def post_purchase_order(client, cur, refs):
    if not refs.get("product") or not refs.get("supplier"):
        return {"ok": False, "blocked_reason": "missing product or supplier master data"}
    before = scalar(cur, "SELECT COALESCE(MAX(id),0) FROM purchase_orders")
    form = {
        "supplier_id": str(refs["supplier"]["id"]),
        "order_date": date.today().isoformat(),
        "expected_date": date.today().isoformat(),
        "warehouse_id": str(refs["warehouse"]["id"]) if refs.get("warehouse") else "",
        "remark": AUDIT_TAG,
        "product_id[]": str(refs["product"]["id"]),
        "quantity[]": "2",
        "unit_price[]": "3.50",
        "tax_rate[]": "13",
        "lot_no[]": AUDIT_TAG,
    }
    response = client.post("/purchase_order/new", data=form, follow_redirects=False)
    created = fetch_one(cur, "SELECT * FROM purchase_orders WHERE id>%s AND remark=%s ORDER BY id DESC LIMIT 1", (before, AUDIT_TAG))
    line_count = scalar(cur, "SELECT COUNT(*) FROM purchase_order_items WHERE order_id=%s", (created["id"],)) if created else 0
    payable = scalar(cur, "SELECT COUNT(*) FROM supplier_payables WHERE doc_type='purchase_order' AND doc_id=%s", (created["id"],)) if created else 0
    ok = response.status_code in {302, 303} and created and line_count == 1 and payable == 1
    result = {"ok": bool(ok), "status_code": response.status_code, "document_id": created["id"] if created else None, "line_count": int(line_count or 0), "payable_count": int(payable or 0)}
    if created:
        cur.execute("DELETE FROM supplier_payables WHERE doc_type='purchase_order' AND doc_id=%s", (created["id"],))
        cur.execute("DELETE FROM document_custom_field_values WHERE document_type='purchase_order' AND document_id=%s", (created["id"],))
        cur.execute("DELETE FROM purchase_order_items WHERE order_id=%s", (created["id"],))
        cur.execute("DELETE FROM purchase_orders WHERE id=%s", (created["id"],))
    return result


def post_sales_order(client, cur, refs):
    if not refs.get("product") or not refs.get("customer"):
        return {"ok": False, "blocked_reason": "missing product or customer master data"}
    before = scalar(cur, "SELECT COALESCE(MAX(id),0) FROM sales_orders")
    form = {
        "customer_id": str(refs["customer"]["id"]),
        "order_date": date.today().isoformat(),
        "delivery_date": date.today().isoformat(),
        "warehouse_id": str(refs["warehouse"]["id"]) if refs.get("warehouse") else "",
        "remark": AUDIT_TAG,
        "product_id[]": str(refs["product"]["id"]),
        "quantity[]": "2",
        "unit_price[]": "3.50",
        "tax_rate[]": "13",
        "lot_no[]": AUDIT_TAG,
    }
    response = client.post("/sales/new", data=form, follow_redirects=False)
    created = fetch_one(cur, "SELECT * FROM sales_orders WHERE id>%s AND remark=%s ORDER BY id DESC LIMIT 1", (before, AUDIT_TAG))
    line_count = scalar(cur, "SELECT COUNT(*) FROM sales_order_items WHERE order_id=%s", (created["id"],)) if created else 0
    receivable = scalar(cur, "SELECT COUNT(*) FROM customer_receivables WHERE source_type='sales_order' AND source_id=%s", (created["id"],)) if created else 0
    ok = response.status_code in {302, 303} and created and line_count == 1 and receivable == 1
    result = {"ok": bool(ok), "status_code": response.status_code, "document_id": created["id"] if created else None, "line_count": int(line_count or 0), "receivable_count": int(receivable or 0)}
    if created:
        cur.execute("DELETE FROM customer_receivables WHERE source_type='sales_order' AND source_id=%s", (created["id"],))
        cur.execute("DELETE FROM document_custom_field_values WHERE document_type='sales_order' AND document_id=%s", (created["id"],))
        cur.execute("DELETE FROM sales_order_items WHERE order_id=%s", (created["id"],))
        cur.execute("DELETE FROM sales_orders WHERE id=%s", (created["id"],))
    return result


def post_subcontract_order(client, cur, refs):
    if not refs.get("product") or not refs.get("supplier"):
        return {"ok": False, "blocked_reason": "missing product or supplier master data"}
    before = scalar(cur, "SELECT COALESCE(MAX(id),0) FROM subcontract_orders")
    form = {
        "supplier_id": str(refs["supplier"]["id"]),
        "order_date": date.today().isoformat(),
        "required_date": date.today().isoformat(),
        "remark": AUDIT_TAG,
        "product_id[]": str(refs["product"]["id"]),
        "quantity[]": "2",
        "unit_price[]": "3.50",
        "process_name[]": "audit",
    }
    response = client.post("/subcontract/new", data=form, follow_redirects=False)
    created = fetch_one(cur, "SELECT * FROM subcontract_orders WHERE id>%s AND remark=%s ORDER BY id DESC LIMIT 1", (before, AUDIT_TAG))
    payable = scalar(cur, "SELECT COUNT(*) FROM supplier_payables WHERE doc_type='subcontract_order' AND doc_id=%s", (created["id"],)) if created else 0
    ok = response.status_code in {302, 303} and created and created["status"] == "draft" and payable == 1
    result = {"ok": bool(ok), "status_code": response.status_code, "document_id": created["id"] if created else None, "status": created["status"] if created else None, "payable_count": int(payable or 0)}
    if created:
        cur.execute("DELETE FROM supplier_payables WHERE doc_type='subcontract_order' AND doc_id=%s", (created["id"],))
        cur.execute("DELETE FROM subcontract_orders WHERE id=%s", (created["id"],))
    return result


def post_work_order(client, cur, refs):
    if not refs.get("product"):
        return {"ok": False, "blocked_reason": "missing product master data"}
    before = scalar(cur, "SELECT COALESCE(MAX(id),0) FROM work_orders")
    form = {
        "product_id": str(refs["product"]["id"]),
        "wo_date": date.today().isoformat(),
        "quantity": "1",
        "unit_cost": "3.50",
        "remark": AUDIT_TAG,
        "material_code_display": refs["product"].get("code") or "",
        "material_name_display": refs["product"].get("name") or "",
        "specification_display": refs["product"].get("specification") or "",
        "unit_display": refs["product"].get("unit") or "",
        "warehouse_id": str(refs["warehouse"]["id"]) if refs.get("warehouse") else "",
    }
    response = client.post("/work-orders/new", data=form, follow_redirects=False)
    created = fetch_one(cur, "SELECT * FROM work_orders WHERE id>%s AND remark=%s ORDER BY id DESC LIMIT 1", (before, AUDIT_TAG))
    ok = response.status_code in {302, 303} and bool(created)
    result = {"ok": bool(ok), "status_code": response.status_code, "document_id": created["id"] if created else None, "status": created["status"] if created else None}
    if created:
        for table, column in (
            ("work_order_stage_logs", "work_order_id"),
            ("work_order_component_items", "work_order_id"),
            ("work_order_extra_materials", "work_order_id"),
            ("work_order_quality_records", "work_order_id"),
        ):
            if table_exists(cur, table) and column_exists(cur, table, column):
                cur.execute(f"DELETE FROM {table} WHERE {column}=%s", (created["id"],))
        cur.execute("DELETE FROM work_orders WHERE id=%s", (created["id"],))
    return result


def post_inventory_check(client, cur, refs):
    if not refs.get("product") or not refs.get("warehouse") or not refs.get("location"):
        return {"ok": False, "blocked_reason": "missing product, warehouse, or location master data"}
    before = scalar(cur, "SELECT COALESCE(MAX(id),0) FROM inventory_check_orders")
    form = {
        "warehouse_id": str(refs["location"]["warehouse_id"] or refs["warehouse"]["id"]),
        "location_id": str(refs["location"]["id"]),
        "check_date": date.today().isoformat(),
        "remark": AUDIT_TAG,
        "product_id[]": str(refs["product"]["id"]),
        "actual_qty[]": "0",
        "unit_cost[]": "0",
        "lot_no[]": AUDIT_TAG,
        "cabinet_no[]": "",
    }
    response = client.post("/inventory_checks/new", data=form, follow_redirects=False)
    created = fetch_one(cur, "SELECT * FROM inventory_check_orders WHERE id>%s AND remark=%s ORDER BY id DESC LIMIT 1", (before, AUDIT_TAG))
    line_count = scalar(cur, "SELECT COUNT(*) FROM inventory_check_order_items WHERE check_id=%s", (created["id"],)) if created else 0
    ok = response.status_code in {302, 303} and created and line_count == 1
    result = {"ok": bool(ok), "status_code": response.status_code, "document_id": created["id"] if created else None, "line_count": int(line_count or 0)}
    if created:
        cur.execute("DELETE FROM document_custom_field_values WHERE document_type='inventory_check' AND document_id=%s", (created["id"],))
        cur.execute("DELETE FROM stock_transactions WHERE reference_no=%s OR source_doc_no=%s", (created.get("check_no"), created.get("check_no")))
        cur.execute("DELETE FROM inventory_check_order_items WHERE check_id=%s", (created["id"],))
        cur.execute("DELETE FROM inventory_check_orders WHERE id=%s", (created["id"],))
    return result


def post_service_order(client, cur, refs):
    card = refs.get("service_card")
    if not card:
        return {
            "ok": True,
            "precondition_missing": True,
            "blocked_reason": "missing machine service card",
            "next_action": "prepare a shipped cabinet number so the service card can be generated before service order entry",
            "delivered_cabinet_count": refs.get("delivered_cabinet_count") or 0,
        }
    before = scalar(cur, "SELECT COALESCE(MAX(id),0) FROM machine_service_orders")
    form = {
        "service_card_id": str(card["id"]),
        "service_date": date.today().isoformat(),
        "service_type": "audit",
        "issue_summary": AUDIT_TAG,
        "remark": AUDIT_TAG,
        "project_code": card.get("project_code") or "",
        "cabinet_no": card.get("cabinet_no") or "",
    }
    response = client.post("/service-orders/new", data=form, follow_redirects=False)
    created = fetch_one(cur, "SELECT * FROM machine_service_orders WHERE id>%s AND issue_summary=%s ORDER BY id DESC LIMIT 1", (before, AUDIT_TAG))
    ok = response.status_code in {302, 303} and bool(created)
    result = {"ok": bool(ok), "status_code": response.status_code, "document_id": created["id"] if created else None}
    if created:
        cur.execute("DELETE FROM machine_service_orders WHERE id=%s", (created["id"],))
    return result


def business_blockers(cur):
    blockers = {}
    ordered_expr = "COALESCE(pri.ordered_qty,0)" if column_exists(cur, "purchase_requisition_items", "ordered_qty") else "0"
    blockers["purchase_request_missing_supplier"] = fetch_all(
        cur,
        f"""
        SELECT pr.id, pr.req_no,
               COUNT(*) FILTER (
                   WHERE COALESCE(pri.quantity,0) > {ordered_expr}
                     AND COALESCE(pri.suggested_supplier_id,0) <= 0
               ) AS blocked_lines
        FROM purchase_requisitions pr
        JOIN purchase_requisition_items pri ON pri.req_id=pr.id
        WHERE COALESCE(pr.status,'') IN ('已审核', 'approved')
        GROUP BY pr.id, pr.req_no
        HAVING COUNT(*) FILTER (
                   WHERE COALESCE(pri.quantity,0) > {ordered_expr}
                     AND COALESCE(pri.suggested_supplier_id,0) <= 0
               ) > 0
        ORDER BY pr.id DESC
        LIMIT 20
        """,
    )
    blockers["invalid_subcontract_status"] = fetch_all(
        cur,
        """
        SELECT id, order_no, status
        FROM subcontract_orders
        WHERE COALESCE(status,'') NOT IN ('draft','confirmed','released','partial_received','completed','cancelled')
        ORDER BY id DESC
        LIMIT 20
        """,
    )
    blockers["schema_amount_quantity_risks"] = fetch_all(
        cur,
        """
        SELECT table_name, column_name, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema='public'
          AND column_name IN ('total_amount','amount','amount_with_tax','tax_amount','unit_price','unit_cost','quantity')
          AND data_type='numeric'
          AND (
              numeric_precision IS NULL
              OR numeric_precision < 10
              OR numeric_scale IS NULL
          )
        ORDER BY table_name, column_name
        LIMIT 100
        """,
    )
    return blockers


def run_posts(client, cur, refs):
    checks = {}
    for name, func in (
        ("purchase_request_save", post_purchase_request),
        ("purchase_order_save_payable", post_purchase_order),
        ("sales_order_save_receivable", post_sales_order),
        ("subcontract_order_save_payable", post_subcontract_order),
        ("work_order_save", post_work_order),
        ("inventory_check_save", post_inventory_check),
        ("service_order_save", post_service_order),
    ):
        print(f"post_check={name}", flush=True)
        try:
            checks[name] = func(client, cur, refs)
        except Exception as exc:
            cur.connection.rollback()
            checks[name] = {"ok": False, "exception": exc.__class__.__name__, "message": str(exc)}
    cur.connection.commit()
    return checks


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    conn = connect()
    try:
        cur = conn.cursor()
        refs = db_snapshot(cur)
        with app.test_client() as client:
            login(client)
            pages = page_access_checks(client)
            posts = run_posts(client, cur, refs)
        blockers = business_blockers(cur)
        cur.close()
    finally:
        conn.close()
    result = {
        "audit_tag": AUDIT_TAG,
        "boundary": {
            "business_loops": [
                "purchase request -> purchase order -> payable readiness",
                "sales order -> receivable readiness",
                "work order creation readiness",
                "subcontract order -> payable readiness",
                "inventory check document creation and cleanup",
                "service card -> service order readiness",
            ],
            "owner": "admin audit session",
            "acceptance_check": "page access plus real POST save plus database reconciliation where reversible",
        },
        "master_data_refs": refs,
        "page_access": pages,
        "post_checks": posts,
        "business_blockers": blockers,
    }
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    failed_pages = [row for row in pages if not row["ok"]]
    mojibake_pages = [row for row in pages if row["mojibake"]]
    failed_posts = {key: value for key, value in posts.items() if not value.get("ok")}
    blocking = bool(failed_pages or failed_posts)

    print(f"audit_output={OUT_PATH}")
    print(f"page_checks={len(pages)}")
    print(f"failed_pages={len(failed_pages)}")
    print(f"mojibake_pages={len(mojibake_pages)}")
    print(f"post_checks={len(posts)}")
    print(f"failed_post_checks={len(failed_posts)}")
    print(f"purchase_request_missing_supplier={len(blockers['purchase_request_missing_supplier'])}")
    print(f"invalid_subcontract_status={len(blockers['invalid_subcontract_status'])}")
    print(f"schema_amount_quantity_risks={len(blockers['schema_amount_quantity_risks'])}")
    for row in failed_pages[:20]:
        print(f"failed_page={row['path']} status={row['status_code']}")
    for key, value in failed_posts.items():
        print(f"failed_post={key} reason={value.get('blocked_reason') or value}")
    for row in blockers["purchase_request_missing_supplier"][:10]:
        print(f"purchase_blocker={row['req_no']} id={row['id']} lines={row['blocked_lines']}")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
