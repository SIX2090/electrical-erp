"""Production module routes: dashboard, work order list, work order form, and material requisition."""
from datetime import datetime
from decimal import Decimal

from flask import render_template

from .document_print_routes import build_template_grid_for_document

from services.work_order_material_service import (
    as_decimal,
    returnable_material_quantity,
    summarize_bom_requirement_generation,
    summarize_material_rows,
)
from services.work_order_snapshot_service import latest_work_order_execution_snapshot
from services.work_order_mrp_service import build_work_order_mrp_preview


def _money_metric(value):
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _bom_display_text(row):
    parts = [row.get("default_bom_no") or row.get("bom_no"), row.get("default_bom_version") or row.get("bom_version")]
    return " / ".join(str(part) for part in parts if part) or "-"


def _manufacturing_control_text(row):
    labels = []
    if row.get("batch_control"):
        labels.append("批次")
    if row.get("serial_control"):
        labels.append("序列")
    if row.get("inspection_required"):
        labels.append("需检")
    return " / ".join(labels) if labels else "-"


PRODUCTION_STAGES = ("创建", "排产", "待料", "投产", "加工", "暂停", "装配", "调试", "入库")


def _source_axis_text(row):
    parts = []
    if row.get("project_code"):
        parts.append(f"项目号 {row.get('project_code')}")
    if row.get("serial_no"):
        parts.append(f"机号 {row.get('serial_no')}")
    return " / ".join(parts) or "-"


def _decorate_work_order_source(row):
    sales_order_no = row.get("sales_order_no")
    source_line = row.get("sales_source_line_no") or row.get("source_line_no")
    bom_display = row.get("bom_display") or _bom_display_text(row)
    row["source_axis"] = _source_axis_text(row)
    row["source_line_display"] = source_line or "-"
    row["source_bom_display"] = bom_display
    if sales_order_no:
        row["source_document"] = f"销售订单 {sales_order_no}"
        row["source_trace_status"] = "已关联销售来源"
        row["source_next_step"] = "按销售需求核对BOM、齐套、领料和完工"
        row["source_owner_role"] = "生产计划"
    elif row.get("project_code") or row.get("serial_no"):
        row["source_document"] = "项目需求"
        row["source_trace_status"] = "待补销售订单"
        row["source_next_step"] = "补齐销售订单或工程确认来源，继续按项目轴推进"
        row["source_owner_role"] = "生产计划/销售"
    else:
        row["source_document"] = "未关联来源"
        row["source_trace_status"] = "来源缺失"
        row["source_next_step"] = "补录销售订单、项目号、机号、BOM和来源行"
        row["source_owner_role"] = "生产计划"
        row["blocked_reason"] = "缺少销售/项目来源，需先补齐追溯轴"
        row["downstream_impact"] = "影响领料、完工入库、发货、服务和成本追溯"
    return row


def _production_stage_from_row(row):
    stage = (row.get("production_stage") or "").strip()
    status = (row.get("status") or "").strip()
    status_stage = {
        "新建": "创建",
        "创建": "创建",
        "已排产": "排产",
        "排产": "排产",
        "待排产": "排产",
        "待料": "待料",
        "缺料": "待料",
        "投产": "投产",
        "已投产": "投产",
        "加工": "加工",
        "生产中": "加工",
        "暂停": "暂停",
        "已暂停": "暂停",
        "装配": "装配",
        "调试": "调试",
        "部分完工": "调试",
        "入库": "入库",
        "已完工": "入库",
        "已完成": "入库",
        "completed": "入库",
        "closed": "入库",
    }.get(status)
    if stage in PRODUCTION_STAGES and not status_stage:
        return stage
    if stage in PRODUCTION_STAGES and status_stage:
        return PRODUCTION_STAGES[max(PRODUCTION_STAGES.index(stage), PRODUCTION_STAGES.index(status_stage))]
    return status_stage or "创建"


def _schedule_compare_text(row):
    planned_start = row.get("planned_start_date") or "-"
    planned_end = row.get("planned_end_date") or "-"
    actual_start = row.get("actual_start_date") or "-"
    actual_end = row.get("actual_end_date") or "-"
    planned_end_date = row.get("planned_end_date")
    actual_end_date = row.get("actual_end_date")
    if actual_end_date and planned_end_date and actual_end_date > planned_end_date:
        result = "延期完成"
    elif not actual_end_date and planned_end_date and planned_end_date < datetime.now().date():
        result = "已逾期"
    elif row.get("actual_start_date") and not actual_end_date:
        result = "执行中"
    elif actual_end_date:
        result = "按期核对"
    else:
        result = "未开始"
    return f"计划 {planned_start} 至 {planned_end} / 实际 {actual_start} 至 {actual_end} / {result}"


def _decorate_work_order_progress(order, subcontract_rows):
    stage = _production_stage_from_row(order)
    order["production_stage"] = stage
    order["stage_items"] = [
        {
            "label": item,
            "state": "done" if PRODUCTION_STAGES.index(item) < PRODUCTION_STAGES.index(stage)
            else ("current" if item == stage else "pending"),
        }
        for item in PRODUCTION_STAGES
    ]
    planned_end = order.get("planned_end_date")
    actual_end = order.get("actual_end_date")
    if actual_end and planned_end and actual_end > planned_end:
        order["delivery_warning"] = f"实际完工晚于计划 {planned_end}"
    elif not actual_end and planned_end and planned_end < datetime.now().date():
        order["delivery_warning"] = f"计划完工已逾期：{planned_end}"
    elif any((row.get("arrival_warning") or "").strip() for row in subcontract_rows or []):
        order["delivery_warning"] = "存在委外未到货或逾期，可能影响交付"
    else:
        order["delivery_warning"] = "暂无交期预警"
    order["schedule_compare"] = _schedule_compare_text(order)


def _decorate_subcontract_arrival(row):
    ordered_qty = as_decimal(row.get("quantity"))
    issued_qty = as_decimal(row.get("issued_qty"))
    received_qty = as_decimal(row.get("received_qty"))
    scrap_qty = as_decimal(row.get("scrap_qty"))
    pending_qty = max(ordered_qty - received_qty - scrap_qty, Decimal("0"))
    today = datetime.now().date()
    row["received_qty"] = received_qty
    row["scrap_qty"] = scrap_qty
    row["short_receipt_qty"] = pending_qty
    row["shortage_qty"] = pending_qty
    row["gap_qty"] = pending_qty
    if issued_qty <= 0:
        row["arrival_status"] = "未发料"
    elif ordered_qty > 0 and pending_qty > 0 and received_qty > 0:
        row["arrival_status"] = "部分到货"
    elif ordered_qty > 0 and pending_qty <= 0:
        row["arrival_status"] = "已到货"
    else:
        row["arrival_status"] = "在外协"
    required_date = row.get("required_date")
    row["overdue_days"] = (today - required_date).days if pending_qty > 0 and required_date and required_date < today else 0
    if pending_qty > 0 and required_date and required_date < today:
        row["arrival_warning"] = f"委外逾期未齐：缺 {pending_qty}"
    elif pending_qty > 0:
        row["arrival_warning"] = f"委外未齐：缺 {pending_qty}"
    else:
        row["arrival_warning"] = ""
    if issued_qty <= 0:
        row["next_step"] = "按委外发料单发料"
        row["owner_role"] = "仓库/委外"
        row["blocked_reason"] = "委外订单未发料"
        row["downstream_impact"] = "外协加工未启动，影响工单装配和项目交付"
    elif pending_qty > 0 and row["overdue_days"]:
        row["next_step"] = "催收到货或登记短收/报废"
        row["owner_role"] = "委外采购/生产计划"
        row["blocked_reason"] = f"要求到货日已逾期 {row['overdue_days']} 天"
        row["downstream_impact"] = "影响工单齐套、完工入库、发货和成本归集"
    elif pending_qty > 0:
        row["next_step"] = "跟进外协到货"
        row["owner_role"] = "委外采购"
        row["blocked_reason"] = "委外到货未齐"
        row["downstream_impact"] = "可能影响后续装配、调试和发货"
    else:
        row["next_step"] = "核对入库、质检和应付"
        row["owner_role"] = "仓库/质量/财务"
        row["blocked_reason"] = "委外已到齐，等待闭环核对"
        row["downstream_impact"] = "支撑工单完工、外协应付和成本结转"


def _quality_type_display(value):
    text = (value or "").strip()
    mapping = {
        "debug": "调试",
        "trial_run": "调试",
        "final": "终检",
        "in_process": "过程检验",
        "key_control": "关键控制点",
        "critical_control_point": "关键控制点",
    }
    return mapping.get(text.lower(), text or "终检")


def _quality_result_display(value):
    text = (value or "").strip()
    mapping = {
        "pass": "合格",
        "passed": "合格",
        "ok": "合格",
        "fail": "不合格",
        "failed": "不合格",
        "ng": "不合格",
        "conditional_pass": "让步放行",
    }
    return mapping.get(text.lower(), text or "未判定")


def _decorate_quality_rows(rows):
    for row in rows or []:
        result_key = (row.get("inspection_result") or "").strip().lower()
        failed_qty = as_decimal(row.get("failed_quantity"))
        row["inspection_type_display"] = _quality_type_display(row.get("inspection_type"))
        row["inspection_result_display"] = _quality_result_display(row.get("inspection_result"))
        if result_key in {"fail", "failed", "ng", "不合格"} or failed_qty > 0:
            row["release_status"] = "未放行"
            row["unreleased_reason"] = row.get("defect_description") or "存在不合格数量，需先完成不合格处理或让步评审。"
            row["owner_role"] = "质量/生产"
            row["next_step"] = row.get("corrective_action") or "登记返工、让步接收或报废处理结论"
        elif result_key == "conditional_pass":
            row["release_status"] = "让步放行"
            row["unreleased_reason"] = row.get("defect_description") or "按让步接收条件跟踪。"
            row["owner_role"] = "质量"
            row["next_step"] = row.get("corrective_action") or "跟踪让步条件并保留质量记录"
        elif result_key in {"pass", "passed", "ok", "合格"}:
            row["release_status"] = "已放行"
            row["unreleased_reason"] = ""
            row["owner_role"] = "质量"
            row["next_step"] = "核对完工入库、项目机号和质量记录"
        else:
            row["release_status"] = "待判定"
            row["unreleased_reason"] = "质检结果未判定。"
            row["owner_role"] = "质量"
            row["next_step"] = "补录检验结论和处理措施"
    return rows


def _build_quality_summary(order, quality_rows, completions):
    total_sample = sum((as_decimal(row.get("sample_size")) for row in quality_rows), Decimal("0"))
    total_passed = sum((as_decimal(row.get("passed_quantity")) for row in quality_rows), Decimal("0"))
    total_failed = sum((as_decimal(row.get("failed_quantity")) for row in quality_rows), Decimal("0"))
    if not quality_rows:
        timing = "完工入库后" if completions else "完工入库前"
        return {
            "release_status": "未登记",
            "unreleased_reason": f"当前工单没有质量记录，{timing}需要登记调试、终检或关键控制点质检。",
            "owner_role": "质量",
            "next_step": "补录质检记录后再核对完工入库和项目机号追溯",
            "downstream_impact": "仅提示质量放行风险，不阻断现有工单操作。",
            "sample_size": total_sample,
            "passed_quantity": total_passed,
            "failed_quantity": total_failed,
        }
    if any(row.get("release_status") == "未放行" for row in quality_rows):
        first_blocked = next(row for row in quality_rows if row.get("release_status") == "未放行")
        release_status = "未放行"
        unreleased_reason = first_blocked.get("unreleased_reason") or "存在不合格质检记录。"
        owner_role = "质量/生产"
        next_step = first_blocked.get("next_step") or "完成不合格处理并复核放行"
    elif any(row.get("release_status") == "待判定" for row in quality_rows):
        release_status = "待判定"
        unreleased_reason = "存在未判定质检记录。"
        owner_role = "质量"
        next_step = "补齐检验结论和处理措施"
    elif any(row.get("release_status") == "让步放行" for row in quality_rows):
        release_status = "让步放行"
        unreleased_reason = "存在让步接收记录，需跟踪处理措施。"
        owner_role = "质量"
        next_step = "跟踪让步条件并核对完工入库"
    else:
        release_status = "已放行"
        unreleased_reason = ""
        owner_role = "质量"
        next_step = "核对完工入库、项目机号和质量记录"
    return {
        "release_status": release_status,
        "unreleased_reason": unreleased_reason,
        "owner_role": owner_role,
        "next_step": next_step,
        "downstream_impact": "影响完工入库后的项目追溯、服务和成本闭环。",
        "sample_size": total_sample,
        "passed_quantity": total_passed,
        "failed_quantity": total_failed,
    }


def _decorate_manufacturing_rows(rows):
    for row in rows or []:
        row["bom_display"] = _bom_display_text(row)
        row["control_display"] = _manufacturing_control_text(row)
    return rows


def _table_columns(query_rows, table_name):
    rows = query_rows(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    return {row.get("column_name") for row in rows or []}


def _column_expr(columns, candidates, alias, default="NULL"):
    for column in candidates:
        if column in columns:
            return f"{column} AS {alias}"
    return f"{default} AS {alias}"


def _optional_table_exists(table_name, query_one):
    try:
        row = query_one("SELECT to_regclass(%s) AS table_name", (table_name,))
    except Exception:
        return False
    return bool(row and row.get("table_name"))


def _sum_cost_lines(cost_lines, keywords):
    total = Decimal("0")
    for row in cost_lines or []:
        cost_text = " ".join(
            str(row.get(field) or "").lower()
            for field in ("cost_type", "source_type", "remark")
        )
        if any(keyword in cost_text for keyword in keywords):
            total += as_decimal(row.get("amount"))
    return total


def _load_operation_report_cost_summary(query_rows, work_order_id):
    columns = _table_columns(query_rows, "operation_reports")
    if not columns or "work_order_id" not in columns:
        return {
            "report_count": 0,
            "pending_count": 0,
            "labor_hours": Decimal("0"),
            "equipment_hours": Decimal("0"),
            "labor_cost": Decimal("0"),
            "equipment_cost": Decimal("0"),
            "basis": "未发现工序报工单",
        }

    labor_hours = "COALESCE(opr.labor_hours, 0)" if "labor_hours" in columns else "0"
    equipment_hours = "COALESCE(opr.equipment_hours, 0)" if "equipment_hours" in columns else "0"
    work_center_join = ""
    labor_rate = "0"
    overhead_rate = "0"
    work_center_columns = _table_columns(query_rows, "work_centers")
    if "work_center_id" in columns and work_center_columns:
        work_center_join = "LEFT JOIN work_centers wc ON wc.id=opr.work_center_id"
        if "labor_rate_per_hour" in work_center_columns:
            labor_rate = "COALESCE(wc.labor_rate_per_hour, 0)"
        if "overhead_rate_per_hour" in work_center_columns:
            overhead_rate = "COALESCE(wc.overhead_rate_per_hour, 0)"

    employee_join = ""
    employee_rate = labor_rate
    employee_columns = _table_columns(query_rows, "employees")
    if "operator_id" in columns and employee_columns:
        employee_join = "LEFT JOIN employees emp ON emp.id=opr.operator_id"
        if "standard_labor_rate_per_hour" in employee_columns:
            employee_rate = f"COALESCE(emp.standard_labor_rate_per_hour, {labor_rate}, 0)"

    status_expr = "COALESCE(opr.status, '')" if "status" in columns else "''"
    rows = query_rows(
        f"""
        SELECT COUNT(*) AS report_count,
               COUNT(*) FILTER (WHERE {status_expr} NOT IN ('已审核','audited')) AS pending_count,
               COALESCE(SUM({labor_hours}), 0) AS labor_hours,
               COALESCE(SUM({equipment_hours}), 0) AS equipment_hours,
               COALESCE(SUM(({labor_hours}) * ({employee_rate})), 0) AS labor_cost,
               COALESCE(SUM(({equipment_hours}) * ({overhead_rate})), 0) AS equipment_cost
        FROM operation_reports opr
        {work_center_join}
        {employee_join}
        WHERE opr.work_order_id=%s
          AND {status_expr} NOT IN ('已作废','已取消','作废','void','cancelled')
        """,
        (work_order_id,),
    )
    summary = dict(rows[0]) if rows else {}
    labor_hours_value = as_decimal(summary.get("labor_hours"))
    equipment_hours_value = as_decimal(summary.get("equipment_hours"))
    pending_count = int(summary.get("pending_count") or 0)
    basis = "工序报工工时 x 员工/工作中心费率"
    if pending_count:
        basis += "；存在未审核报工"
    if labor_hours_value == 0 and equipment_hours_value == 0:
        basis = "报工单未登记人工/设备工时"
    return {
        "report_count": int(summary.get("report_count") or 0),
        "pending_count": pending_count,
        "labor_hours": labor_hours_value,
        "equipment_hours": equipment_hours_value,
        "labor_cost": as_decimal(summary.get("labor_cost")),
        "equipment_cost": as_decimal(summary.get("equipment_cost")),
        "basis": basis,
    }


def _build_work_order_cost_reconciliation(order, material_items, subcontract_rows, completions, cost, cost_lines, operation_cost_summary=None):
    operation_cost_summary = operation_cost_summary or {}
    material_issue_cost = sum(
        (as_decimal(row.get("issued_qty")) * as_decimal(row.get("unit_cost")) for row in material_items),
        Decimal("0"),
    )
    material_return_credit = sum(
        (as_decimal(row.get("returned_qty")) * as_decimal(row.get("unit_cost")) for row in material_items),
        Decimal("0"),
    )
    material_net_cost = material_issue_cost - material_return_credit
    subcontract_cost = sum((as_decimal(row.get("total_amount")) for row in subcontract_rows), Decimal("0"))
    completion_inbound_cost = sum(
        (as_decimal(row.get("qty")) * as_decimal(row.get("unit_cost")) for row in completions),
        Decimal("0"),
    )

    reported_labor_cost = as_decimal(operation_cost_summary.get("labor_cost"))
    reported_equipment_cost = as_decimal(operation_cost_summary.get("equipment_cost"))
    stored_labor_cost = as_decimal(cost.get("labor_cost")) if cost else Decimal("0")
    stored_overhead_cost = as_decimal(cost.get("overhead_cost")) if cost else Decimal("0")
    line_labor_cost = _sum_cost_lines(cost_lines, ("labor", "人工", "工时"))
    line_equipment_cost = _sum_cost_lines(cost_lines, ("equipment", "machine", "overhead", "设备", "制造费用"))
    labor_cost = reported_labor_cost or stored_labor_cost or line_labor_cost
    equipment_cost = reported_equipment_cost or stored_overhead_cost or line_equipment_cost
    stored_material_cost = as_decimal(cost.get("material_cost")) if cost else Decimal("0")
    stored_subcontract_cost = as_decimal(cost.get("subcontract_cost")) if cost else Decimal("0")
    stored_total_cost = as_decimal(cost.get("total_cost")) if cost else Decimal("0")
    if stored_material_cost and material_net_cost == 0:
        material_net_cost = stored_material_cost
    if stored_subcontract_cost and subcontract_cost == 0:
        subcontract_cost = stored_subcontract_cost

    input_cost = material_net_cost + subcontract_cost + labor_cost + equipment_cost
    reference_total_cost = stored_total_cost if stored_total_cost else input_cost
    variance = reference_total_cost - completion_inbound_cost

    pending_material_qty = sum((as_decimal(row.get("shortage_qty")) for row in material_items), Decimal("0"))
    subcontract_pending = [
        row for row in subcontract_rows
        if as_decimal(row.get("received_qty")) < as_decimal(row.get("quantity"))
    ]
    has_cost_lines = bool(cost_lines)
    has_operation_reports = int(operation_cost_summary.get("report_count") or 0) > 0
    pending_operation_reports = int(operation_cost_summary.get("pending_count") or 0)
    has_labor_or_equipment = labor_cost != 0 or equipment_cost != 0
    blockers = []

    if not completions:
        reconcile_status = "待完工入库"
        pending_reason = "尚未登记完工入库，成本只能核到投入端"
        owner = "生产"
        next_action = "登记合格数量、批号/机号和完工入库成本"
        blockers.append("未登记完工入库")
    elif pending_material_qty > 0:
        reconcile_status = "待领料齐套"
        pending_reason = "存在未领材料，投入成本尚未完整"
        owner = "仓库/生产"
        next_action = "补齐领料或确认不再需要并记录原因"
        blockers.append("存在未领材料")
    elif subcontract_pending:
        reconcile_status = "委外待收"
        pending_reason = "委外加工未全部收回或存在报废短收"
        owner = "委外/采购"
        next_action = "核对委外收回、报废短收和应付金额"
        blockers.append("委外加工未全部收回")
    elif pending_operation_reports:
        reconcile_status = "报工待审"
        pending_reason = "存在未审核工序报工，人工和设备成本仍需确认"
        owner = "生产/财务"
        next_action = "审核工序报工并确认工时费率"
        blockers.append("存在未审核报工")
    elif variance != 0:
        reconcile_status = "差异待核"
        pending_reason = "投入成本与完工入库成本不一致"
        owner = "财务/生产"
        next_action = "核对领退补料、委外金额、人工制造费用和完工单价"
        blockers.append("归集成本与完工入库成本存在差异")
    elif not has_cost_lines and not has_labor_or_equipment and not has_operation_reports:
        reconcile_status = "待成本归集"
        pending_reason = "未发现成本明细行或工序报工，人工/设备成本尚未归集"
        owner = "生产/财务"
        next_action = "补录工序报工或按费用分摊规则登记成本明细"
        blockers.append("未发现人工/设备成本归集依据")
    else:
        reconcile_status = "已平衡"
        pending_reason = "投入成本与完工入库成本一致"
        owner = "财务"
        next_action = "复核后进入工单关闭和项目成本结转"

    has_formal_cost = bool(cost) and (stored_total_cost != 0 or bool(cost.get("last_calculated_at")))
    if blockers:
        collection_status = "归集受阻"
        collection_action = "先处理阻断项，再由生产复核来源单据，财务复核金额口径"
        settlement_status = "暂缓结转"
        settlement_advice = "不得结转到财务成本报表；仅作为工单成本核对草稿"
        settlement_blocked_reason = "；".join(blockers)
    elif not has_formal_cost:
        collection_status = "可归集待确认"
        collection_action = "生产确认领退料、委外、报工和完工入库均已完整，财务按受控流程确认成本归集"
        settlement_status = "建议结转待财务确认"
        settlement_advice = "可作为项目/机号成本结转建议；财务在财务模块受控确认，不在生产页面过账"
        settlement_blocked_reason = "无硬阻断，缺少正式成本归集确认记录"
    else:
        collection_status = "已正式归集"
        collection_action = "保留来源单据和成本明细，进入工单关闭、项目成本和期间结账核对"
        settlement_status = "可结转复核"
        settlement_advice = "财务只读核对后按受控结转流程处理；本页不生成总账凭证"
        settlement_blocked_reason = "无"

    if variance == 0:
        variance_adjustment_suggestion = "无差异调整建议"
    elif variance > 0:
        variance_adjustment_suggestion = "归集成本高于完工入库成本，建议复核完工单价、超耗补料、委外短收和制造费用分摊"
    else:
        variance_adjustment_suggestion = "完工入库成本高于归集成本，建议复核漏领料、漏报工、委外应付和入库成本单价"

    operation_basis = operation_cost_summary.get("basis") or "工序报工工时 x 费率"
    rows = [
        {"label": "材料领用成本", "amount": material_issue_cost, "basis": "已领数量 x 库存成本单价", "owner": "仓库/生产", "status": "已领用" if material_issue_cost else "未领用", "next_action": "核对生产领料单和库存流水"},
        {"label": "退料抵减", "amount": -material_return_credit, "basis": "已退数量 x 原领用成本单价", "owner": "仓库", "status": "有退料" if material_return_credit else "无退料", "next_action": "核对生产退料单"},
        {"label": "材料净投入", "amount": material_net_cost, "basis": "领用成本 - 退料抵减", "owner": "生产/财务", "status": "待齐套" if pending_material_qty > 0 else "已核入", "next_action": "核对缺料和超领原因"},
        {"label": "委外成本", "amount": subcontract_cost, "basis": "关联委外订单金额；收回状态用于闭环判断", "owner": "委外/采购", "status": "委外待收" if subcontract_pending else ("已核入" if subcontract_cost else "无委外"), "next_action": "核对委外发出、收回、报废短收和应付"},
        {"label": "报工人工成本", "amount": labor_cost, "basis": operation_basis, "owner": "生产/财务", "status": "报工待审" if pending_operation_reports else ("已核入" if labor_cost else "未归集"), "next_action": "审核报工并确认员工/工作中心工时费率"},
        {"label": "报工设备/制造费用", "amount": equipment_cost, "basis": operation_basis, "owner": "生产/财务", "status": "报工待审" if pending_operation_reports else ("已核入" if equipment_cost else "未归集"), "next_action": "确认设备工时和工作中心制造费用费率"},
        {"label": "完工入库成本", "amount": completion_inbound_cost, "basis": "完工数量 x 入库成本单价", "owner": "生产/仓库", "status": "已入库" if completions else "待入库", "next_action": "核对完工入库单、批号/机号和库存流水"},
        {"label": "差异/待核金额", "amount": variance, "basis": "归集成本 - 完工入库成本", "owner": owner, "status": "需调整建议" if variance else "无差异", "next_action": variance_adjustment_suggestion},
    ]
    return {
        "rows": rows,
        "input_cost": input_cost,
        "stored_total_cost": stored_total_cost,
        "reference_total_cost": reference_total_cost,
        "completion_inbound_cost": completion_inbound_cost,
        "variance": variance,
        "operation_report_count": operation_cost_summary.get("report_count") or 0,
        "operation_report_pending_count": pending_operation_reports,
        "operation_labor_hours": operation_cost_summary.get("labor_hours") or Decimal("0"),
        "operation_equipment_hours": operation_cost_summary.get("equipment_hours") or Decimal("0"),
        "reconcile_status": reconcile_status,
        "collection_status": collection_status,
        "collection_action": collection_action,
        "settlement_status": settlement_status,
        "settlement_advice": settlement_advice,
        "settlement_blocked_reason": settlement_blocked_reason,
        "variance_adjustment_suggestion": variance_adjustment_suggestion,
        "finance_control_note": "生产详情只提供成本归集核对和结转建议；财务确认、期间结账和总账凭证不在本页写入。",
        "pending_reason": pending_reason,
        "owner": owner,
        "next_action": next_action,
        "last_calculated_at": cost.get("last_calculated_at") if cost else None,
        "downstream_impact": "影响项目成本、完工入库价值、发货毛利和期间结账",
    }


def build_work_order_completion_gate(order, material_items, quality_rows, processes, mrp_rows, completions, stock_rows=None, candidate=None):
    blockers = []
    warnings = []
    candidate = candidate or {}
    stock_rows = stock_rows or []
    status = (order.get("status") or "").strip()
    final_statuses = {"已完工", "已关闭", "已作废", "已取消", "closed", "completed", "void", "cancelled"}
    if status in final_statuses:
        blockers.append(f"工单状态为 {status}，不能继续完工入库。")

    target_qty = as_decimal(order.get("quantity"))
    completed_qty = sum((as_decimal(row.get("qty")) for row in completions), Decimal("0"))
    remaining_qty = target_qty - completed_qty if target_qty > 0 else Decimal("0")
    candidate_qty = as_decimal(candidate.get("quantity")) if candidate.get("quantity") is not None else remaining_qty
    warehouse_id = candidate.get("warehouse_id") or order.get("warehouse_id")
    if not order.get("product_id"):
        blockers.append("工单未指定产成品物料，不能生成完工入库流水。")
    if not warehouse_id:
        blockers.append("完工入库仓库未指定，请先在工单或本次入库动作中选择仓库。")
    if candidate_qty <= 0:
        blockers.append("本次完工数量必须大于 0。")
    if target_qty > 0 and completed_qty + candidate_qty > target_qty:
        blockers.append(f"本次完工后将超过工单计划数量，计划 {target_qty}，已完工 {completed_qty}，本次 {candidate_qty}。")

    if not material_items:
        blockers.append("工单没有领料需求，请先按 BOM 生成或手工补齐工单用料。")
    else:
        pending_lines = [row for row in material_items if as_decimal(row.get("shortage_qty")) > 0]
        if pending_lines:
            pending_qty = sum((as_decimal(row.get("shortage_qty")) for row in pending_lines), Decimal("0"))
            blockers.append(f"仍有 {len(pending_lines)} 行物料未领齐，未领数量 {pending_qty}。")

    shortage_rows = [row for row in mrp_rows if as_decimal(row.get("shortage_quantity")) > 0]
    if shortage_rows:
        shortage_qty = sum((as_decimal(row.get("shortage_quantity")) for row in shortage_rows), Decimal("0"))
        blockers.append(f"MRP/齐套仍有 {len(shortage_rows)} 行缺料，缺料数量 {shortage_qty}。")

    release_ok = False
    release_warning = ""
    if quality_rows:
        for row in quality_rows:
            result = (row.get("inspection_result") or "").lower()
            status_text = (row.get("status") or "").lower()
            passed = result in {"pass", "passed", "合格", "conditional_pass", "让步放行", "让步接收"}
            released = status_text in {"audited", "closed", "completed", "已审核", "已关闭", "已完成"}
            if passed and released:
                release_ok = True
                if result in {"conditional_pass", "让步放行", "让步接收"}:
                    release_warning = "质检为让步放行，入库后需在质量和成本中保留追溯。"
                break
        if any((row.get("inspection_result") or "").lower() in {"fail", "failed", "ng", "不合格"} for row in quality_rows):
            blockers.append("存在不合格质检记录，不能完工入库。")
    if not release_ok:
        blockers.append("未找到已放行的完工/终检记录，请先完成质检判定。")
    elif release_warning:
        warnings.append(release_warning)

    actual_processes = [row for row in processes if not row.get("from_routing_reference")]
    if actual_processes:
        unfinished = [
            row for row in actual_processes
            if (row.get("status") or "") not in {"已完成", "完成", "completed", "closed", "已关闭"}
            or (as_decimal(row.get("planned_quantity")) > 0 and as_decimal(row.get("actual_quantity") or row.get("good_quantity")) < as_decimal(row.get("planned_quantity")))
        ]
        qc_blocked = [row for row in actual_processes if (row.get("qc_status") or "") in {"待检", "未放行", "不合格"}]
        if unfinished:
            blockers.append(f"仍有 {len(unfinished)} 道工序未完成或报工数量不足。")
        if qc_blocked:
            blockers.append(f"仍有 {len(qc_blocked)} 道工序过程检未放行。")
    else:
        warnings.append("尚未生成工单工序执行计划；如该工单需要工序报工，请先生成工序。")

    if candidate.get("complete_date"):
        duplicate_key = (
            candidate.get("complete_date"),
            candidate_qty,
            candidate.get("lot_no") or "",
            candidate.get("serial_no") or order.get("serial_no") or "",
            candidate.get("warehouse_id") or order.get("warehouse_id"),
            candidate.get("location_id") or order.get("location_id"),
        )
        for row in completions:
            row_key = (
                row.get("complete_date"),
                as_decimal(row.get("qty")),
                row.get("lot_no") or "",
                row.get("serial_no") or "",
                row.get("warehouse_id") or order.get("warehouse_id"),
                row.get("location_id") or order.get("location_id"),
            )
            if row_key == duplicate_key:
                blockers.append("存在相同日期、数量、批号、机号、仓库和库位的完工记录，请核对是否重复入库。")
                break
    if len([row for row in stock_rows if row.get("transaction_type") == "工单完工入库"]) and not completions:
        blockers.append("存在工单完工入库库存流水但没有完工明细，请先核对库存流水。")

    return {
        "can_complete": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "owner": "生产" if not blockers else "生产/仓库/质量",
        "next_action": "可按本次合格数量办理完工入库" if not blockers else "按阻断原因补齐产成品、仓库、领料、工序和质检后再办理完工入库",
        "downstream_impact": "写入工单完工入库明细、库存流水和库存余额，并回写工单累计完工数量与状态。",
        "remaining_qty": remaining_qty if remaining_qty > 0 else Decimal("0"),
        "candidate_qty": candidate_qty,
        "completed_qty": completed_qty,
        "target_qty": target_qty,
        "status_label": "可入库" if not blockers else "不可入库",
    }


def _decorate_operation_rows(rows, order):
    total_qty = as_decimal(order.get("quantity"))
    for index, row in enumerate(rows or [], start=1):
        planned_qty = as_decimal(row.get("planned_quantity"))
        actual_qty = as_decimal(row.get("actual_quantity"))
        status = (row.get("status") or "").strip()
        row["line_no"] = row.get("sequence") or index
        row["operation_display"] = " / ".join(
            str(part) for part in [row.get("operation_no"), row.get("operation_name")] if part
        ) or "-"
        row["work_center_display"] = " / ".join(
            str(part) for part in [row.get("work_center_code"), row.get("work_center_name")] if part
        ) or "-"
        row["planned_quantity"] = planned_qty if planned_qty > 0 else total_qty
        row["actual_quantity"] = actual_qty
        if not status:
            if actual_qty >= row["planned_quantity"] and row["planned_quantity"] > 0:
                status = "已完成"
            elif actual_qty > 0:
                status = "执行中"
            else:
                status = "待执行"
        row["status"] = status
        row["owner_display"] = row.get("owner_name") or row.get("owner_role") or row.get("responsible_person") or "生产"
        if status in {"已完成", "完成", "completed", "closed"}:
            row["next_action"] = "核对质量记录与完工数量"
        elif actual_qty > 0:
            row["next_action"] = "继续完成本工序并交接下道"
        else:
            row["next_action"] = "按计划开工并记录实际数量"
        row["source_type"] = row.get("source_type") or "工单工序"
    return rows


def _load_work_order_operations(query_rows, order):
    work_order_id = order.get("id")
    operation_columns = _table_columns(query_rows, "work_order_operations")
    if operation_columns and ({"work_order_id", "wo_id"} & operation_columns):
        work_order_key = "work_order_id" if "work_order_id" in operation_columns else "wo_id"
        routing_operation_key = next(
            (col for col in ("routing_operation_id", "operation_id", "routing_op_id") if col in operation_columns),
            None,
        )
        work_center_key = "work_center_id" if "work_center_id" in operation_columns else None
        select_parts = [
            _column_expr(operation_columns, ("sequence", "operation_seq", "seq", "line_no"), "sequence"),
            _column_expr(operation_columns, ("operation_no", "op_no", "code"), "operation_no"),
            _column_expr(operation_columns, ("operation_name", "process_name", "name"), "operation_name"),
            _column_expr(operation_columns, ("planned_quantity", "planned_qty", "plan_qty", "quantity"), "planned_quantity", "0"),
            _column_expr(operation_columns, ("actual_quantity", "actual_qty", "completed_qty", "reported_qty"), "actual_quantity", "0"),
            _column_expr(operation_columns, ("status", "operation_status"), "status", "''"),
            _column_expr(operation_columns, ("owner_role", "owner", "responsible_person", "assigned_to_name"), "owner_role", "''"),
            _column_expr(operation_columns, ("planned_start_date", "plan_start_date", "start_date"), "planned_start_date"),
            _column_expr(operation_columns, ("planned_end_date", "plan_end_date", "end_date"), "planned_end_date"),
            _column_expr(operation_columns, ("actual_start_date", "actual_start_date"), "actual_start_date"),
            _column_expr(operation_columns, ("actual_end_date", "actual_end_date"), "actual_end_date"),
            _column_expr(operation_columns, ("remark", "note", "process_note"), "operation_remark"),
        ]
        routing_join = f"LEFT JOIN routing_operations ro ON ro.id=woo.{routing_operation_key}" if routing_operation_key else "LEFT JOIN routing_operations ro ON FALSE"
        center_join = (
            f"LEFT JOIN work_centers wc ON wc.id=COALESCE(woo.{work_center_key}, ro.work_center_id)"
            if work_center_key
            else "LEFT JOIN work_centers wc ON wc.id=ro.work_center_id"
        )
        order_candidates = [col for col in ("sequence", "operation_seq", "seq", "line_no", "id") if col in operation_columns]
        order_expr = ", ".join(f"woo.{col}" for col in order_candidates) or "woo.id"
        rows = query_rows(
            f"""
            SELECT {", ".join("woo." + part if " AS " in part and not part.startswith("NULL") and not part.startswith("0") and not part.startswith("''") else part for part in select_parts)},
                   COALESCE(wc.code, '') AS work_center_code,
                   COALESCE(wc.name, '') AS work_center_name,
                   COALESCE(wc.responsible_person, '') AS responsible_person,
                   '工单工序' AS source_type
            FROM work_order_operations woo
            {routing_join}
            {center_join}
            WHERE woo.{work_order_key}=%s
            ORDER BY {order_expr}
            LIMIT 80
            """,
            (work_order_id,),
        )
        if rows:
            return _decorate_operation_rows(rows, order), False

    process_columns = _table_columns(query_rows, "work_order_processes")
    if process_columns and "work_order_id" in process_columns:
        process_operation_columns = _table_columns(query_rows, "process_operations")
        po_operation_no = _column_expr(process_operation_columns, ("operation_no", "op_no", "code"), "operation_no", "''")
        po_operation_name = _column_expr(process_operation_columns, ("operation_name", "process_name", "name"), "operation_name", "''")
        po_remark = _column_expr(process_operation_columns, ("remark", "note", "process_note"), "operation_remark", "''")
        rows = query_rows(
            f"""
            SELECT wp.id AS line_no, wp.planned_start_date, wp.planned_end_date, wp.actual_start_date, wp.actual_end_date,
                   wp.planned_quantity, wp.actual_quantity, wp.status, u.username AS owner_name,
                   {("po." + po_operation_no) if not po_operation_no.startswith("''") else po_operation_no},
                   {("po." + po_operation_name) if not po_operation_name.startswith("''") else po_operation_name},
                   po.work_center_id,
                   wc.code AS work_center_code, wc.name AS work_center_name, wc.responsible_person,
                   {("po." + po_remark) if not po_remark.startswith("''") else po_remark}, '工单工序' AS source_type
            FROM work_order_processes wp
            LEFT JOIN process_operations po ON po.id=wp.process_operation_id
            LEFT JOIN work_centers wc ON wc.id=po.work_center_id
            LEFT JOIN users u ON u.id=wp.assigned_to
            WHERE wp.work_order_id=%s
            ORDER BY wp.id
            LIMIT 80
            """,
            (work_order_id,),
        )
        if rows:
            return _decorate_operation_rows(rows, order), False

    routing_rows = query_rows(
        """
        SELECT ro.sequence, ro.operation_no, ro.operation_name,
               %s AS planned_quantity, 0 AS actual_quantity, '待生成工序计划' AS status,
               pr.routing_no, pr.name AS routing_name,
               wc.code AS work_center_code, wc.name AS work_center_name, wc.responsible_person,
               ro.process_note AS operation_remark, '工艺路线' AS source_type
        FROM production_routings pr
        JOIN routing_operations ro ON ro.routing_id=pr.id
        LEFT JOIN work_centers wc ON wc.id=ro.work_center_id
        WHERE pr.product_id=%s
          AND COALESCE(pr.is_active, TRUE)=TRUE
          AND COALESCE(ro.is_active, TRUE)=TRUE
        ORDER BY pr.id DESC, ro.sequence, ro.id
        LIMIT 80
        """,
        (order.get("quantity") or 0, order.get("product_id")),
    )
    for row in routing_rows or []:
        row["next_action"] = "先维护工单工序计划，再按工序执行"
    return _decorate_operation_rows(routing_rows, order), bool(routing_rows)


def _work_order_issue_state(row):
    status = (row.get("status") or "").strip()
    pending_qty = as_decimal(row.get("pending_issue_qty"))
    required_qty = as_decimal(row.get("required_issue_qty"))
    issued_qty = as_decimal(row.get("issued_qty"))
    completed_qty = as_decimal(row.get("completed_qty"))
    if status in {"已作废", "已取消", "void", "cancelled"}:
        return "已作废", "保留追溯", "生产"
    if status in {"已关闭", "已完工", "已完成", "closed", "completed"}:
        return "已完成", "核对成本和质检记录", "生产/财务"
    if required_qty <= 0:
        return "待建领料需求", "按 BOM 生成或手工补充领料需求", "计划"
    if pending_qty > 0:
        return "待领料", "按未领数量领料", "仓库/生产"
    if completed_qty <= 0:
        return "待完工", "登记完工入库和质检", "生产"
    if issued_qty > required_qty:
        return "超领待核", "核对补料原因和工单成本", "生产/财务"
    return "已齐套", "推进完工、质检和关闭", "生产"


def _is_service_work_order(row):
    wo_no = str(row.get("wo_no") or "").strip().lower()
    production_type = str(row.get("production_type") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    service_markers = ("service", "after-sale", "after_sale", "repair", "rma", "售后", "维修", "服务")
    if wo_no.startswith("svc-") or wo_no.startswith("srv-"):
        return True
    if any(marker in production_type for marker in service_markers):
        return True
    if status in {"service", "after_sale"}:
        return True
    return False


def _decorate_work_order_kit_fields(row):
    required_qty = as_decimal(row.get("required_issue_qty"))
    pending_qty = as_decimal(row.get("pending_issue_qty"))
    mrp_shortage_qty = as_decimal(row.get("mrp_shortage_qty"))
    stock_shortage_qty = as_decimal(row.get("stock_shortage_qty"))
    pending_line_count = int(row.get("pending_line_count") or 0)
    stock_shortage_line_count = int(row.get("stock_shortage_line_count") or 0)

    if required_qty <= 0:
        row["kit_status"] = "不可投产"
        row["kit_shortage_reason"] = "未生成工单用料需求"
        row["kit_next_step"] = "按 BOM 生成或补齐工单用料明细"
        row["kit_owner_role"] = "计划"
    elif mrp_shortage_qty > 0:
        row["kit_status"] = "不可投产"
        row["kit_shortage_reason"] = f"MRP 缺料 {mrp_shortage_qty}"
        row["kit_next_step"] = "确认库存、在途采购或转采购申请"
        row["kit_owner_role"] = "计划 / 采购"
    elif stock_shortage_qty > 0:
        row["kit_status"] = "不可投产"
        row["kit_shortage_reason"] = f"库存不足 {stock_shortage_qty}，涉及 {stock_shortage_line_count} 行"
        row["kit_next_step"] = "补料、调拨或释放可用库存后再投产"
        row["kit_owner_role"] = "仓库 / 计划"
    elif pending_qty > 0:
        row["kit_status"] = "可投产"
        row["kit_shortage_reason"] = f"库存可覆盖，待领 {pending_qty}，涉及 {pending_line_count} 行"
        row["kit_next_step"] = "按未领数量领料后投产"
        row["kit_owner_role"] = "仓库 / 生产"
    else:
        row["kit_status"] = "可投产"
        row["kit_shortage_reason"] = "用料已领齐"
        row["kit_next_step"] = "投产并推进完工、质检和入库"
        row["kit_owner_role"] = "生产"
    row["kit_check_result"] = "缺料" if row["kit_status"] == "不可投产" else "齐套"
    row["kit_check_summary"] = f"{row['kit_check_result']}：{row['kit_shortage_reason']}"
    row["bom_preparation_status"] = (
        f"BOM {row.get('bom_display') or '未指定'} / {row['kit_check_summary']}"
        if row.get("bom_display")
        else f"未指定BOM / {row['kit_check_summary']}"
    )
    return row


def _decorate_work_order_loop_fields(row):
    if row.get("subcontract_overdue_count"):
        row["delivery_warning"] = "委外逾期未齐"
    elif row.get("subcontract_pending_count"):
        row["delivery_warning"] = "委外未齐"
    elif row.get("actual_end_date") and row.get("planned_end_date") and row.get("actual_end_date") > row.get("planned_end_date"):
        row["delivery_warning"] = "实际完工晚于计划"
    elif not row.get("actual_end_date") and row.get("planned_end_date") and row.get("planned_end_date") < datetime.now().date():
        row["delivery_warning"] = "计划完工逾期"
    else:
        row["delivery_warning"] = "正常"

    row["issue_state"], row["next_step"], row["owner_role"] = _work_order_issue_state(row)
    _decorate_work_order_kit_fields(row)
    if row["issue_state"] in {"待领料", "待建领料需求"}:
        row["blocked_reason"] = row.get("kit_shortage_reason") or "物料未齐套或未生成领料需求"
        row["downstream_impact"] = "影响装配开工、委外发料和项目交付节点"
    elif row["issue_state"] == "待完工":
        row["blocked_reason"] = "领料已满足，等待完工入库和质检记录"
        row["downstream_impact"] = "影响成品入库、发货、服务建档和成本归集"
    elif row["issue_state"] == "超领待核":
        row["blocked_reason"] = "已领数量超过需求数量"
        row["downstream_impact"] = "影响工单成本、库存准确性和期间结账"
    elif row["issue_state"] == "已完成":
        row["blocked_reason"] = "核对质检、成本和项目台账"
        row["downstream_impact"] = "支撑发货、售后建档、应收和成本结转"
    else:
        row["blocked_reason"] = "按当前工单状态推进"
        row["downstream_impact"] = "影响项目齐套、生产进度和成本闭环"
    if row.get("kit_status") == "不可投产":
        row["next_step"] = row.get("kit_next_step") or row["next_step"]
        row["owner_role"] = row.get("kit_owner_role") or row["owner_role"]
    _decorate_work_order_subcontract_fields(row)
    row["schedule_compare"] = _schedule_compare_text(row)
    row["reporting_status"] = "已报工/完工" if as_decimal(row.get("completed_qty")) > 0 else "待报工/完工"
    if row.get("production_stage") in {"暂停"}:
        row["blocked_reason"] = row.get("blocked_reason") or "工单暂停，需确认恢复条件"
        row["next_step"] = "确认暂停原因并恢复生产或调整计划"
    return row


def _decorate_work_order_subcontract_fields(row):
    order_count = int(row.get("subcontract_order_count") or 0)
    issued_qty = as_decimal(row.get("subcontract_issued_qty"))
    received_qty = as_decimal(row.get("subcontract_received_qty"))
    scrap_qty = as_decimal(row.get("subcontract_scrap_qty"))
    gap_qty = as_decimal(row.get("subcontract_gap_qty"))
    overdue_count = int(row.get("subcontract_overdue_count") or 0)
    pending_count = int(row.get("subcontract_pending_count") or 0)
    row["subcontract_execution"] = (
        f"{order_count} 单 / 发 {issued_qty} / 收 {received_qty} / 报废短收 {scrap_qty} / 缺 {gap_qty}"
        if order_count
        else "无委外"
    )
    if overdue_count:
        row["subcontract_next_step"] = "催收到货或确认短收/报废"
        row["subcontract_owner_role"] = "委外采购/生产计划"
        row["subcontract_blocked_reason"] = f"{overdue_count} 张委外逾期未齐"
        row["subcontract_downstream_impact"] = "影响工单齐套、完工入库、发货和成本归集"
    elif pending_count:
        row["subcontract_next_step"] = "跟进委外到货"
        row["subcontract_owner_role"] = "委外采购"
        row["subcontract_blocked_reason"] = f"{pending_count} 张委外未齐"
        row["subcontract_downstream_impact"] = "可能影响装配、调试和项目交付"
    elif order_count:
        row["subcontract_next_step"] = "核对委外入库和应付"
        row["subcontract_owner_role"] = "仓库/质量/财务"
        row["subcontract_blocked_reason"] = "委外数量已闭环"
        row["subcontract_downstream_impact"] = "支撑工单完工、外协应付和成本结转"
    else:
        row["subcontract_next_step"] = "无委外动作"
        row["subcontract_owner_role"] = "生产计划"
        row["subcontract_blocked_reason"] = "当前工单未关联委外订单"
        row["subcontract_downstream_impact"] = "不影响委外执行闭环"


def _resolve_options(options):
    return options() if callable(options) else (options or [])


def _load_work_order_custom_payload(work_order_id, query_one):
    if not work_order_id:
        return {}
    try:
        row = query_one(
            "SELECT payload FROM document_custom_field_values WHERE document_type=%s AND document_id=%s",
            ("work_order_extra_material", work_order_id),
        )
    except Exception:
        return {}
    if not row:
        return {}
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def _load_work_order_change_control(work_order_id, order, query_one, query_rows):
    def one(sql, params):
        try:
            return query_one(sql, params) or {}
        except Exception:
            logger.warning("work order change control sub-query failed", exc_info=True)
            return {}

    issued = one(
        """
        SELECT COALESCE(SUM(issued_qty),0) AS issued_qty,
               COUNT(*) FILTER (WHERE COALESCE(issued_qty,0) > 0) AS issued_lines
        FROM wo_material_items
        WHERE wo_id=%s
        """,
        (work_order_id,),
    )
    completed = one(
        "SELECT COALESCE(SUM(qty),0) AS completed_qty, COUNT(*) AS completed_lines FROM wo_complete_items WHERE wo_id=%s",
        (work_order_id,),
    )
    reports = one(
        """
        SELECT COUNT(*) FILTER (WHERE COALESCE(status,'') NOT IN ('已作废','作废','void','cancelled')) AS report_count
        FROM operation_reports
        WHERE work_order_id=%s
        """,
        (work_order_id,),
    )
    stock = one("SELECT COUNT(*) AS stock_tx_count FROM stock_transactions WHERE reference_no=%s", (order.get("wo_no"),))
    blockers = []
    if as_decimal(issued.get("issued_qty")) > 0:
        blockers.append("已有领料出库，数量/BOM/用料变更需评估退料、补料、库存流水和成本差异")
    if int(reports.get("report_count") or 0) > 0:
        blockers.append("已有工序报工，计划日期/工艺路线变更需评估排程、工时和质量节点")
    if as_decimal(completed.get("completed_qty")) > 0:
        blockers.append("已有完工入库，数量/BOM/工艺变更需评估成品库存、销售发货和成本结转")
    if int(stock.get("stock_tx_count") or 0) > 0:
        blockers.append("已有库存流水，不能直接覆盖工单关键字段")

    try:
        records = query_rows(
            """
            SELECT cr.*, u.username AS requested_by_name
            FROM work_order_change_records cr
            LEFT JOIN users u ON u.id=cr.requested_by
            WHERE cr.work_order_id=%s
            ORDER BY cr.requested_at DESC, cr.id DESC
            LIMIT 20
            """,
            (work_order_id,),
        )
    except Exception:
        logger.warning("_load_work_order_change_control records query failed for wo_id=%s", work_order_id, exc_info=True)
        records = []
    return {
        "blocked": bool(blockers),
        "status": "待评估" if blockers else "可调整",
        "blockers": blockers,
        "owner_role": "生产计划/技术",
        "next_action": "先登记工单变更评估，确认补料、退料、重排程、重算成本或拆新工单" if blockers else "由生产计划/技术复核后在受控动作中调整",
        "downstream_impact": "采购/MRP、仓库领退料、工序报工、质量、完工入库、项目成本、销售交付和服务追溯",
        "issued_qty": issued.get("issued_qty") or 0,
        "completed_qty": completed.get("completed_qty") or 0,
        "operation_report_count": reports.get("report_count") or 0,
        "stock_tx_count": stock.get("stock_tx_count") or 0,
        "records": records,
    }


def _build_work_order_snapshot_summary(query_one, work_order_id):
    snapshot = latest_work_order_execution_snapshot(query_one, work_order_id)
    if not snapshot:
        return {
            "exists": False,
            "status": "未固化",
            "next_action": "新建或生成 BOM 用料时自动固化执行快照",
            "bom_line_count": 0,
            "routing_operation_count": 0,
            "drawing_count": 0,
        }
    header = snapshot.get("header_payload") or {}
    context = snapshot.get("trace_context_payload") or {}
    work_order = header.get("work_order") or {}
    bom = header.get("bom") or {}
    routing = header.get("routing") or {}
    return {
        "exists": True,
        "status": "已固化",
        "snapshot_at": snapshot.get("snapshot_at") or snapshot.get("created_at"),
        "snapshot_id": snapshot.get("id"),
        "bom_no": bom.get("bom_no") or work_order.get("bom_no"),
        "bom_version": bom.get("version") or work_order.get("bom_version"),
        "bom_status": bom.get("status") or work_order.get("bom_status"),
        "bom_line_count": len(snapshot.get("lines_payload") or []),
        "routing_no": routing.get("routing_no"),
        "routing_name": routing.get("name"),
        "routing_operation_count": len(context.get("routing_operations") or []),
        "drawing_count": len(context.get("drawings") or []),
        "next_action": "按快照 BOM 生成用料；BOM 后续修改不影响本工单已固化依据",
    }


def render_work_order_detail(
    work_order_id,
    query_one,
    query_rows,
    as_decimal,
    qty_metric,
    columns,
    document_attachments,
    document_activity_logs,
    project_kit_rows,
    build_kit_summary,
    product_options,
    warehouse_options,
    location_options,
    back_url="/work-orders",
):
    order = query_one(
        """
        SELECT wo.*, p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               COALESCE(p.unit, '') AS product_unit, b.bom_no, b.version AS bom_version,
               w.name AS warehouse_name, l.code AS location_code, COALESCE(l.name, l.code) AS location_name,
               sales_source.order_no AS sales_order_no,
               sales_source.item_id AS sales_order_item_id,
               sales_source.source_line_no AS sales_source_line_no
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        LEFT JOIN warehouses w ON w.id=wo.warehouse_id
        LEFT JOIN locations l ON l.id=wo.location_id
        LEFT JOIN LATERAL (
            SELECT so.order_no, soi.id AS item_id, COALESCE(soi.source_line_no, soi.id::text) AS source_line_no
            FROM sales_order_items soi
            JOIN sales_orders so ON so.id=soi.order_id
            WHERE soi.product_id=wo.product_id
              AND (
                    (
                        NULLIF(wo.project_code, '') IS NOT NULL
                        AND COALESCE(NULLIF(soi.line_project_code, ''), NULLIF(so.project_code, ''))=wo.project_code
                    )
                    OR (
                        NULLIF(wo.serial_no, '') IS NOT NULL
                        AND COALESCE(NULLIF(soi.line_serial_no, ''), NULLIF(so.serial_no, ''))=wo.serial_no
                    )
                  )
              AND (
                    NULLIF(wo.source_line_no, '') IS NULL
                    OR soi.source_line_no=wo.source_line_no
                    OR soi.id::text=wo.source_line_no
                  )
            ORDER BY so.order_date DESC NULLS LAST, so.id DESC, soi.id DESC
            LIMIT 1
        ) sales_source ON TRUE
        WHERE wo.id=%s
        """,
        (work_order_id,),
    )
    if not order:
        return render_template("simple_detail.html", title="工单详情", row=None, back_url=back_url, labels={})

    project_code = order.get("project_code")
    serial_no = order.get("serial_no")
    cost_object_id = order.get("cost_object_id")
    material_items = query_rows(
        """
        SELECT mi.id, p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               COALESCE(mi.material_code, p.code, '') AS material_code,
               COALESCE(mi.material_name, p.name, '') AS material_name,
               COALESCE(mi.material_spec, p.specification, '') AS material_spec,
               COALESCE(mi.material_unit, p.unit, '') AS material_unit,
               source_bi.quantity AS bom_base_qty,
               COALESCE(source_bi.loss_rate, 0) AS bom_loss_rate,
               COALESCE(p.unit, '') AS unit, mi.required_qty, mi.issued_qty, mi.returned_qty,
               GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) AS shortage_qty,
               mi.unit_cost, mi.amount, mi.warehouse_id, mi.location_id, mi.lot_no,
               mi.source_line_no, mi.line_project_code, mi.line_serial_no, mi.remark,
               w.name AS line_warehouse_name, l.code AS line_location_code, COALESCE(l.name, l.code) AS line_location_name
        FROM wo_material_items mi
        LEFT JOIN products p ON p.id=mi.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN warehouses w ON w.id=mi.warehouse_id
        LEFT JOIN locations l ON l.id=mi.location_id
        LEFT JOIN bom_items source_bi ON mi.source_line_no=CONCAT('BOM-', source_bi.id::text)
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE mi.wo_id=%s
        ORDER BY mi.id
        """,
        (work_order_id,),
    )
    bom_requirement_rows = []
    if order.get("bom_id"):
        bom_requirement_rows = query_rows(
            """
            SELECT bi.id AS bom_item_id, bi.product_id,
                   COALESCE(bi.quantity, 0) AS base_qty,
                   COALESCE(bi.loss_rate, 0) AS loss_rate
            FROM bom_items bi
            WHERE bi.bom_id=%s
            ORDER BY bi.id
            """,
            (order.get("bom_id"),),
        )
    existing_bom_source_lines = [
        row.get("source_line_no")
        for row in material_items
        if (row.get("source_line_no") or "").startswith("BOM-")
    ]
    bom_requirement_summary = summarize_bom_requirement_generation(order, bom_requirement_rows, existing_bom_source_lines)
    component_items = query_rows(
        """
        SELECT ci.id, p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               COALESCE(p.unit, '') AS unit, ci.required_qty, ci.ready_qty,
               GREATEST(COALESCE(ci.required_qty,0)-COALESCE(ci.ready_qty,0),0) AS not_ready_qty,
               ci.supply_mode, ci.manufacturing_role, ci.status, ci.ready_date, ci.ready_remark
        FROM work_order_component_items ci
        LEFT JOIN products p ON p.id=ci.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE ci.wo_id=%s
        ORDER BY ci.id
        """,
        (work_order_id,),
    )
    completions = query_rows(
        """
        SELECT wc.id, wc.complete_date, p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
                COALESCE(p.unit, '') AS unit, wc.qty, wc.lot_no, wc.serial_no, wc.unit_cost,
                wc.warehouse_id, wc.location_id,
                w.name AS warehouse_name, l.code AS location_code, COALESCE(l.name, l.code) AS location_name
        FROM wo_complete_items wc
        LEFT JOIN products p ON p.id=wc.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        LEFT JOIN warehouses w ON w.id=wc.warehouse_id
        LEFT JOIN locations l ON l.id=wc.location_id
        WHERE wc.wo_id=%s
        ORDER BY wc.id DESC
        LIMIT 30
        """,
        (work_order_id,),
    )
    processes, processes_from_routing = _load_work_order_operations(query_rows, order)
    quality_rows = query_rows(
        """
        SELECT id, inspection_no, inspection_date, inspection_type, sample_size,
               passed_quantity, failed_quantity, inspection_result, defect_description,
               corrective_action, status
        FROM quality_inspection_records
        WHERE source_document_type='work_order' AND source_document_id=%s
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND serial_no=%s)
        ORDER BY id DESC
        LIMIT 30
        """,
        (work_order_id, project_code, project_code, serial_no, serial_no),
    )
    has_cost_table = _optional_table_exists("work_order_costs", query_one)
    has_cost_line_table = _optional_table_exists("work_order_cost_lines", query_one)
    cost = {}
    if has_cost_table:
        cost = query_one(
            """
            SELECT *
            FROM work_order_costs
            WHERE work_order_id=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (work_order_id,),
        ) or {}
    cost_lines = []
    if has_cost_line_table:
        cost_lines = query_rows(
            """
            SELECT id, cost_type, source_type, source_no, quantity, unit_cost, amount, remark, created_at
            FROM work_order_cost_lines
            WHERE work_order_id=%s
            ORDER BY id DESC
            LIMIT 40
            """,
            (work_order_id,),
        )
    stock_rows = query_rows(
        """
        SELECT st.id, st.transaction_date, st.transaction_type, p.code AS product_code,
               p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               st.quantity, st.unit_cost, st.amount, st.reference_no, st.source_line_no, st.lot_no, st.serial_no, st.remark
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE st.reference_no=%s
           OR (%s IS NOT NULL AND st.serial_no=%s)
        ORDER BY st.id DESC
        LIMIT 50
        """,
        (order.get("wo_no"), serial_no, serial_no),
    )
    subcontract_rows = query_rows(
        """
        SELECT sc.id, sc.order_no, sc.order_date, sc.required_date, sc.status, sc.total_amount,
               sc.quantity, s.name AS supplier_name,
               COALESCE(issue_sum.issued_qty, 0) AS issued_qty,
               COALESCE(receive_sum.received_qty, 0) AS received_qty,
               COALESCE(receive_sum.scrap_qty, 0) AS scrap_qty
        FROM subcontract_orders sc
        LEFT JOIN suppliers s ON s.id=sc.supplier_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(total_quantity), 0) AS issued_qty
            FROM subcontract_issue_orders sio
            WHERE sio.subcontract_order_id=sc.id
              AND COALESCE(sio.status, '') NOT IN ('已作废','void','cancelled')
        ) issue_sum ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(total_quantity), 0) AS received_qty,
                   COALESCE(SUM(total_scrap), 0) AS scrap_qty
            FROM subcontract_receive_orders sro
            WHERE sro.subcontract_order_id=sc.id
              AND COALESCE(sro.status, '') NOT IN ('已作废','void','cancelled')
        ) receive_sum ON TRUE
        WHERE sc.parent_work_order_id=%s
           OR (%s IS NOT NULL AND sc.project_code=%s)
           OR (%s IS NOT NULL AND sc.serial_no=%s)
        ORDER BY sc.id DESC
        LIMIT 30
        """,
        (work_order_id, project_code, project_code, serial_no, serial_no),
    )
    mrp_rows = query_rows(
        """
        SELECT mr.id, mr.requirement_date, p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               mr.quantity, mr.available_quantity, mr.shortage_quantity, mr.supply_mode, mr.status
        FROM mrp_requirements mr
        LEFT JOIN products p ON p.id=mr.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE mr.work_order_id=%s
           OR (%s IS NOT NULL AND mr.project_code=%s)
           OR (%s IS NOT NULL AND mr.serial_no=%s)
        ORDER BY mr.id DESC
        LIMIT 40
        """,
        (work_order_id, project_code, project_code, serial_no, serial_no),
    )
    order["bom_display"] = _bom_display_text(order)
    order["control_display"] = _manufacturing_control_text(order)
    _decorate_work_order_source(order)
    _decorate_manufacturing_rows(material_items)
    _decorate_manufacturing_rows(component_items)
    _decorate_manufacturing_rows(completions)
    _decorate_manufacturing_rows(stock_rows)
    _decorate_manufacturing_rows(mrp_rows)
    _decorate_quality_rows(quality_rows)
    for row in subcontract_rows:
        _decorate_subcontract_arrival(row)
    operation_cost_summary = _load_operation_report_cost_summary(query_rows, work_order_id)
    status_logs = query_rows(
        """
        SELECT l.id, l.from_stage, l.to_stage, l.changed_at, l.remark, u.username AS operator_name
        FROM work_order_status_logs l
        LEFT JOIN users u ON u.id=l.changed_by
        WHERE l.work_order_id=%s
        ORDER BY l.changed_at DESC, l.id DESC
        LIMIT 20
        """,
        (work_order_id,),
    )
    _decorate_work_order_progress(order, subcontract_rows)
    kit_rows = project_kit_rows(work_order_id, project_code, serial_no, cost_object_id) if project_kit_rows else []
    kit_summary = build_kit_summary(kit_rows) if build_kit_summary else {}
    material_summary = summarize_material_rows(material_items)
    total_required = material_summary["required_qty"]
    total_issued = material_summary["issued_qty"]
    returnable_material_items = []
    for row in material_items:
        returnable_qty = returnable_material_quantity(row)
        if returnable_qty > 0:
            row["returnable_qty"] = returnable_qty
            returnable_material_items.append(row)
    total_completed = sum((as_decimal(row.get("qty")) for row in completions), Decimal("0"))
    total_unissued = material_summary["pending_qty"]
    quality_summary = _build_quality_summary(order, quality_rows, completions)
    completion_gate = build_work_order_completion_gate(order, material_items, quality_rows, processes, mrp_rows, completions, stock_rows)
    cost_reconciliation = _build_work_order_cost_reconciliation(
        order, material_items, subcontract_rows, completions, cost, cost_lines, operation_cost_summary
    )
    change_control = _load_work_order_change_control(work_order_id, order, query_one, query_rows)
    execution_snapshot = _build_work_order_snapshot_summary(query_one, work_order_id)
    mrp_preview = build_work_order_mrp_preview(query_one, work_order_id)
    can_operate = (order.get("status") or "") not in {"已完工", "已关闭", "已作废", "已取消"}
    if not can_operate:
        next_step = "工单已结束，只保留查看、打印、附件和备注。"
    elif total_unissued > 0:
        next_step = "下一步：先完成领料，再按实际完工数量入库。"
    else:
        next_step = "下一步：按实际产出登记完工入库。"
    return render_template(
        "work_order_trace_detail.html",
        back_url=back_url,
        order=order,
        material_items=material_items,
        bom_requirement_summary=bom_requirement_summary,
        returnable_material_items=returnable_material_items,
        component_items=component_items,
        completions=completions,
        processes=processes,
        processes_from_routing=processes_from_routing,
        quality_rows=quality_rows,
        quality_summary=quality_summary,
        completion_gate=completion_gate,
        cost=cost,
        cost_lines=cost_lines,
        cost_reconciliation=cost_reconciliation,
        change_control=change_control,
        execution_snapshot=execution_snapshot,
        mrp_preview=mrp_preview,
        stock_rows=stock_rows,
        subcontract_rows=subcontract_rows,
        mrp_rows=mrp_rows,
        status_logs=status_logs,
        production_stages=PRODUCTION_STAGES,
        stage_items=order.get("stage_items") or [],
        material_options=query_rows("SELECT id, code, name FROM products ORDER BY code LIMIT 300"),
        product_options=_resolve_options(product_options),
        warehouse_options=_resolve_options(warehouse_options),
        location_options=_resolve_options(location_options),
        warehouses=_resolve_options(warehouse_options),
        locations=_resolve_options(location_options),
        attachments=document_attachments("work_order", work_order_id),
        activity_logs=document_activity_logs("work_order", order),
        custom_fields_payload=_load_work_order_custom_payload(work_order_id, query_one),
        can_operate=can_operate,
        next_step=next_step,
        project_kit_rows=kit_rows,
        kit_rows=kit_rows,
        kit_summary=kit_summary,
        detail_columns=columns,
        metrics=[
            {"label": "计划数量", "value": qty_metric(order.get("quantity")), "hint": order.get("product_unit") or ""},
            {"label": "已领料", "value": qty_metric(total_issued), "hint": f"需求 {qty_metric(total_required)}"},
            {"label": "已完工", "value": qty_metric(total_completed), "hint": "完工入库明细"},
            {"label": "工单成本", "value": _money_metric(cost.get("total_cost")), "hint": "材料/委外/人工/制造费用"},
        ],
    )


def render_production_dashboard(query_rows, count_rows, columns, render_module_dashboard):
    metrics = [
        {"label": "工单数", "value": count_rows("work_orders"), "hint": "全部生产工单"},
        {
            "label": "未完工单",
            "value": count_rows("work_orders", "COALESCE(status, '') NOT IN ('已完成','已关闭','已取消')"),
            "hint": "仍在执行",
        },
        {
            "label": "MRP缺料",
            "value": count_rows("mrp_requirements", "COALESCE(shortage_quantity, 0) > 0"),
            "hint": "需要采购/委外/生产",
        },
        {"label": "委外单", "value": count_rows("subcontract_orders"), "hint": "外协加工"},
    ]
    shortcuts = [
        {"label": "BOM清单", "url": "/bom", "icon": "bi-diagram-2"},
        {"label": "工艺路线", "url": "/production-routings", "icon": "bi-signpost-split"},
        {"label": "MRP需求", "url": "/production-enhance/mrp-requirements", "icon": "bi-diagram-3"},
        {"label": "生产领料单", "url": "/production-picks", "icon": "bi-clipboard-check"},
        {"label": "委外", "url": "/subcontract", "icon": "bi-box-seam"},
        {"label": "工作中心", "url": "/work-centers", "icon": "bi-tools"},
        {"label": "设备台账", "url": "/equipment", "icon": "bi-cpu"},
        {"label": "质检", "url": "/production-enhance/quality-inspections", "icon": "bi-check2-square"},
    ]
    work_orders = query_rows(
        """
        SELECT wo.id, wo.wo_no, wo.wo_date, wo.project_code, wo.serial_no, wo.status,
               wo.quantity, wo.production_stage, wo.production_type, wo.planned_start_date, wo.planned_end_date,
               wo.actual_start_date, wo.actual_end_date,
               p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(b.bom_no, default_bom.bom_no) AS bom_no,
               COALESCE(b.version, default_bom.version) AS bom_version,
               NULLIF(CONCAT_WS(' / ', NULLIF(COALESCE(b.bom_no, default_bom.bom_no), ''), NULLIF(COALESCE(b.version, default_bom.version), '')), '') AS bom_display,
               COALESCE(material.required_qty, 0) AS required_issue_qty,
               COALESCE(material.issued_qty, 0) AS issued_qty,
               COALESCE(material.returned_qty, 0) AS returned_qty,
               GREATEST(COALESCE(material.required_qty, 0)-COALESCE(material.issued_qty, 0)+COALESCE(material.returned_qty, 0), 0) AS pending_issue_qty,
               COALESCE(material.pending_line_count, 0) AS pending_line_count,
               COALESCE(material.stock_shortage_line_count, 0) AS stock_shortage_line_count,
               COALESCE(material.stock_shortage_qty, 0) AS stock_shortage_qty,
               COALESCE(mrp_shortage.shortage_qty, 0) AS mrp_shortage_qty,
               COALESCE(completed.completed_qty, 0) AS completed_qty,
               COALESCE(subcontract.order_count, 0) AS subcontract_order_count,
               COALESCE(subcontract.issued_qty, 0) AS subcontract_issued_qty,
               COALESCE(subcontract.received_qty, 0) AS subcontract_received_qty,
               COALESCE(subcontract.scrap_qty, 0) AS subcontract_scrap_qty,
               COALESCE(subcontract.gap_qty, 0) AS subcontract_gap_qty,
               COALESCE(subcontract.pending_count, 0) AS subcontract_pending_count,
               COALESCE(subcontract.overdue_count, 0) AS subcontract_overdue_count,
               sales_source.order_no AS sales_order_no,
               sales_source.item_id AS sales_order_item_id,
               sales_source.source_line_no AS sales_source_line_no
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(required_qty), 0) AS required_qty,
                   COALESCE(SUM(issued_qty), 0) AS issued_qty,
                   COALESCE(SUM(returned_qty), 0) AS returned_qty,
                   COUNT(*) FILTER (
                       WHERE GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > 0
                   ) AS pending_line_count,
                   COUNT(*) FILTER (
                       WHERE GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > COALESCE(inv.available_qty, 0)
                   ) AS stock_shortage_line_count,
                   COALESCE(SUM(GREATEST(
                       GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) - COALESCE(inv.available_qty,0),
                       0
                   )), 0) AS stock_shortage_qty
            FROM wo_material_items mi
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(quantity), 0) AS available_qty
                FROM inventory_balances ib
                WHERE ib.product_id=mi.product_id
                  AND (mi.warehouse_id IS NULL OR ib.warehouse_id=mi.warehouse_id)
                  AND (mi.location_id IS NULL OR ib.location_id=mi.location_id)
                  AND (COALESCE(mi.line_project_code, '')='' OR COALESCE(ib.project_code, '')=COALESCE(mi.line_project_code, ''))
                  AND (COALESCE(mi.line_serial_no, '')='' OR COALESCE(ib.serial_no, '')=COALESCE(mi.line_serial_no, ''))
            ) inv ON TRUE
            WHERE mi.wo_id=wo.id
        ) material ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(shortage_quantity), 0) AS shortage_qty
            FROM mrp_requirements mr
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
              AND (
                  (wo.project_code IS NOT NULL AND mr.project_code=wo.project_code)
                  OR (wo.serial_no IS NOT NULL AND mr.serial_no=wo.serial_no)
              )
        ) mrp_shortage ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(qty), 0) AS completed_qty
            FROM wo_complete_items wc
            WHERE wc.wo_id=wo.id
        ) completed ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS order_count,
                   COALESCE(SUM(COALESCE(issue_sum.issued_qty, 0)), 0) AS issued_qty,
                   COALESCE(SUM(COALESCE(receive_sum.received_qty, 0)), 0) AS received_qty,
                   COALESCE(SUM(COALESCE(receive_sum.scrap_qty, 0)), 0) AS scrap_qty,
                   COALESCE(SUM(GREATEST(COALESCE(sc.quantity, 0) - COALESCE(receive_sum.received_qty, 0) - COALESCE(receive_sum.scrap_qty, 0), 0)), 0) AS gap_qty,
                   COUNT(*) FILTER (
                       WHERE COALESCE(sc.quantity, 0) > COALESCE(receive_sum.received_qty, 0) + COALESCE(receive_sum.scrap_qty, 0)
                   ) AS pending_count,
                   COUNT(*) FILTER (
                       WHERE COALESCE(sc.quantity, 0) > COALESCE(receive_sum.received_qty, 0) + COALESCE(receive_sum.scrap_qty, 0)
                         AND sc.required_date < CURRENT_DATE
                   ) AS overdue_count
            FROM subcontract_orders sc
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(total_quantity), 0) AS issued_qty
                FROM subcontract_issue_orders sio
                WHERE sio.subcontract_order_id=sc.id
                  AND COALESCE(sio.status, '') NOT IN ('已作废','void','cancelled')
            ) issue_sum ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(total_quantity), 0) AS received_qty,
                       COALESCE(SUM(total_scrap), 0) AS scrap_qty
                FROM subcontract_receive_orders sro
                WHERE sro.subcontract_order_id=sc.id
                  AND COALESCE(sro.status, '') NOT IN ('已作废','void','cancelled')
            ) receive_sum ON TRUE
            WHERE sc.parent_work_order_id=wo.id
               OR (wo.project_code IS NOT NULL AND sc.project_code=wo.project_code)
               OR (wo.serial_no IS NOT NULL AND sc.serial_no=wo.serial_no)
        ) subcontract ON TRUE
        LEFT JOIN LATERAL (
            SELECT db.bom_no, db.version
            FROM boms db
            WHERE db.product_id=p.id AND COALESCE(db.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN db.bom_type='production' THEN 0 ELSE 1 END,
                db.id DESC
            LIMIT 1
        ) default_bom ON TRUE
        LEFT JOIN LATERAL (
            SELECT so.order_no, soi.id AS item_id, COALESCE(soi.source_line_no, soi.id::text) AS source_line_no
            FROM sales_order_items soi
            JOIN sales_orders so ON so.id=soi.order_id
            WHERE soi.product_id=wo.product_id
              AND (
                    (
                        NULLIF(wo.project_code, '') IS NOT NULL
                        AND COALESCE(NULLIF(soi.line_project_code, ''), NULLIF(so.project_code, ''))=wo.project_code
                    )
                    OR (
                        NULLIF(wo.serial_no, '') IS NOT NULL
                        AND COALESCE(NULLIF(soi.line_serial_no, ''), NULLIF(so.serial_no, ''))=wo.serial_no
                    )
                  )
              AND (
                    NULLIF(wo.source_line_no, '') IS NULL
                    OR soi.source_line_no=wo.source_line_no
                    OR soi.id::text=wo.source_line_no
                  )
            ORDER BY so.order_date DESC NULLS LAST, so.id DESC, soi.id DESC
            LIMIT 1
        ) sales_source ON TRUE
        WHERE COALESCE(wo.wo_no, '') NOT ILIKE 'SVC-%%'
          AND COALESCE(wo.wo_no, '') NOT ILIKE 'SRV-%%'
          AND COALESCE(wo.production_type, '') NOT ILIKE '%%service%%'
          AND COALESCE(wo.production_type, '') NOT ILIKE '%%repair%%'
          AND COALESCE(wo.production_type, '') NOT LIKE '%%售后%%'
          AND COALESCE(wo.production_type, '') NOT LIKE '%%维修%%'
          AND COALESCE(wo.production_type, '') NOT LIKE '%%服务%%'
        ORDER BY wo.id DESC
        LIMIT 30
        """
    )
    work_orders = [row for row in work_orders if not _is_service_work_order(row)]
    for row in work_orders:
        row["production_stage"] = _production_stage_from_row(row)
        _decorate_work_order_loop_fields(row)
        _decorate_work_order_source(row)
    work_orders = [
        row for row in work_orders
        if row.get("kit_status") == "不可投产"
        or row.get("issue_state") in {"待建领料需求", "待领料", "待完工", "超领待核"}
        or row.get("delivery_warning") != "正常"
        or row.get("subcontract_pending_count")
        or row.get("reporting_status") == "待报工/完工"
    ][:12]
    shortages = query_rows(
        """
        SELECT mr.id, mr.requirement_date, mr.project_code, mr.serial_no, p.code AS product_code,
               p.name AS product_name, mr.quantity, mr.available_quantity, mr.shortage_quantity, mr.status
        FROM mrp_requirements mr
        LEFT JOIN products p ON p.id=mr.product_id
        WHERE COALESCE(mr.shortage_quantity, 0) > 0
        ORDER BY mr.id DESC
        LIMIT 20
        """
    )
    for row in shortages:
        row["next_step"] = "确认库存、在途采购或转采购申请"
        row["owner_role"] = "计划 / 采购"
        row["blocked_reason"] = "MRP 缺料未关闭"
        row["downstream_impact"] = "影响工单齐套、领料和装配计划"
    return render_module_dashboard(
        "生产工作台",
        "只显示生产待办、异常与阻塞队列；完整工单请进入工单列表。",
        metrics,
        shortcuts,
        [
            {
                "title": "生产待办与异常队列",
                "count_label": f"{len(work_orders)} 条待处理，不是完整工单列表",
                "rows": work_orders,
                "columns": columns(
                    ("wo_no", "工单"),
                    ("production_stage", "生产阶段"),
                    ("issue_state", "领料状态"),
                    ("kit_check_result", "齐套结果"),
                    ("kit_shortage_reason", "齐套/缺料说明"),
                    ("reporting_status", "报工/完工"),
                    ("schedule_compare", "计划/实际对比"),
                    ("product_code", "物料编码"),
                    ("product_name", "物料名称"),
                    ("source_axis", "项目/机号"),
                    ("pending_issue_qty", "未领"),
                    ("completed_qty", "完工"),
                    ("delivery_warning", "交期预警"),
                    ("next_step", "下一步"),
                    ("owner_role", "责任"),
                    ("blocked_reason", "堵点/条件"),
                    ("downstream_impact", "下游影响"),
                ),
                "detail_base": "/work-orders",
            },
            {
                "title": "MRP缺料",
                "rows": shortages,
                "columns": columns(
                    ("requirement_date", "需求日期"),
                    ("project_code", "项目号"),
                    ("serial_no", "机号"),
                    ("product_code", "物料编码"),
                    ("product_name", "物料名称"),
                    ("shortage_quantity", "缺料"),
                    ("status", "状态"),
                    ("next_step", "下一步"),
                    ("owner_role", "责任"),
                    ("downstream_impact", "下游影响"),
                ),
                "detail_base": "/production-enhance/mrp-requirements",
            },
        ],
    )


def render_work_order_list(query_rows, columns, render_template_func=render_template, scope_clause="", scope_params=()):
    rows = query_rows(
        f"""
        SELECT wo.id, wo.wo_no, wo.wo_date, wo.project_code, wo.serial_no, wo.status,
               wo.production_type,
               wo.quantity, wo.production_stage, p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(b.bom_no, default_bom.bom_no) AS bom_no,
               COALESCE(b.version, default_bom.version) AS bom_version,
               NULLIF(CONCAT_WS(' / ', NULLIF(COALESCE(b.bom_no, default_bom.bom_no), ''), NULLIF(COALESCE(b.version, default_bom.version), '')), '') AS bom_display,
               COALESCE(material.required_qty, 0) AS required_issue_qty,
               COALESCE(material.issued_qty, 0) AS issued_qty,
               COALESCE(material.returned_qty, 0) AS returned_qty,
               GREATEST(COALESCE(material.required_qty, 0)-COALESCE(material.issued_qty, 0)+COALESCE(material.returned_qty, 0), 0) AS pending_issue_qty,
               COALESCE(material.pending_line_count, 0) AS pending_line_count,
               COALESCE(material.stock_shortage_line_count, 0) AS stock_shortage_line_count,
               COALESCE(material.stock_shortage_qty, 0) AS stock_shortage_qty,
               COALESCE(mrp_shortage.shortage_qty, 0) AS mrp_shortage_qty,
               COALESCE(completed.completed_qty, 0) AS completed_qty,
               COALESCE(subcontract.order_count, 0) AS subcontract_order_count,
               COALESCE(subcontract.issued_qty, 0) AS subcontract_issued_qty,
               COALESCE(subcontract.received_qty, 0) AS subcontract_received_qty,
               COALESCE(subcontract.scrap_qty, 0) AS subcontract_scrap_qty,
               COALESCE(subcontract.gap_qty, 0) AS subcontract_gap_qty,
               COALESCE(subcontract.pending_count, 0) AS subcontract_pending_count,
               COALESCE(subcontract.overdue_count, 0) AS subcontract_overdue_count,
               sales_source.order_no AS sales_order_no,
               sales_source.item_id AS sales_order_item_id,
               sales_source.source_line_no AS sales_source_line_no,
               wo.planned_end_date, wo.actual_end_date
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(required_qty), 0) AS required_qty,
                   COALESCE(SUM(issued_qty), 0) AS issued_qty,
                   COALESCE(SUM(returned_qty), 0) AS returned_qty,
                   COUNT(*) FILTER (
                       WHERE GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > 0
                   ) AS pending_line_count,
                   COUNT(*) FILTER (
                       WHERE GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > COALESCE(inv.available_qty, 0)
                   ) AS stock_shortage_line_count,
                   COALESCE(SUM(GREATEST(
                       GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) - COALESCE(inv.available_qty,0),
                       0
                   )), 0) AS stock_shortage_qty
            FROM wo_material_items mi
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(quantity), 0) AS available_qty
                FROM inventory_balances ib
                WHERE ib.product_id=mi.product_id
                  AND (mi.warehouse_id IS NULL OR ib.warehouse_id=mi.warehouse_id)
                  AND (mi.location_id IS NULL OR ib.location_id=mi.location_id)
                  AND (COALESCE(mi.line_project_code, '')='' OR COALESCE(ib.project_code, '')=COALESCE(mi.line_project_code, ''))
                  AND (COALESCE(mi.line_serial_no, '')='' OR COALESCE(ib.serial_no, '')=COALESCE(mi.line_serial_no, ''))
            ) inv ON TRUE
            WHERE mi.wo_id=wo.id
        ) material ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(shortage_quantity), 0) AS shortage_qty
            FROM mrp_requirements mr
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
              AND (
                  (wo.project_code IS NOT NULL AND mr.project_code=wo.project_code)
                  OR (wo.serial_no IS NOT NULL AND mr.serial_no=wo.serial_no)
              )
        ) mrp_shortage ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(qty), 0) AS completed_qty
            FROM wo_complete_items wc
            WHERE wc.wo_id=wo.id
        ) completed ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS order_count,
                   COALESCE(SUM(COALESCE(issue_sum.issued_qty, 0)), 0) AS issued_qty,
                   COALESCE(SUM(COALESCE(receive_sum.received_qty, 0)), 0) AS received_qty,
                   COALESCE(SUM(COALESCE(receive_sum.scrap_qty, 0)), 0) AS scrap_qty,
                   COALESCE(SUM(GREATEST(COALESCE(sc.quantity, 0) - COALESCE(receive_sum.received_qty, 0) - COALESCE(receive_sum.scrap_qty, 0), 0)), 0) AS gap_qty,
                   COUNT(*) FILTER (
                       WHERE COALESCE(sc.quantity, 0) > COALESCE(receive_sum.received_qty, 0) + COALESCE(receive_sum.scrap_qty, 0)
                   ) AS pending_count,
                   COUNT(*) FILTER (
                       WHERE COALESCE(sc.quantity, 0) > COALESCE(receive_sum.received_qty, 0) + COALESCE(receive_sum.scrap_qty, 0)
                         AND sc.required_date < CURRENT_DATE
                   ) AS overdue_count
            FROM subcontract_orders sc
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(total_quantity), 0) AS issued_qty
                FROM subcontract_issue_orders sio
                WHERE sio.subcontract_order_id=sc.id
                  AND COALESCE(sio.status, '') NOT IN ('已作废','void','cancelled')
            ) issue_sum ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(total_quantity), 0) AS received_qty,
                       COALESCE(SUM(total_scrap), 0) AS scrap_qty
                FROM subcontract_receive_orders sro
                WHERE sro.subcontract_order_id=sc.id
                  AND COALESCE(sro.status, '') NOT IN ('已作废','void','cancelled')
            ) receive_sum ON TRUE
            WHERE sc.parent_work_order_id=wo.id
               OR (wo.project_code IS NOT NULL AND sc.project_code=wo.project_code)
               OR (wo.serial_no IS NOT NULL AND sc.serial_no=wo.serial_no)
        ) subcontract ON TRUE
        LEFT JOIN LATERAL (
            SELECT db.bom_no, db.version
            FROM boms db
            WHERE db.product_id=p.id AND COALESCE(db.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY CASE WHEN db.bom_type='production' THEN 0 ELSE 1 END, db.id DESC
            LIMIT 1
        ) default_bom ON TRUE
        LEFT JOIN LATERAL (
            SELECT so.order_no, soi.id AS item_id, COALESCE(soi.source_line_no, soi.id::text) AS source_line_no
            FROM sales_order_items soi
            JOIN sales_orders so ON so.id=soi.order_id
            WHERE soi.product_id=wo.product_id
              AND (
                    (
                        NULLIF(wo.project_code, '') IS NOT NULL
                        AND COALESCE(NULLIF(soi.line_project_code, ''), NULLIF(so.project_code, ''))=wo.project_code
                    )
                    OR (
                        NULLIF(wo.serial_no, '') IS NOT NULL
                        AND COALESCE(NULLIF(soi.line_serial_no, ''), NULLIF(so.serial_no, ''))=wo.serial_no
                    )
                  )
              AND (
                    NULLIF(wo.source_line_no, '') IS NULL
                    OR soi.source_line_no=wo.source_line_no
                    OR soi.id::text=wo.source_line_no
                  )
            ORDER BY so.order_date DESC NULLS LAST, so.id DESC, soi.id DESC
            LIMIT 1
        ) sales_source ON TRUE
        WHERE COALESCE(wo.wo_no, '') NOT ILIKE 'SVC-%%'
          AND COALESCE(wo.wo_no, '') NOT ILIKE 'SRV-%%'
          AND COALESCE(wo.production_type, '') NOT ILIKE '%%service%%'
          AND COALESCE(wo.production_type, '') NOT ILIKE '%%repair%%'
          AND COALESCE(wo.production_type, '') NOT LIKE '%%售后%%'
          AND COALESCE(wo.production_type, '') NOT LIKE '%%维修%%'
          AND COALESCE(wo.production_type, '') NOT LIKE '%%服务%%'
          {scope_clause}
        ORDER BY wo.id DESC
        LIMIT 120
        """,
        tuple(scope_params or ()),
    )
    rows = [row for row in rows if not _is_service_work_order(row)]
    for row in rows:
        row["production_stage"] = _production_stage_from_row(row)
        _decorate_work_order_loop_fields(row)
        _decorate_work_order_source(row)
    return render_template_func(
        "simple_list.html",
        title="生产工单列表",
        subtitle="生产工单列表，只展示和处理已有工单；新增工单从左侧“生产单据”进入。",
        rows=rows,
        columns=columns(
            ("wo_no", "工单"),
            ("wo_date", "日期"),
            ("product_code", "物料编码"),
            ("product_name", "物料名称"),
            ("product_family", "产品分类"),
            ("source_axis", "项目/机号追踪"),
            ("production_stage", "生产阶段"),
            ("status", "单据状态"),
            ("quantity", "数量"),
            ("completed_qty", "完工"),
            ("pending_issue_qty", "未领"),
            ("kit_check_result", "齐套结果"),
            ("next_step", "下一步"),
            ("blocked_reason", "堵点/条件"),
        ),
        detail_base="/work-orders",
        add_url=None,
    )


def render_work_order_operation_print(kind, work_order_id, query_one, query_rows, as_decimal):
    order = query_one(
        """
        SELECT wo.*, p.code AS product_code, p.name AS product_name, p.specification, p.unit AS product_unit,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               b.bom_no, b.version AS bom_version,
               w.name AS warehouse_name
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        LEFT JOIN warehouses w ON w.id=wo.warehouse_id
        WHERE wo.id=%s
        """,
        (work_order_id,),
    )
    if not order:
        return render_template("simple_detail.html", title="工单打印", row=None, back_url="/work-orders", labels={})
    if kind == "issue":
        rows = query_rows(
            """
            SELECT mi.required_qty AS quantity, mi.issued_qty, mi.returned_qty, mi.unit_cost,
                   p.code AS product_code, p.name AS product_name, p.specification, p.unit,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required,
                   mi.remark,
                   (COALESCE(mi.issued_qty,0) * COALESCE(mi.unit_cost,0)) AS amount
            FROM wo_material_items mi
            LEFT JOIN products p ON p.id=mi.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            WHERE mi.wo_id=%s
            ORDER BY mi.id
            """,
            (work_order_id,),
        )
        _decorate_manufacturing_rows(rows)
        title = "工单领料单"
        line_columns = [
            ("product_code", "物料编码", ""),
            ("product_name", "物料名称", ""),
            ("specification", "规格", ""),
            ("product_family", "产品分类", ""),
            ("bom_display", "BOM版本", ""),
            ("control_display", "管控", ""),
            ("quantity", "需求数量", "right"),
            ("issued_qty", "已领数量", "right"),
            ("unit", "单位", "center"),
            ("unit_cost", "成本", "money right"),
            ("amount", "金额", "money right"),
            ("remark", "备注", ""),
        ]
        total_quantity = sum((as_decimal(row.get("issued_qty")) for row in rows), Decimal("0"))
    else:
        rows = query_rows(
            """
            SELECT wc.complete_date, wc.qty AS quantity, wc.unit_cost, wc.lot_no, wc.serial_no,
                   p.code AS product_code, p.name AS product_name, p.specification, p.unit,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required,
                   w.name AS warehouse_name,
                   (COALESCE(wc.qty,0) * COALESCE(wc.unit_cost,0)) AS amount
            FROM wo_complete_items wc
            LEFT JOIN products p ON p.id=wc.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            LEFT JOIN warehouses w ON w.id=wc.warehouse_id
            WHERE wc.wo_id=%s
            ORDER BY wc.id
            """,
            (work_order_id,),
        )
        _decorate_manufacturing_rows(rows)
        title = "工单完工入库单"
        line_columns = [
            ("complete_date", "完工日期", ""),
            ("product_code", "物料编码", ""),
            ("product_name", "物料名称", ""),
            ("specification", "规格", ""),
            ("product_family", "产品分类", ""),
            ("bom_display", "BOM版本", ""),
            ("control_display", "管控", ""),
            ("quantity", "完工数量", "right"),
            ("unit", "单位", "center"),
            ("unit_cost", "成本", "money right"),
            ("amount", "金额", "money right"),
            ("lot_no", "批号", ""),
            ("serial_no", "机号", ""),
            ("warehouse_name", "入库仓库", ""),
        ]
        total_quantity = sum((as_decimal(row.get("quantity")) for row in rows), Decimal("0"))
    doc = {
        "title": title,
        "subtitle": "机床 ERP 单据打印",
        "number": order.get("wo_no"),
        "date": order.get("wo_date"),
        "status_label": order.get("status") or "",
        "info": [
            ("产品", f"{order.get('product_code') or ''} / {order.get('product_name') or ''}"),
            ("计划数量", order.get("quantity")),
            ("项目号", order.get("project_code")),
            ("机号", order.get("serial_no")),
            ("仓库", order.get("warehouse_name")),
            ("备注", order.get("remark")),
        ],
        "columns": line_columns,
        "rows": rows,
        "total_quantity": total_quantity,
        "total_amount": sum((as_decimal(row.get("amount")) for row in rows), Decimal("0")),
        "remark": order.get("remark"),
        "signatures": ["制单", "生产", "仓库", "审核"],
        "print_time": datetime.now(),
    }
    document_type = "work_order_issue" if kind == "issue" else "work_order_completion"
    template_grid = build_template_grid_for_document(document_type, doc, query_one)
    return render_template("document_print.html", doc=doc, template_grid=template_grid)
