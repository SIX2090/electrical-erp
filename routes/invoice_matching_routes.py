# -*- coding: utf-8 -*-
"""
发票三单匹配报表路由
"""

from flask import render_template, request
from services.invoice_matching_service import (
    query_sales_three_way_match,
    query_purchase_three_way_match,
    query_uninvoiced_sales,
    query_unreceived_purchase_invoice,
)


def register_invoice_matching_routes(app, query_db, _login_required):
    """
    注册发票三单匹配报表路由
    """

    @app.route("/finance/reports/sales-three-way-match")
    @_login_required
    def sales_three_way_match_report():
        """销售三单匹配报表（订单-发货-发票）"""
        filters = {
            "customer_id": request.args.get("customer_id"),
            "order_no": request.args.get("order_no"),
            "project_code": request.args.get("project_code"),
            "cabinet_no": request.args.get("cabinet_no"),
            "start_date": request.args.get("start_date"),
            "end_date": request.args.get("end_date"),
            "match_status": request.args.get("match_status"),
        }
        # 移除空值
        filters = {k: v for k, v in filters.items() if v}

        rows = query_sales_three_way_match(query_db, filters)

        # 获取客户列表用于筛选
        customers = query_db("SELECT id, name FROM customers ORDER BY name")

        return render_template(
            "finance/sales_three_way_match.html",
            rows=rows,
            filters=filters,
            customers=customers,
            page_title="销售三单匹配报表",
        )

    @app.route("/finance/reports/purchase-three-way-match")
    @_login_required
    def purchase_three_way_match_report():
        """采购三单匹配报表（订单-入库-发票）"""
        filters = {
            "supplier_id": request.args.get("supplier_id"),
            "order_no": request.args.get("order_no"),
            "project_code": request.args.get("project_code"),
            "cabinet_no": request.args.get("cabinet_no"),
            "start_date": request.args.get("start_date"),
            "end_date": request.args.get("end_date"),
            "match_status": request.args.get("match_status"),
        }
        filters = {k: v for k, v in filters.items() if v}

        rows = query_purchase_three_way_match(query_db, filters)

        # 获取供应商列表用于筛选
        suppliers = query_db("SELECT id, name FROM suppliers ORDER BY name")

        return render_template(
            "finance/purchase_three_way_match.html",
            rows=rows,
            filters=filters,
            suppliers=suppliers,
            page_title="采购三单匹配报表",
        )

    @app.route("/finance/reports/uninvoiced-sales")
    @_login_required
    def uninvoiced_sales_report():
        """未开票销售明细表"""
        filters = {
            "customer_id": request.args.get("customer_id"),
            "order_no": request.args.get("order_no"),
            "project_code": request.args.get("project_code"),
            "cabinet_no": request.args.get("cabinet_no"),
            "start_date": request.args.get("start_date"),
            "end_date": request.args.get("end_date"),
        }
        filters = {k: v for k, v in filters.items() if v}

        rows = query_uninvoiced_sales(query_db, filters)

        customers = query_db("SELECT id, name FROM customers ORDER BY name")

        # 计算未开票总额
        total_uninvoiced_amount = sum(float(r.get("uninvoiced_amount") or 0) for r in rows)

        return render_template(
            "finance/uninvoiced_sales.html",
            rows=rows,
            filters=filters,
            customers=customers,
            total_uninvoiced_amount=total_uninvoiced_amount,
            page_title="未开票销售明细",
        )

    @app.route("/finance/reports/unreceived-purchase-invoice")
    @_login_required
    def unreceived_purchase_invoice_report():
        """未到票采购明细表"""
        filters = {
            "supplier_id": request.args.get("supplier_id"),
            "order_no": request.args.get("order_no"),
            "project_code": request.args.get("project_code"),
            "cabinet_no": request.args.get("cabinet_no"),
            "start_date": request.args.get("start_date"),
            "end_date": request.args.get("end_date"),
        }
        filters = {k: v for k, v in filters.items() if v}

        rows = query_unreceived_purchase_invoice(query_db, filters)

        suppliers = query_db("SELECT id, name FROM suppliers ORDER BY name")

        # 计算未到票总额
        total_unreceived_amount = sum(float(r.get("unreceived_invoice_amount") or 0) for r in rows)

        return render_template(
            "finance/unreceived_purchase_invoice.html",
            rows=rows,
            filters=filters,
            suppliers=suppliers,
            total_unreceived_amount=total_unreceived_amount,
            page_title="未到票采购明细",
        )
