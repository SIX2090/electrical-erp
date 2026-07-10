from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def require(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    return name, ok, detail


def main() -> int:
    route_text = read("routes/drawing_routes.py")
    registry_text = read("routes/registry.py")
    base_text = read("templates/base.html")
    permissions_text = read("services/pilot_permissions.py")
    list_text = read("templates/engineering_drawing_list.html")
    form_text = read("templates/engineering_drawing_form.html")
    detail_text = read("templates/engineering_drawing_detail.html")
    import_text = read("templates/engineering_drawing_import.html")
    confirmation_route_text = read("routes/engineering_confirmation_routes.py")
    confirmation_form_text = read("templates/engineering_technical_confirmation_form.html")
    classification_text = read("MENU_ROLLOUT_CLASSIFICATION.md")
    combined = "\n".join([route_text, list_text, form_text, detail_text, import_text])

    checks = [
        require("route_list", '"/engineering/drawings"' in route_text and "drawing_list" in route_text, "drawing list route exists"),
        require("route_entry", '"/engineering/drawings/new"' in route_text and "drawing_new" in route_text, "drawing entry route exists"),
        require("route_detail", '"/engineering/drawings/<int:drawing_id>"' in route_text and "drawing_detail" in route_text, "drawing detail route exists"),
        require("registered", "register_drawing_routes" in registry_text, "drawing routes are registered"),
        require("table_drawings", "CREATE TABLE IF NOT EXISTS engineering_drawings" in route_text, "drawing ledger table is created"),
        require("table_links", "CREATE TABLE IF NOT EXISTS engineering_drawing_links" in route_text, "business reference table is created"),
        require("table_change_logs", "CREATE TABLE IF NOT EXISTS engineering_drawing_change_logs" in route_text, "drawing change log table is created"),
        require("version_unique", "UNIQUE (drawing_no, version)" in route_text, "drawing number and version are unique together"),
        require("business_refs", all(token in route_text for token in ("product_id", "bom_id", "project_code", "cabinet_no")), "material/BOM/project/cabinet references are supported"),
        require("release_fields", all(token in route_text for token in ("effective_date", "obsolete_date", "release_no", "approved_by", "approval_date")), "release and lifecycle fields are tracked"),
        require("pagination_sort", all(token in route_text + list_text for token in ("per_page", "total_pages", "DRAWING_SORT_COLUMNS", "pagination")), "drawing list supports pagination and sorting"),
        require("csv_export", "engineering-drawings.csv" in route_text and "export=csv" in list_text, "drawing ledger can be exported as CSV"),
        require("csv_import", all(token in route_text + list_text + import_text for token in ("engineering_drawing_import", "engineering_drawing_import_template", "read_validated_csv_upload", "图纸台账导入", "导入")), "drawing ledger supports controlled CSV import and template"),
        require("status_actions", all(token in route_text for token in ("engineering_drawing_release", "engineering_drawing_mark_changing", "engineering_drawing_obsolete", "engineering_drawing_copy_version")), "release/change/obsolete/copy-version actions exist"),
        require("release_validation", all(token in route_text for token in ("_release_ready_errors", "发布失败", "同一图号已有其他已发布有效版本", "至少需要关联")), "release action validates controlled drawing readiness"),
        require("action_permission", all(token in route_text for token in ("_require_drawing_action", "_has_drawing_action", "当前账号没有图纸台账该操作权限")), "drawing actions have route-level permission checks"),
        require("csrf_forms", "csrf_token" in import_text and "csrf_token" in form_text and detail_text.count("csrf_token") >= 7, "drawing POST forms include CSRF tokens"),
        require("list_operation_menu", all(token in list_text for token in ("操作菜单", "到详情执行发布/变更/作废", "复制新版本", "维护业务引用")), "list page exposes status-aware operation menu without bypassing required action forms"),
        require("change_trace_ui", "变更记录" in detail_text and "change_logs" in detail_text, "detail page exposes change trace"),
        require("downstream_impact", all(token in route_text + detail_text for token in ("_downstream_rows", "_open_downstream_rows", "按图纸引用范围匹配", "未关闭下游引用")), "detail page exposes downstream impact and open replacement risk"),
        require("safe_file_location", all(token in route_text + detail_text for token in ("safe_file_url", "file_open_hint", "复制", "请在文件服务器/PDM中按受控路径打开")), "detail page handles file locations without arbitrary local file opening"),
        require("technical_confirmation_current_drawing", all(token in confirmation_route_text + confirmation_form_text for token in ("_resolve_current_released_drawing", "drawing_version", "data-drawing-version", "status='released'")), "technical confirmation resolves current released drawing version"),
        require("menu_visible", 'href="/engineering/drawings"' in base_text, "engineering navigation exposes drawing ledger"),
        require("pilot_permission", '"/engineering/drawings"' in permissions_text and '"engineering_drawing"' in permissions_text, "pilot tech permissions include drawing ledger"),
        require("page_classified", "/engineering/drawings" in classification_text and "CAD/PDM source files remain outside ERP" in classification_text, "page is classified with ERP/PDM boundary"),
        require("no_cad_editor", "在线编辑" not in combined and "CAD编辑" not in combined and "PDM替代" not in combined, "scope does not implement CAD/PDM editing"),
    ]

    failures = [item for item in checks if not item[1]]
    print("engineering_drawing_scope_audit=ok" if not failures else "engineering_drawing_scope_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
