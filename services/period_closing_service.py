"""
期末处理服务
提供期末结账、反结账、损益结转等功能
"""

import logging
import re
from decimal import Decimal
from datetime import datetime
import json
from typing import Optional, Dict, List, Any

import psycopg2
from psycopg2.extras import RealDictCursor

from config import DB_CONFIG
from services.transaction_utils import cursor_db_helpers
from services.voucher_generation_service import post_voucher


logger = logging.getLogger(__name__)


def _configured_finance_current_period() -> Optional[str]:
    try:
        conn_kwargs = {key: value for key, value in DB_CONFIG.items() if key != "database"}
        with psycopg2.connect(**conn_kwargs, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(option_value, value) AS period
                    FROM system_options
                    WHERE option_key=%s OR key=%s
                    ORDER BY updated_at DESC NULLS LAST, id DESC
                    LIMIT 1
                    """,
                    ("finance_current_period", "finance_current_period"),
                )
                row = cur.fetchone()
        period = str((row or {}).get("period") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}", period):
            datetime.strptime(period + "-01", "%Y-%m-%d")
            return period
    except Exception:
        logger.warning("finance_current_period setting unavailable; using server month", exc_info=True)
    return None


def _next_period(period: str) -> str:
    year, month = period.split("-")
    next_year = int(year)
    next_month = int(month) + 1
    if next_month > 12:
        next_year += 1
        next_month = 1
    return f"{next_year}-{next_month:02d}"


def _save_finance_current_period(execute_db, period: str):
    execute_db(
        """
        INSERT INTO system_options (key, value, option_key, option_value, remark, updated_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (option_key)
        DO UPDATE SET
            key=EXCLUDED.key,
            value=EXCLUDED.value,
            option_value=EXCLUDED.option_value,
            remark=EXCLUDED.remark,
            updated_at=NOW()
        """,
        ("finance_current_period", period, "finance_current_period", period, "当前期间"),
    )


def _query_system_option(query_db, key: str, default: str = "") -> str:
    try:
        row = _query_one(
            query_db,
            """
            SELECT COALESCE(option_value, value) AS option_value
            FROM system_options
            WHERE option_key=%s OR key=%s
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (key, key),
        )
        return str(_value(row, "option_value", 0, default) or default).strip()
    except Exception:
        logger.warning("system option %s unavailable", key, exc_info=True)
        return default


def _valid_period(period: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}", period or ""):
        return False
    try:
        datetime.strptime(period + "-01", "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _is_closed_status(status) -> bool:
    text = str(status or "")
    return text in {"closed", "已结账"} or "结" in text or "粨" in text


def _query_one(query_db, sql, params=None):
    return query_db(sql, params, one=True)


def _value(row, key, index=0, default=None):
    if not row:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    return row[index] if len(row) > index else default


def _next_voucher_no(query_db, year: str, month: str) -> str:
    prefix = f"JZ-{year}{month}-"
    rows = query_db(
        "SELECT voucher_no FROM vouchers WHERE voucher_no LIKE %s ORDER BY voucher_no",
        (prefix + "%",),
    )
    used = set()
    for row in rows:
        voucher_no = _value(row, "voucher_no", 0, "")
        if isinstance(voucher_no, str) and voucher_no.startswith(prefix):
            suffix = voucher_no[len(prefix):]
            if suffix.isdigit():
                used.add(int(suffix))
    seq = 1
    while seq in used:
        seq += 1
    return f"{prefix}{seq:03d}"


def _insert_voucher_returning_id(query_db, execute_db, sql, params, voucher_no):
    try:
        result = execute_db(sql, params)
    except TypeError:
        result = None
    if isinstance(result, int):
        return result
    if isinstance(result, dict):
        return result.get("id")
    if result:
        return result[0]
    row = _query_one(query_db, "SELECT id FROM vouchers WHERE voucher_no = %s", (voucher_no,))
    return _value(row, "id")


def check_period_closing(query_db, period: str) -> Dict[str, Any]:
    """
    检查指定期间是否满足结账条件

    Args:
        query_db: 数据库查询函数
        period: 会计期间(YYYY-MM格式)

    Returns:
        {
            'can_close': bool,              # 是否可以结账
            'issues': list,                 # 未通过的检查项
            'warnings': list,               # 警告信息
            'summary': dict                 # 汇总信息
        }
    """

    issues = []
    warnings = []
    summary = {}

    try:
        # 1. 检查期间是否已结账
        period = str(period or "").strip()
        if not _valid_period(period):
            return {
                'can_close': False,
                'issues': [{
                    'check_item': '期间格式检查',
                    'result': '未通过',
                    'reason': '结账期间必须使用 YYYY-MM 格式',
                    'suggestion': '请从期间结账页面选择正确的会计期间'
                }],
                'warnings': [],
                'summary': summary
            }
        finance_start_period = _query_system_option(query_db, "finance_start_period")
        finance_current_period = _query_system_option(query_db, "finance_current_period") or get_current_period()
        summary['finance_start_period'] = finance_start_period or "-"
        summary['finance_current_period'] = finance_current_period or "-"
        if finance_start_period and _valid_period(finance_start_period) and period < finance_start_period:
            issues.append({
                'check_item': '财务启用期间检查',
                'result': '未通过',
                'reason': f'期间 {period} 早于财务启用期间 {finance_start_period}',
                'suggestion': '请检查系统管理的开账时间/启用期间设置'
            })
        if finance_current_period and _valid_period(finance_current_period) and period != finance_current_period:
            issues.append({
                'check_item': '当前期间检查',
                'result': '未通过',
                'reason': f'只能结当前期间 {finance_current_period}，不能直接结 {period}',
                'suggestion': '请按期间顺序结账；如当前期间不正确，请先在系统管理中调整'
            })
        year, month = period.split('-')
        check_sql = """
            SELECT status AS closing_status
            FROM period_closing
            WHERE period_year = %s AND period_month = %s
        """
        existing = _query_one(query_db, check_sql, (int(year), int(month)))

        if existing and _value(existing, 'closing_status') == '已结账':
            issues.append({
                'check_item': '期间状态检查',
                'result': '未通过',
                'reason': f'期间 {period} 已经结账',
                'suggestion': '如需重新结账，请先执行反结账操作'
            })
            return {
                'can_close': False,
                'issues': issues,
                'warnings': warnings,
                'summary': summary
            }

        # 2. 检查是否有未审核的凭证
        unreviewed_vouchers_sql = """
            SELECT COUNT(*)
            FROM vouchers
            WHERE period_year = %s AND period_month = %s
            AND (status IS NULL OR status NOT IN ('已审核', '已过账', 'posted', 'audited'))
        """
        unreviewed_count = _value(_query_one(query_db, unreviewed_vouchers_sql, (int(year), int(month))), 'count', 0, 0)

        if unreviewed_count > 0:
            issues.append({
                'check_item': '凭证审核检查',
                'result': '未通过',
                'reason': f'有 {unreviewed_count} 张凭证未审核',
                'suggestion': '请先审核所有凭证'
            })

        summary['unreviewed_vouchers'] = unreviewed_count

        # 3. 检查试算是否平衡
        trial_balance_sql = """
            SELECT
                COALESCE(SUM(debit_amount), 0) as total_debit,
                COALESCE(SUM(credit_amount), 0) as total_credit
            FROM voucher_lines vl
            JOIN vouchers v ON vl.voucher_id = v.id
            WHERE v.period_year = %s AND v.period_month = %s
        """
        balance_result = _query_one(query_db, trial_balance_sql, (int(year), int(month)))
        total_debit = Decimal(str(_value(balance_result, 'total_debit', 0, 0) or 0))
        total_credit = Decimal(str(_value(balance_result, 'total_credit', 1, 0) or 0))

        summary['total_debit'] = float(total_debit)
        summary['total_credit'] = float(total_credit)
        summary['balance_diff'] = float(total_debit - total_credit)

        if abs(total_debit - total_credit) > Decimal('0.01'):
            issues.append({
                'check_item': '试算平衡检查',
                'result': '未通过',
                'reason': f'借贷方不平衡，差异: {total_debit - total_credit}',
                'suggestion': '请检查凭证分录'
            })

        # 4. 检查上一期间是否已结账
        year, month = period.split('-')
        prev_month = int(month) - 1
        prev_year = int(year)
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        prev_period = f"{prev_year}-{prev_month:02d}"

        prev_closing_sql = """
            SELECT status AS closing_status
            FROM period_closing
            WHERE period_year = %s AND period_month = %s
        """
        prev_closing = _query_one(query_db, prev_closing_sql, (prev_year, prev_month))

        if not prev_closing or _value(prev_closing, 'closing_status') != '已结账':
            # 查询系统中最早的凭证期间作为系统起始期间
            earliest_period = _query_one(query_db, "SELECT MIN(period_year) AS y, MIN(period_month) AS m FROM vouchers WHERE period_year IS NOT NULL") or {}
            earliest_year = int(earliest_period.get('y') or 2026)
            earliest_month = int(earliest_period.get('m') or 1)
            if int(year) > earliest_year or (int(year) == earliest_year and int(month) > earliest_month):
                warnings.append({
                    'check_item': '上期结账检查',
                    'result': '警告',
                    'reason': f'上期 {prev_period} 未结账',
                    'suggestion': '建议先结账上期'
                })

        prev_closed = bool(prev_closing and _is_closed_status(_value(prev_closing, 'closing_status')))
        if not prev_closed and period != finance_start_period:
            issues.append({
                'check_item': '上期结账检查',
                'result': '未通过',
                'reason': f'上期 {prev_period} 未结账',
                'suggestion': '请先按顺序完成上一期间结账'
            })

        summary['prev_period'] = prev_period
        summary['prev_closed'] = bool(prev_closing and _value(prev_closing, 'closing_status') == '已结账')

        # 5. 统计本期凭证数量
        voucher_count_sql = """
            SELECT COUNT(*)
            FROM vouchers
            WHERE period_year = %s AND period_month = %s
        """
        voucher_count = _value(_query_one(query_db, voucher_count_sql, (int(year), int(month))), 'count', 0, 0)
        summary['voucher_count'] = voucher_count

        # 6. 统计本期损益科目余额
        profit_loss_sql = """
            SELECT
                COALESCE(SUM(CASE WHEN ga.balance_direction = '贷方'
                    THEN -gab.ending_balance ELSE 0 END), 0) as revenue,
                COALESCE(SUM(CASE WHEN ga.balance_direction = '借方'
                    THEN gab.ending_balance ELSE 0 END), 0) as expense
            FROM gl_account_balances gab
            JOIN chart_of_accounts ga ON gab.account_id = ga.id
            WHERE gab.period_year = %s AND gab.period_month = %s
            AND ga.account_type = '损益'
        """
        year, month = period.split('-')
        profit_loss = _query_one(query_db, profit_loss_sql, (int(year), int(month)))
        revenue = Decimal(str(_value(profit_loss, 'revenue', 0, 0) or 0))
        expense = Decimal(str(_value(profit_loss, 'expense', 1, 0) or 0))

        summary['revenue'] = float(revenue)
        summary['expense'] = float(expense)
        summary['net_profit'] = float(revenue - expense)

        # 判断是否可以结账
        can_close = len(issues) == 0

        return {
            'can_close': can_close,
            'issues': issues,
            'warnings': warnings,
            'summary': summary
        }

    except Exception as e:
        return {
            'can_close': False,
            'issues': [{'check_item': '系统检查', 'result': '错误', 'reason': str(e)}],
            'warnings': [],
            'summary': {}
        }


def generate_profit_transfer_voucher(query_db, execute_db, period: str, user_id: int) -> Optional[int]:
    """
    生成损益结转凭证

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数（用于INSERT/UPDATE/DELETE）
        period: 会计期间(YYYY-MM格式)
        user_id: 用户ID

    Returns:
        凭证ID，失败返回None
    """

    voucher_id = None
    try:
        # 1. 获取本期损益类科目余额
        profit_loss_accounts_sql = """
            SELECT
                ga.id as account_id,
                ga.code,
                ga.name,
                ga.balance_direction,
                COALESCE(gab.ending_balance, 0) as balance
            FROM chart_of_accounts ga
            LEFT JOIN gl_account_balances gab ON ga.id = gab.account_id
                AND gab.period_year = %s AND gab.period_month = %s
            WHERE ga.account_type = '损益'
            AND ga.is_leaf = TRUE
            AND COALESCE(gab.ending_balance, 0) != 0
            ORDER BY ga.code
        """

        year, month = period.split('-')
        accounts = query_db(profit_loss_accounts_sql, (int(year), int(month)))

        if not accounts:
            return None

        # 2. 获取"本年利润"科目ID
        profit_account_sql = """
            SELECT id
            FROM chart_of_accounts
            WHERE code = '4103'
            LIMIT 1
        """
        profit_account = _query_one(query_db, profit_account_sql)

        if not profit_account:
            raise Exception("未找到'本年利润'科目(4103)")

        profit_account_id = _value(profit_account, 'id')

        # 3. 创建结转凭证
        # 计算收入和费用总额（仅累计将实际结转的正数余额，保证借贷平衡）
        revenue_total = Decimal('0')
        expense_total = Decimal('0')

        for account in accounts:
            balance = Decimal(str(_value(account, 'balance', 4, 0) or 0))
            if balance == 0:
                continue
            if _value(account, 'balance_direction', 3) == '贷方':  # 收入类
                revenue_total += balance
            else:  # 费用类
                expense_total += balance

        net_profit = revenue_total - expense_total

        # 生成凭证
        voucher_insert_sql = """
            INSERT INTO vouchers (
                voucher_date, period_year, period_month, voucher_type, voucher_no,
                summary, prepared_by, status
            ) VALUES (
                %s, %s, %s, '记',
                %s, '结转本期损益', %s, '已审核'
            ) RETURNING id
        """

        # 获取期间最后一天
        year, month = period.split('-')
        if month == '12':
            voucher_date = f"{year}-12-31"
        else:
            next_month = int(month) + 1
            voucher_date = f"{year}-{next_month:02d}-01"
            # 减一天得到本月最后一天
            from datetime import datetime, timedelta
            date_obj = datetime.strptime(voucher_date, "%Y-%m-%d") - timedelta(days=1)
            voucher_date = date_obj.strftime("%Y-%m-%d")

        # Generate a unique voucher number for repeated close/reverse/close cycles.
        voucher_no = _next_voucher_no(query_db, year, month)

        voucher_id = _insert_voucher_returning_id(
            query_db,
            execute_db,
            voucher_insert_sql,
            (voucher_date, int(year), int(month), voucher_no, user_id),
            voucher_no,
        )

        if not voucher_id:
            raise Exception("创建凭证失败，未能获取凭证ID")

        # 4. 生成凭证分录
        entry_insert_sql = """
            INSERT INTO voucher_lines (
                voucher_id, account_id, summary,
                debit_amount, credit_amount
            ) VALUES (%s, %s, %s, %s, %s)
        """

        entries = []

        # 结转收入类科目（借方）
        for account in accounts:
            if _value(account, 'balance_direction', 3) == '贷方':  # 收入类
                balance = Decimal(str(_value(account, 'balance', 4, 0) or 0))
                if balance != 0:
                    entries.append((
                        voucher_id,
                        _value(account, 'account_id', 0),  # account_id
                        f"结转{_value(account, 'name', 2)}",
                        balance,  # 借方
                        0  # 贷方
                    ))

        # 本年利润贷方（收入总额）
        if revenue_total > 0:
            entries.append((
                voucher_id,
                profit_account_id,
                "结转本期收入",
                0,  # 借方
                revenue_total  # 贷方
            ))

        # 本年利润借方（费用总额）
        if expense_total > 0:
            entries.append((
                voucher_id,
                profit_account_id,
                "结转本期费用",
                expense_total,  # 借方
                0  # 贷方
            ))

        # 结转费用类科目（贷方）
        for account in accounts:
            if _value(account, 'balance_direction', 3) == '借方':  # 费用类
                balance = Decimal(str(_value(account, 'balance', 4, 0) or 0))
                if balance != 0:
                    entries.append((
                        voucher_id,
                        _value(account, 'account_id', 0),  # account_id
                        f"结转{_value(account, 'name', 2)}",
                        0,  # 借方
                        balance  # 贷方
                    ))

        # 批量插入分录 - 使用execute_db
        for entry in entries:
            execute_db(entry_insert_sql, entry)

        execute_db(
            """
            UPDATE vouchers
            SET total_debit = %s,
                total_credit = %s
            WHERE id = %s
            """,
            (revenue_total + expense_total, revenue_total + expense_total, voucher_id),
        )

        post_result = post_voucher(query_db, execute_db, voucher_id, user_id)
        if not post_result.get("success"):
            raise Exception(post_result.get("message") or "损益结转凭证过账失败")

        return voucher_id

    except Exception:
        logger.exception("generate_profit_transfer_voucher failed")
        # 清理已插入的孤儿凭证主表，避免残留无分录凭证
        try:
            if voucher_id:
                execute_db("DELETE FROM voucher_lines WHERE voucher_id = %s", (voucher_id,))
                execute_db("DELETE FROM vouchers WHERE id = %s", (voucher_id,))
        except Exception:
            logger.exception("cleanup orphan voucher failed in generate_profit_transfer_voucher")
        return None


def execute_period_closing(query_db, execute_db, period: str, user_id: int, get_db=None) -> Dict[str, Any]:
    """
    执行期末结账

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数（用于INSERT/UPDATE/DELETE）
        period: 会计期间(YYYY-MM格式)
        user_id: 用户ID

    Returns:
        {
            'success': bool,
            'message': str,
            'voucher_id': int,
            'net_profit': float
        }
    """

    if not getattr(query_db, "_uses_transaction_cursor", False):
        get_db = get_db or getattr(query_db, "__self_get_db__", None) or getattr(execute_db, "__self_get_db__", None)
        if get_db is None:
            try:
                from flask import current_app, has_app_context
                get_db = current_app.config.get("_get_db") if has_app_context() else None
            except Exception:
                get_db = None
        if get_db is not None:
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    tx_query_db, tx_execute_db, _ = cursor_db_helpers(cur)
                    result = execute_period_closing(tx_query_db, tx_execute_db, period, user_id)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    voucher_id = None
    try:
        year, month = period.split('-')
        execute_db(
            """
            INSERT INTO period_closing (period_year, period_month, status)
            VALUES (%s, %s, '结账中')
            ON CONFLICT (period_year, period_month) DO NOTHING
            """,
            (int(year), int(month)),
        )
        closing_lock = _query_one(
            query_db,
            """
            SELECT status
            FROM period_closing
            WHERE period_year = %s AND period_month = %s
            FOR UPDATE
            """,
            (int(year), int(month)),
        )
        if closing_lock and _value(closing_lock, "status", 0) == "已结账":
            return {
                'success': False,
                'message': f'期间 {period} 已经结账'
            }

        # 1. 再次检查结账条件
        check_result = check_period_closing(query_db, period)

        if not check_result['can_close']:
            execute_db(
                """
                UPDATE period_closing
                SET status = 'open'
                WHERE period_year = %s AND period_month = %s AND status = '结账中'
                """,
                (int(year), int(month)),
            )
            return {
                'success': False,
                'message': '结账条件检查未通过',
                'issues': check_result['issues']
            }

        # 2. 生成损益结转凭证
        voucher_id = generate_profit_transfer_voucher(query_db, execute_db, period, user_id)

        if not voucher_id:
            execute_db(
                """
                UPDATE period_closing
                SET status = 'open'
                WHERE period_year = %s AND period_month = %s AND status = '结账中'
                """,
                (int(year), int(month)),
            )
            return {
                'success': False,
                'message': '生成损益结转凭证失败'
            }

        # 3. 记录结账信息
        summary = check_result['summary']
        closing_insert_sql = """
            INSERT INTO period_closing (
                period_year, period_month, closing_date, status,
                revenue, cost, gross_profit, profit_transfer_voucher_id,
                closed_by, closed_at
            ) VALUES (
                %s, %s, CURRENT_DATE, '已结账',
                %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            )
            ON CONFLICT (period_year, period_month)
            DO UPDATE SET
                closing_date = CURRENT_DATE,
                status = '已结账',
                revenue = EXCLUDED.revenue,
                cost = EXCLUDED.cost,
                gross_profit = EXCLUDED.gross_profit,
                profit_transfer_voucher_id = EXCLUDED.profit_transfer_voucher_id,
                closed_by = EXCLUDED.closed_by,
                closed_at = CURRENT_TIMESTAMP
        """

        execute_db(
            closing_insert_sql,
            (
                int(year),
                int(month),
                Decimal(str(summary.get('revenue', 0) or 0)),
                Decimal(str(summary.get('expense', 0) or 0)),
                Decimal(str(summary.get('net_profit', 0) or 0)),
                voucher_id,
                user_id
            )
        )

        # C-3: 同步锁定 accounting_periods，使 _period_is_closed 生效
        execute_db(
            """
            INSERT INTO accounting_periods (year, month, status, closed_by, closed_at)
            VALUES (%s, %s, 'closed', %s, CURRENT_TIMESTAMP)
            ON CONFLICT (year, month) DO UPDATE SET
                status = 'closed',
                closed_by = EXCLUDED.closed_by,
                closed_at = EXCLUDED.closed_at
            """,
            (int(year), int(month), user_id)
        )

        next_period = _next_period(period)
        if get_current_period() == period:
            _save_finance_current_period(execute_db, next_period)

        return {
            'success': True,
            'message': f'期间 {period} 结账成功',
            'voucher_id': voucher_id,
            'net_profit': summary.get('net_profit', 0),
            'next_period': next_period
        }

    except Exception as e:
        # 结账中途失败时清理已生成的孤儿凭证，防止脏数据
        try:
            if voucher_id:
                execute_db("DELETE FROM voucher_lines WHERE voucher_id = %s", (voucher_id,))
                execute_db("DELETE FROM vouchers WHERE id = %s", (voucher_id,))
        except Exception:
            logger.exception("cleanup orphan voucher failed during period closing error")
        try:
            year, month = period.split('-')
            execute_db(
                """
                UPDATE period_closing
                SET status = 'open'
                WHERE period_year = %s AND period_month = %s AND status = '结账中'
                """,
                (int(year), int(month)),
            )
        except Exception:
            logger.exception("cleanup closing marker failed during period closing error")
        return {
            'success': False,
            'message': f'结账失败: {str(e)}'
        }


def reverse_period_closing(query_db, execute_db, period: str, user_id: int, reason: str, get_db=None) -> Dict[str, Any]:
    """
    反结账操作

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数（用于INSERT/UPDATE/DELETE）
        period: 会计期间(YYYY-MM格式)
        user_id: 用户ID
        reason: 反结账原因
        get_db: 可选，提供事务支持的数据库连接函数

    Returns:
        {
            'success': bool,
            'message': str
        }

    反结账不再物理删除凭证和总账记录，改为状态作废（已作废/reversed），
    保留审计链。整个流程在单事务中执行，任一步失败整体回滚。
    """

    try:
        # 1. 检查期间是否已结账
        year, month = period.split('-')
        check_sql = """
            SELECT id, status AS closing_status, profit_transfer_voucher_id
            FROM period_closing
            WHERE period_year = %s AND period_month = %s
        """
        closing = _query_one(query_db, check_sql, (int(year), int(month)))

        if not closing:
            return {
                'success': False,
                'message': f'期间 {period} 未结账，无需反结账'
            }

        closing_status = _value(closing, 'closing_status', 1)
        if closing_status != '已结账':
            return {
                'success': False,
                'message': f'期间 {period} 状态为 {closing_status}，无法反结账'
            }

        # 2. 检查下一期是否已结账
        next_month = int(month) + 1
        next_year = int(year)
        if next_month > 12:
            next_month = 1
            next_year += 1
        next_period = f"{next_year}-{next_month:02d}"

        next_closing_sql = """
            SELECT status AS closing_status
            FROM period_closing
            WHERE period_year = %s AND period_month = %s
        """
        next_closing = _query_one(query_db, next_closing_sql, (next_year, next_month))

        if next_closing and _value(next_closing, 'closing_status') == '已结账':
            return {
                'success': False,
                'message': f'下期 {next_period} 已结账，不允许反结账'
            }

        voucher_id = _value(closing, 'profit_transfer_voucher_id', 2)

        # 3. 执行反结账（单事务：状态作废凭证和总账，更新结账记录）
        if get_db is not None:
            # 有事务支持：使用 get_db 进行单事务控制
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    if voucher_id:
                        # 状态作废总账明细（不再物理删除，保留审计链）
                        cur.execute(
                            "UPDATE general_ledger SET status = 'reversed' WHERE voucher_id = %s AND COALESCE(status, 'active') = 'active'",
                            (voucher_id,)
                        )
                        # 状态作废凭证分录（voucher_lines 无 status 列，通过凭证状态间接控制）
                        # 状态作废凭证
                        cur.execute(
                            "UPDATE vouchers SET status = '已作废', remark = COALESCE(remark, '') || ' | 反结账作废' WHERE id = %s",
                            (voucher_id,)
                        )

                    # 更新结账记录状态
                    cur.execute(
                        """
                        UPDATE period_closing
                        SET status = '已反结账',
                            profit_transfer_voucher_id = NULL,
                            remark = %s,
                            closed_at = CURRENT_TIMESTAMP,
                            closed_by = %s
                        WHERE period_year = %s AND period_month = %s
                        """,
                        (reason, user_id, int(year), int(month))
                    )
                    # C-3: 释放 accounting_periods 锁定，使期间可再写入
                    cur.execute(
                        """
                        UPDATE accounting_periods
                        SET status = 'open', closed_by = NULL, closed_at = NULL
                        WHERE year = %s AND month = %s
                        """,
                        (int(year), int(month))
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        else:
            # 无事务支持（回退路径）：逐步执行，使用 execute_db
            if voucher_id:
                # 状态作废总账明细
                execute_db(
                    "UPDATE general_ledger SET status = 'reversed' WHERE voucher_id = %s AND COALESCE(status, 'active') = 'active'",
                    (voucher_id,)
                )
                # 状态作废凭证
                execute_db(
                    "UPDATE vouchers SET status = '已作废', remark = COALESCE(remark, '') || ' | 反结账作废' WHERE id = %s",
                    (voucher_id,)
                )

            # 更新结账记录状态
            execute_db(
                """
                UPDATE period_closing
                SET status = '已反结账',
                    profit_transfer_voucher_id = NULL,
                    remark = %s,
                    closed_at = CURRENT_TIMESTAMP,
                    closed_by = %s
                WHERE period_year = %s AND period_month = %s
                """,
                (reason, user_id, int(year), int(month))
            )
            # C-3: 释放 accounting_periods 锁定，使期间可再写入
            execute_db(
                """
                UPDATE accounting_periods
                SET status = 'open', closed_by = NULL, closed_at = NULL
                WHERE year = %s AND month = %s
                """,
                (int(year), int(month))
            )

        return {
            'success': True,
            'message': f'期间 {period} 反结账成功'
        }

    except Exception as e:
        logger.exception("反结账失败: period=%s", period)
        return {
            'success': False,
            'message': f'反结账失败: {str(e)}'
        }


def get_closing_history(query_db, limit: int = 12) -> List[Dict[str, Any]]:
    """
    获取结账历史记录

    Args:
        query_db: 数据库查询函数
        limit: 返回记录数量

    Returns:
        结账历史列表
    """

    try:
        sql = """
            SELECT
                TO_CHAR(pc.period_year, 'FM0000') || '-' || TO_CHAR(pc.period_month, 'FM00') AS closing_period,
                pc.closing_date,
                pc.status AS closing_status,
                pc.revenue AS total_revenue,
                pc.cost AS total_expense,
                pc.gross_profit AS net_profit,
                pc.closed_by,
                pc.closed_at,
                NULL::INTEGER AS unclosed_by,
                NULL::TIMESTAMP AS unclosed_at,
                NULL::TEXT AS unclosing_reason,
                u1.username as closer_name,
                NULL::TEXT AS uncloser_name
            FROM period_closing pc
            LEFT JOIN users u1 ON pc.closed_by = u1.id
            ORDER BY pc.period_year DESC, pc.period_month DESC
            LIMIT %s
        """

        rows = query_db(sql, (limit,))

        history = []
        for row in rows:
            closing_date = _value(row, 'closing_date', 1)
            closed_at = _value(row, 'closed_at', 7)
            unclosed_at = _value(row, 'unclosed_at', 9)
            history.append({
                'closing_period': _value(row, 'closing_period', 0),
                'closing_date': closing_date.strftime('%Y-%m-%d') if closing_date else None,
                'closing_status': _value(row, 'closing_status', 2),
                'total_revenue': float(_value(row, 'total_revenue', 3, 0) or 0),
                'total_expense': float(_value(row, 'total_expense', 4, 0) or 0),
                'net_profit': float(_value(row, 'net_profit', 5, 0) or 0),
                'closed_by': _value(row, 'closed_by', 6),
                'closed_at': closed_at.strftime('%Y-%m-%d %H:%M:%S') if closed_at else None,
                'unclosed_by': _value(row, 'unclosed_by', 8),
                'unclosed_at': unclosed_at.strftime('%Y-%m-%d %H:%M:%S') if unclosed_at else None,
                'unclosing_reason': _value(row, 'unclosing_reason', 10),
                'closer_name': _value(row, 'closer_name', 11),
                'uncloser_name': _value(row, 'uncloser_name', 12)
            })

        return history

    except Exception:
        logger.exception("get_closing_history failed")
        return []


def get_current_period() -> str:
    """
    获取当前会计期间(YYYY-MM格式)
    """
    configured_period = _configured_finance_current_period()
    if configured_period:
        return configured_period
    now = datetime.now()
    return now.strftime('%Y-%m')


def get_latest_closed_period(query_db) -> Optional[str]:
    """
    获取最近已结账的期间

    Args:
        query_db: 数据库查询函数

    Returns:
        期间字符串(YYYY-MM)，如果没有则返回None
    """

    try:
        sql = """
            SELECT TO_CHAR(period_year, 'FM0000') || '-' || TO_CHAR(period_month, 'FM00') AS closing_period
            FROM period_closing
            WHERE status = '已结账'
            ORDER BY period_year DESC, period_month DESC
            LIMIT 1
        """

        result = _query_one(query_db, sql)
        return _value(result, 'closing_period') if result else None

    except Exception:
        logger.exception("get_latest_closed_period failed")
        return None
