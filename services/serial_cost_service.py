# -*- coding: utf-8 -*-
"""
机号成本服务
实现机号成本归集、标准成本对比和成本差异分析

核心功能：
1. 记录机号成本
2. 计算机号总成本
3. 计算BOM标准成本
4. 计算成本差异
5. 机号成本明细查询
6. 机号成本汇总查询
7. 机号成本差异分析

作者: AI Assistant
日期: 2026-06-16
"""

from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional


SERIAL_COST_AMOUNT_SQL = "(COALESCE(debit_amount, 0) - COALESCE(credit_amount, 0))"
SERIAL_COST_AMOUNT_SQL_SCL = "(COALESCE(scl.debit_amount, 0) - COALESCE(scl.credit_amount, 0))"


def _escape_like_wildcards_for_psycopg2(sql: str) -> str:
    placeholder = "__PSYCOPG2_PARAM_PLACEHOLDER__"
    return sql.replace("%s", placeholder).replace("%", "%%").replace(placeholder, "%s")


def record_serial_cost(
    query_db,
    execute_db,
    cost_data: Dict
) -> Dict:
    """
    记录机号成本

    Args:
        cost_data: {
            'serial_no': 机号,
            'product_id': 产品ID（可选）,
            'project_code': 项目号（可选）,
            'cost_date': 成本日期,
            'cost_type': 成本类型（领料成本、采购成本、委外成本等）,
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
            INSERT INTO serial_cost_ledger (
                serial_no,
                product_id,
                project_code,
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
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                cost_data['serial_no'],
                cost_data.get('product_id'),
                cost_data.get('project_code'),
                cost_data.get('cost_date', datetime.now().date()),
                cost_data['cost_type'],
                cost_data.get('source_type'),
                cost_data.get('source_no'),
                cost_data.get('description'),
                float(cost_data['cost_amount']),
                float(cost_data['quantity']) if cost_data.get('quantity') is not None else None,
                float(cost_data['unit_cost']) if cost_data.get('unit_cost') is not None else None,
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
                "SELECT id FROM serial_cost_ledger WHERE serial_no=%s AND source_no=%s ORDER BY id DESC LIMIT 1",
                (cost_data['serial_no'], cost_data.get('source_no')),
                one=True,
            )
            cost_id = row.get('id') if row else None

        return {
            'success': True,
            'message': '机号成本记录成功',
            'cost_id': cost_id
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'机号成本记录失败: {str(e)}'
        }


def calculate_serial_total_cost(
    query_db,
    serial_no: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    计算机号总成本

    Args:
        query_db: 数据库查询函数
        serial_no: 机号
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）

    Returns:
        {
            'material_cost': 领料成本,
            'purchase_cost': 采购成本,
            'outsource_cost': 委外成本,
            'labor_cost': 人工成本,
            'other_cost': 其他成本,
            'total_cost': 总成本,
            'cost_details': [按类型分组的明细]
        }
    """
    where_clauses = ["serial_no = %s"]
    params = [serial_no]

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
            SUM({SERIAL_COST_AMOUNT_SQL}) AS total_amount,
            COUNT(*) AS record_count
        FROM (
            SELECT *, {SERIAL_COST_AMOUNT_SQL} AS cost_amount
            FROM serial_cost_ledger
        ) serial_cost_ledger
        WHERE {where_sql}
        GROUP BY cost_type
        ORDER BY total_amount DESC
        """,
        tuple(params)
    )

    # 计算各类成本
    material_cost = Decimal('0')
    purchase_cost = Decimal('0')
    outsource_cost = Decimal('0')
    labor_cost = Decimal('0')
    other_cost = Decimal('0')

    for item in cost_by_type:
        amount = Decimal(str(item.get('total_amount') or 0))
        cost_type = item.get('cost_type') or ''

        if '领料' in cost_type or '材料' in cost_type:
            material_cost += amount
        elif '采购' in cost_type:
            purchase_cost += amount
        elif '委外' in cost_type:
            outsource_cost += amount
        elif '人工' in cost_type or '装配' in cost_type:
            labor_cost += amount
        else:
            other_cost += amount

    total_cost = material_cost + purchase_cost + outsource_cost + labor_cost + other_cost

    return {
        'material_cost': material_cost,
        'purchase_cost': purchase_cost,
        'outsource_cost': outsource_cost,
        'labor_cost': labor_cost,
        'other_cost': other_cost,
        'total_cost': total_cost,
        'cost_details': cost_by_type
    }


def calculate_bom_standard_cost(
    query_db,
    serial_no: str
) -> Dict:
    """
    计算BOM标准成本

    根据BOM清单计算标准成本

    Args:
        query_db: 数据库查询函数
        serial_no: 机号

    Returns:
        {
            'success': True/False,
            'message': 消息,
            'standard_cost': 标准成本,
            'bom_items': [BOM明细]
        }
    """
    try:
        # 查询机号对应的产品：优先从 serial_cost_ledger，回退到 work_orders
        serial_product = query_db(
            """
            SELECT product_id
            FROM serial_cost_ledger
            WHERE serial_no = %s AND product_id IS NOT NULL
            LIMIT 1
            """,
            (serial_no,),
            one=True
        )

        product_id = serial_product.get('product_id') if serial_product else None

        if not product_id:
            # 回退：从 work_orders 查找该机号对应的产品
            wo_product = query_db(
                """
                SELECT product_id
                FROM work_orders
                WHERE serial_no = %s AND product_id IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (serial_no,),
                one=True
            )
            if wo_product:
                product_id = wo_product.get('product_id')

        if not product_id:
            return {
                'success': False,
                'message': '无法找到机号对应的产品',
                'standard_cost': Decimal('0'),
                'bom_items': []
            }

        # 解析产品对应的生产 BOM（与 MRP 引擎 _resolve_bom_id 逻辑一致）
        bom_row = query_db(
            """
            SELECT id FROM boms
            WHERE product_id = %s
              AND COALESCE(status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN bom_type='production' THEN 0 ELSE 1 END,
                id DESC
            LIMIT 1
            """,
            (product_id,),
            one=True
        )

        if not bom_row or not bom_row.get('id'):
            return {
                'success': False,
                'message': '无法找到产品对应的 BOM',
                'standard_cost': Decimal('0'),
                'bom_items': []
            }

        bom_id = bom_row['id']

        # 查询 BOM 明细
        # bom_items.product_id 是子物料编码，bom_id 链接到父 BOM
        # products.standard_price 是成本引擎统一使用的标准价字段
        bom_items = query_db(
            """
            SELECT
                bi.id,
                bi.product_id AS material_id,
                p.code AS material_code,
                p.name AS material_name,
                p.specification AS material_spec,
                bi.quantity AS required_quantity,
                COALESCE(p.standard_price, 0) AS unit_standard_cost,
                bi.quantity * COALESCE(p.standard_price, 0) AS line_standard_cost
            FROM bom_items bi
            JOIN products p ON bi.product_id = p.id
            WHERE bi.bom_id = %s
            ORDER BY bi.id
            """,
            (bom_id,)
        )

        # 计算标准成本
        standard_cost = sum(
            Decimal(str(item.get('line_standard_cost') or 0))
            for item in bom_items
        )

        return {
            'success': True,
            'message': 'BOM标准成本计算成功',
            'standard_cost': standard_cost,
            'bom_items': bom_items
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'BOM标准成本计算失败: {str(e)}',
            'standard_cost': Decimal('0'),
            'bom_items': []
        }


def calculate_cost_variance(
    query_db,
    serial_no: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    计算成本差异

    标准成本 vs 实际成本

    Args:
        query_db: 数据库查询函数
        serial_no: 机号
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）

    Returns:
        {
            'standard_cost': 标准成本,
            'actual_cost': 实际成本,
            'variance': 差异（实际-标准）,
            'variance_rate': 差异率（%）,
            'variance_type': 差异类型（超支/节约）
        }
    """
    # 计算实际成本
    actual_result = calculate_serial_total_cost(query_db, serial_no, start_date, end_date)
    actual_cost = actual_result['total_cost']

    # 计算标准成本
    standard_result = calculate_bom_standard_cost(query_db, serial_no)
    standard_cost = standard_result['standard_cost']

    # 计算差异
    variance = actual_cost - standard_cost

    # 计算差异率
    if standard_cost > 0:
        variance_rate = (variance / standard_cost * 100)
    else:
        variance_rate = Decimal('0')

    # 判断差异类型
    if variance > 0:
        variance_type = '超支'
    elif variance < 0:
        variance_type = '节约'
    else:
        variance_type = '无差异'

    return {
        'standard_cost': standard_cost,
        'actual_cost': actual_cost,
        'variance': variance,
        'variance_rate': variance_rate,
        'variance_type': variance_type
    }


def query_serial_cost_detail(
    query_db,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    查询机号成本明细

    Args:
        filters: {
            'serial_no': 机号,
            'project_code': 项目号,
            'start_date': 开始日期,
            'end_date': 结束日期,
            'cost_type': 成本类型,
            'source_type': 来源类型
        }

    Returns:
        机号成本明细列表
    """
    filters = filters or {}

    where_clauses = ["1=1"]
    params = []

    if filters.get('serial_no'):
        where_clauses.append("scl.serial_no = %s")
        params.append(filters['serial_no'])

    if filters.get('project_code'):
        where_clauses.append("scl.project_code = %s")
        params.append(filters['project_code'])

    if filters.get('start_date'):
        where_clauses.append("scl.cost_date >= %s")
        params.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses.append("scl.cost_date <= %s")
        params.append(filters['end_date'])

    if filters.get('cost_type'):
        where_clauses.append("scl.cost_type = %s")
        params.append(filters['cost_type'])

    if filters.get('source_type'):
        where_clauses.append("scl.source_type = %s")
        params.append(filters['source_type'])

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    SELECT
        scl.*,
        {SERIAL_COST_AMOUNT_SQL_SCL} AS cost_amount,
        p.code AS product_code,
        p.name AS product_name,
        u.username AS recorded_by_name
    FROM serial_cost_ledger scl
    LEFT JOIN products p ON scl.product_id = p.id
    LEFT JOIN users u ON scl.created_by = u.id
    WHERE {where_sql}
    ORDER BY scl.cost_date DESC, scl.id DESC
    """

    return query_db(sql, tuple(params))


def query_serial_cost_summary(
    query_db,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    查询机号成本汇总

    Args:
        filters: {
            'start_date': 开始日期,
            'end_date': 结束日期,
            'project_code': 项目号,
            'serial_nos': 机号列表（可选）
        }

    Returns:
        机号成本汇总列表
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

    if filters.get('project_code'):
        where_clauses.append("project_code = %s")
        params.append(filters['project_code'])

    if filters.get('serial_nos'):
        placeholders = ','.join(['%s'] * len(filters['serial_nos']))
        where_clauses.append(f"serial_no IN ({placeholders})")
        params.extend(filters['serial_nos'])

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    SELECT
        serial_no,
        MAX(project_code) AS project_code,
        MAX(product_id) AS product_id,
        SUM(CASE WHEN cost_type LIKE '%领料%' OR cost_type LIKE '%材料%' THEN normalized_cost_amount ELSE 0 END) AS material_cost,
        SUM(CASE WHEN cost_type LIKE '%采购%' THEN normalized_cost_amount ELSE 0 END) AS purchase_cost,
        SUM(CASE WHEN cost_type LIKE '%委外%' THEN normalized_cost_amount ELSE 0 END) AS outsource_cost,
        SUM(CASE WHEN cost_type LIKE '%人工%' OR cost_type LIKE '%装配%' THEN normalized_cost_amount ELSE 0 END) AS labor_cost,
        SUM(CASE WHEN cost_type NOT LIKE '%领料%' AND cost_type NOT LIKE '%材料%'
                 AND cost_type NOT LIKE '%采购%' AND cost_type NOT LIKE '%委外%'
                 AND cost_type NOT LIKE '%人工%' AND cost_type NOT LIKE '%装配%'
                 THEN normalized_cost_amount ELSE 0 END) AS other_cost,
        SUM(normalized_cost_amount) AS total_cost,
        COUNT(*) AS cost_records
    FROM (
        SELECT *, {SERIAL_COST_AMOUNT_SQL} AS normalized_cost_amount
        FROM serial_cost_ledger
    ) serial_cost_ledger
    WHERE {where_sql}
    GROUP BY serial_no
    ORDER BY total_cost DESC
    """

    sql = _escape_like_wildcards_for_psycopg2(sql)
    return query_db(sql, tuple(params))


def query_serial_cost_variance(
    query_db,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    查询机号成本差异

    Args:
        filters: {
            'start_date': 开始日期,
            'end_date': 结束日期,
            'project_code': 项目号,
            'serial_nos': 机号列表（可选）
        }

    Returns:
        机号成本差异列表
    """
    filters = filters or {}

    # 获取机号汇总成本
    summary_list = query_serial_cost_summary(query_db, filters)

    # 计算每个机号的差异
    variance_list = []

    for summary in summary_list:
        serial_no = summary['serial_no']
        actual_cost = Decimal(str(summary.get('total_cost') or 0))

        # 计算标准成本
        standard_result = calculate_bom_standard_cost(query_db, serial_no)
        standard_cost = standard_result['standard_cost']

        # 计算差异
        variance = actual_cost - standard_cost
        variance_rate = (variance / standard_cost * 100) if standard_cost > 0 else Decimal('0')

        if variance > 0:
            variance_type = '超支'
        elif variance < 0:
            variance_type = '节约'
        else:
            variance_type = '无差异'

        variance_list.append({
            'serial_no': serial_no,
            'project_code': summary.get('project_code'),
            'standard_cost': standard_cost,
            'actual_cost': actual_cost,
            'material_cost': Decimal(str(summary.get('material_cost') or 0)),
            'purchase_cost': Decimal(str(summary.get('purchase_cost') or 0)),
            'outsource_cost': Decimal(str(summary.get('outsource_cost') or 0)),
            'labor_cost': Decimal(str(summary.get('labor_cost') or 0)),
            'other_cost': Decimal(str(summary.get('other_cost') or 0)),
            'variance': variance,
            'variance_rate': variance_rate,
            'variance_type': variance_type
        })

    # 按差异金额降序排序
    variance_list.sort(key=lambda x: abs(x['variance']), reverse=True)

    return variance_list


def get_serial_cost_types(query_db) -> List[str]:
    """
    获取所有机号成本类型

    Returns:
        成本类型列表
    """
    result = query_db(
        """
        SELECT DISTINCT cost_type
        FROM serial_cost_ledger
        WHERE cost_type IS NOT NULL
        ORDER BY cost_type
        """
    )

    return [item['cost_type'] for item in result]
