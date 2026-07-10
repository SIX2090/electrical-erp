# -*- coding: utf-8 -*-
"""
凭证模板配置和自动生成服务
根据业务单据自动生成会计凭证
"""
from decimal import Decimal
from datetime import datetime

from services.trace_engine import create_trace_link, create_trace_snapshot
from services.transaction_utils import cursor_db_helpers


VOUCHER_BALANCE_TOLERANCE = Decimal('0.005')


# 凭证模板配置
# C-1 enhancement: each line now carries a mapping_key that resolves the
# account code from the finance_account_mappings table. The hardcoded
# account_code is kept as a fallback so behavior is unchanged when the
# mapping table is empty or the key is missing.
VOUCHER_TEMPLATES = {
    'sales_invoice': {
        'name': '销售发票',
        'voucher_type': '记账凭证',
        'lines': [
            {
                'mapping_key': 'accounts_receivable',
                'account_code': '1122',  # 应收账款
                'account_name': '应收账款',
                'side': 'debit',  # 借方
                'amount_field': 'amount_with_tax',
                'summary_template': '销售商品-{customer_name}'
            },
            {
                'mapping_key': 'sales_revenue',
                'account_code': '5001',  # 主营业务收入
                'account_name': '主营业务收入',
                'side': 'credit',  # 贷方
                'amount_field': 'amount_without_tax',
                'summary_template': '销售商品-{customer_name}'
            },
            {
                'mapping_key': 'tax_payable',
                'account_code': '2221',  # 应交税费-应交增值税(销项税额)
                'account_name': '应交税费-应交增值税(销项税额)',
                'side': 'credit',
                'amount_field': 'tax_amount',
                'summary_template': '销售商品-{customer_name}'
            }
        ]
    },
    'purchase_invoice': {
        'name': '采购发票',
        'voucher_type': '记账凭证',
        'lines': [
            {
                'mapping_key': 'inventory',
                'account_code': '1405',  # 原材料
                'account_name': '原材料',
                'side': 'debit',
                'amount_field': 'amount_without_tax',
                'summary_template': '采购原材料-{supplier_name}'
            },
            {
                'mapping_key': 'tax_payable',
                'account_code': '2221',  # 应交税费-应交增值税(进项税额)
                'account_name': '应交税费-应交增值税(进项税额)',
                'side': 'debit',
                'amount_field': 'tax_amount',
                'summary_template': '采购原材料-{supplier_name}'
            },
            {
                'mapping_key': 'accounts_payable',
                'account_code': '2202',  # 应付账款
                'account_name': '应付账款',
                'side': 'credit',
                'amount_field': 'amount_with_tax',
                'summary_template': '采购原材料-{supplier_name}'
            }
        ]
    },
    'customer_receipt': {
        'name': '收款单',
        'voucher_type': '记账凭证',
        'lines': [
            {
                'mapping_key': 'bank',
                'account_code': '1002',  # 银行存款
                'account_name': '银行存款',
                'side': 'debit',
                'amount_field': 'amount',
                'summary_template': '收到货款-{customer_name}'
            },
            {
                'mapping_key': 'accounts_receivable',
                'account_code': '1122',  # 应收账款
                'account_name': '应收账款',
                'side': 'credit',
                'amount_field': 'amount',
                'summary_template': '收到货款-{customer_name}'
            }
        ]
    },
    'supplier_payment': {
        'name': '付款单',
        'voucher_type': '记账凭证',
        'lines': [
            {
                'mapping_key': 'accounts_payable',
                'account_code': '2202',  # 应付账款
                'account_name': '应付账款',
                'side': 'debit',
                'amount_field': 'amount',
                'summary_template': '支付货款-{supplier_name}'
            },
            {
                'mapping_key': 'bank',
                'account_code': '1002',  # 银行存款
                'account_name': '银行存款',
                'side': 'credit',
                'amount_field': 'amount',
                'summary_template': '支付货款-{supplier_name}'
            }
        ]
    }
}


def _resolve_account_from_mapping(query_db, line_template):
    """Resolve account code/id/name for a template line.

    C-1 enhancement: reads the finance_account_mappings table first so
    accountants can adjust the target account without code changes.
    Falls back to the hardcoded account_code in the template when the
    mapping table has no entry for the key.
    """
    mapping_key = line_template.get('mapping_key')
    fallback_code = line_template.get('account_code')
    fallback_name = line_template.get('account_name')

    account_code = fallback_code
    account_name = fallback_name

    if mapping_key:
        try:
            mapping = query_db(
                """
                SELECT account_code, account_name
                FROM finance_account_mappings
                WHERE mapping_key = %s
                """,
                (mapping_key,),
                one=True,
            )
            if mapping:
                account_code = mapping.get('account_code') or fallback_code
                account_name = mapping.get('account_name') or fallback_name
        except Exception:
            # Mapping table missing or query error: fall back to hardcoded code.
            pass

    account = query_db(
        "SELECT id, code, name FROM chart_of_accounts WHERE code = %s",
        (account_code,),
        one=True,
    )
    return account, account_code, account_name


def generate_voucher_from_source(query_db, execute_db, source_type, source_id, current_user_id):
    """
    根据源单据自动生成凭证

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        source_type: 源单据类型 ('sales_invoice', 'purchase_invoice', 'customer_receipt', 'supplier_payment')
        source_id: 源单据ID
        current_user_id: 当前用户ID

    Returns:
        dict: {'success': bool, 'voucher_id': int, 'voucher_no': str, 'message': str}
    """
    # 获取模板配置
    if not getattr(query_db, "_uses_transaction_cursor", False):
        get_db = getattr(query_db, "__self_get_db__", None) or getattr(execute_db, "__self_get_db__", None)
        try:
            from flask import current_app, has_app_context
            get_db = get_db or (current_app.config.get("_get_db") if has_app_context() else None)
        except Exception:
            pass
        if get_db is not None:
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    tx_query_db, tx_execute_db, _ = cursor_db_helpers(cur)
                    result = generate_voucher_from_source(
                        tx_query_db, tx_execute_db, source_type, source_id, current_user_id
                    )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    template = VOUCHER_TEMPLATES.get(source_type)
    if not template:
        return {'success': False, 'message': f'不支持的单据类型: {source_type}'}

    # 获取源单据数据
    source_data = _get_source_document(query_db, source_type, source_id)
    if not source_data:
        return {'success': False, 'message': '源单据不存在'}

    # 检查是否已生成凭证
    existing_voucher = query_db(
        "SELECT id, voucher_no FROM vouchers WHERE source_type = %s AND source_id = %s",
        (source_type, source_id),
        one=True
    )
    if existing_voucher:
        return {
            'success': False,
            'message': f'该单据已生成凭证: {existing_voucher["voucher_no"]}'
        }

    # 生成凭证号
    voucher_date = source_data.get('voucher_date', datetime.now().date())
    if isinstance(voucher_date, str):
        try:
            voucher_date = datetime.strptime(voucher_date[:10], '%Y-%m-%d').date()
        except ValueError:
            voucher_date = datetime.now().date()
    elif voucher_date is None:
        voucher_date = datetime.now().date()
    voucher_no = _generate_voucher_no(query_db, voucher_date)

    # 计算期间
    period_year = voucher_date.year
    period_month = voucher_date.month

    # 准备凭证明细行
    voucher_lines = []
    total_debit = Decimal('0')
    total_credit = Decimal('0')

    for line_no, line_template in enumerate(template['lines'], start=1):
        # C-1: resolve account from finance_account_mappings (with fallback).
        account, resolved_code, resolved_name = _resolve_account_from_mapping(query_db, line_template)
        if not account:
            return {
                'success': False,
                'message': f'科目不存在: {resolved_code} - {resolved_name}'
            }

        # 获取金额
        amount_field = line_template['amount_field']
        amount = Decimal(str(source_data.get(amount_field) or 0))

        if amount == 0:
            continue  # 跳过金额为0的分录

        # 生成摘要
        try:
            summary = line_template['summary_template'].format(**source_data)
        except KeyError:
            summary = line_template['summary_template']

        # 确定借贷方向
        if line_template['side'] == 'debit':
            debit_amount = amount
            credit_amount = Decimal('0')
            total_debit += amount
        else:
            debit_amount = Decimal('0')
            credit_amount = amount
            total_credit += amount

        voucher_lines.append({
            'line_no': line_no,
            'account_id': account['id'],
            'summary': summary,
            'debit_amount': debit_amount,
            'credit_amount': credit_amount,
            'project_code': source_data.get('project_code'),
            'cabinet_no': source_data.get('cabinet_no'),
            'partner_type': source_data.get('partner_type'),
            'partner_id': source_data.get('partner_id')
        })

    # 检查借贷平衡
    if abs(total_debit - total_credit) > VOUCHER_BALANCE_TOLERANCE:
        return {
            'success': False,
            'message': f'借贷不平衡: 借方={total_debit}, 贷方={total_credit}'
        }

    # 创建凭证主表
    voucher_row = query_db(
        """
        INSERT INTO vouchers
            (voucher_no, voucher_date, date, voucher_type, period_year, period_month,
             total_debit, total_credit, source_type, source_id, source_no, summary, status,
             auto_generated, prepared_by, prepared_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)
        RETURNING id
        """,
        (voucher_no, voucher_date, voucher_date, template['voucher_type'], period_year, period_month,
         total_debit, total_credit, source_type, source_id, source_data.get('source_no'),
         f"自动生成-{template['name']}", 'draft',
         current_user_id, datetime.now(), datetime.now(), datetime.now()),
        one=True
    )
    if not voucher_row:
        return {'success': False, 'message': '凭证主表插入失败'}
    voucher_id = voucher_row.get('id') if isinstance(voucher_row, dict) else (
        voucher_row[0] if isinstance(voucher_row, (list, tuple)) and voucher_row else None
    )

    # 创建凭证明细行
    for line in voucher_lines:
        execute_db(
            """
            INSERT INTO voucher_lines
                (voucher_id, line_no, account_id, summary, debit_amount, credit_amount,
                 project_code, cabinet_no, partner_type, partner_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (voucher_id, line['line_no'], line['account_id'], line['summary'],
             line['debit_amount'], line['credit_amount'], line['project_code'],
             line['cabinet_no'], line['partner_type'], line['partner_id'], datetime.now())
        )

    create_trace_link(
        query_db,
        execute_db,
        source_doc_type=source_type,
        source_doc_id=source_id,
        source_doc_no=source_data.get('source_no'),
        target_doc_type='voucher',
        target_doc_id=voucher_id,
        target_doc_no=voucher_no,
        link_type='posts_to',
        link_strength='hard',
        project_code=source_data.get('project_code'),
        cabinet_no=source_data.get('cabinet_no'),
        created_by=current_user_id,
        created_event='generate_voucher',
    )
    create_trace_snapshot(
        query_db,
        execute_db,
        doc_type='voucher',
        doc_id=voucher_id,
        doc_no=voucher_no,
        snapshot_event='generate',
        snapshot_by=current_user_id,
        project_code=source_data.get('project_code'),
        cabinet_no=source_data.get('cabinet_no'),
        header_payload={
            'voucher_id': voucher_id,
            'voucher_no': voucher_no,
            'voucher_date': voucher_date,
            'source_type': source_type,
            'source_id': source_id,
            'source_no': source_data.get('source_no'),
            'total_debit': total_debit,
            'total_credit': total_credit,
        },
        lines_payload=voucher_lines,
        trace_context_payload={
            'upstream': {
                'doc_type': source_type,
                'doc_id': source_id,
                'doc_no': source_data.get('source_no'),
            }
        },
    )

    return {
        'success': True,
        'voucher_id': voucher_id,
        'voucher_no': voucher_no,
        'message': f'凭证 {voucher_no} 生成成功'
    }


def _get_source_document(query_db, source_type, source_id):
    """
    获取源单据数据
    """
    if source_type == 'sales_invoice':
        invoice = query_db(
            """
            SELECT
                si.id,
                si.invoice_no AS source_no,
                si.invoice_date AS voucher_date,
                COALESCE(NULLIF(si.total_amount, 0), si.amount, si.amount_with_tax - si.tax_amount, 0) AS amount_without_tax,
                si.tax_amount,
                si.amount_with_tax,
                si.project_code,
                si.cabinet_no,
                c.name AS customer_name,
                'customer' AS partner_type,
                si.customer_id AS partner_id
            FROM sales_invoices si
            LEFT JOIN customers c ON si.customer_id = c.id
            WHERE si.id = %s
            """,
            (source_id,),
            one=True
        )
        return invoice

    elif source_type == 'purchase_invoice':
        invoice = query_db(
            """
            SELECT
                pi.id,
                pi.invoice_no AS source_no,
                pi.invoice_date AS voucher_date,
                COALESCE(NULLIF(pi.total_amount, 0), pi.amount, pi.amount_with_tax - pi.tax_amount, 0) AS amount_without_tax,
                pi.tax_amount,
                pi.amount_with_tax,
                pi.project_code,
                pi.cabinet_no,
                s.name AS supplier_name,
                'supplier' AS partner_type,
                pi.supplier_id AS partner_id
            FROM purchase_invoices pi
            LEFT JOIN suppliers s ON pi.supplier_id = s.id
            WHERE pi.id = %s
            """,
            (source_id,),
            one=True
        )
        return invoice

    elif source_type == 'customer_receipt':
        receipt = query_db(
            """
            SELECT
                cr.id,
                cr.receipt_no AS source_no,
                cr.receipt_date AS voucher_date,
                cr.amount,
                cr.project_code,
                cr.cabinet_no,
                c.name AS customer_name,
                'customer' AS partner_type,
                cr.customer_id AS partner_id
            FROM customer_receipts cr
            LEFT JOIN customers c ON cr.customer_id = c.id
            WHERE cr.id = %s
            """,
            (source_id,),
            one=True
        )
        return receipt

    elif source_type == 'supplier_payment':
        payment = query_db(
            """
            SELECT
                sp.id,
                sp.payment_no AS source_no,
                sp.payment_date AS voucher_date,
                sp.amount,
                sp.project_code,
                sp.cabinet_no,
                s.name AS supplier_name,
                'supplier' AS partner_type,
                sp.supplier_id AS partner_id
            FROM supplier_payments sp
            LEFT JOIN suppliers s ON sp.supplier_id = s.id
            WHERE sp.id = %s
            """,
            (source_id,),
            one=True
        )
        return payment

    return None


def _generate_voucher_no(query_db, voucher_date):
    """
    生成凭证号
    格式: 记-YYYYMM-001
    """
    if isinstance(voucher_date, str):
        try:
            voucher_date = datetime.strptime(voucher_date[:10], '%Y-%m-%d').date()
        except ValueError:
            voucher_date = datetime.now().date()
    elif voucher_date is None:
        voucher_date = datetime.now().date()
    period_prefix = voucher_date.strftime('%Y%m')
    prefix = f'\u8bb0-{period_prefix}-'

    try:
        max_voucher = query_db(
            """
            SELECT voucher_no FROM vouchers
            WHERE voucher_no LIKE %s
            ORDER BY voucher_no DESC
            LIMIT 1
            """,
            (f'{prefix}%',),
            one=True
        )
        existing_value = 0
        if max_voucher:
            seq_part = (max_voucher.get('voucher_no') or '').split('-')[-1]
            if seq_part.isdigit():
                existing_value = int(seq_part)
        row = query_db(
            """
            INSERT INTO document_sequences (prefix, scope, last_value, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (prefix, scope) DO UPDATE
            SET last_value = GREATEST(document_sequences.last_value, EXCLUDED.last_value) + 1,
                updated_at = NOW()
            RETURNING last_value
            """,
            (prefix, 'vouchers.voucher_no', existing_value + 1),
            one=True
        )
        if row:
            return f'{prefix}{int(row["last_value"]):03d}'
    except Exception as exc:
        raise RuntimeError("生成凭证号失败") from exc


def generate_voucher_number(query_db, voucher_date):
    """
    生成凭证号（兼容别名，供 inventory_costing_service 等模块调用）
    """
    return _generate_voucher_no(query_db, voucher_date)


def create_voucher_with_lines(
    query_db,
    execute_db,
    voucher_no,
    voucher_date,
    voucher_type,
    summary,
    source_type,
    source_no,
    lines,
    prepared_by,
):
    """
    创建凭证主表及明细行，返回凭证ID。

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        voucher_no: 凭证号
        voucher_date: 凭证日期
        voucher_type: 凭证类型
        summary: 凭证摘要
        source_type: 来源单据类型
        source_no: 来源单据号
        lines: 凭证分录列表，每项包含 account_code, summary, debit_amount, credit_amount, project_code, cabinet_no
        prepared_by: 制单人ID

    Returns:
        凭证ID
    """
    if isinstance(voucher_date, str):
        try:
            voucher_date = datetime.strptime(voucher_date[:10], '%Y-%m-%d').date()
        except ValueError:
            voucher_date = datetime.now().date()
    elif voucher_date is None:
        voucher_date = datetime.now().date()

    total_debit = Decimal('0')
    total_credit = Decimal('0')
    for line in lines:
        total_debit += Decimal(str(line.get('debit_amount') or 0))
        total_credit += Decimal(str(line.get('credit_amount') or 0))

    voucher_row = query_db(
        """
        INSERT INTO vouchers
            (voucher_no, voucher_date, date, voucher_type, period_year, period_month,
             total_debit, total_credit, source_type, source_no, summary, status,
             prepared_by, prepared_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s)
        RETURNING id
        """,
        (
            voucher_no,
            voucher_date,
            voucher_date,
            voucher_type,
            voucher_date.year,
            voucher_date.month,
            total_debit,
            total_credit,
            source_type,
            source_no,
            summary,
            prepared_by,
            datetime.now(),
            datetime.now(),
            datetime.now(),
        ),
        one=True,
    )
    voucher_id = voucher_row.get('id') if isinstance(voucher_row, dict) else (
        voucher_row[0] if isinstance(voucher_row, (list, tuple)) and voucher_row else None
    )

    for idx, line in enumerate(lines, start=1):
        account = query_db(
            "SELECT id FROM chart_of_accounts WHERE code = %s LIMIT 1",
            (line.get('account_code'),),
            one=True,
        )
        if not account:
            raise ValueError(f"科目不存在: {line.get('account_code')}")
        execute_db(
            """
            INSERT INTO voucher_lines
                (voucher_id, line_no, account_id, summary, debit_amount, credit_amount,
                 project_code, cabinet_no, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                voucher_id,
                idx,
                account['id'],
                line.get('summary') or summary,
                Decimal(str(line.get('debit_amount') or 0)),
                Decimal(str(line.get('credit_amount') or 0)),
                line.get('project_code'),
                line.get('cabinet_no'),
                datetime.now(),
            ),
        )

    return voucher_id


def post_voucher(query_db, execute_db, voucher_id, current_user_id):
    """
    凭证过账（记入总账）

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        voucher_id: 凭证ID
        current_user_id: 当前用户ID

    Returns:
        dict: {'success': bool, 'message': str}
    """
    # 获取凭证
    if not getattr(query_db, "_uses_transaction_cursor", False):
        get_db = getattr(query_db, "__self_get_db__", None) or getattr(execute_db, "__self_get_db__", None)
        try:
            from flask import current_app, has_app_context
            get_db = get_db or (current_app.config.get("_get_db") if has_app_context() else None)
        except Exception:
            pass
        if get_db is not None:
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    tx_query_db, tx_execute_db, _ = cursor_db_helpers(cur)
                    result = post_voucher(tx_query_db, tx_execute_db, voucher_id, current_user_id)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    voucher = query_db(
        "SELECT * FROM vouchers WHERE id = %s",
        (voucher_id,),
        one=True
    )

    if not voucher:
        return {'success': False, 'message': '凭证不存在'}

    if voucher['status'] == 'posted':
        return {'success': False, 'message': '凭证已过账，不能重复过账'}

    # 检查借贷平衡
    if abs(Decimal(str(voucher['total_debit'])) - Decimal(str(voucher['total_credit']))) > VOUCHER_BALANCE_TOLERANCE:
        return {'success': False, 'message': '借贷不平衡，不能过账'}

    # 获取凭证明细行
    lines = query_db(
        """
        SELECT vl.*, coa.code AS account_code, coa.name AS account_name
        FROM voucher_lines vl
        JOIN chart_of_accounts coa ON vl.account_id = coa.id
        WHERE vl.voucher_id = %s
        ORDER BY vl.line_no
        """,
        (voucher_id,)
    )

    if not lines:
        return {'success': False, 'message': '凭证没有明细行'}

    # 防重入：若已有总账记录（异常重试场景），先清理以避免重复入账
    existing_ledger = query_db(
        "SELECT id FROM general_ledger WHERE voucher_id = %s AND COALESCE(status, 'active') = 'active' LIMIT 1",
        (voucher_id,),
        one=True,
    )
    if existing_ledger:
        execute_db(
            "UPDATE general_ledger SET status = 'reversed' WHERE voucher_id = %s AND COALESCE(status, 'active') = 'active'",
            (voucher_id,),
        )

    # 写入总账
    for line in lines:
        execute_db(
            """
            INSERT INTO general_ledger
                (voucher_id, account_id, account_code, account_name, entry_date,
                 period_year, period_month, debit_amount, credit_amount, summary,
                 project_code, cabinet_no, voucher_no, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (voucher_id, line['account_id'], line['account_code'], line['account_name'],
             voucher['voucher_date'], voucher['period_year'], voucher['period_month'],
             line['debit_amount'], line['credit_amount'], line['summary'],
             line['project_code'], line['cabinet_no'], voucher['voucher_no'], datetime.now())
        )

    ledger_rows = query_db(
        """
        SELECT id, voucher_id, account_id, account_code, account_name, debit_amount, credit_amount,
               summary, project_code, cabinet_no, voucher_no
        FROM general_ledger
        WHERE voucher_id = %s
          AND COALESCE(status, 'active') = 'active'
        ORDER BY id
        """,
        (voucher_id,)
    )
    matched_line_ids = set()
    for ledger in ledger_rows:
        matching_line = None
        for line in lines:
            if line.get('id') in matched_line_ids:
                continue
            if (
                line.get('account_id') == ledger.get('account_id')
                and line.get('debit_amount') == ledger.get('debit_amount')
                and line.get('credit_amount') == ledger.get('credit_amount')
            ):
                matching_line = line
                matched_line_ids.add(line.get('id'))
                break
        create_trace_link(
            query_db,
            execute_db,
            source_doc_type='voucher',
            source_doc_id=voucher_id,
            source_doc_no=voucher.get('voucher_no'),
            source_line_id=matching_line.get('id') if matching_line else None,
            source_line_no=matching_line.get('line_no') if matching_line else None,
            target_doc_type='general_ledger',
            target_doc_id=ledger.get('id'),
            target_doc_no=ledger.get('voucher_no'),
            target_line_id=ledger.get('id'),
            link_type='posts_to',
            link_strength='hard',
            project_code=ledger.get('project_code'),
            cabinet_no=ledger.get('cabinet_no'),
            created_by=current_user_id,
            created_event='post_voucher',
        )
    create_trace_snapshot(
        query_db,
        execute_db,
        doc_type='voucher',
        doc_id=voucher_id,
        doc_no=voucher.get('voucher_no'),
        snapshot_event='post',
        snapshot_by=current_user_id,
        project_code=None,
        cabinet_no=None,
        header_payload=dict(voucher),
        lines_payload=[dict(line) for line in lines],
        trace_context_payload={
            'downstream': [
                {'doc_type': 'general_ledger', 'doc_id': row.get('id'), 'doc_no': row.get('voucher_no')}
                for row in ledger_rows
            ]
        },
    )

    # 更新凭证状态
    execute_db(
        """
        UPDATE vouchers
        SET status = 'posted', posted_by = %s, posted_at = %s, updated_at = %s
        WHERE id = %s
        """,
        (current_user_id, datetime.now(), datetime.now(), voucher_id)
    )

    return {
        'success': True,
        'message': f'凭证 {voucher["voucher_no"]} 已过账'
    }


def reverse_posting(query_db, execute_db, voucher_id, current_user_id):
    """
    反过账（从总账中删除）

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        voucher_id: 凭证ID
        current_user_id: 当前用户ID

    Returns:
        dict: {'success': bool, 'message': str}
    """
    # 获取凭证
    voucher = query_db(
        "SELECT * FROM vouchers WHERE id = %s",
        (voucher_id,),
        one=True
    )

    if not voucher:
        return {'success': False, 'message': '凭证不存在'}

    if voucher['status'] != 'posted':
        return {'success': False, 'message': '凭证未过账，不能反过账'}

    # 检查期间是否已结账
    period_close = query_db(
        """
        SELECT * FROM period_closing
        WHERE period_year = %s AND period_month = %s AND status = '已结账'
        """,
        (voucher['period_year'], voucher['period_month']),
        one=True
    )

    if period_close:
        return {
            'success': False,
            'message': f'{voucher["period_year"]}年{voucher["period_month"]}月已结账，不能反过账'
        }

    # 标记总账记录为已冲销（保留审计轨迹，不物理删除）
    execute_db(
        "UPDATE general_ledger SET status = 'reversed' WHERE voucher_id = %s AND COALESCE(status,'active') = 'active'",
        (voucher_id,)
    )

    # 更新凭证状态（与 finance_routes.py reverse_post_voucher 保持一致：反过账回到已复核/audited）
    execute_db(
        """
        UPDATE vouchers
        SET status = 'audited', posted_by = NULL, posted_at = NULL, updated_at = %s
        WHERE id = %s
        """,
        (datetime.now(), voucher_id)
    )

    return {
        'success': True,
        'message': f'凭证 {voucher["voucher_no"]} 已反过账'
    }
