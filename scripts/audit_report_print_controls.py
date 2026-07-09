from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("LOGIN_RATE_LIMIT", "1000")


REPORT_HINTS = (
    "/reports",
    "/finance/financial-statements",
    "/finance/inventory-cost",
)
SKIP_PREFIXES = ("/static/", "/api/")
REQUIRED_REPORT_ACTIONS = ("查询", "重置", "导出", "打印", "刷新")
FORBIDDEN_REPORT_ACTIONS = ("新增", "保存", "提交", "审核", "反审核", "作废", "过账", "反过账")
REQUIRED_TEMPLATE_LIST_ACTIONS = ("新增模板", "预览", "设计", "复制", "设默认", "启用", "停用")
REQUIRED_EDITOR_MARKERS = (
    "print-template-form",
    "grid_cells_json",
    "grid_styles_json",
    "grid_col_widths_json",
    "designer-toolstrip",
    "sheet-edit-cell",
    "contentEditable",
)


def login_admin(client) -> None:
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit_admin"
        session["role"] = "admin"


def collect_report_paths(app) -> list[str]:
    paths: set[str] = set()
    for rule in app.url_map.iter_rules():
        path = str(rule.rule)
        if "GET" not in rule.methods:
            continue
        if "<" in path:
            continue
        if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if any(hint in path for hint in REPORT_HINTS):
            paths.add(path)
    return sorted(paths)


def nav_blocks(body: str) -> list[str]:
    return re.findall(r"<nav class=\"document-menu-bar\".*?</nav>", body, flags=re.S)


def visible_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def require(checks: list[str], failures: list[str], name: str, ok: bool, detail: str = "") -> None:
    checks.append(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    if not ok:
        failures.append(f"{name}: {detail}")


def audit_reports(app, client, checks: list[str], failures: list[str]) -> None:
    paths = collect_report_paths(app)
    require(checks, failures, "report_route_count", len(paths) >= 150, f"count={len(paths)}")
    for path in paths:
        response = client.get(path)
        body = response.get_data(as_text=True)
        blocks = nav_blocks(body)
        text = visible_text(body)
        require(checks, failures, f"report_status:{path}", response.status_code == 200, f"status={response.status_code}")
        require(checks, failures, f"report_menu:{path}", bool(blocks), "document menu bar present")
        if path == "/reports":
            center_text = visible_text(blocks[-1] if blocks else body)
            require(checks, failures, "report_center_refresh", "刷新" in center_text, center_text[:120])
            require(checks, failures, "report_center_print", "打印" in center_text, center_text[:120])
            continue
        if "/reports" in path or "/inventory-cost" in path:
            report_block = next((block for block in blocks if "reportPrintMenuBtn" in block), blocks[-1] if blocks else "")
            block_text = visible_text(report_block)
            for action in REQUIRED_REPORT_ACTIONS:
                require(checks, failures, f"report_action:{path}:{action}", action in block_text or action in text, block_text[:120])
            for action in FORBIDDEN_REPORT_ACTIONS:
                require(checks, failures, f"report_forbidden:{path}:{action}", action not in block_text, block_text[:120])
            require(checks, failures, f"report_filter_form:{path}", "reportFilterForm" in body or "method=\"get\"" in body, "GET filter form")
            require(checks, failures, f"report_print_hook:{path}", "window.print()" in body, "print action wired")


def audit_print_templates(client, query_db, execute_db, checks: list[str], failures: list[str]) -> None:
    from routes.print_template_routes import DOCUMENT_TYPES, ensure_print_template_table

    ensure_print_template_table(execute_db)
    expected_types = [item[0] for item in DOCUMENT_TYPES]
    rows = query_db(
        """
        SELECT document_type, COUNT(*) AS total,
               SUM(CASE WHEN is_default AND status='enabled' THEN 1 ELSE 0 END) AS enabled_default_count
        FROM print_templates
        GROUP BY document_type
        """
    )
    by_type = {row["document_type"]: row for row in rows}
    for document_type in expected_types:
        row = by_type.get(document_type)
        require(checks, failures, f"template_seed:{document_type}", bool(row), f"row={row}")
        require(
            checks,
            failures,
            f"template_default_enabled:{document_type}",
            bool(row) and int(row.get("enabled_default_count") or 0) >= 1,
            f"row={row}",
        )

    list_response = client.get("/system/print-templates")
    list_body = list_response.get_data(as_text=True)
    require(checks, failures, "template_list_status", list_response.status_code == 200, f"status={list_response.status_code}")
    for action in REQUIRED_TEMPLATE_LIST_ACTIONS:
        ok = action in list_body or (action == "设默认" and "默认" in list_body)
        require(checks, failures, f"template_list_action:{action}", ok, action)

    template_rows = query_db(
        """
        SELECT id, template_code, document_type, layout_json
        FROM print_templates
        WHERE is_default=TRUE AND status='enabled'
        ORDER BY document_type, id
        """
    )
    checked_types = set()
    for row in template_rows:
        document_type = row["document_type"]
        if document_type in checked_types or document_type not in expected_types:
            continue
        checked_types.add(document_type)
        layout = row.get("layout_json") or {}
        require(checks, failures, f"template_layout:{document_type}", bool(layout.get("cells")), row["template_code"])
        edit_response = client.get(f"/system/print-templates/{row['id']}/edit")
        edit_body = edit_response.get_data(as_text=True)
        require(checks, failures, f"template_edit_status:{document_type}", edit_response.status_code == 200, f"id={row['id']}")
        for marker in REQUIRED_EDITOR_MARKERS:
            require(checks, failures, f"template_editor_marker:{document_type}:{marker}", marker in edit_body, marker)
        preview_response = client.get(f"/system/print-templates/{row['id']}/preview")
        preview_body = preview_response.get_data(as_text=True)
        require(
            checks,
            failures,
            f"template_preview:{document_type}",
            preview_response.status_code == 200 and "preview-grid" in preview_body and "window.print()" in preview_body,
            f"id={row['id']} status={preview_response.status_code}",
        )


def main() -> int:
    from app import create_app, get_db_config
    from services.app_runtime import create_db_helpers

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    _get_db, query_db, execute_db, _execute_and_return = create_db_helpers(app, get_db_config())
    checks: list[str] = []
    failures: list[str] = []

    client = app.test_client()
    login_admin(client)
    audit_reports(app, client, checks, failures)
    audit_print_templates(client, query_db, execute_db, checks, failures)

    print(f"report_print_controls={'failed' if failures else 'ok'}")
    for line in checks:
        print(line)
    for failure in failures:
        print(f"failure | {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
