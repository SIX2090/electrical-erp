"""Trace routes: forward and reverse traceability by project number and machine serial number."""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, session, url_for

from services.data_scope_service import get_data_scope, log_data_access, row_allowed, scope_has_rules
from services.trace_engine import (
    find_by_project,
    find_by_serial,
    find_downstream_recursive,
    find_upstream_recursive,
    get_trace_snapshot,
    list_trace_snapshots,
)
from services.trace_integrity_service import (
    DOC_TYPE_LABELS,
    backfill_trace_links,
    build_trace_graph,
    check_trace_integrity,
    get_findings,
    resolve_finding,
    save_findings,
    trace_completeness_score,
)

import logging

logger = logging.getLogger(__name__)


def _label(doc_type):
    if not doc_type:
        return "-"
    return DOC_TYPE_LABELS.get(doc_type, doc_type)


def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    execute_and_return = deps.get("execute_and_return")
    login_required = deps["login_required"]
    log_action = deps.get("log_action")

    _SCOPE_FIELD_MAP = {"project": "project_code", "serial": "serial_no"}

    def _current_scope():
        try:
            return get_data_scope(
                query_db,
                user_id=session.get("user_id"),
                role=session.get("role", "staff"),
                permission="view",
            )
        except Exception:
            return {"bypass": False, "rules": {}, "permission": "view"}

    def _scope_denied(row):
        scope = _current_scope()
        if not scope_has_rules(scope):
            return False
        return not row_allowed(scope, row, _SCOPE_FIELD_MAP)

    def _filter_by_scope(rows):
        scope = _current_scope()
        if not scope_has_rules(scope):
            return rows
        return [row for row in rows if row_allowed(scope, row, _SCOPE_FIELD_MAP)]

    def _log_view(resource_type, resource_id=None, reason=""):
        """P3-B5: 记录追溯路由访问日志，失败不影响业务流程。"""
        try:
            log_data_access(
                execute_db,
                user_id=session.get("user_id"),
                role=session.get("role", "staff"),
                resource_type=resource_type,
                resource_id=resource_id,
                action="view",
                allowed=True,
                reason=reason,
            )
        except Exception:
            logger.warning("Failed to create trace link", exc_info=True)

    @app.get("/trace", endpoint="trace_index")
    @login_required
    def trace_index():
        _log_view("trace_index", reason="追溯首页")
        project_code = (request.args.get("project_code") or "").strip()
        serial_no = (request.args.get("serial_no") or "").strip()
        doc_type = (request.args.get("doc_type") or "").strip()
        doc_id = (request.args.get("doc_id") or "").strip()

        if project_code:
            return redirect(url_for("trace_project", project_code=project_code))
        if serial_no:
            return redirect(url_for("trace_serial", serial_no=serial_no))
        if doc_type and doc_id:
            return redirect(url_for("trace_document", doc_type=doc_type, doc_id=doc_id))

        recent_findings = _filter_by_scope(get_findings(query_db, status="open")[:10])
        open_count = len(_filter_by_scope(get_findings(query_db, status="open")))
        score = trace_completeness_score(query_db)

        return render_template(
            "trace/index.html",
            recent_findings=recent_findings,
            open_count=open_count,
            score=score,
            doc_type_options=sorted(DOC_TYPE_LABELS.items()),
        )

    @app.get("/trace/project/<project_code>", endpoint="trace_project")
    @login_required
    def trace_project(project_code):
        project_code = project_code.strip()
        _log_view("trace_project", resource_id=project_code, reason="项目号追溯")
        if _scope_denied({"project_code": project_code}):
            abort(403)
        links = find_by_project(query_db, project_code, limit=500)
        score = trace_completeness_score(query_db, project_code=project_code)
        graph = {"nodes": [], "edges": [], "seed": None}
        if links:
            first = links[0]
            graph = build_trace_graph(
                query_db,
                first.get("source_doc_type") or first.get("target_doc_type"),
                first.get("source_doc_id") or first.get("target_doc_id"),
                depth=3,
            )
        return render_template(
            "trace/project_trace.html",
            project_code=project_code,
            links=links,
            score=score,
            graph=graph,
            label=_label,
        )

    @app.get("/trace/serial/<serial_no>", endpoint="trace_serial")
    @login_required
    def trace_serial(serial_no):
        serial_no = serial_no.strip()
        _log_view("trace_serial", resource_id=serial_no, reason="机号追溯")
        if _scope_denied({"serial_no": serial_no}):
            abort(403)
        links = find_by_serial(query_db, serial_no, limit=500)
        score = trace_completeness_score(query_db, serial_no=serial_no)
        graph = {"nodes": [], "edges": [], "seed": None}
        if links:
            first = links[0]
            graph = build_trace_graph(
                query_db,
                first.get("source_doc_type") or first.get("target_doc_type"),
                first.get("source_doc_id") or first.get("target_doc_id"),
                depth=3,
            )
        return render_template(
            "trace/serial_trace.html",
            serial_no=serial_no,
            links=links,
            score=score,
            graph=graph,
            label=_label,
        )

    @app.get("/trace/document/<doc_type>/<int:doc_id>", endpoint="trace_document")
    @login_required
    def trace_document(doc_type, doc_id):
        _log_view("trace_document", resource_id=f"{doc_type}:{doc_id}", reason="单据追溯")
        # B-2 enhancement: use recursive multi-level traversal so operators
        # see the full upstream/downstream chain, not just direct links.
        upstream = find_upstream_recursive(query_db, doc_type, doc_id, max_depth=5)
        downstream = find_downstream_recursive(query_db, doc_type, doc_id, max_depth=5)
        graph = build_trace_graph(query_db, doc_type, doc_id, depth=3)
        return render_template(
            "trace/document_trace.html",
            doc_type=doc_type,
            doc_id=doc_id,
            doc_label=_label(doc_type),
            upstream=upstream,
            downstream=downstream,
            graph=graph,
            label=_label,
        )

    @app.get("/trace/snapshots", endpoint="trace_snapshots")
    @login_required
    def trace_snapshots():
        """B-2: Trace snapshot visualization - list view."""
        _log_view("trace_snapshots", reason="追溯快照列表")
        doc_type = (request.args.get("doc_type") or "").strip() or None
        doc_id = request.args.get("doc_id", type=int) or None
        snapshots = list_trace_snapshots(query_db, doc_type=doc_type, doc_id=doc_id, limit=100)
        snapshots = _filter_by_scope(snapshots)
        return render_template(
            "trace/snapshots.html",
            snapshots=snapshots,
            filters={"doc_type": doc_type or "", "doc_id": doc_id or ""},
            label=_label,
        )

    @app.get("/trace/snapshots/<int:snapshot_id>", endpoint="trace_snapshot_detail")
    @login_required
    def trace_snapshot_detail(snapshot_id):
        """B-2: Trace snapshot visualization - detail view."""
        _log_view("trace_snapshot_detail", resource_id=snapshot_id, reason="追溯快照明细")
        snapshot = get_trace_snapshot(query_db, snapshot_id)
        if not snapshot:
            abort(404)
        if _scope_denied(snapshot):
            abort(403)
        return render_template(
            "trace/snapshot_detail.html",
            snapshot=snapshot,
            label=_label,
        )

    @app.get("/trace/integrity", endpoint="trace_integrity")
    @login_required
    def trace_integrity():
        _log_view("trace_integrity", reason="追溯完整性异常列表")
        status = (request.args.get("status") or "").strip() or None
        severity = (request.args.get("severity") or "").strip() or None
        findings = _filter_by_scope(get_findings(query_db, status=status, severity=severity))
        return render_template(
            "trace/integrity.html",
            findings=findings,
            filters={"status": status or "", "severity": severity or ""},
        )

    @app.post("/trace/integrity/<int:finding_id>/resolve", endpoint="trace_integrity_resolve")
    @login_required
    def trace_integrity_resolve(finding_id):
        resolve_finding(query_db, execute_db, finding_id)
        if log_action:
            log_action("解决追溯完整性异常", f"finding_id={finding_id}", "")
        return redirect(url_for("trace_integrity"))

    @app.post("/trace/integrity/scan", endpoint="trace_integrity_scan")
    @login_required
    def trace_integrity_scan():
        findings = check_trace_integrity(query_db)
        inserted = save_findings(query_db, execute_db, findings)
        if log_action:
            log_action("追溯完整性扫描", f"inserted={inserted}", "")
        return redirect(url_for("trace_integrity"))

    @app.post("/trace/integrity/backfill", endpoint="trace_integrity_backfill")
    @login_required
    def trace_integrity_backfill():
        """P4-B2: 执行追溯回填（缺失 trace_links + 缺失 project_code/serial_no）。"""
        _log_view("trace_backfill", reason="执行追溯回填")
        result = backfill_trace_links(
            query_db,
            execute_db,
            execute_and_return=execute_and_return,
            created_by=session.get("user_id"),
        )
        if log_action:
            log_action(
                "追溯回填执行",
                f"links={result.get('links_inserted')}",
                f"回填链接 {result.get('links_inserted')}，"
                f"回填字段 {result.get('fields_backfilled')}",
            )
        flash(
            f"追溯回填完成：新建追溯链接 {result.get('links_inserted')} 条，"
            f"回填字段 {result.get('fields_backfilled')} 行。",
            "success",
        )
        return render_template(
            "trace/backfill_result.html",
            result=result,
        )
