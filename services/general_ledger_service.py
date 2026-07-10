# -*- coding: utf-8 -*-
"""
总账报表服务
提供科目余额表、明细账、总账等报表查询
"""
from decimal import Decimal


def query_account_balance(query_db, filters=None):
    """
    科目余额表查询

    Args:
        query_db: 数据库查询函数
        filters: 筛选条件
            - period_year: 年份
            - period_month: 月份
            - account_type: 科目类型
            - account_code: 科目代码（模糊匹配）

    Returns:
        list: 科目余额列表
    """
    filters = filters or {}
    where_clauses = ["coa.status = 'active'"]
    params = []

    # 期间筛选（必须）
    if not filters.get('period_year') or not filters.get('period_month'):
        return []

    period_year = int(filters['period_year'])
    period_month = int(filters['period_month'])

    # 科目类型筛选
    if filters.get('account_type'):
        where_clauses.append("coa.account_type = %s")
        params.append(filters['account_type'])

    # 科目代码筛选
    if filters.get('account_code'):
        where_clauses.append("coa.code LIKE %s")
        params.append(f"{filters['account_code']}%")

    where_sql = " AND ".join(where_clauses)

    # 计算期初余额、本期发生额、期末余额
    sql = f"""
    WITH opening_balance AS (
        -- 期初余额 = 上期期末余额
        SELECT
            account_id,
            SUM(debit_amount) - SUM(credit_amount) AS opening_debit,
            CASE
                WHEN SUM(debit_amount) - SUM(credit_amount) >= 0
                THEN SUM(debit_amount) - SUM(credit_amount)
                ELSE 0
            END AS opening_debit_balance,
            CASE
                WHEN SUM(debit_amount) - SUM(credit_amount) < 0
                THEN ABS(SUM(debit_amount) - SUM(credit_amount))
                ELSE 0
            END AS opening_credit_balance
        FROM general_ledger
        WHERE (period_year < %s OR (period_year = %s AND period_month < %s))
        GROUP BY account_id
    ),
    current_period AS (
        -- 本期发生额
        SELECT
            account_id,
            SUM(debit_amount) AS current_debit,
            SUM(credit_amount) AS current_credit
        FROM general_ledger
        WHERE period_year = %s AND period_month = %s
        GROUP BY account_id
    )
    SELECT
        coa.id,
        coa.code,
        coa.name,
        coa.account_type,
        coa.balance_direction,
        COALESCE(ob.opening_debit_balance, 0) AS opening_debit,
        COALESCE(ob.opening_credit_balance, 0) AS opening_credit,
        COALESCE(cp.current_debit, 0) AS current_debit,
        COALESCE(cp.current_credit, 0) AS current_credit,
        -- 期末余额计算
        CASE
            WHEN coa.balance_direction = '借方' THEN
                COALESCE(ob.opening_debit_balance, 0) + COALESCE(cp.current_debit, 0) - COALESCE(cp.current_credit, 0)
            ELSE
                COALESCE(ob.opening_credit_balance, 0) + COALESCE(cp.current_credit, 0) - COALESCE(cp.current_debit, 0)
        END AS ending_balance,
        -- 期末借方余额
        CASE
            WHEN (COALESCE(ob.opening_debit_balance, 0) - COALESCE(ob.opening_credit_balance, 0) +
                  COALESCE(cp.current_debit, 0) - COALESCE(cp.current_credit, 0)) >= 0
            THEN (COALESCE(ob.opening_debit_balance, 0) - COALESCE(ob.opening_credit_balance, 0) +
                  COALESCE(cp.current_debit, 0) - COALESCE(cp.current_credit, 0))
            ELSE 0
        END AS ending_debit,
        -- 期末贷方余额
        CASE
            WHEN (COALESCE(ob.opening_debit_balance, 0) - COALESCE(ob.opening_credit_balance, 0) +
                  COALESCE(cp.current_debit, 0) - COALESCE(cp.current_credit, 0)) < 0
            THEN ABS(COALESCE(ob.opening_debit_balance, 0) - COALESCE(ob.opening_credit_balance, 0) +
                     COALESCE(cp.current_debit, 0) - COALESCE(cp.current_credit, 0))
            ELSE 0
        END AS ending_credit
    FROM chart_of_accounts coa
    LEFT JOIN opening_balance ob ON coa.id = ob.account_id
    LEFT JOIN current_period cp ON coa.id = cp.account_id
    WHERE {where_sql}
      AND (ob.opening_debit_balance IS NOT NULL OR ob.opening_credit_balance IS NOT NULL
           OR cp.current_debit IS NOT NULL OR cp.current_credit IS NOT NULL)
    ORDER BY coa.code
    """

    params_tuple = (period_year, period_year, period_month,
                    period_year, period_month) + tuple(params)

    rows = query_db(sql, params_tuple)

    # 转换为字典列表
    result = []
    for row in rows:
        result.append({
            'account_id': row['id'],
            'account_code': row['code'],
            'account_name': row['name'],
            'account_type': row['account_type'],
            'balance_direction': row['balance_direction'],
            'opening_debit': float(row['opening_debit']) if row['opening_debit'] else 0,
            'opening_credit': float(row['opening_credit']) if row['opening_credit'] else 0,
            'current_debit': float(row['current_debit']) if row['current_debit'] else 0,
            'current_credit': float(row['current_credit']) if row['current_credit'] else 0,
            'ending_debit': float(row['ending_debit']) if row['ending_debit'] else 0,
            'ending_credit': float(row['ending_credit']) if row['ending_credit'] else 0,
            'ending_balance': float(row['ending_balance']) if row['ending_balance'] else 0
        })

    return result


def query_account_detail_ledger(query_db, filters=None):
    """
    科目明细账查询

    Args:
        query_db: 数据库查询函数
        filters: 筛选条件
            - account_id: 科目ID（必填）
            - start_date: 开始日期
            - end_date: 结束日期
            - project_code: 项目号
            - cabinet_no: 柜号

    Returns:
        list: 明细账列表
    """
    filters = filters or {}

    if not filters.get('account_id'):
        return []

    where_clauses = ["gl.account_id = %s"]
    params = [filters['account_id']]

    # 日期范围
    if filters.get('start_date'):
        where_clauses.append("gl.entry_date >= %s")
        params.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses.append("gl.entry_date <= %s")
        params.append(filters['end_date'])

    # 项目号
    if filters.get('project_code'):
        where_clauses.append("gl.project_code = %s")
        params.append(filters['project_code'])

    # 柜号
    if filters.get('cabinet_no'):
        where_clauses.append("gl.cabinet_no = %s")
        params.append(filters['cabinet_no'])

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    SELECT
        gl.id,
        gl.entry_date,
        gl.voucher_no,
        gl.summary,
        gl.debit_amount,
        gl.credit_amount,
        gl.project_code,
        gl.cabinet_no,
        v.voucher_type,
        v.status AS voucher_status
    FROM general_ledger gl
    JOIN vouchers v ON gl.voucher_id = v.id
    WHERE {where_sql}
    ORDER BY gl.entry_date, gl.voucher_no, gl.id
    """

    rows = query_db(sql, tuple(params))

    # 计算累计余额
    result = []
    balance = Decimal('0')

    for row in rows:
        debit = Decimal(str(row['debit_amount'])) if row['debit_amount'] else Decimal('0')
        credit = Decimal(str(row['credit_amount'])) if row['credit_amount'] else Decimal('0')
        balance += debit - credit

        result.append({
            'id': row['id'],
            'entry_date': row['entry_date'],
            'voucher_no': row['voucher_no'],
            'voucher_type': row['voucher_type'],
            'voucher_status': row['voucher_status'],
            'summary': row['summary'],
            'debit_amount': float(debit),
            'credit_amount': float(credit),
            'balance': float(balance),
            'project_code': row['project_code'],
            'cabinet_no': row['cabinet_no']
        })

    return result


def query_trial_balance(query_db, period_year, period_month):
    """
    试算平衡表

    Args:
        query_db: 数据库查询函数
        period_year: 年份
        period_month: 月份

    Returns:
        dict: 试算平衡结果
    """
    # 查询本期所有科目的借贷发生额
    sql = """
    SELECT
        coa.account_type,
        SUM(gl.debit_amount) AS total_debit,
        SUM(gl.credit_amount) AS total_credit
    FROM general_ledger gl
    JOIN chart_of_accounts coa ON gl.account_id = coa.id
    WHERE gl.period_year = %s AND gl.period_month = %s
    GROUP BY coa.account_type
    ORDER BY coa.account_type
    """

    rows = query_db(sql, (period_year, period_month))

    # 汇总统计
    result = {
        'period_year': period_year,
        'period_month': period_month,
        'by_type': [],
        'total_debit': 0,
        'total_credit': 0,
        'is_balanced': False,
        'variance': 0
    }

    total_debit = Decimal('0')
    total_credit = Decimal('0')

    for row in rows:
        debit = Decimal(str(row['total_debit'])) if row['total_debit'] else Decimal('0')
        credit = Decimal(str(row['total_credit'])) if row['total_credit'] else Decimal('0')

        result['by_type'].append({
            'account_type': row['account_type'],
            'total_debit': float(debit),
            'total_credit': float(credit)
        })

        total_debit += debit
        total_credit += credit

    result['total_debit'] = float(total_debit)
    result['total_credit'] = float(total_credit)
    result['variance'] = float(total_debit - total_credit)
    result['is_balanced'] = abs(total_debit - total_credit) < Decimal('0.01')

    return result


def get_account_balance_summary(rows):
    """
    科目余额表汇总统计

    Args:
        rows: 科目余额列表

    Returns:
        dict: 汇总数据
    """
    summary = {
        'total_accounts': len(rows),
        'total_opening_debit': 0,
        'total_opening_credit': 0,
        'total_current_debit': 0,
        'total_current_credit': 0,
        'total_ending_debit': 0,
        'total_ending_credit': 0,
        'by_type': {}
    }

    for row in rows:
        summary['total_opening_debit'] += row['opening_debit']
        summary['total_opening_credit'] += row['opening_credit']
        summary['total_current_debit'] += row['current_debit']
        summary['total_current_credit'] += row['current_credit']
        summary['total_ending_debit'] += row['ending_debit']
        summary['total_ending_credit'] += row['ending_credit']

        # 按科目类型统计
        account_type = row['account_type']
        if account_type not in summary['by_type']:
            summary['by_type'][account_type] = {
                'count': 0,
                'ending_debit': 0,
                'ending_credit': 0
            }

        summary['by_type'][account_type]['count'] += 1
        summary['by_type'][account_type]['ending_debit'] += row['ending_debit']
        summary['by_type'][account_type]['ending_credit'] += row['ending_credit']

    return summary
