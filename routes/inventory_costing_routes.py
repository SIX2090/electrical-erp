# -*- coding: utf-8 -*-
"""
存货核算路由
处理存货成本核算相关请求

路由列表：
- GET /finance/inventory-costing - 存货核算首页
- GET /finance/inventory-costing/cost-ledger - 存货成本明细账
- POST /finance/inventory-costing/calculate-receipt - 核算入库成本
- POST /finance/inventory-costing/calculate-issue - 核算出库成本
- POST /finance/inventory-costing/generate-voucher - 生成成本凭证
- GET /finance/inventory-costing/reconciliation - 存货与总账对账
"""
from flask import request, render_template, jsonify, flash, redirect
from services.inventory_costing_service import (
    cost_inventory_receipt,
    cost_inventory_issue,
    generate_costing_voucher,
    query_inventory_cost_ledger,
    query_inventory_ledger_reconciliation
)
from datetime import datetime


def register_inventory_costing_routes(app, query_db, execute_db, _login_required):
    """
    注册存货核算路由

    Args:
        app: Flask应用实例
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        _login_required: 登录验证装饰器
    """

    @app.route("/finance/inventory-costing")
    @_login_required
    def inventory_costing_home():
        """
        存货核算首页
        """
        # 统计待核算单据数量
        pending_receipts = query_db(
            """
            SELECT COUNT(*) as cnt
            FROM inventory_transactions
            WHERE transaction_type IN ('采购入库', '完工入库', '其他入库')
              AND unit_cost = 0
            """
        )

        pending_issues = query_db(
            """
            SELECT COUNT(*) as cnt
            FROM inventory_transactions
            WHERE transaction_type IN ('销售出库', '生产领料', '其他出库')
              AND unit_cost = 0
            """
        )

        # 获取最近核算记录
        recent_costings = query_db(
            """
            SELECT
                ic.*,
                p.code AS product_code,
                p.name AS product_name,
                COALESCE(ic.unit_cost, 0) AS avg_cost
            FROM inventory_costing ic
            LEFT JOIN products p ON ic.product_id = p.id
            ORDER BY ic.costing_date DESC, ic.created_at DESC
            LIMIT 20
            """
        )

        # 获取成本差异较大的产品
        cost_variance_products = query_db(
            """
            SELECT
                p.code,
                p.name,
                COALESCE(SUM(ib.quantity), 0) AS quantity,
                COALESCE(AVG(NULLIF(ib.unit_cost, 0)), 0) AS current_cost,
                COALESCE(p.standard_price, 0) AS last_purchase_cost,
                COALESCE(AVG(NULLIF(ib.unit_cost, 0)), 0) - COALESCE(p.standard_price, 0) AS variance
            FROM products p
            JOIN inventory_balances ib ON ib.product_id = p.id
            GROUP BY p.id, p.code, p.name, p.standard_price
            HAVING ABS(COALESCE(AVG(NULLIF(ib.unit_cost, 0)), 0) - COALESCE(p.standard_price, 0)) > 10
            ORDER BY ABS(COALESCE(AVG(NULLIF(ib.unit_cost, 0)), 0) - COALESCE(p.standard_price, 0)) DESC
            LIMIT 10
            """
        )

        return render_template(
            'finance/inventory_costing_home.html',
            pending_receipts_count=pending_receipts[0]['cnt'] if pending_receipts else 0,
            pending_issues_count=pending_issues[0]['cnt'] if pending_issues else 0,
            recent_costings=recent_costings,
            cost_variance_products=cost_variance_products
        )

    @app.route("/finance/inventory-costing/cost-ledger")
    @_login_required
    def inventory_cost_ledger():
        """
        存货成本明细账
        """
        # 获取筛选条件
        filters = {
            'product_id': request.args.get('product_id'),
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'project_code': request.args.get('project_code'),
            'cabinet_no': request.args.get('cabinet_no'),
            'transaction_type': request.args.get('transaction_type')
        }

        # 查询成本明细
        rows = []
        product = None

        if filters.get('product_id'):
            rows = query_inventory_cost_ledger(query_db, filters)

            # 获取产品信息
            product = query_db(
                """
                SELECT
                    id,
                    code,
                    name,
                    unit,
                    quantity,
                    current_cost,
                    quantity * current_cost AS total_amount
                FROM products
                WHERE id = %s
                """,
                (filters['product_id'],),
                one=True
            )

        # 获取产品列表（用于筛选下拉框）
        products = query_db(
            """
            SELECT p.id, p.code, p.name
            FROM products p
            LEFT JOIN inventory_balances ib ON ib.product_id = p.id
            GROUP BY p.id, p.code, p.name, p.standard_price
            HAVING COALESCE(SUM(ib.quantity), 0) > 0 OR COALESCE(p.standard_price, 0) > 0
            ORDER BY p.code
            LIMIT 200
            """
        )

        return render_template(
            'finance/inventory_cost_ledger.html',
            rows=rows,
            product=product,
            filters=filters,
            products=products
        )

    @app.route("/finance/inventory-costing/calculate-receipt", methods=["POST"])
    @_login_required
    def calculate_receipt_cost():
        """
        核算入库成本（AJAX接口）
        """
        from flask import session
        current_user_id = session.get('user_id')

        try:
            data = request.get_json(silent=True) or {}

            receipt_data = {
                'costing_date': data.get('costing_date'),
                'product_id': data.get('product_id'),
                'transaction_type': data.get('transaction_type'),
                'transaction_id': data.get('transaction_id'),
                'transaction_no': data.get('transaction_no'),
                'quantity': data.get('quantity'),
                'unit_cost': data.get('unit_cost'),
                'project_code': data.get('project_code'),
                'cabinet_no': data.get('cabinet_no'),
                'warehouse_id': data.get('warehouse_id'),
                'costed_by': current_user_id,
                'remark': data.get('remark')
            }

            result = cost_inventory_receipt(query_db, execute_db, receipt_data)

            return jsonify(result)

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'核算失败: {str(e)}'
            }), 400

    @app.route("/finance/inventory-costing/calculate-issue", methods=["POST"])
    @_login_required
    def calculate_issue_cost():
        """
        核算出库成本（AJAX接口）
        """
        from flask import session
        current_user_id = session.get('user_id')

        try:
            data = request.get_json(silent=True) or {}

            issue_data = {
                'costing_date': data.get('costing_date'),
                'product_id': data.get('product_id'),
                'transaction_type': data.get('transaction_type'),
                'transaction_id': data.get('transaction_id'),
                'transaction_no': data.get('transaction_no'),
                'quantity': data.get('quantity'),
                'project_code': data.get('project_code'),
                'cabinet_no': data.get('cabinet_no'),
                'warehouse_id': data.get('warehouse_id'),
                'costed_by': current_user_id,
                'remark': data.get('remark')
            }

            result = cost_inventory_issue(query_db, execute_db, issue_data)

            return jsonify(result)

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'核算失败: {str(e)}'
            }), 400

    @app.route("/finance/inventory-costing/generate-voucher/<int:costing_id>", methods=["POST"])
    @_login_required
    def generate_cost_voucher(costing_id):
        """
        生成成本凭证
        """
        from flask import session
        current_user_id = session.get('user_id')

        result = generate_costing_voucher(query_db, execute_db, costing_id, current_user_id)

        if result['success']:
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'danger')

        return redirect(request.referrer or '/finance/inventory-costing')

    @app.route("/finance/inventory-costing/reconciliation")
    @_login_required
    def inventory_ledger_reconciliation():
        """
        存货与总账对账
        """
        # 查询对账结果
        reconciliation = query_inventory_ledger_reconciliation(query_db)

        return render_template(
            'finance/inventory_ledger_reconciliation.html',
            reconciliation=reconciliation
        )
