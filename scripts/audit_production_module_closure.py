import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _env():
    os.environ.setdefault("PG_HOST", "127.0.0.1")
    os.environ.setdefault("PG_PORT", "5432")
    os.environ.setdefault("PG_DATABASE", "wms")
    os.environ.setdefault("PG_USER", "wms_user")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "production-module-closure-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")


def _check_page(client, path, markers, forbidden=()):
    response = client.get(path)
    body = response.get_data(as_text=True)
    check_body = body.split('<main class="main">', 1)[-1].split("</main>", 1)[0]
    checks = [(f"{path}:status", response.status_code == 200, response.status_code)]
    for marker in markers:
        checks.append((f"{path}:visible:{marker}", marker in check_body, "visible"))
    for marker in forbidden:
        checks.append((f"{path}:absent:{marker}", marker not in check_body, "absent"))
    dirty_markers = ("\ufffd", "???")
    checks.append((f"{path}:clean_text", not any(marker in check_body for marker in dirty_markers), "clean"))
    return checks, body


def _check_post_result(client, path, expected):
    response = client.post(path, data={}, follow_redirects=True)
    body = response.get_data(as_text=True)
    check_body = body.split('<main class="main">', 1)[-1].split("</main>", 1)[0]
    dirty_markers = ("\ufffd", "???")
    checks = [(f"{path}:post_status", response.status_code == 200, response.status_code)]
    checks.append((f"{path}:post_clean_text", not any(marker in check_body for marker in dirty_markers), "clean"))
    checks.append((f"{path}:post_visible:{expected}", expected in check_body, "visible"))
    return checks


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


def _fetch_audit_work_order():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT wo.id, wo.wo_no
                FROM work_orders wo
                JOIN wo_material_items mi ON mi.wo_id=wo.id
                WHERE (COALESCE(mi.required_qty,0) - COALESCE(mi.issued_qty,0) + COALESCE(mi.returned_qty,0)) > 0
                  AND COALESCE(wo.wo_no,'') NOT ILIKE 'SVC-%%'
                  AND COALESCE(wo.production_type,'') NOT ILIKE '%%service%%'
                  AND COALESCE(wo.production_type,'') NOT LIKE '%%售后%%'
                  AND COALESCE(wo.production_type,'') NOT LIKE '%%维修%%'
                  AND COALESCE(wo.status,'') NOT IN ('已关闭','已完工','已完成','已作废','已取消','closed','completed','void','cancelled','canceled')
                ORDER BY wo.id DESC
                LIMIT 1
                """
            )
            return cur.fetchone() or {}
    finally:
        conn.close()


def _fetch_returnable_work_order():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT wo.id, wo.wo_no
                FROM work_orders wo
                JOIN wo_material_items mi ON mi.wo_id=wo.id
                WHERE (COALESCE(mi.issued_qty,0) - COALESCE(mi.returned_qty,0)) > 0
                  AND COALESCE(wo.wo_no,'') NOT ILIKE 'SVC-%%'
                  AND COALESCE(wo.production_type,'') NOT ILIKE '%%service%%'
                  AND COALESCE(wo.production_type,'') NOT LIKE '%%售后%%'
                  AND COALESCE(wo.production_type,'') NOT LIKE '%%维修%%'
                  AND COALESCE(wo.status,'') NOT IN ('已关闭','已完工','已完成','已作废','已取消','closed','completed','void','cancelled','canceled')
                ORDER BY wo.id DESC
                LIMIT 1
                """
            )
            return cur.fetchone() or {}
    finally:
        conn.close()


def _fetch_latest_production_issue():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, doc_no
                FROM pick_lists
                WHERE doc_type='production_issue'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            return cur.fetchone() or {}
    finally:
        conn.close()


def main():
    _env()
    from app import create_app

    checks = []
    try:
        work_order = _fetch_audit_work_order()
    except Exception as exc:
        work_order = {"_error": str(exc)}
    try:
        returnable_work_order = _fetch_returnable_work_order()
    except Exception as exc:
        returnable_work_order = {"_error": str(exc)}
    try:
        latest_issue = _fetch_latest_production_issue()
    except Exception as exc:
        latest_issue = {"_error": str(exc)}
    checks.append(("sample_production_work_order_exists", bool(work_order.get("id")), work_order.get("wo_no") or work_order.get("_error") or "no eligible source"))

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "admin"

        for path, markers in (
            ("/production-issues", ("生产领料单列表", "状态", "新增")),
            ("/production-returns", ("生产退料单列表", "状态", "新增")),
            ("/production/operation-reports", ("工序报工", "状态")),
            ("/production-issues/new", ("新增生产领料单", "来源生产工单", "用料明细", "本次领料", "物料名称")),
            ("/production-returns/new", ("新增生产退料单", "来源生产工单", "用料明细", "本次退料", "只显示已领未退")),
            ("/production/operation-reports/new", ("新增", "工序")),
        ):
            page_checks, _ = _check_page(client, path, markers, forbidden=("SVC-WO",))
            checks.extend(page_checks)

        if work_order.get("id"):
            page_checks, body = _check_page(
                client,
                f"/production-issues/new?work_order_id={work_order['id']}",
                ("新增生产领料单", work_order["wo_no"], "物料编码", "物料名称", "可用数量", "保存草稿", "保存并过账"),
                forbidden=("SVC-WO",),
            )
            checks.extend(page_checks)
            checks.append(("production_issue_entry_has_quantity_inputs", 'name="quantity[]"' in body, "quantity grid"))
            checks.append(("production_issue_entry_has_source_line_ids", 'name="item_id[]"' in body, "source lines"))

        if returnable_work_order.get("id"):
            page_checks, body = _check_page(
                client,
                f"/production-returns/new?work_order_id={returnable_work_order['id']}",
                ("新增生产退料单", returnable_work_order["wo_no"], "物料编码", "物料名称", "已领", "已退", "可用数量", "本次退料", "保存并过账"),
                forbidden=("SVC-WO",),
            )
            checks.extend(page_checks)
            checks.append(("production_return_source_filtered_by_returnable_qty", "本次退料" in body and 'name="quantity[]"' in body, "returnable quantity grid"))
            checks.append(("production_return_entry_has_source_line_ids", 'name="item_id[]"' in body, "source lines"))

        if latest_issue.get("id"):
            page_checks, _ = _check_page(
                client,
                f"/production-issues/{latest_issue['id']}",
                ("生产领料单", "提交", "提交并过账", "作废", "物料编码", "物料名称", "库存流水"),
                forbidden=("SVC-WO", "draft"),
            )
            checks.extend(page_checks)

        for post_path in (
            "/work-orders/999999999/issue-materials",
            "/work-orders/999999999/return-materials",
            "/work-orders/999999999/material-requirements",
            "/work-orders/999999999/generate-bom-material-requirements",
            "/work-orders/999999999/extra-material",
            "/work-orders/999999999/complete",
            "/work-orders/999999999/quality",
        ):
            checks.extend(_check_post_result(client, post_path, "工单不存在"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("production_module_closure_audit=ok" if not failures else "production_module_closure_audit=failed")
    print(f"checked_items={len(checks)}")
    if work_order.get("id"):
        print(f"sample_work_order={work_order.get('wo_no')} id={work_order.get('id')}")
    if returnable_work_order.get("id"):
        print(f"sample_returnable_work_order={returnable_work_order.get('wo_no')} id={returnable_work_order.get('id')}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
