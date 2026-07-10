# -*- coding: utf-8 -*-
"""
成本对账服务 (P0-3)

实现业务成本与库存成本、业务成本与总账成本之间的对账。
所有金额均使用 Decimal 处理；DDL 已在 services/schema_migrations.py
的 20260621_004_p0_cost_engine 迁移中定义。

核心功能：
1. 业务成本 vs 库存成本对账（cost_runs vs inventory_balances 估值）
2. 业务成本 vs 总账成本对账（cost_runs vs gl_account_balances / general_ledger）
3. 对账结果保存到 cost_reconciliation_results
4. 对账结果列表查询
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _decimal(value: Any) -> Decimal:
    try:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _optional_columns(query_one, table_name: str) -> set:
    """通过 information_schema 检查表是否存在某些列。"""
    rows_query = query_one(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    ) or {}
    if not rows_query or int(rows_query.get("cnt") or 0) == 0:
        return set()
    # 由于 query_one 只能取一行，这里改为查询单列聚合
    # 实际列检查通过 _has_column 完成
    return {"__exists__"}


def _has_column(query_one, table_name: str, column: str) -> bool:
    row = query_one(
        """
        SELECT 1 AS found
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table_name, column),
    )
    return bool(row)


def _table_exists(query_one, table_name: str) -> bool:
    row = query_one(
        """
        SELECT 1 AS found
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        LIMIT 1
        """,
        (table_name,),
    )
    return bool(row)


# ---------------------------------------------------------------------------
# 业务成本 vs 库存成本
# ---------------------------------------------------------------------------
def reconcile_business_vs_inventory(
    query_one,
    *,
    period: Optional[str] = None,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
) -> Dict:
    """对比业务成本（来自 cost_runs）与库存成本（来自 inventory_balances 估值）。

    业务成本：从 cost_runs 汇总 total_cost（按 project_code/cabinet_no 过滤）
    库存成本：从 inventory_balances 汇总 quantity * unit_cost
              （若表存在且能按 project_code/cabinet_no 过滤则过滤，否则全量）
    """
    # 1. 业务成本
    business_cost = Decimal("0")
    if _table_exists(query_one, "cost_runs"):
        clauses: List[str] = ["status='completed'"]
        params: List[Any] = []
        if period:
            clauses.append("period=%s")
            params.append(period)
        if project_code:
            clauses.append("COALESCE(project_code, '')=%s")
            params.append(project_code)
        if cabinet_no:
            clauses.append("COALESCE(cabinet_no, '')=%s")
            params.append(cabinet_no)
        where_sql = " AND ".join(clauses)
        row = query_one(
            f"""
            SELECT COALESCE(SUM(total_cost), 0) AS total
            FROM cost_runs
            WHERE {where_sql}
            """,
            tuple(params),
        ) or {}
        business_cost = _decimal(row.get("total"))

    # 2. 库存成本
    inventory_cost = Decimal("0")
    inventory_details: List[Dict] = []
    if _table_exists(query_one, "inventory_balances"):
        # 检查 inventory_balances 是否有 project_code/cabinet_no 列
        has_proj = _has_column(query_one, "inventory_balances", "project_code")
        has_cabinet = _has_column(query_one, "inventory_balances", "cabinet_no")
        clauses = ["COALESCE(quantity, 0) <> 0"]
        params = []
        if project_code and has_proj:
            clauses.append("COALESCE(project_code, '')=%s")
            params.append(project_code)
        if cabinet_no and has_cabinet:
            clauses.append("COALESCE(cabinet_no, '')=%s")
            params.append(cabinet_no)
        where_sql = " AND ".join(clauses)
        row = query_one(
            f"""
            SELECT COALESCE(SUM(COALESCE(quantity, 0) * COALESCE(unit_cost, 0)), 0) AS total
            FROM inventory_balances
            WHERE {where_sql}
            """,
            tuple(params),
        ) or {}
        inventory_cost = _decimal(row.get("total"))

    difference = business_cost - inventory_cost
    is_balanced = abs(difference) < Decimal("0.01")

    return {
        "reconciliation_type": "business_vs_inventory",
        "period": period,
        "project_code": project_code,
        "cabinet_no": cabinet_no,
        "business_cost": business_cost,
        "inventory_cost": inventory_cost,
        "gl_cost": Decimal("0"),
        "difference": difference,
        "is_balanced": is_balanced,
        "status": "balanced" if is_balanced else "unbalanced",
        "remark": (
            "业务成本来自 cost_runs.total_cost 汇总；"
            "库存成本来自 inventory_balances.quantity * unit_cost 汇总。"
        ),
    }


# ---------------------------------------------------------------------------
# 业务成本 vs 总账成本
# ---------------------------------------------------------------------------
def reconcile_business_vs_gl(
    query_one,
    *,
    period: Optional[str] = None,
    project_code: Optional[str] = None,
    cabinet_no: Optional[str] = None,
) -> Dict:
    """对比业务成本（来自 cost_runs）与总账成本（来自 gl_account_balances / general_ledger）。

    总账成本：优先使用 gl_account_balances（按期间过滤存货类科目 1405/1406），
             若不可用则回退到 general_ledger。
    """
    # 1. 业务成本
    business_cost = Decimal("0")
    if _table_exists(query_one, "cost_runs"):
        clauses: List[str] = ["status='completed'"]
        params: List[Any] = []
        if period:
            clauses.append("period=%s")
            params.append(period)
        if project_code:
            clauses.append("COALESCE(project_code, '')=%s")
            params.append(project_code)
        if cabinet_no:
            clauses.append("COALESCE(cabinet_no, '')=%s")
            params.append(cabinet_no)
        where_sql = " AND ".join(clauses)
        row = query_one(
            f"""
            SELECT COALESCE(SUM(total_cost), 0) AS total
            FROM cost_runs
            WHERE {where_sql}
            """,
            tuple(params),
        ) or {}
        business_cost = _decimal(row.get("total"))

    # 2. 总账成本
    gl_cost = Decimal("0")
    gl_source = ""

    # 优先 gl_account_balances
    if _table_exists(query_one, "gl_account_balances") and _table_exists(query_one, "chart_of_accounts"):
        clauses = ["coa.account_code IN ('1405', '1406')"]
        params: List[Any] = []
        if period:
            # period 格式 YYYY-MM 或 YYYYMM
            period_str = str(period).replace("-", "")
            if len(period_str) >= 6:
                try:
                    year = int(period_str[:4])
                    month = int(period_str[4:6])
                    clauses.append("gab.period_year=%s")
                    params.append(year)
                    clauses.append("gab.period_month=%s")
                    params.append(month)
                except Exception:
                    pass
        where_sql = " AND ".join(clauses)
        row = query_one(
            f"""
            SELECT COALESCE(SUM(gab.debit_amount - gab.credit_amount), 0) AS total
            FROM gl_account_balances gab
            JOIN chart_of_accounts coa ON coa.id=gab.account_id
            WHERE {where_sql}
            """,
            tuple(params),
        ) or {}
        gl_cost = _decimal(row.get("total"))
        gl_source = "gl_account_balances"

    # 回退到 general_ledger
    if gl_source == "" and _table_exists(query_one, "general_ledger"):
        clauses = ["account_code IN ('1405', '1406')"]
        params = []
        if period:
            clauses.append("COALESCE(period, '')=%s")
            params.append(period)
        if _has_column(query_one, "general_ledger", "status"):
            clauses.append("COALESCE(status, 'active')='active'")
        where_sql = " AND ".join(clauses)
        row = query_one(
            f"""
            SELECT COALESCE(SUM(debit_amount - credit_amount), 0) AS total
            FROM general_ledger
            WHERE {where_sql}
            """,
            tuple(params),
        ) or {}
        gl_cost = _decimal(row.get("total"))
        gl_source = "general_ledger"

    difference = business_cost - gl_cost
    is_balanced = abs(difference) < Decimal("0.01")

    return {
        "reconciliation_type": "business_vs_gl",
        "period": period,
        "project_code": project_code,
        "cabinet_no": cabinet_no,
        "business_cost": business_cost,
        "inventory_cost": Decimal("0"),
        "gl_cost": gl_cost,
        "gl_source": gl_source,
        "difference": difference,
        "is_balanced": is_balanced,
        "status": "balanced" if is_balanced else "unbalanced",
        "remark": (
            f"业务成本来自 cost_runs.total_cost 汇总；"
            f"总账成本来自 {gl_source or '（无可用总账表）'} 存货科目 1405/1406 余额。"
        ),
    }


# ---------------------------------------------------------------------------
# 保存对账结果
# ---------------------------------------------------------------------------
def save_reconciliation_result(query_db, execute_db, result: Dict) -> Dict:
    """将对账结果保存到 cost_reconciliation_results 表。

    Args:
        query_db: 用于检查表是否存在
        execute_db: 用于 INSERT
        result: 来自 reconcile_business_vs_inventory / reconcile_business_vs_gl 的结果

    Returns:
        {"success": True/False, "id": ..., "message": ...}
    """
    try:
        execute_db(
            """
            INSERT INTO cost_reconciliation_results
                (period, project_code, cabinet_no,
                 business_cost, inventory_cost, gl_cost,
                 difference, status, remark, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """,
            (
                result.get("period"),
                result.get("project_code"),
                result.get("cabinet_no"),
                result.get("business_cost", Decimal("0")),
                result.get("inventory_cost", Decimal("0")),
                result.get("gl_cost", Decimal("0")),
                result.get("difference", Decimal("0")),
                result.get("status", "open"),
                result.get("remark", ""),
            ),
        )
        return {
            "success": True,
            "message": "对账结果已保存",
        }
    except Exception as exc:
        logger.exception("对账结果保存失败")
        return {
            "success": False,
            "message": f"对账结果保存失败: {exc}",
        }


# ---------------------------------------------------------------------------
# 对账结果列表
# ---------------------------------------------------------------------------
def list_reconciliation_results(query_rows, filters: Optional[Dict] = None) -> List[Dict]:
    """列出对账结果。"""
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
    where_sql = " AND ".join(clauses)
    rows = query_rows(
        f"""
        SELECT id, period, project_code, cabinet_no,
               business_cost, inventory_cost, gl_cost,
               difference, status, remark, created_at
        FROM cost_reconciliation_results
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT 200
        """,
        tuple(params),
    )
    return rows or []
