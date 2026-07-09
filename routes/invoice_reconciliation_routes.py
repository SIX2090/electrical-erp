# -*- coding: utf-8 -*-
"""
发票勾稽报表路由
处理销售和采购发票的勾稽查询
"""
from flask import request, render_template
from services.invoice_reconciliation_service import (
    query_invoice_reconciliation,
    get_invoice_reconciliation_summary
)


def register_invoice_reconciliation_routes(app, query_db, _login_required):
    """
    注册发票勾稽报表路由

    Args:
        app: Flask应用实例
        query_db: 数据库查询函数
        _login_required: 登录验证装饰器
    """

    @app.route("/finance/reports/sales-invoice-reconciliation")
    @_login_required
    def sales_invoice_reconciliation_report():
        """
        销售发票勾稽报表
        """
        # 获取筛选条件
        filters = {
            'customer_id': request.args.get('customer_id'),
            'order_no': request.args.get('order_no'),
            'project_code': request.args.get('project_code'),
            'serial_no': request.args.get('serial_no'),
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'has_variance': request.args.get('has_variance', '0')
        }

        # 查询数据
        rows = query_invoice_reconciliation(query_db, 'sales', filters)

        # 获取汇总统计
        summary = get_invoice_reconciliation_summary(rows)

        # 获取客户列表（用于筛选下拉框）
        customers = query_db(
            "SELECT id, name FROM customers ORDER BY name"
        )

        return render_template(
            'finance/sales_invoice_reconciliation.html',
            rows=rows,
            summary=summary,
            filters=filters,
            customers=customers
        )

    @app.route("/finance/reports/purchase-invoice-reconciliation")
    @_login_required
    def purchase_invoice_reconciliation_report():
        """
        采购发票勾稽报表
        """
        # 获取筛选条件
        filters = {
            'supplier_id': request.args.get('supplier_id'),
            'order_no': request.args.get('order_no'),
            'project_code': request.args.get('project_code'),
            'serial_no': request.args.get('serial_no'),
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'has_variance': request.args.get('has_variance', '0')
        }

        # 查询数据
        rows = query_invoice_reconciliation(query_db, 'purchase', filters)

        # 获取汇总统计
        summary = get_invoice_reconciliation_summary(rows)

        # 获取供应商列表（用于筛选下拉框）
        suppliers = query_db(
            "SELECT id, name FROM suppliers ORDER BY name"
        )

        return render_template(
            'finance/purchase_invoice_reconciliation.html',
            rows=rows,
            summary=summary,
            filters=filters,
            suppliers=suppliers
        )
