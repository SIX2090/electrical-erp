# -*- coding: utf-8 -*-
"""
项目成本报表路由
处理项目成本查询和分析报表

路由列表：
- GET /finance/project-cost/detail - 项目成本明细报表
- GET /finance/project-cost/summary - 项目成本汇总报表
- GET /finance/project-cost/gross-profit - 项目毛利分析报表
- POST /finance/project-cost/record - 记录项目成本（AJAX）
- POST /finance/project-cost/record-revenue - 记录项目收入（AJAX）
- GET /finance/project-cost/types - 获取成本类型列表（AJAX）
"""
from flask import request, render_template, jsonify, session
from services.data_scope_service import get_data_scope, scope_has_rules, row_allowed
from services.project_cost_service import (
    record_project_cost,
    record_project_revenue,
    calculate_project_total_cost,
    calculate_project_gross_profit,
    query_project_cost_detail,
    query_project_cost_summary,
    query_project_gross_profit_analysis,
    get_project_cost_types
)
from datetime import datetime


def register_project_cost_routes(app, query_db, execute_db, _login_required):
    """
    注册项目成本报表路由

    Args:
        app: Flask应用实例
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        _login_required: 登录验证装饰器
    """

    _PROJECT_SCOPE_FIELD_MAP = {"project": "project_code", "serial": "serial_no"}

    def _current_project_scope():
        try:
            return get_data_scope(query_db, user_id=session.get("user_id"), role=session.get("role", "staff"), permission="view")
        except Exception:
            return {"bypass": False, "rules": {}, "permission": "view"}

    def _filter_rows_by_scope(rows):
        scope = _current_project_scope()
        if not scope_has_rules(scope):
            return rows
        return [row for row in rows if row_allowed(scope, row, _PROJECT_SCOPE_FIELD_MAP)]

    # B-001: /finance/project-cost/detail is intentionally NOT registered here.
    # project_cost_routes.py:535 already serves that path with endpoint
    # "finance_project_cost_detail". Registering it here too would override
    # the active handler. Original handler body preserved below for reference.
    #
    # @app.route("/finance/project-cost/detail")
    # @_login_required
    # def project_cost_detail_report():
    #     ... (see git history for the original body)

    @app.route("/finance/project-cost/summary")
    @_login_required
    def project_cost_summary_report():
        """
        项目成本汇总报表
        """
        # 获取筛选条件
        filters = {
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'project_codes': request.args.getlist('project_codes[]') if request.args.getlist('project_codes[]') else None
        }

        # 查询成本汇总
        rows = query_project_cost_summary(query_db, filters)

        # 数据权限过滤
        rows = _filter_rows_by_scope(rows)

        # 计算总计
        total_material = sum(float(row.get('material_cost', 0)) for row in rows)
        total_labor = sum(float(row.get('labor_cost', 0)) for row in rows)
        total_outsource = sum(float(row.get('outsource_cost', 0)) for row in rows)
        total_transport = sum(float(row.get('transport_cost', 0)) for row in rows)
        total_other = sum(float(row.get('other_cost', 0)) for row in rows)
        grand_total = sum(float(row.get('total_cost', 0)) for row in rows)

        totals = {
            'material_cost': total_material,
            'labor_cost': total_labor,
            'outsource_cost': total_outsource,
            'transport_cost': total_transport,
            'other_cost': total_other,
            'total_cost': grand_total
        }

        # 获取所有项目列表
        all_projects = query_db(
            """
            SELECT DISTINCT project_code, project_name
            FROM project_cost_ledger
            WHERE project_code IS NOT NULL
            ORDER BY project_code DESC
            LIMIT 200
            """
        )

        return render_template(
            'finance/project_cost_summary.html',
            rows=rows,
            totals=totals,
            filters=filters,
            all_projects=all_projects
        )

    @app.route("/finance/project-cost/gross-profit")
    @_login_required
    def project_gross_profit_report():
        """
        项目毛利分析报表
        """
        # 获取筛选条件
        filters = {
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'project_codes': request.args.getlist('project_codes[]') if request.args.getlist('project_codes[]') else None
        }

        # 查询毛利分析
        rows = query_project_gross_profit_analysis(query_db, filters)

        # 数据权限过滤
        rows = _filter_rows_by_scope(rows)

        # 计算总计
        total_revenue = sum(float(row.get('revenue', 0)) for row in rows)
        total_cost = sum(float(row.get('cost', 0)) for row in rows)
        total_gross_profit = total_revenue - total_cost
        total_gross_margin = (total_gross_profit / total_revenue * 100) if total_revenue > 0 else 0

        totals = {
            'revenue': total_revenue,
            'cost': total_cost,
            'gross_profit': total_gross_profit,
            'gross_margin': total_gross_margin
        }

        # 获取所有项目列表
        all_projects = query_db(
            """
            SELECT DISTINCT project_code, MAX(project_name) AS project_name
            FROM project_cost_ledger
            WHERE project_code IS NOT NULL
            GROUP BY project_code
            ORDER BY project_code DESC
            LIMIT 200
            """
        )

        return render_template(
            'finance/project_gross_profit.html',
            rows=rows,
            totals=totals,
            filters=filters,
            all_projects=all_projects
        )

    @app.route("/finance/project-cost/record", methods=["POST"])
    @_login_required
    def record_project_cost_entry():
        """
        记录项目成本（AJAX接口）
        """
        from flask import session
        current_user_id = session.get('user_id')

        try:
            data = request.get_json()

            cost_data = {
                'project_code': data.get('project_code'),
                'project_name': data.get('project_name'),
                'cost_date': data.get('cost_date'),
                'cost_type': data.get('cost_type'),
                'source_type': data.get('source_type'),
                'source_no': data.get('source_no'),
                'description': data.get('description'),
                'cost_amount': data.get('cost_amount'),
                'quantity': data.get('quantity'),
                'unit_cost': data.get('unit_cost'),
                'department_id': data.get('department_id'),
                'employee_id': data.get('employee_id'),
                'recorded_by': current_user_id,
                'remark': data.get('remark')
            }

            result = record_project_cost(query_db, execute_db, cost_data)

            return jsonify(result)

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'记录失败: {str(e)}'
            }), 400

    @app.route("/finance/project-cost/record-revenue", methods=["POST"])
    @_login_required
    def record_project_revenue_entry():
        """
        记录项目收入（AJAX接口）
        """
        from flask import session
        current_user_id = session.get('user_id')

        try:
            data = request.get_json()

            revenue_data = {
                'project_code': data.get('project_code'),
                'revenue_date': data.get('revenue_date'),
                'revenue_type': data.get('revenue_type'),
                'source_type': data.get('source_type'),
                'source_no': data.get('source_no'),
                'customer_id': data.get('customer_id'),
                'revenue_amount': data.get('revenue_amount'),
                'cost_amount': data.get('cost_amount'),
                'recorded_by': current_user_id,
                'remark': data.get('remark')
            }

            result = record_project_revenue(query_db, execute_db, revenue_data)

            return jsonify(result)

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'记录失败: {str(e)}'
            }), 400

    @app.route("/finance/project-cost/types")
    @_login_required
    def get_project_cost_types_api():
        """
        获取成本类型列表（AJAX接口）
        """
        try:
            types = get_project_cost_types(query_db)
            return jsonify({
                'success': True,
                'types': types
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'获取失败: {str(e)}'
            }), 400
