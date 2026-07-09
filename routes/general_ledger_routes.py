# -*- coding: utf-8 -*-
"""
总账报表路由
处理科目余额表、明细账、试算平衡表等总账报表查询
"""
from flask import request, render_template
from services.general_ledger_service import (
    query_account_balance,
    query_account_detail_ledger,
    query_trial_balance,
    get_account_balance_summary
)
from datetime import datetime


def register_general_ledger_routes(app, query_db, _login_required):
    """
    注册总账报表路由

    Args:
        app: Flask应用实例
        query_db: 数据库查询函数
        _login_required: 登录验证装饰器
    """

    # B-001: /finance/reports/account-balance is intentionally NOT registered
    # here. finance_routes.py:7572 already serves that path with a different
    # endpoint name. Registering it here too would override the active handler.
    # The original handler body is preserved below for reference but disabled.
    #
    # @app.route("/finance/reports/account-balance")
    # @_login_required
    # def account_balance_report():
    #     ... (see git history for the original body)

    @app.route("/finance/reports/account-detail-ledger")
    @_login_required
    def account_detail_ledger_report():
        """
        科目明细账
        """
        # 获取筛选条件
        filters = {
            'account_id': request.args.get('account_id'),
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'project_code': request.args.get('project_code'),
            'serial_no': request.args.get('serial_no')
        }

        rows = []
        account = None

        if filters['account_id']:
            # 查询数据
            rows = query_account_detail_ledger(query_db, filters)

            # 获取科目信息
            account = query_db(
                "SELECT id, code, name, balance_direction FROM chart_of_accounts WHERE id = %s",
                (filters['account_id'],),
                one=True
            )

        # 获取科目列表（用于筛选下拉框）
        accounts = query_db(
            """
            SELECT id, code, name
            FROM chart_of_accounts
            WHERE is_leaf = TRUE AND status = 'active'
            ORDER BY code
            """
        )

        return render_template(
            'finance/account_detail_ledger.html',
            rows=rows,
            account=account,
            filters=filters,
            accounts=accounts
        )

    @app.route("/finance/reports/trial-balance")
    @_login_required
    def trial_balance_report():
        """
        试算平衡表
        """
        # 获取期间参数
        current_year = datetime.now().year
        current_month = datetime.now().month

        try:
            period_year = int(request.args.get('period_year', current_year))
        except (TypeError, ValueError):
            period_year = current_year
        try:
            period_month = int(request.args.get('period_month', current_month))
        except (TypeError, ValueError):
            period_month = current_month

        # 查询试算平衡数据
        result = query_trial_balance(query_db, period_year, period_month)

        return render_template(
            'finance/trial_balance_report.html',
            result=result,
            period_year=period_year,
            period_month=period_month
        )
