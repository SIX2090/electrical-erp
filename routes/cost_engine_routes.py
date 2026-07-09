# -*- coding: utf-8 -*-
"""
成本引擎路由 (P0-3)

路由列表：
- GET  /cost                          成本引擎首页（最近运行 + 发起运行表单）
- POST /cost/run                      执行成本计算
- GET  /cost/runs                     成本运行列表
- GET  /cost/runs/<run_id>            成本运行明细（按成本类型分组）
- GET  /cost/project/<project_code>   项目成本汇总
- GET  /cost/serial/<serial_no>       机号成本汇总
- GET  /cost/reconciliation           成本对账页面
- POST /cost/reconciliation/run       执行成本对账
"""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

from flask import abort, flash, redirect, render_template, request, session, url_for

from services.cost_engine import (
    COST_TYPE_LABOR,
    COST_TYPE_MATERIAL,
    COST_TYPE_OUTSOURCE,
    COST_TYPE_OVERHEAD,
    COST_TYPE_QUALITY,
    COST_TYPE_SERVICE,
    get_cost_run,
    get_cost_variance_report,
    get_project_cost_summary,
    get_serial_cost_summary,
    list_cost_runs,
    run_cost_calculation,
)
from services.cost_reconciliation_service import (
    list_reconciliation_results,
    reconcile_business_vs_gl,
    reconcile_business_vs_inventory,
    save_reconciliation_result,
)
from services.data_scope_service import get_data_scope, log_data_access, row_allowed, scope_has_rules

import logging

logger = logging.getLogger(__name__)


COST_TYPE_LABELS = {
    COST_TYPE_MATERIAL: "材料成本",
    COST_TYPE_LABOR: "人工成本",
    COST_TYPE_OVERHEAD: "制造费用",
    COST_TYPE_OUTSOURCE: "委外成本",
    COST_TYPE_SERVICE: "售后服务成本",
    COST_TYPE_QUALITY: "质量成本",
}


def _decimal(value):
    try:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _money(value) -> str:
    try:
        return f"{float(value or 0):,.2f}"
    except Exception:
        return "0.00"


def _current_user_id() -> int:
    from flask import session

    uid = session.get("user_id") or session.get("uid")
    try:
        return int(uid) if uid is not None else 0
    except Exception:
        return 0


def _filters_from_request() -> dict:
    return {
        "keyword": (request.args.get("keyword") or "").strip(),
        "period": (request.args.get("period") or "").strip(),
        "project_code": (request.args.get("project_code") or "").strip(),
        "serial_no": (request.args.get("serial_no") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
    }


def register_routes(app, deps):
    login_required = deps["login_required"]
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    execute_and_return = deps.get("execute_and_return") or (lambda sql, params=None: None)
    log_action = deps.get("log_action") or (lambda *args, **kwargs: None)

    query_one = lambda sql, params=None: query_db(sql, params or (), one=True)
    query_rows = lambda sql, params=None: query_db(sql, params or ())

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
        """P3-B5: 记录成本引擎路由访问日志，失败不影响业务流程。"""
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
            logger.warning("Failed to create trace link in cost engine route", exc_info=True)

    # -----------------------------------------------------------------------
    # GET /cost - 成本引擎首页
    # -----------------------------------------------------------------------
    @app.get("/cost", endpoint="cost_engine_home")
    @login_required
    def cost_engine_home():
        _log_view("cost_home", reason="成本引擎首页")
        filters = _filters_from_request()
        recent_runs = _filter_by_scope(list_cost_runs(query_rows, filters))
        # 首页指标
        total_runs = len(recent_runs)
        total_cost = sum(_decimal(r.get("total_cost")) for r in recent_runs)
        total_material = sum(_decimal(r.get("total_material_cost")) for r in recent_runs)
        total_labor = sum(_decimal(r.get("total_labor_cost")) for r in recent_runs)
        total_outsource = sum(_decimal(r.get("total_outsource_cost")) for r in recent_runs)
        metrics = [
            {"label": "成本运行数", "value": total_runs, "hint": "最近 200 条运行记录"},
            {"label": "运行总成本", "value": _money(total_cost), "hint": "所有运行 total_cost 汇总"},
            {"label": "材料成本", "value": _money(total_material), "hint": "材料领料 - 退料"},
            {"label": "人工成本", "value": _money(total_labor), "hint": "工序报工人工"},
            {"label": "委外成本", "value": _money(total_outsource), "hint": "委外收货应付"},
            {"label": "对账入口", "value": "成本对账", "hint": "业务 vs 库存 / 总账"},
        ]
        return render_template(
            "cost/index.html",
            title="成本引擎",
            subtitle="按项目号/机号/工单归集材料、人工、制造费用、委外、售后、质量成本，生成成本运行记录。",
            recent_runs=recent_runs,
            metrics=metrics,
            filters=filters,
            cost_type_labels=COST_TYPE_LABELS,
            money=_money,
        )

    # -----------------------------------------------------------------------
    # POST /cost/run - 执行成本计算
    # -----------------------------------------------------------------------
    @app.post("/cost/run", endpoint="cost_engine_run")
    @login_required
    def cost_engine_run():
        period = (request.form.get("period") or "").strip()
        project_code = (request.form.get("project_code") or "").strip()
        serial_no = (request.form.get("serial_no") or "").strip()
        work_order_id_raw = (request.form.get("work_order_id") or "").strip()
        work_order_id = None
        if work_order_id_raw:
            try:
                work_order_id = int(work_order_id_raw)
            except ValueError:
                flash("工单 ID 必须为整数", "error")
                return redirect("/cost")
        if not any([period, project_code, serial_no, work_order_id]):
            flash("请至少填写期间、项目号、机号或工单 ID 之一", "error")
            return redirect("/cost")

        created_by = _current_user_id()
        result = run_cost_calculation(
            query_one, query_rows, execute_db, execute_and_return,
            period=period or None,
            project_code=project_code or None,
            serial_no=serial_no or None,
            work_order_id=work_order_id,
            created_by=created_by,
        )
        if not result.get("success"):
            flash(result.get("message", "成本计算失败"), "error")
            return redirect("/cost")

        log_action(
            "cost_engine_run",
            target=result.get("run_no", ""),
            remark=f"成本计算运行 {result.get('run_no')}，"
                   f"总成本 {_money(result.get('totals', {}).get('total', 0))}，"
                   f"明细行 {result.get('line_count', 0)}",
        )
        flash(
            f"成本计算完成：{result.get('run_no')}，"
            f"总成本 {_money(result.get('totals', {}).get('total', 0))}，"
            f"明细行 {result.get('line_count', 0)}",
            "success",
        )
        return redirect(f"/cost/runs/{result.get('run_id')}")

    # -----------------------------------------------------------------------
    # GET /cost/runs - 成本运行列表
    # -----------------------------------------------------------------------
    @app.get("/cost/runs", endpoint="cost_engine_runs")
    @login_required
    def cost_engine_runs():
        _log_view("cost_runs", reason="成本运行列表")
        filters = _filters_from_request()
        runs = _filter_by_scope(list_cost_runs(query_rows, filters))
        total_cost = sum(_decimal(r.get("total_cost")) for r in runs)
        metrics = [
            {"label": "运行数", "value": len(runs), "hint": "当前筛选结果"},
            {"label": "总成本", "value": _money(total_cost), "hint": "所有运行 total_cost 汇总"},
        ]
        return render_template(
            "cost/runs.html",
            title="成本运行列表",
            subtitle="查看所有成本计算运行记录，点击运行编号查看明细。",
            runs=runs,
            metrics=metrics,
            filters=filters,
            money=_money,
        )

    # -----------------------------------------------------------------------
    # GET /cost/runs/<run_id> - 成本运行明细
    # -----------------------------------------------------------------------
    @app.get("/cost/runs/<int:run_id>", endpoint="cost_engine_run_detail")
    @login_required
    def cost_engine_run_detail(run_id: int):
        _log_view("cost_run_detail", resource_id=run_id, reason="成本运行明细")
        data = get_cost_run(query_one, query_rows, run_id)
        if not data.get("found"):
            flash("成本运行不存在", "error")
            return redirect("/cost/runs")
        run = data.get("run") or {}
        items = data.get("items") or []
        items_by_type = data.get("items_by_type") or {}

        # 按类型汇总金额
        type_summaries = []
        for ct, label in COST_TYPE_LABELS.items():
            type_items = items_by_type.get(ct, [])
            amount = sum(_decimal(i.get("amount")) for i in type_items)
            type_summaries.append({
                "cost_type": ct,
                "label": label,
                "line_count": len(type_items),
                "amount": amount,
                "amount_display": _money(amount),
            })

        metrics = [
            {"label": "运行编号", "value": run.get("run_no", ""), "hint": "唯一标识"},
            {"label": "状态", "value": run.get("status", ""), "hint": "运行状态"},
            {"label": "期间", "value": run.get("period") or "-", "hint": "成本期间"},
            {"label": "项目号", "value": run.get("project_code") or "-", "hint": "项目号过滤"},
            {"label": "机号", "value": run.get("serial_no") or "-", "hint": "机号过滤"},
            {"label": "工单 ID", "value": run.get("work_order_id") or "-", "hint": "工单过滤"},
            {"label": "明细行数", "value": len(items), "hint": "全部明细行"},
            {"label": "总成本", "value": _money(run.get("total_cost")), "hint": "运行总成本"},
        ]
        return render_template(
            "cost/run_detail.html",
            title=f"成本运行明细 - {run.get('run_no', '')}",
            subtitle="按成本类型分组的明细行，支持追溯来源单据。",
            run=run,
            items=items,
            items_by_type=items_by_type,
            type_summaries=type_summaries,
            metrics=metrics,
            cost_type_labels=COST_TYPE_LABELS,
            money=_money,
        )

    # -----------------------------------------------------------------------
    # GET /cost/project/<project_code> - 项目成本汇总
    # -----------------------------------------------------------------------
    @app.get("/cost/project/<project_code>", endpoint="cost_engine_project_summary")
    @login_required
    def cost_engine_project_summary(project_code: str):
        if _scope_denied({"project_code": project_code}):
            abort(403)
        summary = get_project_cost_summary(query_one, project_code)
        # 取该项目相关的运行列表
        runs = list_cost_runs(query_rows, {"project_code": project_code})
        metrics = [
            {"label": "项目号", "value": project_code, "hint": "成本汇总对象"},
            {"label": "运行数", "value": summary.get("run_count", 0), "hint": "已完成运行数"},
            {"label": "材料成本", "value": _money(summary.get("material")), "hint": "材料领料 - 退料"},
            {"label": "人工成本", "value": _money(summary.get("labor")), "hint": "工序报工人工"},
            {"label": "制造费用", "value": _money(summary.get("overhead")), "hint": "工序设备/制造费用"},
            {"label": "委外成本", "value": _money(summary.get("outsource")), "hint": "委外收货应付"},
            {"label": "售后成本", "value": _money(summary.get("service")), "hint": "售后服务成本"},
            {"label": "质量成本", "value": _money(summary.get("quality")), "hint": "报废/质量成本"},
            {"label": "总成本", "value": _money(summary.get("total")), "hint": "所有成本汇总"},
        ]
        return render_template(
            "cost/project_cost.html",
            title=f"项目成本汇总 - {project_code}",
            subtitle="按项目号汇总所有成本运行结果，支持查看运行明细。",
            project_code=project_code,
            summary=summary,
            runs=runs,
            metrics=metrics,
            money=_money,
        )

    # -----------------------------------------------------------------------
    # GET /cost/serial/<serial_no> - 机号成本汇总
    # -----------------------------------------------------------------------
    @app.get("/cost/serial/<serial_no>", endpoint="cost_engine_serial_summary")
    @login_required
    def cost_engine_serial_summary(serial_no: str):
        if _scope_denied({"serial_no": serial_no}):
            abort(403)
        summary = get_serial_cost_summary(query_one, serial_no)
        runs = list_cost_runs(query_rows, {"serial_no": serial_no})
        metrics = [
            {"label": "机号", "value": serial_no, "hint": "成本汇总对象"},
            {"label": "运行数", "value": summary.get("run_count", 0), "hint": "已完成运行数"},
            {"label": "材料成本", "value": _money(summary.get("material")), "hint": "材料领料 - 退料"},
            {"label": "人工成本", "value": _money(summary.get("labor")), "hint": "工序报工人工"},
            {"label": "制造费用", "value": _money(summary.get("overhead")), "hint": "工序设备/制造费用"},
            {"label": "委外成本", "value": _money(summary.get("outsource")), "hint": "委外收货应付"},
            {"label": "售后成本", "value": _money(summary.get("service")), "hint": "售后服务成本"},
            {"label": "质量成本", "value": _money(summary.get("quality")), "hint": "报废/质量成本"},
            {"label": "总成本", "value": _money(summary.get("total")), "hint": "所有成本汇总"},
        ]
        return render_template(
            "cost/serial_cost.html",
            title=f"机号成本汇总 - {serial_no}",
            subtitle="按机号汇总所有成本运行结果，支持查看运行明细。",
            serial_no=serial_no,
            summary=summary,
            runs=runs,
            metrics=metrics,
            money=_money,
        )

    # -----------------------------------------------------------------------
    # GET /cost/reconciliation - 成本对账页面
    # -----------------------------------------------------------------------
    @app.get("/cost/reconciliation", endpoint="cost_engine_reconciliation")
    @login_required
    def cost_engine_reconciliation():
        _log_view("cost_reconciliation", reason="成本对账")
        filters = _filters_from_request()
        results = _filter_by_scope(list_reconciliation_results(query_rows, filters))
        return render_template(
            "cost/reconciliation.html",
            title="成本对账",
            subtitle="对比业务成本与库存成本、总账成本，发现差异并保存对账结果。",
            results=results,
            filters=filters,
            money=_money,
        )

    # -----------------------------------------------------------------------
    # POST /cost/reconciliation/run - 执行成本对账
    # -----------------------------------------------------------------------
    @app.post("/cost/reconciliation/run", endpoint="cost_engine_reconciliation_run")
    @login_required
    def cost_engine_reconciliation_run():
        period = (request.form.get("period") or "").strip()
        project_code = (request.form.get("project_code") or "").strip()
        serial_no = (request.form.get("serial_no") or "").strip()
        recon_type = (request.form.get("reconciliation_type") or "business_vs_inventory").strip()

        if recon_type == "business_vs_gl":
            result = reconcile_business_vs_gl(
                query_one,
                period=period or None,
                project_code=project_code or None,
                serial_no=serial_no or None,
            )
        else:
            result = reconcile_business_vs_inventory(
                query_one,
                period=period or None,
                project_code=project_code or None,
                serial_no=serial_no or None,
            )

        save_result = save_reconciliation_result(query_db, execute_db, result)
        if not save_result.get("success"):
            flash(save_result.get("message", "对账结果保存失败"), "error")

        log_action(
            "cost_reconciliation_run",
            target=recon_type,
            remark=f"对账类型 {recon_type}，期间 {period}，"
                   f"业务成本 {_money(result.get('business_cost'))}，"
                   f"差异 {_money(result.get('difference'))}，"
                   f"状态 {result.get('status')}",
        )
        flash(
            f"对账完成：业务成本 {_money(result.get('business_cost'))}，"
            f"差异 {_money(result.get('difference'))}，"
            f"状态 {result.get('status')}",
            "success",
        )
        return redirect("/cost/reconciliation")

    @app.get("/cost/variance", endpoint="cost_engine_variance")
    @login_required
    def cost_engine_variance():
        """P2-B3: 标准 vs 实际成本差异报表。"""
        _log_view("cost_variance", reason="标准 vs 实际成本差异报表")
        run_id = request.args.get("run_id", type=int)
        if not run_id:
            # 默认取最近一次完成的成本运行
            latest = query_one(
                "SELECT id FROM cost_runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
            )
            run_id = latest.get("id") if latest else None
        report = get_cost_variance_report(query_db, run_id) if run_id else {
            "summary": [], "lines": [], "total_standard": 0,
            "total_actual": 0, "total_variance": 0,
        }
        runs = query_db(
            "SELECT id, run_no, period, project_code, serial_no, status, created_at "
            "FROM cost_runs WHERE status='completed' ORDER BY id DESC LIMIT 50"
        )
        return render_template(
            "cost/variance.html",
            report=report,
            runs=[dict(r) for r in runs or []],
            current_run_id=run_id,
            COST_TYPE_LABELS=COST_TYPE_LABELS,
        )
