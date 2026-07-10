# -*- coding: utf-8 -*-
"""
成本引擎服务 (P0-3)

实现成本归集、成本计算运行、成本汇总等核心能力。
所有金额均使用 Decimal 处理；DDL 已在 services/schema_migrations.py
的 20260621_004_p0_cost_engine 迁移中定义，本服务在请求期不再执行 DDL。

核心功能：
1. 按项目号/柜号/工单归集材料、人工、制造费用、委外、售后、质量成本
2. 生成成本计算运行记录 (cost_runs / cost_run_items)
3. 查询成本运行明细
4. 项目/柜号成本汇总
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from services.trace_engine import create_trace_link as _create_trace_link

logger = logging.getLogger(__name__)


COST_TYPE_MATERIAL = "material"
COST_TYPE_LABOR = "labor"
COST_TYPE_OVERHEAD = "overhead"
COST_TYPE_OUTSOURCE = "outsource"
COST_TYPE_SERVICE = "service"
COST_TYPE_QUALITY = "quality"

COST_TYPE_LABELS = {
    COST_TYPE_MATERIAL: "材料成本",
    COST_TYPE_LABOR: "人工成本",
    COST_TYPE_OVERHEAD: "制造费用",
    COST_TYPE_OUTSOURCE: "委外成本",
    COST_TYPE_SERVICE: "售后成本",
    COST_TYPE_QUALITY: "质量成本",
}

SOURCE_TYPE_MATERIAL_ISSUE = "工单领料"
SOURCE_TYPE_MATERIAL_RETURN = "工单退料"
SOURCE_TYPE_LABOR = "工序人工"
SOURCE_TYPE_OVERHEAD = "工序设备"
SOURCE_TYPE_OUTSOURCE = "委外成本"
SOURCE_TYPE_SERVICE = "售后服务"
SOURCE_TYPE_QUALITY = "质量成本"

CLOSED_STATUS = (
    "已关闭",
    "已完成",
    "已作废",
    "closed",
    "completed",
    "void",
    "voided",
    "cancelled",
    "canceled",
)


def _decimal(value: Any) -> Decimal:
    try:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _optional_columns(query_rows, table_name: str) -> set:
    rows = query_rows(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    return {row.get("column_name") for row in rows or []}


def _has_column(query_rows, table_name: str, column: str) -> bool:
    return column in _optional_columns(query_rows, table_name)


def _work_order_filter_clause(
    *,
    project_code: Optional[str],
    cabinet_no: Optional[str],
    work_order_id: Optional[int],
    wo_alias: str = "wo",
) -> Tuple[str, List[Any]]:
    """构造 work_orders 维度的过滤条件，返回 (where_sql_without_leading_AND, params)。"""
    clauses: List[str] = []
    params: List[Any] = []
    if work_order_id:
        clauses.append(f"{wo_alias}.id=%s")
        params.append(work_order_id)
    if project_code:
        clauses.append(f"COALESCE({wo_alias}.project_code, '')=%s")
        params.append(project_code)
    if cabinet_no:
        clauses.append(f"COALESCE({wo_alias}.cabinet_no, '')=%s")
        params.append(cabinet_no)
    if not clauses:
        return "1=1", params
    return " AND ".join(clauses), params


# ---------------------------------------------------------------------------
# 材料成本归集
# ---------------------------------------------------------------------------
def collect_material_costs(
    query_one,
    query_rows,
    *,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
    work_order_id: Optional[int] = None,
) -> Tuple[Decimal, List[Dict]]:
    """从 wo_material_items 归集材料成本（领料为正、退料为负）。"""
    wo_columns = _optional_columns(query_rows, "work_orders")
    if "project_code" not in wo_columns and "cabinet_no" not in wo_columns and not work_order_id:
        # 没有任何过滤条件可用且 work_orders 缺关键字段时直接返回空
        return Decimal("0"), []

    where_sql, params = _work_order_filter_clause(
        project_code=project_code,
        cabinet_no=cabinet_no,
        work_order_id=work_order_id,
        wo_alias="wo",
    )

    rows = query_rows(
        f"""
        SELECT mi.id, mi.product_id, mi.wo_id AS work_order_id,
               COALESCE(mi.issued_qty, 0) AS issued_qty,
               COALESCE(mi.returned_qty, 0) AS returned_qty,
               COALESCE(NULLIF(mi.unit_cost, 0), p.standard_price, 0) AS unit_cost,
               COALESCE(mi.material_name, p.name, mi.material_code, p.code) AS material_name,
               wo.wo_no, wo.project_code, wo.cabinet_no
        FROM wo_material_items mi
        JOIN work_orders wo ON wo.id=mi.wo_id
        LEFT JOIN products p ON p.id=mi.product_id
        WHERE {where_sql}
        ORDER BY mi.id
        """,
        tuple(params),
    )

    lines: List[Dict] = []
    total = Decimal("0")
    for row in rows or []:
        issued_qty = _decimal(row.get("issued_qty"))
        returned_qty = _decimal(row.get("returned_qty"))
        unit_cost = _decimal(row.get("unit_cost"))
        wo_id = row.get("work_order_id")
        proj = row.get("project_code")
        sno = row.get("cabinet_no")
        if issued_qty > 0:
            amount = issued_qty * unit_cost
            total += amount
            lines.append({
                "cost_type": COST_TYPE_MATERIAL,
                "source_type": SOURCE_TYPE_MATERIAL_ISSUE,
                "source_id": row.get("id"),
                "source_no": f"WO-MAT-{row.get('id')}",
                "product_id": row.get("product_id"),
                "quantity": issued_qty,
                "unit_cost": unit_cost,
                "amount": amount,
                "work_order_id": wo_id,
                "project_code": proj,
                "cabinet_no": sno,
                "remark": row.get("material_name") or "",
            })
        if returned_qty > 0:
            amount = returned_qty * unit_cost * Decimal("-1")
            total += amount
            lines.append({
                "cost_type": COST_TYPE_MATERIAL,
                "source_type": SOURCE_TYPE_MATERIAL_RETURN,
                "source_id": row.get("id"),
                "source_no": f"WO-MAT-{row.get('id')}",
                "product_id": row.get("product_id"),
                "quantity": returned_qty,
                "unit_cost": unit_cost,
                "amount": amount,
                "work_order_id": wo_id,
                "project_code": proj,
                "cabinet_no": sno,
                "remark": row.get("material_name") or "",
            })
    return total, lines


# ---------------------------------------------------------------------------
# 人工成本归集
# ---------------------------------------------------------------------------
def collect_labor_costs(
    query_one,
    query_rows,
    *,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
    work_order_id: Optional[int] = None,
) -> Tuple[Decimal, List[Dict]]:
    """从 operation_reports 归集人工成本。

    优先读取 labor_cost 列（如果存在）；否则从 labor_hours × 员工/工作中心费率派生。
    """
    op_columns = _optional_columns(query_rows, "operation_reports")
    if "work_order_id" not in op_columns:
        return Decimal("0"), []

    has_labor_cost_col = "labor_cost" in op_columns
    has_labor_hours = "labor_hours" in op_columns

    # If neither a direct cost column nor hours exist, nothing to collect.
    if not has_labor_cost_col and not has_labor_hours:
        return Decimal("0"), []

    where_sql, params = _work_order_filter_clause(
        project_code=project_code,
        cabinet_no=cabinet_no,
        work_order_id=work_order_id,
        wo_alias="wo",
    )
    report_no_expr = "opr.report_no" if "report_no" in op_columns else "'OPR-' || opr.id::text"

    # Build the labor cost expression: prefer direct column, else derive from hours × rate.
    extra_joins = ""
    if has_labor_cost_col:
        labor_cost_expr = "COALESCE(opr.labor_cost, 0)"
    else:
        # Derive from labor_hours × rate, mirroring production_routes._load_operation_report_cost_summary.
        labor_hours_expr = "COALESCE(opr.labor_hours, 0)"
        wc_rate = "0"
        wc_columns = _optional_columns(query_rows, "work_centers")
        if "work_center_id" in op_columns and wc_columns:
            extra_joins += " LEFT JOIN work_centers wc ON wc.id=opr.work_center_id"
            if "labor_rate_per_hour" in wc_columns:
                wc_rate = "COALESCE(wc.labor_rate_per_hour, 0)"

        emp_rate = wc_rate
        emp_columns = _optional_columns(query_rows, "employees")
        if "operator_id" in op_columns and emp_columns:
            extra_joins += " LEFT JOIN employees emp ON emp.id=opr.operator_id"
            if "standard_labor_rate_per_hour" in emp_columns:
                emp_rate = f"COALESCE(emp.standard_labor_rate_per_hour, {wc_rate}, 0)"

        labor_cost_expr = f"({labor_hours_expr}) * ({emp_rate})"

    rows = query_rows(
        f"""
        SELECT opr.id, opr.work_order_id,
               {labor_cost_expr} AS labor_cost,
               {report_no_expr} AS report_no,
               wo.wo_no, wo.product_id, wo.project_code, wo.cabinet_no
        FROM operation_reports opr
        {extra_joins}
        JOIN work_orders wo ON wo.id=opr.work_order_id
        WHERE {where_sql}
        ORDER BY opr.id
        """,
        tuple(params),
    )

    lines: List[Dict] = []
    total = Decimal("0")
    for row in rows or []:
        labor = _decimal(row.get("labor_cost"))
        if labor == 0:
            continue
        total += labor
        lines.append({
            "cost_type": COST_TYPE_LABOR,
            "source_type": SOURCE_TYPE_LABOR,
            "source_id": row.get("id"),
            "source_no": row.get("report_no"),
            "product_id": row.get("product_id"),
            "quantity": Decimal("0"),
            "unit_cost": Decimal("0"),
            "amount": labor,
            "work_order_id": row.get("work_order_id"),
            "project_code": row.get("project_code"),
            "cabinet_no": row.get("cabinet_no"),
            "remark": "工序报工人工归集",
        })
    return total, lines


# ---------------------------------------------------------------------------
# 制造费用归集
# ---------------------------------------------------------------------------
def collect_overhead_costs(
    query_one,
    query_rows,
    *,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
    work_order_id: Optional[int] = None,
) -> Tuple[Decimal, List[Dict]]:
    """从 operation_reports 归集制造费用（设备/制造成本）。

    优先读取 overhead_cost/equipment_cost 列（如果存在）；否则从 equipment_hours × 工作中心费率派生。
    """
    op_columns = _optional_columns(query_rows, "operation_reports")
    if "work_order_id" not in op_columns:
        return Decimal("0"), []

    overhead_column = None
    if "overhead_cost" in op_columns:
        overhead_column = "overhead_cost"
    elif "equipment_cost" in op_columns:
        overhead_column = "equipment_cost"

    has_equipment_hours = "equipment_hours" in op_columns

    # If neither a direct cost column nor hours exist, nothing to collect.
    if not overhead_column and not has_equipment_hours:
        return Decimal("0"), []

    where_sql, params = _work_order_filter_clause(
        project_code=project_code,
        cabinet_no=cabinet_no,
        work_order_id=work_order_id,
        wo_alias="wo",
    )
    report_no_expr = "opr.report_no" if "report_no" in op_columns else "'OPR-' || opr.id::text"

    # Build the overhead cost expression.
    extra_joins = ""
    if overhead_column:
        overhead_cost_expr = f"COALESCE(opr.{overhead_column}, 0)"
    else:
        # Derive from equipment_hours × work center overhead rate.
        equipment_hours_expr = "COALESCE(opr.equipment_hours, 0)"
        oh_rate = "0"
        wc_columns = _optional_columns(query_rows, "work_centers")
        if "work_center_id" in op_columns and wc_columns:
            extra_joins += " LEFT JOIN work_centers wc ON wc.id=opr.work_center_id"
            if "overhead_rate_per_hour" in wc_columns:
                oh_rate = "COALESCE(wc.overhead_rate_per_hour, 0)"
        overhead_cost_expr = f"({equipment_hours_expr}) * ({oh_rate})"

    rows = query_rows(
        f"""
        SELECT opr.id, opr.work_order_id,
               {overhead_cost_expr} AS overhead_cost,
               {report_no_expr} AS report_no,
               wo.wo_no, wo.product_id, wo.project_code, wo.cabinet_no
        FROM operation_reports opr
        {extra_joins}
        JOIN work_orders wo ON wo.id=opr.work_order_id
        WHERE {where_sql}
        ORDER BY opr.id
        """,
        tuple(params),
    )

    lines: List[Dict] = []
    total = Decimal("0")
    for row in rows or []:
        overhead = _decimal(row.get("overhead_cost"))
        if overhead == 0:
            continue
        total += overhead
        lines.append({
            "cost_type": COST_TYPE_OVERHEAD,
            "source_type": SOURCE_TYPE_OVERHEAD,
            "source_id": row.get("id"),
            "source_no": row.get("report_no"),
            "product_id": row.get("product_id"),
            "quantity": Decimal("0"),
            "unit_cost": Decimal("0"),
            "amount": overhead,
            "work_order_id": row.get("work_order_id"),
            "project_code": row.get("project_code"),
            "cabinet_no": row.get("cabinet_no"),
            "remark": "工序报工设备/制造费用归集",
        })
    return total, lines


# ---------------------------------------------------------------------------
# 委外成本归集
# ---------------------------------------------------------------------------
def collect_outsource_costs(
    query_one,
    query_rows,
    *,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
    work_order_id: Optional[int] = None,
) -> Tuple[Decimal, List[Dict]]:
    """从 supplier_payables (doc_type='subcontract_receive') 归集委外成本。"""
    sp_columns = _optional_columns(query_rows, "supplier_payables")
    if "doc_type" not in sp_columns and "source_type" not in sp_columns:
        return Decimal("0"), []

    clauses: List[str] = [
        "COALESCE(sp.doc_type, sp.source_type, '') IN ('subcontract_receive','subcontract_receive_order')",
        "COALESCE(sp.status, '') NOT IN %s",
    ]
    params: List[Any] = [tuple(CLOSED_STATUS)]

    if work_order_id:
        clauses.append("COALESCE(sc.parent_work_order_id, 0)=%s")
        params.append(work_order_id)
    if project_code:
        clauses.append("COALESCE(sp.project_code, sc.project_code, '')=%s")
        params.append(project_code)
    if cabinet_no:
        clauses.append("COALESCE(sp.cabinet_no, sc.cabinet_no, '')=%s")
        params.append(cabinet_no)

    where_sql = " AND ".join(clauses)

    rows = query_rows(
        f"""
        SELECT sp.id, sp.doc_id,
               COALESCE(sp.doc_no, sro.receive_no) AS source_no,
               COALESCE(NULLIF(sp.confirmed_amount, 0), sp.amount, 0) AS amount,
               COALESCE(sro.total_quantity, 0) AS quantity,
               sp.project_code, sp.cabinet_no,
               sc.parent_work_order_id AS work_order_id
        FROM supplier_payables sp
        LEFT JOIN subcontract_receive_orders sro ON sro.id=sp.doc_id
        LEFT JOIN subcontract_orders sc ON sc.id=sro.subcontract_order_id
        WHERE {where_sql}
        ORDER BY sp.id
        """,
        tuple(params),
    )

    lines: List[Dict] = []
    total = Decimal("0")
    seen: set = set()
    for row in rows or []:
        rid = row.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        amount = _decimal(row.get("amount"))
        if amount == 0:
            continue
        total += amount
        lines.append({
            "cost_type": COST_TYPE_OUTSOURCE,
            "source_type": SOURCE_TYPE_OUTSOURCE,
            "source_id": rid,
            "source_no": row.get("source_no"),
            "product_id": None,
            "quantity": _decimal(row.get("quantity")),
            "unit_cost": Decimal("0"),
            "amount": amount,
            "work_order_id": row.get("work_order_id"),
            "project_code": row.get("project_code"),
            "cabinet_no": row.get("cabinet_no"),
            "remark": "委外收货应付成本归集",
        })
    return total, lines


# ---------------------------------------------------------------------------
# 售后服务成本归集
# ---------------------------------------------------------------------------
def collect_service_costs(
    query_one,
    query_rows,
    *,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
) -> Tuple[Decimal, List[Dict]]:
    """从 machine_service_orders 归集售后服务成本。"""
    if not cabinet_no and not project_code:
        return Decimal("0"), []

    mso_columns = _optional_columns(query_rows, "machine_service_orders")
    if not mso_columns:
        return Decimal("0"), []

    clauses: List[str] = []
    params: List[Any] = []
    if cabinet_no:
        clauses.append("COALESCE(mso.cabinet_no, '')=%s")
        params.append(cabinet_no)
    if project_code:
        clauses.append("COALESCE(mso.project_code, '')=%s")
        params.append(project_code)
    clauses.append("COALESCE(mso.status, '') NOT IN %s")
    params.append(tuple(CLOSED_STATUS))
    where_sql = " AND ".join(clauses)

    parts_expr = "mso.parts_cost" if "parts_cost" in mso_columns else "0"
    labor_expr = "mso.labor_cost" if "labor_cost" in mso_columns else "0"
    travel_expr = "mso.travel_cost" if "travel_cost" in mso_columns else "0"
    total_cost_expr = "mso.total_cost" if "total_cost" in mso_columns else (
        f"COALESCE({parts_expr},0)+COALESCE({labor_expr},0)+COALESCE({travel_expr},0)"
    )

    rows = query_rows(
        f"""
        SELECT mso.id, mso.order_no,
               COALESCE({total_cost_expr}, 0) AS amount,
               COALESCE({parts_expr}, 0) AS parts_cost,
               COALESCE({labor_expr}, 0) AS labor_cost,
               COALESCE({travel_expr}, 0) AS travel_cost,
               mso.project_code, mso.cabinet_no
        FROM machine_service_orders mso
        WHERE {where_sql}
        ORDER BY mso.id
        """,
        tuple(params),
    )

    lines: List[Dict] = []
    total = Decimal("0")
    for row in rows or []:
        amount = _decimal(row.get("amount"))
        if amount == 0:
            continue
        total += amount
        remark = (
            f"售后成本：备件 {_decimal(row.get('parts_cost'))}，"
            f"人工 {_decimal(row.get('labor_cost'))}，"
            f"差旅 {_decimal(row.get('travel_cost'))}。"
        )
        lines.append({
            "cost_type": COST_TYPE_SERVICE,
            "source_type": SOURCE_TYPE_SERVICE,
            "source_id": row.get("id"),
            "source_no": row.get("order_no"),
            "product_id": None,
            "quantity": Decimal("0"),
            "unit_cost": Decimal("0"),
            "amount": amount,
            "work_order_id": None,
            "project_code": row.get("project_code"),
            "cabinet_no": row.get("cabinet_no"),
            "remark": remark,
        })
    return total, lines


# ---------------------------------------------------------------------------
# 质量成本归集
# ---------------------------------------------------------------------------
def collect_quality_costs(
    query_one,
    query_rows,
    *,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
    work_order_id: Optional[int] = None,
) -> Tuple[Decimal, List[Dict]]:
    """从 operation_reports.scrap_qty 与 work_order_costs.scrap_cost 归集质量成本。

    若表/列缺失则返回 0，保持防御性。
    """
    op_columns = _optional_columns(query_rows, "operation_reports")
    woc_columns = _optional_columns(query_rows, "work_order_costs")

    lines: List[Dict] = []
    total = Decimal("0")

    # 优先使用 work_order_costs.scrap_cost
    if "scrap_cost" in woc_columns and (work_order_id or project_code or cabinet_no):
        where_sql, params = _work_order_filter_clause(
            project_code=project_code,
            cabinet_no=cabinet_no,
            work_order_id=work_order_id,
            wo_alias="wo",
        )
        rows = query_rows(
            f"""
            SELECT woc.id, woc.work_order_id, woc.scrap_cost,
                   wo.wo_no, wo.project_code, wo.cabinet_no, wo.product_id
            FROM work_order_costs woc
            JOIN work_orders wo ON wo.id=woc.work_order_id
            WHERE {where_sql}
              AND COALESCE(woc.scrap_cost, 0) <> 0
            ORDER BY woc.id
            """,
            tuple(params),
        )
        for row in rows or []:
            amount = _decimal(row.get("scrap_cost"))
            if amount == 0:
                continue
            total += amount
            lines.append({
                "cost_type": COST_TYPE_QUALITY,
                "source_type": SOURCE_TYPE_QUALITY,
                "source_id": row.get("id"),
                "source_no": f"WOC-{row.get('id')}",
                "product_id": row.get("product_id"),
                "quantity": Decimal("0"),
                "unit_cost": Decimal("0"),
                "amount": amount,
                "work_order_id": row.get("work_order_id"),
                "project_code": row.get("project_code"),
                "cabinet_no": row.get("cabinet_no"),
                "remark": "工单报废成本归集",
            })

    # 补充：从 operation_reports.scrap_qty * standard_price 估算
    if "scrap_qty" in op_columns and "work_order_id" in op_columns and (work_order_id or project_code or cabinet_no):
        where_sql, params = _work_order_filter_clause(
            project_code=project_code,
            cabinet_no=cabinet_no,
            work_order_id=work_order_id,
            wo_alias="wo",
        )
        report_no_expr = "opr.report_no" if "report_no" in op_columns else "'OPR-' || opr.id::text"
        rows = query_rows(
            f"""
            SELECT opr.id, opr.work_order_id, opr.scrap_qty,
                   {report_no_expr} AS report_no,
                   wo.wo_no, wo.product_id, wo.project_code, wo.cabinet_no,
                   COALESCE(p.standard_price, 0) AS unit_cost
            FROM operation_reports opr
            JOIN work_orders wo ON wo.id=opr.work_order_id
            LEFT JOIN products p ON p.id=wo.product_id
            WHERE {where_sql}
              AND COALESCE(opr.scrap_qty, 0) > 0
            ORDER BY opr.id
            """,
            tuple(params),
        )
        for row in rows or []:
            scrap_qty = _decimal(row.get("scrap_qty"))
            unit_cost = _decimal(row.get("unit_cost"))
            amount = scrap_qty * unit_cost
            if amount == 0:
                continue
            total += amount
            lines.append({
                "cost_type": COST_TYPE_QUALITY,
                "source_type": SOURCE_TYPE_QUALITY,
                "source_id": row.get("id"),
                "source_no": row.get("report_no"),
                "product_id": row.get("product_id"),
                "quantity": scrap_qty,
                "unit_cost": unit_cost,
                "amount": amount,
                "work_order_id": row.get("work_order_id"),
                "project_code": row.get("project_code"),
                "cabinet_no": row.get("cabinet_no"),
                "remark": "工序报废数量 * 标准成本估算",
            })

    return total, lines


# ---------------------------------------------------------------------------
# 主入口：成本计算运行
# ---------------------------------------------------------------------------
def _generate_run_no(query_one) -> str:
    today = date.today()
    prefix = f"COST-{today.strftime('%Y%m%d')}-"
    row = query_one(
        """
        SELECT run_no
        FROM cost_runs
        WHERE run_no LIKE %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (f"{prefix}%",),
    )
    seq = 1
    if row and row.get("run_no"):
        try:
            seq = int(str(row["run_no"]).rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:03d}"


def _sync_cost_run_to_ledgers(
    query_rows,
    execute_db,
    run_id: int,
    run_no: str,
    period: Optional[str] = None,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
    created_by: Optional[int] = None,
) -> int:
    """Sync cost_run_items into cabinet_cost_ledger / project_cost_ledger.

    Bridges the dual-track cost system: the engine-populated cost_runs and
    the ledger tables used by cabinet/project cost reports. Items with a
    cabinet_no are synced to cabinet_cost_ledger; items with only a
    project_code are synced to project_cost_ledger. Re-running replaces
    previous ledger entries for the same run (idempotent).

    Returns the number of ledger rows synced.
    """
    # Idempotent re-runs: remove previous sync for this run.
    execute_db(
        "DELETE FROM cabinet_cost_ledger WHERE source_no = %s AND source_type = 'cost_run'",
        (run_no,),
    )
    execute_db(
        "DELETE FROM project_cost_ledger WHERE source_no = %s AND source_type = 'cost_run'",
        (run_no,),
    )

    items = query_rows(
        """
        SELECT cost_type, source_type, source_id, source_no,
               product_id, quantity, unit_cost, amount,
               project_code, cabinet_no, work_order_id
        FROM cost_run_items
        WHERE run_id = %s
        """,
        (run_id,),
    ) or []

    # Resolve cost_date: use last day of period if given, else today.
    cost_date = date.today()
    if period:
        try:
            year, month = period.split("-")
            y, m = int(year), int(month)
            if m == 12:
                cost_date = date(y, 12, 31)
            else:
                cost_date = date(y, m + 1, 1) - timedelta(days=1)
        except Exception:
            cost_date = date.today()

    synced = 0
    for item in items:
        item_cabinet = item.get("cabinet_no") or cabinet_no
        item_project = item.get("project_code") or project_code
        amount = _decimal(item.get("amount"))
        # Map English cost_type to Chinese label for ledger categorization.
        cost_type_label = COST_TYPE_LABELS.get(item.get("cost_type"), item.get("cost_type") or "")
        description = f"成本运行 {run_no} 自动归集"

        if item_cabinet:
            execute_db(
                """
                INSERT INTO cabinet_cost_ledger
                    (cabinet_no, product_id, project_code, cost_date, cost_type,
                     source_type, source_no, description,
                     cost_amount, debit_amount, credit_amount,
                     quantity, unit_cost, work_order_id,
                     recorded_by, created_by, remark)
                VALUES (%s,%s,%s,%s,%s,'cost_run',%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s)
                """,
                (
                    item_cabinet,
                    item.get("product_id"),
                    item_project,
                    cost_date,
                    cost_type_label,
                    run_no,
                    description,
                    float(amount),
                    float(amount),
                    item.get("quantity"),
                    item.get("unit_cost"),
                    item.get("work_order_id"),
                    created_by,
                    created_by,
                    item.get("source_type"),
                ),
            )
            synced += 1
        elif item_project:
            execute_db(
                """
                INSERT INTO project_cost_ledger
                    (project_code, cost_date, cost_type,
                     source_type, source_no, description,
                     cost_amount, debit_amount, credit_amount,
                     quantity, unit_cost,
                     recorded_by, created_by, remark)
                VALUES (%s,%s,%s,'cost_run',%s,%s,%s,%s,0,%s,%s,%s,%s,%s)
                """,
                (
                    item_project,
                    cost_date,
                    cost_type_label,
                    run_no,
                    description,
                    float(amount),
                    float(amount),
                    item.get("quantity"),
                    item.get("unit_cost"),
                    created_by,
                    created_by,
                    item.get("source_type"),
                ),
            )
            synced += 1

    return synced


def run_cost_calculation(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    *,
    period: Optional[str] = None,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
    work_order_id: Optional[int] = None,
    created_by: Optional[int] = None,
) -> Dict:
    """执行一次成本计算运行，写入 cost_runs / cost_run_items。"""
    run_no = _generate_run_no(query_one)

    execute_db(
        """
        INSERT INTO cost_runs
            (run_no, period, project_code, cabinet_no, work_order_id,
             status, total_material_cost, total_labor_cost, total_overhead_cost,
             total_outsource_cost, total_quality_cost, total_service_cost,
             total_cost, created_by, created_at)
        VALUES (%s,%s,%s,%s,%s,'draft',0,0,0,0,0,0,0,%s,NOW())
        """,
        (run_no, period, project_code, cabinet_no, work_order_id, created_by),
    )

    run_row = query_one(
        "SELECT id FROM cost_runs WHERE run_no=%s",
        (run_no,),
    )
    if not run_row:
        return {"success": False, "message": "无法创建成本运行记录", "run_no": run_no}
    run_id = run_row.get("id")

    material_total, material_lines = collect_material_costs(
        query_one, query_rows,
        project_code=project_code, cabinet_no=cabinet_no, work_order_id=work_order_id,
    )
    labor_total, labor_lines = collect_labor_costs(
        query_one, query_rows,
        project_code=project_code, cabinet_no=cabinet_no, work_order_id=work_order_id,
    )
    overhead_total, overhead_lines = collect_overhead_costs(
        query_one, query_rows,
        project_code=project_code, cabinet_no=cabinet_no, work_order_id=work_order_id,
    )
    outsource_total, outsource_lines = collect_outsource_costs(
        query_one, query_rows,
        project_code=project_code, cabinet_no=cabinet_no, work_order_id=work_order_id,
    )
    service_total, service_lines = collect_service_costs(
        query_one, query_rows,
        project_code=project_code, cabinet_no=cabinet_no,
    )
    quality_total, quality_lines = collect_quality_costs(
        query_one, query_rows,
        project_code=project_code, cabinet_no=cabinet_no, work_order_id=work_order_id,
    )

    all_lines = (
        material_lines + labor_lines + overhead_lines
        + outsource_lines + service_lines + quality_lines
    )

    # P2-B3: 为每条成本行计算标准成本与差异
    # 标准成本来源：products.standard_price（材料/质量）或 work_centers 标准费率（人工/制造费用）
    # 对于无明确标准价的成本类型（委外/售后），standard_cost = unit_cost，variance = 0
    product_ids = set()
    for line in all_lines:
        pid = line.get("product_id")
        if pid:
            product_ids.add(int(pid))
    product_standard_map: Dict[int, Decimal] = {}
    if product_ids:
        pid_list = tuple(product_ids)
        std_rows = query_rows(
            f"SELECT id, COALESCE(standard_price, 0) AS standard_price FROM products WHERE id IN %s",
            (pid_list,),
        )
        for r in std_rows or []:
            product_standard_map[int(r["id"])] = _decimal(r.get("standard_price"))

    for line in all_lines:
        pid = line.get("product_id")
        qty = _decimal(line.get("quantity"))
        actual_unit = _decimal(line.get("unit_cost"))
        actual_amount = _decimal(line.get("amount"))
        cost_type = line.get("cost_type")
        # 标准成本逻辑：材料/质量按产品标准价计算差异；
        # 人工/制造费用/委外/售后无标准价基准，standard_cost = actual_amount，variance = 0
        if pid and cost_type in (COST_TYPE_MATERIAL, COST_TYPE_QUALITY):
            std_unit = product_standard_map.get(int(pid), Decimal("0"))
            std_amount = qty * std_unit
            variance = actual_amount - std_amount
        else:
            std_amount = actual_amount
            variance = Decimal("0")
        line["standard_cost"] = std_amount
        line["variance_amount"] = variance
        line["variance_reason"] = ""
        if abs(variance) > Decimal("0.01"):
            if variance > 0:
                line["variance_reason"] = f"实际成本超标准 {variance:.4f}"
            else:
                line["variance_reason"] = f"实际成本低于标准 {abs(variance):.4f}"

        execute_db(
            """
            INSERT INTO cost_run_items
                (run_id, cost_type, source_type, source_id, source_no,
                 product_id, quantity, unit_cost, amount,
                 standard_cost, variance_amount, variance_reason,
                 project_code, cabinet_no, work_order_id, remark, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """,
            (
                run_id,
                line.get("cost_type"),
                line.get("source_type"),
                line.get("source_id"),
                line.get("source_no"),
                line.get("product_id"),
                line.get("quantity"),
                line.get("unit_cost"),
                line.get("amount"),
                line.get("standard_cost"),
                line.get("variance_amount"),
                line.get("variance_reason"),
                line.get("project_code"),
                line.get("cabinet_no"),
                line.get("work_order_id"),
                line.get("remark"),
            ),
        )

    total_cost = (
        material_total + labor_total + overhead_total
        + outsource_total + service_total + quality_total
    )

    execute_db(
        """
        UPDATE cost_runs
        SET status='completed',
            total_material_cost=%s,
            total_labor_cost=%s,
            total_overhead_cost=%s,
            total_outsource_cost=%s,
            total_quality_cost=%s,
            total_service_cost=%s,
            total_cost=%s
        WHERE id=%s
        """,
        (
            material_total, labor_total, overhead_total,
            outsource_total, quality_total, service_total,
            total_cost, run_id,
        ),
    )

    # Write trace_links from source documents to this cost run so the trace
    # graph can connect operational documents to their cost absorption.
    # We link work orders and supplier payables (outsource) to the cost run.
    _linked_sources = set()
    for line in all_lines:
        source_type = line.get("source_type") or ""
        source_id = line.get("source_id")
        if not source_id:
            continue
        # Map cost source types to trace doc types.
        if "工单" in source_type or "领料" in source_type or "报工" in source_type:
            trace_doc_type = "work_order"
            wo_id = line.get("work_order_id") or source_id
            link_key = ("work_order", wo_id)
        elif "委外" in source_type or "应付" in source_type:
            trace_doc_type = "supplier_payable"
            link_key = ("supplier_payable", source_id)
        elif "售后" in source_type or "服务" in source_type:
            trace_doc_type = "machine_service_order"
            link_key = ("machine_service_order", source_id)
        else:
            continue
        if link_key in _linked_sources:
            continue
        _linked_sources.add(link_key)
        try:
            _create_trace_link(
                query_one,
                execute_db,
                source_doc_type=trace_doc_type,
                source_doc_id=wo_id if trace_doc_type == "work_order" else source_id,
                target_doc_type="cost_run",
                target_doc_id=run_id,
                target_doc_no=run_no,
                link_type="posts_to",
                link_strength="soft",
                project_code=project_code,
                cabinet_no=cabinet_no,
                created_by=created_by,
                created_event="cost_run",
                execute_and_return=execute_and_return,
            )
        except Exception:
            # Trace link failure must not block cost run completion.
            logger.warning("cost run trace link failed for run_no=%s", run_no, exc_info=True)
            pass

    # Sync cost run results into cabinet/project cost ledgers so the
    # cabinet_cost_service / project_cost_service reports reflect engine
    # output without requiring manual AJAX entry.
    ledger_synced = 0
    try:
        ledger_synced = _sync_cost_run_to_ledgers(
            query_rows,
            execute_db,
            run_id=run_id,
            run_no=run_no,
            period=period,
            project_code=project_code,
            cabinet_no=cabinet_no,
            created_by=created_by,
        )
    except Exception:
        # Ledger sync failure must not block cost run completion.
        logger.warning("cost run ledger sync failed for run_no=%s", run_no, exc_info=True)
        pass

    return {
        "success": True,
        "run_id": run_id,
        "run_no": run_no,
        "period": period,
        "project_code": project_code,
        "cabinet_no": cabinet_no,
        "work_order_id": work_order_id,
        "totals": {
            "material": material_total,
            "labor": labor_total,
            "overhead": overhead_total,
            "outsource": outsource_total,
            "service": service_total,
            "quality": quality_total,
            "total": total_cost,
        },
        "line_count": len(all_lines),
        "ledger_synced": ledger_synced,
    }


# ---------------------------------------------------------------------------
# 查询接口
# ---------------------------------------------------------------------------
def get_cost_run(query_one, query_rows, run_id: int) -> Dict:
    """获取成本运行头 + 按 cost_type 分组的明细。

    返回结构：
    {
        "found": True,
        "run": {...},                # cost_runs 头
        "items_by_type": {           # 按 cost_type 分组的明细
            "material": [...],
            "labor": [...],
            ...
        },
        "items": [...]               # 全部明细（按 cost_type, id 排序）
    }
    """
    run = query_one(
        """
        SELECT id, run_no, period, project_code, cabinet_no, work_order_id,
               status, total_material_cost, total_labor_cost, total_overhead_cost,
               total_outsource_cost, total_quality_cost, total_service_cost,
               total_cost, created_by, created_at
        FROM cost_runs
        WHERE id=%s
        """,
        (run_id,),
    )
    if not run:
        return {"found": False}

    items = query_rows(
        """
        SELECT id, run_id, cost_type, source_type, source_id, source_no,
               product_id, quantity, unit_cost, amount,
               project_code, cabinet_no, work_order_id, remark, created_at
        FROM cost_run_items
        WHERE run_id=%s
        ORDER BY cost_type, id
        """,
        (run_id,),
    ) or []

    items_by_type: Dict[str, List[Dict]] = {
        COST_TYPE_MATERIAL: [],
        COST_TYPE_LABOR: [],
        COST_TYPE_OVERHEAD: [],
        COST_TYPE_OUTSOURCE: [],
        COST_TYPE_SERVICE: [],
        COST_TYPE_QUALITY: [],
    }
    for item in items:
        ct = item.get("cost_type") or "other"
        items_by_type.setdefault(ct, []).append(item)

    return {"found": True, "run": run, "items": items, "items_by_type": items_by_type}


def get_cost_run_items(query_rows, run_id: int) -> List[Dict]:
    """获取成本运行明细行。"""
    return query_rows(
        """
        SELECT id, run_id, cost_type, source_type, source_id, source_no,
               product_id, quantity, unit_cost, amount,
               project_code, cabinet_no, work_order_id, remark, created_at
        FROM cost_run_items
        WHERE run_id=%s
        ORDER BY cost_type, id
        """,
        (run_id,),
    )


def list_cost_runs(query_rows, filters: Optional[Dict] = None) -> List[Dict]:
    """列出成本运行记录。"""
    filters = filters or {}
    clauses: List[str] = ["1=1"]
    params: List[Any] = []
    if filters.get("period"):
        clauses.append("period=%s")
        params.append(filters["period"])
    if filters.get("project_code"):
        clauses.append("COALESCE(project_code, '')=%s")
        params.append(filters["project_code"])
    if filters.get("cabinet_no"):
        clauses.append("COALESCE(cabinet_no, '')=%s")
        params.append(filters["cabinet_no"])
    if filters.get("status"):
        clauses.append("status=%s")
        params.append(filters["status"])
    if filters.get("keyword"):
        clauses.append("run_no ILIKE %s")
        params.append(f"%{filters['keyword']}%")
    where_sql = " AND ".join(clauses)
    rows = query_rows(
        f"""
        SELECT id, run_no, period, project_code, cabinet_no, work_order_id,
               status, total_material_cost, total_labor_cost, total_overhead_cost,
               total_outsource_cost, total_quality_cost, total_service_cost,
               total_cost, created_by, created_at
        FROM cost_runs
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT 200
        """,
        tuple(params),
    )
    return rows or []


def get_project_cost_summary(query_one, project_code: str) -> Dict:
    """汇总指定项目的所有成本运行结果。"""
    if not project_code:
        return {
            "project_code": "",
            "material": Decimal("0"),
            "labor": Decimal("0"),
            "overhead": Decimal("0"),
            "outsource": Decimal("0"),
            "service": Decimal("0"),
            "quality": Decimal("0"),
            "total": Decimal("0"),
            "run_count": 0,
        }
    row = query_one(
        """
        SELECT COUNT(*) AS run_count,
               COALESCE(SUM(total_material_cost), 0) AS material,
               COALESCE(SUM(total_labor_cost), 0) AS labor,
               COALESCE(SUM(total_overhead_cost), 0) AS overhead,
               COALESCE(SUM(total_outsource_cost), 0) AS outsource,
               COALESCE(SUM(total_service_cost), 0) AS service,
               COALESCE(SUM(total_quality_cost), 0) AS quality,
               COALESCE(SUM(total_cost), 0) AS total
        FROM cost_runs
        WHERE project_code=%s AND status='completed'
        """,
        (project_code,),
    ) or {}
    return {
        "project_code": project_code,
        "material": _decimal(row.get("material")),
        "labor": _decimal(row.get("labor")),
        "overhead": _decimal(row.get("overhead")),
        "outsource": _decimal(row.get("outsource")),
        "service": _decimal(row.get("service")),
        "quality": _decimal(row.get("quality")),
        "total": _decimal(row.get("total")),
        "run_count": int(row.get("run_count") or 0),
    }


def get_cabinet_cost_summary(query_one, cabinet_no: str) -> Dict:
    """汇总指定柜号的所有成本运行结果。"""
    if not cabinet_no:
        return {
            "cabinet_no": "",
            "material": Decimal("0"),
            "labor": Decimal("0"),
            "overhead": Decimal("0"),
            "outsource": Decimal("0"),
            "service": Decimal("0"),
            "quality": Decimal("0"),
            "total": Decimal("0"),
            "run_count": 0,
        }
    row = query_one(
        """
        SELECT COUNT(*) AS run_count,
               COALESCE(SUM(total_material_cost), 0) AS material,
               COALESCE(SUM(total_labor_cost), 0) AS labor,
               COALESCE(SUM(total_overhead_cost), 0) AS overhead,
               COALESCE(SUM(total_outsource_cost), 0) AS outsource,
               COALESCE(SUM(total_service_cost), 0) AS service,
               COALESCE(SUM(total_quality_cost), 0) AS quality,
               COALESCE(SUM(total_cost), 0) AS total
        FROM cost_runs
        WHERE cabinet_no=%s AND status='completed'
        """,
        (cabinet_no,),
    ) or {}
    return {
        "cabinet_no": cabinet_no,
        "material": _decimal(row.get("material")),
        "labor": _decimal(row.get("labor")),
        "overhead": _decimal(row.get("overhead")),
        "outsource": _decimal(row.get("outsource")),
        "service": _decimal(row.get("service")),
        "quality": _decimal(row.get("quality")),
        "total": _decimal(row.get("total")),
        "run_count": int(row.get("run_count") or 0),
    }


def get_cost_variance_report(query_rows, run_id: int) -> Dict:
    """P2-B3: 获取指定成本运行的标准 vs 实际差异报表。

    返回:
      - summary: 按 cost_type 汇总的标准成本、实际成本、差异
      - lines: 有差异的明细行（variance_amount != 0）
    """
    if not run_id:
        return {"summary": [], "lines": [], "total_standard": Decimal("0"),
                "total_actual": Decimal("0"), "total_variance": Decimal("0")}
    rows = query_rows(
        """
        SELECT cri.id, cri.cost_type, cri.source_type, cri.source_no,
               cri.product_id, cri.quantity, cri.unit_cost, cri.amount,
               cri.standard_cost, cri.variance_amount, cri.variance_reason,
               cri.project_code, cri.cabinet_no, cri.work_order_id,
               p.code AS product_code, p.name AS product_name,
               p.specification AS product_spec,
               cr.run_no
        FROM cost_run_items cri
        LEFT JOIN cost_runs cr ON cr.id=cri.run_id
        LEFT JOIN products p ON p.id=cri.product_id
        WHERE cri.run_id=%s
        ORDER BY ABS(cri.variance_amount) DESC, cri.id
        """,
        (run_id,),
    )
    type_map: Dict[str, Dict[str, Decimal]] = {}
    lines = []
    total_std = Decimal("0")
    total_actual = Decimal("0")
    total_var = Decimal("0")
    for row in rows or []:
        item = dict(row)
        ct = item.get("cost_type") or ""
        std = _decimal(item.get("standard_cost"))
        actual = _decimal(item.get("amount"))
        var = _decimal(item.get("variance_amount"))
        total_std += std
        total_actual += actual
        total_var += var
        if ct not in type_map:
            type_map[ct] = {"standard": Decimal("0"), "actual": Decimal("0"), "variance": Decimal("0"), "count": 0}
        type_map[ct]["standard"] += std
        type_map[ct]["actual"] += actual
        type_map[ct]["variance"] += var
        type_map[ct]["count"] += 1
        if abs(var) > Decimal("0.01"):
            lines.append(item)
    summary = []
    for ct, vals in type_map.items():
        summary.append({
            "cost_type": ct,
            "cost_type_label": COST_TYPE_LABELS.get(ct, ct),
            "standard_cost": vals["standard"],
            "actual_cost": vals["actual"],
            "variance_amount": vals["variance"],
            "variance_pct": (vals["variance"] / vals["standard"] * 100) if vals["standard"] else Decimal("0"),
            "line_count": vals["count"],
        })
    summary.sort(key=lambda x: abs(x["variance_amount"]), reverse=True)
    return {
        "summary": summary,
        "lines": lines,
        "total_standard": total_std,
        "total_actual": total_actual,
        "total_variance": total_var,
    }
