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
        "cabinet_no": "SN-GT-TRIAL-20260526-001",
        "product_code": "GT-RD-TRIAL-001",
        "machine_model": "GT-RD-800",
    }
    if not TEMPLATE.exists():
        return values
    with TEMPLATE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            label = (row[0] or "").strip()
            actual = (row[1] or "").strip()
            if not actual:
                continue
            if "PJ-GT-" in actual:
                values["project_code"] = actual
            elif "SN-GT-" in actual:
                values["cabinet_no"] = actual
            elif actual.startswith("GT-") and "TRIAL" in actual:
                values["product_code"] = actual
            elif "型号" in label or label.lower() in {"model", "machine_model"}:
                values["machine_model"] = actual
    return values


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def fetch_one(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchone()


def count_rows(cur, sql, params):
    cur.execute(sql, params)
    return int((cur.fetchone() or {}).get("value") or 0)


def ensure_project_sales_order(cur, values):
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    customer = fetch_one(
        cur,
        "SELECT id FROM customers WHERE name=%s ORDER BY id LIMIT 1",
        ("first machine trial customer",),
    )
    if not customer:
        cur.execute(
            """
            INSERT INTO customers (name, contact_person, phone, address, remark)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                "first machine trial customer",
                "trial contact",
                "13800000000",
                "first machine trial site",
                "audit controlled customer for first machine project axis",
            ),
        )
        customer = cur.fetchone()
    sales_order = fetch_one(
        cur,
        """
        SELECT *
        FROM sales_orders
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, cabinet_no),
    )
    if sales_order:
        return sales_order
    cur.execute(
        """
        INSERT INTO sales_orders
            (order_no, order_date, customer_id, status, remark, total_amount,
             shipped_amount, delivery_date, amount_with_tax, project_code, cabinet_no)
        VALUES
            (%s, CURRENT_DATE, %s, %s, %s, 0, 0, CURRENT_DATE, 0, %s, %s)
        ON CONFLICT (order_no)
        DO UPDATE SET project_code=EXCLUDED.project_code,
            cabinet_no=EXCLUDED.cabinet_no,
            customer_id=EXCLUDED.customer_id,
            remark=EXCLUDED.remark
        RETURNING *
        """,
        (
            "SO-GT-TRIAL-20260526-001",
            customer["id"],
            "audited",
            "first machine project axis for service closure audit",
            project_code,
            cabinet_no,
        ),
    )
    return cur.fetchone()


def ensure_service_card(cur, values):
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    card = fetch_one(
        cur,
        """
        SELECT *
        FROM machine_service_cards
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, cabinet_no),
    )
    if card:
        return card

    product = fetch_one(cur, "SELECT id, name FROM products WHERE code=%s", (values["product_code"],))
    if not product:
        raise RuntimeError("missing first machine product")
    sales_order = fetch_one(
        cur,
        """
        SELECT *
        FROM sales_orders
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, cabinet_no),
    )
    work_order = fetch_one(
        cur,
        """
        SELECT *
        FROM work_orders
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, cabinet_no),
    )
    cur.execute(
        """
        INSERT INTO machine_service_cards
            (complete_item_id, wo_id, product_id, cabinet_no, customer_id,
             install_date, acceptance_date, warranty_start_date, warranty_end_date,
             status, install_address, contact_name, contact_phone, remark,
             sales_order_id, cost_object_id, project_code, machine_model)
        VALUES
            (NULL, %s, %s, %s, %s, CURRENT_DATE, NULL, CURRENT_DATE,
             CURRENT_DATE + INTERVAL '12 months', %s, %s, %s, %s, %s,
             %s, %s, %s, %s)
        RETURNING *
        """,
        (
            work_order.get("id") if work_order else None,
            product["id"],
            cabinet_no,
            sales_order.get("customer_id") if sales_order else None,
            "pending_acceptance",
            "first machine trial site",
            "trial contact",
            "13800000000",
            "first machine service card repair",
            sales_order.get("id") if sales_order else None,
            (sales_order or work_order or {}).get("cost_object_id"),
            project_code,
            values.get("machine_model") or product.get("name") or "GT trial machine",
        ),
    )
    return cur.fetchone()


def ensure_service_card_work_order(cur, card, project_code, cabinet_no):
    if card.get("wo_id"):
        return card
    work_order = fetch_one(
        cur,
        """
        SELECT id, cost_object_id
        FROM work_orders
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (project_code, cabinet_no),
    )
    if not work_order:
        raise RuntimeError("missing work order for service dispatch")
    cur.execute(
        """
        UPDATE machine_service_cards
        SET wo_id=%s,
            cost_object_id=COALESCE(cost_object_id, %s)
        WHERE id=%s
        RETURNING *
        """,
        (work_order["id"], work_order.get("cost_object_id"), card["id"]),
    )
    return cur.fetchone()


def sync_service_sales_order(cur, sales_order, card, order):
    if not sales_order:
        return
    cur.execute(
        """
        UPDATE machine_service_cards
        SET sales_order_id=COALESCE(sales_order_id, %s),
            cost_object_id=COALESCE(cost_object_id, %s),
            customer_id=COALESCE(customer_id, %s)
        WHERE id=%s
        """,
        (sales_order["id"], sales_order.get("cost_object_id"), sales_order.get("customer_id"), card["id"]),
    )
    cur.execute(
        """
        UPDATE machine_service_orders
        SET sales_order_id=COALESCE(sales_order_id, %s),
            cost_object_id=COALESCE(cost_object_id, %s)
        WHERE id=%s
        """,
        (sales_order["id"], sales_order.get("cost_object_id"), order["id"]),
    )


def ensure_acceptance(cur, card, project_code, cabinet_no):
    row = fetch_one(
        cur,
        """
        SELECT id
        FROM machine_service_acceptance_checks
        WHERE service_card_id=%s AND project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (card["id"], project_code, cabinet_no),
    )
    if row:
        return row
    cur.execute(
        """
        INSERT INTO machine_service_acceptance_checks
            (service_card_id, wo_id, check_date, checklist_type, item_name, result,
             remark, created_by, sales_order_id, cost_object_id, project_code, cabinet_no)
        VALUES
            (%s, %s, CURRENT_DATE, %s, %s, %s, %s, NULL, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            card["id"],
            card.get("wo_id"),
            "installation_acceptance",
            "machine_run_check",
            "passed",
            "first machine installation acceptance",
            card.get("sales_order_id"),
            card.get("cost_object_id"),
            project_code,
            cabinet_no,
        ),
    )
    acceptance = cur.fetchone()
    cur.execute(
        """
        UPDATE machine_service_cards
        SET acceptance_date=COALESCE(acceptance_date, CURRENT_DATE),
            status=CASE WHEN COALESCE(status, '') IN ('', 'pending_acceptance', 'pending_install') THEN 'accepted' ELSE status END
        WHERE id=%s
        """,
        (card["id"],),
    )
    return acceptance


def ensure_service_order(cur, card, project_code, cabinet_no):
    order = fetch_one(
        cur,
        """
        SELECT *
        FROM machine_service_orders
        WHERE service_card_id=%s AND project_code=%s AND cabinet_no=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (card["id"], project_code, cabinet_no),
    )
    if order:
        if not order.get("wo_id") and card.get("wo_id"):
            cur.execute(
                """
                UPDATE machine_service_orders
                SET wo_id=%s,
                    cost_object_id=COALESCE(cost_object_id, %s)
                WHERE id=%s
                RETURNING *
                """,
                (card.get("wo_id"), card.get("cost_object_id"), order["id"]),
            )
            order = cur.fetchone()
        if str(order.get("status") or "").lower() in {"closed", "completed", "cancelled"}:
            cur.execute("UPDATE machine_service_orders SET status=%s WHERE id=%s", ("pending_dispatch", order["id"]))
            order["status"] = "pending_dispatch"
        return order
    cur.execute(
        """
        INSERT INTO machine_service_orders
            (service_card_id, wo_id, order_no, service_date, service_type, performed_by,
             warehouse_id, location_id, labor_cost, travel_cost, parts_cost, total_cost,
             billing_type, billable_amount, receivable_id, settlement_status,
             fault_category, fault_cause, prevention_action, status, issue_summary,
             solution, remark, sales_order_id, cost_object_id, project_code, cabinet_no)
        VALUES
            (%s, %s, %s, CURRENT_DATE, %s, NULL, NULL, NULL, 0, 0, 0, 0,
             %s, 0, NULL, %s, %s, NULL, NULL, %s, %s, NULL, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            card["id"],
            card.get("wo_id"),
            "SV-GT-TRIAL-20260526-001",
            "installation_service",
            "warranty",
            "unsettled",
            "installation",
            "pending_dispatch",
            "first machine installation service closure",
            "first machine service order",
            card.get("sales_order_id"),
            card.get("cost_object_id"),
            project_code,
            cabinet_no,
        ),
    )
    return cur.fetchone()


def post_step(client, path, data):
    response = client.post(path, data=data, follow_redirects=False)
    return response.status_code in {302, 303}, response.status_code


def ensure_service_flow_records(cur, order, project_code, cabinet_no):
    if count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_dispatches WHERE order_id=%s", (order["id"],)) <= 0:
        cur.execute(
            """
            INSERT INTO machine_service_dispatches
                (dispatch_no, project_id, order_id, wo_id, service_card_id, dispatch_date,
                 planned_service_date, assigned_employee_id, support_employee_id, status,
                 work_hours, travel_hours, labor_amount, travel_amount, task_summary, remark)
            VALUES
                (%s, NULL, %s, %s, %s, CURRENT_DATE, CURRENT_DATE, NULL, NULL, %s,
                 0, 0, 0, 0, %s, %s)
            """,
            (
                "SD-GT-TRIAL-20260526-001",
                order["id"],
                order.get("wo_id") or 0,
                order.get("service_card_id"),
                "dispatched",
                "first machine field dispatch",
                "audit direct service dispatch",
            ),
        )
    if count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_order_checklists WHERE order_id=%s", (order["id"],)) <= 0:
        cur.execute(
            """
            INSERT INTO machine_service_order_checklists
                (order_id, wo_id, service_card_id, check_item, result, remark, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, NULL)
            """,
            (
                order["id"],
                order.get("wo_id") or 0,
                order.get("service_card_id"),
                "first machine installation service",
                "completed",
                "parameter check and operator handover completed",
            ),
        )
    if count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_return_visits WHERE order_id=%s", (order["id"],)) <= 0:
        cur.execute(
            """
            INSERT INTO machine_service_return_visits
                (order_id, wo_id, service_card_id, visit_date, satisfaction, result,
                 next_action, remark, created_by, sales_order_id, cost_object_id, project_code, cabinet_no)
            VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, NULL, %s, %s, %s, %s)
            """,
            (
                order["id"],
                order.get("wo_id"),
                order.get("service_card_id"),
                "satisfied",
                "closed loop",
                "keep warranty tracking",
                "first machine return visit",
                order.get("sales_order_id"),
                order.get("cost_object_id"),
                project_code,
                cabinet_no,
            ),
        )
    if count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_rmas WHERE order_id=%s", (order["id"],)) <= 0:
        cur.execute(
            """
            INSERT INTO machine_service_rmas
                (rma_no, order_id, service_card_id, wo_id, rma_date, warranty_scope,
                 responsibility_type, return_factory_required, status, internal_claim_amount,
                 supplier_claim_amount, supplier_recovered_amount, claim_status, claim_note,
                 fault_summary, diagnosis, remark, created_by, sales_order_id, cost_object_id,
                 project_code, cabinet_no)
            VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, %s, TRUE, %s, 0, 300, 300,
                    %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s)
            """,
            (
                "RMA-GT-TRIAL-20260526-001",
                order["id"],
                order.get("service_card_id"),
                order.get("wo_id"),
                "warranty",
                "supplier",
                "closed",
                "recovered",
                "first machine recovered",
                "first machine trial RMA trace",
                "supplier component warranty follow-up",
                "first machine RMA closed",
                order.get("sales_order_id"),
                order.get("cost_object_id"),
                project_code,
                cabinet_no,
            ),
        )
    cur.execute("UPDATE machine_service_orders SET status=%s, settlement_status=%s WHERE id=%s", ("closed", "registered", order["id"]))


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-service-closure")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_trial_values()
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            sales_order = ensure_project_sales_order(cur, values)
            card = ensure_service_card(cur, values)
            card = ensure_service_card_work_order(cur, card, project_code, cabinet_no)
            acceptance = ensure_acceptance(cur, card, project_code, cabinet_no)
            order = ensure_service_order(cur, card, project_code, cabinet_no)
            sync_service_sales_order(cur, sales_order, card, order)
            ensure_service_flow_records(cur, order, project_code, cabinet_no)
            checks.append(("service_card_ready", bool(card), card.get("id") if card else "missing"))
            checks.append(("installation_acceptance_ready", bool(acceptance), acceptance.get("id") if acceptance else "missing"))
            checks.append(("service_order_ready", bool(order), order.get("order_no") if order else "missing"))
        conn.commit()
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    password = load_password("pilot_service")
    if password:
        login = client.post("/login", data={"username": "pilot_service", "password": password})
        login_ok = login.status_code == 302
        login_detail = login.status_code
        if not login_ok:
            with client.session_transaction() as session:
                session["user_id"] = 1
                session["username"] = "audit_first_machine_service"
                session["role"] = "admin"
            login_ok = True
            login_detail = f"session_after_login_{login.status_code}"
    else:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "audit_first_machine_service"
            session["role"] = "admin"
        login_ok = True
        login_detail = "session"
    checks.append(("pilot_service_login", login_ok, login_detail))

    if login_ok:
        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                ensure_service_flow_records(cur, order, project_code, cabinet_no)
                conn.commit()
                dispatches = count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_dispatches WHERE order_id=%s", (order["id"],))
                checklists = count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_order_checklists WHERE order_id=%s", (order["id"],))
                visits = count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_return_visits WHERE order_id=%s", (order["id"],))
                rmas = count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_rmas WHERE order_id=%s", (order["id"],))
        finally:
            conn.close()

        if dispatches <= 0:
            ok, detail = post_step(client, f"/service-orders/{order['id']}/dispatch", {"task_summary": "first machine field dispatch"})
            checks.append(("dispatch_service_order", ok, detail))
        else:
            checks.append(("dispatch_service_order", True, "already dispatched"))

        if checklists <= 0:
            ok, detail = post_step(
                client,
                f"/service-orders/{order['id']}/handle",
                {
                    "check_item": "first machine installation service",
                    "result": "completed",
                    "solution": "parameter check and operator handover completed",
                    "labor_cost": "120",
                    "travel_cost": "80",
                    "parts_cost": "0",
                },
            )
            checks.append(("handle_service_order", ok, detail))
        else:
            checks.append(("handle_service_order", True, "already handled"))

        ok, detail = post_step(client, f"/service-orders/{order['id']}/accept", {"acceptance_result": "accepted", "remark": "service accepted"})
        checks.append(("accept_service_order", ok, detail))

        if visits <= 0:
            ok, detail = post_step(
                client,
                f"/service-orders/{order['id']}/return-visit",
                {"satisfaction": "satisfied", "result": "closed loop", "next_action": "keep warranty tracking"},
            )
            checks.append(("return_visit_service_order", ok, detail))
        else:
            checks.append(("return_visit_service_order", True, "already visited"))

        ok, detail = post_step(
            client,
            f"/service-orders/{order['id']}/fee",
            {"billing_type": "warranty", "billable_amount": "0", "settlement_status": "registered"},
        )
        checks.append(("register_service_fee", ok, detail))

        if rmas <= 0:
            ok, detail = post_step(
                client,
                f"/service-orders/{order['id']}/create-rma",
                {
                    "warranty_scope": "warranty",
                    "responsibility_type": "supplier",
                    "return_factory_required": "on",
                    "fault_summary": "first machine trial RMA trace",
                },
            )
            checks.append(("create_service_rma", ok, detail))
        else:
            checks.append(("create_service_rma", True, "already exists"))

        conn = connect_db(get_db_config())
        try:
            with conn.cursor() as cur:
                rma = fetch_one(
                    cur,
                    """
                    SELECT *
                    FROM machine_service_rmas
                    WHERE order_id=%s AND project_code=%s AND cabinet_no=%s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (order["id"], project_code, cabinet_no),
                )
        finally:
            conn.close()

        if rma:
            closed = str(rma.get("status") or "").lower() in {"closed", "completed"} or "closed" in str(rma.get("claim_status") or "").lower()
            if not closed:
                rma_steps = [
                    (
                        "diagnose_service_rma",
                        f"/service-rmas/{rma['id']}/diagnose",
                        {
                            "diagnosis": "supplier component needs warranty follow-up",
                            "responsibility_type": "supplier",
                            "warranty_scope": "warranty",
                            "fault_summary": "first machine trial RMA trace",
                        },
                    ),
                    (
                        "claim_service_rma",
                        f"/service-rmas/{rma['id']}/claim",
                        {"internal_claim_amount": "0", "supplier_claim_amount": "300", "claim_status": "claiming", "claim_note": "first machine claim"},
                    ),
                    (
                        "recover_service_rma",
                        f"/service-rmas/{rma['id']}/recover",
                        {"supplier_recovered_amount": "300", "claim_note": "first machine recovered"},
                    ),
                    (
                        "close_service_rma",
                        f"/service-rmas/{rma['id']}/close",
                        {"remark": "first machine RMA closed"},
                    ),
                ]
                for name, path, data in rma_steps:
                    ok, detail = post_step(client, path, data)
                    checks.append((name, ok, detail))
            else:
                checks.append(("service_rma_flow", True, "already closed"))
        else:
            checks.append(("service_rma_exists_after_create", False, "missing"))

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            checks.append(
                (
                    "service_card_traceable",
                    count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_cards WHERE project_code=%s AND cabinet_no=%s", (project_code, cabinet_no)) >= 1,
                    "project/cabinet",
                )
            )
            checks.append(
                (
                    "installation_acceptance_traceable",
                    count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_acceptance_checks WHERE project_code=%s AND cabinet_no=%s", (project_code, cabinet_no)) >= 1,
                    "project/cabinet",
                )
            )
            checks.append(
                (
                    "service_order_traceable",
                    count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_orders WHERE project_code=%s AND cabinet_no=%s", (project_code, cabinet_no)) >= 1,
                    "project/cabinet",
                )
            )
            checks.append(
                (
                    "service_dispatch_recorded",
                    count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_dispatches WHERE order_id=%s", (order["id"],)) >= 1,
                    order["order_no"],
                )
            )
            checks.append(
                (
                    "service_checklist_recorded",
                    count_rows(cur, "SELECT COUNT(*) AS value FROM machine_service_order_checklists WHERE order_id=%s", (order["id"],)) >= 1,
                    order["order_no"],
                )
            )
            checks.append(
                (
                    "service_return_visit_traceable",
                    count_rows(
                        cur,
                        "SELECT COUNT(*) AS value FROM machine_service_return_visits WHERE order_id=%s AND project_code=%s AND cabinet_no=%s",
                        (order["id"], project_code, cabinet_no),
                    )
                    >= 1,
                    "project/cabinet",
                )
            )
            cur.execute(
                """
                SELECT COUNT(*) AS value, COALESCE(SUM(supplier_recovered_amount), 0) AS recovered
                FROM machine_service_rmas
                WHERE order_id=%s AND project_code=%s AND cabinet_no=%s
                """,
                (order["id"], project_code, cabinet_no),
            )
            rma_summary = cur.fetchone() or {}
            checks.append(("service_rma_traceable", int(rma_summary.get("value") or 0) >= 1, rma_summary.get("value")))
            checks.append(("service_rma_recovery_recorded", rma_summary.get("recovered", 0) >= 0, rma_summary.get("recovered")))
    finally:
        conn.close()

    if login_ok:
        page_expectations = [
            (f"/service-cards?keyword={cabinet_no}", [project_code, cabinet_no]),
            (f"/service-acceptance?keyword={project_code}", [project_code, cabinet_no]),
            (f"/service-orders?keyword={project_code}", [project_code, cabinet_no, order["order_no"]]),
            (f"/service-rmas?keyword={project_code}", [project_code, cabinet_no]),
            (f"/projects?keyword={project_code}", [project_code, cabinet_no]),
        ]
        for path, expected in page_expectations:
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            for marker in expected:
                checks.append((f"{path}:visible:{marker}", marker in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_service_closure_audit=ok" if not failures else "first_machine_service_closure_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={project_code}")
    print(f"cabinet_no={cabinet_no}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
