# -*- coding: utf-8 -*-
"""
发票红冲路由
处理销售发票和采购发票的红冲操作
"""
from flask import request, jsonify, render_template, redirect, url_for, flash
from services.invoice_red_flush_service import (
    create_red_invoice,
    can_red_flush_invoice,
    get_red_invoice_info
)


def register_invoice_red_flush_routes(app, query_db, execute_db, _login_required, get_db=None, role_required=None):
    """
    注册发票红冲相关路由

    Args:
        app: Flask应用实例
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        _login_required: 登录验证装饰器
        get_db: 可选，数据库连接获取函数，用于事务包裹
    """

    finance_required = role_required("admin", "manager", "finance") if role_required else (lambda func: func)

    @app.route("/finance/<kind>-invoices/<int:invoice_id>/red-flush", methods=["GET"])
    @_login_required
    @finance_required
    def invoice_red_flush_form(kind, invoice_id):
        """
        显示红冲发票表单页面

        Args:
            kind: 'sales' 或 'purchase'
            invoice_id: 原发票ID
        """
        # 验证发票类型
        if kind not in ['sales', 'purchase']:
            flash('不支持的发票类型', 'danger')
            return redirect(request.referrer or '/')

        # 检查是否可以红冲
        check_result = can_red_flush_invoice(query_db, kind, invoice_id)
        if not check_result['can_flush']:
            flash(check_result['reason'], 'danger')
            return redirect(request.referrer or f"/finance/{kind}-invoices")

        # 获取原发票信息
        invoice_table = 'sales_invoices' if kind == 'sales' else 'purchase_invoices'
        invoice = query_db(
            f"""
            SELECT * FROM {invoice_table}
            WHERE id = %s
            """,
            (invoice_id,),
            one=True
        )

        if not invoice:
            flash('发票不存在', 'danger')
            return redirect(f"/finance/{kind}-invoices")

        # 获取发票明细
        items_table = 'sales_invoice_items' if kind == 'sales' else 'purchase_invoice_items'
        items = query_db(
            f"""
            SELECT * FROM {items_table}
            WHERE invoice_id = %s
            ORDER BY line_no, id
            """,
            (invoice_id,)
        )

        return render_template(
            'finance/invoice_red_flush_form.html',
            kind=kind,
            invoice=invoice,
            items=items
        )

    @app.route("/finance/<kind>-invoices/<int:invoice_id>/red-flush", methods=["POST"])
    @_login_required
    @finance_required
    def invoice_red_flush_submit(kind, invoice_id):
        """
        提交红冲发票

        Args:
            kind: 'sales' 或 'purchase'
            invoice_id: 原发票ID
        """
        from flask import session

        # 验证发票类型
        if kind not in ['sales', 'purchase']:
            return jsonify({'success': False, 'message': '不支持的发票类型'}), 400

        # 检查是否可以红冲
        check_result = can_red_flush_invoice(query_db, kind, invoice_id)
        if not check_result['can_flush']:
            return jsonify({'success': False, 'message': check_result['reason']}), 400

        # 获取表单数据
        red_invoice_data = {
            'red_invoice_date': request.form.get('red_invoice_date'),
            'red_reason': request.form.get('red_reason', '红冲发票')
        }

        # 获取当前用户
        current_user_id = session.get('user_id')

        # 创建红字发票
        result = create_red_invoice(
            query_db,
            execute_db,
            kind,
            invoice_id,
            red_invoice_data,
            current_user_id,
            get_db=get_db
        )

        if result['success']:
            flash(result['message'], 'success')
            return jsonify({
                'success': True,
                'message': result['message'],
                'red_invoice_id': result['red_invoice_id'],
                'red_invoice_no': result['red_invoice_no'],
                'redirect_url': f"/finance/{kind}-invoices/{result['red_invoice_id']}"
            })
        else:
            return jsonify({'success': False, 'message': result['message']}), 400

    @app.route("/finance/<kind>-invoices/<int:invoice_id>/red-flush-info", methods=["GET"])
    @_login_required
    @finance_required
    def invoice_red_flush_info(kind, invoice_id):
        """
        获取红字发票信息（AJAX接口）

        Args:
            kind: 'sales' 或 'purchase'
            invoice_id: 原发票ID
        """
        if kind not in ['sales', 'purchase']:
            return jsonify({'success': False, 'message': '不支持的发票类型'}), 400

        red_invoice = get_red_invoice_info(query_db, kind, invoice_id)

        if red_invoice:
            return jsonify({
                'success': True,
                'red_invoice': {
                    'id': red_invoice['id'],
                    'invoice_no': red_invoice['invoice_no'],
                    'invoice_date': str(red_invoice['invoice_date']),
                    'amount_with_tax': float(red_invoice['amount_with_tax']),
                    'status': red_invoice['status'],
                    'remark': red_invoice['remark']
                }
            })
        else:
            return jsonify({'success': False, 'message': '未找到红字发票'})

    @app.route("/finance/<kind>-invoices/<int:invoice_id>/can-red-flush", methods=["GET"])
    @_login_required
    @finance_required
    def invoice_can_red_flush(kind, invoice_id):
        """
        检查发票是否可以红冲（AJAX接口）

        Args:
            kind: 'sales' 或 'purchase'
            invoice_id: 发票ID
        """
        if kind not in ['sales', 'purchase']:
            return jsonify({'can_flush': False, 'reason': '不支持的发票类型'})

        result = can_red_flush_invoice(query_db, kind, invoice_id)
        return jsonify(result)
