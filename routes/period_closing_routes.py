"""
期末处理路由
提供期末结账、反结账相关的路由和API接口
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from services.period_closing_service import (
    check_period_closing,
    execute_period_closing,
    reverse_period_closing,
    get_closing_history,
    get_current_period,
    get_latest_closed_period
)

# 全局变量，用于存储query_db和execute_db函数
_query_db = None
_execute_db = None
_get_db = None


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def register_period_closing_routes(app, query_db, execute_db, login_required_decorator, get_db=None):
    """注册期末处理路由到Flask应用"""
    global _query_db, _execute_db, _get_db
    _query_db = query_db
    _execute_db = execute_db
    _get_db = get_db

    @app.route('/finance/period-closing/')
    @login_required_decorator
    def period_closing_home():
        """期末处理首页"""
        try:
            # 获取当前期间
            current_period = get_current_period()

            # 获取最近已结账期间
            latest_closed = get_latest_closed_period(_query_db)

            # 获取最近3个月的结账历史
            history = get_closing_history(_query_db, limit=3)

            return render_template(
                'finance/period_closing_home.html',
                current_period=current_period,
                latest_closed=latest_closed,
                history=history
            )

        except Exception as e:
            return render_template(
                'finance/period_closing_home.html',
                error=str(e)
            )


    @app.route('/finance/period-closing/check', methods=['GET', 'POST'])
    @login_required_decorator
    def closing_check():
        """结账检查页面"""
        try:
            if request.method == 'GET':
                # GET请求：显示检查页面
                period = request.args.get('period', get_current_period())

                return render_template(
                    'finance/period_closing_check.html',
                    period=period
                )

            else:
                # POST请求：执行检查
                data = request.get_json(silent=True) or {}
                period = data.get('period', get_current_period())

                # 执行检查
                result = check_period_closing(_query_db, period)

                return jsonify(result)

        except Exception as e:
            return jsonify({
                'can_close': False,
                'issues': [{'check_item': '系统错误', 'result': '错误', 'reason': str(e)}],
                'warnings': [],
                'summary': {}
            })


    @app.route('/finance/period-closing/execute', methods=['POST'])
    @login_required_decorator
    def execute_closing():
        """执行结账"""
        try:
            data = request.get_json(silent=True) or {}
            period = data.get('period')
            user_id = session.get('user_id')

            if not period:
                return jsonify({
                    'success': False,
                    'message': '缺少期间参数'
                })

            # 执行结账
            result = execute_period_closing(_query_db, _execute_db, period, user_id, get_db=_get_db)

            return jsonify(result)

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'执行结账失败: {str(e)}'
            })


    @app.route('/finance/period-closing/reverse', methods=['POST'])
    @login_required_decorator
    def reverse_closing():
        """反结账"""
        try:
            data = request.get_json(silent=True) or {}
            period = data.get('period')
            reason = data.get('reason', '用户反结账操作')
            user_id = session.get('user_id')

            if not period:
                return jsonify({
                    'success': False,
                    'message': '缺少期间参数'
                })

            # 执行反结账
            result = reverse_period_closing(_query_db, _execute_db, period, user_id, reason, get_db=_get_db)

            return jsonify(result)

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'反结账失败: {str(e)}'
            })


    @app.route('/finance/period-closing/history')
    @login_required_decorator
    def closing_history():
        """结账历史页面"""
        try:
            # 获取最近12个月的结账历史
            history = get_closing_history(_query_db, limit=12)

            return render_template(
                'finance/period_closing_history.html',
                history=history
            )

        except Exception as e:
            return render_template(
                'finance/period_closing_history.html',
                error=str(e),
                history=[]
            )


    @app.route('/finance/period-closing/api/check/<period>')
    @login_required_decorator
    def api_check_period(period):
        """API: 检查指定期间"""
        try:
            result = check_period_closing(_query_db, period)
            return jsonify(result)

        except Exception as e:
            return jsonify({
                'can_close': False,
                'issues': [{'check_item': '系统错误', 'result': '错误', 'reason': str(e)}],
                'warnings': [],
                'summary': {}
            })


    @app.route('/finance/period-closing/api/current-period')
    @login_required_decorator
    def api_current_period():
        """API: 获取当前期间"""
        try:
            current_period = get_current_period()
            latest_closed = get_latest_closed_period(_query_db)

            return jsonify({
                'current_period': current_period,
                'latest_closed': latest_closed
            })

        except Exception as e:
            return jsonify({
                'error': str(e)
            })
