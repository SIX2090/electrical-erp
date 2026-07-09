# -*- coding: utf-8 -*-
"""
机号成本报表路由
处理机号成本查询、分析和差异报表

路由列表：
- GET /finance/serial-cost/detail - 机号成本明细报表
- GET /finance/serial-cost/summary - 机号成本汇总报表
- GET /finance/serial-cost/variance - 机号成本差异分析报表
- POST /finance/serial-cost/record - 记录机号成本（AJAX）
- GET /finance/serial-cost/types - 获取成本类型列表（AJAX）
- GET /finance/serial-cost/calculate-variance/<serial_no> - 计算机号成本差异（AJAX）
"""
from flask import request, render_template, jsonify, session
from services.data_scope_service import get_data_scope, scope_has_rules, row_allowed
from services.serial_cost_service import (
    record_serial_cost,
    calculate_serial_total_cost,
    calculate_bom_standard_cost,
    calculate_cost_variance,
    query_serial_cost_detail,
    query_serial_cost_summary,
    query_serial_cost_variance,
    get_serial_cost_types
)
from datetime import datetime


def register_serial_cost_routes(app, query_db, execute_db, _login_required):
    """
    注册机号成本报表路由

    Args:
        app: Flask应用实例
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        _login_required: 登录验证装饰器
    """

    _SERIAL_SCOPE_FIELD_MAP = {"project": "project_code", "serial": "serial_no"}

    def _current_serial_scope():
        try:
            return get_data_scope(query_db, user_id=session.get("user_id"), role=session.get("role", "staff"), permission="view")
        except Exception:
            return {"bypass": False, "rules": {}, "permission": "view"}

    def _filter_rows_by_scope(rows):
        scope = _current_serial_scope()
        if not scope_has_rules(scope):
            return rows
        return [row for row in rows if row_allowed(scope, row, _SERIAL_SCOPE_FIELD_MAP)]

    @app.route("/finance/serial-cost/detail")
    @_login_required
    def serial_cost_detail_report():
        """
        机号成本明细报表
        """
        # 获取筛选条件
        filters = {
            'serial_no': request.args.get('serial_no'),
            'project_code': request.args.get('project_code'),
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'cost_type': request.args.get('cost_type'),
            'source_type': request.args.get('source_type')
        }

        # 查询成本明细
        rows = query_serial_cost_detail(query_db, filters)

        # 数据权限过滤
        rows = _filter_rows_by_scope(rows)

        # 计算合计
        total_amount = sum(float(row.get('cost_amount', 0)) for row in rows)

        # 如果指定了机号，计算该机号的成本汇总
        serial_summary = None
        if filters.get('serial_no'):
            cost_result = calculate_serial_total_cost(
                query_db,
                filters['serial_no'],
                filters.get('start_date'),
                filters.get('end_date')
            )
            serial_summary = cost_result

        # 获取机号列表（用于筛选下拉框）
        serial_nos = query_db(
            """
            SELECT DISTINCT serial_no, project_code
            FROM serial_cost_ledger
            WHERE serial_no IS NOT NULL
            ORDER BY serial_no DESC
            LIMIT 200
            """
        )

        # 获取成本类型列表
        cost_types = get_serial_cost_types(query_db)

        # 获取来源类型列表
        source_types = query_db(
            """
            SELECT DISTINCT source_type
            FROM serial_cost_ledger
            WHERE source_type IS NOT NULL
            ORDER BY source_type
            """
        )

        return render_template(
            'finance/serial_cost_detail.html',
            rows=rows,
            total_amount=total_amount,
            serial_summary=serial_summary,
            filters=filters,
            serial_nos=serial_nos,
            cost_types=cost_types,
            source_types=source_types
        )

    @app.route("/finance/serial-cost/summary")
    @_login_required
    def serial_cost_summary_report():
        """
        机号成本汇总报表
        """
        # 获取筛选条件
        filters = {
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'project_code': request.args.get('project_code'),
            'serial_nos': request.args.getlist('serial_nos[]') if request.args.getlist('serial_nos[]') else None
        }

        # 查询成本汇总
        rows = query_serial_cost_summary(query_db, filters)

        # 数据权限过滤
        rows = _filter_rows_by_scope(rows)

        # 计算总计
        total_material = sum(float(row.get('material_cost', 0)) for row in rows)
        total_purchase = sum(float(row.get('purchase_cost', 0)) for row in rows)
        total_outsource = sum(float(row.get('outsource_cost', 0)) for row in rows)
        total_labor = sum(float(row.get('labor_cost', 0)) for row in rows)
        total_other = sum(float(row.get('other_cost', 0)) for row in rows)
        grand_total = sum(float(row.get('total_cost', 0)) for row in rows)

        totals = {
            'material_cost': total_material,
            'purchase_cost': total_purchase,
            'outsource_cost': total_outsource,
            'labor_cost': total_labor,
            'other_cost': total_other,
            'total_cost': grand_total
        }

        # 获取所有机号列表
        all_serial_nos = query_db(
            """
            SELECT DISTINCT serial_no, project_code
            FROM serial_cost_ledger
            WHERE serial_no IS NOT NULL
            ORDER BY serial_no DESC
            LIMIT 300
            """
        )

        # 获取项目列表
        projects = query_db(
            """
            SELECT DISTINCT project_code
            FROM serial_cost_ledger
            WHERE project_code IS NOT NULL
            ORDER BY project_code DESC
            """
        )

        return render_template(
            'finance/serial_cost_summary.html',
            rows=rows,
            totals=totals,
            filters=filters,
            all_serial_nos=all_serial_nos,
            projects=projects
        )

    @app.route("/finance/serial-cost/variance")
    @_login_required
    def serial_cost_variance_report():
        """
        机号成本差异分析报表
        """
        # 获取筛选条件
        filters = {
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'project_code': request.args.get('project_code'),
            'serial_nos': request.args.getlist('serial_nos[]') if request.args.getlist('serial_nos[]') else None
        }

        # 查询成本差异
        rows = query_serial_cost_variance(query_db, filters)

        # 数据权限过滤
        rows = _filter_rows_by_scope(rows)

        # 计算总计
        total_standard = sum(float(row.get('standard_cost', 0)) for row in rows)
        total_actual = sum(float(row.get('actual_cost', 0)) for row in rows)
        total_variance = total_actual - total_standard
        total_variance_rate = (total_variance / total_standard * 100) if total_standard > 0 else 0

        # 统计差异类型数量
        overrun_count = sum(1 for row in rows if row.get('variance_type') == '超支')
        saving_count = sum(1 for row in rows if row.get('variance_type') == '节约')
        balanced_count = sum(1 for row in rows if row.get('variance_type') == '无差异')

        totals = {
            'standard_cost': total_standard,
            'actual_cost': total_actual,
            'variance': total_variance,
            'variance_rate': total_variance_rate
        }

        statistics = {
            'overrun_count': overrun_count,
            'saving_count': saving_count,
            'balanced_count': balanced_count,
            'total_count': len(rows)
        }

        # 获取所有机号列表
        all_serial_nos = query_db(
            """
            SELECT DISTINCT serial_no, project_code
            FROM serial_cost_ledger
            WHERE serial_no IS NOT NULL
            ORDER BY serial_no DESC
            LIMIT 300
            """
        )

        # 获取项目列表
        projects = query_db(
            """
            SELECT DISTINCT project_code
            FROM serial_cost_ledger
            WHERE project_code IS NOT NULL
            ORDER BY project_code DESC
            """
        )

        return render_template(
            'finance/serial_cost_variance.html',
            rows=rows,
            totals=totals,
            statistics=statistics,
            filters=filters,
            all_serial_nos=all_serial_nos,
            projects=projects
        )

    @app.route("/finance/serial-cost/record", methods=["POST"])
    @_login_required
    def record_serial_cost_entry():
        """
        记录机号成本（AJAX接口）
        """
        from flask import session
        current_user_id = session.get('user_id')

        try:
            data = request.get_json()

            cost_data = {
                'serial_no': data.get('serial_no'),
                'product_id': data.get('product_id'),
                'project_code': data.get('project_code'),
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

            result = record_serial_cost(query_db, execute_db, cost_data)

            return jsonify(result)

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'记录失败: {str(e)}'
            }), 400

    @app.route("/finance/serial-cost/types")
    @_login_required
    def get_serial_cost_types_api():
        """
        获取成本类型列表（AJAX接口）
        """
        try:
            types = get_serial_cost_types(query_db)
            return jsonify({
                'success': True,
                'types': types
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'获取失败: {str(e)}'
            }), 400

    @app.route("/finance/serial-cost/calculate-variance/<serial_no>")
    @_login_required
    def calculate_serial_variance_api(serial_no):
        """
        计算机号成本差异（AJAX接口）
        """
        try:
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            variance = calculate_cost_variance(query_db, serial_no, start_date, end_date)

            return jsonify({
                'success': True,
                'data': {
                    'standard_cost': float(variance['standard_cost']),
                    'actual_cost': float(variance['actual_cost']),
                    'variance': float(variance['variance']),
                    'variance_rate': float(variance['variance_rate']),
                    'variance_type': variance['variance_type']
                }
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'计算失败: {str(e)}'
            }), 400
