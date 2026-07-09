"""Generic data list route helpers: POST rejection and detail-owned path guards for list pages."""
from collections.abc import Callable, Sequence
from typing import Any

from flask import jsonify, redirect, render_template, request, session


FORMAL_DETAIL_OWNED_PATHS = {
    "/production-completions",
    "/production-enhance/quality-inspections",
}


def data_route_post_rejected_response():
    message = "\u6b64\u5217\u8868\u9875\u4e0d\u63a5\u6536\u901a\u7528\u63d0\u4ea4\uff0c\u8bf7\u4f7f\u7528\u5bf9\u5e94\u4e1a\u52a1\u5355\u636e\u5165\u53e3\u3002"
    return jsonify({"ok": False, "error": message}), 400


def data_route_unavailable_subtitle(title, subtitle):
    message = "\u5f53\u524d\u6570\u636e\u5e93\u672a\u521d\u59cb\u5316\u5bf9\u5e94\u5355\u636e\u8868\uff0c\u8bf7\u5148\u5b8c\u6210\u6a21\u5757\u5efa\u8868\u548c\u4e1a\u52a1\u521d\u59cb\u5316\u3002"
    return f"{subtitle or title}\uff1b{message}"


def data_route_detail_title(title):
    return f"{title}\u8be6\u60c5"


def _system_option_int(safe_one, key, default, minimum=None, maximum=None):
    try:
        row = safe_one("SELECT option_value FROM system_options WHERE option_key=%s LIMIT 1", (key,))
    except Exception:
        row = None
    if not row:
        try:
            row = safe_one("SELECT value AS option_value FROM system_options WHERE key=%s LIMIT 1", (key,))
        except Exception:
            row = None
    try:
        value = int((row or {}).get("option_value") or default)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def list_operator_subtitle(path, subtitle, detail_base):
    if path == "/operation_logs":
        return "\u7cfb\u7edf\u5ba1\u8ba1\u65e5\u5fd7\uff1b\u53ea\u5141\u8bb8\u7ba1\u7406\u5458\u6309\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u6e05\u7406\uff0c\u4e0d\u5f71\u54cd\u4e1a\u52a1\u5355\u636e\u548c\u8d22\u52a1\u6570\u636e\u3002"
    if path in {"/assembly-orders", "/disassembly-orders"}:
        note = "\u5217\u8868\u56fa\u5b9a\u663e\u793a\u72b6\u6001\u548c\u8be6\u60c5\u5165\u53e3\uff0c\u4fbf\u4e8e\u5e93\u7ba1\u8ddf\u8fdb\u8fc7\u8d26\u3001\u5173\u95ed\u548c\u8ffd\u6eaf\u3002"
        text = subtitle or ""
        return text if note in text else f"{text}\uff1b{note}" if text else note
    if path in {"/inventory/inbound", "/inventory/outbound"}:
        note = "\u672c\u5355\u636e\u5f55\u5165\u9700\u7ef4\u62a4\u5355\u636e\u4fe1\u606f\u3001\u6765\u6e90\u5355\u636e\u3001\u9879\u76ee\u53f7\u3001\u673a\u53f7\u3001\u7269\u6599\u660e\u7ec6\u3001\u5e93\u5b58\u6210\u672c\u5355\u4ef7\u548c\u6279\u53f7\uff1b\u65b0\u589e\u8bf7\u4ece\u5bf9\u5e94\u5355\u636e\u5f55\u5165\u5165\u53e3\u8fdb\u5165\u3002"
        text = subtitle or ""
        return text if note in text else f"{text}\uff1b{note}" if text else note
    return subtitle


def register_report_route(
    app,
    path: str,
    title: str,
    table: str | None,
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]],
    endpoint: Callable[[str, str], str],
    select_rows: Callable[..., tuple[Sequence[dict[str, Any]], Sequence[dict[str, Any]]]],
    special_report_renderers: dict[str, Callable[[], Any]] | None = None,
) -> None:
    route_endpoint = endpoint("report", path)

    @app.get(path, endpoint=route_endpoint)
    @login_required
    def report_page(path=path, title=title, table=table):
        special_renderer = (special_report_renderers or {}).get(path)
        if special_renderer is not None:
            return special_renderer()
        rows, columns = select_rows(table, limit=100) if table else ([], [])
        return render_template(
            "simple_list.html",
            title=title,
            subtitle="\u901a\u7528\u67e5\u8be2\u9875\uff0c\u6309\u6570\u636e\u8868\u5b57\u6bb5\u5c55\u793a\u6700\u8fd1\u8bb0\u5f55\u3002",
            rows=rows,
            columns=columns,
        )


def register_data_route(
    app,
    path: str,
    title: str,
    table: str,
    preferred: Sequence[str] | None,
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]],
    endpoint: Callable[[str, str], str],
    render_special_list: Callable[[str, str, str], Any],
    select_rows: Callable[..., tuple[Sequence[dict[str, Any]], Sequence[dict[str, Any]]]],
    table_columns: Callable[[str], Sequence[dict[str, Any]]],
    apply_document_list_context: Callable[..., tuple[Any, Any, Any, Any, Any]],
    has_document_list_config: Callable[[str], bool],
    render_special_detail: Callable[[str, int, str, str], Any],
    safe_one: Callable[..., dict[str, Any] | None],
    document_list_title: Callable[[str, str], str],
    unavailable_subtitle: Callable[[str, str | None], str],
    detail_title: Callable[[str], str],
    post_rejected_response: Callable[[], Any],
    execute_db: Callable[..., Any] | None = None,
    log_action: Callable[..., Any] | None = None,
    detail: bool = True,
    methods: Sequence[str] = ("GET", "POST"),
) -> None:
    route_endpoint = endpoint("data", path)

    @app.route(path, methods=list(methods), endpoint=route_endpoint)
    @login_required
    def data_page(path=path, title=title, table=table, preferred=preferred, detail=detail):
        if path in {"/inventory/inbound", "/inventory/outbound"} and request.args.get("return_type"):
            special_page = render_special_list(table, path, title)
            if special_page is not None:
                return special_page
        if request.method == "POST":
            return post_rejected_response()
        special_page = render_special_list(table, path, title)
        if special_page is not None:
            return special_page
        table_column_names = [c["column_name"] for c in table_columns(table)]
        rows, columns = select_rows(table, preferred)
        if table == "inventory_assembly_orders" and path == "/assembly-orders":
            rows = [row for row in rows if row.get("doc_type") == "assembly"]
        elif table == "inventory_assembly_orders" and path == "/disassembly-orders":
            rows = [row for row in rows if row.get("doc_type") == "disassembly"]
        detail_base = path.rstrip("/") if detail and "id" in table_column_names else None
        list_context = apply_document_list_context(
            path, rows, columns, detail_base
        )
        bulk_actions = None
        if len(list_context) == 6:
            rows, columns, detail_base, add_url, subtitle, bulk_actions = list_context
        else:
            rows, columns, detail_base, add_url, subtitle = list_context
        if has_document_list_config(path):
            add_url = None
        if table_column_names:
            available_columns = set(table_column_names) | {
                "status", "next_step", "owner_role", "issue_state", "production_stage",
                "delivery_warning", "data_source", "schedule_compare", "blocked_reason",
                "work_center_display", "source_work_order", "planned_date_range",
                "dispatch_action", "report_action", "responsible_person", "dispatch_status",
            }
            columns = [column for column in columns if column.get("key") in available_columns]
        if not table_column_names and has_document_list_config(path):
            subtitle = unavailable_subtitle(title, subtitle)
        subtitle = list_operator_subtitle(path, subtitle, detail_base)
        if path == "/operation_logs":
            detail_base = None
            bulk_actions = {
                "select": True,
                "delete_url": "/operation_logs/delete",
                "clear_filtered": True,
            }
        return render_template(
            "simple_list.html",
            title=document_list_title(path, title),
            subtitle=subtitle,
            rows=rows,
            columns=columns,
            detail_base=detail_base,
            add_url=add_url,
            bulk_actions=bulk_actions,
        )

    if path == "/operation_logs":
        @app.post("/operation_logs/delete", endpoint=endpoint("delete", path))
        @login_required
        def operation_logs_delete():
            if session.get("role") not in {"admin", "manager"}:
                return jsonify({"ok": False, "msg": "\u6ca1\u6709\u6743\u9650\u6e05\u7406\u64cd\u4f5c\u65e5\u5fd7"}), 403
            if execute_db is None:
                return jsonify({"ok": False, "msg": "\u7cfb\u7edf\u672a\u914d\u7f6e\u65e5\u5fd7\u6e05\u7406\u6267\u884c\u5668"}), 500
            data = request.get_json(silent=True) or {}
            mode = str(data.get("mode") or "selected").strip()
            ids = []
            for value in data.get("ids") or []:
                try:
                    item_id = int(value)
                except (TypeError, ValueError):
                    continue
                if item_id > 0:
                    ids.append(item_id)
            ids = sorted(set(ids))
            if mode == "filtered":
                keyword = str(data.get("keyword") or "").strip()
                if keyword:
                    pattern = f"%{keyword}%"
                    affected_row = safe_one(
                        """
                        SELECT COUNT(*) AS count
                        FROM operation_logs
                        WHERE username ILIKE %s OR action ILIKE %s OR target ILIKE %s OR remark ILIKE %s
                           OR request_path ILIKE %s OR request_method ILIKE %s OR remote_addr ILIKE %s
                        """,
                        (pattern, pattern, pattern, pattern, pattern, pattern, pattern),
                    )
                    affected = int((affected_row or {}).get("count") or 0)
                    execute_db(
                        """
                        DELETE FROM operation_logs
                        WHERE username ILIKE %s OR action ILIKE %s OR target ILIKE %s OR remark ILIKE %s
                           OR request_path ILIKE %s OR request_method ILIKE %s OR remote_addr ILIKE %s
                        """,
                        (pattern, pattern, pattern, pattern, pattern, pattern, pattern),
                    )
                    if log_action:
                        log_action("\u5220\u9664\u64cd\u4f5c\u65e5\u5fd7", "filtered", f"keyword={keyword[:80]} deleted={affected}")
                else:
                    retention_days = _system_option_int(safe_one, "operation_log_retention_days", 180, 30, 3650)
                    affected_row = safe_one(
                        "SELECT COUNT(*) AS count FROM operation_logs WHERE created_at < NOW() - (%s::int * INTERVAL '1 day')",
                        (retention_days,),
                    )
                    affected = int((affected_row or {}).get("count") or 0)
                    execute_db(
                        "DELETE FROM operation_logs WHERE created_at < NOW() - (%s::int * INTERVAL '1 day')",
                        (retention_days,),
                    )
                    if log_action:
                        log_action("\u5220\u9664\u64cd\u4f5c\u65e5\u5fd7", "retention", f"retention_days={retention_days} deleted={affected}")
                    return jsonify({"ok": True, "msg": f"已按 {retention_days} 天保留策略清理 {affected or 0} 条操作日志", "deleted": affected or 0})
                return jsonify({"ok": True, "msg": f"\u5df2\u6e05\u7406 {affected or 0} \u6761\u64cd\u4f5c\u65e5\u5fd7", "deleted": affected or 0})
            if not ids:
                return jsonify({"ok": False, "msg": "\u8bf7\u5148\u9009\u62e9\u8981\u5220\u9664\u7684\u65e5\u5fd7"}), 400
            affected_row = safe_one("SELECT COUNT(*) AS count FROM operation_logs WHERE id = ANY(%s)", (ids,))
            affected = int((affected_row or {}).get("count") or 0)
            execute_db("DELETE FROM operation_logs WHERE id = ANY(%s)", (ids,))
            if log_action:
                log_action("\u5220\u9664\u64cd\u4f5c\u65e5\u5fd7", ",".join(str(item) for item in ids[:20]), f"deleted={affected}")
            return jsonify({"ok": True, "msg": f"\u5df2\u5220\u9664 {affected or 0} \u6761\u64cd\u4f5c\u65e5\u5fd7", "deleted": affected or 0})

    if detail and path not in FORMAL_DETAIL_OWNED_PATHS:
        detail_endpoint = endpoint("detail", path)

        @app.get(path.rstrip("/") + "/<int:id>", endpoint=detail_endpoint)
        @login_required
        def data_detail(id, title=title, table=table, path=path):
            special_detail = render_special_detail(table, id, title, path)
            if special_detail is not None:
                return special_detail
            row = safe_one(f"SELECT * FROM {table} WHERE id=%s", (id,))
            return render_template(
                "simple_detail.html",
                title=detail_title(title),
                row=row,
                back_url=path,
                labels={},
                table_name=table,
            )


def register_data_routes(
    app,
    routes: Sequence[tuple[str, str, str, Sequence[str] | None]],
    report_page_redirects: set[str] | dict[str, str],
    has_table: Callable[[str], bool],
    **kwargs: Any,
) -> None:
    special_report_renderers = kwargs.pop("special_report_renderers", None)
    for path, title, table, preferred in routes:
        if path == "/users":
            continue
        if path in {"/inventory/inbound", "/inventory/outbound"}:
            continue
        if path in report_page_redirects:
            continue
        if has_table(table) or kwargs["has_document_list_config"](path):
            register_data_route(app, path, title, table, preferred, **kwargs)
        else:
            register_report_route(
                app,
                path,
                title,
                None,
                kwargs["login_required"],
                kwargs["endpoint"],
                kwargs["select_rows"],
                special_report_renderers,
            )


def register_report_routes(
    app,
    routes: Sequence[tuple[str, str, str]],
    report_page_redirects: set[str] | dict[str, str],
    has_table: Callable[[str], bool],
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]],
    endpoint: Callable[[str, str], str],
    select_rows: Callable[..., tuple[Sequence[dict[str, Any]], Sequence[dict[str, Any]]]],
    special_report_renderers: dict[str, Callable[[], Any]] | None = None,
) -> None:
    for path, title, table in routes:
        if path in report_page_redirects:
            continue
        register_report_route(
            app,
            path,
            title,
            table if has_table(table) else None,
            login_required,
            endpoint,
            select_rows,
            special_report_renderers,
        )


def _register_redirect(
    app,
    path: str,
    target: str,
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]],
    endpoint: Callable[[str, str], str],
) -> None:
    route_endpoint = endpoint("redirect", path)

    @app.route(path, methods=["GET", "POST"], endpoint=route_endpoint)
    @login_required
    def redirect_alias(target=target):
        return redirect(target)


def register_redirect_routes(
    app,
    redirects: dict[str, str],
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]],
    endpoint: Callable[[str, str], str],
) -> None:
    for path, target in redirects.items():
        _register_redirect(app, path, target, login_required, endpoint)
