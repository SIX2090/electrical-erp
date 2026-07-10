"""MRP routes: BOM explosion, shortage analysis, and material requirement planning."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import flash, jsonify, redirect, render_template, request, session

from services.data_scope_service import get_data_scope, log_data_access, row_allowed, scope_has_rules
from services.mrp_engine import (
    build_kitting_analysis,
    get_mrp_run_detail,
    get_mrp_suggestions,
    list_mrp_runs,
    run_mrp,
)
from services.mrp_suggestion_service import (
    batch_convert,
    convert_single,
    convert_to_purchase_requisition,
    convert_to_subcontract_order,
    convert_to_work_order,
)

import logging

logger = logging.getLogger(__name__)


def _query_one(query_db):
    def _fn(sql, params=None, one=None):
        # `one` kwarg is accepted for compatibility with services that call
        # query_db(sql, params, one=True). This wrapper always returns a single
        # row, so the flag is a no-op here.
        return query_db(sql, params or (), one=True)
    return _fn


def _query_rows(query_db):
    def _fn(sql, params=None):
        return query_db(sql, params or ())
    return _fn


def _qty(value) -> str:
    try:
        qty = Decimal(str(value if value is not None else "0"))
    except Exception:
        qty = Decimal("0")
    text = f"{qty:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _percent(value) -> str:
    try:
        rate = Decimal(str(value if value is not None else "0"))
    except Exception:
        rate = Decimal("0")
    return f"{rate:.2f}"


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]
    login_required = deps["login_required"]
    log_action = deps.get("log_action")

    _SCOPE_FIELD_MAP = {"project": "project_code", "cabinet": "cabinet_no"}

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

    def _filter_by_scope(rows):
        scope = _current_scope()
        if not scope_has_rules(scope):
            return rows
        return [row for row in rows if row_allowed(scope, row, _SCOPE_FIELD_MAP)]

    def _log_view(resource_type, resource_id=None, reason=""):
        """P3-B5: 记录 P0 业务路由的访问日志，失败不影响业务流程。"""
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
            logger.warning("Failed to create trace link in MRP route", exc_info=True)

    @app.get("/mrp", endpoint="mrp_home")
    @login_required
    def mrp_home():
        query_one = _query_one(query_db)
        query_rows = _query_rows(query_db)
        _log_view("mrp_home", reason="MRP 首页")
        recent_runs = _filter_by_scope(list_mrp_runs(query_rows, filters={}))[:10]
        open_suggestions = get_mrp_suggestions(query_rows, status="open")[:10]
        work_orders = query_rows(
            """
            SELECT wo.id, wo.wo_no, wo.project_code, wo.cabinet_no, wo.status, wo.quantity,
                   p.code AS product_code, p.name AS product_name
            FROM work_orders wo
            LEFT JOIN products p ON p.id=wo.product_id
            WHERE COALESCE(wo.status, '') NOT IN ('已完工','已关闭','已完成','closed','completed','cancelled','canceled')
            ORDER BY wo.id DESC
            LIMIT 100
            """,
            (),
        ) or []
        products = query_rows(
            """
            SELECT p.id, p.code, p.name, p.specification, p.unit
            FROM products p
            WHERE EXISTS (SELECT 1 FROM boms b WHERE b.product_id=p.id AND COALESCE(b.status,'') NOT IN ('停用','inactive','disabled'))
            ORDER BY p.code
            LIMIT 200
            """,
            (),
        ) or []
        return render_template(
            "mrp/index.html",
            recent_runs=recent_runs,
            open_suggestions=open_suggestions,
            work_orders=work_orders,
            products=products,
            qty=_qty,
            percent=_percent,
        )

    @app.post("/mrp/run", endpoint="mrp_run_execute")
    @login_required
    def mrp_run_execute():
        query_one = _query_one(query_db)
        query_rows = _query_rows(query_db)
        source_type = (request.form.get("source_type") or "").strip()
        source_id = _int(request.form.get("source_id"))
        project_code = (request.form.get("project_code") or "").strip() or None
        cabinet_no = (request.form.get("cabinet_no") or "").strip() or None
        bom_id = _int(request.form.get("bom_id")) or None
        quantity = request.form.get("quantity") or "1"
        created_by = session.get("user_id")
        # Optional explicit required date for time-phased MRP.
        required_date_str = (request.form.get("required_date") or "").strip() or None
        required_date = None
        if required_date_str:
            try:
                required_date = datetime.strptime(required_date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("需求日期格式不正确，应为 YYYY-MM-DD。", "warning")
                return redirect("/mrp")
        if not source_type:
            flash("请选择 MRP 运行来源类型。", "warning")
            return redirect("/mrp")
        if source_type not in ("work_order", "sales_order", "product"):
            flash("不支持的来源类型。", "warning")
            return redirect("/mrp")
        if not source_id:
            flash("请指定来源单据或物料。", "warning")
            return redirect("/mrp")
        result = run_mrp(
            query_one,
            query_rows,
            execute_db,
            execute_and_return,
            source_type=source_type,
            source_id=source_id,
            project_code=project_code,
            cabinet_no=cabinet_no,
            bom_id=bom_id,
            quantity=quantity,
            required_date=required_date,
            created_by=created_by,
        )
        if result.get("status") != "ok":
            flash(f"MRP 运行失败：{result.get('message') or '未知错误'}", "danger")
            return redirect("/mrp")
        if log_action:
            log_action(
                "执行MRP运行",
                result.get("run_no") or "",
                f"来源 {source_type}，行数 {result.get('line_count')}，缺料 {result.get('shortage_line_count')}",
            )
        flash(
            f"MRP 运行 {result.get('run_no')} 完成：共 {result.get('line_count')} 行，"
            f"缺料 {result.get('shortage_line_count')} 行，齐套率 {result.get('kitting_rate')}%。",
            "success",
        )
        return redirect(f"/mrp/runs/{result.get('run_id')}")

    @app.get("/mrp/runs", endpoint="mrp_runs_list")
    @login_required
    def mrp_runs_list():
        query_rows = _query_rows(query_db)
        _log_view("mrp_runs", reason="MRP 运行列表")
        filters = {
            "status": (request.args.get("status") or "").strip() or None,
            "source_type": (request.args.get("source_type") or "").strip() or None,
            "project_code": (request.args.get("project_code") or "").strip() or None,
            "cabinet_no": (request.args.get("cabinet_no") or "").strip() or None,
            "keyword": (request.args.get("keyword") or request.args.get("q") or "").strip() or None,
        }
        filters = {k: v for k, v in filters.items() if v}
        runs = _filter_by_scope(list_mrp_runs(query_rows, filters=filters))
        return render_template(
            "mrp/runs.html",
            runs=runs,
            filters=filters,
            qty=_qty,
            percent=_percent,
        )

    @app.get("/mrp/runs/<int:run_id>", endpoint="mrp_run_detail")
    @login_required
    def mrp_run_detail(run_id):
        query_one = _query_one(query_db)
        query_rows = _query_rows(query_db)
        _log_view("mrp_run_detail", resource_id=run_id, reason="MRP 运行明细")
        detail = get_mrp_run_detail(query_one, query_rows, run_id)
        if detail.get("status") != "ok":
            flash("MRP 运行记录不存在。", "warning")
            return redirect("/mrp/runs")
        return render_template(
            "mrp/run_detail.html",
            header=detail.get("header") or {},
            items=detail.get("items") or [],
            suggestions=detail.get("suggestions") or [],
            qty=_qty,
            percent=_percent,
        )

    @app.get("/mrp/suggestions", endpoint="mrp_suggestions_list")
    @login_required
    def mrp_suggestions_list():
        query_rows = _query_rows(query_db)
        _log_view("mrp_suggestions", reason="MRP 建议列表")
        status = (request.args.get("status") or "").strip() or None
        suggestion_type = (request.args.get("suggestion_type") or "").strip() or None
        suggestions = _filter_by_scope(get_mrp_suggestions(query_rows, status=status))
        if suggestion_type:
            suggestions = [s for s in suggestions if s.get("suggestion_type") == suggestion_type]
        return render_template(
            "mrp/suggestions.html",
            suggestions=suggestions,
            status_filter=status,
            suggestion_type_filter=suggestion_type,
            qty=_qty,
        )

    @app.post("/mrp/suggestions/<int:suggestion_id>/convert", endpoint="mrp_suggestion_convert")
    @login_required
    def mrp_suggestion_convert(suggestion_id):
        query_one = _query_one(query_db)
        query_rows = _query_rows(query_db)
        action = (request.form.get("action") or "auto").strip()
        created_by = session.get("user_id")
        if action == "purchase_requisition":
            result = convert_to_purchase_requisition(query_one, query_rows, execute_db, execute_and_return, suggestion_id, created_by)
        elif action == "work_order":
            result = convert_to_work_order(query_one, query_rows, execute_db, execute_and_return, suggestion_id, created_by)
        elif action == "subcontract_order":
            result = convert_to_subcontract_order(query_one, query_rows, execute_db, execute_and_return, suggestion_id, created_by)
        else:
            result = convert_single(query_one, query_rows, execute_db, execute_and_return, suggestion_id, created_by)
        if result.get("status") != "ok":
            flash(f"转换失败：{result.get('message') or '未知错误'}", "danger")
            return redirect("/mrp/suggestions")
        if log_action:
            log_action(
                "转换MRP建议",
                f"{suggestion_id}",
                f"生成 {result.get('doc_type')} {result.get('doc_no')}",
            )
        flash(
            f"已生成 {result.get('doc_type')} {result.get('doc_no')}。",
            "success",
        )
        return_url = request.form.get("return_url") or ""
        if return_url:
            return redirect(return_url)
        return redirect("/mrp/suggestions")

    @app.post("/mrp/suggestions/batch-convert", endpoint="mrp_suggestions_batch_convert")
    @login_required
    def mrp_suggestions_batch_convert():
        query_one = _query_one(query_db)
        query_rows = _query_rows(query_db)
        ids = request.form.getlist("suggestion_ids")
        suggestion_ids = [_int(v) for v in ids if _int(v) > 0]
        if not suggestion_ids:
            flash("请选择需要转换的建议。", "warning")
            return redirect("/mrp/suggestions")
        created_by = session.get("user_id")
        result = batch_convert(query_one, query_rows, execute_db, execute_and_return, suggestion_ids, created_by)
        if log_action:
            log_action(
                "批量转换MRP建议",
                f"{len(suggestion_ids)}条",
                f"成功 {result.get('success_count')}，失败 {result.get('failure_count')}",
            )
        flash(
            f"批量转换完成：成功 {result.get('success_count')}，失败 {result.get('failure_count')}。",
            "success" if result.get("failure_count") == 0 else "warning",
        )
        return redirect("/mrp/suggestions")

    @app.get("/mrp/kitting", endpoint="mrp_kitting_analysis")
    @login_required
    def mrp_kitting_analysis():
        query_rows = _query_rows(query_db)
        work_order_id = _int(request.args.get("work_order_id"))
        _log_view("mrp_kitting", resource_id=work_order_id or None, reason="MRP 齐套分析")
        analysis: dict = {}
        if work_order_id:
            query_one = _query_one(query_db)
            analysis = build_kitting_analysis(query_one, query_rows, work_order_id)
        work_orders = _filter_by_scope(query_rows(
            """
            SELECT wo.id, wo.wo_no, wo.project_code, wo.cabinet_no, wo.status, wo.quantity,
                   p.code AS product_code, p.name AS product_name
            FROM work_orders wo
            LEFT JOIN products p ON p.id=wo.product_id
            ORDER BY wo.id DESC
            LIMIT 200
            """,
            (),
        ) or [])
        return render_template(
            "mrp/kitting.html",
            work_orders=work_orders,
            work_order_id=work_order_id,
            analysis=analysis,
            qty=_qty,
            percent=_percent,
        )

    @app.get("/api/mrp/runs/<int:run_id>/suggestions", endpoint="api_mrp_run_suggestions")
    @login_required
    def api_mrp_run_suggestions(run_id):
        query_rows = _query_rows(query_db)
        suggestions = get_mrp_suggestions(query_rows, run_id=run_id)
        return jsonify({"status": "ok", "suggestions": suggestions})
