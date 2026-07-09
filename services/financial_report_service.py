"""
财务报表服务
提供资产负债表、利润表、现金流量表生成功能
"""

from decimal import Decimal
from datetime import datetime
import json
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


def get_account_balance(query_db, account_codes: List[str], period: str,
                       balance_type: str = 'ending') -> Decimal:
    """
    获取指定科目的余额

    Args:
        query_db: 数据库查询函数
        account_codes: 科目编码列表
        period: 会计期间(YYYY-MM格式)
        balance_type: 余额类型 'ending'期末余额 / 'debit'借方发生额 / 'credit'贷方发生额

    Returns:
        余额总额
    """

    if not account_codes:
        return Decimal('0')

    try:
        placeholders = ','.join(['%s'] * len(account_codes))

        if balance_type == 'ending':
            sql = f"""
                SELECT COALESCE(SUM(gab.ending_balance), 0) AS balance_amount
                FROM gl_account_balances gab
                JOIN chart_of_accounts ga ON gab.account_id = ga.id
                WHERE ga.code IN ({placeholders})
                AND gab.period_year = %s AND gab.period_month = %s
            """
        elif balance_type == 'debit':
            sql = f"""
                SELECT COALESCE(SUM(gab.debit_amount), 0) AS balance_amount
                FROM gl_account_balances gab
                JOIN chart_of_accounts ga ON gab.account_id = ga.id
                WHERE ga.code IN ({placeholders})
                AND gab.period_year = %s AND gab.period_month = %s
            """
        elif balance_type == 'credit':
            sql = f"""
                SELECT COALESCE(SUM(gab.credit_amount), 0) AS balance_amount
                FROM gl_account_balances gab
                JOIN chart_of_accounts ga ON gab.account_id = ga.id
                WHERE ga.code IN ({placeholders})
                AND gab.period_year = %s AND gab.period_month = %s
            """
        else:
            return Decimal('0')

        year, month = period.split('-')
        params = tuple(account_codes) + (int(year), int(month))
        result = query_db(sql, params, one=True)

        return Decimal(str((result or {}).get('balance_amount') or 0))

    except Exception as e:
        logger.exception("获取科目余额失败")
        return Decimal('0')


def generate_balance_sheet(query_db, period: str) -> Dict[str, Any]:
    """
    生成资产负债表

    Args:
        query_db: 数据库查询函数
        period: 会计期间(YYYY-MM格式)

    Returns:
        资产负债表数据
    """

    try:
        report_data = {
            'period': period,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'assets': {},
            'liabilities': {},
            'equity': {},
            'balanced': False
        }

        # ==================== 资产类 ====================

        # 流动资产
        current_assets = {}

        # 货币资金 = 库存现金 + 银行存款 + 其他货币资金
        current_assets['货币资金'] = float(
            get_account_balance(query_db, ['1001', '1002', '1012'], period)
        )

        # 应收账款
        current_assets['应收账款'] = float(
            get_account_balance(query_db, ['1122'], period)
        )

        # 预付账款
        current_assets['预付账款'] = float(
            get_account_balance(query_db, ['1123'], period)
        )

        # 其他应收款
        current_assets['其他应收款'] = float(
            get_account_balance(query_db, ['1221'], period)
        )

        # 存货 = 原材料 + 库存商品 + 在产品 + 发出商品 + 委托加工物资
        current_assets['存货'] = float(
            get_account_balance(query_db, ['1403', '1405', '1404', '1406', '1407'], period)
        )

        # 流动资产合计
        current_assets['流动资产合计'] = sum(
            v for k, v in current_assets.items() if k != '流动资产合计'
        )

        # 非流动资产
        non_current_assets = {}

        # 固定资产
        non_current_assets['固定资产'] = float(
            get_account_balance(query_db, ['1601'], period)
        )

        # 无形资产
        non_current_assets['无形资产'] = float(
            get_account_balance(query_db, ['1701'], period)
        )

        # 长期待摊费用
        non_current_assets['长期待摊费用'] = float(
            get_account_balance(query_db, ['1801'], period)
        )

        # 非流动资产合计
        non_current_assets['非流动资产合计'] = sum(
            v for k, v in non_current_assets.items() if k != '非流动资产合计'
        )

        # 资产总计
        report_data['assets'] = {
            '流动资产': current_assets,
            '非流动资产': non_current_assets,
            '资产总计': current_assets['流动资产合计'] + non_current_assets['非流动资产合计']
        }

        # ==================== 负债类 ====================

        # 流动负债
        current_liabilities = {}

        # 应付账款
        current_liabilities['应付账款'] = float(
            get_account_balance(query_db, ['2202'], period)
        )

        # 预收账款
        current_liabilities['预收账款'] = float(
            get_account_balance(query_db, ['2203'], period)
        )

        # 应付职工薪酬
        current_liabilities['应付职工薪酬'] = float(
            get_account_balance(query_db, ['2211'], period)
        )

        # 应交税费
        current_liabilities['应交税费'] = float(
            get_account_balance(query_db, ['2221'], period)
        )

        # 其他应付款
        current_liabilities['其他应付款'] = float(
            get_account_balance(query_db, ['2241'], period)
        )

        # 流动负债合计
        current_liabilities['流动负债合计'] = sum(
            v for k, v in current_liabilities.items() if k != '流动负债合计'
        )

        # 非流动负债
        non_current_liabilities = {}

        # 长期借款
        non_current_liabilities['长期借款'] = float(
            get_account_balance(query_db, ['2501'], period)
        )

        # 长期应付款
        non_current_liabilities['长期应付款'] = float(
            get_account_balance(query_db, ['2701'], period)
        )

        # 非流动负债合计
        non_current_liabilities['非流动负债合计'] = sum(
            v for k, v in non_current_liabilities.items() if k != '非流动负债合计'
        )

        # 负债合计
        report_data['liabilities'] = {
            '流动负债': current_liabilities,
            '非流动负债': non_current_liabilities,
            '负债合计': current_liabilities['流动负债合计'] + non_current_liabilities['非流动负债合计']
        }

        # ==================== 所有者权益类 ====================

        equity = {}

        # 实收资本
        equity['实收资本'] = float(
            get_account_balance(query_db, ['4001'], period)
        )

        # 资本公积
        equity['资本公积'] = float(
            get_account_balance(query_db, ['4002'], period)
        )

        # 盈余公积
        equity['盈余公积'] = float(
            get_account_balance(query_db, ['4101'], period)
        )

        # 未分配利润
        equity['未分配利润'] = float(
            get_account_balance(query_db, ['4104'], period)
        )

        # 本年利润
        equity['本年利润'] = float(
            get_account_balance(query_db, ['4103'], period)
        )

        # 所有者权益合计
        equity['所有者权益合计'] = sum(
            v for k, v in equity.items() if k != '所有者权益合计'
        )

        report_data['equity'] = equity

        # ==================== 平衡校验 ====================

        assets_total = report_data['assets']['资产总计']
        liabilities_equity_total = (
            report_data['liabilities']['负债合计'] +
            report_data['equity']['所有者权益合计']
        )

        # 允许0.01的误差
        report_data['balanced'] = abs(assets_total - liabilities_equity_total) < 0.01
        report_data['balance_diff'] = assets_total - liabilities_equity_total

        return report_data

    except Exception as e:
        print(f"生成资产负债表失败: {e}")
        return {
            'period': period,
            'error': str(e),
            'assets': {},
            'liabilities': {},
            'equity': {},
            'balanced': False
        }


def generate_income_statement(query_db, period: str) -> Dict[str, Any]:
    """
    生成利润表

    Args:
        query_db: 数据库查询函数
        period: 会计期间(YYYY-MM格式)

    Returns:
        利润表数据
    """

    try:
        report_data = {
            'period': period,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # ==================== 收入 ====================

        # 主营业务收入（取贷方发生额）
        revenue_main = float(
            get_account_balance(query_db, ['6001'], period, 'credit')
        )

        # 其他业务收入
        revenue_other = float(
            get_account_balance(query_db, ['6051'], period, 'credit')
        )

        # 营业收入合计
        revenue_total = revenue_main + revenue_other

        report_data['revenue'] = {
            '主营业务收入': revenue_main,
            '其他业务收入': revenue_other,
            '营业收入合计': revenue_total
        }

        # ==================== 成本 ====================

        # 主营业务成本（取借方发生额）
        cost_main = float(
            get_account_balance(query_db, ['6401'], period, 'debit')
        )

        # 其他业务成本
        cost_other = float(
            get_account_balance(query_db, ['6402'], period, 'debit')
        )

        # 营业成本合计
        cost_total = cost_main + cost_other

        report_data['cost'] = {
            '主营业务成本': cost_main,
            '其他业务成本': cost_other,
            '营业成本合计': cost_total
        }

        # ==================== 税金及附加 ====================

        taxes = float(
            get_account_balance(query_db, ['6403'], period, 'debit')
        )

        report_data['taxes'] = taxes

        # ==================== 期间费用 ====================

        # 销售费用
        expense_selling = float(
            get_account_balance(query_db, ['6601'], period, 'debit')
        )

        # 管理费用
        expense_admin = float(
            get_account_balance(query_db, ['6602'], period, 'debit')
        )

        # 财务费用
        expense_finance = float(
            get_account_balance(query_db, ['6603'], period, 'debit')
        )

        # 期间费用合计
        expense_total = expense_selling + expense_admin + expense_finance

        report_data['expenses'] = {
            '销售费用': expense_selling,
            '管理费用': expense_admin,
            '财务费用': expense_finance,
            '期间费用合计': expense_total
        }

        # ==================== 其他收益和损失 ====================

        # 其他收益（贷方发生额）
        other_income = float(
            get_account_balance(query_db, ['6301'], period, 'credit')
        )

        # 营业外收入（贷方发生额）
        non_operating_income = float(
            get_account_balance(query_db, ['6701'], period, 'credit')
        )

        # 营业外支出（借方发生额）
        non_operating_expense = float(
            get_account_balance(query_db, ['6711'], period, 'debit')
        )

        report_data['other'] = {
            '其他收益': other_income,
            '营业外收入': non_operating_income,
            '营业外支出': non_operating_expense
        }

        # ==================== 利润计算 ====================

        # 营业利润 = 营业收入 - 营业成本 - 税金及附加 - 期间费用 + 其他收益
        operating_profit = (
            revenue_total - cost_total - taxes - expense_total + other_income
        )

        # 利润总额 = 营业利润 + 营业外收入 - 营业外支出
        profit_before_tax = (
            operating_profit + non_operating_income - non_operating_expense
        )

        # 所得税费用
        income_tax = float(
            get_account_balance(query_db, ['6801'], period, 'debit')
        )

        # 净利润 = 利润总额 - 所得税费用
        net_profit = profit_before_tax - income_tax

        report_data['profit'] = {
            '营业利润': operating_profit,
            '利润总额': profit_before_tax,
            '所得税费用': income_tax,
            '净利润': net_profit
        }

        return report_data

    except Exception as e:
        print(f"生成利润表失败: {e}")
        return {
            'period': period,
            'error': str(e),
            'revenue': {},
            'cost': {},
            'expenses': {},
            'profit': {}
        }


def generate_cash_flow_statement(query_db, period: str) -> Dict[str, Any]:
    """
    生成现金流量表（简化版-直接法）

    Args:
        query_db: 数据库查询函数
        period: 会计期间(YYYY-MM格式)

    Returns:
        现金流量表数据
    """

    try:
        report_data = {
            'period': period,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # 现金科目：库存现金(1001)、银行存款(1002)
        cash_accounts = ['1001', '1002']

        # ==================== 经营活动现金流量 ====================

        operating = {}

        # 销售商品、提供劳务收到的现金
        # 简化：应收账款的贷方发生额 + 预收账款的贷方发生额
        operating['销售商品收到的现金'] = float(
            get_account_balance(query_db, ['1122', '2203'], period, 'credit')
        )

        # 收到的其他与经营活动有关的现金
        operating['收到其他经营现金'] = float(
            get_account_balance(query_db, ['1221'], period, 'credit')
        )

        # 经营活动现金流入小计
        operating['经营活动现金流入小计'] = (
            operating['销售商品收到的现金'] +
            operating['收到其他经营现金']
        )

        # 购买商品、接受劳务支付的现金
        # 简化：应付账款的借方发生额 + 预付账款的借方发生额
        operating['购买商品支付的现金'] = float(
            get_account_balance(query_db, ['2202', '1123'], period, 'debit')
        )

        # 支付给职工以及为职工支付的现金
        operating['支付职工薪酬'] = float(
            get_account_balance(query_db, ['2211'], period, 'debit')
        )

        # 支付的各项税费
        operating['支付的税费'] = float(
            get_account_balance(query_db, ['2221'], period, 'debit')
        )

        # 支付其他与经营活动有关的现金
        operating['支付其他经营现金'] = float(
            get_account_balance(query_db, ['2241'], period, 'debit')
        )

        # 经营活动现金流出小计
        operating['经营活动现金流出小计'] = (
            operating['购买商品支付的现金'] +
            operating['支付职工薪酬'] +
            operating['支付的税费'] +
            operating['支付其他经营现金']
        )

        # 经营活动产生的现金流量净额
        operating['经营活动现金流量净额'] = (
            operating['经营活动现金流入小计'] -
            operating['经营活动现金流出小计']
        )

        report_data['operating'] = operating

        # ==================== 投资活动现金流量 ====================

        investing = {}

        # 处置固定资产收到的现金
        investing['处置固定资产收到现金'] = 0.0

        # 投资活动现金流入小计
        investing['投资活动现金流入小计'] = 0.0

        # 购建固定资产支付的现金
        investing['购建固定资产支付现金'] = 0.0

        # 投资支付的现金
        investing['投资支付的现金'] = 0.0

        # 投资活动现金流出小计
        investing['投资活动现金流出小计'] = 0.0

        # 投资活动产生的现金流量净额
        investing['投资活动现金流量净额'] = 0.0

        report_data['investing'] = investing

        # ==================== 筹资活动现金流量 ====================

        financing = {}

        # 吸收投资收到的现金
        financing['吸收投资收到现金'] = 0.0

        # 取得借款收到的现金
        financing['取得借款收到现金'] = float(
            get_account_balance(query_db, ['2501'], period, 'credit')
        )

        # 筹资活动现金流入小计
        financing['筹资活动现金流入小计'] = (
            financing['吸收投资收到现金'] +
            financing['取得借款收到现金']
        )

        # 偿还债务支付的现金
        financing['偿还债务支付现金'] = float(
            get_account_balance(query_db, ['2501'], period, 'debit')
        )

        # 分配股利支付的现金
        financing['分配股利支付现金'] = 0.0

        # 筹资活动现金流出小计
        financing['筹资活动现金流出小计'] = (
            financing['偿还债务支付现金'] +
            financing['分配股利支付现金']
        )

        # 筹资活动产生的现金流量净额
        financing['筹资活动现金流量净额'] = (
            financing['筹资活动现金流入小计'] -
            financing['筹资活动现金流出小计']
        )

        report_data['financing'] = financing

        # ==================== 现金净增加额 ====================

        # 汇率变动对现金的影响
        exchange_effect = 0.0

        # 现金及现金等价物净增加额
        net_increase = (
            operating['经营活动现金流量净额'] +
            investing['投资活动现金流量净额'] +
            financing['筹资活动现金流量净额'] +
            exchange_effect
        )

        report_data['summary'] = {
            '汇率变动对现金的影响': exchange_effect,
            '现金及现金等价物净增加额': net_increase
        }

        # 期初现金余额
        # 获取上期期末余额
        year, month = period.split('-')
        prev_month = int(month) - 1
        prev_year = int(year)
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        prev_period = f"{prev_year}-{prev_month:02d}"

        beginning_cash = float(
            get_account_balance(query_db, cash_accounts, prev_period, 'ending')
        )

        # 期末现金余额
        ending_cash = float(
            get_account_balance(query_db, cash_accounts, period, 'ending')
        )

        report_data['cash_balance'] = {
            '期初现金余额': beginning_cash,
            '期末现金余额': ending_cash,
            '净增加额校验': ending_cash - beginning_cash
        }

        return report_data

    except Exception as e:
        logger.exception("生成现金流量表失败: %s", e)
        return {
            'period': period,
            'error': str(e),
            'operating': {},
            'investing': {},
            'financing': {},
            'summary': {}
        }


def save_report_data(query_db, execute_db, report_type: str, period: str,
                    data: Dict[str, Any], user_id: int) -> bool:
    """
    保存报表生成记录到数据库

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数（用于INSERT/UPDATE/DELETE）
        report_type: 报表类型
        period: 会计期间
        data: 报表数据
        user_id: 用户ID

    Returns:
        是否保存成功
    """

    try:
        year, month = period.split('-')
        sql = """
            INSERT INTO financial_report_log (
                report_type, period_year, period_month, report_data,
                generated_by, generated_at
            ) VALUES (
                %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            )
        """

        execute_db(
            sql,
            (
                report_type,
                int(year),
                int(month),
                json.dumps(data, ensure_ascii=False),
                user_id
            )
        )

        return True

    except Exception as e:
        print(f"保存报表数据失败: {e}")
        return False


def get_report_history(query_db, report_type: Optional[str] = None,
                      limit: int = 20) -> List[Dict[str, Any]]:
    """
    获取报表生成历史

    Args:
        query_db: 数据库查询函数
        report_type: 报表类型，None表示所有类型
        limit: 返回记录数量

    Returns:
        报表历史列表
    """

    try:
        if report_type:
            sql = """
                SELECT
                    frl.id,
                    frl.report_type,
                    TO_CHAR(frl.period_year, 'FM0000') || '-' || TO_CHAR(frl.period_month, 'FM00') AS report_period,
                    frl.generated_by,
                    frl.generated_at,
                    u.username as generator_name
                FROM financial_report_log frl
                LEFT JOIN users u ON frl.generated_by = u.id
                WHERE frl.report_type = %s
                ORDER BY frl.generated_at DESC
                LIMIT %s
            """
            params = (report_type, limit)
        else:
            sql = """
                SELECT
                    frl.id,
                    frl.report_type,
                    TO_CHAR(frl.period_year, 'FM0000') || '-' || TO_CHAR(frl.period_month, 'FM00') AS report_period,
                    frl.generated_by,
                    frl.generated_at,
                    u.username as generator_name
                FROM financial_report_log frl
                LEFT JOIN users u ON frl.generated_by = u.id
                ORDER BY frl.generated_at DESC
                LIMIT %s
            """
            params = (limit,)

        rows = query_db(sql, params)

        history = []
        for row in rows:
            history.append({
                'id': row.get('id'),
                'report_type': row.get('report_type'),
                'report_period': row.get('report_period'),
                'generated_by': row.get('generated_by'),
                'generated_at': row.get('generated_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('generated_at') else None,
                'generator_name': row.get('generator_name')
            })

        return history

    except Exception as e:
        print(f"获取报表历史失败: {e}")
        return []
