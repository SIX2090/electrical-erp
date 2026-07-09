"""
财务报表路由
提供资产负债表、利润表、现金流量表相关的路由和API接口
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from services.financial_report_service import (
    generate_balance_sheet,
    generate_income_statement,
    generate_cash_flow_statement,
    get_report_history
)
from services.period_closing_service import get_current_period

# 全局变量，用于存储query_db和execute_db函数
_query_db = None
_execute_db = None


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def register_financial_report_routes(app, query_db, execute_db, login_required_decorator):
    """注册财务报表路由到Flask应用"""
    global _query_db, _execute_db
    _query_db = query_db
    _execute_db = execute_db

    @app.route('/finance/reports/')
    @login_required_decorator
    def report_home():
        """财务报表首页"""
        try:
            # 获取当前期间
            current_period = get_current_period()

            # 获取最近的报表生成历史
            history = get_report_history(_query_db, limit=10)

            return render_template(
                'finance/financial_report_home.html',
                current_period=current_period,
                history=history
            )

        except Exception as e:
            return render_template(
                'finance/financial_report_home.html',
                error=str(e)
            )


    @app.route('/finance/reports/balance-sheet')
    @login_required_decorator
    def balance_sheet():
        """资产负债表页面"""
        try:
            # 获取查询参数
            period = request.args.get('period', get_current_period())

            # 生成报表数据（GET 请求只读不写库，避免每次查看都产生历史记录）
            report_data = generate_balance_sheet(_query_db, period)

            return render_template(
                'finance/balance_sheet.html',
                period=period,
                report_data=report_data
            )

        except Exception as e:
            return render_template(
                'finance/balance_sheet.html',
                error=str(e),
                period=get_current_period(),
                report_data={}
            )


    @app.route('/finance/reports/income-statement')
    @login_required_decorator
    def income_statement():
        """利润表页面"""
        try:
            # 获取查询参数
            period = request.args.get('period', get_current_period())

            # 生成报表数据（GET 请求只读不写库）
            report_data = generate_income_statement(_query_db, period)

            return render_template(
                'finance/income_statement.html',
                period=period,
                report_data=report_data
            )

        except Exception as e:
            return render_template(
                'finance/income_statement.html',
                error=str(e),
                period=get_current_period(),
                report_data={}
            )


    @app.route('/finance/reports/cash-flow-statement')
    @login_required_decorator
    def cash_flow_statement():
        """现金流量表页面"""
        try:
            # 获取查询参数
            period = request.args.get('period', get_current_period())

            # 生成报表数据（GET 请求只读不写库）
            report_data = generate_cash_flow_statement(_query_db, period)

            return render_template(
                'finance/cash_flow_statement.html',
                period=period,
                report_data=report_data
            )

        except Exception as e:
            return render_template(
                'finance/cash_flow_statement.html',
                error=str(e),
                period=get_current_period(),
                report_data={}
            )


    @app.route('/finance/reports/api/balance-sheet/<period>')
    @login_required_decorator
    def api_balance_sheet(period):
        """API: 获取资产负债表数据"""
        try:
            report_data = generate_balance_sheet(_query_db, period)
            return jsonify(report_data)

        except Exception as e:
            return jsonify({
                'error': str(e)
            })


    @app.route('/finance/reports/api/income-statement/<period>')
    @login_required_decorator
    def api_income_statement(period):
        """API: 获取利润表数据"""
        try:
            report_data = generate_income_statement(_query_db, period)
            return jsonify(report_data)

        except Exception as e:
            return jsonify({
                'error': str(e)
            })


    @app.route('/finance/reports/api/cash-flow-statement/<period>')
    @login_required_decorator
    def api_cash_flow_statement(period):
        """API: 获取现金流量表数据"""
        try:
            report_data = generate_cash_flow_statement(_query_db, period)
            return jsonify(report_data)

        except Exception as e:
            return jsonify({
                'error': str(e)
            })


    @app.route('/api/finance/reports/history')
    @login_required_decorator
    def api_report_history():
        """API: 获取报表生成历史"""
        try:
            report_type = request.args.get('type')
            try:
                limit = int(request.args.get('limit', 20))
            except (TypeError, ValueError):
                limit = 20

            history = get_report_history(_query_db, report_type, limit)

            return jsonify({
                'history': history
            })

        except Exception as e:
            return jsonify({
                'error': str(e),
                'history': []
            })
