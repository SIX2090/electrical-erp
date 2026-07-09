# -*- coding: utf-8 -*-
"""
凭证管理路由
处理凭证的增删改查、过账、反过账等操作
"""
from flask import request, jsonify, render_template, redirect, url_for, flash
from services.voucher_generation_service import (
    generate_voucher_from_source,
    post_voucher,
    reverse_posting
)


def register_voucher_routes(app, query_db, execute_db, _login_required):
    """
    注册凭证管理路由

    Args:
        app: Flask应用实例
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        _login_required: 登录验证装饰器
    """

    @app.route("/finance/vouchers")
    @_login_required
    def voucher_list():
        """
        凭证列表页面
        """
        # 获取筛选条件
        filters = {
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'period_year': request.args.get('period_year'),
            'period_month': request.args.get('period_month'),
            'status': request.args.get('status'),
            'voucher_no': request.args.get('voucher_no'),
            'source_type': request.args.get('source_type')
        }

        # 构建查询条件
        where_clauses = ["1=1"]
        params = []

        if filters['start_date']:
            where_clauses.append("v.voucher_date >= %s")
            params.append(filters['start_date'])

        if filters['end_date']:
            where_clauses.append("v.voucher_date <= %s")
            params.append(filters['end_date'])

        if filters['period_year']:
            where_clauses.append("v.period_year = %s")
            params.append(int(filters['period_year']))

        if filters['period_month']:
            where_clauses.append("v.period_month = %s")
            params.append(int(filters['period_month']))

        if filters['status']:
            where_clauses.append("v.status = %s")
            params.append(filters['status'])

        if filters['voucher_no']:
            where_clauses.append("v.voucher_no LIKE %s")
            params.append(f"%{filters['voucher_no']}%")

        if filters['source_type']:
            where_clauses.append("v.source_type = %s")
            params.append(filters['source_type'])

        where_sql = " AND ".join(where_clauses)

        # 查询凭证列表
        sql = f"""
        SELECT
            v.id,
            v.voucher_no,
            v.voucher_date,
            v.voucher_type,
            v.period_year,
            v.period_month,
            v.total_debit,
            v.total_credit,
            v.source_type,
            v.source_no,
            v.summary,
            v.status,
            u1.username AS prepared_by_name,
            u2.username AS posted_by_name,
            v.prepared_at,
            v.posted_at
        FROM vouchers v
        LEFT JOIN users u1 ON v.prepared_by = u1.id
        LEFT JOIN users u2 ON v.posted_by = u2.id
        WHERE {where_sql}
        ORDER BY v.voucher_date DESC, v.voucher_no DESC
        LIMIT 100
        """

        vouchers = query_db(sql, tuple(params))

        return render_template(
            'finance/voucher_list.html',
            vouchers=vouchers,
            filters=filters
        )

    @app.route("/finance/vouchers/<int:voucher_id>")
    @_login_required
    def voucher_detail(voucher_id):
        """
        凭证详情页面
        """
        # 获取凭证主表
        voucher = query_db(
            """
            SELECT
                v.*,
                u1.username AS prepared_by_name,
                u2.username AS reviewed_by_name,
                u3.username AS posted_by_name
            FROM vouchers v
            LEFT JOIN users u1 ON v.prepared_by = u1.id
            LEFT JOIN users u2 ON v.reviewed_by = u2.id
            LEFT JOIN users u3 ON v.posted_by = u3.id
            WHERE v.id = %s
            """,
            (voucher_id,),
            one=True
        )

        if not voucher:
            flash('凭证不存在', 'danger')
            return redirect('/finance/vouchers')

        # 获取凭证明细行
        lines = query_db(
            """
            SELECT
                vl.*,
                coa.code AS account_code,
                coa.name AS account_name,
                c.name AS customer_name,
                s.name AS supplier_name
            FROM voucher_lines vl
            JOIN chart_of_accounts coa ON vl.account_id = coa.id
            LEFT JOIN customers c ON vl.partner_type = 'customer' AND vl.partner_id = c.id
            LEFT JOIN suppliers s ON vl.partner_type = 'supplier' AND vl.partner_id = s.id
            WHERE vl.voucher_id = %s
            ORDER BY vl.line_no
            """,
            (voucher_id,)
        )

        return render_template(
            'finance/voucher_detail.html',
            voucher=voucher,
            lines=lines
        )

    @app.route("/finance/vouchers/<int:voucher_id>/post", methods=["POST"])
    @_login_required
    def voucher_post(voucher_id):
        """
        凭证过账
        """
        from flask import session
        current_user_id = session.get('user_id')

        result = post_voucher(query_db, execute_db, voucher_id, current_user_id)

        if result['success']:
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'danger')

        return redirect(f'/finance/vouchers/{voucher_id}')

    @app.route("/finance/vouchers/<int:voucher_id>/reverse", methods=["POST"])
    @_login_required
    def voucher_reverse(voucher_id):
        """
        凭证反过账
        """
        from flask import session
        current_user_id = session.get('user_id')

        result = reverse_posting(query_db, execute_db, voucher_id, current_user_id)

        if result['success']:
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'danger')

        return redirect(f'/finance/vouchers/{voucher_id}')

    @app.route("/finance/vouchers/generate", methods=["GET", "POST"])
    @_login_required
    def voucher_generate_batch():
        """
        批量生成凭证页面和处理
        """
        if request.method == 'GET':
            # 显示批量生成页面
            # 查询未生成凭证的单据

            # 未生成凭证的销售发票
            sales_invoices = query_db(
                """
                SELECT
                    si.id,
                    si.invoice_no,
                    si.invoice_date,
                    si.amount_with_tax,
                    c.name AS customer_name
                FROM sales_invoices si
                JOIN customers c ON si.customer_id = c.id
                WHERE si.status = '已确认'
                  AND NOT EXISTS (
                      SELECT 1 FROM vouchers v
                      WHERE v.source_type = 'sales_invoice' AND v.source_no = si.invoice_no
                  )
                ORDER BY si.invoice_date DESC
                LIMIT 50
                """
            )

            # 未生成凭证的采购发票
            purchase_invoices = query_db(
                """
                SELECT
                    pi.id,
                    pi.invoice_no,
                    pi.invoice_date,
                    pi.amount_with_tax,
                    s.name AS supplier_name
                FROM purchase_invoices pi
                JOIN suppliers s ON pi.supplier_id = s.id
                WHERE pi.status = '已确认'
                  AND NOT EXISTS (
                      SELECT 1 FROM vouchers v
                      WHERE v.source_type = 'purchase_invoice' AND v.source_no = pi.invoice_no
                  )
                ORDER BY pi.invoice_date DESC
                LIMIT 50
                """
            )

            # 未生成凭证的收款单
            receipts = query_db(
                """
                SELECT
                    cr.id,
                    cr.receipt_no,
                    cr.receipt_date,
                    cr.amount,
                    c.name AS customer_name
                FROM customer_receipts cr
                JOIN customers c ON cr.customer_id = c.id
                WHERE cr.status = '已确认'
                  AND NOT EXISTS (
                      SELECT 1 FROM vouchers v
                      WHERE v.source_type = 'customer_receipt' AND v.source_no = cr.receipt_no
                  )
                ORDER BY cr.receipt_date DESC
                LIMIT 50
                """
            )

            # 未生成凭证的付款单
            payments = query_db(
                """
                SELECT
                    sp.id,
                    sp.payment_no,
                    sp.payment_date,
                    sp.amount,
                    s.name AS supplier_name
                FROM supplier_payments sp
                JOIN suppliers s ON sp.supplier_id = s.id
                WHERE sp.status = '已确认'
                  AND NOT EXISTS (
                      SELECT 1 FROM vouchers v
                      WHERE v.source_type = 'supplier_payment' AND v.source_no = sp.payment_no
                  )
                ORDER BY sp.payment_date DESC
                LIMIT 50
                """
            )

            return render_template(
                'finance/voucher_generate_batch.html',
                sales_invoices=sales_invoices,
                purchase_invoices=purchase_invoices,
                receipts=receipts,
                payments=payments
            )

        else:
            # POST - 批量生成凭证
            from flask import session
            current_user_id = session.get('user_id')

            # 获取选中的单据
            selected_items = request.form.getlist('selected_items')

            success_count = 0
            error_count = 0
            errors = []

            for item in selected_items:
                # 格式: source_type:source_id
                parts = item.split(':')
                if len(parts) != 2:
                    continue

                source_type, source_id = parts[0], int(parts[1])

                result = generate_voucher_from_source(
                    query_db,
                    execute_db,
                    source_type,
                    source_id,
                    current_user_id
                )

                if result['success']:
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"{source_type}#{source_id}: {result['message']}")

            # 返回结果
            if success_count > 0:
                flash(f'成功生成 {success_count} 张凭证', 'success')
            if error_count > 0:
                flash(f'失败 {error_count} 张，原因：{"; ".join(errors[:5])}', 'warning')

            return redirect('/finance/vouchers/generate')

    @app.route("/finance/vouchers/generate-single", methods=["POST"])
    @_login_required
    def voucher_generate_single():
        """
        单张凭证生成（AJAX接口）
        """
        from flask import session
        current_user_id = session.get('user_id')

        source_type = (request.json or {}).get('source_type')
        source_id = (request.json or {}).get('source_id')

        if not source_type or not source_id:
            return jsonify({'success': False, 'message': '参数缺失'}), 400

        result = generate_voucher_from_source(
            query_db,
            execute_db,
            source_type,
            source_id,
            current_user_id
        )

        return jsonify(result)
