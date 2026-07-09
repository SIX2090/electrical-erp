from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WTF_CSRF_ENABLED", "0")


def require(checks: list[str], failures: list[str], name: str, ok: bool, detail: str = "") -> None:
    status = "ok" if ok else "failed"
    checks.append(f"{status} | {name} | {detail}")
    if not ok:
        failures.append(f"{name}: {detail}")


def login_admin(client) -> None:
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit_admin"
        session["role"] = "admin"


def main() -> int:
    from app import create_app, get_db_config
    from services.app_runtime import create_db_helpers

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    _get_db, query_db, execute_db, _execute_and_return = create_db_helpers(app, get_db_config())
    checks: list[str] = []
    failures: list[str] = []
    client = app.test_client()
    login_admin(client)

    base_template = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    require(checks, failures, "menu_entry", "/system/print-templates" in base_template, "system menu exposes print templates")

    list_response = client.get("/system/print-templates")
    require(checks, failures, "list_page", list_response.status_code == 200, f"status={list_response.status_code}")
    body = list_response.get_data(as_text=True)
    require(checks, failures, "seed_templates", "PT-PURCHASE-ORDER-STD" in body, "purchase order seed template visible")

    code = f"PT-CHECK-{int(time.time())}"
    copy_id = None
    template_id = None
    execute_db("DELETE FROM print_templates WHERE template_code LIKE %s", ("PT-CHECK-%",))
    create_response = client.post(
        "/system/print-templates/new",
        data={
            "template_code": code,
            "template_name": "打印模板检查件",
            "document_type": "purchase_order",
            "category": "测试",
            "print_type": "单据打印",
            "status": "enabled",
            "is_default": "",
            "paper": "A4",
            "orientation": "portrait",
            "grid_rows": "18",
            "grid_cols": "10",
            "grid_cells_json": "{}",
            "grid_styles_json": "{}",
            "grid_col_widths_json": "{}",
            "content_html": "<div class='print-sheet-title'>打印模板检查件</div>",
            "remark": "runtime audit",
        },
        follow_redirects=False,
    )
    location = create_response.headers.get("Location", "")
    match = re.search(r"/system/print-templates/(\d+)/edit", location)
    require(checks, failures, "create_template", create_response.status_code in {302, 303} and bool(match), f"status={create_response.status_code} location={location}")
    if not match:
        print("print_template_feature=failed")
        for line in checks:
            print(line)
        for failure in failures:
            print(f"failure | {failure}")
        return 1

    template_id = match.group(1)
    edit_get = client.get(f"/system/print-templates/{template_id}/edit")
    require(checks, failures, "edit_page", edit_get.status_code == 200 and code in edit_get.get_data(as_text=True), f"status={edit_get.status_code}")

    edit_post = client.post(
        f"/system/print-templates/{template_id}/edit",
        data={
            "template_code": code,
            "template_name": "打印模板检查件-已保存",
            "document_type": "purchase_order",
            "category": "测试",
            "print_type": "套打",
            "status": "enabled",
            "is_default": "1",
            "paper": "A4",
            "orientation": "portrait",
            "grid_rows": "22",
            "grid_cols": "12",
            "grid_cells_json": '{"1-1":"检查表头","2-1":"{{ 单据编号 }}","2-2":"{{ 项目号 }}"}',
            "grid_styles_json": '{"1-1":{"fontWeight":"700","textAlign":"center","fontSize":"12","color":"#111827","border":true,"merged":true,"colSpan":2},"1-2":{"covered":true,"mergeAnchor":"1-1"}}',
            "grid_col_widths_json": '{"1":140,"2":120}',
            "content_html": "<div class='print-sheet-title'>打印模板检查件-已保存</div>",
            "remark": "runtime audit saved",
        },
        follow_redirects=False,
    )
    require(checks, failures, "save_template", edit_post.status_code in {302, 303}, f"status={edit_post.status_code}")

    preview = client.get(f"/system/print-templates/{template_id}/preview")
    preview_body = preview.get_data(as_text=True)
    require(checks, failures, "preview_page", preview.status_code == 200 and "检查表头" in preview_body, f"status={preview.status_code}")
    require(checks, failures, "preview_grid_renderer", "preview-grid" in preview_body and "preview-cell" in preview_body, "preview uses designer grid renderer")
    require(checks, failures, "preview_style", "font-weight:700" in preview_body and "text-align:center" in preview_body, "cell style persisted")
    require(checks, failures, "preview_border", "border:1px solid #111827" in preview_body, "border style normalized")
    require(checks, failures, "preview_col_width", "minmax(0,140fr)" in preview_body, "column width persisted")
    require(checks, failures, "preview_merge_cell", "grid-column:1 / span 2" in preview_body and 'mergeAnchor' not in preview_body, "merged cells render and covered cells are skipped")

    copy_response = client.post(f"/system/print-templates/{template_id}/copy", follow_redirects=False)
    copy_location = copy_response.headers.get("Location", "")
    copy_match = re.search(r"/system/print-templates/(\d+)/edit", copy_location)
    require(checks, failures, "copy_template", copy_response.status_code in {302, 303} and bool(copy_match), f"status={copy_response.status_code} location={copy_location}")
    if copy_match:
        copy_id = copy_match.group(1)
        copied = query_db("SELECT template_code, template_name, is_default, status FROM print_templates WHERE id=%s", (copy_id,), one=True)
        require(
            checks,
            failures,
            "copy_properties",
            bool(copied) and copied["template_code"].startswith(f"{code}-COPY") and not copied["is_default"] and copied["status"] == "enabled",
            f"copied={copied}",
        )
        copy_edit = client.get(f"/system/print-templates/{copy_id}/edit")
        copy_edit_body = copy_edit.get_data(as_text=True)
        require(
            checks,
            failures,
            "copy_grid_layout",
            copy_edit.status_code == 200 and "物料编码" in copy_edit_body and "{{ 单据编号 }}" in copy_edit_body,
            f"status={copy_edit.status_code}",
        )
        require(
            checks,
            failures,
            "designer_html_collapsed",
            'id="template-html-open"' in copy_edit_body and "grid_col_widths_json" in copy_edit_body,
            "template html panel can be toggled and column widths are posted",
        )
        set_default = client.post(f"/system/print-templates/{copy_id}/set-default", follow_redirects=False)
        require(checks, failures, "set_default", set_default.status_code in {302, 303}, f"status={set_default.status_code}")
        copied_default = query_db("SELECT is_default, status FROM print_templates WHERE id=%s", (copy_id,), one=True)
        require(
            checks,
            failures,
            "set_default_properties",
            bool(copied_default) and copied_default["is_default"] and copied_default["status"] == "enabled",
            f"copied_default={copied_default}",
        )
        toggle_disabled = client.post(f"/system/print-templates/{copy_id}/toggle", follow_redirects=False)
        disabled = query_db("SELECT is_default, status FROM print_templates WHERE id=%s", (copy_id,), one=True)
        require(
            checks,
            failures,
            "toggle_disable",
            toggle_disabled.status_code in {302, 303} and bool(disabled) and not disabled["is_default"] and disabled["status"] == "disabled",
            f"status={toggle_disabled.status_code} disabled={disabled}",
        )
        toggle_enabled = client.post(f"/system/print-templates/{copy_id}/toggle", follow_redirects=False)
        enabled = query_db("SELECT status FROM print_templates WHERE id=%s", (copy_id,), one=True)
        require(
            checks,
            failures,
            "toggle_enable",
            toggle_enabled.status_code in {302, 303} and bool(enabled) and enabled["status"] == "enabled",
            f"status={toggle_enabled.status_code} enabled={enabled}",
        )
        delete_copy = client.post(f"/system/print-templates/{copy_id}/delete", follow_redirects=False)
        deleted = query_db("SELECT id FROM print_templates WHERE id=%s", (copy_id,), one=True)
        require(
            checks,
            failures,
            "delete_copy",
            delete_copy.status_code in {302, 303} and deleted is None,
            f"status={delete_copy.status_code} deleted={deleted}",
        )
        copy_id = None

    delete_builtin = client.post("/system/print-templates/1/delete", follow_redirects=False)
    builtin_exists = query_db("SELECT id FROM print_templates WHERE id=1 AND template_code='PT-PURCHASE-ORDER-STD'", one=True)
    require(
        checks,
        failures,
        "protect_builtin_delete",
        delete_builtin.status_code in {302, 303} and bool(builtin_exists),
        f"status={delete_builtin.status_code} builtin_exists={builtin_exists}",
    )

    audit_list_response = client.get("/system/print-templates")
    audit_body = audit_list_response.get_data(as_text=True)
    require(checks, failures, "audit_category_hidden", "PT-AUDIT-" not in audit_body and "审计" not in audit_body, "operator list is not polluted by audit templates")

    execute_db("DELETE FROM print_templates WHERE template_code LIKE %s", ("PT-CHECK-%",))
    execute_db("UPDATE print_templates SET is_default=TRUE, status='enabled', updated_at=NOW() WHERE template_code='PT-PURCHASE-ORDER-STD'")

    print(f"print_template_feature={'failed' if failures else 'ok'}")
    for line in checks:
        print(line)
    for failure in failures:
        print(f"failure | {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
