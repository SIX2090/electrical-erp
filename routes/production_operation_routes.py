"""Production operation routes: operation report, pause/resume, and rework/scrap handling."""
from datetime import datetime
from decimal import Decimal

from flask import flash, redirect, render_template, request, session

from services.production_execution_service import (
    execution_blocked_reason,
    execution_downstream_impact,
    execution_next_action,
    operation_status_from_quantities,
    operation_wip_qty,
    status_label as execution_status_label,
)


DOC_STATUS_DRAFT = "草稿"
DOC_STATUS_SUBMITTED = "已提交"
DOC_STATUS_AUDITED = "已审核"
DOC_STATUS_VOIDED = "已作废"

REPORT_TYPE_START = "start"
REPORT_TYPE_PAUSE = "pause"
REPORT_TYPE_COMPLETE = "complete"
REPORT_TYPE_REWORK = "rework"
REPORT_TYPE_SCRAP = "scrap"

FINAL_WORK_ORDER_STATUSES = {
    "已关闭",
    "已完工",
    "已完成",
    "已作废",
    "已取消",
    "closed",
    "completed",
    "void",
    "cancelled",
    "canceled",
}


def register_production_operation_routes(app, deps):
    login_required = deps["login_required"]
    safe_rows = deps["safe_rows"]
    safe_one = deps["safe_one"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]
    next_doc_no = deps["next_doc_no"]
    as_decimal = deps["as_decimal"]
    form_text = deps["form_text"]
    form_int = deps["form_int"]
    log_action = deps["log_action"]
    has_column = deps.get("has_column") or (lambda table, column: False)

    def ensure_schema():
        # DDL 已迁移至 services/schema_migrations.py（20260619_002_operation_reports_schema）
        # 请求期不再执行 CREATE TABLE / ALTER TABLE
        pass

    def status_label(value):
        return {
            "draft": DOC_STATUS_DRAFT,
            "submitted": DOC_STATUS_SUBMITTED,
            "audited": DOC_STATUS_AUDITED,
            "voided": DOC_STATUS_VOIDED,
            DOC_STATUS_DRAFT: DOC_STATUS_DRAFT,
            DOC_STATUS_SUBMITTED: DOC_STATUS_SUBMITTED,
            DOC_STATUS_AUDITED: DOC_STATUS_AUDITED,
            DOC_STATUS_VOIDED: DOC_STATUS_VOIDED,
        }.get(value or DOC_STATUS_DRAFT, value or DOC_STATUS_DRAFT)

    def can_edit_operation_report(report):
        if not report:
            return False
        if report.get("audited_at") or report.get("voided_at"):
            return False
        return status_label(report.get("status")) in {DOC_STATUS_DRAFT, DOC_STATUS_SUBMITTED}

    def report_type_label(value):
        return {
            REPORT_TYPE_START: "开工",
            REPORT_TYPE_PAUSE: "暂停",
            REPORT_TYPE_COMPLETE: "完工",
            REPORT_TYPE_REWORK: "返工",
            REPORT_TYPE_SCRAP: "报废",
        }.get(value or REPORT_TYPE_COMPLETE, value or "完工")

    def process_status_label(value):
        return {
            "not_started": "待报工",
            "ready": "待报工",
            "in_progress": "执行中",
            "completed": "已完工",
            "cancelled": "已取消",
        }.get(value or "", value or "-")

    def next_action_for_type(report_type):
        if report_type == REPORT_TYPE_START:
            return "继续加工并登记后续完工或异常报工"
        if report_type == REPORT_TYPE_REWORK:
            return "完成返工处理后重新报工或提交质量复判"
        if report_type == REPORT_TYPE_SCRAP:
            return "确认报废原因并评估补制、返修或改单影响"
        if report_type == REPORT_TYPE_PAUSE:
            return "解除阻塞后继续加工"
        return "审核后回写工序进度并判断工单可完工数量"

    def open_orders():
        columns = {row.get("column_name") for row in safe_rows(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='work_orders'
            """
        )}
        extra_filters = ["COALESCE(wo_no,'') NOT ILIKE %s"]
        params = ("SVC-%",)
        if "order_type" in columns:
            extra_filters.append("COALESCE(order_type,'') NOT IN ('service','after_sale','售后','服务')")
        if "production_type" in columns:
            extra_filters.append("COALESCE(production_type,'') NOT IN ('service','after_sale','售后','服务')")
        extra_sql = " AND ".join(extra_filters)
        return safe_rows(
            f"""
            SELECT id, wo_no, project_code, serial_no, status
            FROM work_orders
            WHERE COALESCE(status,'') NOT IN ('已关闭','已完工','已完成','已作废','已取消','closed','completed','void','cancelled','canceled')
              AND {extra_sql}
            ORDER BY id DESC
            LIMIT 200
            """,
            params,
        )

    def processes(work_order_id):
        if not work_order_id:
            return []
        return safe_rows(
            """
            SELECT wop.*, wc.name AS work_center_name
            FROM work_order_processes wop
            LEFT JOIN work_centers wc ON wc.id=wop.work_center_id
            WHERE wop.work_order_id=%s
            ORDER BY COALESCE(wop.sequence_no, wop.id), wop.id
            """,
            (work_order_id,),
        )

    def order(work_order_id):
        return safe_one("SELECT * FROM work_orders WHERE id=%s", (work_order_id,))

    def report_row(report_id):
        return safe_one("SELECT * FROM operation_reports WHERE id=%s", (report_id,))

    def process_status_from_summary(row):
        report_count = int(row.get("report_count") or 0)
        start_count = int(row.get("start_count") or 0)
        pause_count = int(row.get("pause_count") or 0)
        good_qty = as_decimal(row.get("good_qty"))
        rework_qty = as_decimal(row.get("rework_qty"))
        scrap_qty = as_decimal(row.get("scrap_qty"))
        planned_qty = as_decimal(row.get("planned_quantity"))
        if scrap_qty > 0 and good_qty <= 0 and rework_qty <= 0:
            return "in_progress"
        if rework_qty > 0:
            return "in_progress"
        if planned_qty > 0 and good_qty >= planned_qty:
            return "completed"
        if good_qty > 0:
            return "in_progress"
        if pause_count > 0:
            return "in_progress"
        if start_count > 0:
            return "in_progress"
        return row.get("old_status") or ("not_started" if report_count == 0 else "in_progress")

    def process_next_action(status, good_qty, planned_qty, rework_qty, scrap_qty):
        if status == "completed":
            return "核对后续质检、完工入库门禁和项目追溯"
        if rework_qty > 0:
            return "处理返工并重新登记合格报工"
        if scrap_qty > 0:
            return "确认补制、返修或改单处理"
        if good_qty > 0 and planned_qty > good_qty:
            return "继续报工剩余数量"
        if scrap_qty > 0:
            return "确认报废处理影响"
        return "登记开工、完工、返工或报废报工"

    def process_status_label(value):
        return execution_status_label(value)

    def process_status_from_summary(row):
        report_count = int(row.get("report_count") or 0)
        if report_count <= 0:
            return row.get("old_status") or "not_started"
        return operation_status_from_quantities(
            row.get("planned_quantity"),
            row.get("good_qty"),
            row.get("rework_qty"),
            row.get("scrap_qty"),
            int(row.get("pause_count") or 0),
            int(row.get("start_count") or 0),
        )

    def process_next_action(status, good_qty, planned_qty, rework_qty, scrap_qty):
        return execution_next_action(status, operation_wip_qty(planned_qty, good_qty, scrap_qty))

    def refresh_work_order_operation_progress(work_order_id):
        if not work_order_id:
            return
        rows = safe_rows(
            """
            SELECT planned_quantity, actual_quantity, good_quantity, rework_quantity, scrap_quantity, status
            FROM work_order_processes
            WHERE work_order_id=%s
            ORDER BY COALESCE(sequence_no, id), id
            """,
            (work_order_id,),
        )
        if not rows:
            return
        process_good = [as_decimal(row.get("good_quantity") or row.get("actual_quantity")) for row in rows]
        positive_good = [qty for qty in process_good if qty > 0]
        operation_completed_qty = min(positive_good) if positive_good and len(positive_good) == len(rows) else Decimal("0")
        rework_qty = sum((as_decimal(row.get("rework_quantity")) for row in rows), Decimal("0"))
        scrap_qty = sum((as_decimal(row.get("scrap_quantity")) for row in rows), Decimal("0"))
        wip_qty = sum(
            (operation_wip_qty(row.get("planned_quantity"), row.get("good_quantity") or row.get("actual_quantity"), row.get("scrap_quantity")) for row in rows),
            Decimal("0"),
        )
        all_finished = all(
            (row.get("status") or "") == "completed"
            or (
                as_decimal(row.get("planned_quantity")) > 0
                and as_decimal(row.get("good_quantity") or row.get("actual_quantity")) >= as_decimal(row.get("planned_quantity"))
            )
            for row in rows
        )
        any_reported = any(qty > 0 for qty in process_good) or rework_qty > 0 or scrap_qty > 0
        order_row = order(work_order_id) or {}
        if (order_row.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
            return
        fields = [
            "operation_completed_qty=%s",
            "operation_rework_qty=%s",
            "operation_scrap_qty=%s",
            "operation_wip_qty=%s",
        ]
        params = [operation_completed_qty, rework_qty, scrap_qty, wip_qty]
        summary_status = "rework_pending" if rework_qty > 0 else ("scrap_pending" if scrap_qty > 0 else ("completed" if all_finished else ("in_progress" if any_reported else "not_started")))
        if has_column("work_orders", "next_action"):
            fields.append("next_action=%s")
            params.append(execution_next_action(summary_status, wip_qty))
        if has_column("work_orders", "downstream_impact"):
            fields.append("downstream_impact=%s")
            params.append(execution_downstream_impact(summary_status, wip_qty, rework_qty, scrap_qty))
        if has_column("work_orders", "status"):
            fields.append("status=CASE WHEN COALESCE(status,'') IN ('待提交','已提交','待生产','') THEN %s ELSE status END")
            params.append("待完工入库" if all_finished else ("生产中" if any_reported else order_row.get("status")))
        if has_column("work_orders", "blocked_reason"):
            fields.append("blocked_reason=%s")
            params.append("存在返工或报废报工，需确认处理结论" if rework_qty > 0 or scrap_qty > 0 else "")
        if has_column("work_orders", "owner_role"):
            fields.append("owner_role=%s")
            params.append("生产")
        if has_column("work_orders", "production_stage"):
            fields.append("production_stage=%s")
            params.append("待完工入库" if all_finished else "生产执行")
        if has_column("work_orders", "updated_at"):
            fields.append("updated_at=NOW()")
        params.append(work_order_id)
        execute_db(f"UPDATE work_orders SET {', '.join(fields)} WHERE id=%s", tuple(params))

    def refresh_process_progress(process_id):
        process = safe_one("SELECT * FROM work_order_processes WHERE id=%s", (process_id,))
        if not process:
            return None
        summary = safe_one(
            """
            SELECT
                COUNT(*) AS report_count,
                COUNT(*) FILTER (WHERE report_type=%s) AS start_count,
                COUNT(*) FILTER (WHERE report_type=%s) AS pause_count,
                COALESCE(SUM(good_qty),0) AS good_qty,
                COALESCE(SUM(rework_qty),0) AS rework_qty,
                COALESCE(SUM(scrap_qty),0) AS scrap_qty,
                COALESCE(SUM(labor_hours),0) AS labor_hours,
                COALESCE(SUM(equipment_hours),0) AS equipment_hours,
                MIN(start_time) AS first_start_time,
                MAX(end_time) AS last_end_time,
                MAX(NULLIF(blocked_reason,'')) AS blocked_reason
            FROM operation_reports
            WHERE work_order_process_id=%s
              AND COALESCE(status,'') IN (%s,%s)
            """,
            (REPORT_TYPE_START, REPORT_TYPE_PAUSE, process_id, DOC_STATUS_AUDITED, "audited"),
        ) or {}
        summary["planned_quantity"] = process.get("planned_quantity")
        summary["old_status"] = process.get("status")
        good_qty = as_decimal(summary.get("good_qty"))
        planned_qty = as_decimal(process.get("planned_quantity"))
        rework_qty = as_decimal(summary.get("rework_qty"))
        scrap_qty = as_decimal(summary.get("scrap_qty"))
        process_status = process_status_from_summary(summary)
        wip_qty = operation_wip_qty(planned_qty, good_qty, scrap_qty)
        blocked_reason = execution_blocked_reason(process_status, summary.get("blocked_reason") or "", rework_qty, scrap_qty, wip_qty)
        next_action = process_next_action(process_status, good_qty, planned_qty, rework_qty, scrap_qty)
        downstream_impact = execution_downstream_impact(process_status, wip_qty, rework_qty, scrap_qty)
        execute_db(
            """
            UPDATE work_order_processes
            SET actual_quantity=%s,
                good_quantity=%s,
                rework_quantity=%s,
                scrap_quantity=%s,
                labor_hours=%s,
                equipment_hours=%s,
                status=%s,
                qc_status=CASE
                    WHEN %s > 0 THEN '需复判'
                    WHEN %s > 0 THEN '待处理'
                    WHEN %s='completed' THEN '待检'
                    ELSE COALESCE(qc_status, '')
                END,
                owner_role=%s,
                blocked_reason=NULLIF(%s,''),
                next_action=%s,
                downstream_impact=%s,
                wip_quantity=%s,
                started_at=COALESCE(started_at, %s),
                completed_at=CASE WHEN %s='completed' THEN COALESCE(completed_at, %s, NOW()) ELSE completed_at END,
                updated_at=NOW()
            WHERE id=%s
            """,
            (
                good_qty,
                good_qty,
                rework_qty,
                scrap_qty,
                as_decimal(summary.get("labor_hours")),
                as_decimal(summary.get("equipment_hours")),
                process_status,
                rework_qty,
                scrap_qty,
                process_status,
                "production",
                blocked_reason,
                next_action,
                downstream_impact,
                wip_qty,
                summary.get("first_start_time"),
                process_status,
                summary.get("last_end_time"),
                process_id,
            ),
        )
        refresh_work_order_operation_progress(process.get("work_order_id"))
        return process_status

    def list_page():
        ensure_schema()
        rows = safe_rows(
            """
            SELECT opr.*, wo.wo_no, wc.name AS work_center_name
            FROM operation_reports opr
            LEFT JOIN work_orders wo ON wo.id=opr.work_order_id
            LEFT JOIN work_centers wc ON wc.id=opr.work_center_id
            ORDER BY opr.id DESC
            LIMIT 200
            """
        )
        return render_template("operation_report_list.html", rows=rows, status_label=status_label, report_type_label=report_type_label)

    def form_page():
        ensure_schema()
        if request.method == "POST":
            work_order_id = form_int("work_order_id")
            process_id = form_int("work_order_process_id") or form_int("process_id")
            wo = order(work_order_id)
            if not wo:
                flash("请选择有效工单。", "warning")
                return redirect("/production/operation-reports/new")
            if (wo.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
                flash("来源工单已关闭、已完工或已作废，不能新增工序报工单。", "warning")
                return redirect(f"/work-orders/{work_order_id}")
            process = safe_one("SELECT * FROM work_order_processes WHERE id=%s AND work_order_id=%s", (process_id, work_order_id)) if process_id else {}
            if not process:
                flash("请选择来源工单下的有效工序。", "warning")
                return redirect(f"/production/operation-reports/new?work_order_id={work_order_id}")
            report_type = form_text("report_type", REPORT_TYPE_COMPLETE)
            good_qty = as_decimal(form_text("good_qty", "0"))
            rework_qty = as_decimal(form_text("rework_qty", "0"))
            scrap_qty = as_decimal(form_text("scrap_qty", "0"))
            if report_type in {REPORT_TYPE_COMPLETE, REPORT_TYPE_REWORK, REPORT_TYPE_SCRAP} and good_qty + rework_qty + scrap_qty <= 0:
                flash("完工、返工或报废报工必须填写数量。", "warning")
                return redirect(f"/production/operation-reports/new?work_order_id={work_order_id}&process_id={process_id}")
            start_time = datetime.now() if report_type == REPORT_TYPE_START else None
            end_time = datetime.now() if report_type in {REPORT_TYPE_COMPLETE, REPORT_TYPE_REWORK, REPORT_TYPE_SCRAP} else None
            report_no = next_doc_no("OPR", "operation_reports", "report_no")
            report = execute_and_return(
                """
                INSERT INTO operation_reports
                    (report_no, work_order_id, work_order_process_id, routing_operation_id, report_type, report_date,
                     status, operator_id, work_center_id, start_time, end_time, labor_hours, equipment_hours,
                     good_qty, rework_qty, scrap_qty, blocked_reason, next_action, downstream_impact, project_code, serial_no,
                     remark, submitted_by, submitted_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                RETURNING id, report_no
                """,
                (
                    report_no,
                    work_order_id,
                    process_id,
                    process.get("routing_operation_id"),
                    report_type,
                    form_text("report_date", datetime.now().date().isoformat()),
                    DOC_STATUS_SUBMITTED,
                    session.get("user_id"),
                    form_int("work_center_id") or process.get("work_center_id"),
                    start_time,
                    end_time,
                    as_decimal(form_text("labor_hours", "0")),
                    as_decimal(form_text("equipment_hours", "0")),
                    good_qty,
                    rework_qty,
                    scrap_qty,
                    form_text("blocked_reason"),
                    form_text("next_action", next_action_for_type(report_type)),
                    form_text("downstream_impact", execution_downstream_impact(report_type)),
                    wo.get("project_code"),
                    wo.get("serial_no"),
                    form_text("remark"),
                    session.get("user_id"),
                ),
            )
            log_action("创建工序报工", report_no, f"work_order_id={work_order_id} process_id={process_id}")
            flash("工序报工已保存并提交，请审核回写。", "success")
            return redirect(f"/production/operation-reports/{report.get('id')}")
        work_order_id = request.args.get("work_order_id", "").strip()
        process_id = request.args.get("work_order_process_id") or request.args.get("process_id") or ""
        return render_template(
            "operation_report_form.html",
            order=order(int(work_order_id)) if work_order_id else None,
            orders=open_orders(),
            processes=processes(int(work_order_id)) if work_order_id else [],
            process_id=process_id,
            report_type=request.args.get("type") or REPORT_TYPE_COMPLETE,
            next_action_for_type=next_action_for_type,
            process_status_label=process_status_label,
        )

    def update_report(report_id):
        report = report_row(report_id)
        if not report:
            flash("工序报工单不存在。", "warning")
            return redirect("/production/operation-reports")
        if not can_edit_operation_report(report):
            flash("当前工序报工单不允许编辑；已审核回写或已作废单据为只读。", "warning")
            return redirect(f"/production/operation-reports/{report_id}")
        work_order_id = form_int("work_order_id")
        process_id = form_int("work_order_process_id") or form_int("process_id")
        wo = order(work_order_id)
        if not wo:
            flash("请选择有效工单。", "warning")
            return redirect(f"/production/operation-reports/{report_id}/edit")
        if (wo.get("status") or "") in FINAL_WORK_ORDER_STATUSES:
            flash("来源工单已关闭、已完工或已作废，不能编辑工序报工单。", "warning")
            return redirect(f"/production/operation-reports/{report_id}")
        process = safe_one("SELECT * FROM work_order_processes WHERE id=%s AND work_order_id=%s", (process_id, work_order_id)) if process_id else {}
        if not process:
            flash("请选择来源工单下的有效工序。", "warning")
            return redirect(f"/production/operation-reports/{report_id}/edit?work_order_id={work_order_id}")
        report_type = form_text("report_type", REPORT_TYPE_COMPLETE)
        good_qty = as_decimal(form_text("good_qty", "0"))
        rework_qty = as_decimal(form_text("rework_qty", "0"))
        scrap_qty = as_decimal(form_text("scrap_qty", "0"))
        if report_type in {REPORT_TYPE_COMPLETE, REPORT_TYPE_REWORK, REPORT_TYPE_SCRAP} and good_qty + rework_qty + scrap_qty <= 0:
            flash("完工、返工或报废报工必须填写数量。", "warning")
            return redirect(f"/production/operation-reports/{report_id}/edit")
        execute_db(
            """
            UPDATE operation_reports
            SET work_order_id=%s, work_order_process_id=%s, routing_operation_id=%s,
                report_type=%s, report_date=%s, operator_id=%s, work_center_id=%s,
                labor_hours=%s, equipment_hours=%s, good_qty=%s, rework_qty=%s, scrap_qty=%s,
                blocked_reason=%s, next_action=%s, downstream_impact=%s, project_code=%s, serial_no=%s, remark=%s
            WHERE id=%s
            """,
            (
                work_order_id,
                process_id,
                process.get("routing_operation_id"),
                report_type,
                form_text("report_date", datetime.now().date().isoformat()),
                session.get("user_id"),
                form_int("work_center_id") or process.get("work_center_id"),
                as_decimal(form_text("labor_hours", "0")),
                as_decimal(form_text("equipment_hours", "0")),
                good_qty,
                rework_qty,
                scrap_qty,
                form_text("blocked_reason"),
                form_text("next_action", next_action_for_type(report_type)),
                form_text("downstream_impact", execution_downstream_impact(report_type)),
                wo.get("project_code"),
                wo.get("serial_no"),
                form_text("remark"),
                report_id,
            ),
        )
        log_action("编辑工序报工", report.get("report_no"), f"id={report_id}")
        flash("工序报工单已保存修改。", "success")
        return redirect(f"/production/operation-reports/{report_id}")

    def edit_page(report_id):
        ensure_schema()
        report = report_row(report_id)
        if not report:
            flash("工序报工单不存在。", "warning")
            return redirect("/production/operation-reports")
        if not can_edit_operation_report(report):
            flash("当前工序报工单不允许编辑。", "warning")
            return redirect(f"/production/operation-reports/{report_id}")
        if request.method == "POST":
            return update_report(report_id)
        work_order_id = request.args.get("work_order_id") or report.get("work_order_id")
        return render_template(
            "operation_report_form.html",
            edit_mode=True,
            form_action=f"/production/operation-reports/{report_id}/edit",
            report=report,
            order=order(int(work_order_id)) if work_order_id else None,
            orders=open_orders(),
            processes=processes(int(work_order_id)) if work_order_id else [],
            process_id=report.get("work_order_process_id"),
            report_type=report.get("report_type") or REPORT_TYPE_COMPLETE,
            next_action_for_type=next_action_for_type,
            process_status_label=process_status_label,
        )

    def detail_page(report_id):
        ensure_schema()
        report = safe_one(
            """
            SELECT opr.*, wo.wo_no, wo.status AS work_order_status, wc.name AS work_center_name,
                   wop.operation_no, wop.operation_name, wop.status AS process_status,
                   wop.good_quantity AS process_good_quantity, wop.rework_quantity AS process_rework_quantity,
                   wop.scrap_quantity AS process_scrap_quantity
            FROM operation_reports opr
            LEFT JOIN work_orders wo ON wo.id=opr.work_order_id
            LEFT JOIN work_order_processes wop ON wop.id=opr.work_order_process_id
            LEFT JOIN work_centers wc ON wc.id=opr.work_center_id
            WHERE opr.id=%s
            """,
            (report_id,),
        )
        return render_template(
            "operation_report_detail.html",
            report=report,
            status_label=status_label,
            report_type_label=report_type_label,
            process_status_label=process_status_label,
        )

    def action(report_id, action_name):
        ensure_schema()
        report = safe_one("SELECT * FROM operation_reports WHERE id=%s", (report_id,))
        if not report:
            flash("工序报工单不存在。", "warning")
            return redirect("/production/operation-reports")
        label = status_label(report.get("status"))
        if action_name == "submit":
            if label == DOC_STATUS_DRAFT:
                execute_db(
                    "UPDATE operation_reports SET status=%s, submitted_by=%s, submitted_at=NOW() WHERE id=%s",
                    (DOC_STATUS_SUBMITTED, session.get("user_id"), report_id),
                )
                flash("工序报工已提交。", "success")
            else:
                flash("只有草稿状态可以提交。", "warning")
        elif action_name == "audit":
            if label != DOC_STATUS_SUBMITTED:
                flash("只有已提交的工序报工可以审核回写。", "warning")
                return redirect(f"/production/operation-reports/{report_id}")
            execute_db(
                "UPDATE operation_reports SET status=%s, audited_by=%s, audited_at=NOW() WHERE id=%s",
                (DOC_STATUS_AUDITED, session.get("user_id"), report_id),
            )
            if report.get("work_order_process_id"):
                refresh_process_progress(report.get("work_order_process_id"))
            flash("工序报工已审核并回写工序进度。", "success")
        elif action_name == "void":
            if label in {DOC_STATUS_DRAFT, DOC_STATUS_SUBMITTED}:
                execute_db(
                    "UPDATE operation_reports SET status=%s, voided_by=%s, voided_at=NOW() WHERE id=%s",
                    (DOC_STATUS_VOIDED, session.get("user_id"), report_id),
                )
                flash("工序报工已作废。", "success")
            else:
                flash("只有草稿或已提交状态可以作废。", "warning")
        else:
            flash("不支持的报工动作。", "warning")
        return redirect(f"/production/operation-reports/{report_id}")

    def execution_wip_page():
        ensure_schema()
        rows = safe_rows(
            """
            SELECT wop.*, wo.wo_no, wo.project_code, wo.serial_no,
                   wc.code AS work_center_code, wc.name AS work_center_name,
                   COALESCE(wop.wip_quantity, GREATEST(COALESCE(wop.planned_quantity,0)-COALESCE(wop.good_quantity,0)-COALESCE(wop.scrap_quantity,0),0)) AS open_wip_qty
            FROM work_order_processes wop
            LEFT JOIN work_orders wo ON wo.id=wop.work_order_id
            LEFT JOIN work_centers wc ON wc.id=wop.work_center_id
            WHERE COALESCE(wop.status,'not_started') NOT IN ('completed','cancelled')
               OR COALESCE(wop.rework_quantity,0) > 0
               OR COALESCE(wop.scrap_quantity,0) > 0
            ORDER BY wo.planned_end_date NULLS LAST, wo.id DESC, COALESCE(wop.sequence_no,wop.id), wop.id
            LIMIT 300
            """
        )
        return render_template("production_execution_wip.html", rows=rows, process_status_label=process_status_label)

    def capacity_load_page():
        ensure_schema()
        rows = safe_rows(
            """
            SELECT wc.id AS work_center_id, wc.code AS work_center_code, wc.name AS work_center_name,
                   ps.planned_start_date,
                   COUNT(ps.id) AS schedule_count,
                   COALESCE(SUM(COALESCE(ps.quantity, wop.planned_quantity, 0)),0) AS planned_qty,
                   COALESCE(SUM(COALESCE(wop.good_quantity,0)),0) AS good_qty,
                   COALESCE(SUM(COALESCE(wop.rework_quantity,0)),0) AS rework_qty,
                   COALESCE(SUM(COALESCE(wop.scrap_quantity,0)),0) AS scrap_qty,
                   COALESCE(SUM(COALESCE(wop.wip_quantity, GREATEST(COALESCE(wop.planned_quantity,0)-COALESCE(wop.good_quantity,0)-COALESCE(wop.scrap_quantity,0),0))),0) AS open_wip_qty,
                   MAX(NULLIF(ps.blocked_reason,'')) AS blocked_reason,
                   MAX(NULLIF(ps.next_action,'')) AS next_action,
                   MAX(NULLIF(ps.downstream_impact,'')) AS downstream_impact
            FROM production_schedules ps
            LEFT JOIN work_order_processes wop ON wop.id=ps.work_order_process_id
            LEFT JOIN work_centers wc ON wc.id=COALESCE(ps.work_center_id, wop.work_center_id)
            GROUP BY wc.id, wc.code, wc.name, ps.planned_start_date
            ORDER BY ps.planned_start_date NULLS LAST, wc.code NULLS LAST, wc.name NULLS LAST
            LIMIT 300
            """
        )
        return render_template("production_capacity_load.html", rows=rows)

    @app.get("/production/operation-reports", endpoint="operation_report_list")
    @login_required
    def operation_report_list():
        return list_page()

    @app.get("/production/execution-wip", endpoint="production_execution_wip")
    @login_required
    def production_execution_wip():
        return execution_wip_page()

    @app.get("/production/capacity-load", endpoint="production_capacity_load")
    @login_required
    def production_capacity_load():
        return capacity_load_page()

    @app.route("/production/operation-reports/new", methods=["GET", "POST"], endpoint="operation_report_new")
    @login_required
    def operation_report_new():
        return form_page()

    @app.get("/production/operation-reports/<int:report_id>", endpoint="operation_report_detail")
    @login_required
    def operation_report_detail(report_id):
        return detail_page(report_id)

    @app.route("/production/operation-reports/<int:report_id>/edit", methods=["GET", "POST"], endpoint="operation_report_edit")
    @login_required
    def operation_report_edit(report_id):
        return edit_page(report_id)

    @app.post("/production/operation-reports/<int:report_id>/<action_name>", endpoint="operation_report_action")
    @login_required
    def operation_report_action(report_id, action_name):
        return action(report_id, action_name)
