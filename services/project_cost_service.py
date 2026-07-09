# -*- coding: utf-8 -*-
"""
项目成本服务
实现项目成本归集、毛利计算和成本报表

核心功能：
1. 记录项目成本
2. 计算项目总成本
3. 计算项目毛利和毛利率
4. 项目成本明细查询
5. 项目成本汇总查询
6. 项目毛利分析

作者: AI Assistant
日期: 2026-06-16
"""

from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional


PROJECT_COST_AMOUNT_SQL = "(COALESCE(debit_amount, 0) - COALESCE(credit_amount, 0))"
PROJECT_COST_AMOUNT_SQL_PCL = "(COALESCE(pcl.debit_amount, 0) - COALESCE(pcl.credit_amount, 0))"


def _escape_like_wildcards_for_psycopg2(sql: str) -> str:
    placeholder = "__PSYCOPG2_PARAM_PLACEHOLDER__"
    return sql.replace("%s", placeholder).replace("%", "%%").replace(placeholder, "%s")


def record_project_cost(
    query_db,
    execute_db,
    cost_data: Dict
) -> Dict:
    """
    记录项目成本

    Args:
        cost_data: {
            'project_code': 项目号,
            'project_name': 项目名称（可选）,
            'cost_date': 成本日期,
            'cost_type': 成本类型（材料成本、人工成本、委外成本等）,
            'source_type': 来源类型,
            'source_no': 来源单号,
            'description': 描述,
            'cost_amount': 成本金额,
            'quantity': 数量（可选）,
            'unit_cost': 单位成本（可选）,
            'department_id': 部门ID（可选）,
            'employee_id': 员工ID（可选）,
            'recorded_by': 记录人,
            'remark': 备注（可选）
        }

    Returns:
        {
            'success': True/False,
            'message': 消息,
            'cost_id': 成本记录ID
        }
    """
    try:
        result = execute_db(
            """
            INSERT INTO project_cost_ledger (
                project_code,
                project_name,
                cost_date,
                cost_type,
                source_type,
                source_no,
                description,
                cost_amount,
                quantity,
                unit_cost,
                department_id,
                employee_id,
                recorded_by,
                remark
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                cost_data['project_code'],
                cost_data.get('project_name'),
                cost_data.get('cost_date', datetime.now().date()),
                cost_data['cost_type'],
                cost_data.get('source_type'),
                cost_data.get('source_no'),
                cost_data.get('description'),
                Decimal(str(cost_data['cost_amount'] or 0)),
                Decimal(str(cost_data['quantity'])) if cost_data.get('quantity') is not None else None,
                Decimal(str(cost_data['unit_cost'])) if cost_data.get('unit_cost') is not None else None,
                cost_data.get('department_id'),
                cost_data.get('employee_id'),
                cost_data['recorded_by'],
                cost_data.get('remark')
            )
        )

        if isinstance(result, list) and result:
            cost_id = result[0].get('id') if isinstance(result[0], dict) else result[0]
        elif isinstance(result, dict):
            cost_id = result.get('id')
        elif isinstance(result, int):
            cost_id = result
        else:
            row = query_db(
                "SELECT id FROM project_cost_ledger WHERE project_code=%s AND source_no=%s ORDER BY id DESC LIMIT 1",
                (cost_data['project_code'], cost_data.get('source_no')),
                one=True,
            )
            cost_id = row.get('id') if row else None

        return {
            'success': True,
            'message': '项目成本记录成功',
            'cost_id': cost_id
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'项目成本记录失败: {str(e)}'
        }


def record_project_revenue(
    query_db,
    execute_db,
    revenue_data: Dict
) -> Dict:
    """
    记录项目收入

    Args:
        revenue_data: {
            'project_code': 项目号,
            'revenue_date': 收入日期,
            'revenue_type': 收入类型,
            'source_type': 来源类型,
            'source_no': 来源单号,
            'customer_id': 客户ID（可选）,
            'revenue_amount': 收入金额,
            'cost_amount': 对应成本（可选）,
            'recorded_by': 记录人,
            'remark': 备注（可选）
        }

    Returns:
        {
            'success': True/False,
            'message': 消息,
            'revenue_id': 收入记录ID
        }
    """
    try:
        revenue_amount = Decimal(str(revenue_data.get('revenue_amount') or 0))
        cost_amount = Decimal(str(revenue_data.get('cost_amount') or 0))
        gross_profit = revenue_amount - cost_amount
        gross_margin = (gross_profit / revenue_amount * 100) if revenue_amount > 0 else Decimal('0')

        result = execute_db(
            """
            INSERT INTO project_revenue_ledger (
                project_code,
                revenue_date,
                revenue_type,
                source_type,
                source_no,
                customer_id,
                revenue_amount,
                cost_amount,
                gross_profit,
                gross_margin,
                recorded_by,
                remark
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                revenue_data['project_code'],
                revenue_data.get('revenue_date', datetime.now().date()),
                revenue_data.get('revenue_type'),
                revenue_data.get('source_type'),
                revenue_data.get('source_no'),
                revenue_data.get('customer_id'),
                float(revenue_amount),
                float(cost_amount),
                float(gross_profit),
                float(gross_margin),
                revenue_data['recorded_by'],
                revenue_data.get('remark')
            )
        )

        if isinstance(result, list) and result:
            revenue_id = result[0].get('id') if isinstance(result[0], dict) else result[0]
        elif isinstance(result, dict):
            revenue_id = result.get('id')
        elif isinstance(result, int):
            revenue_id = result
        else:
            row = query_db(
                "SELECT id FROM project_revenue_ledger WHERE project_code=%s AND source_no=%s ORDER BY id DESC LIMIT 1",
                (revenue_data['project_code'], revenue_data.get('source_no')),
                one=True,
            )
            revenue_id = row.get('id') if row else None

        return {
            'success': True,
            'message': '项目收入记录成功',
            'revenue_id': revenue_id
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'项目收入记录失败: {str(e)}'
        }


def calculate_project_total_cost(
    query_db,
    project_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    计算项目总成本

    Args:
        query_db: 数据库查询函数
        project_code: 项目号
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）

    Returns:
        {
            'material_cost': 材料成本,
            'labor_cost': 人工成本,
            'outsource_cost': 委外成本,
            'transport_cost': 运输费用,
            'other_cost': 其他费用,
            'total_cost': 总成本,
            'cost_details': [按类型分组的明细]
        }
    """
    where_clauses = ["project_code = %s"]
    params = [project_code]

    if start_date:
        where_clauses.append("cost_date >= %s")
        params.append(start_date)

    if end_date:
        where_clauses.append("cost_date <= %s")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses)

    # 按成本类型汇总
    cost_by_type = query_db(
        f"""
        SELECT
            cost_type,
            SUM({PROJECT_COST_AMOUNT_SQL}) AS total_amount,
            COUNT(*) AS record_count
        FROM (
            SELECT *, {PROJECT_COST_AMOUNT_SQL} AS cost_amount
            FROM project_cost_ledger
        ) project_cost_ledger
        WHERE {where_sql}
        GROUP BY cost_type
        ORDER BY total_amount DESC
        """,
        tuple(params)
    )

    # 计算各类成本
    material_cost = Decimal('0')
    labor_cost = Decimal('0')
    outsource_cost = Decimal('0')
    transport_cost = Decimal('0')
    other_cost = Decimal('0')

    for item in cost_by_type:
        amount = Decimal(str(item.get('total_amount') or 0))
        cost_type = item.get('cost_type') or ''

        if '材料' in cost_type:
            material_cost += amount
        elif '人工' in cost_type:
            labor_cost += amount
        elif '委外' in cost_type:
            outsource_cost += amount
        elif '运输' in cost_type or '物流' in cost_type:
            transport_cost += amount
        else:
            other_cost += amount

    total_cost = material_cost + labor_cost + outsource_cost + transport_cost + other_cost

    return {
        'material_cost': material_cost,
        'labor_cost': labor_cost,
        'outsource_cost': outsource_cost,
        'transport_cost': transport_cost,
        'other_cost': other_cost,
        'total_cost': total_cost,
        'cost_details': cost_by_type
    }


def calculate_project_gross_profit(
    query_db,
    project_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    计算项目毛利

    Args:
        query_db: 数据库查询函数
        project_code: 项目号
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）

    Returns:
        {
            'revenue': 收入,
            'cost': 成本,
            'gross_profit': 毛利,
            'gross_margin': 毛利率（%）
        }
    """
    where_clauses = ["project_code = %s"]
    params = [project_code]

    if start_date:
        where_clauses.append("revenue_date >= %s")
        params.append(start_date)

    if end_date:
        where_clauses.append("revenue_date <= %s")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses)

    # 查询收入
    revenue_result = query_db(
        f"""
        SELECT
            COALESCE(SUM(revenue_amount), 0) AS total_revenue
        FROM project_revenue_ledger
        WHERE {where_sql}
        """,
        tuple(params),
        one=True
    )

    revenue = Decimal(str((revenue_result or {}).get('total_revenue') or 0))

    # 查询成本
    cost_result = calculate_project_total_cost(query_db, project_code, start_date, end_date)
    cost = cost_result['total_cost']

    # 计算毛利
    gross_profit = revenue - cost
    gross_margin = (gross_profit / revenue * 100) if revenue > 0 else Decimal('0')

    return {
        'revenue': revenue,
        'cost': cost,
        'gross_profit': gross_profit,
        'gross_margin': gross_margin
    }


def query_project_cost_detail(
    query_db,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    查询项目成本明细

    Args:
        filters: {
            'project_code': 项目号,
            'start_date': 开始日期,
            'end_date': 结束日期,
            'cost_type': 成本类型,
            'source_type': 来源类型
        }

    Returns:
        项目成本明细列表
    """
    filters = filters or {}

    where_clauses = ["1=1"]
    params = []

    if filters.get('project_code'):
        where_clauses.append("pcl.project_code = %s")
        params.append(filters['project_code'])

    if filters.get('start_date'):
        where_clauses.append("pcl.cost_date >= %s")
        params.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses.append("pcl.cost_date <= %s")
        params.append(filters['end_date'])

    if filters.get('cost_type'):
        where_clauses.append("pcl.cost_type = %s")
        params.append(filters['cost_type'])

    if filters.get('source_type'):
        where_clauses.append("pcl.source_type = %s")
        params.append(filters['source_type'])

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    SELECT
        pcl.*,
        {PROJECT_COST_AMOUNT_SQL_PCL} AS cost_amount,
        u.username AS recorded_by_name
    FROM project_cost_ledger pcl
    LEFT JOIN users u ON pcl.created_by = u.id
    WHERE {where_sql}
    ORDER BY pcl.cost_date DESC, pcl.id DESC
    """

    sql = _escape_like_wildcards_for_psycopg2(sql)
    return query_db(sql, tuple(params) if params else None)


def query_project_cost_summary(
    query_db,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    查询项目成本汇总

    Args:
        filters: {
            'start_date': 开始日期,
            'end_date': 结束日期,
            'project_codes': 项目号列表（可选）
        }

    Returns:
        项目成本汇总列表
    """
    filters = filters or {}

    where_clauses = ["1=1"]
    params = []

    if filters.get('start_date'):
        where_clauses.append("cost_date >= %s")
        params.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses.append("cost_date <= %s")
        params.append(filters['end_date'])

    if filters.get('project_codes'):
        placeholders = ','.join(['%s'] * len(filters['project_codes']))
        where_clauses.append(f"project_code IN ({placeholders})")
        params.extend(filters['project_codes'])

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    SELECT
        project_code,
        MAX(project_name) AS project_name,
        SUM(CASE WHEN cost_type LIKE '%材料%' THEN normalized_cost_amount ELSE 0 END) AS material_cost,
        SUM(CASE WHEN cost_type LIKE '%人工%' THEN normalized_cost_amount ELSE 0 END) AS labor_cost,
        SUM(CASE WHEN cost_type LIKE '%委外%' THEN normalized_cost_amount ELSE 0 END) AS outsource_cost,
        SUM(CASE WHEN cost_type LIKE '%运输%' OR cost_type LIKE '%物流%' THEN normalized_cost_amount ELSE 0 END) AS transport_cost,
        SUM(CASE WHEN cost_type NOT LIKE '%材料%' AND cost_type NOT LIKE '%人工%'
                 AND cost_type NOT LIKE '%委外%' AND cost_type NOT LIKE '%运输%'
                 AND cost_type NOT LIKE '%物流%' THEN normalized_cost_amount ELSE 0 END) AS other_cost,
        SUM(normalized_cost_amount) AS total_cost,
        COUNT(*) AS cost_records
    FROM (
        SELECT *, {PROJECT_COST_AMOUNT_SQL} AS normalized_cost_amount
        FROM project_cost_ledger
    ) project_cost_ledger
    WHERE {where_sql}
    GROUP BY project_code
    ORDER BY total_cost DESC
    """

    sql = _escape_like_wildcards_for_psycopg2(sql)
    return query_db(sql, tuple(params))


def query_project_gross_profit_analysis(
    query_db,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    查询项目毛利分析

    Args:
        filters: {
            'start_date': 开始日期,
            'end_date': 结束日期,
            'project_codes': 项目号列表（可选）
        }

    Returns:
        项目毛利分析列表
    """
    filters = filters or {}

    where_clauses_cost = ["1=1"]
    where_clauses_revenue = ["1=1"]
    params_cost = []
    params_revenue = []

    if filters.get('start_date'):
        where_clauses_cost.append("cost_date >= %s")
        params_cost.append(filters['start_date'])
        where_clauses_revenue.append("invoice_date >= %s")
        params_revenue.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses_cost.append("cost_date <= %s")
        params_cost.append(filters['end_date'])
        where_clauses_revenue.append("invoice_date <= %s")
        params_revenue.append(filters['end_date'])

    if filters.get('project_codes'):
        placeholders = ','.join(['%s'] * len(filters['project_codes']))
        where_clauses_cost.append(f"project_code IN ({placeholders})")
        params_cost.extend(filters['project_codes'])
        where_clauses_revenue.append(f"project_code IN ({placeholders})")
        params_revenue.extend(filters['project_codes'])

    where_sql_cost = " AND ".join(where_clauses_cost)
    where_sql_revenue = " AND ".join(where_clauses_revenue)

    sql = f"""
    WITH project_costs AS (
        SELECT
            project_code,
            MAX(project_name) AS project_name,
            SUM(normalized_cost_amount) AS total_cost
        FROM (
            SELECT *, {PROJECT_COST_AMOUNT_SQL} AS normalized_cost_amount
            FROM project_cost_ledger
        ) project_cost_ledger
        WHERE {where_sql_cost}
        GROUP BY project_code
    ),
    project_revenues AS (
        SELECT
            project_code,
            SUM(COALESCE(amount_with_tax, total_amount, 0)) AS total_revenue
        FROM sales_invoices
        WHERE {where_sql_revenue}
        GROUP BY project_code
    )
    SELECT
        COALESCE(pc.project_code, pr.project_code) AS project_code,
        pc.project_name,
        COALESCE(pr.total_revenue, 0) AS revenue,
        COALESCE(pc.total_cost, 0) AS cost,
        COALESCE(pr.total_revenue, 0) - COALESCE(pc.total_cost, 0) AS gross_profit,
        CASE
            WHEN COALESCE(pr.total_revenue, 0) > 0 THEN
                (COALESCE(pr.total_revenue, 0) - COALESCE(pc.total_cost, 0)) / pr.total_revenue * 100
            ELSE 0
        END AS gross_margin
    FROM project_costs pc
    FULL OUTER JOIN project_revenues pr ON pc.project_code = pr.project_code
    ORDER BY gross_profit DESC
    """

    all_params = params_cost + params_revenue
    return query_db(sql, tuple(all_params))


def get_project_cost_types(query_db) -> List[str]:
    """
    获取所有成本类型

    Returns:
        成本类型列表
    """
    result = query_db(
        """
        SELECT DISTINCT cost_type
        FROM project_cost_ledger
        WHERE cost_type IS NOT NULL
        ORDER BY cost_type
        """
    )

    return [item['cost_type'] for item in result]
