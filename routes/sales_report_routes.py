"""
销售报表路由
实现销售模块核心报表的 HTTP 端点
"""
from flask import Blueprint, request, render_template, jsonify, session
from routes.report_routes import REPORT_SECTIONS
from services.data_scope_service import get_data_scope, scope_has_rules, row_allowed
from services.sales_analysis_report_service import get_sales_analysis_report
from services.sales_invoice_report_service import build_sales_invoice_report
from services.sales_receivable_report_service import (
    query_customer_ranking,
    query_receivable_collection_detail,
)
from services.sales_shipment_report_service import build_sales_shipment_report, query_shipment_execution_detail
from services.sales_report_service import (
    query_sales_order_execution_detail,
    query_receivable_aging_analysis,
    query_project_serial_sales_tracking,
    query_shipped_unsettled_detail,
)
from services.sales_order_report_service import (
    query_customer_open_order_analysis,
    query_order_execution_summary,
    query_project_serial_open_order_analysis,
    query_sales_summary,
)


REAL_SALES_REPORT_PATHS = {
    "/sales/reports",
    "/sales/reports/pending",
    "/sales/reports/customer-ranking",
    "/sales/reports/execution",
    "/sales/reports/summary",
    "/sales/reports/order-execution-summary",
    "/sales/reports/order-execution-detail",
    "/sales/reports/customer-open-order-analysis",
    "/sales/reports/project-serial-open-order-analysis",
    "/sales/reports/project-serial-order-tracking",
    "/sales/reports/shipment-execution-detail",
    "/sales/reports/shipped-goods-detail",
    "/sales/reports/shipped-goods-summary",
    "/sales/reports/shipped-unsettled-detail",
    "/sales/reports/invoice-execution-detail",
    "/sales/reports/invoice-summary",
    "/sales/reports/receivable-collection-detail",
    "/sales/reports/receivable-aging",
    "/sales/reports/project-serial-gross-margin",
    "/sales/reports/price-execution-analysis",
    "/sales/reports/delivery-delay-analysis",
    "/sales/reports/operation-snapshot",
    "/sales/reports/daily",
}


def register_sales_report_routes(app, deps):
    """注册销售报表路由"""

    query_db = deps['query_db']
    login_required = deps['login_required']
    role_required = deps.get('role_required')
    sales_report_required = role_required("admin", "manager", "sales", "finance") if role_required else (lambda func: func)

    def _current_sales_scope():
        """获取当前用户的数据权限范围"""
        try:
            return get_data_scope(query_db, user_id=session.get("user_id"), role=session.get("role", "staff"), permission="view")
        except Exception:
            return {"bypass": False, "rules": {}, "permission": "view"}

    def _scope_allows_row(row, field_map):
        """检查行数据是否在用户的数据权限范围内"""
        scope = _current_sales_scope()
        if not scope_has_rules(scope):
            return True
        return row_allowed(scope, row, field_map)

    def _apply_scope_to_report(report_data, field_map, count_keys=None, amount_keys=None):
        """对报表数据进行数据权限过滤，并重算 summary 中的 count/amount 字段。

        field_map: {"project": "project_code", "serial": "serial_no", "customer": "customer_id"}
        count_keys: summary 中需要按 len(rows) 重算的键，如 ["order_count"]
        amount_keys: summary 中需要按 sum(rows[field]) 重算的键，如 [("total_order_amount", "order_amount")]
        """
        scope = _current_sales_scope()
        if not scope_has_rules(scope):
            return report_data
        rows = report_data.get("rows") or []
        filtered_rows = [row for row in rows if row_allowed(scope, row, field_map)]
        report_data["rows"] = filtered_rows
        summary = report_data.get("summary")
        if isinstance(summary, dict):
            if count_keys:
                for key in count_keys:
                    if key in summary:
                        summary[key] = len(filtered_rows)
            if amount_keys:
                for summary_key, row_key in amount_keys:
                    if summary_key in summary:
                        total = sum(float(row.get(row_key) or 0) for row in filtered_rows)
                        if isinstance(summary[summary_key], str):
                            summary[summary_key] = f"{total:,.2f}"
                        else:
                            summary[summary_key] = total
        return report_data

    def _order_report_filters():
        return {
            'date_start': request.args.get('date_start'),
            'date_end': request.args.get('date_end'),
            'customer_name': request.args.get('customer_name'),
            'project_code': request.args.get('project_code'),
            'serial_no': request.args.get('serial_no'),
            'status': request.args.get('status'),
            'group_by': request.args.get('group_by'),
        }

    def _render_order_report(report_data, show_group_by=False):
        return render_template(
            'reports/sales_order_reports.html',
            title=report_data['title'],
            filters=report_data['filters'],
            summary=report_data['summary'],
            columns=report_data['columns'],
            rows=report_data['rows'],
            show_group_by=show_group_by,
        )

    def _render_receivable_report(report_data, title, basis_note):
        return render_template(
            'reports/sales_receivable_reports.html',
            title=title,
            basis_note=basis_note,
            filters=report_data['filters'],
            summary=report_data['summary'],
            columns=report_data['columns'],
            rows=report_data['rows'],
        )

    @app.route('/sales/reports')
    @login_required
    @sales_report_required
    def sales_reports_center():
        sections = [
            {"url": url, "title": title}
            for url, title, _words in REPORT_SECTIONS["sales"]["sections"]
            if url in REAL_SALES_REPORT_PATHS
        ]
        reports = [
            {
                "title": "销售报表",
                "subtitle": " / ".join(section["title"] for section in sections),
                "url": "/sales/reports",
                "tags": [section["title"] for section in sections],
                "sections": sections,
            }
        ]
        return render_template('report_center.html', reports=reports)

    _SALES_SCOPE_FIELD_MAP = {"project": "project_code", "serial": "serial_no", "customer": "customer_id"}

    @app.route('/sales/reports/pending')
    @login_required
    @sales_report_required
    def sales_pending_report():
        report_data = query_customer_open_order_analysis(query_db, _order_report_filters())
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_order_report(report_data)

    @app.route('/sales/reports/customer-ranking')
    @login_required
    @sales_report_required
    def sales_customer_ranking_report():
        report_data = query_customer_ranking(query_db, request.args)
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_receivable_report(
            report_data,
            '客户未交排行',
            '只读客户风险排行，按未交付金额、未收余额和逾期状态汇总。',
        )

    @app.route('/sales/reports/execution')
    @login_required
    @sales_report_required
    def sales_execution_report():
        report_data = query_order_execution_summary(query_db, _order_report_filters())
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_order_report(report_data)

    @app.route('/sales/reports/summary')
    @login_required
    @sales_report_required
    def sales_summary_report():
        report_data = query_sales_summary(query_db, _order_report_filters())
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_order_report(report_data, show_group_by=True)

    @app.route('/sales/reports/order-execution-summary')
    @login_required
    @sales_report_required
    def sales_order_execution_summary_report():
        report_data = query_order_execution_summary(query_db, _order_report_filters())
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_order_report(report_data)

    @app.route('/sales/reports/customer-open-order-analysis')
    @login_required
    @sales_report_required
    def customer_open_order_analysis_report():
        report_data = query_customer_open_order_analysis(query_db, _order_report_filters())
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_order_report(report_data)

    @app.route('/sales/reports/project-serial-open-order-analysis')
    @login_required
    @sales_report_required
    def project_serial_open_order_analysis_report():
        report_data = query_project_serial_open_order_analysis(query_db, _order_report_filters())
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_order_report(report_data)

    @app.route('/sales/reports/shipment-execution-detail')
    @login_required
    @sales_report_required
    def sales_shipment_execution_detail_report():
        report_data = query_shipment_execution_detail(query_db, request.args)
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return render_template(
            'reports/sales_shipment_reports.html',
            title='销售发货执行明细',
            report=report_data,
        )

    @app.route('/sales/reports/shipped-goods-detail')
    @login_required
    @sales_report_required
    def sales_shipped_goods_detail_report():
        report_data = build_sales_shipment_report(query_db, 'shipped_goods_detail', request.args)
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return render_template(
            'reports/sales_shipment_reports.html',
            title='发出商品明细',
            report=report_data,
        )

    @app.route('/sales/reports/shipped-goods-summary')
    @login_required
    @sales_report_required
    def sales_shipped_goods_summary_report():
        report_data = build_sales_shipment_report(query_db, 'shipped_goods_summary', request.args)
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return render_template(
            'reports/sales_shipment_reports.html',
            title='发出商品汇总',
            report=report_data,
        )

    @app.route('/sales/reports/invoice-execution-detail')
    @login_required
    @sales_report_required
    def sales_invoice_execution_detail_report():
        report_data = build_sales_invoice_report(query_db, 'invoice-execution-detail', request.args)
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return render_template(
            'reports/sales_invoice_reports.html',
            title=report_data['title'],
            report_key=report_data['report_key'],
            filters=report_data['filters'],
            summary=report_data['summary'],
            columns=report_data['columns'],
            rows=report_data['rows'],
        )

    @app.route('/sales/reports/invoice-summary')
    @login_required
    @sales_report_required
    def sales_invoice_summary_report():
        report_data = build_sales_invoice_report(query_db, 'invoice-summary', request.args)
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return render_template(
            'reports/sales_invoice_reports.html',
            title=report_data['title'],
            report_key=report_data['report_key'],
            filters=report_data['filters'],
            summary=report_data['summary'],
            columns=report_data['columns'],
            rows=report_data['rows'],
        )

    @app.route('/sales/reports/receivable-collection-detail')
    @login_required
    @sales_report_required
    def sales_receivable_collection_detail_report():
        report_data = query_receivable_collection_detail(query_db, request.args)
        _apply_scope_to_report(report_data, _SALES_SCOPE_FIELD_MAP)
        return _render_receivable_report(
            report_data,
            '销售收款执行明细',
            '只读收款执行明细，优先按收款核销关系展示；未核销收款按收款单记录展示。',
        )

    def _render_analysis_report(report_key):
        report = get_sales_analysis_report(query_db, report_key, request.args)
        _apply_scope_to_report(report, _SALES_SCOPE_FIELD_MAP)
        return render_template('reports/sales_analysis_reports.html', report=report)

    @app.route('/sales/reports/project-serial-gross-margin')
    @login_required
    @sales_report_required
    def sales_project_serial_gross_margin_report():
        return _render_analysis_report('project-serial-gross-margin')

    @app.route('/sales/reports/price-execution-analysis')
    @login_required
    @sales_report_required
    def sales_price_execution_analysis_report():
        return _render_analysis_report('price-execution-analysis')

    @app.route('/sales/reports/delivery-delay-analysis')
    @login_required
    @sales_report_required
    def sales_delivery_delay_analysis_report():
        return _render_analysis_report('delivery-delay-analysis')

    @app.route('/sales/reports/operation-snapshot')
    @login_required
    @sales_report_required
    def sales_operation_snapshot_report():
        return _render_analysis_report('operation-snapshot')

    @app.route('/sales/reports/daily')
    @login_required
    @sales_report_required
    def sales_daily_report():
        return _render_analysis_report('daily')

    @app.route('/sales/reports/order-execution-detail')
    @login_required
    @sales_report_required
    def sales_order_execution_detail_report():
        """销售订单执行明细报表"""

        # 获取筛选参数
        filters = {
            'date_start': request.args.get('date_start'),
            'date_end': request.args.get('date_end'),
            'customer_id': request.args.get('customer_id'),
            'customer_name': request.args.get('customer_name'),
            'project_code': request.args.get('project_code'),
            'serial_no': request.args.get('serial_no'),
            'status': request.args.get('status'),
        }

        # 查询数据
        rows = query_sales_order_execution_detail(query_db, filters)

        # 数据权限过滤
        scope = _current_sales_scope()
        if scope_has_rules(scope):
            rows = [row for row in rows if row_allowed(scope, row, _SALES_SCOPE_FIELD_MAP)]

        # 汇总统计
        total_order_amount = sum(float(row.get('order_amount', 0)) for row in rows)
        total_shipped_amount = sum(float(row.get('shipped_amount', 0)) for row in rows)
        total_unshipped_amount = sum(float(row.get('unshipped_amount', 0)) for row in rows)
        total_unreceived_amount = sum(float(row.get('unreceived_amount', 0)) for row in rows)

        summary = {
            'total_order_amount': f"{total_order_amount:,.2f}",
            'total_shipped_amount': f"{total_shipped_amount:,.2f}",
            'total_unshipped_amount': f"{total_unshipped_amount:,.2f}",
            'total_unreceived_amount': f"{total_unreceived_amount:,.2f}",
            'shipment_rate': f"{(total_shipped_amount / total_order_amount * 100):.1f}%" if total_order_amount > 0 else "0%",
            'order_count': len(rows),
        }

        # 列定义
        columns = [
            {'key': 'order_no', 'label': '订单号', 'url_key': 'order_url'},
            {'key': 'order_date', 'label': '订单日期'},
            {'key': 'customer_name', 'label': '客户'},
            {'key': 'project_code', 'label': '项目号'},
            {'key': 'serial_no', 'label': '机号'},
            {'key': 'order_amount', 'label': '订单金额', 'align': 'right', 'format': 'money'},
            {'key': 'shipped_amount', 'label': '已发货', 'align': 'right', 'format': 'money'},
            {'key': 'unshipped_amount', 'label': '未发货', 'align': 'right', 'format': 'money'},
            {'key': 'shipment_rate', 'label': '发货率'},
            {'key': 'invoiced_amount', 'label': '已开票', 'align': 'right', 'format': 'money'},
            {'key': 'received_amount', 'label': '已收款', 'align': 'right', 'format': 'money'},
            {'key': 'unreceived_amount', 'label': '待回款', 'align': 'right', 'format': 'money'},
            {'key': 'delivery_date', 'label': '交期'},
            {'key': 'overdue_days', 'label': '逾期天数'},
            {'key': 'status', 'label': '状态'},
        ]

        return render_template(
            'reports/sales_order_execution_detail.html',
            title='销售订单执行明细',
            rows=rows,
            columns=columns,
            summary=summary,
            filters=filters,
        )

    @app.route('/sales/reports/receivable-aging')
    @login_required
    @sales_report_required
    def receivable_aging_analysis_report():
        """销售应收账龄分析报表"""

        # 获取筛选参数
        filters = {
            'customer_id': request.args.get('customer_id'),
            'customer_name': request.args.get('customer_name'),
            'project_code': request.args.get('project_code'),
            'serial_no': request.args.get('serial_no'),
            'aging_range': request.args.get('aging_range'),
        }

        # 查询数据
        rows = query_receivable_aging_analysis(query_db, filters)

        # 数据权限过滤
        scope = _current_sales_scope()
        if scope_has_rules(scope):
            rows = [row for row in rows if row_allowed(scope, row, _SALES_SCOPE_FIELD_MAP)]

        # 按账龄区间汇总
        aging_summary = {
            '未到期': 0,
            '1-30天': 0,
            '31-60天': 0,
            '61-90天': 0,
            '91-180天': 0,
            '180天以上': 0,
        }

        total_balance = 0
        for row in rows:
            balance = float(row.get('balance', 0))
            aging_range = row.get('aging_range', '未到期')
            aging_summary[aging_range] = aging_summary.get(aging_range, 0) + balance
            total_balance += balance

        summary = {
            'total_balance': f"{total_balance:,.2f}",
            'aging_summary': aging_summary,
            'receivable_count': len(rows),
        }

        # 列定义
        columns = [
            {'key': 'receivable_no', 'label': '应收单号', 'url_key': 'receivable_url'},
            {'key': 'customer_name', 'label': '客户', 'url_key': 'customer_url'},
            {'key': 'project_code', 'label': '项目号'},
            {'key': 'serial_no', 'label': '机号'},
            {'key': 'source_no', 'label': '来源单号'},
            {'key': 'source_date', 'label': '来源日期'},
            {'key': 'due_date', 'label': '到期日'},
            {'key': 'original_amount', 'label': '原始金额', 'align': 'right', 'format': 'money'},
            {'key': 'received_amount', 'label': '已收金额', 'align': 'right', 'format': 'money'},
            {'key': 'balance', 'label': '余额', 'align': 'right', 'format': 'money'},
            {'key': 'aging_days', 'label': '账龄天数', 'align': 'right'},
            {'key': 'aging_range', 'label': '账龄区间'},
            {'key': 'risk_level', 'label': '风险等级'},
        ]

        return render_template(
            'reports/receivable_aging_analysis.html',
            title='销售应收账龄分析',
            rows=rows,
            columns=columns,
            summary=summary,
            filters=filters,
        )

    @app.route('/sales/reports/project-serial-order-tracking')
    @login_required
    @sales_report_required
    def project_serial_sales_tracking_report():
        """项目/机号销售订单跟踪报表"""

        # 获取筛选参数
        filters = {
            'project_code': request.args.get('project_code'),
            'serial_no': request.args.get('serial_no'),
            'customer_id': request.args.get('customer_id'),
            'customer_name': request.args.get('customer_name'),
        }

        # 查询数据
        rows = query_project_serial_sales_tracking(query_db, filters)

        # 数据权限过滤
        scope = _current_sales_scope()
        if scope_has_rules(scope):
            rows = [row for row in rows if row_allowed(scope, row, _SALES_SCOPE_FIELD_MAP)]

        # 汇总统计
        total_order_amount = sum(float(row.get('order_amount', 0)) for row in rows)
        total_shipped_amount = sum(float(row.get('shipped_amount', 0)) for row in rows)
        total_receivable_balance = sum(float(row.get('receivable_balance', 0)) for row in rows)

        summary = {
            'total_order_amount': f"{total_order_amount:,.2f}",
            'total_shipped_amount': f"{total_shipped_amount:,.2f}",
            'total_receivable_balance': f"{total_receivable_balance:,.2f}",
            'tracking_count': len(rows),
        }

        # 列定义
        columns = [
            {'key': 'project_code', 'label': '项目号'},
            {'key': 'serial_no', 'label': '机号'},
            {'key': 'customer_name', 'label': '客户'},
            {'key': 'order_no', 'label': '订单号', 'url_key': 'order_url'},
            {'key': 'order_date', 'label': '订单日期'},
            {'key': 'order_amount', 'label': '订单金额', 'align': 'right', 'format': 'money'},
            {'key': 'shipment_count', 'label': '发货次数', 'align': 'right'},
            {'key': 'shipped_amount', 'label': '已发货金额', 'align': 'right', 'format': 'money'},
            {'key': 'receivable_balance', 'label': '应收余额', 'align': 'right', 'format': 'money'},
            {'key': 'service_card_count', 'label': '服务卡数', 'align': 'right'},
            {'key': 'order_status', 'label': '订单状态'},
        ]

        return render_template(
            'reports/project_serial_sales_tracking.html',
            title='项目/机号销售订单跟踪',
            rows=rows,
            columns=columns,
            summary=summary,
            filters=filters,
        )

    @app.route('/sales/reports/shipped-unsettled-detail')
    @login_required
    @sales_report_required
    def shipped_unsettled_detail_report():
        """销售发货未结明细报表"""

        # 获取筛选参数
        filters = {
            'date_start': request.args.get('date_start'),
            'date_end': request.args.get('date_end'),
            'customer_id': request.args.get('customer_id'),
            'customer_name': request.args.get('customer_name'),
            'unsettled_type': request.args.get('unsettled_type'),  # uninvoiced | unreceived
        }

        # 查询数据
        rows = query_shipped_unsettled_detail(query_db, filters)

        # 数据权限过滤
        scope = _current_sales_scope()
        if scope_has_rules(scope):
            rows = [row for row in rows if row_allowed(scope, row, _SALES_SCOPE_FIELD_MAP)]

        # 汇总统计
        total_shipped_amount = sum(float(row.get('shipped_amount', 0)) for row in rows)
        total_uninvoiced_amount = sum(float(row.get('uninvoiced_amount', 0)) for row in rows)
        total_unreceived_amount = sum(float(row.get('unreceived_amount', 0)) for row in rows)

        summary = {
            'total_shipped_amount': f"{total_shipped_amount:,.2f}",
            'total_uninvoiced_amount': f"{total_uninvoiced_amount:,.2f}",
            'total_unreceived_amount': f"{total_unreceived_amount:,.2f}",
            'shipment_count': len(rows),
        }

        # 列定义
        columns = [
            {'key': 'shipment_no', 'label': '发货单号', 'url_key': 'shipment_url'},
            {'key': 'shipment_date', 'label': '发货日期'},
            {'key': 'customer_name', 'label': '客户'},
            {'key': 'order_no', 'label': '订单号'},
            {'key': 'project_code', 'label': '项目号'},
            {'key': 'serial_no', 'label': '机号'},
            {'key': 'shipped_amount', 'label': '发货金额', 'align': 'right', 'format': 'money'},
            {'key': 'invoiced_amount', 'label': '已开票', 'align': 'right', 'format': 'money'},
            {'key': 'uninvoiced_amount', 'label': '未开票', 'align': 'right', 'format': 'money'},
            {'key': 'received_amount', 'label': '已收款', 'align': 'right', 'format': 'money'},
            {'key': 'unreceived_amount', 'label': '未收款', 'align': 'right', 'format': 'money'},
            {'key': 'aging_days', 'label': '账龄天数', 'align': 'right'},
            {'key': 'alert_status', 'label': '告警状态'},
        ]

        return render_template(
            'reports/shipped_unsettled_detail.html',
            title='销售发货未结明细',
            rows=rows,
            columns=columns,
            summary=summary,
            filters=filters,
        )
