"""Finance module routes: receivables, payables, vouchers, period closing, and financial reports."""
from datetime import date, timedelta
from decimal import Decimal
import json
import uuid

from flask import current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

from routes.read_query_helpers import _csv_response
from services.decimal_utils import as_decimal, money_fmt as money_metric
from services.voucher_generation_service import generate_voucher_from_source
from services.bank_reconciliation_service import (
    auto_match_statement_lines,
    get_statement_detail,
    import_bank_statement_lines,
    list_bank_statements,
    list_unmatched_journal_entries,
    manual_match_line,
    unmatch_line,
)
from services.fx_adjustment_service import (
    get_fx_adjustment_run_detail,
    get_period_end_rate,
    list_exchange_rates,
    list_fx_adjustment_runs,
    run_fx_adjustment,
    upsert_exchange_rate,
)
from routes.import_csv_helpers import read_validated_csv_upload, csv_cell, decimal_text


ALLOWED_PERIOD_CLOSE_ROLES = {"admin", "manager", "finance"}
PERIOD_CLOSE_LOCK_ACTIONS = {"audit", "close", "lock"}


AR_RECEIPT_DOCUMENT_TYPES = {
    "customer_receipt": {
        "label": "收款单",
        "new_label": "新增收款单",
        "list_title": "收款单列表",
        "entry_title": "新增收款单",
        "edit_title": "编辑收款单",
        "detail_title": "收款单详情",
        "list_url": "/customer-receipts",
        "new_url": "/customer-receipts/new",
        "detail_base": "/customer-receipts",
        "prefix": "CR",
        "amount_label": "收款金额",
        "method_label": "收款方式",
        "line_section_title": "收款信息",
        "line_amount_label": "收款金额",
        "line_account_label": "收款账户",
        "line_remark_label": "收款备注",
        "settlement_enabled": True,
        "settlement_required": False,
        "partner_source": "open_receivables",
        "direction": "in",
        "source_type": "customer_receipt",
        "action_name": "新增收款单",
        "cash_summary": "收款单",
        "flash_noun": "收款单",
        "subtitle": "客户收款单据列表，只做往来资金核销，不写库存或项目成本。",
    },
    "advance_receipt": {
        "label": "预收款单",
        "new_label": "新增预收款单",
        "list_title": "预收款单列表",
        "entry_title": "新增预收款单",
        "edit_title": "编辑预收款单",
        "detail_title": "预收款单详情",
        "list_url": "/customer-advance-receipts",
        "new_url": "/customer-advance-receipts/new",
        "detail_base": "/customer-advance-receipts",
        "prefix": "AR",
        "amount_label": "预收金额",
        "method_label": "收款方式",
        "line_section_title": "收款信息",
        "line_amount_label": "预收金额",
        "line_account_label": "收款账户",
        "line_remark_label": "预收备注",
        "settlement_enabled": False,
        "settlement_required": False,
        "partner_source": "all_customers",
        "direction": "in",
        "source_type": "customer_advance_receipt",
        "action_name": "新增预收款单",
        "cash_summary": "预收款单",
        "flash_noun": "预收款单",
        "subtitle": "客户预收款登记，形成未分配金额，后续通过应收核销或退款处理。",
    },
    "receipt_refund": {
        "label": "收款退款单",
        "new_label": "新增收款退款单",
        "list_title": "收款退款单列表",
        "entry_title": "新增收款退款单",
        "edit_title": "编辑收款退款单",
        "detail_title": "收款退款单详情",
        "list_url": "/customer-receipt-refunds",
        "new_url": "/customer-receipt-refunds/new",
        "detail_base": "/customer-receipt-refunds",
        "prefix": "RF",
        "amount_label": "退款金额",
        "method_label": "退款方式",
        "line_section_title": "退款信息",
        "line_amount_label": "退款金额",
        "line_account_label": "退款账户",
        "line_remark_label": "退款备注",
        "settlement_enabled": False,
        "settlement_required": False,
        "partner_source": "all_customers",
        "direction": "out",
        "source_type": "customer_receipt_refund",
        "action_name": "新增收款退款单",
        "cash_summary": "收款退款单",
        "flash_noun": "收款退款单",
        "subtitle": "客户收款退款登记，只写现金银行流出；原应收反核销仍通过收款单详情执行。",
    },
    "advance_refund": {
        "label": "预收退款单",
        "new_label": "新增预收退款单",
        "list_title": "预收退款单列表",
        "entry_title": "新增预收退款单",
        "edit_title": "编辑预收退款单",
        "detail_title": "预收退款单详情",
        "list_url": "/customer-advance-refunds",
        "new_url": "/customer-advance-refunds/new",
        "detail_base": "/customer-advance-refunds",
        "prefix": "AF",
        "amount_label": "退款金额",
        "method_label": "退款方式",
        "line_section_title": "退款信息",
        "line_amount_label": "退款金额",
        "line_account_label": "退款账户",
        "line_remark_label": "退款备注",
        "settlement_enabled": False,
        "settlement_required": False,
        "partner_source": "all_customers",
        "direction": "out",
        "source_type": "customer_advance_refund",
        "action_name": "新增预收退款单",
        "cash_summary": "预收退款单",
        "flash_noun": "预收退款单",
        "subtitle": "预收款退款登记，只写现金银行流出；不自动冲减历史预收来源。",
    },
    "other_income": {
        "label": "其他收入单",
        "new_label": "新增其他收入单",
        "list_title": "其他收入单列表",
        "entry_title": "新增其他收入单",
        "edit_title": "编辑其他收入单",
        "detail_title": "其他收入单详情",
        "list_url": "/customer-other-income",
        "new_url": "/customer-other-income/new",
        "detail_base": "/customer-other-income",
        "prefix": "OI",
        "amount_label": "收入金额",
        "method_label": "收款方式",
        "line_section_title": "收入信息",
        "line_amount_label": "收入金额",
        "line_account_label": "收入账户",
        "line_remark_label": "收入备注",
        "settlement_enabled": False,
        "settlement_required": False,
        "partner_source": "all_customers",
        "direction": "in",
        "source_type": "customer_other_income",
        "action_name": "新增其他收入单",
        "cash_summary": "其他收入单",
        "flash_noun": "其他收入单",
        "subtitle": "客户其他收入登记，只写现金银行流入；不自动生成销售应收或收入凭证。",
    },
    "other_income_refund": {
        "label": "其他收入退款单",
        "new_label": "新增其他收入退款单",
        "list_title": "其他收入退款单列表",
        "entry_title": "新增其他收入退款单",
        "edit_title": "编辑其他收入退款单",
        "detail_title": "其他收入退款单详情",
        "list_url": "/customer-other-income-refunds",
        "new_url": "/customer-other-income-refunds/new",
        "detail_base": "/customer-other-income-refunds",
        "prefix": "OR",
        "amount_label": "退款金额",
        "method_label": "退款方式",
        "line_section_title": "退款信息",
        "line_amount_label": "退款金额",
        "line_account_label": "退款账户",
        "line_remark_label": "退款备注",
        "settlement_enabled": False,
        "settlement_required": False,
        "partner_source": "all_customers",
        "direction": "out",
        "source_type": "customer_other_income_refund",
        "action_name": "新增其他收入退款单",
        "cash_summary": "其他收入退款单",
        "flash_noun": "其他收入退款单",
        "subtitle": "其他收入退款登记，只写现金银行流出；不自动冲减销售应收。",
    },
}


AP_PAYMENT_DOCUMENT_TYPES = {
    "supplier_payment": {
        "label": "付款单",
        "new_label": "新增付款单",
        "list_title": "付款单列表",
        "entry_title": "新增付款单",
        "edit_title": "编辑付款单",
        "detail_title": "付款单详情",
        "list_url": "/payments",
        "new_url": "/payments/new",
        "detail_base": "/payments",
        "prefix": "SP",
        "amount_label": "付款金额",
        "method_label": "付款方式",
        "line_section_title": "付款信息",
        "line_amount_label": "付款金额",
        "line_account_label": "付款账户",
        "line_remark_label": "付款备注",
        "settlement_enabled": True,
        "partner_source": "open_payables",
        "direction": "out",
        "source_type": "supplier_payment",
        "action_name": "新增付款单",
        "cash_summary": "付款单",
        "flash_noun": "付款单",
        "subtitle": "供应商付款单据列表，用于应付核销和现金银行流出登记。",
    },
    "advance_payment": {
        "label": "预付款单",
        "new_label": "新增预付款单",
        "list_title": "预付款单列表",
        "entry_title": "新增预付款单",
        "edit_title": "编辑预付款单",
        "detail_title": "预付款单详情",
        "list_url": "/supplier-advance-payments",
        "new_url": "/supplier-advance-payments/new",
        "detail_base": "/supplier-advance-payments",
        "prefix": "AP",
        "amount_label": "预付金额",
        "method_label": "付款方式",
        "line_section_title": "付款信息",
        "line_amount_label": "预付金额",
        "line_account_label": "付款账户",
        "line_remark_label": "预付备注",
        "settlement_enabled": False,
        "partner_source": "all_suppliers",
        "direction": "out",
        "source_type": "supplier_advance_payment",
        "action_name": "新增预付款单",
        "cash_summary": "预付款单",
        "flash_noun": "预付款单",
        "subtitle": "供应商预付款登记，只写现金银行流出并形成未分配金额；后续冲应付需通过付款核销流程处理。",
    },
    "payment_refund": {
        "label": "付款退款单",
        "new_label": "新增付款退款单",
        "list_title": "付款退款单列表",
        "entry_title": "新增付款退款单",
        "edit_title": "编辑付款退款单",
        "detail_title": "付款退款单详情",
        "list_url": "/supplier-payment-refunds",
        "new_url": "/supplier-payment-refunds/new",
        "detail_base": "/supplier-payment-refunds",
        "prefix": "PR",
        "amount_label": "退款金额",
        "method_label": "退款方式",
        "line_section_title": "退款信息",
        "line_amount_label": "退款金额",
        "line_account_label": "收款账户",
        "line_remark_label": "退款备注",
        "settlement_enabled": False,
        "partner_source": "all_suppliers",
        "direction": "in",
        "source_type": "supplier_payment_refund",
        "action_name": "新增付款退款单",
        "cash_summary": "付款退款单",
        "flash_noun": "付款退款单",
        "subtitle": "供应商付款退款登记，只写现金银行流入；原应付核销回滚仍通过付款单详情执行。",
    },
    "advance_refund": {
        "label": "预付退款单",
        "new_label": "新增预付退款单",
        "list_title": "预付退款单列表",
        "entry_title": "新增预付退款单",
        "edit_title": "编辑预付退款单",
        "detail_title": "预付退款单详情",
        "list_url": "/supplier-advance-refunds",
        "new_url": "/supplier-advance-refunds/new",
        "detail_base": "/supplier-advance-refunds",
        "prefix": "ARF",
        "amount_label": "退款金额",
        "method_label": "退款方式",
        "line_section_title": "退款信息",
        "line_amount_label": "退款金额",
        "line_account_label": "收款账户",
        "line_remark_label": "退款备注",
        "settlement_enabled": False,
        "partner_source": "all_suppliers",
        "direction": "in",
        "source_type": "supplier_advance_refund",
        "action_name": "新增预付退款单",
        "cash_summary": "预付退款单",
        "flash_noun": "预付退款单",
        "subtitle": "供应商预付款退款登记，只写现金银行流入；不自动冲减历史预付款来源。",
    },
    "other_expense": {
        "label": "其他支出单",
        "new_label": "新增其他支出单",
        "list_title": "其他支出单列表",
        "entry_title": "新增其他支出单",
        "edit_title": "编辑其他支出单",
        "detail_title": "其他支出单详情",
        "list_url": "/supplier-other-expenses",
        "new_url": "/supplier-other-expenses/new",
        "detail_base": "/supplier-other-expenses",
        "prefix": "OE",
        "amount_label": "支出金额",
        "method_label": "付款方式",
        "line_section_title": "支出信息",
        "line_amount_label": "支出金额",
        "line_account_label": "支出账户",
        "line_remark_label": "支出备注",
        "settlement_enabled": False,
        "partner_source": "all_suppliers",
        "direction": "out",
        "source_type": "supplier_other_expense",
        "action_name": "新增其他支出单",
        "cash_summary": "其他支出单",
        "flash_noun": "其他支出单",
        "subtitle": "其他支出登记，只写现金银行流出；不自动生成采购应付、库存成本或费用凭证。",
    },
    "other_expense_refund": {
        "label": "其他支出退款单",
        "new_label": "新增其他支出退款单",
        "list_title": "其他支出退款单列表",
        "entry_title": "新增其他支出退款单",
        "edit_title": "编辑其他支出退款单",
        "detail_title": "其他支出退款单详情",
        "list_url": "/supplier-other-expense-refunds",
        "new_url": "/supplier-other-expense-refunds/new",
        "detail_base": "/supplier-other-expense-refunds",
        "prefix": "OER",
        "amount_label": "退款金额",
        "method_label": "退款方式",
        "line_section_title": "退款信息",
        "line_amount_label": "退款金额",
        "line_account_label": "收款账户",
        "line_remark_label": "退款备注",
        "settlement_enabled": False,
        "partner_source": "all_suppliers",
        "direction": "in",
        "source_type": "supplier_other_expense_refund",
        "action_name": "新增其他支出退款单",
        "cash_summary": "其他支出退款单",
        "flash_noun": "其他支出退款单",
        "subtitle": "其他支出退款登记，只写现金银行流入；不自动冲减费用或采购应付。",
    },
}


def returned_id(result):
    if result is None:
        return None
    if isinstance(result, dict):
        return result.get("id")
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
        if isinstance(first, dict):
            return first.get("id")
        return first
    return None


def _cursor_returned_id(cursor):
    try:
        row = cursor.fetchone()
    except Exception:
        return None
    return returned_id(row)


def _transaction_callables(cursor):
    def query_one(sql, params=None):
        cursor.execute(sql, params or ())
        return cursor.fetchone()

    def query_rows(sql, params=None):
        cursor.execute(sql, params or ())
        return cursor.fetchall()

    def execute_db(sql, params=None):
        cursor.execute(sql, params or ())

    def execute_and_return(sql, params=None):
        cursor.execute(sql, params or ())
        return cursor.fetchone()

    return query_one, query_rows, execute_db, execute_and_return


def _run_finance_funds_transaction(operation):
    runner = current_app.extensions.get("run_in_transaction") if current_app else None
    if runner:
        return runner(operation)
    return operation(None)


def _finance_transaction_log_action(execute_db, action, target="", remark=""):
    trace_id = getattr(g, "trace_id", None) or uuid.uuid4().hex
    g.trace_id = trace_id
    execute_db(
        """
        INSERT INTO operation_logs
            (user_id, username, action, target, remark, request_path, request_method, remote_addr, user_agent, trace_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            session.get("user_id"),
            session.get("username", ""),
            action,
            target,
            remark,
            request.path,
            request.method,
            request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            request.headers.get("User-Agent", ""),
            trace_id,
        ),
    )


def period_bounds(year, month):
    start = date(int(year), int(month), 1)
    if int(month) == 12:
        end = date(int(year) + 1, 1, 1)
    else:
        end = date(int(year), int(month) + 1, 1)
    return start, end


def period_label(year, month):
    return f"{int(year):04d}-{int(month):02d}"


def _period_parts(doc_date):
    value = str(doc_date or date.today().isoformat())[:10]
    try:
        year = int(value[0:4])
        month = int(value[5:7])
    except Exception:
        today = date.today()
        year = today.year
        month = today.month
        value = today.isoformat()
    return value, year, month


def _period_is_closed(query_one, doc_date):
    _, year, month = _period_parts(doc_date)
    row = query_one(
        "SELECT status FROM accounting_periods WHERE year=%s AND month=%s",
        (year, month),
    ) or {}
    return (row.get("status") or "open") in {"closed", "locked"}


def _period_write_error(query_one, doc_date):
    if _period_is_closed(query_one, doc_date):
        return "Accounting period is closed; reverse close before posting this document."
    return ""


def _account_for_mapping(query_one, execute_and_return, mapping_key, fallback_code, fallback_name):
    row = query_one(
        """
        SELECT coa.id, coa.code, coa.name
        FROM finance_account_mappings fam
        LEFT JOIN chart_of_accounts coa
          ON coa.id=fam.account_id OR coa.code=fam.account_code
        WHERE fam.mapping_key=%s
        ORDER BY coa.id NULLS LAST
        LIMIT 1
        """,
        (mapping_key,),
    )
    if row and row.get("id"):
        return row
    row = query_one(
        "SELECT id, code, name FROM chart_of_accounts WHERE code=%s LIMIT 1",
        (fallback_code,),
    )
    if row:
        return row
    return execute_and_return(
        """
        INSERT INTO chart_of_accounts (code, name, account_type, balance_direction, is_leaf, status, remark)
        VALUES (%s,%s,'auto','debit',TRUE,'active','Auto-created for finance voucher generation')
        ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name
        RETURNING id, code, name
        """,
        (fallback_code, fallback_name),
    )


def _next_auto_voucher_no(query_one, prefix, doc_date):
    date_text, _, _ = _period_parts(doc_date)
    base = f"{prefix}-{date_text.replace('-', '')}"
    row = query_one(
        "SELECT voucher_no FROM vouchers WHERE voucher_no LIKE %s ORDER BY voucher_no DESC LIMIT 1",
        (f"{base}-%",),
    )
    if row and row.get("voucher_no"):
        try:
            seq = int(str(row["voucher_no"]).rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    else:
        seq = 1
    return f"{base}-{seq:03d}"


def _insert_auto_voucher(query_one, execute_db, execute_and_return, *, source_type, source_id, source_no, doc_date, summary, lines, reversal_of_id=None):
    if not source_type or source_id is None:
        return None
    existing = query_one(
        "SELECT id FROM vouchers WHERE source_type=%s AND source_id=%s AND COALESCE(auto_generated,FALSE)=TRUE AND status='posted' LIMIT 1",
        (source_type, source_id),
    )
    if existing:
        return existing.get("id")
    error = _period_write_error(query_one, doc_date)
    if error:
        raise ValueError(error)
    date_text, year, month = _period_parts(doc_date)
    total_debit = sum(as_decimal(line.get("debit_amount")) for line in lines)
    total_credit = sum(as_decimal(line.get("credit_amount")) for line in lines)
    if abs(total_debit - total_credit) > Decimal("0.005") or total_debit <= 0:
        raise ValueError("Generated voucher is not balanced.")
    voucher_no = _next_auto_voucher_no(query_one, "AUTO", date_text)
    row = execute_and_return(
        """
        INSERT INTO vouchers
            (voucher_no, voucher_date, date, voucher_type, period_year, period_month,
             total_debit, total_credit, source_type, source_id, source_no, summary,
             status, auto_generated, reversal_of_id, prepared_by, reviewed_at, posted_by, posted_at, business_remark)
        VALUES (%s,%s,%s,'auto',%s,%s,%s,%s,%s,%s,%s,%s,'posted',TRUE,%s,%s,NOW(),%s,NOW(),%s)
        RETURNING id
        """,
        (
            voucher_no,
            date_text,
            date_text,
            year,
            month,
            total_debit,
            total_credit,
            source_type,
            source_id,
            source_no,
            summary,
            reversal_of_id,
            session.get("user_id"),
            session.get("user_id"),
            summary,
        ),
    )
    voucher_id = returned_id(row)
    for idx, line in enumerate(lines, 1):
        account = line["account"]
        debit = as_decimal(line.get("debit_amount"))
        credit = as_decimal(line.get("credit_amount"))
        execute_db(
            """
            INSERT INTO voucher_lines
                (voucher_id, line_no, account_id, summary, debit_amount, credit_amount,
                 project_code, cabinet_no, partner_type, partner_id, source_type, source_id, source_no)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                voucher_id,
                idx,
                account.get("id"),
                line.get("summary") or summary,
                debit,
                credit,
                line.get("project_code"),
                line.get("cabinet_no"),
                line.get("partner_type"),
                line.get("partner_id"),
                source_type,
                source_id,
                source_no,
            ),
        )
        execute_db(
            """
            INSERT INTO general_ledger
                (voucher_id, account_id, account_code, account_name, entry_date, period_year, period_month,
                 debit_amount, credit_amount, summary, project_code, cabinet_no, voucher_no,
                 source_type, source_id, source_no)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                voucher_id,
                account.get("id"),
                account.get("code"),
                account.get("name"),
                date_text,
                year,
                month,
                debit,
                credit,
                line.get("summary") or summary,
                line.get("project_code"),
                line.get("cabinet_no"),
                voucher_no,
                source_type,
                source_id,
                source_no,
            ),
        )
    return voucher_id


def _post_customer_receipt_voucher(query_one, execute_db, execute_and_return, *, receipt_id, receipt_no, doc_date, amount, applied_amount, project_code, cabinet_no, customer_id):
    bank = _account_for_mapping(query_one, execute_and_return, "bank", "1002", "\u94f6\u884c\u5b58\u6b3e")
    ar = _account_for_mapping(query_one, execute_and_return, "accounts_receivable", "1122", "\u5e94\u6536\u8d26\u6b3e")
    advance = _account_for_mapping(query_one, execute_and_return, "advance_receipt", "2203", "\u9884\u6536\u8d26\u6b3e")
    lines = [
        {"account": bank, "debit_amount": amount, "credit_amount": 0, "project_code": project_code, "cabinet_no": cabinet_no, "partner_type": "customer", "partner_id": customer_id},
    ]
    if applied_amount > 0:
        lines.append({"account": ar, "debit_amount": 0, "credit_amount": applied_amount, "project_code": project_code, "cabinet_no": cabinet_no, "partner_type": "customer", "partner_id": customer_id})
    unapplied = max(as_decimal(amount) - as_decimal(applied_amount), Decimal("0"))
    if unapplied > 0:
        lines.append({"account": advance, "debit_amount": 0, "credit_amount": unapplied, "project_code": project_code, "cabinet_no": cabinet_no, "partner_type": "customer", "partner_id": customer_id})
    return _insert_auto_voucher(query_one, execute_db, execute_and_return, source_type="customer_receipt", source_id=receipt_id, source_no=receipt_no, doc_date=doc_date, summary=f"\u5ba2\u6237\u6536\u6b3e {receipt_no}", lines=lines)


def _post_supplier_payment_voucher(query_one, execute_db, execute_and_return, *, payment_id, payment_no, doc_date, amount, applied_amount, project_code, cabinet_no, supplier_id):
    bank = _account_for_mapping(query_one, execute_and_return, "bank", "1002", "\u94f6\u884c\u5b58\u6b3e")
    ap = _account_for_mapping(query_one, execute_and_return, "accounts_payable", "2202", "\u5e94\u4ed8\u8d26\u6b3e")
    prepayment = _account_for_mapping(query_one, execute_and_return, "prepayment", "1123", "\u9884\u4ed8\u8d26\u6b3e")
    lines = []
    if applied_amount > 0:
        lines.append({"account": ap, "debit_amount": applied_amount, "credit_amount": 0, "project_code": project_code, "cabinet_no": cabinet_no, "partner_type": "supplier", "partner_id": supplier_id})
    unapplied = max(as_decimal(amount) - as_decimal(applied_amount), Decimal("0"))
    if unapplied > 0:
        lines.append({"account": prepayment, "debit_amount": unapplied, "credit_amount": 0, "project_code": project_code, "cabinet_no": cabinet_no, "partner_type": "supplier", "partner_id": supplier_id})
    lines.append({"account": bank, "debit_amount": 0, "credit_amount": amount, "project_code": project_code, "cabinet_no": cabinet_no, "partner_type": "supplier", "partner_id": supplier_id})
    return _insert_auto_voucher(query_one, execute_db, execute_and_return, source_type="supplier_payment", source_id=payment_id, source_no=payment_no, doc_date=doc_date, summary=f"\u4f9b\u5e94\u5546\u4ed8\u6b3e {payment_no}", lines=lines)


def build_current_finance_period(query_one):
    today = date.today()
    row = query_one(
        "SELECT id, year, month, status, closed_at FROM accounting_periods WHERE year=%s AND month=%s",
        (today.year, today.month),
    )
    status = (row or {}).get("status") or "open"
    return {
        "id": (row or {}).get("id"),
        "year": today.year,
        "month": today.month,
        "label": period_label(today.year, today.month),
        "status": status,
        "status_label": "已结账/锁定" if status in {"closed", "locked", "已结账"} else "未结账",
    }


def finance_sum(query_one, sql, params):
    row = query_one(sql, params) or {}
    return as_decimal(row.get("value"))


def finance_scalar_int(query_one, sql, params=()):
    row = query_one(sql, params) or {}
    try:
        return int(row.get("value") or 0)
    except Exception:
        return 0


def build_period_close_checks(query_one, year, month, payload):
    start, end = period_bounds(year, month)
    unposted_completion_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM production_completion_orders WHERE status NOT IN ('已过账','已作废','已反过账') AND completion_date < %s",
        (end,),
    )
    unposted_subcontract_receive_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM subcontract_receive_orders WHERE status NOT IN ('已过账','已作废') AND date < %s",
        (end,),
    )
    open_work_order_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM work_orders WHERE status NOT IN ('已关闭','已完工','已完成','已作废','已取消') AND planned_end_date < %s",
        (end,),
    )
    checks = [
        {
            "item": "应收核销检查",
            "basis": "应收余额来自 customer_receivables.balance，收款核销来自 customer_receipt_settlements。",
            "result": f"未清应收 {finance_scalar_int(query_one, 'SELECT COUNT(*) AS value FROM customer_receivables WHERE COALESCE(balance,0) > 0')} 笔，余额 {money_metric(payload['summary']['receivable_balance'])}。",
            "action": "结账前确认逾期、争议和本期已收未核销款项。",
        },
        {
            "item": "应付核销检查",
            "basis": "应付余额来自 supplier_payables.balance，付款核销来自 supplier_payment_settlements。",
            "result": f"未清应付 {finance_scalar_int(query_one, 'SELECT COUNT(*) AS value FROM supplier_payables WHERE COALESCE(balance,0) > 0')} 笔，余额 {money_metric(payload['summary']['payable_balance'])}。",
            "action": "结账前确认到货/外协结算、付款安排和争议供应商。",
        },
        {
            "item": "现金银行检查",
            "basis": "经营现金净流入=本期客户收款-本期供应商付款，资金流水保留来源单号。",
            "result": f"本期资金流水 {finance_scalar_int(query_one, 'SELECT COUNT(*) AS value FROM cash_bank_journal_entries WHERE entry_date >= %s AND entry_date < %s', (start, end))} 笔，净流入 {money_metric(payload['summary']['net_cash_flow'])}。",
            "action": "结账前核对收款单、付款单和现金银行流水是否一致。",
        },
        {
            "item": "库存成本检查",
            "basis": "库存成本余额来自 inventory_balances.quantity * unit_cost，库存成本明细可查看库存流水来源单。",
            "result": f"库存成本余额 {money_metric(payload['summary']['inventory_cost_balance'])}。",
            "action": "结账前检查负库存、异常成本和项目/柜号库存占用。",
        },
        {
            "item": "凭证草稿追溯检查",
            "basis": "凭证草稿只读展示来源备注，不提供过账、反过账或科目余额表。",
            "result": f"本期凭证草稿 {finance_scalar_int(query_one, 'SELECT COUNT(*) AS value FROM vouchers WHERE voucher_date >= %s AND voucher_date < %s', (start, end))} 张。",
            "action": "结账前复核凭证摘要、来源单号和借贷金额是否平衡。",
        },
        {
            "item": "完工入库单过账检查",
            "basis": "未过账完工入库单来自 production_completion_orders，状态不含已过账/已作废/已反过账。",
            "result": f"未过账完工入库单 {unposted_completion_count} 笔。",
            "action": "结账前确认所有本期完工入库单已过账或作废。",
        },
        {
            "item": "委外收货单过账检查",
            "basis": "未过账委外收货单来自 subcontract_receive_orders，状态不含已过账/已作废。",
            "result": f"未过账委外收货单 {unposted_subcontract_receive_count} 笔。",
            "action": "结账前确认所有本期委外收货单已过账或作废。",
        },
        {
            "item": "生产工单关闭检查",
            "basis": "未关闭生产工单来自 work_orders，状态不含已关闭/已完工/已完成/已作废/已取消。",
            "result": f"未关闭生产工单 {open_work_order_count} 笔。",
            "action": "结账前确认所有计划结束日期在本期内的工单已关闭或作废。",
        },
    ]
    # C-3: 未审批凭证与银行对账检查（只读展示）
    draft_voucher_display = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM vouchers WHERE voucher_date >= %s AND voucher_date < %s AND status IN ('draft','audited')",
        (start, end),
    )
    unmatched_bank_display = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM bank_statement_lines bsl JOIN bank_statements bs ON bsl.statement_id=bs.id WHERE bs.statement_date >= %s AND bs.statement_date < %s AND bsl.match_status='unmatched'",
        (start, end),
    )
    checks.append(
        {
            "item": "未审批凭证检查",
            "basis": "草稿或已复核但未过账的凭证来自 vouchers，结账前应完成复核与过账。",
            "result": f"本期未过账凭证 {draft_voucher_display} 张。",
            "action": "结账前复核并过账所有本期凭证。",
        }
    )
    checks.append(
        {
            "item": "银行对账匹配检查",
            "basis": "未匹配银行对账单明细来自 bank_statement_lines，结账前应完成银行对账。",
            "result": f"本期未匹配银行对账单明细 {unmatched_bank_display} 条。",
            "action": "结账前完成银行对账单导入与匹配。",
        }
    )
    return checks


def build_period_close_validation(query_one, year, month, payload):
    start, end = period_bounds(year, month)
    errors = []
    warnings = []
    unposted_completion_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM production_completion_orders WHERE status NOT IN ('已过账','已作废','已反过账') AND completion_date >= %s AND completion_date < %s",
        (start, end),
    )
    unposted_subcontract_receive_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM subcontract_receive_orders WHERE status NOT IN ('已过账','已作废') AND date >= %s AND date < %s",
        (start, end),
    )
    open_work_order_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM work_orders WHERE status NOT IN ('已关闭','已完工','已完成','已作废','已取消') AND planned_end_date >= %s AND planned_end_date < %s",
        (start, end),
    )
    negative_inventory_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM inventory_balances WHERE COALESCE(quantity,0) < 0",
    )
    missing_inventory_cost_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM inventory_balances
        WHERE COALESCE(quantity,0) > 0 AND COALESCE(unit_cost,0) <= 0
        """,
    )
    missing_completion_cost_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM production_completion_orders
        WHERE completion_date >= %s AND completion_date < %s
          AND status IN ('已过账','已完成','已完工')
          AND COALESCE(unit_cost,0) <= 0
        """,
        (start, end),
    )
    receivable_open_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM customer_receivables WHERE receivable_date < %s AND COALESCE(balance,0) > 0",
        (end,),
    )
    payable_open_count = finance_scalar_int(
        query_one,
        "SELECT COUNT(*) AS value FROM supplier_payables WHERE doc_date < %s AND COALESCE(balance,0) > 0",
        (end,),
    )
    unbalanced_voucher_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM vouchers
        WHERE voucher_date >= %s AND voucher_date < %s
          AND ABS(COALESCE(total_debit,0) - COALESCE(total_credit,0)) > 0.005
        """,
        (start, end),
    )

    unvouchered_sales_invoice_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM sales_invoices si
        WHERE si.invoice_date >= %s AND si.invoice_date < %s
          AND COALESCE(si.status,'') NOT IN ('void','voided','cancelled')
          AND NOT EXISTS (
              SELECT 1 FROM vouchers v
              WHERE v.source_type='sales_invoice' AND v.source_id=si.id
                AND COALESCE(v.auto_generated,FALSE)=TRUE
                AND v.status IN ('posted','已过账')
          )
        """,
        (start, end),
    )
    unvouchered_purchase_invoice_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM purchase_invoices pi
        WHERE pi.invoice_date >= %s AND pi.invoice_date < %s
          AND COALESCE(pi.status,'') NOT IN ('void','voided','cancelled')
          AND NOT EXISTS (
              SELECT 1 FROM vouchers v
              WHERE v.source_type='purchase_invoice' AND v.source_id=pi.id
                AND COALESCE(v.auto_generated,FALSE)=TRUE
                AND v.status IN ('posted','已过账')
          )
        """,
        (start, end),
    )
    unvouchered_receipt_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM customer_receipts cr
        WHERE cr.receipt_date >= %s AND cr.receipt_date < %s
          AND COALESCE(cr.status,'') NOT IN ('void','voided','cancelled')
          AND NOT EXISTS (
              SELECT 1 FROM vouchers v
              WHERE v.source_type='customer_receipt' AND v.source_id=cr.id
                AND COALESCE(v.auto_generated,FALSE)=TRUE
                AND v.status IN ('posted','已过账')
          )
        """,
        (start, end),
    )
    unvouchered_payment_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM supplier_payments sp
        WHERE sp.payment_date >= %s AND sp.payment_date < %s
          AND COALESCE(sp.status,'') NOT IN ('void','voided','cancelled')
          AND NOT EXISTS (
              SELECT 1 FROM vouchers v
              WHERE v.source_type='supplier_payment' AND v.source_id=sp.id
                AND COALESCE(v.auto_generated,FALSE)=TRUE
                AND v.status IN ('posted','已过账')
          )
        """,
        (start, end),
    )

    # C-3: 未审批凭证检查（草稿/已复核但未过账的凭证）
    draft_voucher_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM vouchers
        WHERE voucher_date >= %s AND voucher_date < %s
          AND status IN ('draft','audited')
        """,
        (start, end),
    )

    # C-3: 未匹配银行对账单检查
    unmatched_bank_statement_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM bank_statement_lines bsl
        JOIN bank_statements bs ON bsl.statement_id = bs.id
        WHERE bs.statement_date >= %s AND bs.statement_date < %s
          AND bsl.match_status = 'unmatched'
        """,
        (start, end),
    )

    # C-3: 未关闭发票检查（本期内有未作废的销售/采购发票但未生成凭证）
    open_sales_invoice_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM sales_invoices si
        WHERE si.invoice_date >= %s AND si.invoice_date < %s
          AND COALESCE(si.status,'') NOT IN ('void','voided','cancelled','closed','已关闭')
          AND NOT EXISTS (
              SELECT 1 FROM vouchers v
              WHERE v.source_type='sales_invoice' AND v.source_id=si.id
                AND v.status='posted'
          )
        """,
        (start, end),
    )
    open_purchase_invoice_count = finance_scalar_int(
        query_one,
        """
        SELECT COUNT(*) AS value
        FROM purchase_invoices pi
        WHERE pi.invoice_date >= %s AND pi.invoice_date < %s
          AND COALESCE(pi.status,'') NOT IN ('void','voided','cancelled','closed','已关闭')
          AND NOT EXISTS (
              SELECT 1 FROM vouchers v
              WHERE v.source_type='purchase_invoice' AND v.source_id=pi.id
                AND v.status='posted'
          )
        """,
        (start, end),
    )

    if negative_inventory_count:
        errors.append(f"存在负库存 {negative_inventory_count} 条，必须先调整或补齐入库后才能锁定期间。")
    if missing_inventory_cost_count:
        errors.append(f"存在有数量但成本为零/空的库存余额 {missing_inventory_cost_count} 条，必须先完成库存成本核算。")
    if missing_completion_cost_count:
        errors.append(f"本期已过账完工入库单存在缺失成本 {missing_completion_cost_count} 条，必须先补齐完工成本。")
    if unbalanced_voucher_count:
        errors.append(f"本期存在借贷不平衡凭证 {unbalanced_voucher_count} 张，必须先修正凭证。")
    if unposted_completion_count:
        warnings.append(f"本期未过账完工入库单 {unposted_completion_count} 笔，结账前应过账或作废。")
    if unposted_subcontract_receive_count:
        warnings.append(f"本期未过账委外收货单 {unposted_subcontract_receive_count} 笔，结账前应过账或作废。")
    if open_work_order_count:
        warnings.append(f"本期计划结束但未关闭生产工单 {open_work_order_count} 张，结账前应完工、关闭或作废。")
    if receivable_open_count:
        warnings.append(f"期末仍有未清应收 {receivable_open_count} 笔，请确认逾期、争议和已收未核销款项。")
    if payable_open_count:
        warnings.append(f"期末仍有未清应付 {payable_open_count} 笔，请确认到货、委外结算和付款安排。")

    if unvouchered_sales_invoice_count:
        errors.append(f"sales_invoice without posted auto voucher: {unvouchered_sales_invoice_count}")
    if unvouchered_purchase_invoice_count:
        errors.append(f"purchase_invoice without posted auto voucher: {unvouchered_purchase_invoice_count}")
    if unvouchered_receipt_count:
        errors.append(f"customer_receipt without posted auto voucher: {unvouchered_receipt_count}")
    if unvouchered_payment_count:
        errors.append(f"supplier_payment without posted auto voucher: {unvouchered_payment_count}")

    # C-3: 未审批凭证检查
    if draft_voucher_count:
        warnings.append(f"本期存在未过账凭证（草稿/已复核）{draft_voucher_count} 张，结账前应完成复核与过账。")

    # C-3: 未匹配银行对账单检查
    if unmatched_bank_statement_count:
        warnings.append(f"本期存在未匹配银行对账单明细 {unmatched_bank_statement_count} 条，结账前应完成银行对账匹配。")

    # C-3: 未关闭发票检查
    if open_sales_invoice_count:
        warnings.append(f"本期存在未关闭销售发票 {open_sales_invoice_count} 张，结账前应生成凭证或关闭。")
    if open_purchase_invoice_count:
        warnings.append(f"本期存在未关闭采购发票 {open_purchase_invoice_count} 张，结账前应生成凭证或关闭。")

    return {
        "errors": errors,
        "warnings": warnings,
        "can_close": not errors,
        "period_label": payload["period_label"],
    }


def build_financial_statement_payload(query_one, year, month):
    start, end = period_bounds(year, month)
    current_period = period_label(year, month)
    revenue = finance_sum(
        query_one,
        """
        SELECT COALESCE(SUM(COALESCE(amount_with_tax,total_amount,0)),0) AS value
        FROM sales_orders
        WHERE order_date >= %s AND order_date < %s
          AND COALESCE(status,'') NOT IN ('已作废','void','cancelled')
        """,
        (start, end),
    )
    purchase_cost = finance_sum(
        query_one,
        """
        SELECT COALESCE(SUM(COALESCE(amount_with_tax,total_amount,0)),0) AS value
        FROM purchase_orders
        WHERE order_date >= %s AND order_date < %s
          AND COALESCE(status,'') NOT IN ('已作废','void','cancelled')
        """,
        (start, end),
    )
    work_order_cost = finance_sum(
        query_one,
        """
        SELECT COALESCE(SUM(total_cost),0) AS value
        FROM work_order_costs
        WHERE COALESCE(last_calculated_at::date, CURRENT_DATE) >= %s
          AND COALESCE(last_calculated_at::date, CURRENT_DATE) < %s
        """,
        (start, end),
    )
    subcontract_cost = finance_sum(
        query_one,
        """
        SELECT COALESCE(SUM(total_amount),0) AS value
        FROM subcontract_orders
        WHERE order_date >= %s AND order_date < %s
          AND COALESCE(status,'') NOT IN ('已作废','void','cancelled')
        """,
        (start, end),
    )
    service_cost = finance_sum(
        query_one,
        """
        SELECT COALESCE(SUM(total_cost),0) AS value
        FROM machine_service_orders
        WHERE COALESCE(service_date, CURRENT_DATE) >= %s
          AND COALESCE(service_date, CURRENT_DATE) < %s
          AND COALESCE(status,'') NOT IN ('已作废','void','cancelled')
        """,
        (start, end),
    )
    cash_in = finance_sum(
        query_one,
        "SELECT COALESCE(SUM(amount),0) AS value FROM customer_receipts WHERE receipt_date >= %s AND receipt_date < %s",
        (start, end),
    )
    cash_out = finance_sum(
        query_one,
        "SELECT COALESCE(SUM(amount),0) AS value FROM supplier_payments WHERE payment_date >= %s AND payment_date < %s",
        (start, end),
    )
    receivable_balance = finance_sum(query_one, "SELECT COALESCE(SUM(balance),0) AS value FROM customer_receivables", ())
    payable_balance = finance_sum(query_one, "SELECT COALESCE(SUM(balance),0) AS value FROM supplier_payables", ())
    inventory_amount = finance_sum(
        query_one,
        "SELECT COALESCE(SUM(COALESCE(quantity,0) * COALESCE(unit_cost,0)),0) AS value FROM inventory_balances",
        (),
    )
    cash_balance = cash_in - cash_out
    cost = purchase_cost + work_order_cost + subcontract_cost + service_cost
    gross_profit = revenue - cost
    operating_assets = cash_balance + receivable_balance + inventory_amount
    operating_equity = operating_assets - payable_balance
    return {
        "period_label": current_period,
        "start_date": start.isoformat(),
        "end_date": (end - timedelta(days=1)).isoformat(),
        "reconciliation_note": "勾稽关系：经营资产估算=经营现金净流入+应收余额+库存成本余额；经营权益估算=经营资产估算-应付余额；经营毛利=销售业务收入-采购/工单/外协/售后成本。",
        "basis_note": "经营财务快照：按业务单据、应收应付余额、库存余额和收付款汇总；不是完整法定总账、科目余额表、纳税申报表或工资/固定资产账。",
        "income_statement": {
            "title": "经营利润快照",
            "rows": [
                {"item": "销售订单收入（含税业务口径）", "amount": str(revenue)},
                {"item": "采购成本", "amount": str(purchase_cost)},
                {"item": "工单成本", "amount": str(work_order_cost)},
                {"item": "委外成本", "amount": str(subcontract_cost)},
                {"item": "售后成本", "amount": str(service_cost)},
                {"item": "经营成本合计", "amount": str(cost)},
                {"item": "经营毛利", "amount": str(gross_profit)},
            ],
        },
        "balance_sheet": {
            "title": "经营资产负债快照",
            "rows": [
                {"item": "资金净流入", "amount": str(cash_balance)},
                {"item": "应收余额", "amount": str(receivable_balance)},
                {"item": "库存成本余额", "amount": str(inventory_amount)},
                {"item": "经营资产估算", "amount": str(cash_balance + receivable_balance + inventory_amount)},
                {"item": "应付余额", "amount": str(payable_balance)},
                {"item": "经营权益估算", "amount": str(cash_balance + receivable_balance + inventory_amount - payable_balance)},
            ],
        },
        "cash_flow_statement": {
            "title": "经营现金流快照",
            "rows": [
                {"item": "客户收款", "amount": str(cash_in)},
                {"item": "供应商付款", "amount": str(cash_out)},
                {"item": "经营现金净流入", "amount": str(cash_balance)},
            ],
        },
        "summary": {
            "revenue": str(revenue),
            "cost": str(cost),
            "gross_profit": str(gross_profit),
            "receivable_balance": str(receivable_balance),
            "payable_balance": str(payable_balance),
            "cash_in": str(cash_in),
            "cash_out": str(cash_out),
            "net_cash_flow": str(cash_balance),
            "inventory_cost_balance": str(inventory_amount),
            "operating_assets": str(operating_assets),
            "operating_equity": str(operating_equity),
        },
    }


def ensure_accounting_period(query_one, execute_db, year, month):
    row = query_one("SELECT id FROM accounting_periods WHERE year=%s AND month=%s", (year, month))
    if row:
        return row.get("id")
    execute_db(
        "INSERT INTO accounting_periods (year, month, status) VALUES (%s,%s,'open') ON CONFLICT (year, month) DO NOTHING",
        (year, month),
    )
    row = query_one("SELECT id FROM accounting_periods WHERE year=%s AND month=%s", (year, month))
    return row.get("id") if row else None


def save_financial_reports(execute_db, period_id, payload, status="generated"):
    for report_type in ("income_statement", "balance_sheet", "cash_flow_statement"):
        execute_db(
            """
            INSERT INTO financial_reports (report_type, period_id, data, status, created_at)
            VALUES (%s,%s,%s::jsonb,%s,NOW())
            ON CONFLICT (period_id, report_type)
            DO UPDATE SET data=EXCLUDED.data, status=EXCLUDED.status, created_at=NOW()
            """,
            (report_type, period_id, json.dumps(payload.get(report_type, {}), ensure_ascii=False), status),
        )


def render_finance_period_close(query_one, query_rows, execute_db):
    today = date.today()
    try:
        year = int(request.args.get("year") or today.year)
    except (TypeError, ValueError):
        year = today.year
    try:
        month = int(request.args.get("month") or today.month)
    except (TypeError, ValueError):
        month = today.month
    payload = build_financial_statement_payload(query_one, year, month)
    period_id = ensure_accounting_period(query_one, execute_db, year, month)
    pre_close_checks = build_period_close_checks(query_one, year, month, payload)
    period_close_validation = build_period_close_validation(query_one, year, month, payload)
    closes = query_rows(
        """
        SELECT id, period_label, status, revenue, cost, gross_profit,
               receivable_balance, payable_balance, cash_in, cash_out, net_cash_flow,
               closed_at, remark
        FROM finance_period_closes
        ORDER BY period_label DESC
        LIMIT 18
        """
    )
    current_close = query_one("SELECT * FROM finance_period_closes WHERE period_label=%s", (payload["period_label"],))
    return render_template(
        "finance_period_close.html",
        title="期间结账",
        subtitle="按会计期间生成经营财务快照；结账只锁定一期经营口径，不提供完整法定总账、税务、工资或固定资产月结。",
        year=year,
        month=month,
        period_id=period_id,
        period_label=payload["period_label"],
        payload=payload,
        summary=payload["summary"],
        pre_close_checks=pre_close_checks,
        period_close_validation=period_close_validation,
        closes=closes,
        current_close=current_close,
    )


def _exchange_adjustment_status_label(value):
    return {
        "draft": "草稿",
        "checked": "已检查",
        "audited": "已审核",
        "voided": "已作废",
    }.get((value or "").strip(), value or "-")


def _exchange_adjustment_direction_label(value):
    return {"gain": "汇兑收益", "loss": "汇兑损失"}.get((value or "").strip(), value or "-")


def _next_exchange_adjustment_no(query_one, year, month):
    prefix = f"TH-{year:04d}{month:02d}"
    row = query_one(
        "SELECT doc_no FROM finance_exchange_adjustments WHERE doc_no LIKE %s ORDER BY doc_no DESC LIMIT 1",
        (prefix + "-%",),
    )
    seq = 1
    if row and row.get("doc_no"):
        try:
            seq = int(str(row["doc_no"]).rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}-{seq:03d}"


def _exchange_period_from_request():
    today = date.today()
    try:
        year = int(request.values.get("year") or today.year)
    except (TypeError, ValueError):
        year = today.year
    try:
        month = int(request.values.get("month") or today.month)
    except (TypeError, ValueError):
        month = today.month
    return year, month


def _exchange_adjustment_candidates(query_rows):
    rows = query_rows(
        """
        SELECT id, account_code, account_name, account_type, bank_name,
               bank_account_no, currency, current_balance, account_id, account_code_link
        FROM cash_bank_accounts
        WHERE status='active'
          AND COALESCE(NULLIF(currency,''),'CNY') <> 'CNY'
        ORDER BY currency, account_code, id
        """
    )
    for row in rows:
        currency = (row.get("currency") or "").strip() or "CNY"
        row["book_rate"] = as_decimal(request.values.get(f"book_rate_{row['id']}") or "1")
        row["closing_rate"] = as_decimal(request.values.get(f"closing_rate_{currency}") or request.values.get(f"closing_rate_{row['id']}") or "1")
        row["foreign_balance"] = as_decimal(row.get("current_balance"))
        row["book_base_amount"] = row["foreign_balance"] * row["book_rate"]
        row["closing_base_amount"] = row["foreign_balance"] * row["closing_rate"]
        row["adjustment_amount"] = row["closing_base_amount"] - row["book_base_amount"]
        row["direction"] = "gain" if row["adjustment_amount"] >= 0 else "loss"
        row["direction_label"] = _exchange_adjustment_direction_label(row["direction"])
    return rows


def _exchange_adjustment_totals(rows):
    total_gain = sum(as_decimal(row.get("adjustment_amount")) for row in rows if as_decimal(row.get("adjustment_amount")) > 0)
    total_loss = sum(abs(as_decimal(row.get("adjustment_amount"))) for row in rows if as_decimal(row.get("adjustment_amount")) < 0)
    return {
        "account_count": len(rows),
        "currency_count": len({row.get("currency") for row in rows}),
        "total_gain": total_gain,
        "total_loss": total_loss,
        "net_adjustment": total_gain - total_loss,
    }


def render_finance_exchange_adjustment(query_one, query_rows):
    year, month = _exchange_period_from_request()
    rows = _exchange_adjustment_candidates(query_rows)
    totals = _exchange_adjustment_totals(rows)
    current_doc = query_one(
        """
        SELECT id, doc_no, doc_date, period_label, status, total_gain, total_loss,
               net_adjustment, voucher_no, audited_at, remark
        FROM finance_exchange_adjustments
        WHERE period_year=%s AND period_month=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (year, month),
    )
    if current_doc:
        current_doc["status_label"] = _exchange_adjustment_status_label(current_doc.get("status"))
    history = query_rows(
        """
        SELECT id, doc_no, doc_date, period_label, status, total_gain, total_loss,
               net_adjustment, voucher_no, audited_at
        FROM finance_exchange_adjustments
        ORDER BY period_year DESC, period_month DESC, id DESC
        LIMIT 12
        """
    )
    for row in history:
        row["status_label"] = _exchange_adjustment_status_label(row.get("status"))
    return render_template(
        "finance_exchange_adjustment.html",
        title="期末调汇",
        subtitle="按外币资金账户余额和期末汇率生成调汇单；审核后生成调汇凭证，调汇单查询页只做检索和导出。",
        year=year,
        month=month,
        period_label=period_label(year, month),
        rows=rows,
        totals=totals,
        current_doc=current_doc,
        history=history,
    )


def post_finance_exchange_adjustment(query_one, query_rows, execute_db, execute_and_return, log_action):
    year, month = _exchange_period_from_request()
    action = (request.form.get("action") or "check").strip()
    rows = _exchange_adjustment_candidates(query_rows)
    rows = [row for row in rows if abs(as_decimal(row.get("adjustment_amount"))) > Decimal("0.005")]
    totals = _exchange_adjustment_totals(rows)
    if action == "check":
        flash(f"调汇前检查完成：外币账户 {len(rows)} 个，净调汇金额 {money_metric(totals['net_adjustment'])}。", "info")
        return redirect(f"/finance/exchange-adjustment?year={year}&month={month}")
    if not rows:
        flash("没有可生成调汇单的外币账户差额。", "warning")
        return redirect(f"/finance/exchange-adjustment?year={year}&month={month}")
    doc_no = _next_exchange_adjustment_no(query_one, year, month)
    doc_date = request.form.get("doc_date") or (period_bounds(year, month)[1] - timedelta(days=1)).isoformat()
    remark = (request.form.get("remark") or "").strip()
    inserted = execute_and_return(
        """
        INSERT INTO finance_exchange_adjustments
            (doc_no, doc_date, period_year, period_month, period_label, status,
             total_gain, total_loss, net_adjustment, prepared_by, remark)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            doc_no,
            doc_date,
            year,
            month,
            period_label(year, month),
            "checked" if action == "generate" else "draft",
            totals["total_gain"],
            totals["total_loss"],
            totals["net_adjustment"],
            session.get("user_id"),
            remark,
        ),
    )
    adjustment_id = returned_id(inserted)
    for idx, row in enumerate(rows, 1):
        execute_db(
            """
            INSERT INTO finance_exchange_adjustment_lines
                (adjustment_id, line_no, cash_bank_account_id, account_code, account_name,
                 currency, foreign_balance, book_rate, closing_rate, book_base_amount,
                 closing_base_amount, adjustment_amount, direction, remark)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                adjustment_id,
                idx,
                row.get("id"),
                row.get("account_code"),
                row.get("account_name"),
                row.get("currency"),
                row.get("foreign_balance"),
                row.get("book_rate"),
                row.get("closing_rate"),
                row.get("book_base_amount"),
                row.get("closing_base_amount"),
                row.get("adjustment_amount"),
                row.get("direction"),
                row.get("bank_account_no"),
            ),
        )
    log_action("生成期末调汇单", doc_no, remark)
    if action == "audit":
        return _audit_exchange_adjustment(adjustment_id, query_one, query_rows, execute_db, execute_and_return, log_action)
    flash(f"调汇单 {doc_no} 已生成。", "success")
    return redirect("/finance/exchange-adjustments")


def _audit_exchange_adjustment(adjustment_id, query_one, query_rows, execute_db, execute_and_return, log_action):
    doc = query_one(
        "SELECT * FROM finance_exchange_adjustments WHERE id=%s",
        (adjustment_id,),
    )
    if not doc:
        flash("调汇单不存在。", "warning")
        return redirect("/finance/exchange-adjustments")
    if doc.get("status") == "audited":
        flash("调汇单已审核。", "info")
        return redirect("/finance/exchange-adjustments")
    if _period_is_closed(query_one, doc.get("doc_date")):
        flash("会计期间已关闭，不能审核调汇单。", "danger")
        return redirect("/finance/exchange-adjustments")
    lines = query_rows(
        "SELECT * FROM finance_exchange_adjustment_lines WHERE adjustment_id=%s ORDER BY line_no",
        (adjustment_id,),
    )
    bank_account = _account_for_mapping(query_one, execute_and_return, "bank", "1002", "\u94f6\u884c\u5b58\u6b3e")
    exchange_account = _account_for_mapping(query_one, execute_and_return, "exchange_gain_loss", "6603", "Exchange Gain/Loss")
    voucher_lines = []
    for line in lines:
        amount = as_decimal(line.get("adjustment_amount"))
        if abs(amount) <= Decimal("0.005"):
            continue
        summary = f"期末调汇 {doc.get('period_label')} {line.get('currency')} {line.get('account_name')}"
        if amount > 0:
            voucher_lines.append({"account": bank_account, "debit_amount": amount, "credit_amount": 0, "summary": summary})
            voucher_lines.append({"account": exchange_account, "debit_amount": 0, "credit_amount": amount, "summary": summary})
        else:
            amount = abs(amount)
            voucher_lines.append({"account": exchange_account, "debit_amount": amount, "credit_amount": 0, "summary": summary})
            voucher_lines.append({"account": bank_account, "debit_amount": 0, "credit_amount": amount, "summary": summary})
    try:
        voucher_id = _insert_auto_voucher(
            query_one,
            execute_db,
            execute_and_return,
            source_type="exchange_adjustment",
            source_id=adjustment_id,
            source_no=doc.get("doc_no"),
            doc_date=doc.get("doc_date"),
            summary=f"期末调汇 {doc.get('period_label')} {doc.get('doc_no')}",
            lines=voucher_lines,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(f"/finance/exchange-adjustment?year={doc.get('period_year')}&month={doc.get('period_month')}")
    voucher = query_one("SELECT voucher_no FROM vouchers WHERE id=%s", (voucher_id,)) if voucher_id else None
    execute_db(
        """
        UPDATE finance_exchange_adjustments
        SET status='audited', voucher_id=%s, voucher_no=%s, audited_by=%s, audited_at=NOW(), updated_at=NOW()
        WHERE id=%s
        """,
        (voucher_id, (voucher or {}).get("voucher_no"), session.get("user_id"), adjustment_id),
    )
    log_action("审核期末调汇单", doc.get("doc_no"), (voucher or {}).get("voucher_no"))
    flash(f"调汇单 {doc.get('doc_no')} 已审核并生成凭证。", "success")
    return redirect("/finance/exchange-adjustments")


def render_finance_exchange_adjustment_list(query_rows):
    filters = {
        "keyword": (request.args.get("keyword") or "").strip(),
        "period": (request.args.get("period") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
    }
    where = ["1=1"]
    params = []
    if filters["keyword"]:
        where.append("(a.doc_no ILIKE %s OR a.voucher_no ILIKE %s OR l.account_name ILIKE %s OR l.currency ILIKE %s)")
        pattern = f"%{filters['keyword']}%"
        params.extend([pattern, pattern, pattern, pattern])
    if filters["period"] and "-" in filters["period"]:
        parts = filters["period"].split("-", 1)
        where.append("a.period_year=%s AND a.period_month=%s")
        params.extend([int(parts[0]), int(parts[1])])
    if filters["status"]:
        where.append("a.status=%s")
        params.append(filters["status"])
    rows = query_rows(
        f"""
        SELECT a.id, a.doc_no, a.doc_date, a.period_label, a.status, a.total_gain,
               a.total_loss, a.net_adjustment, a.voucher_no, a.audited_at,
               COUNT(l.id) AS line_count,
               STRING_AGG(DISTINCT l.currency, ', ') AS currencies
        FROM finance_exchange_adjustments a
        LEFT JOIN finance_exchange_adjustment_lines l ON l.adjustment_id=a.id
        WHERE {' AND '.join(where)}
        GROUP BY a.id
        ORDER BY a.period_year DESC, a.period_month DESC, a.id DESC
        LIMIT 300
        """,
        tuple(params),
    )
    for row in rows:
        row["status_label"] = _exchange_adjustment_status_label(row.get("status"))
        row["next_step"] = "查看凭证" if row.get("voucher_no") else "审核生成凭证"
    if _is_tabular_export_request():
        return _csv_response(rows, "exchange-adjustments")
    return render_template(
        "finance_exchange_adjustment_list.html",
        title="调汇单查询",
        subtitle="查询期末调汇单、调汇金额和凭证来源；本页只做查询、导出和跳转，不新增调汇单。",
        rows=rows,
        filters=filters,
    )


def post_finance_exchange_adjustment_audit(adjustment_id, query_one, query_rows, execute_db, execute_and_return, log_action):
    return _audit_exchange_adjustment(adjustment_id, query_one, query_rows, execute_db, execute_and_return, log_action)


def render_finance_dashboard(query_one, query_rows, count_rows, money_metric, columns, render_module_dashboard):
    _SUM_TABLES = {
        "customer_receivables": "balance",
        "supplier_payables": "balance",
    }
    def sum_value(table, field):
        if table not in _SUM_TABLES or _SUM_TABLES[table] != field:
            return 0
        row = query_one(f"SELECT COALESCE(SUM({field}), 0) AS value FROM {table}") or {}
        return row.get("value") or 0

    current_period = build_current_finance_period(query_one)
    metrics = [
        {"label": "应收余额", "value": money_metric(sum_value("customer_receivables", "balance")), "hint": "客户未回款"},
        {"label": "应付余额", "value": money_metric(sum_value("supplier_payables", "balance")), "hint": "供应商未付款"},
        {"label": "凭证数", "value": count_rows("vouchers"), "hint": "财务凭证"},
        {"label": "当前期间", "value": current_period["label"], "hint": current_period["status_label"]},
    ]
    shortcuts = [
        {"label": "应收", "url": "/receivables", "icon": "bi-wallet2"},
        {"label": "应付", "url": "/payables", "icon": "bi-cash-stack"},
        {"label": "凭证", "url": "/finance/vouchers", "icon": "bi-journal-text"},
        {"label": "期间结账", "url": "/finance/period-close", "icon": "bi-calendar-check"},
        {"label": "财务报表", "url": "/finance/financial-statements", "icon": "bi-file-earmark-bar-graph"},
    ]
    receivables = query_rows(
        """
        SELECT cr.id, cr.source_no, cr.receivable_date, cr.due_date, cr.project_code, cr.cabinet_no,
               c.name AS customer_name, cr.total_amount, cr.received_amount, cr.balance, cr.status
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE COALESCE(cr.balance, 0) > 0
        ORDER BY cr.due_date NULLS FIRST, cr.id DESC
        LIMIT 20
        """
    )
    for row in receivables:
        row["next_step"] = "核对发货/签收并登记回款"
        row["owner_role"] = "销售 / 财务"
        row["blocked_reason"] = "应收余额未清"
        row["downstream_impact"] = "影响现金流、账龄、项目毛利和期间结账"
    payables = query_rows(
        """
        SELECT sp.id, sp.doc_no, sp.doc_date, sp.project_code, sp.cabinet_no,
               s.name AS supplier_name, sp.amount, sp.paid_amount, sp.balance, sp.status
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE COALESCE(sp.balance, 0) > 0
        ORDER BY sp.next_follow_up_date NULLS FIRST, sp.id DESC
        LIMIT 20
        """
    )
    for row in payables:
        row["next_step"] = "核对收货/委外结算并安排付款"
        row["owner_role"] = "采购 / 财务"
        row["blocked_reason"] = "应付余额未清"
        row["downstream_impact"] = "影响供应商账期、项目成本和期间结账"
    vouchers = query_rows(
        """
        SELECT id, voucher_no, voucher_type, date, summary, total_debit, total_credit, status
        FROM vouchers
        ORDER BY id DESC
        LIMIT 20
        """
    )
    period_closes = query_rows(
        """
        SELECT id, period_label, status, revenue, cost, gross_profit,
               receivable_balance, payable_balance, net_cash_flow, closed_at
        FROM finance_period_closes
        ORDER BY period_label DESC
        LIMIT 12
        """
    )
    return render_module_dashboard(
        "财务",
        "按应收、应付、凭证和期间结账推进财务闭环。",
        metrics,
        shortcuts,
        [
            {
                "title": "应收跟进队列",
                "rows": receivables,
                "columns": columns(
                    ("source_no", "来源"),
                    ("customer_name", "客户"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("receivable_date", "日期"),
                    ("due_date", "到期日"),
                    ("total_amount", "应收"),
                    ("received_amount", "已收"),
                    ("balance", "余额"),
                    ("status", "状态"),
                    ("next_step", "下一步"),
                    ("owner_role", "责任"),
                    ("downstream_impact", "下游影响"),
                ),
                "detail_base": "/receivables",
            },
            {
                "title": "应付跟进队列",
                "rows": payables,
                "columns": columns(
                    ("doc_no", "来源"),
                    ("supplier_name", "供应商"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("doc_date", "日期"),
                    ("amount", "应付"),
                    ("paid_amount", "已付"),
                    ("balance", "余额"),
                    ("status", "状态"),
                    ("next_step", "下一步"),
                    ("owner_role", "责任"),
                    ("downstream_impact", "下游影响"),
                ),
                "detail_base": "/payables",
            },
            {
                "title": "最近凭证",
                "rows": vouchers,
                "columns": columns(
                    ("voucher_no", "凭证号"),
                    ("voucher_type", "类型"),
                    ("date", "日期"),
                    ("summary", "摘要"),
                    ("total_debit", "借方"),
                    ("total_credit", "贷方"),
                    ("status", "状态"),
                ),
                "detail_base": "/finance/vouchers",
            },
            {
                "title": "最近期间结账",
                "rows": period_closes,
                "columns": columns(
                    ("period_label", "期间"),
                    ("status", "状态"),
                    ("revenue", "收入"),
                    ("cost", "成本"),
                    ("gross_profit", "毛利"),
                    ("receivable_balance", "应收余额"),
                    ("payable_balance", "应付余额"),
                    ("net_cash_flow", "净现金流"),
                    ("closed_at", "结账时间"),
                ),
            },
        ],
    )


def render_receivable_detail(
    receivable_id,
    query_one,
    query_rows,
    money_metric_func,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/receivables",
):
    receivable = query_one(
        """
        SELECT cr.*, c.name AS customer_name, c.contact_person, c.phone AS customer_phone,
               co.cost_object_code, co.project_name
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        LEFT JOIN cost_objects co ON co.id=cr.cost_object_id
        WHERE cr.id=%s
        """,
        (receivable_id,),
    )
    if not receivable:
        return render_template("simple_detail.html", title="应收详情", row=None, back_url=back_url, labels={})

    settlements = query_rows(
        """
        SELECT s.id, r.receipt_no, r.receipt_date, r.source_no, r.project_code, r.cabinet_no,
               s.applied_amount, r.amount AS receipt_amount, r.payment_method, r.bank_account,
               r.status, s.created_at
        FROM customer_receipt_settlements s
        JOIN customer_receipts r ON r.id=s.receipt_id
        WHERE s.receivable_id=%s
        ORDER BY r.receipt_date DESC NULLS LAST, r.id DESC
        LIMIT 50
        """,
        (receivable_id,),
    )
    receipts = query_rows(
        """
        SELECT id, receipt_no, receipt_date, source_no, project_code, cabinet_no,
               amount, payment_method, bank_account, status, remark
        FROM customer_receipts
        WHERE customer_id=%s
          AND (
            receivable_id=%s OR source_id=%s OR source_no=%s
            OR (%s IS NOT NULL AND cost_object_id=%s)
            OR (%s IS NOT NULL AND project_code=%s)
            OR (%s IS NOT NULL AND cabinet_no=%s)
          )
        ORDER BY receipt_date DESC NULLS LAST, id DESC
        LIMIT 30
        """,
        (
            receivable.get("customer_id"),
            receivable_id,
            receivable.get("source_id"),
            receivable.get("source_no"),
            receivable.get("cost_object_id"),
            receivable.get("cost_object_id"),
            receivable.get("project_code"),
            receivable.get("project_code"),
            receivable.get("cabinet_no"),
            receivable.get("cabinet_no"),
        ),
    )
    sales_orders = query_rows(
        """
        SELECT id, order_no, order_date, project_code, cabinet_no, total_amount, shipped_amount, status
        FROM sales_orders
        WHERE id=%s OR order_no=%s
           OR (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND cabinet_no=%s)
        ORDER BY id DESC
        LIMIT 20
        """,
        (
            receivable.get("source_id"),
            receivable.get("source_no"),
            receivable.get("cost_object_id"),
            receivable.get("cost_object_id"),
            receivable.get("project_code"),
            receivable.get("project_code"),
            receivable.get("cabinet_no"),
            receivable.get("cabinet_no"),
        ),
    )
    return render_template(
        "finance_trace_detail.html",
        doc_type="应收",
        back_url=back_url,
        doc=receivable,
        doc_kind="receivable",
        action_prefix="/receivables",
        partner_label="客户",
        partner_name=receivable.get("customer_name"),
        attachments=document_attachments("receivable", receivable_id),
        activity_logs=document_activity_logs("receivable", receivable),
        metrics=[
            {"label": "应收金额", "value": money_metric_func(receivable.get("total_amount")), "hint": receivable.get("source_no") or "-"},
            {"label": "已收金额", "value": money_metric_func(receivable.get("received_amount")), "hint": "已登记回款"},
            {"label": "未收余额", "value": money_metric_func(receivable.get("balance")), "hint": receivable.get("status") or "-"},
            {"label": "到期日", "value": receivable.get("due_date") or "-", "hint": "逾期需跟进"},
        ],
        sections=[
            {
                "title": "关联销售订单",
                "rows": sales_orders,
                "columns": columns(
                    ("order_no", "销售订单"),
                    ("order_date", "日期"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("total_amount", "金额"),
                    ("shipped_amount", "已发货"),
                    ("status", "状态"),
                ),
            },
            {
                "title": "客户回款",
                "rows": settlements,
                "columns": columns(
                    ("receipt_no", "回款单"),
                    ("source_no", "来源单"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("receipt_date", "日期"),
                    ("applied_amount", "核销金额"),
                    ("receipt_amount", "回款金额"),
                    ("status", "状态"),
                    ("payment_method", "方式"),
                    ("bank_account", "账户"),
                ),
            },
            {
                "title": "相关客户回款",
                "rows": receipts,
                "columns": columns(
                    ("receipt_no", "回款单"),
                    ("source_no", "来源单"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("receipt_date", "日期"),
                    ("amount", "金额"),
                    ("status", "状态"),
                    ("payment_method", "方式"),
                    ("bank_account", "账户"),
                    ("remark", "备注"),
                ),
            },
        ],
    )


def render_payable_detail(
    payable_id,
    query_one,
    query_rows,
    money_metric_func,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/payables",
):
    payable = query_one(
        """
        SELECT sp.*, s.name AS supplier_name, s.contact_person, s.phone AS supplier_phone
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE sp.id=%s
        """,
        (payable_id,),
    )
    if not payable:
        return render_template("simple_detail.html", title="应付详情", row=None, back_url=back_url, labels={})

    payments = query_rows(
        """
        SELECT id, payment_no, payment_date, amount, payment_method, bank_account, remark
        FROM supplier_payments
        WHERE supplier_id=%s
        ORDER BY payment_date DESC NULLS LAST, id DESC
        LIMIT 30
        """,
        (payable.get("supplier_id"),),
    )
    payment_settlements = query_rows(
        """
        SELECT s.id, s.applied_amount,
               p.id AS payment_id, p.payment_no, p.payment_date, p.amount,
               p.payment_method, p.bank_account, p.remark
        FROM supplier_payment_settlements s
        JOIN supplier_payments p ON p.id=s.payment_id
        WHERE s.payable_id=%s
        ORDER BY p.payment_date DESC NULLS LAST, p.id DESC, s.id DESC
        """,
        (payable_id,),
    )
    purchase_orders = query_rows(
        """
        SELECT id, order_no, order_date, project_code, cabinet_no, total_amount, received_amount, status
        FROM purchase_orders
        WHERE id=%s OR order_no=%s
        ORDER BY id DESC
        LIMIT 20
        """,
        (payable.get("doc_id"), payable.get("doc_no")),
    )
    subcontract_orders = query_rows(
        """
        SELECT id, order_no, order_date, project_code, cabinet_no, total_amount, status
        FROM subcontract_orders
        WHERE id=%s OR order_no=%s
        ORDER BY id DESC
        LIMIT 20
        """,
        (payable.get("doc_id"), payable.get("doc_no")),
    )
    return render_template(
        "finance_trace_detail.html",
        doc_type="应付",
        back_url=back_url,
        doc=payable,
        doc_kind="payable",
        action_prefix="/payables",
        partner_label="供应商",
        partner_name=payable.get("supplier_name"),
        attachments=document_attachments("payable", payable_id),
        activity_logs=document_activity_logs("payable", payable),
        metrics=[
            {"label": "应付金额", "value": money_metric_func(payable.get("amount")), "hint": payable.get("payable_no") or payable.get("doc_no") or "-"},
            {"label": "已付金额", "value": money_metric_func(payable.get("paid_amount")), "hint": "已登记付款"},
            {"label": "未付余额", "value": money_metric_func(payable.get("balance")), "hint": payable.get("status") or "-"},
            {"label": "跟进日期", "value": payable.get("next_follow_up_date") or "-", "hint": payable.get("follow_up_status") or "-"},
        ],
        sections=[
            {
                "title": "关联采购单",
                "rows": purchase_orders,
                "columns": columns(
                    ("order_no", "采购单"),
                    ("order_date", "日期"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("total_amount", "金额"),
                    ("received_amount", "已收货"),
                    ("status", "状态"),
                ),
            },
            {
                "title": "关联委外单",
                "rows": subcontract_orders,
                "columns": columns(
                    ("order_no", "委外单"),
                    ("order_date", "日期"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("total_amount", "加工费"),
                    ("status", "状态"),
                ),
            },
            {
                "title": "付款核销明细",
                "rows": payment_settlements,
                "columns": columns(
                    ("payment_no", "付款单"),
                    ("payment_date", "日期"),
                    ("applied_amount", "核销金额"),
                    ("amount", "付款金额"),
                    ("payment_method", "方式"),
                    ("bank_account", "账户"),
                    ("remark", "备注"),
                ),
            },
            {
                "title": "付款记录",
                "rows": payments,
                "columns": columns(
                    ("payment_no", "付款单"),
                    ("payment_date", "日期"),
                    ("amount", "金额"),
                    ("payment_method", "方式"),
                    ("bank_account", "账户"),
                    ("remark", "备注"),
                ),
            },
        ],
    )


def post_profit_loss_transfer(query_one, query_rows, execute_db, execute_and_return, log_action):
    """期末结转损益：将收入/费用科目余额转入本年利润"""
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    now = date.today()
    if not year:
        year = now.year
    if not month:
        month = now.month

    # 检查是否已结账
    closed = query_one("SELECT id FROM finance_period_closes WHERE period_year=%s AND period_month=%s AND status='closed'", (year, month))
    if closed:
        flash("该期间已结账，不能执行结转损益。", "warning")
        return redirect(f"/finance/period-close?year={year}&month={month}")

    # 查找本年利润科目
    profit_account = query_one("SELECT id, code, name FROM chart_of_accounts WHERE (code='4103' OR name='本年利润') AND status='active'")
    if not profit_account:
        flash("未找到本年利润科目（编码4103），请在会计科目表中添加。", "warning")
        return redirect(f"/finance/period-close?year={year}&month={month}")

    # 检查是否已有结转凭证
    existing = query_one(
        "SELECT id FROM vouchers WHERE source_type='period_close' AND source_no=%s AND status='posted'",
        (f"profit_loss_{year}{month:02d}",),
    )
    if existing:
        flash("该期间已存在结转损益凭证，请先反过账再重新结转。", "warning")
        return redirect(f"/finance/period-close?year={year}&month={month}")

    # 获取所有收入类科目本期贷方余额
    revenue_accounts = query_rows(
        """SELECT coa.id, coa.code, coa.name,
                  COALESCE(SUM(gl.credit_amount), 0) - COALESCE(SUM(gl.debit_amount), 0) AS balance
           FROM chart_of_accounts coa
           JOIN general_ledger gl ON gl.account_id=coa.id AND gl.period_year=%s AND gl.period_month=%s
           WHERE coa.status='active' AND coa.account_type IN ('收入', 'revenue')
           GROUP BY coa.id, coa.code, coa.name
           HAVING COALESCE(SUM(gl.credit_amount), 0) - COALESCE(SUM(gl.debit_amount), 0) > 0.005
           ORDER BY coa.code""",
        (year, month),
    )

    # 获取所有费用/成本科目本期借方余额
    expense_accounts = query_rows(
        """SELECT coa.id, coa.code, coa.name,
                  COALESCE(SUM(gl.debit_amount), 0) - COALESCE(SUM(gl.credit_amount), 0) AS balance
           FROM chart_of_accounts coa
           JOIN general_ledger gl ON gl.account_id=coa.id AND gl.period_year=%s AND gl.period_month=%s
           WHERE coa.status='active' AND coa.account_type IN ('费用', '成本', '成本费用', 'expense', 'cost')
           GROUP BY coa.id, coa.code, coa.name
           HAVING COALESCE(SUM(gl.debit_amount), 0) - COALESCE(SUM(gl.credit_amount), 0) > 0.005
           ORDER BY coa.code""",
        (year, month),
    )

    if not revenue_accounts and not expense_accounts:
        flash("该期间无收入或费用发生额，无需结转。", "info")
        return redirect(f"/finance/period-close?year={year}&month={month}")

    # 生成凭证号
    voucher_no = f"JZ-{year}{month:02d}-001"
    existing_no = query_one("SELECT id FROM vouchers WHERE voucher_no=%s", (voucher_no,))
    if existing_no:
        seq = 1
        while True:
            voucher_no = f"JZ-{year}{month:02d}-{seq:03d}"
            if not query_one("SELECT id FROM vouchers WHERE voucher_no=%s", (voucher_no,)):
                break
            seq += 1
            if seq > 999:
                flash("凭证号生成失败，请清理结转凭证。", "warning")
                return redirect(f"/finance/period-close?year={year}&month={month}")

    user_id = session.get("user_id")
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    lines = []
    line_no = 0

    # 结转收入 → 本年利润
    for acc in revenue_accounts:
        bal = Decimal(str(acc.get("balance") or 0))
        line_no += 1
        lines.append((line_no, acc.get("id"), acc.get("name"), bal, Decimal("0")))
        total_debit += bal

    # 结转费用/成本 → 本年利润
    for acc in expense_accounts:
        bal = Decimal(str(acc.get("balance") or 0))
        line_no += 1
        lines.append((line_no, acc.get("id"), acc.get("name"), Decimal("0"), bal))
        total_credit += bal

    # 差额进本年利润
    net_profit = total_debit - total_credit
    if net_profit > 0:
        # 亏损：借本年利润
        line_no += 1
        lines.append((line_no, profit_account["id"], "结转本期损益", net_profit, Decimal("0")))
        total_credit += net_profit
    elif net_profit < 0:
        # 盈利：贷本年利润
        line_no += 1
        lines.append((line_no, profit_account["id"], "结转本期损益", Decimal("0"), abs(net_profit)))
        total_debit += abs(net_profit)

    # 创建凭证
    source_no = f"profit_loss_{year}{month:02d}"
    row = execute_and_return(
        """INSERT INTO vouchers (voucher_no, voucher_date, date, voucher_type, period_year, period_month,
           total_debit, total_credit, source_type, source_no, summary, status, prepared_by, reviewed_at, posted_by, posted_at)
           VALUES (%s,%s,%s,'结转凭证',%s,%s,%s,%s,'period_close',%s,'期末结转损益','posted',%s,NOW(),%s,NOW()) RETURNING id""",
        (voucher_no, f"{year}-{month:02d}-{_month_last_day(year, month):02d}", f"{year}-{month:02d}-{_month_last_day(year, month):02d}",
         year, month, float(total_debit), float(total_credit), source_no, user_id, user_id),
    )
    if not row:
        raise RuntimeError("结转凭证插入失败")
    voucher_id = row["id"] if isinstance(row, dict) else row[0]

    # 插入凭证明细行 + 写入总账
    for ln, acc_id, summary, debit, credit in lines:
        execute_db(
            "INSERT INTO voucher_lines (voucher_id, line_no, account_id, summary, debit_amount, credit_amount) VALUES (%s,%s,%s,%s,%s,%s)",
            (voucher_id, ln, acc_id, summary, float(debit), float(credit)),
        )
        # 查找科目编码和名称
        acc_info = query_one("SELECT code, name FROM chart_of_accounts WHERE id=%s", (acc_id,))
        execute_db(
            """INSERT INTO general_ledger (voucher_id, account_id, account_code, account_name,
               entry_date, period_year, period_month, debit_amount, credit_amount, summary, voucher_no)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (voucher_id, acc_id, acc_info["code"] if acc_info else "", acc_info["name"] if acc_info else "",
             f"{year}-{month:02d}-{_month_last_day(year, month):02d}", year, month,
             float(debit), float(credit), summary, voucher_no),
        )

    log_action("期末结转损益", voucher_no)
    flash(f"结转凭证 {voucher_no} 已生成并过账。净利润 {net_profit:.2f}", "success")
    return redirect(f"/finance/period-close?year={year}&month={month}")


def _month_last_day(year, month):
    """返回指定月份的最后一天"""
    import calendar
    return calendar.monthrange(year, month)[1]


def post_finance_period_close(query_one, execute_db, log_action):
    year = int((request.form.get("year") or date.today().year))
    month = int((request.form.get("month") or date.today().month))
    action = (request.form.get("action") or "generate").strip()
    remark = (request.form.get("remark") or "").strip()
    if session.get("role") not in ALLOWED_PERIOD_CLOSE_ROLES:
        flash("仅管理员、主管或财务角色可执行期间结账。", "error")
        return redirect(f"/finance/period-close?year={year}&month={month}")
    period_id = ensure_accounting_period(query_one, execute_db, year, month)
    payload = build_financial_statement_payload(query_one, year, month)
    summary = payload["summary"]
    period_close_validation = build_period_close_validation(query_one, year, month, payload)
    if action in PERIOD_CLOSE_LOCK_ACTIONS and not period_close_validation["can_close"]:
        flash("期间存在结账阻断项，已停止审核锁定；请先处理负库存、缺成本或凭证不平。", "error")
        return redirect(f"/finance/period-close?year={year}&month={month}")
    status = "closed" if action in PERIOD_CLOSE_LOCK_ACTIONS else "generated"
    def operation(cursor):
        _tx_query_one, _tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
        save_financial_reports(tx_execute_db, period_id, payload, status=status)
        tx_execute_db(
            """
            INSERT INTO finance_period_closes
                (period_id, period_label, status, revenue, cost, gross_profit,
                 receivable_balance, payable_balance, cash_in, cash_out, net_cash_flow,
                 report_payload, remark, closed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,CASE WHEN %s='closed' THEN NOW() ELSE NULL END)
            ON CONFLICT (period_label)
            DO UPDATE SET period_id=EXCLUDED.period_id, status=EXCLUDED.status,
                revenue=EXCLUDED.revenue, cost=EXCLUDED.cost, gross_profit=EXCLUDED.gross_profit,
                receivable_balance=EXCLUDED.receivable_balance, payable_balance=EXCLUDED.payable_balance,
                cash_in=EXCLUDED.cash_in, cash_out=EXCLUDED.cash_out, net_cash_flow=EXCLUDED.net_cash_flow,
                report_payload=EXCLUDED.report_payload, remark=EXCLUDED.remark,
                closed_at=CASE WHEN EXCLUDED.status='closed' THEN NOW() ELSE finance_period_closes.closed_at END
            """,
            (
                period_id,
                payload["period_label"],
                status,
                summary["revenue"],
                summary["cost"],
                summary["gross_profit"],
                summary["receivable_balance"],
                summary["payable_balance"],
                summary["cash_in"],
                summary["cash_out"],
                summary["net_cash_flow"],
                json.dumps(payload, ensure_ascii=False),
                remark,
                status,
            ),
        )
        if action in PERIOD_CLOSE_LOCK_ACTIONS:
            tx_execute_db("UPDATE accounting_periods SET status='closed', closed_at=NOW() WHERE id=%s", (period_id,))

    _run_finance_funds_transaction(operation)
    if action in PERIOD_CLOSE_LOCK_ACTIONS:
        log_action("期间结账审核/锁定", payload["period_label"], remark)
        flash("期间已审核并锁定，经营财务快照已保存。反结账当前仅允许管理员按审计流程处理。", "success")
    else:
        log_action("生成经营财务快照", payload["period_label"], remark)
        flash("经营财务快照已生成，尚未审核锁定。", "success")
    return redirect(f"/finance/period-close?year={year}&month={month}")


def render_detail_ledger(query_rows, query_one):
    """明细账：按科目展示每笔发生额及余额滚存"""
    account_id = request.args.get("account_id", type=int)
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    now = date.today()
    if not year:
        year = now.year
    if not month:
        month = now.month

    accounts = query_rows("SELECT id, code, name, account_type FROM chart_of_accounts WHERE status='active' ORDER BY code")
    rows = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    opening_balance = Decimal("0")
    ending_balance = Decimal("0")
    account_info = None

    if account_id:
        account_info = query_one("SELECT id, code, name, account_type FROM chart_of_accounts WHERE id=%s", (account_id,))

        # Calculate opening balance from期初余额表 + prior GL entries
        ob = query_one(
            "SELECT opening_debit, opening_credit FROM account_opening_balances WHERE account_id=%s AND year=%s AND month=1",
            (account_id, year),
        )
        if ob:
            opening_balance = Decimal(str(ob.get("opening_debit") or 0)) - Decimal(str(ob.get("opening_credit") or 0))
        # Add prior periods within this year (if month > 1)
        if month > 1:
            prior = query_one(
                """SELECT COALESCE(SUM(debit_amount), 0) AS d, COALESCE(SUM(credit_amount), 0) AS c
                   FROM general_ledger WHERE account_id=%s AND period_year=%s AND period_month>=1 AND period_month<%s""",
                (account_id, year, month),
            )
            if prior:
                opening_balance += Decimal(str(prior.get("d") or 0)) - Decimal(str(prior.get("c") or 0))

        is_debit_nature = (account_info["account_type"] or "") in ("资产", "成本", "费用", "成本费用", "expense", "cost")
        direction = "借" if is_debit_nature else "贷"

        # Query GL entries
        where = ["gl.account_id=%s"]
        params = [account_id]
        if month > 0:
            where.append("gl.period_year=%s AND gl.period_month=%s")
            params.extend([year, month])
        else:
            where.append("gl.period_year=%s")
            params.append(year)

        gl_rows = query_rows(
            f"SELECT gl.* FROM general_ledger gl WHERE {' AND '.join(where)} ORDER BY gl.entry_date, gl.voucher_id, gl.id",
            tuple(params),
        )
        running = opening_balance
        for r in gl_rows:
            d = Decimal(str(r.get("debit_amount") or 0))
            c = Decimal(str(r.get("credit_amount") or 0))
            if is_debit_nature:
                running = running + d - c
            else:
                running = running + c - d
            total_debit += d
            total_credit += c
            rows.append({
                **r,
                "running_balance": running,
            })

        if is_debit_nature:
            ending_balance = opening_balance + total_debit - total_credit
        else:
            ending_balance = opening_balance + total_credit - total_debit

    return render_template(
        "finance_detail_ledger.html",
        title="明细账",
        subtitle="按会计科目查看每笔发生额及余额滚存。",
        year=year,
        month=month,
        accounts=accounts,
        selected_account_id=account_id,
        account_info=account_info,
        opening_balance=opening_balance,
        rows=rows,
        total_debit=total_debit,
        total_credit=total_credit,
        ending_balance=ending_balance,
    )


def render_opening_balances(query_rows, query_one, execute_db):
    """期初余额管理"""
    year = request.args.get("year", type=int)
    account_type = (request.args.get("account_type") or "").strip()
    now = date.today()
    if not year:
        year = now.year

    # Check if year is locked
    closed = query_one("SELECT COUNT(*) as cnt FROM accounting_periods WHERE year=%s AND status='closed'", (year,))
    year_locked = closed and closed.get("cnt", 0) > 0

    # Get all active accounts with their current opening balances
    accounts = query_rows(
        """SELECT coa.id, coa.code, coa.name, coa.account_type,
                  COALESCE(ob.opening_debit, 0) AS opening_debit,
                  COALESCE(ob.opening_credit, 0) AS opening_credit
           FROM chart_of_accounts coa
           LEFT JOIN account_opening_balances ob ON ob.account_id=coa.id AND ob.year=%s AND ob.month=1
           WHERE coa.status='active'
           ORDER BY coa.code""",
        (year,),
    )
    for a in accounts:
        atype = a["account_type"] or ""
        a["direction"] = "借" if atype in ("资产", "成本", "费用", "成本费用", "expense", "cost") else "贷"
        a["locked"] = year_locked

    account_types = sorted(set(a["account_type"] for a in accounts))
    filtered = accounts
    if account_type:
        filtered = [a for a in accounts if a["account_type"] == account_type]

    return render_template(
        "finance_opening_balances.html",
        title="期初余额管理",
        subtitle=f"{year}年各科目年初余额。已结账年份不可修改。",
        year=year,
        rows=filtered,
        account_types=account_types,
        selected_account_type=account_type,
        locked=year_locked,
    )


def post_opening_balances(query_one, execute_db, log_action):
    """保存期初余额"""
    year = request.args.get("year", date.today().year, type=int)
    user_id = session.get("user_id")
    saved = 0
    for key in request.form:
        if key.startswith("opening_debit_"):
            account_id = int(key.replace("opening_debit_", ""))
            debit = as_decimal(request.form.get(f"opening_debit_{account_id}", "0"))
            credit = as_decimal(request.form.get(f"opening_credit_{account_id}", "0"))
            execute_db(
                """INSERT INTO account_opening_balances (account_id, year, month, opening_debit, opening_credit, created_by, updated_by)
                   VALUES (%s,%s,1,%s,%s,%s,%s)
                   ON CONFLICT (account_id, year, month)
                   DO UPDATE SET opening_debit=%s, opening_credit=%s, updated_by=%s, updated_at=NOW()""",
                (account_id, year, float(debit), float(credit), user_id, user_id,
                 float(debit), float(credit), user_id),
            )
            saved += 1
    log_action("更新期初余额", f"{year}年 {saved}个科目")
    flash(f"已保存 {saved} 个科目的期初余额。", "success")
    return redirect(f"/finance/opening-balances?year={year}")


def render_general_ledger(query_rows, query_one):
    """总账明细查询"""
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    account_id = request.args.get("account_id", type=int)
    keyword = (request.args.get("keyword") or "").strip()
    now = date.today()
    if not year:
        year = now.year
    if not month:
        month = now.month
    where = ["period_year=%s", "period_month=%s"]
    params = [year, month]
    if account_id:
        where.append("gl.account_id=%s")
        params.append(account_id)
    if keyword:
        where.append("(gl.summary ILIKE %s OR gl.voucher_no ILIKE %s OR gl.project_code ILIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    rows = query_rows(
        f"""SELECT gl.* FROM general_ledger gl
            WHERE {' AND '.join(where)}
            ORDER BY gl.entry_date, gl.voucher_id, gl.id LIMIT 1000""",
        tuple(params),
    )
    total_debit = sum(Decimal(str(r.get("debit_amount") or 0)) for r in rows)
    total_credit = sum(Decimal(str(r.get("credit_amount") or 0)) for r in rows)
    accounts = query_rows("SELECT id, code, name FROM chart_of_accounts WHERE status='active' ORDER BY code")
    return render_template(
        "finance_general_ledger.html",
        title="总账明细",
        subtitle=f"{year}年{month}月过账凭证明细。",
        view_mode="gl",
        year=year,
        month=month,
        rows=rows,
        total_debit=total_debit,
        total_credit=total_credit,
        accounts=accounts,
        selected_account_id=account_id,
        keyword=keyword,
    )


def render_account_balance_summary(query_rows, query_one):
    """科目余额表"""
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    account_type = (request.args.get("account_type") or "").strip()
    now = date.today()
    if not year:
        year = now.year
    if not month:
        month = now.month

    # opening balance = 期初余额表 + 本年度当期之前的GL
    opening = query_rows(
        """SELECT coa.id, coa.code, coa.name, coa.account_type,
                  COALESCE(ob.opening_debit, 0) + COALESCE(SUM(gl.debit_amount), 0) AS prior_debit,
                  COALESCE(ob.opening_credit, 0) + COALESCE(SUM(gl.credit_amount), 0) AS prior_credit
           FROM chart_of_accounts coa
           LEFT JOIN account_opening_balances ob ON ob.account_id=coa.id AND ob.year=%s AND ob.month=1
           LEFT JOIN general_ledger gl ON gl.account_id=coa.id AND gl.period_year=%s AND gl.period_month>=1 AND gl.period_month<%s
           WHERE coa.status='active'
           GROUP BY coa.id, coa.code, coa.name, coa.account_type, ob.opening_debit, ob.opening_credit
           ORDER BY coa.code""",
        (year, year, month),
    )
    # current period movement
    current = query_rows(
        """SELECT gl.account_id,
                  COALESCE(SUM(gl.debit_amount), 0) AS period_debit,
                  COALESCE(SUM(gl.credit_amount), 0) AS period_credit
           FROM general_ledger gl
           WHERE gl.period_year=%s AND gl.period_month=%s
           GROUP BY gl.account_id""",
        (year, month),
    )
    current_map = {r["account_id"]: r for r in current}
    rows = []
    for o in opening:
        c = current_map.get(o["id"], {"period_debit": 0, "period_credit": 0})
        prior_debit = Decimal(str(o.get("prior_debit") or 0))
        prior_credit = Decimal(str(o.get("prior_credit") or 0))
        period_debit = Decimal(str(c.get("period_debit") or 0))
        period_credit = Decimal(str(c.get("period_credit") or 0))
        atype = o.get("account_type") or ""
        # debit-nature: asset(资产), cost(成本), expense(费用/支出)
        # credit-nature: liability(负债), equity(权益), revenue(收入)
        is_debit_nature = atype in ("资产", "成本费用", "费用", "成本", "expense", "cost")
        if is_debit_nature:
            opening_bal = prior_debit - prior_credit
            ending_bal = opening_bal + period_debit - period_credit
            direction = "借"
        else:
            opening_bal = prior_credit - prior_debit
            ending_bal = opening_bal + period_credit - period_debit
            direction = "贷"
        if abs(prior_debit) < 0.005 and abs(prior_credit) < 0.005 and abs(period_debit) < 0.005 and abs(period_credit) < 0.005:
            continue  # skip zero-balance accounts with no activity
        rows.append({
            "id": o["id"],
            "code": o["code"],
            "name": o["name"],
            "account_type": atype,
            "balance_direction": direction,
            "opening_balance": opening_bal,
            "period_debit": period_debit,
            "period_credit": period_credit,
            "ending_balance": ending_bal,
        })

    account_types = sorted(set(r["account_type"] for r in rows))
    filtered_rows = rows
    if account_type:
        filtered_rows = [r for r in rows if r["account_type"] == account_type]

    return render_template(
        "finance_general_ledger.html",
        title="科目余额表",
        subtitle=f"{year}年{month}月各科目期初余额、发生额及期末余额。",
        view_mode="balance",
        year=year,
        month=month,
        rows=filtered_rows,
        account_types=account_types,
        selected_account_type=account_type,
    )


def render_trial_balance(query_rows, query_one):
    """试算平衡表"""
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    now = date.today()
    if not year:
        year = now.year
    if not month:
        month = now.month

    rows = query_rows(
        """SELECT coa.id, coa.code, coa.name, coa.account_type,
                  COALESCE(SUM(gl.debit_amount), 0) AS debit,
                  COALESCE(SUM(gl.credit_amount), 0) AS credit
           FROM chart_of_accounts coa
           LEFT JOIN general_ledger gl ON gl.account_id=coa.id AND gl.period_year=%s AND gl.period_month=%s
           WHERE coa.status='active'
           GROUP BY coa.id, coa.code, coa.name, coa.account_type
           HAVING COALESCE(SUM(gl.debit_amount), 0) > 0 OR COALESCE(SUM(gl.credit_amount), 0) > 0
           ORDER BY coa.code""",
        (year, month),
    )
    total_debit = sum(Decimal(str(r.get("debit") or 0)) for r in rows)
    total_credit = sum(Decimal(str(r.get("credit") or 0)) for r in rows)
    diff = total_debit - total_credit
    balanced = abs(diff) < Decimal("0.01")

    return render_template(
        "finance_general_ledger.html",
        title="试算平衡表",
        subtitle=f"{year}年{month}月试算平衡验证。" if balanced else f"{year}年{month}月试算不平衡！",
        view_mode="trial_balance",
        year=year,
        month=month,
        rows=rows,
        total_debit=total_debit,
        total_credit=total_credit,
        diff=diff,
        balanced=balanced,
    )


def render_financial_statements(query_one, query_rows, execute_db):
    today = date.today()
    try:
        year = int(request.args.get("year") or today.year)
    except (TypeError, ValueError):
        year = today.year
    try:
        month = int(request.args.get("month") or today.month)
    except (TypeError, ValueError):
        month = today.month
    period_id = ensure_accounting_period(query_one, execute_db, year, month)
    reports = query_rows(
        """
        SELECT report_type, data, status, created_at
        FROM financial_reports
        WHERE period_id=%s
        ORDER BY report_type
        """,
        (period_id,),
    )
    if not reports:
        payload = build_financial_statement_payload(query_one, year, month)
        reports = [
            {"report_type": "income_statement", "data": payload["income_statement"], "status": "preview", "created_at": None},
            {"report_type": "balance_sheet", "data": payload["balance_sheet"], "status": "preview", "created_at": None},
            {"report_type": "cash_flow_statement", "data": payload["cash_flow_statement"], "status": "preview", "created_at": None},
        ]
    else:
        payload = build_financial_statement_payload(query_one, year, month)
    return render_template(
        "financial_statements.html",
        title="经营财务快照",
        subtitle="按销售、采购、工单、委外、售后、应收应付、库存和收付款汇总展示；不是完整法定财务三表。",
        year=year,
        month=month,
        period_label=period_label(year, month),
        payload=payload,
        reports=reports,
    )


def render_voucher_list(query_rows):
    keyword = (request.args.get("keyword") or "").strip()
    status = (request.args.get("status") or "").strip()
    period = (request.args.get("period") or "").strip()
    where = ["1=1"]
    params = []
    if status:
        where.append("status=%s")
        params.append(status)
    if keyword:
        pattern = f"%{keyword}%"
        where.append("(voucher_no ILIKE %s OR summary ILIKE %s OR source_type ILIKE %s)")
        params.extend([pattern, pattern, pattern])
    if period:
        parts = period.split("-")
        if len(parts) == 2:
            where.append("period_year=%s AND period_month=%s")
            params.extend([int(parts[0]), int(parts[1])])
    rows = query_rows(
        f"SELECT id, voucher_no, voucher_date, voucher_type, period_year, period_month, "
        f"total_debit, total_credit, source_type, source_no, summary, "
        f"'只读追溯' AS finance_audit_marker, "
        f"status AS status "
        f"FROM vouchers WHERE {' AND '.join(where)} ORDER BY voucher_date DESC, id DESC LIMIT 300",
        tuple(params),
    )
    periods = query_rows(
        "SELECT DISTINCT period_year, period_month FROM vouchers ORDER BY period_year DESC, period_month DESC LIMIT 24"
    )
    return render_template(
        "simple_list.html",
        title="记账凭证",
        subtitle="凭证来源只读查询；暂不提供手工录入、复核、过账、反过账。",
        rows=rows,
        columns=[
            {"key": "finance_audit_marker", "label": "凭证草稿 只读 来源追溯 不提供过账"},
            {"key": "voucher_no", "label": "凭证号"},
            {"key": "voucher_date", "label": "日期"},
            {"key": "voucher_type", "label": "凭证类型"},
            {"key": "summary", "label": "摘要"},
            {"key": "total_debit", "label": "借方金额"},
            {"key": "total_credit", "label": "贷方金额"},
            {"key": "status", "label": "状态"},
        ],
        detail_base="/finance/vouchers",
    )


def render_voucher_form(query_rows, query_one, execute_db, voucher_id=None, readonly=True):
    """渲染凭证录入/编辑/详情页面"""
    from datetime import date as dt_date
    today = dt_date.today().strftime("%Y-%m-%d")
    current_period = f"{dt_date.today().year}-{dt_date.today().month:02d}"

    voucher = None
    lines = []
    if voucher_id:
        voucher = query_one("SELECT * FROM vouchers WHERE id=%s", (voucher_id,))
        if not voucher:
            flash("凭证不存在。", "warning")
            return redirect("/finance/vouchers")
        lines = query_rows(
            """SELECT vl.*, coa.code AS account_code, coa.name AS account_name
               FROM voucher_lines vl
               LEFT JOIN chart_of_accounts coa ON coa.id=vl.account_id
               WHERE vl.voucher_id=%s ORDER BY vl.line_no""",
            (voucher_id,),
        )

    periods = query_rows(
        "SELECT DISTINCT year AS period_year, month AS period_month FROM accounting_periods WHERE status='open' ORDER BY year DESC, month DESC LIMIT 12"
    )
    period_options = [{"value": f"{p['period_year']}-{p['period_month']:02d}", "label": f"{p['period_year']}年{p['period_month']:02d}月"} for p in periods]

    return render_template(
        "voucher_form.html",
        voucher=voucher,
        lines=lines,
        today=today,
        current_period=current_period,
        periods=period_options,
        readonly=readonly,
    )


def _parse_voucher_form():
    """从表单提取凭证数据，返回 (header_dict, lines_list)"""
    h = {
        "voucher_no": (request.form.get("voucher_no") or "").strip(),
        "voucher_date": (request.form.get("voucher_date") or "").strip(),
        "voucher_type": (request.form.get("voucher_type") or "记账凭证").strip(),
        "summary": (request.form.get("summary") or "").strip(),
        "remark": (request.form.get("remark") or "").strip(),
        "status": (request.form.get("status") or "草稿").strip(),
    }
    period = (request.form.get("period") or "").strip()
    if "-" in period:
        parts = period.split("-")
        h["period_year"] = int(parts[0])
        h["period_month"] = int(parts[1])
    source_info = (request.form.get("source_info") or "").strip()
    if ":" in source_info:
        h["source_type"], h["source_no"] = source_info.split(":", 1)
    else:
        h["source_type"] = h["source_no"] = None

    lines = []
    # collect all line data by scanning form keys
    line_ids = set()
    for key in request.form:
        if key.startswith("line_account_id_"):
            ln = key.replace("line_account_id_", "")
            try:
                line_ids.add(int(ln))
            except ValueError:
                pass
    for ln in sorted(line_ids):
        account_id = request.form.get(f"line_account_id_{ln}")
        if not account_id:
            continue
        try:
            account_id = int(account_id)
        except (ValueError, TypeError):
            continue
        debit = as_decimal(request.form.get(f"line_debit_{ln}", "0"))
        credit = as_decimal(request.form.get(f"line_credit_{ln}", "0"))
        if debit == 0 and credit == 0:
            continue
        lines.append({
            "line_no": ln,
            "account_id": account_id,
            "summary": (request.form.get(f"line_summary_{ln}") or "").strip(),
            "debit_amount": float(debit),
            "credit_amount": float(credit),
        })
    return h, lines


def _next_voucher_no(query_one, prefix="PZ"):
    """生成凭证号"""
    today = date.today()
    base = f"{prefix}-{today:%Y%m%d}"
    row = query_one(
        "SELECT voucher_no FROM vouchers WHERE voucher_no LIKE %s ORDER BY id DESC LIMIT 1",
        (f"{base}%",),
    )
    if row and row.get("voucher_no"):
        try:
            seq = int(row["voucher_no"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{base}-{seq:03d}"


def save_voucher(query_one, query_rows, execute_db, execute_and_return, next_doc_no_fn, log_action, voucher_id=None):
    header, lines = _parse_voucher_form()
    if not header["voucher_no"]:
        return jsonify({"ok": False, "error": "凭证号必填。"})
    if not header["voucher_date"]:
        return jsonify({"ok": False, "error": "凭证日期必填。"})
    if not lines:
        return jsonify({"ok": False, "error": "请至少添加一行会计分录。"})

    total_debit = sum(line["debit_amount"] for line in lines)
    total_credit = sum(line["credit_amount"] for line in lines)
    period_error = _period_write_error(query_one, header["voucher_date"])
    if period_error:
        return jsonify({"ok": False, "error": period_error})
    if abs(total_debit - total_credit) > 0.005:
        return jsonify({"ok": False, "error": f"借贷不平衡！借方={total_debit:.2f} 贷方={total_credit:.2f}"})
    if total_debit < 0.005:
        return jsonify({"ok": False, "error": "借贷金额均为零。"})

    if voucher_id:
        existing = query_one("SELECT * FROM vouchers WHERE id=%s", (voucher_id,))
        if not existing:
            return jsonify({"ok": False, "error": "凭证不存在。"})
        if existing.get("status") not in ("草稿",):
            return jsonify({"ok": False, "error": "只能编辑草稿状态的凭证。"})
        dup = query_one("SELECT id FROM vouchers WHERE voucher_no=%s AND id!=%s", (header["voucher_no"], voucher_id))
        if dup:
            return jsonify({"ok": False, "error": f"凭证号 {header['voucher_no']} 已存在。"})
        status_val = header.get("status", "draft")
        is_reviewed = status_val == "audited"
        execute_db(
            """UPDATE vouchers SET voucher_no=%s, voucher_date=%s, voucher_type=%s,
               period_year=%s, period_month=%s, total_debit=%s, total_credit=%s,
               source_type=%s, source_no=%s, summary=%s, status=%s,
               reviewed_at=CASE WHEN %s THEN NOW() ELSE NULL END,
               remark=%s, updated_at=NOW()
               WHERE id=%s""",
            (header["voucher_no"], header["voucher_date"], header["voucher_type"],
             header.get("period_year"), header.get("period_month"),
             total_debit, total_credit, header.get("source_type"), header.get("source_no"),
             header["summary"], status_val, is_reviewed, header["remark"], voucher_id),
        )
        execute_db("DELETE FROM voucher_lines WHERE voucher_id=%s", (voucher_id,))
        target_id = voucher_id
        action = "更新凭证"
    else:
        dup = query_one("SELECT id FROM vouchers WHERE voucher_no=%s", (header["voucher_no"],))
        if dup:
            return jsonify({"ok": False, "error": f"凭证号 {header['voucher_no']} 已存在。"})
        user_id = session.get("user_id")
        status_val = header.get("status", "draft")
        is_reviewed = status_val == "audited"
        row = execute_and_return(
            """INSERT INTO vouchers (voucher_no, voucher_date, date, voucher_type,
               period_year, period_month, total_debit, total_credit, source_type, source_no,
               summary, status, prepared_by, reviewed_at, remark)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN NOW() ELSE NULL END,%s) RETURNING id""",
            (header["voucher_no"], header["voucher_date"], header["voucher_date"], header["voucher_type"],
             header.get("period_year"), header.get("period_month"),
             total_debit, total_credit, header.get("source_type"), header.get("source_no"),
             header["summary"], status_val, user_id, is_reviewed, header["remark"]),
        )
        if not row:
            raise RuntimeError("凭证插入失败")
        target_id = row["id"] if isinstance(row, dict) else row[0]
        action = "新增凭证"

    for line in lines:
        execute_db(
            "INSERT INTO voucher_lines (voucher_id, line_no, account_id, summary, debit_amount, credit_amount) VALUES (%s,%s,%s,%s,%s,%s)",
            (target_id, line["line_no"], line["account_id"], line["summary"], line["debit_amount"], line["credit_amount"]),
        )

    log_action(action, header["voucher_no"])
    return jsonify({"ok": True, "id": target_id, "message": "保存成功"})


def post_voucher_to_gl(voucher_id, query_one, query_rows, execute_db, log_action):
    """过账凭证到总账"""
    voucher = query_one("SELECT * FROM vouchers WHERE id=%s FOR UPDATE", (voucher_id,))
    if not voucher:
        return jsonify({"ok": False, "error": "凭证不存在。"})
    if voucher["status"] == "posted":
        return jsonify({"ok": False, "error": "凭证已过账，不能重复过账。"})
    if voucher["status"] == "closed":
        return jsonify({"ok": False, "error": "已作废的凭证不能过账。"})

    period_error = _period_write_error(query_one, voucher.get("voucher_date"))
    if period_error:
        return jsonify({"ok": False, "error": period_error})

    lines = query_rows(
        """SELECT vl.*, coa.code AS account_code, coa.name AS account_name
           FROM voucher_lines vl
           LEFT JOIN chart_of_accounts coa ON coa.id=vl.account_id
           WHERE vl.voucher_id=%s ORDER BY vl.line_no""",
        (voucher_id,),
    )
    if not lines:
        return jsonify({"ok": False, "error": "凭证无明细行。"})

    user_id = session.get("user_id")
    execute_db("DELETE FROM general_ledger WHERE voucher_id=%s", (voucher_id,))
    # insert into general_ledger
    for line in lines:
        execute_db(
            """INSERT INTO general_ledger (voucher_id, account_id, account_code, account_name,
               entry_date, period_year, period_month, debit_amount, credit_amount, summary,
               project_code, cabinet_no, voucher_no, source_type, source_id, source_no)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (voucher_id, line["account_id"], line.get("account_code"), line.get("account_name"),
             voucher["voucher_date"], voucher.get("period_year"), voucher.get("period_month"),
             line["debit_amount"], line["credit_amount"], line.get("summary"),
             line.get("project_code"), line.get("cabinet_no"), voucher["voucher_no"],
             voucher.get("source_type"), voucher.get("source_id"), voucher.get("source_no")),
        )

    execute_db(
        "UPDATE vouchers SET status='posted', posted_by=%s, posted_at=NOW(), updated_at=NOW() WHERE id=%s",
        (user_id, voucher_id),
    )
    log_action("凭证过账", voucher["voucher_no"])
    return jsonify({"ok": True, "message": "过账成功"})


def unreview_voucher(voucher_id, query_one, execute_db, log_action):
    """撤销复核"""
    voucher = query_one("SELECT * FROM vouchers WHERE id=%s", (voucher_id,))
    if not voucher:
        return jsonify({"ok": False, "error": "凭证不存在。"})
    if voucher["status"] != "audited":
        return jsonify({"ok": False, "error": "只有已复核的凭证才能撤销复核。"})
    execute_db(
        "UPDATE vouchers SET status='draft', reviewed_at=NULL, reviewed_by=NULL, updated_at=NOW() WHERE id=%s",
        (voucher_id,),
    )
    log_action("撤销凭证复核", voucher["voucher_no"])
    return jsonify({"ok": True, "message": "已撤销复核"})


def reverse_post_voucher(voucher_id, query_one, execute_db, log_action):
    """反过账"""
    voucher = query_one("SELECT * FROM vouchers WHERE id=%s FOR UPDATE", (voucher_id,))
    if not voucher:
        return jsonify({"ok": False, "error": "凭证不存在。"})
    if voucher["status"] != "posted":
        return jsonify({"ok": False, "error": "只有已过账的凭证才能反过账。"})

    period_error = _period_write_error(query_one, voucher.get("voucher_date"))
    if period_error:
        return jsonify({"ok": False, "error": period_error})

    execute_db("DELETE FROM general_ledger WHERE voucher_id=%s", (voucher_id,))
    execute_db(
        "UPDATE vouchers SET status='audited', posted_by=NULL, posted_at=NULL, updated_at=NOW() WHERE id=%s",
        (voucher_id,),
    )
    log_action("凭证反过账", voucher["voucher_no"])
    return jsonify({"ok": True, "message": "反过账成功"})


def void_voucher(voucher_id, query_one, execute_db, log_action):
    """作废凭证"""
    voucher = query_one("SELECT * FROM vouchers WHERE id=%s FOR UPDATE", (voucher_id,))
    if not voucher:
        return jsonify({"ok": False, "error": "凭证不存在。"})
    status = voucher.get("status")
    if status == "posted":
        return jsonify({"ok": False, "error": "已过账的凭证不能直接作废，请先反过账。"})
    if status == "closed":
        return jsonify({"ok": False, "error": "凭证已经作废，无需重复操作。"})

    execute_db(
        "UPDATE vouchers SET status='closed', updated_at=NOW() WHERE id=%s",
        (voucher_id,),
    )
    log_action("作废凭证", voucher["voucher_no"])
    return jsonify({"ok": True, "message": "凭证已作废"})


def cash_bank_account_type_label(value):
    return {"cash": "现金", "bank": "银行账户"}.get((value or "").strip(), value or "-")


def cash_bank_status_label(value):
    return {
        "active": "启用",
        "inactive": "停用",
        "closed": "已销户",
        "confirmed": "已确认",
    }.get((value or "").strip(), value or "-")


def cash_bank_direction_label(value):
    return {"in": "收入", "out": "支出"}.get((value or "").strip(), value or "-")


def cash_bank_source_label(value):
    return {
        "cash_bank_journal": "现金银行流水",
        "customer_receipt": "客户收款单",
        "customer_advance_receipt": "预收款单",
        "customer_receipt_refund": "收款退款单",
        "customer_advance_refund": "预收退款单",
        "customer_other_income": "其他收入单",
        "customer_other_income_refund": "其他收入退款单",
        "supplier_payment": "供应商付款单",
        "supplier_advance_payment": "预付款单",
        "supplier_payment_refund": "付款退款单",
        "supplier_advance_refund": "预付退款单",
        "supplier_other_expense": "其他支出单",
        "supplier_other_expense_refund": "其他支出退款单",
        "sales_order": "销售订单",
        "purchase_order": "采购订单",
        "receivable": "应收单",
        "payable": "应付单",
    }.get((value or "").strip(), value or "-")


def cash_bank_source_url(source_type, source_id, source_no):
    source_type = (source_type or "").strip()
    ar_routes = {config["source_type"]: config["detail_base"] for config in AR_RECEIPT_DOCUMENT_TYPES.values()}
    ap_routes = {config["source_type"]: config["detail_base"] for config in AP_PAYMENT_DOCUMENT_TYPES.values()}
    if source_type in ar_routes and source_id:
        return f"{ar_routes[source_type]}/{source_id}"
    if source_type in ap_routes and source_id:
        return f"{ap_routes[source_type]}/{source_id}"
    if source_type == "receivable" and source_id:
        return f"/receivables/{source_id}"
    if source_type == "payable" and source_id:
        return f"/payables/{source_id}"
    if source_type == "sales_order" and source_id:
        return f"/sales-orders/{source_id}"
    if source_type == "purchase_order" and source_id:
        return f"/purchase-orders/{source_id}"
    if source_type in ar_routes and source_no:
        return f"{ar_routes[source_type]}?keyword={source_no}"
    if source_type in ap_routes and source_no:
        return f"{ap_routes[source_type]}?keyword={source_no}"
    return None


def _cash_bank_account_for_label(query_one, execute_db, bank_account, created_by=None):
    label = (bank_account or "").strip()
    if not label:
        raise ValueError("cash_bank_account_required")
    row = query_one(
        """
        SELECT id
        FROM cash_bank_accounts
        WHERE status='active'
          AND (
              account_code=%s
              OR account_name=%s
              OR bank_account_no=%s
          )
        ORDER BY id
        LIMIT 1
        """,
        (label, label, label),
    )
    if not row:
        raise ValueError("cash_bank_account_not_found")
    return row.get("id")


def _cash_bank_account_validation_response(query_one, bank_account, redirect_url):
    try:
        _cash_bank_account_for_label(query_one, None, bank_account)
    except ValueError:
        flash("Please maintain an active cash/bank account before saving this receipt or payment.", "warning")
        return redirect(redirect_url)
    return None


def _cash_bank_accounts_validation_response(query_one, fund_lines, redirect_url):
    for line in fund_lines or []:
        try:
            _cash_bank_account_for_label(query_one, None, line.get("bank_account"))
        except ValueError:
            flash(f"Please maintain an active cash/bank account for funds line {line.get('line_no') or 1}.", "warning")
            return redirect(redirect_url)
    return None


def _cash_bank_journal_entry_no(prefix, source_no, line_no, line_count):
    return f"{prefix}-{source_no}-{line_no}" if line_count > 1 else f"{prefix}-{source_no}"


def _upsert_cash_bank_journal_for_funds(query_one, execute_db, *, source_type, source_id, source_no, doc_date, direction, amount, bank_account, partner_type, partner_name, project_code, cabinet_no, summary, created_by):
    _upsert_cash_bank_journal_for_funds_lines(
        query_one,
        execute_db,
        source_type=source_type,
        source_id=source_id,
        source_no=source_no,
        doc_date=doc_date,
        direction=direction,
        fund_lines=[{"line_no": 1, "amount": amount, "bank_account": bank_account, "transaction_no": "", "remark": ""}],
        partner_type=partner_type,
        partner_name=partner_name,
        project_code=project_code,
        cabinet_no=cabinet_no,
        summary=summary,
        created_by=created_by,
    )


def _upsert_cash_bank_journal_for_funds_lines(query_one, execute_db, *, source_type, source_id, source_no, doc_date, direction, fund_lines, partner_type, partner_name, project_code, cabinet_no, summary, created_by):
    execute_db("DELETE FROM cash_bank_journal_entries WHERE source_type=%s AND source_no=%s", (source_type, source_no))
    prefix = "CBR" if direction == "in" else "CBP"
    active_lines = [line for line in (fund_lines or []) if as_decimal(line.get("amount")) > 0]
    line_count = len(active_lines)
    for index, line in enumerate(active_lines, start=1):
        account_id = _cash_bank_account_for_label(query_one, execute_db, line.get("bank_account"), created_by)
        line_no = line.get("line_no") or index
        entry_no = _cash_bank_journal_entry_no(prefix, source_no, line_no, line_count)
        line_summary_parts = [summary]
        if line_count > 1:
            line_summary_parts.append(f"funds line {line_no}")
        if line.get("transaction_no"):
            line_summary_parts.append(f"txn {line.get('transaction_no')}")
        if line.get("remark"):
            line_summary_parts.append(str(line.get("remark")))
        line_summary = " | ".join(part for part in line_summary_parts if part)
        amount = as_decimal(line.get("amount"))
        if as_decimal(line.get("fee_amount")) > 0:
            line_summary = f"{line_summary} | fee {as_decimal(line.get('fee_amount'))}"
        execute_db(
            """
            INSERT INTO cash_bank_journal_entries
                (account_id, entry_date, entry_no, source_type, source_no, direction, amount,
                 partner_type, partner_name, project_code, cabinet_no, summary, status, created_by,
                 source_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (account_id, doc_date, entry_no, source_type, source_no, direction, amount, partner_type, partner_name, project_code, cabinet_no, line_summary, created_by, source_id),
        )


def _mark_cash_bank_journal_status(execute_db, source_type, source_no, status, summary_suffix):
    execute_db(
        """
        UPDATE cash_bank_journal_entries
        SET status=%s,
            summary=COALESCE(summary,'') || %s
        WHERE source_type=%s AND source_no=%s AND COALESCE(status,'') <> %s
        """,
        (status, summary_suffix, source_type, source_no, status),
    )


def cash_bank_keyword_clause(keyword, columns, start_index=1):
    if not keyword:
        return "", []
    pattern = f"%{keyword}%"
    clauses = [f"COALESCE({column}::text,'') ILIKE %s" for column in columns]
    return " AND (" + " OR ".join(clauses) + ")", [pattern for _ in columns]


def cash_bank_filter_args():
    return {
        "keyword": (request.args.get("keyword") or "").strip(),
        "account_id": (request.args.get("account_id") or "").strip(),
        "account_type": (request.args.get("account_type") or "").strip(),
        "direction": (request.args.get("direction") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }


def render_cash_bank_accounts(query_rows, query_one):
    filters = cash_bank_filter_args()
    params = []
    where = ["1=1"]
    if filters["account_type"] in {"cash", "bank"}:
        where.append("account_type=%s")
        params.append(filters["account_type"])
    if filters["keyword"]:
        clause, clause_params = cash_bank_keyword_clause(
            filters["keyword"],
            ["account_code", "account_name", "bank_name", "bank_account_no", "owner_department", "owner_person"],
        )
        where.append(clause.replace(" AND ", "", 1))
        params.extend(clause_params)
    rows = query_rows(
        f"""
        SELECT id, account_code, account_name, account_type, bank_name, bank_branch,
               bank_account_no, currency, opening_balance, current_balance, status,
               owner_department, owner_person, remark, updated_at
        FROM cash_bank_accounts
        WHERE {' AND '.join(where)}
        ORDER BY account_type, account_code, id
        LIMIT 200
        """,
        tuple(params),
    )
    for row in rows:
        row["account_type_label"] = cash_bank_account_type_label(row.get("account_type"))
        row["status_label"] = cash_bank_status_label(row.get("status"))
    summary = query_one(
        """
        SELECT COUNT(*) AS account_count,
               COALESCE(SUM(CASE WHEN status='active' THEN current_balance ELSE 0 END),0) AS active_balance,
               COALESCE(SUM(CASE WHEN account_type='cash' THEN current_balance ELSE 0 END),0) AS cash_balance,
               COALESCE(SUM(CASE WHEN account_type='bank' THEN current_balance ELSE 0 END),0) AS bank_balance
        FROM cash_bank_accounts
        """
    ) or {}
    return render_template(
        "cash_bank_accounts.html",
        title="现金银行账户",
        subtitle="现金/银行账户主数据，维护资金账户口径，不承载收付款单据录入。",
        rows=rows,
        summary=summary,
        filters=filters,
    )


def post_cash_bank_account(execute_db, log_action):
    account_id = (request.form.get("account_id") or "").strip()
    account_code = (request.form.get("account_code") or "").strip()
    account_name = (request.form.get("account_name") or "").strip()
    account_type = (request.form.get("account_type") or "bank").strip()
    status = (request.form.get("status") or "active").strip()
    if not account_code or not account_name:
        flash("账户编码和账户名称不能为空。", "danger")
        return redirect("/finance/cash-bank/accounts")
    if account_type not in {"cash", "bank"}:
        account_type = "bank"
    if status not in {"active", "inactive", "closed"}:
        status = "active"
    params = (
        account_code,
        account_name,
        account_type,
        (request.form.get("bank_name") or "").strip(),
        (request.form.get("bank_branch") or "").strip(),
        (request.form.get("bank_account_no") or "").strip(),
        (request.form.get("currency") or "CNY").strip() or "CNY",
        as_decimal(request.form.get("opening_balance")),
        as_decimal(request.form.get("current_balance")),
        status,
        (request.form.get("owner_department") or "").strip(),
        (request.form.get("owner_person") or "").strip(),
        (request.form.get("remark") or "").strip(),
        session.get("user_id"),
    )
    if account_id:
        execute_db(
            """
            UPDATE cash_bank_accounts
            SET account_code=%s, account_name=%s, account_type=%s, bank_name=%s,
                bank_branch=%s, bank_account_no=%s, currency=%s, opening_balance=%s,
                current_balance=%s, status=%s, owner_department=%s, owner_person=%s,
                remark=%s, updated_at=NOW()
            WHERE id=%s
            """,
            params[:-1] + (account_id,),
        )
        log_action("维护现金银行账户", account_code, "更新账户主数据")
    else:
        execute_db(
            """
            INSERT INTO cash_bank_accounts
                (account_code, account_name, account_type, bank_name, bank_branch,
                 bank_account_no, currency, opening_balance, current_balance, status,
                 owner_department, owner_person, remark, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (account_code)
            DO UPDATE SET account_name=EXCLUDED.account_name, account_type=EXCLUDED.account_type,
                bank_name=EXCLUDED.bank_name, bank_branch=EXCLUDED.bank_branch,
                bank_account_no=EXCLUDED.bank_account_no, currency=EXCLUDED.currency,
                opening_balance=EXCLUDED.opening_balance, current_balance=EXCLUDED.current_balance,
                status=EXCLUDED.status, owner_department=EXCLUDED.owner_department,
                owner_person=EXCLUDED.owner_person, remark=EXCLUDED.remark, updated_at=NOW()
            """,
            params,
        )
        log_action("维护现金银行账户", account_code, "新增或更新账户主数据")
    flash("现金银行账户已保存。", "success")
    return redirect("/finance/cash-bank/accounts")


def render_cash_bank_journal(query_rows):
    filters = cash_bank_filter_args()
    account_rows = query_rows(
        """
        SELECT id, account_code, account_name, account_type
        FROM cash_bank_accounts
        ORDER BY account_type, account_code, id
        """
    )
    params = []
    journal_where = ["1=1"]
    if filters["account_id"].isdigit():
        journal_where.append("j.account_id=%s")
        params.append(int(filters["account_id"]))
    if filters["direction"] in {"in", "out"}:
        journal_where.append("j.direction=%s")
        params.append(filters["direction"])
    if filters["date_from"]:
        journal_where.append("j.entry_date >= %s")
        params.append(filters["date_from"])
    if filters["date_to"]:
        journal_where.append("j.entry_date <= %s")
        params.append(filters["date_to"])
    if filters["keyword"]:
        clause, clause_params = cash_bank_keyword_clause(
            filters["keyword"],
            ["j.entry_no", "j.source_no", "j.partner_name", "j.project_code", "j.cabinet_no", "j.summary", "a.account_name"],
        )
        journal_where.append(clause.replace(" AND ", "", 1))
        params.extend(clause_params)
    journal_rows = query_rows(
        f"""
        SELECT j.id, j.entry_date, j.entry_no, j.source_type, j.source_no, j.direction,
               j.amount, j.balance_after, j.partner_type, j.partner_name, j.project_code, j.cabinet_no,
               j.summary, j.status, a.account_code, a.account_name, a.account_type,
               cr.id AS receipt_id, cr.receipt_no, cr.source_no AS receipt_source_no,
               cr.project_code AS receipt_project_code, cr.cabinet_no AS receipt_cabinet_no,
               c.name AS customer_name,
               sp.id AS payment_id, sp.payment_no, sp.source_no AS payment_source_no,
               sp.project_code AS payment_project_code, sp.cabinet_no AS payment_cabinet_no,
               s.name AS supplier_name
        FROM cash_bank_journal_entries j
        LEFT JOIN cash_bank_accounts a ON a.id=j.account_id
        LEFT JOIN customer_receipts cr
            ON j.source_type IN ('customer_receipt','customer_advance_receipt','customer_receipt_refund','customer_advance_refund','customer_other_income','customer_other_income_refund')
           AND (cr.receipt_no=j.source_no OR cr.id::text=j.source_no)
        LEFT JOIN customers c ON c.id=cr.customer_id
        LEFT JOIN supplier_payments sp
            ON j.source_type IN ('supplier_payment','supplier_advance_payment','supplier_payment_refund','supplier_advance_refund','supplier_other_expense','supplier_other_expense_refund')
           AND (sp.payment_no=j.source_no OR sp.id::text=j.source_no)
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE {' AND '.join(journal_where)}
        ORDER BY j.entry_date DESC, j.id DESC
        LIMIT 300
        """,
        tuple(params),
    )

    legacy_params = []
    legacy_filters = []
    if filters["date_from"]:
        legacy_filters.append("doc_date >= %s")
        legacy_params.append(filters["date_from"])
    if filters["date_to"]:
        legacy_filters.append("doc_date <= %s")
        legacy_params.append(filters["date_to"])
    if filters["direction"] in {"in", "out"}:
        legacy_filters.append("direction=%s")
        legacy_params.append(filters["direction"])
    if filters["keyword"]:
        clause, clause_params = cash_bank_keyword_clause(
            filters["keyword"],
            ["doc_no", "source_no", "partner_name", "project_code", "cabinet_no", "bank_account", "summary"],
        )
        legacy_filters.append(clause.replace(" AND ", "", 1))
        legacy_params.extend(clause_params)
    legacy_where = " AND ".join(legacy_filters) if legacy_filters else "1=1"
    legacy_rows = query_rows(
        f"""
        SELECT *
        FROM (
            SELECT cr.id, cr.receipt_date AS doc_date, cr.receipt_no AS doc_no,
                   'customer_receipt' AS source_type, cr.source_no, 'in' AS direction,
                   cr.amount, c.name AS partner_name, cr.project_code, cr.cabinet_no,
                   cr.bank_account, cr.payment_method, cr.remark AS summary, cr.status
            FROM customer_receipts cr
            LEFT JOIN customers c ON c.id=cr.customer_id
            UNION ALL
            SELECT sp.id, sp.payment_date AS doc_date, sp.payment_no AS doc_no,
                   'supplier_payment' AS source_type, NULL::VARCHAR AS source_no, 'out' AS direction,
                   sp.amount, s.name AS partner_name, NULL::VARCHAR AS project_code, NULL::VARCHAR AS cabinet_no,
                   sp.bank_account, sp.payment_method, sp.remark AS summary, sp.status
            FROM supplier_payments sp
            LEFT JOIN suppliers s ON s.id=sp.supplier_id
        ) legacy_cash
        WHERE {legacy_where}
        ORDER BY doc_date DESC NULLS LAST, id DESC
        LIMIT 300
        """,
        tuple(legacy_params),
    )
    rows = []
    ar_source_types = {config["source_type"] for config in AR_RECEIPT_DOCUMENT_TYPES.values()}
    ap_source_types = {config["source_type"] for config in AP_PAYMENT_DOCUMENT_TYPES.values()}
    for row in journal_rows:
        item = dict(row)
        if item.get("source_type") in ar_source_types:
            item["source_id"] = item.get("receipt_id")
            item["source_doc_no"] = item.get("receipt_no") or item.get("source_no")
            item["settlement_source_no"] = item.get("receipt_source_no")
            item["partner_name"] = item.get("partner_name") or item.get("customer_name")
            item["partner_type_label"] = "客户"
            item["project_code"] = item.get("project_code") or item.get("receipt_project_code")
            item["cabinet_no"] = item.get("cabinet_no") or item.get("receipt_cabinet_no")
        elif item.get("source_type") in ap_source_types:
            item["source_id"] = item.get("payment_id")
            item["source_doc_no"] = item.get("payment_no") or item.get("source_no")
            item["settlement_source_no"] = item.get("payment_source_no")
            item["partner_name"] = item.get("partner_name") or item.get("supplier_name")
            item["partner_type_label"] = "供应商"
            item["project_code"] = item.get("project_code") or item.get("payment_project_code")
            item["cabinet_no"] = item.get("cabinet_no") or item.get("payment_cabinet_no")
        else:
            item["source_id"] = None
            item["source_doc_no"] = item.get("source_no")
            item["settlement_source_no"] = None
            item["partner_type_label"] = item.get("partner_type") or "-"
        item["source_label"] = cash_bank_source_label(item.get("source_type"))
        item["source_url"] = cash_bank_source_url(item.get("source_type"), item.get("source_id"), item.get("source_doc_no"))
        item["direction_label"] = cash_bank_direction_label(item.get("direction"))
        item["status_label"] = cash_bank_status_label(item.get("status"))
        item["doc_date"] = item.get("entry_date")
        item["doc_no"] = item.get("entry_no")
        item["bank_account"] = item.get("account_name")
        rows.append(item)
    for row in legacy_rows:
        item = dict(row)
        item["source_id"] = item.get("id")
        item["source_doc_no"] = item.get("doc_no")
        item["source_url"] = cash_bank_source_url(item.get("source_type"), item.get("source_id"), item.get("source_doc_no"))
        item["settlement_source_no"] = item.get("source_no")
        item["partner_type_label"] = "客户" if item.get("source_type") in ar_source_types else "供应商"
        item["source_label"] = cash_bank_source_label(item.get("source_type"))
        item["direction_label"] = cash_bank_direction_label(item.get("direction"))
        item["status_label"] = item.get("status") or "-"
        item["account_code"] = "-"
        item["account_name"] = item.get("bank_account") or item.get("payment_method") or "-"
        item["balance_after"] = None
        rows.append(item)
    rows.sort(key=lambda item: (str(item.get("doc_date") or ""), int(item.get("id") or 0)), reverse=True)
    rows = rows[:300]
    total_in = sum(as_decimal(row.get("amount")) for row in rows if row.get("direction") == "in")
    total_out = sum(as_decimal(row.get("amount")) for row in rows if row.get("direction") == "out")
    return render_template(
        "cash_bank_journal.html",
        title="现金银行流水",
        subtitle="现金/银行日记账查询，只做资金流水核对；收付款业务单据仍在应收应付流程内处理。",
        rows=rows,
        accounts=account_rows,
        filters=filters,
        total_in=total_in,
        total_out=total_out,
        net_amount=total_in - total_out,
    )


def _counterparty_keyword_filter(alias, fields, keyword):
    if not keyword:
        return "", []
    pattern = f"%{keyword}%"
    clauses = [f"COALESCE({alias}.{field}::text,'') ILIKE %s" for field in fields]
    return " AND (" + " OR ".join(clauses) + ")", [pattern for _ in fields]


def _columns(*items):
    return [{"key": key, "label": label} for key, label in items]


def _finance_report_filters(default_date_field="date"):
    return {
        "keyword": (request.args.get("keyword") or request.args.get("q") or "").strip(),
        "date_from": (request.args.get("date_from") or request.args.get("date_start") or "").strip(),
        "date_to": (request.args.get("date_to") or request.args.get("date_end") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "project": (request.args.get("project") or "").strip(),
        "date_field": (request.args.get("date_field") or default_date_field).strip(),
    }


def _finance_report_date_where(column, filters, params):
    where = []
    if filters["date_from"]:
        where.append(f"{column} >= %s")
        params.append(filters["date_from"])
    if filters["date_to"]:
        where.append(f"{column} <= %s")
        params.append(filters["date_to"])
    return where


def _settlement_status(total, settled, balance):
    balance_value = as_decimal(balance)
    settled_value = as_decimal(settled)
    if balance_value <= 0:
        return "已结清"
    if settled_value > 0:
        return "部分核销"
    return "未核销"


def _aging_bucket(days):
    value = as_decimal(days)
    if value < 0:
        return "未到期"
    if value <= 30:
        return "0-30天"
    if value <= 60:
        return "31-60天"
    if value <= 90:
        return "61-90天"
    if value <= 180:
        return "91-180天"
    return "180天以上"


def _bad_debt_rate(days):
    value = as_decimal(days)
    if value <= 30:
        return Decimal("0.00")
    if value <= 60:
        return Decimal("0.01")
    if value <= 90:
        return Decimal("0.03")
    if value <= 180:
        return Decimal("0.05")
    return Decimal("0.10")


def _is_tabular_export_request():
    return request.args.get("export") in {"csv", "xlsx", "excel"} or request.args.get("format") in {"csv", "xlsx", "excel"}


def _render_finance_report(title, subtitle, metrics, sections, actions=None):
    if _is_tabular_export_request():
        export_rows = []
        for section in sections:
            for row in section.get("rows") or []:
                item = {"报表分区": section.get("title") or title}
                for column in section.get("columns") or []:
                    item[column["label"]] = row.get(column["key"])
                export_rows.append(item)
        return _csv_response(export_rows, title)
    return render_template(
        "finance_counterparty_tools.html",
        title=title,
        subtitle=subtitle,
        metrics=metrics,
        sections=sections,
        actions=[
            {"label": "引出", "href": f"{request.path}?export=csv"},
            {"label": "XLSX", "href": f"{request.path}?export=xlsx"},
            {"label": "刷新", "href": request.full_path if request.query_string else request.path},
            *(actions or []),
        ],
    )


def _finance_workflow_rows(*rows):
    return [
        {
            "module": row[0],
            "task": row[1],
            "path": row[2],
            "control_point": row[3],
            "status": row[4] if len(row) > 4 else "已纳入财务导航",
        }
        for row in rows
    ]


def _render_finance_workflow_page(title, subtitle, rows, actions=None):
    live_count = sum(1 for row in rows if "已" in (row.get("status") or "") or "只读" in (row.get("status") or ""))
    return _render_finance_report(
        title,
        subtitle,
        [
            {"label": "功能项", "value": len(rows), "hint": "本页覆盖的业务点"},
            {"label": "已接入", "value": live_count, "hint": "菜单/路由/只读报表"},
            {"label": "边界", "value": "只读优先", "hint": "不自动过账、不绕过审批"},
        ],
        [
            {
                "title": title,
                "rows": rows,
                "columns": _columns(
                    ("module", "模块"),
                    ("task", "功能/报表"),
                    ("path", "入口"),
                    ("control_point", "控制点"),
                    ("status", "状态"),
                ),
            }
        ],
        actions=actions,
    )


def render_finance_todo_documents():
    rows = _finance_workflow_rows(
        ("应收", "待审核应收单", "/finance/receivables", "先确认来源订单、客户、项目号和到期日", "沿用应收单列表审核状态"),
        ("收款", "待审核收款单", "/finance/receipts", "确认收款账户、结算方式和核销明细", "沿用收款单列表审核状态"),
        ("应付", "待审核应付单", "/finance/payables", "核对采购/委外来源、供应商和税额", "沿用应付单列表审核状态"),
        ("付款", "待审核付款单", "/finance/payments", "付款前核对申请、账户、供应商余额", "沿用付款单列表审核状态"),
        ("发票", "待审核销售/采购发票", "/finance/invoice-matching", "发票与订单、入库、应收应付勾稽", "只读勾稽工作台"),
        ("总账", "待生成凭证业务单据", "/finance/vouchers/generate", "只预览凭证来源，不自动过账", "只读预览"),
    )
    return _render_finance_workflow_page("待审核单据", "汇总财务人员日常需要处理的应收、应付、收付款、发票和凭证待办。", rows)


def render_business_exceptions_report():
    rows = _finance_workflow_rows(
        ("\u5e94\u6536", "\u903e\u671f\u5e94\u6536\u9884\u8b66", "/finance/reports/receivable-warning", "\u6309\u5230\u671f\u65e5\u3001\u5ba2\u6237\u3001\u9879\u76ee\u53f7\u548c\u673a\u53f7\u67e5\u770b\u903e\u671f\u672a\u6536", "\u53ea\u8bfb\u9884\u8b66"),
        ("\u5e94\u4ed8", "\u903e\u671f\u5e94\u4ed8\u9884\u8b66", "/finance/reports/payable-warning", "\u6309\u4f9b\u5e94\u5546\u3001\u91c7\u8d2d\u6765\u6e90\u548c\u9879\u76ee\u8ffd\u8e2a\u8d85\u671f\u672a\u4ed8", "\u53ea\u8bfb\u9884\u8b66"),
        ("\u53d1\u7968", "\u672a\u5f00\u7968\u9500\u552e", "/finance/unbilled-sales", "\u9500\u552e\u5df2\u53d1\u8d27\u6216\u5df2\u786e\u8ba4\uff0c\u4f46\u672a\u767b\u8bb0\u9500\u552e\u53d1\u7968", "\u53ea\u8bfb\u6838\u5bf9"),
        ("\u53d1\u7968", "\u672a\u5230\u7968\u91c7\u8d2d", "/finance/unreceived-purchase-invoices", "\u91c7\u8d2d\u5165\u5e93\u6216\u59d4\u5916\u6536\u8d27\u540e\uff0c\u672a\u767b\u8bb0\u91c7\u8d2d\u53d1\u7968", "\u53ea\u8bfb\u6838\u5bf9"),
        ("\u5b58\u8d27", "\u5b58\u8d27\u4e0e\u603b\u8d26\u5bf9\u8d26", "/finance/inventory-reconciliation", "\u5bf9\u6bd4\u5e93\u5b58\u6210\u672c\u3001\u5b58\u8d27\u79d1\u76ee\u548c\u5f02\u5e38\u5dee\u5f02", "\u53ea\u8bfb\u68c0\u67e5"),
        ("\u8d44\u91d1", "\u9879\u76ee\u8d44\u91d1\u5360\u7528", "/finance/reports/project-capital-occupation", "\u6309\u9879\u76ee\u67e5\u770b\u5e94\u6536\u3001\u5e94\u4ed8\u3001\u5b58\u8d27\u5360\u7528\u548c\u8d44\u91d1\u98ce\u9669", "\u53ea\u8bfb\u5206\u6790"),
    )
    return _render_finance_workflow_page(
        "\u4e1a\u52a1\u8d22\u52a1\u5f02\u5e38",
        "\u96c6\u4e2d\u5c55\u793a\u5e94\u6536\u3001\u5e94\u4ed8\u3001\u53d1\u7968\u3001\u5b58\u8d27\u548c\u9879\u76ee\u8d44\u91d1\u7684\u4e1a\u52a1\u8d22\u52a1\u5f02\u5e38\u5165\u53e3\uff1b\u672c\u9875\u53ea\u8bfb\uff0c\u4e0d\u6267\u884c\u7ed3\u8d26\u3001\u8fc7\u8d26\u6216\u6838\u9500\u3002",
        rows,
    )


def render_unbilled_sales_report():
    rows = _finance_workflow_rows(
        ("销售", "未开票销售订单", "/sales-orders", "销售已确认但尚未登记销售发票", "只读核对"),
        ("销售", "销售发票登记", "/finance/sales-invoices", "登记后继续形成应收/税额/凭证来源", "已接入"),
        ("应收", "应收单追踪", "/finance/receivables", "防止开票与应收脱节", "已接入"),
    )
    return _render_finance_workflow_page("未开票销售", "按金蝶式发票管理口径提供未开票销售核对入口，避免收入、应收和税额漏登记。", rows)


def render_unreceived_purchase_invoice_report():
    rows = _finance_workflow_rows(
        ("采购", "未到票采购/入库", "/purchase-orders", "采购入库或委外收货后跟踪采购发票", "只读核对"),
        ("采购发票", "采购发票登记", "/finance/purchase-invoices", "到票后登记税额、供应商和应付来源", "已接入"),
        ("应付", "应付单追踪", "/finance/payables", "防止到票、入库、应付不一致", "已接入"),
    )
    return _render_finance_workflow_page("未到票采购", "跟踪采购入库/委外收货后尚未收到采购发票的业务，支撑应付和进项税核对。", rows)


def render_invoice_matching_report():
    rows = _finance_workflow_rows(
        ("销售勾稽", "销售订单 → 销售发票 → 应收单 → 收款单", "/finance/reports/sales-collection-reconciliation", "开票金额不得超过可开票金额，收款不得超过应收余额", "已接入核对表"),
        ("采购勾稽", "采购订单/入库 → 采购发票 → 应付单 → 付款单", "/finance/reports/purchase-payment-reconciliation", "付款申请、付款单不得脱离供应商余额", "已接入核对表"),
        ("税额勾稽", "销项/进项发票明细与税额汇总", "/finance/reports/tax-summary", "只做内部登记核对，不做税控申报", "只读报表"),
    )
    return _render_finance_workflow_page("发票勾稽", "集中展示销售、采购、应收、应付与发票之间的勾稽关系；本页只读，不生成税控或凭证。", rows)


def render_output_tax_report():
    rows = _finance_workflow_rows(
        ("销项", "销售发票登记列表", "/finance/sales-invoices", "按客户、项目号、柜号和税率追踪销项税", "已接入"),
        ("销项", "销售收款核对", "/finance/reports/sales-collection-reconciliation", "核对订单、开票、应收和收款差异", "已接入"),
    )
    return _render_finance_workflow_page("销项发票明细", "销售发票和销项税内部登记明细入口；不包含税控开票、申报和抵扣操作。", rows)


def render_input_tax_report():
    rows = _finance_workflow_rows(
        ("进项", "采购发票登记列表", "/finance/purchase-invoices", "按供应商、采购订单、项目号和税率追踪进项税", "已接入"),
        ("进项", "采购付款核对", "/finance/reports/purchase-payment-reconciliation", "核对采购、入库、发票、应付和付款差异", "已接入"),
    )
    return _render_finance_workflow_page("进项发票明细", "采购发票和进项税内部登记明细入口；不包含认证抵扣、税控或申报操作。", rows)


def render_tax_summary_report():
    rows = _finance_workflow_rows(
        ("销项税", "销项发票明细", "/finance/reports/output-tax", "销售发票登记口径", "只读汇总"),
        ("进项税", "进项发票明细", "/finance/reports/input-tax", "采购发票登记口径", "只读汇总"),
        ("税额差异", "发票勾稽", "/finance/invoice-matching", "核对发票与应收应付是否脱节", "只读检查"),
    )
    return _render_finance_workflow_page("税额汇总表", "按内部发票登记口径汇总销项、进项与差异检查入口；不替代法定纳税申报。", rows)


def render_bank_reconciliation_report(query_rows):
    account_rows = query_rows(
        """
        SELECT a.id, a.account_code, a.account_name, a.account_type, a.currency,
               a.opening_balance, a.current_balance, a.status,
               COALESCE(SUM(CASE WHEN j.direction='in' THEN j.amount ELSE 0 END),0) AS income_amount,
               COALESCE(SUM(CASE WHEN j.direction='out' THEN j.amount ELSE 0 END),0) AS expense_amount,
               COUNT(j.id) AS journal_count,
               MAX(j.entry_date) AS last_entry_date
        FROM cash_bank_accounts a
        LEFT JOIN cash_bank_journal_entries j ON j.account_id=a.id
        WHERE a.account_type='bank'
        GROUP BY a.id
        ORDER BY a.account_code, a.id
        LIMIT 200
        """
    )
    for row in account_rows:
        row["account_type_label"] = cash_bank_account_type_label(row.get("account_type"))
        row["status_label"] = cash_bank_status_label(row.get("status"))
        row["calculated_balance"] = as_decimal(row.get("opening_balance")) + as_decimal(row.get("income_amount")) - as_decimal(row.get("expense_amount"))
        row["balance_diff"] = as_decimal(row.get("current_balance")) - as_decimal(row.get("calculated_balance"))
        row["reconcile_status"] = "balance mismatch" if abs(row["balance_diff"]) > Decimal("0.005") else "balanced"
        row["next_step"] = "verify bank statement and account master balance" if row["reconcile_status"] == "balance mismatch" else "archive reconciliation evidence"

    exception_rows = query_rows(
        """
        SELECT *
        FROM (
            SELECT j.entry_date, j.entry_no, j.source_type, j.source_no, j.direction, j.amount,
                   a.account_code, a.account_name, a.status AS account_status,
                   j.partner_name, j.project_code, j.cabinet_no, j.summary,
                   CASE
                       WHEN j.account_id IS NULL THEN 'missing account'
                       WHEN a.id IS NULL THEN 'account master missing'
                       WHEN COALESCE(a.status,'') <> 'active' THEN 'inactive account'
                       WHEN j.source_type IN ('customer_receipt','customer_advance_receipt','customer_receipt_refund','customer_advance_refund','customer_other_income','customer_other_income_refund') AND cr.id IS NULL THEN 'receipt source missing'
                       WHEN j.source_type IN ('supplier_payment','supplier_advance_payment','supplier_payment_refund','supplier_advance_refund','supplier_other_expense','supplier_other_expense_refund') AND sp.id IS NULL THEN 'payment source missing'
                       ELSE 'linked'
                   END AS reconcile_status,
                   CASE
                       WHEN j.account_id IS NULL OR a.id IS NULL THEN 'maintain cash/bank account master data'
                       WHEN COALESCE(a.status,'') <> 'active' THEN 'enable or replace bank account before reconciliation'
                       WHEN j.source_type LIKE 'customer%%' AND cr.id IS NULL THEN 'check receipt document traceability'
                       WHEN j.source_type LIKE 'supplier%%' AND sp.id IS NULL THEN 'check payment document traceability'
                       ELSE 'no exception'
                   END AS next_step
            FROM cash_bank_journal_entries j
            LEFT JOIN cash_bank_accounts a ON a.id=j.account_id
            LEFT JOIN customer_receipts cr
                ON j.source_type IN ('customer_receipt','customer_advance_receipt','customer_receipt_refund','customer_advance_refund','customer_other_income','customer_other_income_refund')
               AND cr.receipt_no=j.source_no
            LEFT JOIN supplier_payments sp
                ON j.source_type IN ('supplier_payment','supplier_advance_payment','supplier_payment_refund','supplier_advance_refund','supplier_other_expense','supplier_other_expense_refund')
               AND sp.payment_no=j.source_no
            WHERE COALESCE(a.account_type,'bank')='bank'
        ) q
        WHERE reconcile_status <> 'linked'
        ORDER BY entry_date DESC NULLS LAST, entry_no DESC
        LIMIT 200
        """
    )
    for row in exception_rows:
        row["direction_label"] = cash_bank_direction_label(row.get("direction"))
        row["source_label"] = cash_bank_source_label(row.get("source_type"))

    recent_rows = query_rows(
        """
        SELECT j.entry_date, j.entry_no, j.source_type, j.source_no, j.direction, j.amount,
               a.account_code, a.account_name, j.partner_name, j.project_code, j.cabinet_no,
               j.summary, j.status
        FROM cash_bank_journal_entries j
        JOIN cash_bank_accounts a ON a.id=j.account_id
        WHERE a.account_type='bank'
        ORDER BY j.entry_date DESC NULLS LAST, j.id DESC
        LIMIT 80
        """
    )
    for row in recent_rows:
        row["direction_label"] = cash_bank_direction_label(row.get("direction"))
        row["source_label"] = cash_bank_source_label(row.get("source_type"))

    balance_diff_total = sum(abs(as_decimal(row.get("balance_diff"))) for row in account_rows)
    journal_count = sum(int(row.get("journal_count") or 0) for row in account_rows)
    actions = [
        {"label": "bank journal", "href": "/finance/bank-journal"},
        {"label": "cash bank journal", "href": "/finance/cash-bank/journal?account_type=bank"},
        {"label": "account balance", "href": "/finance/reports/account-balance"},
    ]
    return _render_finance_report(
        "Bank Reconciliation",
        "Read-only bank reconciliation: account balance, cash-bank source trace, exceptions, no import, no auto-match, no balance adjustment.",
        [
            {"label": "Bank Accounts", "value": len(account_rows), "hint": "active and historical bank accounts"},
            {"label": "Bank Entries", "value": journal_count, "hint": "cash-bank journal entries"},
            {"label": "Exceptions", "value": len(exception_rows), "hint": "source/account exceptions"},
            {"label": "Balance Diff", "value": money_metric(balance_diff_total), "hint": "absolute account balance difference"},
        ],
        [
            {"title": "Bank Account Balance Check", "rows": account_rows, "columns": _columns(("account_code", "Account Code"), ("account_name", "Account Name"), ("currency", "Currency"), ("opening_balance", "Opening Balance"), ("income_amount", "Income Amount"), ("expense_amount", "Expense Amount"), ("current_balance", "System Balance"), ("calculated_balance", "Calculated Balance"), ("balance_diff", "Difference"), ("journal_count", "Entry Count"), ("last_entry_date", "Last Entry Date"), ("status_label", "Account Status"), ("reconcile_status", "Reconcile Status"), ("next_step", "Next Step"))},
            {"title": "Bank Journal Exceptions", "rows": exception_rows, "columns": _columns(("entry_date", "Date"), ("entry_no", "Entry No"), ("source_label", "Source Type"), ("source_no", "Source No"), ("account_name", "Bank Account"), ("direction_label", "Direction"), ("amount", "Amount"), ("partner_name", "Partner"), ("project_code", "Project Code"), ("cabinet_no", "Serial No"), ("reconcile_status", "Exception"), ("next_step", "Next Step"))},
            {"title": "Recent Bank Journal", "rows": recent_rows, "columns": _columns(("entry_date", "Date"), ("entry_no", "Entry No"), ("source_label", "Source Type"), ("source_no", "Source No"), ("account_name", "Bank Account"), ("direction_label", "Direction"), ("amount", "Amount"), ("partner_name", "Partner"), ("project_code", "Project Code"), ("cabinet_no", "Serial No"), ("status", "Status"), ("summary", "Summary"))},
        ],
        actions=actions,
    )

def render_fund_daily_report():
    rows = _finance_workflow_rows(
        ("资金日报", "银行账户余额", "/finance/reports/account-balance", "按账户查看余额", "已接入"),
        ("资金日报", "今日/本期资金流水", "/finance/reports/cash-bank-transactions", "按收入、支出、净流入查看", "已接入"),
        ("资金日报", "项目资金占用", "/finance/reports/project-capital-occupation", "结合库存占用、应收未收、应付未付", "已接入"),
    )
    return _render_finance_workflow_page("资金日报", "按出纳日常习惯汇总银行余额、现金余额、收支流水和项目资金占用。", rows)


def render_closing_checks_report():
    rows = _finance_workflow_rows(
        ("期末", "月末结账", "/finance/period-close", "结账前检查未审核、未核销、未生成凭证和成本异常", "已接入"),
        ("期末", "期末调汇", "/finance/exchange-adjustment", "外币调汇必须走调汇单", "已接入"),
        ("期末", "调汇单查询", "/finance/exchange-adjustments", "保留调汇过程和审计痕迹", "已接入"),
        ("期末", "损益结转", "/finance/period-close", "仅通过期末处理触发，不在普通菜单暴露直接过账", "受控"),
    )
    return _render_finance_workflow_page("结账检查", "月末结账前的业务财务一致性检查清单，避免未审核、未核销、未结转数据进入已结账期间。", rows)


def render_voucher_generation_preview(query_rows):
    rows = query_rows(
        """
        SELECT *
        FROM (
            SELECT 'sales_invoice' AS source_type,
                   si.id AS source_id,
                   si.invoice_no AS source_no,
                   si.invoice_date AS doc_date,
                   COALESCE(si.amount_with_tax, si.amount, 0) AS amount,
                   si.project_code,
                   si.cabinet_no,
                   COALESCE(si.status,'') AS source_status,
                   'debit AR, credit revenue/tax' AS voucher_rule,
                   'sales invoice voucher preview' AS preview_basis,
                   v.voucher_no,
                   v.status AS voucher_status,
                   v.total_debit,
                   v.total_credit
            FROM sales_invoices si
            LEFT JOIN vouchers v
              ON v.source_type='sales_invoice'
             AND v.source_id=si.id
             AND COALESCE(v.auto_generated,FALSE)=TRUE
            WHERE COALESCE(si.status,'') NOT IN ('void','voided','cancelled')
            UNION ALL
            SELECT 'purchase_invoice' AS source_type,
                   pi.id AS source_id,
                   pi.invoice_no AS source_no,
                   pi.invoice_date AS doc_date,
                   COALESCE(pi.amount_with_tax, pi.amount, 0) AS amount,
                   pi.project_code,
                   pi.cabinet_no,
                   COALESCE(pi.status,'') AS source_status,
                   'debit inventory/expense/tax, credit AP' AS voucher_rule,
                   'purchase invoice voucher preview' AS preview_basis,
                   v.voucher_no,
                   v.status AS voucher_status,
                   v.total_debit,
                   v.total_credit
            FROM purchase_invoices pi
            LEFT JOIN vouchers v
              ON v.source_type='purchase_invoice'
             AND v.source_id=pi.id
             AND COALESCE(v.auto_generated,FALSE)=TRUE
            WHERE COALESCE(pi.status,'') NOT IN ('void','voided','cancelled')
            UNION ALL
            SELECT COALESCE(cr.receipt_kind,'customer_receipt') AS source_type,
                   cr.id AS source_id,
                   cr.receipt_no AS source_no,
                   cr.receipt_date AS doc_date,
                   COALESCE(cr.amount,0) AS amount,
                   cr.project_code,
                   cr.cabinet_no,
                   COALESCE(cr.status,'') AS source_status,
                   'debit bank, credit AR/advance receipt' AS voucher_rule,
                   'customer receipt voucher preview' AS preview_basis,
                   v.voucher_no,
                   v.status AS voucher_status,
                   v.total_debit,
                   v.total_credit
            FROM customer_receipts cr
            LEFT JOIN vouchers v
              ON v.source_type=COALESCE(cr.receipt_kind,'customer_receipt')
             AND v.source_id=cr.id
             AND COALESCE(v.auto_generated,FALSE)=TRUE
            WHERE COALESCE(cr.status,'') NOT IN ('void','voided','cancelled')
            UNION ALL
            SELECT COALESCE(sp.payment_kind,'supplier_payment') AS source_type,
                   sp.id AS source_id,
                   sp.payment_no AS source_no,
                   sp.payment_date AS doc_date,
                   COALESCE(sp.amount,0) AS amount,
                   sp.project_code,
                   sp.cabinet_no,
                   COALESCE(sp.status,'') AS source_status,
                   'debit AP/prepayment, credit bank' AS voucher_rule,
                   'supplier payment voucher preview' AS preview_basis,
                   v.voucher_no,
                   v.status AS voucher_status,
                   v.total_debit,
                   v.total_credit
            FROM supplier_payments sp
            LEFT JOIN vouchers v
              ON v.source_type=COALESCE(sp.payment_kind,'supplier_payment')
             AND v.source_id=sp.id
             AND COALESCE(v.auto_generated,FALSE)=TRUE
            WHERE COALESCE(sp.status,'') NOT IN ('void','voided','cancelled')
        ) q
        ORDER BY doc_date DESC NULLS LAST, source_no DESC
        LIMIT 300
        """
    )
    for row in rows:
        row["source_label"] = cash_bank_source_label(row.get("source_type"))
        row["voucher_state"] = "generated" if row.get("voucher_no") else "pending"
        row["balance_state"] = "balanced" if row.get("voucher_no") and abs(as_decimal(row.get("total_debit")) - as_decimal(row.get("total_credit"))) <= Decimal("0.005") else ("not generated" if not row.get("voucher_no") else "unbalanced")
        row["next_step"] = "review source and generate voucher through controlled posting flow" if not row.get("voucher_no") else "review voucher list and posting status"

    pending_rows = [row for row in rows if row.get("voucher_state") == "pending"]
    generated_rows = [row for row in rows if row.get("voucher_state") == "generated"]
    unbalanced_rows = [row for row in generated_rows if row.get("balance_state") == "unbalanced"]
    total_pending_amount = sum(as_decimal(row.get("amount")) for row in pending_rows)
    actions = [
        {"label": "Voucher List", "href": "/finance/vouchers"},
        {"label": "Sales Invoices", "href": "/finance/sales-invoices"},
        {"label": "Purchase Invoices", "href": "/finance/purchase-invoices"},
        {"label": "Receipts", "href": "/finance/receipts"},
        {"label": "Payments", "href": "/finance/payments"},
    ]
    return _render_finance_report(
        "Voucher Generation Preview",
        "Read-only voucher source preview. This page does not create vouchers, does not review, and does not post to the general ledger.",
        [
            {"label": "Source Docs", "value": len(rows), "hint": "invoice receipt payment sources"},
            {"label": "Pending", "value": len(pending_rows), "hint": "without generated voucher"},
            {"label": "Generated", "value": len(generated_rows), "hint": "linked auto vouchers"},
            {"label": "Pending Amount", "value": money_metric(total_pending_amount), "hint": "source amount preview"},
        ],
        [
            {"title": "Pending Voucher Sources", "rows": pending_rows, "columns": _columns(("source_label", "Source Type"), ("source_no", "Source No"), ("doc_date", "Date"), ("amount", "Amount"), ("project_code", "Project Code"), ("cabinet_no", "Serial No"), ("source_status", "Source Status"), ("voucher_rule", "Voucher Rule"), ("voucher_state", "Voucher State"), ("next_step", "Next Step"))},
            {"title": "Generated Voucher Sources", "rows": generated_rows, "columns": _columns(("source_label", "Source Type"), ("source_no", "Source No"), ("doc_date", "Date"), ("amount", "Amount"), ("voucher_no", "Voucher No"), ("voucher_status", "Voucher Status"), ("total_debit", "Debit"), ("total_credit", "Credit"), ("balance_state", "Balance State"), ("project_code", "Project Code"), ("cabinet_no", "Serial No"))},
            {"title": "Unbalanced Generated Vouchers", "rows": unbalanced_rows, "columns": _columns(("source_label", "Source Type"), ("source_no", "Source No"), ("voucher_no", "Voucher No"), ("total_debit", "Debit"), ("total_credit", "Credit"), ("balance_state", "Balance State"), ("next_step", "Next Step"))},
        ],
        actions=actions,
    )

def render_finance_settings_overview():
    rows = _finance_workflow_rows(
        ("基础资料", "会计科目", "/master/chart-of-accounts", "财务科目编码和余额方向", "已接入"),
        ("基础资料", "科目映射", "/finance/account-mappings", "业务单据到会计科目的默认映射", "已接入"),
        ("基础资料", "结算方式", "/settlement-methods", "现金、银行转账、票据等", "已接入"),
        ("基础资料", "收付款条件", "/payment-terms", "账期、到期日和预收预付比例", "已接入"),
        ("内控", "结账和凭证控制", "/finance/closing-checks", "已结账期间不可随意修改", "受控"),
    )
    return _render_finance_workflow_page("财务设置", "集中列示财务模块上线所需基础资料、科目映射和内控入口。", rows)


def render_inventory_accounting_home():
    rows = _finance_workflow_rows(
        ("存货核算", "存货核算首页", "/finance/inventory-accounting", "库存数量、成本和金额核对入口", "只读导航"),
        ("存货核算", "库存成本总账", "/finance/inventory-cost/summary", "按物料/仓库/项目/柜号汇总库存成本", "已接入"),
        ("存货核算", "库存成本明细账", "/finance/inventory-cost/detail", "按库存流水追踪入库和出库成本", "已接入"),
        ("存货核算", "存货与总账对账", "/finance/inventory-reconciliation", "对比库存成本和财务科目余额", "只读检查"),
    )
    return _render_finance_workflow_page("存货核算首页", "按存货会计习惯组织入库成本、出库成本、暂估和存货对账入口。", rows)


def render_inventory_reconciliation_report():
    rows = _finance_workflow_rows(
        ("库存", "库存成本总账", "/finance/inventory-cost/summary", "库存侧金额", "已接入"),
        ("明细", "库存成本明细账", "/finance/inventory-cost/detail", "库存流水侧金额", "已接入"),
        ("总账", "科目余额表", "/finance/account-balance", "存货科目余额", "已接入"),
        ("差异", "存货与总账对账", "/finance/inventory-reconciliation", "当前只读提示差异来源，不自动调账", "只读检查"),
    )
    return _render_finance_workflow_page("存货与总账对账", "提供库存成本与财务科目余额的核对入口，避免库存金额和总账脱节。", rows)


def render_cost_management_home():
    rows = _finance_workflow_rows(
        ("项目成本", "项目成本台账", "/finance/project-costs", "按项目号汇总材料、委外、售后和收入", "已接入"),
        ("柜号成本", "柜号成本台账", "/finance/cabinet-costs", "按柜号汇总单台设备实际成本", "已接入"),
        ("生产成本", "生产工单成本", "/finance/work-order-costs", "衔接生产领料、报工、完工入库", "只读导航"),
        ("毛利分析", "项目/柜号毛利", "/finance/reports/project-profit", "收入、成本和毛利率核对", "只读导航"),
    )
    return _render_finance_workflow_page("成本管理首页", "围绕项目号、柜号、生产工单和委外加工组织成本核算入口。", rows)


def _fund_analysis_filters(default_date_field="date"):
    filters = _finance_report_filters(default_date_field)
    filters.update(
        {
            "direction": (request.args.get("direction") or "").strip(),
            "account": (request.args.get("account") or "").strip(),
            "partner_type": (request.args.get("partner_type") or "").strip(),
        }
    )
    return filters


def _fund_flow_rows(query_rows, source_types=None, limit=500):
    filters = _fund_analysis_filters()
    params = []
    where = _finance_report_date_where("j.entry_date", filters, params)
    if filters["direction"] in {"in", "out"}:
        where.append("j.direction=%s")
        params.append(filters["direction"])
    if filters["account"]:
        pattern = f"%{filters['account']}%"
        where.append("(a.account_name ILIKE %s OR a.account_code ILIKE %s OR a.bank_account_no ILIKE %s)")
        params.extend([pattern, pattern, pattern])
    if filters["partner_type"]:
        where.append("COALESCE(j.partner_type,'')=%s")
        params.append(filters["partner_type"])
    if filters["keyword"]:
        pattern = f"%{filters['keyword']}%"
        where.append("(j.entry_no ILIKE %s OR j.source_no ILIKE %s OR j.partner_name ILIKE %s OR j.project_code ILIKE %s OR j.cabinet_no ILIKE %s OR j.summary ILIKE %s OR a.account_name ILIKE %s)")
        params.extend([pattern] * 7)
    if source_types:
        placeholders = ",".join(["%s"] * len(source_types))
        where.append(f"j.source_type IN ({placeholders})")
        params.extend(source_types)
    where_sql = " AND ".join(where) if where else "1=1"
    rows = query_rows(
        f"""
        SELECT j.entry_date AS doc_date, j.entry_no AS doc_no, j.source_type, j.source_no,
               j.direction, j.amount,
               CASE WHEN j.direction='in' THEN j.amount ELSE 0 END AS income_amount,
               CASE WHEN j.direction='out' THEN j.amount ELSE 0 END AS expense_amount,
               j.balance_after, j.partner_type, j.partner_name, j.project_code, j.cabinet_no,
               j.summary, j.status, a.account_code, a.account_name, a.currency
        FROM cash_bank_journal_entries j
        LEFT JOIN cash_bank_accounts a ON a.id=j.account_id
        WHERE {where_sql}
        ORDER BY j.entry_date DESC NULLS LAST, j.id DESC
        LIMIT {int(limit)}
        """,
        tuple(params),
    )
    if not rows:
        legacy_params = []
        legacy_where = []
        if filters["date_from"]:
            legacy_where.append("doc_date >= %s")
            legacy_params.append(filters["date_from"])
        if filters["date_to"]:
            legacy_where.append("doc_date <= %s")
            legacy_params.append(filters["date_to"])
        if filters["direction"] in {"in", "out"}:
            legacy_where.append("direction=%s")
            legacy_params.append(filters["direction"])
        if filters["account"]:
            pattern = f"%{filters['account']}%"
            legacy_where.append("account_name ILIKE %s")
            legacy_params.append(pattern)
        if filters["partner_type"]:
            legacy_where.append("partner_type=%s")
            legacy_params.append(filters["partner_type"])
        if filters["keyword"]:
            pattern = f"%{filters['keyword']}%"
            legacy_where.append("(doc_no ILIKE %s OR source_no ILIKE %s OR partner_name ILIKE %s OR project_code ILIKE %s OR cabinet_no ILIKE %s OR summary ILIKE %s OR account_name ILIKE %s)")
            legacy_params.extend([pattern] * 7)
        if source_types:
            placeholders = ",".join(["%s"] * len(source_types))
            legacy_where.append(f"source_type IN ({placeholders})")
            legacy_params.extend(source_types)
        legacy_sql = " AND ".join(legacy_where) if legacy_where else "1=1"
        rows = query_rows(
            f"""
            SELECT *
            FROM (
                SELECT r.receipt_date AS doc_date, r.receipt_no AS doc_no, COALESCE(r.receipt_kind,'customer_receipt') AS source_type,
                       r.source_no, COALESCE(r.fund_direction,'in') AS direction, r.amount,
                       CASE WHEN COALESCE(r.fund_direction,'in')='in' THEN r.amount ELSE 0 END AS income_amount,
                       CASE WHEN COALESCE(r.fund_direction,'in')='out' THEN r.amount ELSE 0 END AS expense_amount,
                       NULL::NUMERIC AS balance_after, 'customer' AS partner_type, c.name AS partner_name,
                       r.project_code, r.cabinet_no, r.remark AS summary, r.status,
                       NULL::VARCHAR AS account_code, COALESCE(r.bank_account, r.payment_method, '-') AS account_name, 'CNY' AS currency
                FROM customer_receipts r
                LEFT JOIN customers c ON c.id=r.customer_id
                UNION ALL
                SELECT p.payment_date AS doc_date, p.payment_no AS doc_no, COALESCE(p.payment_kind,'supplier_payment') AS source_type,
                       p.source_no, COALESCE(p.fund_direction,'out') AS direction, p.amount,
                       CASE WHEN COALESCE(p.fund_direction,'out')='in' THEN p.amount ELSE 0 END AS income_amount,
                       CASE WHEN COALESCE(p.fund_direction,'out')='out' THEN p.amount ELSE 0 END AS expense_amount,
                       NULL::NUMERIC AS balance_after, 'supplier' AS partner_type, s.name AS partner_name,
                       p.project_code, p.cabinet_no, p.remark AS summary, p.status,
                       NULL::VARCHAR AS account_code, COALESCE(p.bank_account, p.payment_method, '-') AS account_name, 'CNY' AS currency
                FROM supplier_payments p
                LEFT JOIN suppliers s ON s.id=p.supplier_id
            ) fund_flow
            WHERE {legacy_sql}
            ORDER BY doc_date DESC NULLS LAST, doc_no DESC
            LIMIT {int(limit)}
            """,
            tuple(legacy_params),
        )
    for row in rows:
        row["source_label"] = cash_bank_source_label(row.get("source_type"))
        row["direction_label"] = cash_bank_direction_label(row.get("direction"))
        row["partner_type_label"] = {"customer": "客户", "supplier": "供应商"}.get(row.get("partner_type"), row.get("partner_type") or "-")
        row["net_amount"] = as_decimal(row.get("income_amount")) - as_decimal(row.get("expense_amount"))
    return rows


def render_enterprise_income_expense_detail_report(query_rows):
    rows = _fund_flow_rows(query_rows)
    total_income = sum(as_decimal(row.get("income_amount")) for row in rows)
    total_expense = sum(as_decimal(row.get("expense_amount")) for row in rows)
    summary = {}
    for row in rows:
        key = row.get("source_label") or "-"
        item = summary.setdefault(key, {"source_label": key, "doc_count": 0, "income_amount": Decimal("0"), "expense_amount": Decimal("0"), "net_amount": Decimal("0")})
        item["doc_count"] += 1
        item["income_amount"] += as_decimal(row.get("income_amount"))
        item["expense_amount"] += as_decimal(row.get("expense_amount"))
        item["net_amount"] += as_decimal(row.get("net_amount"))
    return _render_finance_report(
        "企业收支明细表",
        "按资金账户、来源单据、往来单位、项目号和柜号列示企业资金流入流出；本页只查询和导出，不登记收付款。",
        [
            {"label": "收入合计", "value": money_metric(total_income), "hint": "当前筛选"},
            {"label": "支出合计", "value": money_metric(total_expense), "hint": "当前筛选"},
            {"label": "净流入", "value": money_metric(total_income - total_expense), "hint": "收入-支出"},
        ],
        [
            {"title": "收支类别汇总", "rows": list(summary.values()), "columns": _columns(("source_label", "来源类别"), ("doc_count", "单据数"), ("income_amount", "收入金额"), ("expense_amount", "支出金额"), ("net_amount", "净流入"))},
            {"title": "企业收支明细", "rows": rows, "columns": _columns(("doc_date", "日期"), ("doc_no", "流水号"), ("source_label", "来源类别"), ("source_no", "来源单据"), ("account_name", "资金账户"), ("partner_type_label", "往来类型"), ("partner_name", "往来单位"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("income_amount", "收入金额"), ("expense_amount", "支出金额"), ("balance_after", "账户余额"), ("summary", "摘要"))},
        ],
    )


def render_account_income_expense_detail_report(query_rows):
    rows = _fund_flow_rows(query_rows)
    accounts = {}
    for row in rows:
        key = row.get("account_name") or "未指定资金账户"
        item = accounts.setdefault(key, {"account_name": key, "currency": row.get("currency") or "CNY", "doc_count": 0, "income_amount": Decimal("0"), "expense_amount": Decimal("0"), "net_amount": Decimal("0")})
        item["doc_count"] += 1
        item["income_amount"] += as_decimal(row.get("income_amount"))
        item["expense_amount"] += as_decimal(row.get("expense_amount"))
        item["net_amount"] += as_decimal(row.get("net_amount"))
    return _render_finance_report(
        "账户收支明细表",
        "按现金/银行账户列示资金收入、支出、余额和来源单据，用于账户流水核对；不在本页调整账户余额。",
        [
            {"label": "账户数", "value": len(accounts), "hint": "当前筛选"},
            {"label": "收入合计", "value": money_metric(sum(as_decimal(r.get("income_amount")) for r in rows)), "hint": "当前筛选"},
            {"label": "支出合计", "value": money_metric(sum(as_decimal(r.get("expense_amount")) for r in rows)), "hint": "当前筛选"},
        ],
        [
            {"title": "账户汇总", "rows": list(accounts.values()), "columns": _columns(("account_name", "资金账户"), ("currency", "币别"), ("doc_count", "流水数"), ("income_amount", "收入金额"), ("expense_amount", "支出金额"), ("net_amount", "净流入"))},
            {"title": "账户收支明细", "rows": rows, "columns": _columns(("doc_date", "日期"), ("account_name", "资金账户"), ("doc_no", "流水号"), ("source_label", "来源类别"), ("source_no", "来源单据"), ("direction_label", "方向"), ("income_amount", "收入金额"), ("expense_amount", "支出金额"), ("balance_after", "账户余额"), ("partner_name", "往来单位"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("summary", "摘要"))},
        ],
    )


def render_other_income_expense_detail_report(query_rows):
    source_types = [
        "customer_other_income",
        "customer_other_income_refund",
        "supplier_other_expense",
        "supplier_other_expense_refund",
    ]
    rows = _fund_flow_rows(query_rows, source_types=source_types)
    return _render_finance_report(
        "其他收支明细表",
        "列示其他收入、其他支出及其退款形成的资金流水；只用于费用/收入口径核对，不生成凭证或收付款单。",
        [
            {"label": "明细行数", "value": len(rows), "hint": "当前筛选"},
            {"label": "其他收入", "value": money_metric(sum(as_decimal(r.get("income_amount")) for r in rows)), "hint": "含退款流入"},
            {"label": "其他支出", "value": money_metric(sum(as_decimal(r.get("expense_amount")) for r in rows)), "hint": "含退款流出"},
        ],
        [{"title": "其他收支明细", "rows": rows, "columns": _columns(("doc_date", "日期"), ("doc_no", "单据号"), ("source_label", "单据类型"), ("account_name", "资金账户"), ("partner_name", "往来单位"), ("direction_label", "方向"), ("income_amount", "收入金额"), ("expense_amount", "支出金额"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("summary", "摘要"), ("status", "状态"))}],
    )


def render_fund_account_balance_report(query_rows):
    rows = query_rows(
        """
        SELECT a.id, a.account_code, a.account_name, a.account_type, a.currency,
               a.opening_balance, a.current_balance, a.status,
               COALESCE(SUM(CASE WHEN j.direction='in' THEN j.amount ELSE 0 END),0) AS income_amount,
               COALESCE(SUM(CASE WHEN j.direction='out' THEN j.amount ELSE 0 END),0) AS expense_amount,
               COALESCE(COUNT(j.id),0) AS entry_count
        FROM cash_bank_accounts a
        LEFT JOIN cash_bank_journal_entries j ON j.account_id=a.id
        GROUP BY a.id
        ORDER BY a.account_type, a.account_code, a.id
        LIMIT 300
        """
    )
    for row in rows:
        row["account_type_label"] = cash_bank_account_type_label(row.get("account_type"))
        row["status_label"] = cash_bank_status_label(row.get("status"))
        row["calculated_balance"] = as_decimal(row.get("opening_balance")) + as_decimal(row.get("income_amount")) - as_decimal(row.get("expense_amount"))
        row["balance_diff"] = as_decimal(row.get("current_balance")) - as_decimal(row.get("calculated_balance"))
        row["next_step"] = "核对账户余额差异" if abs(row["balance_diff"]) > Decimal("0.005") else "余额一致"
    return _render_finance_report(
        "账户余额表",
        "按现金/银行账户汇总期初、收入、支出、系统余额和计算余额；用于核对资金账户，不在本页余额重算。",
        [
            {"label": "账户数", "value": len(rows), "hint": "现金/银行"},
            {"label": "系统余额", "value": money_metric(sum(as_decimal(r.get("current_balance")) for r in rows)), "hint": "账户主数据"},
            {"label": "计算余额", "value": money_metric(sum(as_decimal(r.get("calculated_balance")) for r in rows)), "hint": "期初+收入-支出"},
        ],
        [{"title": "账户余额", "rows": rows, "columns": _columns(("account_code", "账户编码"), ("account_name", "账户名称"), ("account_type_label", "账户类型"), ("currency", "币别"), ("opening_balance", "期初余额"), ("income_amount", "收入金额"), ("expense_amount", "支出金额"), ("current_balance", "系统余额"), ("calculated_balance", "计算余额"), ("balance_diff", "差异"), ("entry_count", "流水数"), ("status_label", "状态"), ("next_step", "下一步"))}],
    )


def render_credit_management_report(query_rows):
    rows = query_rows(
        """
        SELECT c.id, c.name AS customer_name, COALESCE(c.credit_limit,0) AS credit_limit,
               COALESCE(c.credit_used,0) AS credit_used,
               COALESCE(SUM(cr.balance),0) AS receivable_balance,
               COALESCE(SUM(CASE WHEN cr.due_date < CURRENT_DATE THEN cr.balance ELSE 0 END),0) AS overdue_balance,
               COUNT(cr.id) FILTER (WHERE COALESCE(cr.balance,0)>0) AS open_doc_count,
               MAX(CASE WHEN cr.due_date < CURRENT_DATE THEN CURRENT_DATE - cr.due_date ELSE 0 END) AS max_overdue_days
        FROM customers c
        LEFT JOIN customer_receivables cr ON cr.customer_id=c.id AND COALESCE(cr.balance,0)>0
        GROUP BY c.id
        ORDER BY (COALESCE(c.credit_used,0)+COALESCE(SUM(cr.balance),0)-COALESCE(c.credit_limit,0)) DESC, c.id DESC
        LIMIT 300
        """
    )
    for row in rows:
        exposure = as_decimal(row.get("credit_used")) + as_decimal(row.get("receivable_balance"))
        row["credit_exposure"] = exposure
        row["available_credit"] = as_decimal(row.get("credit_limit")) - exposure
        if as_decimal(row.get("credit_limit")) > 0 and exposure > as_decimal(row.get("credit_limit")):
            row["credit_status"] = "超信用额度"
            row["next_step"] = "销售主管和财务确认放行或催收"
        elif as_decimal(row.get("overdue_balance")) > 0:
            row["credit_status"] = "存在逾期"
            row["next_step"] = "优先催收到期应收"
        elif as_decimal(row.get("credit_limit")) <= 0:
            row["credit_status"] = "未设额度"
            row["next_step"] = "到客户档案维护信用额度"
        else:
            row["credit_status"] = "正常"
            row["next_step"] = "持续跟踪"
    return _render_finance_report(
        "信用管理",
        "按客户信用额度、已用额度、未收应收和逾期余额分析信用占用；本页只预警，不维护客户信用参数。",
        [
            {"label": "信用客户", "value": sum(1 for r in rows if as_decimal(r.get("credit_limit")) > 0), "hint": "已设置额度"},
            {"label": "超额客户", "value": sum(1 for r in rows if r.get("credit_status") == "超信用额度"), "hint": "需确认放行"},
            {"label": "逾期余额", "value": money_metric(sum(as_decimal(r.get("overdue_balance")) for r in rows)), "hint": "当前客户范围"},
        ],
        [{"title": "客户信用占用", "rows": rows, "columns": _columns(("customer_name", "客户"), ("credit_limit", "信用额度"), ("credit_used", "已用额度"), ("receivable_balance", "应收余额"), ("overdue_balance", "逾期余额"), ("credit_exposure", "信用占用"), ("available_credit", "可用额度"), ("open_doc_count", "未清单据数"), ("max_overdue_days", "最长逾期天数"), ("credit_status", "信用状态"), ("next_step", "下一步"))}],
    )


def render_account_aging_analysis_report(query_rows):
    rows = query_rows(
        """
        SELECT '应收' AS account_type, cr.source_no AS doc_no, cr.receivable_date AS doc_date,
               COALESCE(cr.due_date, cr.receivable_date) AS due_date, c.name AS partner_name,
               cr.project_code, cr.cabinet_no, cr.balance,
               CURRENT_DATE - COALESCE(cr.due_date, cr.receivable_date, CURRENT_DATE) AS age_days,
               cr.status
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE COALESCE(cr.balance,0)>0
        UNION ALL
        SELECT '应付' AS account_type, sp.doc_no, sp.doc_date,
               COALESCE(sp.next_follow_up_date, sp.doc_date) AS due_date, s.name AS partner_name,
               sp.project_code, sp.cabinet_no, sp.balance,
               CURRENT_DATE - COALESCE(sp.next_follow_up_date, sp.doc_date, CURRENT_DATE) AS age_days,
               sp.status
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE COALESCE(sp.balance,0)>0
        ORDER BY age_days DESC NULLS LAST, balance DESC
        LIMIT 500
        """
    )
    bucket_rows = {}
    for row in rows:
        row["aging_bucket"] = _aging_bucket(row.get("age_days"))
        key = (row.get("account_type"), row.get("aging_bucket"))
        item = bucket_rows.setdefault(key, {"account_type": row.get("account_type"), "aging_bucket": row.get("aging_bucket"), "doc_count": 0, "balance": Decimal("0")})
        item["doc_count"] += 1
        item["balance"] += as_decimal(row.get("balance"))
    return _render_finance_report(
        "账龄分析表",
        "汇总应收和应付未清余额的账龄区间，用于资金回笼、付款计划和信用风险跟踪；不在本页核销。",
        [
            {"label": "应收余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows if r.get("account_type") == "应收")), "hint": "未清应收"},
            {"label": "应付余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows if r.get("account_type") == "应付")), "hint": "未清应付"},
            {"label": "明细行数", "value": len(rows), "hint": "当前范围"},
        ],
        [
            {"title": "账龄区间汇总", "rows": list(bucket_rows.values()), "columns": _columns(("account_type", "往来类型"), ("aging_bucket", "账龄区间"), ("doc_count", "单据数"), ("balance", "余额"))},
            {"title": "账龄明细", "rows": rows, "columns": _columns(("account_type", "往来类型"), ("doc_no", "来源单据"), ("doc_date", "单据日期"), ("due_date", "到期/跟进日"), ("partner_name", "往来单位"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("balance", "余额"), ("age_days", "逾期天数"), ("aging_bucket", "账龄区间"), ("status", "状态"))},
        ],
    )


def render_project_capital_occupation_report(query_rows):
    rows = query_rows(
        """
        SELECT COALESCE(project_code,'') AS project_code, COALESCE(cabinet_no,'') AS cabinet_no,
               SUM(receivable_balance) AS receivable_balance,
               SUM(payable_balance) AS payable_balance,
               SUM(receivable_balance) - SUM(payable_balance) AS net_occupation,
               COUNT(*) AS source_count
        FROM (
            SELECT cr.project_code, cr.cabinet_no, COALESCE(cr.balance,0) AS receivable_balance, 0::NUMERIC AS payable_balance
            FROM customer_receivables cr
            WHERE COALESCE(cr.balance,0)>0
            UNION ALL
            SELECT sp.project_code, sp.cabinet_no, 0::NUMERIC AS receivable_balance, COALESCE(sp.balance,0) AS payable_balance
            FROM supplier_payables sp
            WHERE COALESCE(sp.balance,0)>0
        ) t
        WHERE COALESCE(project_code,'')<>'' OR COALESCE(cabinet_no,'')<>''
        GROUP BY COALESCE(project_code,''), COALESCE(cabinet_no,'')
        ORDER BY ABS(SUM(receivable_balance) - SUM(payable_balance)) DESC, project_code, cabinet_no
        LIMIT 300
        """
    )
    for row in rows:
        row["capital_status"] = "占用资金" if as_decimal(row.get("net_occupation")) > 0 else "应付释放"
        row["next_step"] = "跟进回款和项目结算" if as_decimal(row.get("net_occupation")) > 0 else "结合付款计划安排"
    return _render_finance_report(
        "项目资金占用表",
        "按项目号和柜号汇总未收应收、未付应付和净资金占用，用于项目现金流复核；不在本页收款或付款。",
        [
            {"label": "项目/柜号数", "value": len(rows), "hint": "当前范围"},
            {"label": "应收未收", "value": money_metric(sum(as_decimal(r.get("receivable_balance")) for r in rows)), "hint": "客户未回款"},
            {"label": "净占用", "value": money_metric(sum(as_decimal(r.get("net_occupation")) for r in rows)), "hint": "应收-应付"},
        ],
        [{"title": "项目资金占用", "rows": rows, "columns": _columns(("project_code", "项目号"), ("cabinet_no", "柜号"), ("receivable_balance", "应收未收"), ("payable_balance", "应付未付"), ("net_occupation", "净资金占用"), ("source_count", "来源单据数"), ("capital_status", "资金状态"), ("next_step", "下一步"))}],
    )


def render_receivable_detail_report(query_rows):
    filters = _finance_report_filters()
    params = []
    where = _finance_report_date_where("cr.receivable_date", filters, params)
    if filters["keyword"]:
        pattern = f"%{filters['keyword']}%"
        where.append("(cr.source_no ILIKE %s OR c.name ILIKE %s OR cr.project_code ILIKE %s OR cr.cabinet_no ILIKE %s)")
        params.extend([pattern] * 4)
    if filters["status"]:
        where.append("COALESCE(cr.status,'')=%s")
        params.append(filters["status"])
    if filters["project"]:
        pattern = f"%{filters['project']}%"
        where.append("(cr.project_code ILIKE %s OR cr.cabinet_no ILIKE %s)")
        params.extend([pattern, pattern])
    rows = query_rows(
        f"""
        SELECT cr.id, cr.source_no, cr.receivable_date, cr.due_date, c.name AS customer_name,
               cr.project_code, cr.cabinet_no, cr.total_amount, cr.received_amount,
               COALESCE(rs.settled_amount,0) AS settled_detail_amount,
               cr.balance, cr.status,
               CURRENT_DATE - COALESCE(cr.due_date, cr.receivable_date, CURRENT_DATE) AS age_days,
               CASE
                   WHEN COALESCE(cr.balance,0)=0 THEN '已结清，保留对账记录'
                   WHEN cr.due_date IS NOT NULL AND cr.due_date < CURRENT_DATE THEN '逾期未清，核对发货签收和回款计划'
                   WHEN cr.due_date IS NOT NULL THEN '按到期日跟进回款'
                   ELSE '补齐到期日和收款责任人'
               END AS next_step
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        LEFT JOIN (
            SELECT receivable_id, SUM(applied_amount) AS settled_amount
            FROM customer_receipt_settlements
            GROUP BY receivable_id
        ) rs ON rs.receivable_id=cr.id
        WHERE {' AND '.join(where) if where else '1=1'}
        ORDER BY cr.receivable_date DESC NULLS LAST, cr.id DESC
        LIMIT 500
        """,
        tuple(params),
    )
    for row in rows:
        row["aging_bucket"] = _aging_bucket(row.get("age_days"))
        row["settlement_status"] = _settlement_status(row.get("total_amount"), row.get("received_amount"), row.get("balance"))
    return _render_finance_report(
        "应收账款明细表",
        "按客户、来源单据、项目号、柜号、到期日和核销状态查询应收明细；只读报表，不登记收款或核销。",
        [
            {"label": "明细行数", "value": len(rows), "hint": "最多 500 行"},
            {"label": "应收金额", "value": money_metric(sum(as_decimal(r.get("total_amount")) for r in rows)), "hint": "当前筛选"},
            {"label": "未收余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows)), "hint": "当前筛选"},
        ],
        [{"title": "应收账款明细", "rows": rows, "columns": _columns(("source_no", "来源单据"), ("receivable_date", "应收日期"), ("due_date", "到期日"), ("customer_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("total_amount", "应收金额"), ("received_amount", "已收金额"), ("balance", "未收余额"), ("aging_bucket", "账龄区间"), ("settlement_status", "核销状态"), ("status", "业务状态"), ("next_step", "下一步"))}],
    )


def render_payable_detail_report(query_rows):
    filters = _finance_report_filters()
    params = []
    where = _finance_report_date_where("sp.doc_date", filters, params)
    if filters["keyword"]:
        pattern = f"%{filters['keyword']}%"
        where.append("(sp.doc_no ILIKE %s OR s.name ILIKE %s OR sp.project_code ILIKE %s OR sp.cabinet_no ILIKE %s)")
        params.extend([pattern] * 4)
    if filters["status"]:
        where.append("COALESCE(sp.status,'')=%s")
        params.append(filters["status"])
    if filters["project"]:
        pattern = f"%{filters['project']}%"
        where.append("(sp.project_code ILIKE %s OR sp.cabinet_no ILIKE %s)")
        params.extend([pattern, pattern])
    rows = query_rows(
        f"""
        SELECT sp.id, sp.doc_no, sp.doc_date, COALESCE(sp.next_follow_up_date, sp.doc_date) AS due_date,
               s.name AS supplier_name, sp.project_code, sp.cabinet_no, sp.amount,
               sp.paid_amount, COALESCE(ps.settled_amount,0) AS settled_detail_amount,
               sp.balance, sp.status,
               CURRENT_DATE - COALESCE(sp.next_follow_up_date, sp.doc_date, CURRENT_DATE) AS age_days,
               CASE
                   WHEN COALESCE(sp.balance,0)=0 THEN '已结清，保留对账记录'
                   WHEN sp.next_follow_up_date IS NOT NULL AND sp.next_follow_up_date < CURRENT_DATE THEN '付款跟进日已过，确认付款安排'
                   WHEN sp.next_follow_up_date IS NOT NULL THEN '按跟进日核对付款计划'
                   ELSE '补齐账期和付款责任人'
               END AS next_step
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        LEFT JOIN (
            SELECT payable_id, SUM(applied_amount) AS settled_amount
            FROM supplier_payment_settlements
            GROUP BY payable_id
        ) ps ON ps.payable_id=sp.id
        WHERE {' AND '.join(where) if where else '1=1'}
        ORDER BY sp.doc_date DESC NULLS LAST, sp.id DESC
        LIMIT 500
        """,
        tuple(params),
    )
    for row in rows:
        row["aging_bucket"] = _aging_bucket(row.get("age_days"))
        row["settlement_status"] = _settlement_status(row.get("amount"), row.get("paid_amount"), row.get("balance"))
    return _render_finance_report(
        "应付账款明细表",
        "按供应商、来源单据、项目号、柜号、跟进日和核销状态查询应付明细；只读报表，不登记付款或核销。",
        [
            {"label": "明细行数", "value": len(rows), "hint": "最多 500 行"},
            {"label": "应付金额", "value": money_metric(sum(as_decimal(r.get("amount")) for r in rows)), "hint": "当前筛选"},
            {"label": "未付余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows)), "hint": "当前筛选"},
        ],
        [{"title": "应付账款明细", "rows": rows, "columns": _columns(("doc_no", "来源单据"), ("doc_date", "应付日期"), ("due_date", "跟进日"), ("supplier_name", "供应商"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("amount", "应付金额"), ("paid_amount", "已付金额"), ("balance", "未付余额"), ("aging_bucket", "账龄区间"), ("settlement_status", "核销状态"), ("status", "业务状态"), ("next_step", "下一步"))}],
    )


def render_receivable_summary_report(query_rows):
    rows = query_rows(
        """
        SELECT c.name AS customer_name, cr.project_code, cr.cabinet_no,
               COUNT(*) AS doc_count, SUM(cr.total_amount) AS total_amount,
               SUM(cr.received_amount) AS received_amount, SUM(cr.balance) AS balance,
               MIN(cr.due_date) AS earliest_due_date,
               SUM(CASE WHEN COALESCE(cr.balance,0)>0 AND cr.due_date < CURRENT_DATE THEN 1 ELSE 0 END) AS overdue_count
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        GROUP BY c.name, cr.project_code, cr.cabinet_no
        ORDER BY SUM(cr.balance) DESC NULLS LAST, c.name
        LIMIT 300
        """
    )
    for row in rows:
        row["next_step"] = "逾期优先催收" if as_decimal(row.get("overdue_count")) > 0 else "按余额和到期日跟进"
    return _render_finance_report(
        "应收账款汇总表",
        "按客户、项目号和柜号汇总应收发生、已收和余额；用于回款计划和项目资金占用核对。",
        [
            {"label": "汇总行数", "value": len(rows), "hint": "客户/项目/柜号"},
            {"label": "应收余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows)), "hint": "当前列表"},
            {"label": "逾期组数", "value": sum(1 for r in rows if as_decimal(r.get("overdue_count")) > 0), "hint": "存在逾期应收"},
        ],
        [{"title": "应收汇总", "rows": rows, "columns": _columns(("customer_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("doc_count", "单据数"), ("total_amount", "应收金额"), ("received_amount", "已收金额"), ("balance", "未收余额"), ("earliest_due_date", "最早到期日"), ("overdue_count", "逾期笔数"), ("next_step", "下一步"))}],
    )


def render_payable_summary_report(query_rows):
    rows = query_rows(
        """
        SELECT s.name AS supplier_name, sp.project_code, sp.cabinet_no,
               COUNT(*) AS doc_count, SUM(sp.amount) AS amount,
               SUM(sp.paid_amount) AS paid_amount, SUM(sp.balance) AS balance,
               MIN(COALESCE(sp.next_follow_up_date, sp.doc_date)) AS earliest_due_date,
               SUM(CASE WHEN COALESCE(sp.balance,0)>0 AND COALESCE(sp.next_follow_up_date, sp.doc_date) < CURRENT_DATE THEN 1 ELSE 0 END) AS overdue_count
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        GROUP BY s.name, sp.project_code, sp.cabinet_no
        ORDER BY SUM(sp.balance) DESC NULLS LAST, s.name
        LIMIT 300
        """
    )
    for row in rows:
        row["next_step"] = "逾期优先确认付款安排" if as_decimal(row.get("overdue_count")) > 0 else "按账期和资金计划跟进"
    return _render_finance_report(
        "应付账款汇总表",
        "按供应商、项目号和柜号汇总应付发生、已付和余额；用于付款计划和供应商对账。",
        [
            {"label": "汇总行数", "value": len(rows), "hint": "供应商/项目/柜号"},
            {"label": "应付余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows)), "hint": "当前列表"},
            {"label": "逾期组数", "value": sum(1 for r in rows if as_decimal(r.get("overdue_count")) > 0), "hint": "存在逾期应付"},
        ],
        [{"title": "应付汇总", "rows": rows, "columns": _columns(("supplier_name", "供应商"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("doc_count", "单据数"), ("amount", "应付金额"), ("paid_amount", "已付金额"), ("balance", "未付余额"), ("earliest_due_date", "最早跟进日"), ("overdue_count", "逾期笔数"), ("next_step", "下一步"))}],
    )

def render_payment_request_statistics_report(query_rows):
    rows = query_rows(
        """
        SELECT s.name AS supplier_name, sp.project_code, sp.cabinet_no,
               CASE
                   WHEN COALESCE(sp.balance,0)<=0 THEN '已结清'
                   WHEN COALESCE(sp.next_follow_up_date, sp.doc_date) < CURRENT_DATE THEN '已逾期'
                   WHEN COALESCE(sp.next_follow_up_date, sp.doc_date) <= CURRENT_DATE + INTERVAL '7 days' THEN '7天内到期'
                   ELSE '未到期'
               END AS request_bucket,
               COUNT(*) AS payable_count,
               SUM(sp.amount) AS payable_amount,
               SUM(sp.paid_amount) AS paid_amount,
               SUM(sp.balance) AS request_amount,
               MIN(COALESCE(sp.next_follow_up_date, sp.doc_date)) AS earliest_due_date,
               '到付款单据处理，不在统计表生成付款申请' AS next_step
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE COALESCE(sp.balance,0)>0
        GROUP BY s.name, sp.project_code, sp.cabinet_no,
                 CASE
                   WHEN COALESCE(sp.balance,0)<=0 THEN '已结清'
                   WHEN COALESCE(sp.next_follow_up_date, sp.doc_date) < CURRENT_DATE THEN '已逾期'
                   WHEN COALESCE(sp.next_follow_up_date, sp.doc_date) <= CURRENT_DATE + INTERVAL '7 days' THEN '7天内到期'
                   ELSE '未到期'
                 END
        ORDER BY MIN(COALESCE(sp.next_follow_up_date, sp.doc_date)) NULLS FIRST, SUM(sp.balance) DESC
        LIMIT 300
        """
    )
    return _render_finance_report(
        "付款申请统计表",
        "按供应商、项目号、柜号和付款紧急程度统计应付余额；付款申请单仍保持隐藏，不在报表页生成申请。",
        [
            {"label": "统计行数", "value": len(rows), "hint": "最多 300 行"},
            {"label": "建议付款金额", "value": money_metric(sum(as_decimal(r.get("request_amount")) for r in rows)), "hint": "未付余额"},
            {"label": "逾期组数", "value": sum(1 for r in rows if r.get("request_bucket") == "已逾期"), "hint": "优先处理"},
        ],
        [{"title": "付款申请统计", "rows": rows, "columns": _columns(("supplier_name", "供应商"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("request_bucket", "付款分类"), ("payable_count", "应付笔数"), ("payable_amount", "应付金额"), ("paid_amount", "已付金额"), ("request_amount", "建议付款金额"), ("earliest_due_date", "最早跟进日"), ("next_step", "下一步"))}],
    )


def render_receivable_warning_report(query_rows):
    rows = query_rows(
        """
        SELECT cr.id, cr.source_no, cr.receivable_date, cr.due_date, c.name AS customer_name,
               cr.project_code, cr.cabinet_no, cr.total_amount, cr.received_amount, cr.balance,
               CURRENT_DATE - COALESCE(cr.due_date, cr.receivable_date, CURRENT_DATE) AS age_days,
               CASE
                   WHEN cr.due_date IS NOT NULL AND cr.due_date < CURRENT_DATE THEN '逾期预警'
                   WHEN cr.due_date IS NULL THEN '缺少到期日'
                   WHEN cr.due_date <= CURRENT_DATE + INTERVAL '7 days' THEN '7天内到期'
                   ELSE '未到期'
               END AS warning_type,
               CASE
                   WHEN cr.due_date IS NOT NULL AND cr.due_date < CURRENT_DATE THEN '高'
                   WHEN cr.due_date IS NULL THEN '中'
                   ELSE '低'
               END AS warning_level,
               '核对发货签收、客户对账和收款计划' AS next_step
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE COALESCE(cr.balance,0)>0
          AND (cr.due_date IS NULL OR cr.due_date <= CURRENT_DATE + INTERVAL '7 days')
        ORDER BY cr.due_date NULLS FIRST, cr.balance DESC, cr.id DESC
        LIMIT 300
        """
    )
    for row in rows:
        row["aging_bucket"] = _aging_bucket(row.get("age_days"))
    return _render_finance_report(
        "应收账款预警表",
        "按到期日、逾期天数和未收余额列示应收风险；用于催收和对账，不在本页核销。",
        [
            {"label": "预警行数", "value": len(rows), "hint": "最多 300 行"},
            {"label": "预警余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows)), "hint": "当前列表"},
            {"label": "高风险", "value": sum(1 for r in rows if r.get("warning_level") == "高"), "hint": "已逾期"},
        ],
        [{"title": "应收预警", "rows": rows, "columns": _columns(("warning_level", "预警等级"), ("warning_type", "预警类型"), ("source_no", "来源单据"), ("receivable_date", "应收日期"), ("due_date", "到期日"), ("customer_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("balance", "未收余额"), ("age_days", "逾期天数"), ("aging_bucket", "账龄区间"), ("next_step", "下一步"))}],
    )


def render_payable_warning_report(query_rows):
    rows = query_rows(
        """
        SELECT sp.id, sp.doc_no, sp.doc_date, COALESCE(sp.next_follow_up_date, sp.doc_date) AS due_date,
               s.name AS supplier_name, sp.project_code, sp.cabinet_no, sp.amount, sp.paid_amount, sp.balance,
               CURRENT_DATE - COALESCE(sp.next_follow_up_date, sp.doc_date, CURRENT_DATE) AS age_days,
               CASE
                   WHEN COALESCE(sp.next_follow_up_date, sp.doc_date) < CURRENT_DATE THEN '逾期预警'
                   WHEN COALESCE(sp.next_follow_up_date, sp.doc_date) <= CURRENT_DATE + INTERVAL '7 days' THEN '7天内到期'
                   ELSE '未到期'
               END AS warning_type,
               CASE
                   WHEN COALESCE(sp.next_follow_up_date, sp.doc_date) < CURRENT_DATE THEN '高'
                   ELSE '低'
               END AS warning_level,
               '核对到货、发票、供应商对账和付款计划' AS next_step
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE COALESCE(sp.balance,0)>0
          AND COALESCE(sp.next_follow_up_date, sp.doc_date) <= CURRENT_DATE + INTERVAL '7 days'
        ORDER BY COALESCE(sp.next_follow_up_date, sp.doc_date) NULLS FIRST, sp.balance DESC, sp.id DESC
        LIMIT 300
        """
    )
    for row in rows:
        row["aging_bucket"] = _aging_bucket(row.get("age_days"))
    return _render_finance_report(
        "应付账款预警表",
        "按跟进日、逾期天数和未付余额列示应付风险；用于资金计划和供应商对账，不在本页付款。",
        [
            {"label": "预警行数", "value": len(rows), "hint": "最多 300 行"},
            {"label": "预警余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows)), "hint": "当前列表"},
            {"label": "高风险", "value": sum(1 for r in rows if r.get("warning_level") == "高"), "hint": "已逾期"},
        ],
        [{"title": "应付预警", "rows": rows, "columns": _columns(("warning_level", "预警等级"), ("warning_type", "预警类型"), ("doc_no", "来源单据"), ("doc_date", "应付日期"), ("due_date", "跟进日"), ("supplier_name", "供应商"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("balance", "未付余额"), ("age_days", "逾期天数"), ("aging_bucket", "账龄区间"), ("next_step", "下一步"))}],
    )


def render_bad_debt_reserve_balance_report(query_rows):
    rows = query_rows(
        """
        SELECT cr.id, cr.source_no, cr.receivable_date, cr.due_date, c.name AS customer_name,
               cr.project_code, cr.cabinet_no, cr.total_amount, cr.received_amount, cr.balance,
               CURRENT_DATE - COALESCE(cr.due_date, cr.receivable_date, CURRENT_DATE) AS age_days,
               cr.status
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE COALESCE(cr.balance,0)>0
        ORDER BY COALESCE(cr.due_date, cr.receivable_date) NULLS FIRST, cr.balance DESC, cr.id DESC
        LIMIT 500
        """
    )
    for row in rows:
        rate = _bad_debt_rate(row.get("age_days"))
        row["aging_bucket"] = _aging_bucket(row.get("age_days"))
        row["reserve_rate"] = f"{(rate * Decimal('100')).quantize(Decimal('0.01'))}%"
        row["reserve_balance"] = (as_decimal(row.get("balance")) * rate).quantize(Decimal("0.01"))
        row["next_step"] = "持续催收并保留对账依据" if rate > 0 else "未达到准备建议口径"
    bucket_rows = []
    for bucket in ("未到期", "0-30天", "31-60天", "61-90天", "91-180天", "180天以上"):
        bucket_items = [row for row in rows if row.get("aging_bucket") == bucket]
        if bucket_items:
            bucket_rows.append(
                {
                    "aging_bucket": bucket,
                    "doc_count": len(bucket_items),
                    "receivable_balance": sum(as_decimal(row.get("balance")) for row in bucket_items),
                    "reserve_balance": sum(as_decimal(row.get("reserve_balance")) for row in bucket_items),
                }
            )
    return _render_finance_report(
        "坏账准备余额表",
        "按应收账龄派生坏账准备建议余额；只作管理报表，不生成坏账计提、转回或核销凭证。",
        [
            {"label": "应收余额", "value": money_metric(sum(as_decimal(r.get("balance")) for r in rows)), "hint": "当前列表"},
            {"label": "建议准备", "value": money_metric(sum(as_decimal(r.get("reserve_balance")) for r in rows)), "hint": "账龄派生"},
            {"label": "明细行数", "value": len(rows), "hint": "最多 500 行"},
        ],
        [
            {"title": "账龄汇总", "rows": bucket_rows, "columns": _columns(("aging_bucket", "账龄区间"), ("doc_count", "单据数"), ("receivable_balance", "应收余额"), ("reserve_balance", "建议准备余额"))},
            {"title": "坏账准备明细", "rows": rows, "columns": _columns(("source_no", "来源单据"), ("receivable_date", "应收日期"), ("due_date", "到期日"), ("customer_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("balance", "应收余额"), ("age_days", "逾期天数"), ("aging_bucket", "账龄区间"), ("reserve_rate", "建议比例"), ("reserve_balance", "建议准备余额"), ("next_step", "下一步"))},
        ],
    )


def render_auto_settlement_schemes(query_rows):
    rows = [
        {
            "scheme_no": "AR-MATCH-001",
            "scheme_name": "客户收款按客户+项目+柜号匹配",
            "settlement_type": "应收收款",
            "match_basis": "客户、项目号、柜号、未收余额",
            "status": "启用建议",
            "next_step": "进入智能收款核对建议，人工确认后到收款单处理",
        },
        {
            "scheme_no": "AP-MATCH-001",
            "scheme_name": "供应商付款按供应商+项目+柜号匹配",
            "settlement_type": "应付付款",
            "match_basis": "供应商、项目号、柜号、未付余额",
            "status": "启用建议",
            "next_step": "进入智能付款核对建议，人工确认后到付款单处理",
        },
        {
            "scheme_no": "CASH-MATCH-001",
            "scheme_name": "现金银行流水来源单据反查",
            "settlement_type": "资金流水",
            "match_basis": "流水来源类型、来源单号、往来单位",
            "status": "只读核对",
            "next_step": "核对现金银行流水，不自动生成业务单据",
        },
    ]
    return render_template(
        "finance_counterparty_tools.html",
        title="自动核销方案列表",
        subtitle="往来核销匹配方案清单；当前只作为收付款核对建议，不自动改写应收、应付或现金银行余额。",
        metrics=[
            {"label": "方案数", "value": len(rows), "hint": "应收、应付、资金流水"},
            {"label": "执行方式", "value": "人工确认", "hint": "不自动过账"},
            {"label": "影响范围", "value": "只读建议", "hint": "核销仍在收付款单完成"},
        ],
        sections=[{"title": "方案列表", "rows": rows, "columns": _columns(("scheme_no", "方案编码"), ("scheme_name", "方案名称"), ("settlement_type", "核销类型"), ("match_basis", "匹配依据"), ("status", "状态"), ("next_step", "下一步"))}],
    )


def render_auto_settlement_runs(query_rows):
    rows = query_rows(
        """
        SELECT 'AR-' || s.id::text AS run_no, s.created_at::date AS run_date,
               '客户收款核销' AS scheme_name, r.receipt_no AS source_no,
               c.name AS partner_name, s.applied_amount AS settled_amount,
               '已生成核销明细' AS status,
               '查看收款单并复核应收余额' AS next_step
        FROM customer_receipt_settlements s
        JOIN customer_receipts r ON r.id=s.receipt_id
        LEFT JOIN customers c ON c.id=r.customer_id
        UNION ALL
        SELECT 'AP-' || s.id::text AS run_no, s.created_at::date AS run_date,
               '供应商付款核销' AS scheme_name, p.payment_no AS source_no,
               sup.name AS partner_name, s.applied_amount AS settled_amount,
               '已生成核销明细' AS status,
               '查看付款单并复核应付余额' AS next_step
        FROM supplier_payment_settlements s
        JOIN supplier_payments p ON p.id=s.payment_id
        LEFT JOIN suppliers sup ON sup.id=p.supplier_id
        ORDER BY run_date DESC NULLS LAST, run_no DESC
        LIMIT 200
        """
    )
    return render_template(
        "finance_counterparty_tools.html",
        title="自动核销执行日志",
        subtitle="展示系统中已经形成的收款/付款核销明细；本页不重新执行核销。",
        metrics=[
            {"label": "日志行数", "value": len(rows), "hint": "最近 200 条"},
            {"label": "核销金额", "value": money_metric(sum(as_decimal(row.get("settled_amount")) for row in rows)), "hint": "当前列表合计"},
            {"label": "状态", "value": "只读", "hint": "用于复核和追溯"},
        ],
        sections=[{"title": "执行日志", "rows": rows, "columns": _columns(("run_no", "日志号"), ("run_date", "执行日期"), ("scheme_name", "方案"), ("source_no", "来源单据"), ("partner_name", "往来单位"), ("settled_amount", "核销金额"), ("status", "状态"), ("next_step", "下一步"))}],
    )


def render_manual_settlement_console(query_rows):
    open_receivables = _open_receivables(query_rows)[:80]
    open_payables = _open_payables(query_rows)[:80]
    unapplied_receipts = query_rows(
        """
        SELECT r.id, r.receipt_no AS doc_no, r.receipt_date AS doc_date, c.name AS partner_name,
               r.project_code, r.cabinet_no, r.amount,
               GREATEST(COALESCE(r.amount,0)-COALESCE(SUM(s.applied_amount),0),0) AS unapplied_amount,
               '到收款单详情补充应收核销明细' AS next_step
        FROM customer_receipts r
        LEFT JOIN customers c ON c.id=r.customer_id
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        WHERE COALESCE(r.receipt_kind,'customer_receipt')='customer_receipt'
        GROUP BY r.id, c.name
        HAVING GREATEST(COALESCE(r.amount,0)-COALESCE(SUM(s.applied_amount),0),0) > 0
        ORDER BY r.receipt_date DESC NULLS LAST, r.id DESC
        LIMIT 80
        """
    )
    unapplied_payments = query_rows(
        """
        SELECT p.id, p.payment_no AS doc_no, p.payment_date AS doc_date, s.name AS partner_name,
               p.project_code, p.cabinet_no, p.amount,
               GREATEST(COALESCE(p.amount,0)-COALESCE(SUM(ps.applied_amount),0),0) AS unapplied_amount,
               '到付款单详情补充应付核销明细' AS next_step
        FROM supplier_payments p
        LEFT JOIN suppliers s ON s.id=p.supplier_id
        LEFT JOIN supplier_payment_settlements ps ON ps.payment_id=p.id
        WHERE COALESCE(p.payment_kind,'supplier_payment')='supplier_payment'
        GROUP BY p.id, s.name
        HAVING GREATEST(COALESCE(p.amount,0)-COALESCE(SUM(ps.applied_amount),0),0) > 0
        ORDER BY p.payment_date DESC NULLS LAST, p.id DESC
        LIMIT 80
        """
    )
    return render_template(
        "finance_counterparty_tools.html",
        title="手动核销",
        subtitle="人工选择未清应收/应付与未分配收付款进行核对；金额写入仍通过收款单、付款单详情页执行。",
        metrics=[
            {"label": "未清应收", "value": len(open_receivables), "hint": "最多 80 行"},
            {"label": "未清应付", "value": len(open_payables), "hint": "最多 80 行"},
            {"label": "未分配收付款", "value": len(unapplied_receipts) + len(unapplied_payments), "hint": "需要补核销"},
        ],
        actions=[
            {"label": "新增收款单", "href": "/customer-receipts/new"},
            {"label": "新增付款单", "href": "/payments/new"},
            {"label": "现金银行流水", "href": "/finance/cash-bank/journal"},
        ],
        sections=[
            {"title": "未清应收", "rows": open_receivables, "columns": _columns(("source_no", "来源单据"), ("receivable_date", "应收日期"), ("partner_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("total_amount", "应收金额"), ("received_amount", "已收金额"), ("balance", "未收余额"), ("status", "状态"))},
            {"title": "未分配收款", "rows": unapplied_receipts, "columns": _columns(("doc_no", "收款单"), ("doc_date", "日期"), ("partner_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("amount", "收款金额"), ("unapplied_amount", "未分配金额"), ("next_step", "下一步"))},
            {"title": "未清应付", "rows": open_payables, "columns": _columns(("doc_no", "来源单据"), ("doc_date", "应付日期"), ("partner_name", "供应商"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("amount", "应付金额"), ("paid_amount", "已付金额"), ("balance", "未付余额"), ("status", "状态"))},
            {"title": "未分配付款", "rows": unapplied_payments, "columns": _columns(("doc_no", "付款单"), ("doc_date", "日期"), ("partner_name", "供应商"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("amount", "付款金额"), ("unapplied_amount", "未分配金额"), ("next_step", "下一步"))},
        ],
    )


def render_smart_collection_queue(query_rows):
    keyword = (request.args.get("keyword") or "").strip()
    clause, params = _counterparty_keyword_filter("cr", ("source_no", "project_code", "cabinet_no", "status"), keyword)
    if keyword:
        clause = clause[:-1] + " OR COALESCE(c.name,'') ILIKE %s)"
        params.append(f"%{keyword}%")
    rows = query_rows(
        f"""
        SELECT cr.id, cr.source_no, cr.receivable_date, cr.due_date, c.name AS partner_name,
               cr.project_code, cr.cabinet_no, cr.total_amount, cr.received_amount, cr.balance,
               CASE
                   WHEN cr.due_date IS NOT NULL AND cr.due_date < CURRENT_DATE THEN '逾期优先催收并核对回单'
                   WHEN cr.due_date IS NOT NULL THEN '按到期日安排收款'
                   ELSE '补齐到期日和收款责任人'
               END AS match_advice,
               '/customer-receipts/new?customer_id=' || cr.customer_id::text || '&receivable_id=' || cr.id::text AS action_url
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE COALESCE(cr.balance,0)>0 {clause}
        ORDER BY cr.due_date NULLS FIRST, cr.balance DESC, cr.id DESC
        LIMIT 200
        """,
        tuple(params),
    )
    return render_template(
        "finance_counterparty_tools.html",
        title="智能收款",
        subtitle="按客户、项目号、柜号和到期日生成收款建议；不自动创建收款单。",
        metrics=[
            {"label": "建议行数", "value": len(rows), "hint": "最多 200 行"},
            {"label": "待收金额", "value": money_metric(sum(as_decimal(row.get("balance")) for row in rows)), "hint": "当前筛选"},
            {"label": "处理方式", "value": "人工登记", "hint": "跳转收款单"},
        ],
        sections=[{"title": "收款建议", "rows": rows, "columns": _columns(("source_no", "来源单据"), ("receivable_date", "应收日期"), ("due_date", "到期日"), ("partner_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("total_amount", "应收金额"), ("received_amount", "已收金额"), ("balance", "待收金额"), ("match_advice", "建议"))}],
    )


def render_smart_payment_queue(query_rows):
    keyword = (request.args.get("keyword") or "").strip()
    clause, params = _counterparty_keyword_filter("sp", ("doc_no", "project_code", "cabinet_no", "status"), keyword)
    if keyword:
        clause = clause[:-1] + " OR COALESCE(s.name,'') ILIKE %s)"
        params.append(f"%{keyword}%")
    rows = query_rows(
        f"""
        SELECT sp.id, sp.doc_no, sp.doc_date, COALESCE(sp.next_follow_up_date, sp.doc_date) AS due_date,
               s.name AS partner_name, sp.project_code, sp.cabinet_no, sp.amount, sp.paid_amount, sp.balance,
               CASE
                   WHEN sp.next_follow_up_date IS NOT NULL AND sp.next_follow_up_date < CURRENT_DATE THEN '跟进日已过，确认付款安排'
                   WHEN sp.next_follow_up_date IS NOT NULL THEN '按跟进日安排付款'
                   ELSE '补齐账期和付款计划'
               END AS match_advice,
               '/payments/new?supplier_id=' || sp.supplier_id::text || '&payable_id=' || sp.id::text AS action_url
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE COALESCE(sp.balance,0)>0 {clause}
        ORDER BY COALESCE(sp.next_follow_up_date, sp.doc_date) NULLS FIRST, sp.balance DESC, sp.id DESC
        LIMIT 200
        """,
        tuple(params),
    )
    return render_template(
        "finance_counterparty_tools.html",
        title="智能付款",
        subtitle="按供应商、项目号、柜号和付款跟进日生成付款建议；不自动创建付款单。",
        metrics=[
            {"label": "建议行数", "value": len(rows), "hint": "最多 200 行"},
            {"label": "待付金额", "value": money_metric(sum(as_decimal(row.get("balance")) for row in rows)), "hint": "当前筛选"},
            {"label": "处理方式", "value": "人工登记", "hint": "跳转付款单"},
        ],
        sections=[{"title": "付款建议", "rows": rows, "columns": _columns(("doc_no", "来源单据"), ("doc_date", "应付日期"), ("due_date", "跟进日"), ("partner_name", "供应商"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("amount", "应付金额"), ("paid_amount", "已付金额"), ("balance", "待付金额"), ("match_advice", "建议"))}],
    )


def render_counterparty_matching_statement(query_rows):
    rows = query_rows(
        """
        SELECT name AS partner_name,
               MAX(customer_id) AS customer_id,
               MAX(supplier_id) AS supplier_id,
               COALESCE(SUM(receivable_balance),0) AS receivable_balance,
               COALESCE(SUM(payable_balance),0) AS payable_balance,
               COALESCE(SUM(receivable_balance),0)-COALESCE(SUM(payable_balance),0) AS net_balance,
               CASE
                   WHEN MAX(customer_id) IS NOT NULL AND MAX(supplier_id) IS NOT NULL THEN '客户/供应商同名匹配'
                   WHEN MAX(customer_id) IS NOT NULL THEN '仅客户'
                   ELSE '仅供应商'
               END AS match_status
        FROM (
            SELECT c.name, c.id AS customer_id, NULL::INTEGER AS supplier_id,
                   COALESCE(SUM(cr.balance),0) AS receivable_balance, 0::NUMERIC AS payable_balance
            FROM customers c
            LEFT JOIN customer_receivables cr ON cr.customer_id=c.id
            GROUP BY c.id, c.name
            UNION ALL
            SELECT s.name, NULL::INTEGER AS customer_id, s.id AS supplier_id,
                   0::NUMERIC AS receivable_balance, COALESCE(SUM(sp.balance),0) AS payable_balance
            FROM suppliers s
            LEFT JOIN supplier_payables sp ON sp.supplier_id=s.id
            GROUP BY s.id, s.name
        ) t
        WHERE COALESCE(name,'') <> ''
        GROUP BY name
        ORDER BY ABS(COALESCE(SUM(receivable_balance),0)-COALESCE(SUM(payable_balance),0)) DESC, name
        LIMIT 200
        """
    )
    return render_template(
        "finance_counterparty_tools.html",
        title="客商匹配对账单",
        subtitle="按同名客户/供应商汇总应收、应付和净额；用于识别同一客商双向往来。",
        metrics=[
            {"label": "客商行数", "value": len(rows), "hint": "最多 200 行"},
            {"label": "应收净额", "value": money_metric(sum(as_decimal(row.get("receivable_balance")) for row in rows)), "hint": "当前列表"},
            {"label": "应付净额", "value": money_metric(sum(as_decimal(row.get("payable_balance")) for row in rows)), "hint": "当前列表"},
        ],
        sections=[{"title": "客商匹配", "rows": rows, "columns": _columns(("partner_name", "客商名称"), ("receivable_balance", "应收余额"), ("payable_balance", "应付余额"), ("net_balance", "净额"), ("match_status", "匹配状态"))}],
    )


def render_statement_history(query_rows):
    rows = query_rows(
        """
        SELECT '客户' AS partner_type, c.name AS partner_name, r.receipt_no AS doc_no,
               r.receipt_date AS doc_date, COALESCE(SUM(s.applied_amount),0) AS settled_amount,
               r.project_code, r.cabinet_no, '收款核销记录' AS statement_basis
        FROM customer_receipts r
        LEFT JOIN customers c ON c.id=r.customer_id
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        GROUP BY r.id, c.name
        UNION ALL
        SELECT '供应商' AS partner_type, sup.name AS partner_name, p.payment_no AS doc_no,
               p.payment_date AS doc_date, COALESCE(SUM(ps.applied_amount),0) AS settled_amount,
               p.project_code, p.cabinet_no, '付款核销记录' AS statement_basis
        FROM supplier_payments p
        LEFT JOIN suppliers sup ON sup.id=p.supplier_id
        LEFT JOIN supplier_payment_settlements ps ON ps.payment_id=p.id
        GROUP BY p.id, sup.name
        ORDER BY doc_date DESC NULLS LAST, doc_no DESC
        LIMIT 200
        """
    )
    return render_template(
        "finance_counterparty_tools.html",
        title="历史对账单",
        subtitle="按已经发生的收付款与核销明细形成历史对账查询；不生成新的对账确认单。",
        metrics=[
            {"label": "记录数", "value": len(rows), "hint": "最近 200 行"},
            {"label": "核销金额", "value": money_metric(sum(as_decimal(row.get("settled_amount")) for row in rows)), "hint": "当前列表"},
            {"label": "来源", "value": "收付款", "hint": "核销明细"},
        ],
        sections=[{"title": "历史对账", "rows": rows, "columns": _columns(("partner_type", "类型"), ("partner_name", "往来单位"), ("doc_no", "收付款单"), ("doc_date", "日期"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("settled_amount", "核销金额"), ("statement_basis", "依据"))}],
    )


def render_statement_templates():
    rows = [
        {"template_no": "CUST-STMT", "template_name": "客户对账函", "partner_type": "客户", "basis": "应收余额、收款核销、项目号、柜号", "status": "启用", "next_step": "从客户对账单导出后线下确认"},
        {"template_no": "SUP-STMT", "template_name": "供应商对账函", "partner_type": "供应商", "basis": "应付余额、付款核销、项目号、柜号", "status": "启用", "next_step": "从供应商对账单导出后线下确认"},
        {"template_no": "CP-MATCH", "template_name": "客商匹配确认函", "partner_type": "客商", "basis": "同名客户/供应商应收应付净额", "status": "启用", "next_step": "从客商匹配对账单复核"},
    ]
    return render_template(
        "finance_counterparty_tools.html",
        title="对账函模板列表",
        subtitle="对账函模板口径清单；模板维护仅定义查询口径，不在本页生成业务单据。",
        metrics=[
            {"label": "模板数", "value": len(rows), "hint": "客户/供应商/客商"},
            {"label": "用途", "value": "对账确认", "hint": "只读口径"},
            {"label": "输出", "value": "报表导出", "hint": "不自动发函"},
        ],
        sections=[{"title": "模板列表", "rows": rows, "columns": _columns(("template_no", "模板编码"), ("template_name", "模板名称"), ("partner_type", "往来类型"), ("basis", "取数依据"), ("status", "状态"), ("next_step", "下一步"))}],
    )


def _form_decimal(name, default="0"):
    return as_decimal(request.form.get(name), default)


def _posted_settlement_amount(row_id):
    for key in (f"settle_{row_id}", f"settlement_amount_{row_id}", f"apply_{row_id}"):
        if key in request.form:
            return as_decimal(request.form.get(key))
    return Decimal("0")


def _receipt_payment_methods():
    return ["银行转账", "现金", "承兑汇票", "支付宝/微信", "其他"]


def _partner_test_data_clause(alias, column="name"):
    field = f"COALESCE({alias}.{column},'')"
    return (
        f"{field} NOT LIKE '测试%%' "
        f"AND {field} NOT LIKE '售后%%' "
        f"AND {field} NOT LIKE 'Delete Customer%%' "
        f"AND {field} NOT ILIKE 'CF supplier%%' "
        f"AND {field} NOT ILIKE 'Delete%%'"
    )


def _open_receivables(query_rows, customer_id=None):
    params = []
    where = ["COALESCE(cr.balance,0) > 0", _partner_test_data_clause("c")]
    if customer_id:
        where.append("cr.customer_id=%s")
        params.append(customer_id)
    return query_rows(
        f"""
        SELECT cr.id, cr.source_type, cr.source_id, cr.source_no, cr.receivable_date,
               cr.due_date, cr.customer_id, c.name AS partner_name, cr.total_amount,
               cr.received_amount, cr.balance, cr.project_code, cr.cabinet_no,
               cr.cost_object_id, cr.status
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE {' AND '.join(where)}
        ORDER BY cr.due_date NULLS LAST, cr.id
        LIMIT 200
        """,
        tuple(params),
    )


def _open_payables(query_rows, supplier_id=None):
    params = []
    where = ["COALESCE(sp.balance,0) > 0", _partner_test_data_clause("s")]
    if supplier_id:
        where.append("sp.supplier_id=%s")
        params.append(supplier_id)
    return query_rows(
        f"""
        SELECT sp.id, sp.payable_no, sp.doc_type, sp.doc_id, sp.doc_no, sp.source_no, sp.doc_date,
               sp.supplier_id, s.name AS partner_name, sp.amount,
               sp.paid_amount, sp.balance, sp.cost_object_id, sp.project_code, sp.cabinet_no, sp.status
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE {' AND '.join(where)}
        ORDER BY sp.next_follow_up_date NULLS LAST, sp.id
        LIMIT 200
        """,
        tuple(params),
    )


def render_payable_list(query_rows, money_metric_func):
    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    date_from = (request.args.get("date_from") or request.args.get("date_start") or "").strip()
    date_to = (request.args.get("date_to") or request.args.get("date_end") or "").strip()
    params = []
    where = ["1=1"]
    if keyword:
        pattern = f"%{keyword}%"
        where.append(
            "(sp.payable_no ILIKE %s OR sp.doc_no ILIKE %s OR sp.source_no ILIKE %s OR s.name ILIKE %s OR sp.project_code ILIKE %s OR sp.cabinet_no ILIKE %s OR sp.finance_remark ILIKE %s)"
        )
        params.extend([pattern] * 7)
    if status:
        where.append("COALESCE(sp.status, '')=%s")
        params.append(status)
    if date_from:
        where.append("sp.doc_date >= %s")
        params.append(date_from)
    if date_to:
        where.append("sp.doc_date <= %s")
        params.append(date_to)
    rows = query_rows(
        f"""
        SELECT sp.id, sp.payable_no, sp.doc_type, sp.doc_id, sp.doc_no, sp.source_no, sp.doc_date,
               sp.supplier_id, s.name AS supplier_name, s.contact_person, s.phone AS supplier_phone,
               sp.project_code, sp.cabinet_no, sp.amount, sp.paid_amount, sp.balance,
               sp.status, sp.next_follow_up_date,
               CASE
                   WHEN sp.next_follow_up_date IS NOT NULL THEN sp.next_follow_up_date::VARCHAR
                   WHEN sp.doc_date IS NOT NULL THEN sp.doc_date::VARCHAR
                   ELSE '未维护'
               END AS payment_term,
               CASE
                   WHEN COALESCE(sp.balance,0)=0 THEN '已结清，保留对账记录'
                   WHEN sp.next_follow_up_date IS NOT NULL AND sp.next_follow_up_date < CURRENT_DATE THEN '跟进日已过，安排付款或供应商沟通'
                   WHEN sp.next_follow_up_date IS NOT NULL THEN '按跟进日核对付款计划'
                   ELSE '补充账期/跟进日期'
               END AS next_step
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(sp.next_follow_up_date, sp.doc_date) NULLS FIRST, sp.id DESC
        LIMIT 300
        """,
        tuple(params),
    )
    statuses = query_rows(
        """
        SELECT status, COUNT(*) AS count
        FROM supplier_payables
        WHERE COALESCE(status, '') <> ''
        GROUP BY status
        ORDER BY count DESC, status
        """
    )
    summary = {
        "open_count": sum(1 for row in rows if (row.get("balance") or 0) != 0),
        "balance": money_metric_func(sum((row.get("balance") or 0) for row in rows)),
    }
    return render_template(
        "payable_list.html",
        title="应付账款列表",
        subtitle="按供应商、来源单、项目号、柜号、账期和未付余额展示应付，不在采购工作台渲染完整应付清单。",
        rows=rows,
        statuses=statuses,
        filters={"keyword": keyword, "status": status, "date_from": date_from, "date_to": date_to},
        summary=summary,
    )


def render_receivable_list(query_rows, money_metric_func):
    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    date_from = (request.args.get("date_from") or request.args.get("date_start") or "").strip()
    date_to = (request.args.get("date_to") or request.args.get("date_end") or "").strip()
    params = []
    where = ["1=1"]
    if keyword:
        pattern = f"%{keyword}%"
        where.append(
            "(cr.receivable_no ILIKE %s OR cr.source_no ILIKE %s OR c.name ILIKE %s OR cr.project_code ILIKE %s OR cr.cabinet_no ILIKE %s OR cr.remark ILIKE %s)"
        )
        params.extend([pattern] * 6)
    if status:
        where.append("COALESCE(cr.status, '')=%s")
        params.append(status)
    if date_from:
        where.append("cr.receivable_date >= %s")
        params.append(date_from)
    if date_to:
        where.append("cr.receivable_date <= %s")
        params.append(date_to)
    rows = query_rows(
        f"""
        SELECT cr.id, cr.receivable_no, cr.source_type, cr.source_id, cr.source_no, cr.receivable_date,
               cr.due_date, cr.customer_id, c.name AS customer_name,
               c.contact_person, c.phone AS customer_phone,
               cr.project_code, cr.cabinet_no, cr.total_amount, cr.received_amount,
               cr.balance, cr.status,
               CASE
                   WHEN cr.due_date IS NOT NULL THEN cr.due_date::VARCHAR
                   WHEN cr.receivable_date IS NOT NULL THEN cr.receivable_date::VARCHAR
                   ELSE '未维护'
               END AS collection_term,
               CASE
                   WHEN COALESCE(cr.balance,0)=0 THEN '已结清，保留对账记录'
                   WHEN cr.due_date IS NOT NULL AND cr.due_date < CURRENT_DATE THEN '已逾期，核对发货签收并催收'
                   WHEN cr.due_date IS NOT NULL THEN '按到期日跟进收款'
                   ELSE '补充到期日和回款责任'
               END AS next_step
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(cr.due_date, cr.receivable_date) NULLS FIRST, cr.id DESC
        LIMIT 300
        """,
        tuple(params),
    )
    statuses = query_rows(
        """
        SELECT status, COUNT(*) AS count
        FROM customer_receivables
        WHERE COALESCE(status, '') <> ''
        GROUP BY status
        ORDER BY count DESC, status
        """
    )
    summary = {
        "open_count": sum(1 for row in rows if (row.get("balance") or 0) != 0),
        "balance": money_metric_func(sum((row.get("balance") or 0) for row in rows)),
    }
    return render_template(
        "receivable_list.html",
        title="应收账款列表",
        subtitle="按客户、来源单、项目号、柜号、到期日和未收余额展示应收；回款登记从收款单入口进入。",
        rows=rows,
        statuses=statuses,
        filters={"keyword": keyword, "status": status, "date_from": date_from, "date_to": date_to},
        summary=summary,
    )


def render_receivable_payable_workbench(query_one, query_rows):
    def scalar(sql, params=()):
        row = query_one(sql, params) or {}
        return row.get("value") or 0

    metrics = {
        "receivable_balance": scalar("SELECT COALESCE(SUM(balance),0) AS value FROM customer_receivables"),
        "payable_balance": scalar("SELECT COALESCE(SUM(balance),0) AS value FROM supplier_payables"),
        "overdue_receivable_count": scalar(
            "SELECT COUNT(*) AS value FROM customer_receivables WHERE COALESCE(balance,0)>0 AND due_date < CURRENT_DATE"
        ),
        "due_payable_count": scalar(
            "SELECT COUNT(*) AS value FROM supplier_payables WHERE COALESCE(balance,0)>0 AND COALESCE(next_follow_up_date, doc_date) <= CURRENT_DATE"
        ),
    }
    receivables = query_rows(
        """
        SELECT cr.id, cr.source_no AS doc_no, cr.receivable_date AS doc_date, cr.due_date,
               c.name AS partner_name, cr.project_code, cr.cabinet_no,
               cr.total_amount, cr.received_amount AS settled_amount, cr.balance, cr.status,
               CASE
                   WHEN cr.due_date IS NOT NULL AND cr.due_date < CURRENT_DATE THEN '已逾期，优先催收并核对争议'
                   WHEN cr.due_date IS NOT NULL THEN '按到期日跟进回款'
                   ELSE '补齐到期日和责任人'
               END AS next_step,
               '销售/财务' AS owner_role,
               '影响现金流、项目毛利和期间结账' AS downstream_impact
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE COALESCE(cr.balance,0) > 0
        ORDER BY cr.due_date NULLS FIRST, cr.id DESC
        LIMIT 12
        """
    )
    payables = query_rows(
        """
        SELECT sp.id, sp.doc_no, sp.doc_date, COALESCE(sp.next_follow_up_date, sp.doc_date) AS due_date,
               s.name AS partner_name, sp.project_code, sp.cabinet_no,
               sp.amount AS total_amount, sp.paid_amount AS settled_amount, sp.balance, sp.status,
               CASE
                   WHEN sp.next_follow_up_date IS NOT NULL AND sp.next_follow_up_date < CURRENT_DATE THEN '跟进日已过，确认付款安排'
                   WHEN sp.next_follow_up_date IS NOT NULL THEN '按跟进日核对付款计划'
                   ELSE '补齐账期和付款计划'
               END AS next_step,
               '采购/财务' AS owner_role,
               '影响供应商账期、项目成本和期间结账' AS downstream_impact
        FROM supplier_payables sp
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE COALESCE(sp.balance,0) > 0
        ORDER BY COALESCE(sp.next_follow_up_date, sp.doc_date) NULLS FIRST, sp.id DESC
        LIMIT 12
        """
    )
    return render_template(
        "finance_ar_ap_workbench.html",
        title="应收应付工作台",
        subtitle="围绕收款、付款、往来对账、账龄、资金流水和期间结账的财务闭环入口。",
        metrics=metrics,
        receivables=receivables,
        payables=payables,
    )


def _ar_receipt_config(receipt_kind):
    return AR_RECEIPT_DOCUMENT_TYPES.get(receipt_kind) or AR_RECEIPT_DOCUMENT_TYPES["customer_receipt"]


def _ap_payment_config(payment_kind):
    return AP_PAYMENT_DOCUMENT_TYPES.get(payment_kind) or AP_PAYMENT_DOCUMENT_TYPES["supplier_payment"]


def render_customer_receipt_list(query_rows, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    params = []
    where = ["COALESCE(r.receipt_kind,'customer_receipt')=%s"]
    params.append(receipt_kind)
    if keyword:
        pattern = f"%{keyword}%"
        where.append("(r.receipt_no ILIKE %s OR c.name ILIKE %s OR r.source_no ILIKE %s OR r.project_code ILIKE %s OR r.cabinet_no ILIKE %s OR r.remark ILIKE %s)")
        params.extend([pattern] * 6)
    rows = query_rows(
        f"""
        SELECT r.id, r.receipt_no, r.receipt_date, c.name AS customer_name,
               r.source_no, r.project_code, r.cabinet_no, r.amount,
               COALESCE(SUM(s.applied_amount),0) AS settled_amount,
               GREATEST(COALESCE(r.amount,0)-COALESCE(SUM(s.applied_amount),0),0) AS unapplied_amount,
               COALESCE(STRING_AGG(DISTINCT cr.source_no, ' / ') FILTER (WHERE cr.source_no IS NOT NULL), r.source_no, '-') AS settlement_sources,
               COUNT(DISTINCT s.receivable_id) AS settlement_count,
               r.payment_method, r.bank_account, r.status,
               CASE WHEN %s='out'
                    THEN '已登记资金流出，复核原单据和对账备注'
                    WHEN COALESCE(r.amount,0) <= COALESCE(SUM(s.applied_amount),0)
                    THEN '已核销，核对应收余额'
                    ELSE '存在未分配金额，补充核销明细或备注说明' END AS next_step
        FROM customer_receipts r
        LEFT JOIN customers c ON c.id=r.customer_id
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        LEFT JOIN customer_receivables cr ON cr.id=s.receivable_id
        WHERE {' AND '.join(where)}
        GROUP BY r.id, r.receipt_no, r.receipt_date, c.name, r.source_no, r.project_code, r.cabinet_no, r.amount, r.payment_method, r.bank_account, r.status
        ORDER BY r.receipt_date DESC NULLS LAST, r.id DESC
        LIMIT 300
        """,
        tuple([config["direction"]] + params),
    )
    return render_template(
        "finance_funds_list.html",
        title=config["list_title"],
        subtitle=config["subtitle"],
        rows=rows,
        columns=[("receipt_no", config["label"]), ("receipt_date", "单据日期"), ("customer_name", "客户"), ("settlement_sources", "核销应收来源"), ("settlement_count", "核销笔数"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("amount", config["amount_label"]), ("settled_amount", "已核销"), ("unapplied_amount", "未分配"), ("status", "状态"), ("next_step", "下一步")],
        new_url=config["new_url"],
        detail_base=config["detail_base"],
        edit_base=config["detail_base"],
        delete_base=config["detail_base"],
        keyword=keyword,
    )


def render_supplier_payment_list(query_rows, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    params = []
    where = ["COALESCE(p.payment_kind,'supplier_payment')=%s"]
    params.append(payment_kind)
    if keyword:
        pattern = f"%{keyword}%"
        where.append("(p.payment_no ILIKE %s OR s.name ILIKE %s OR p.source_no ILIKE %s OR p.project_code ILIKE %s OR p.cabinet_no ILIKE %s OR p.remark ILIKE %s)")
        params.extend([pattern] * 6)
    rows = query_rows(
        f"""
        SELECT p.id, p.payment_no, p.payment_date, s.name AS supplier_name,
               p.source_no, p.project_code, p.cabinet_no, p.amount,
               COALESCE(SUM(ps.applied_amount),0) AS settled_amount,
               GREATEST(COALESCE(p.amount,0)-COALESCE(SUM(ps.applied_amount),0),0) AS unapplied_amount,
               p.payment_method, p.bank_account, p.status,
               CASE WHEN %s='in'
                    THEN '已登记资金流入，复核原单据和对账备注'
                    WHEN COALESCE(p.amount,0) <= COALESCE(SUM(ps.applied_amount),0)
                    THEN '已核销，核对应付余额'
                    ELSE '存在未分配金额，补充核销明细或备注说明' END AS next_step
        FROM supplier_payments p
        LEFT JOIN suppliers s ON s.id=p.supplier_id
        LEFT JOIN supplier_payment_settlements ps ON ps.payment_id=p.id
        WHERE {' AND '.join(where)}
        GROUP BY p.id, p.payment_no, p.payment_date, s.name, p.source_no, p.project_code, p.cabinet_no, p.amount, p.payment_method, p.bank_account, p.status
        ORDER BY p.payment_date DESC NULLS LAST, p.id DESC
        LIMIT 300
        """,
        tuple([config["direction"]] + params),
    )
    return render_template(
        "finance_funds_list.html",
        title=config["list_title"],
        subtitle=config["subtitle"],
        rows=rows,
        columns=[("payment_no", config["label"]), ("payment_date", "单据日期"), ("supplier_name", "供应商"), ("source_no", "来源单"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("amount", config["amount_label"]), ("settled_amount", "已核销"), ("unapplied_amount", "未分配"), ("status", "状态"), ("next_step", "下一步")],
        new_url=config["new_url"],
        detail_base=config["detail_base"],
        edit_base=config["detail_base"],
        delete_base=config["detail_base"],
        keyword=keyword,
    )


def render_customer_receipt_entry(query_rows, doc=None, settlements=None, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    doc = doc or {}
    settlements = settlements or []
    customer_id = str(request.args.get("customer_id") or doc.get("customer_id") or "").strip()
    selected_id = (request.args.get("receivable_id") or "").strip()
    selected_partner_id = customer_id
    if selected_id.isdigit() and not selected_partner_id.isdigit():
        selected_rows = query_rows(
            """
            SELECT customer_id
            FROM customer_receivables
            WHERE id=%s AND COALESCE(balance,0)>0
            LIMIT 1
            """,
            (int(selected_id),),
        )
        if selected_rows:
            selected_partner_id = str(selected_rows[0].get("customer_id") or "")
    has_partner_filter = selected_partner_id.isdigit()
    rows = _open_receivables(query_rows, int(selected_partner_id)) if has_partner_filter and config["settlement_enabled"] else []
    settlement_ids = {row.get("receivable_id") for row in settlements}
    if settlement_ids:
        existing_by_id = {row.get("id"): row for row in rows}
        for settlement in settlements:
            receivable_id = settlement.get("receivable_id")
            if receivable_id in existing_by_id:
                existing_by_id[receivable_id]["balance"] = as_decimal(existing_by_id[receivable_id].get("balance")) + as_decimal(settlement.get("applied_amount"))
            else:
                rows.append(
                    {
                        "id": receivable_id,
                        "source_type": settlement.get("source_type"),
                        "source_no": settlement.get("source_no"),
                        "partner_name": settlement.get("partner_name"),
                        "receivable_date": settlement.get("receivable_date"),
                        "due_date": settlement.get("due_date"),
                        "customer_id": doc.get("customer_id"),
                        "total_amount": settlement.get("total_amount"),
                        "received_amount": settlement.get("received_amount"),
                        "balance": as_decimal(settlement.get("balance")) + as_decimal(settlement.get("applied_amount")),
                        "project_code": settlement.get("project_code"),
                        "cabinet_no": settlement.get("cabinet_no"),
                        "status": settlement.get("status"),
                    }
                )
    if config["partner_source"] == "open_receivables":
        customers = query_rows(
            """
            SELECT DISTINCT c.id, c.name
            FROM customer_receivables cr
            JOIN customers c ON c.id=cr.customer_id
            WHERE COALESCE(cr.balance,0)>0
              AND """ + _partner_test_data_clause("c") + """
            ORDER BY c.name
            """
        )
    else:
        customers = query_rows(
            """
            SELECT id, name
            FROM customers c
            WHERE """ + _partner_test_data_clause("c") + """
            ORDER BY name
            LIMIT 500
            """
        )
    return render_template(
        "finance_funds_form.html",
        title=config["edit_title"] if doc else config["entry_title"],
        list_url=config["list_url"],
        post_url=f"{config['detail_base']}/{doc.get('id')}/edit" if doc else config["new_url"],
        partner_label="客户",
        partner_field="customer_id",
        date_field="receipt_date",
        amount_label=config["amount_label"],
        method_label=config["method_label"],
        methods=_receipt_payment_methods(),
        partners=customers,
        selected_partner_id=selected_partner_id,
        doc=doc,
        has_partner_filter=has_partner_filter,
        empty_message="请先选择客户；系统只显示该客户的未清应收明细。" if config["settlement_enabled"] else "该单据不做应收核销，请在备注中说明业务来源。",
        source_rows=rows,
        selected_ids=settlement_ids or ({int(selected_id)} if selected_id.isdigit() else set()),
        settlement_values={row.get("receivable_id"): row.get("applied_amount") for row in settlements},
        source_columns=[("source_type", "来源类型"), ("source_no", "来源单"), ("partner_name", "客户"), ("receivable_date", "应收日期"), ("due_date", "到期日"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("total_amount", "应收金额"), ("received_amount", "已收"), ("balance", "未收余额"), ("status", "状态")],
        funds_kind="receipt",
        document_label=config["label"],
        new_document_label=config["new_label"],
        line_section_title=config["line_section_title"],
        line_amount_label=config["line_amount_label"],
        line_account_label=config["line_account_label"],
        line_remark_label=config["line_remark_label"],
        settlement_enabled=config["settlement_enabled"],
    )


def render_supplier_payment_entry(query_rows, doc=None, settlements=None, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    doc = doc or {}
    settlements = settlements or []
    supplier_id = str(request.args.get("supplier_id") or doc.get("supplier_id") or "").strip()
    selected_id = (request.args.get("payable_id") or "").strip()
    selected_partner_id = supplier_id
    if selected_id.isdigit() and not selected_partner_id.isdigit():
        selected_rows = query_rows(
            """
            SELECT supplier_id
            FROM supplier_payables
            WHERE id=%s AND COALESCE(balance,0)>0
            LIMIT 1
            """,
            (int(selected_id),),
        )
        if selected_rows:
            selected_partner_id = str(selected_rows[0].get("supplier_id") or "")
    has_partner_filter = selected_partner_id.isdigit()
    rows = _open_payables(query_rows, int(selected_partner_id)) if has_partner_filter and config["settlement_enabled"] else []
    settlement_ids = {row.get("payable_id") for row in settlements}
    if settlement_ids:
        existing_by_id = {row.get("id"): row for row in rows}
        for settlement in settlements:
            payable_id = settlement.get("payable_id")
            if payable_id in existing_by_id:
                existing_by_id[payable_id]["balance"] = as_decimal(existing_by_id[payable_id].get("balance")) + as_decimal(settlement.get("applied_amount"))
            else:
                rows.append(
                    {
                        "id": payable_id,
                        "doc_no": settlement.get("doc_no"),
                        "partner_name": settlement.get("partner_name"),
                        "doc_date": settlement.get("doc_date"),
                        "supplier_id": doc.get("supplier_id"),
                        "amount": settlement.get("amount"),
                        "paid_amount": settlement.get("paid_amount"),
                        "balance": as_decimal(settlement.get("balance")) + as_decimal(settlement.get("applied_amount")),
                        "project_code": settlement.get("project_code"),
                        "cabinet_no": settlement.get("cabinet_no"),
                        "status": settlement.get("status"),
                    }
                )
    if config["partner_source"] == "open_payables":
        suppliers = query_rows(
            """
            SELECT DISTINCT s.id, s.name
            FROM supplier_payables sp
            JOIN suppliers s ON s.id=sp.supplier_id
            WHERE COALESCE(sp.balance,0)>0
              AND """ + _partner_test_data_clause("s") + """
            ORDER BY s.name
            """
        )
    else:
        suppliers = query_rows(
            """
            SELECT id, name
            FROM suppliers s
            WHERE """ + _partner_test_data_clause("s") + """
            ORDER BY name
            LIMIT 500
            """
        )
    return render_template(
        "finance_funds_form.html",
        title=config["edit_title"] if doc else config["entry_title"],
        list_url=config["list_url"],
        post_url=f"{config['detail_base']}/{doc.get('id')}/edit" if doc else config["new_url"],
        partner_label="供应商",
        partner_field="supplier_id",
        date_field="payment_date",
        amount_label=config["amount_label"],
        method_label=config["method_label"],
        methods=_receipt_payment_methods(),
        partners=suppliers,
        selected_partner_id=selected_partner_id,
        doc=doc,
        has_partner_filter=has_partner_filter,
        empty_message="请先选择供应商；系统只显示该供应商的未清应付明细。" if config["settlement_enabled"] else "该单据不做应付核销，请在备注中说明业务来源。",
        source_rows=rows,
        selected_ids=settlement_ids or ({int(selected_id)} if selected_id.isdigit() else set()),
        settlement_values={row.get("payable_id"): row.get("applied_amount") for row in settlements},
        source_columns=[("payable_no", "应付单号"), ("doc_no", "来源单"), ("partner_name", "供应商"), ("doc_date", "应付日期"), ("amount", "应付金额"), ("paid_amount", "已付"), ("balance", "未付余额"), ("status", "状态")],
        funds_kind="payment",
        document_label=config["label"],
        new_document_label=config["new_label"],
        line_section_title=config["line_section_title"],
        line_amount_label=config["line_amount_label"],
        line_account_label=config["line_account_label"],
        line_remark_label=config["line_remark_label"],
        settlement_enabled=config["settlement_enabled"],
    )


def _insert_receipt_or_payment_settlements(source_rows, amount):
    applied_by_id = {row["id"]: min(_posted_settlement_amount(row["id"]), as_decimal(row.get("balance"))) for row in source_rows}
    if not any(value > 0 for value in applied_by_id.values()):
        remaining = amount
        for row in source_rows:
            if remaining <= 0:
                break
            applied = min(remaining, as_decimal(row.get("balance")))
            applied_by_id[row["id"]] = applied
            remaining -= applied
    return applied_by_id


def _posted_customer_receipt_settlements(source_rows):
    applied_by_id = {}
    errors = []
    for row in source_rows:
        row_id = row.get("id")
        applied = _posted_settlement_amount(row_id)
        balance = as_decimal(row.get("balance"))
        if applied < 0:
            errors.append(f"{row.get('source_no') or row_id} 本次核销不能小于 0。")
            applied = Decimal("0")
        if applied > balance:
            errors.append(f"{row.get('source_no') or row_id} 本次核销不能超过未收余额 {balance}。")
            applied = balance
        applied_by_id[row_id] = applied
    return applied_by_id, errors


def _posted_funds_lines(line_label="收款明细"):
    line_numbers = set()
    for key in request.form:
        if key.startswith("receipt_line_amount_"):
            try:
                line_numbers.add(int(key.rsplit("_", 1)[-1]))
            except ValueError:
                continue
    if not line_numbers:
        line_numbers = {1}
    lines = []
    errors = []
    for idx in sorted(line_numbers):
        amount = _form_decimal(f"receipt_line_amount_{idx}")
        fee_amount = _form_decimal(f"receipt_line_fee_{idx}")
        payment_method = (request.form.get(f"receipt_line_method_{idx}") or request.form.get("payment_method") or "银行转账").strip()
        bank_account = (request.form.get(f"receipt_line_account_{idx}") or request.form.get("bank_account") or "").strip()
        transaction_no = (request.form.get(f"receipt_line_transaction_{idx}") or "").strip()
        remark = (request.form.get(f"receipt_line_remark_{idx}") or "").strip()
        if amount <= 0 and not any([bank_account, transaction_no, remark]):
            continue
        if amount <= 0:
            errors.append(f"{line_label}第 {idx} 行金额必须大于 0。")
            continue
        if fee_amount < 0:
            errors.append(f"{line_label}第 {idx} 行手续费不能小于 0。")
            fee_amount = Decimal("0")
        lines.append(
            {
                "line_no": len(lines) + 1,
                "payment_method": payment_method,
                "bank_account": bank_account,
                "amount": amount,
                "fee_amount": fee_amount,
                "transaction_no": transaction_no,
                "remark": remark,
            }
        )
    return lines, sum((line["amount"] for line in lines), Decimal("0")), errors


def _posted_customer_receipt_lines():
    return _posted_funds_lines("收款明细")


def _posted_supplier_payment_lines():
    return _posted_funds_lines("付款明细")


def _is_final_funds_status(status):
    return (status or "") in {"已作废", "已反核销", "void", "voided", "cancelled"}


def _is_draft_funds_status(status):
    return (status or "") in {"draft", "草稿", "新建", "未确认"}


def _funds_action_flags(doc):
    status = (doc or {}).get("status") or ""
    settled_amount = as_decimal((doc or {}).get("settled_amount"))
    return {
        "can_edit": _is_draft_funds_status(status) and settled_amount <= 0,
        "can_delete": _is_draft_funds_status(status) and settled_amount <= 0,
        "can_reverse_settlement": settled_amount > 0 and not _is_final_funds_status(status),
        "can_void": status not in {"已作废", "void", "voided", "cancelled"},
    }


def _recalculate_customer_receivable_from_settlements(receivable_id, execute_db):
    execute_db(
        """
        WITH settlement AS (
            SELECT s.receivable_id, SUM(COALESCE(s.applied_amount,0)) AS settled_amount
            FROM customer_receipt_settlements s
            JOIN customer_receipts r ON r.id=s.receipt_id
            WHERE s.receivable_id=%s
              AND COALESCE(r.status,'') NOT IN ('已作废','已反核销','void','voided','cancelled')
            GROUP BY s.receivable_id
        )
        UPDATE customer_receivables cr
        SET received_amount=COALESCE(settlement.settled_amount,0),
            balance=GREATEST(COALESCE(cr.total_amount,0)-COALESCE(settlement.settled_amount,0),0),
            status=CASE
                WHEN COALESCE(settlement.settled_amount,0) <= 0 THEN '未收款'
                WHEN GREATEST(COALESCE(cr.total_amount,0)-COALESCE(settlement.settled_amount,0),0) <= 0 THEN '已收款'
                ELSE '部分收款'
            END
        FROM (SELECT %s::INTEGER AS receivable_id) target
        LEFT JOIN settlement ON settlement.receivable_id=target.receivable_id
        WHERE cr.id=target.receivable_id
        """,
        (receivable_id, receivable_id),
    )


def _rollback_customer_receipt_settlements(receipt_id, query_rows, execute_db):
    settlement_rows = query_rows(
        """
        SELECT DISTINCT receivable_id
        FROM customer_receipt_settlements
        WHERE receipt_id=%s
        """,
        (receipt_id,),
    )
    execute_db("DELETE FROM customer_receipt_settlements WHERE receipt_id=%s", (receipt_id,))
    for row in settlement_rows:
        _recalculate_customer_receivable_from_settlements(row.get("receivable_id"), execute_db)


def _rollback_supplier_payment_settlements(payment_id, execute_db):
    execute_db(
        """
        WITH rollback AS (
            SELECT payable_id, SUM(COALESCE(applied_amount,0)) AS rollback_amount
            FROM supplier_payment_settlements
            WHERE payment_id=%s
            GROUP BY payable_id
        ),
        recalculated AS (
            SELECT sp.id,
                   GREATEST(COALESCE(sp.paid_amount,0)-rollback.rollback_amount,0) AS new_paid,
                   COALESCE(sp.amount,0) AS total_amount
            FROM supplier_payables sp
            JOIN rollback ON rollback.payable_id=sp.id
        )
        UPDATE supplier_payables sp
        SET paid_amount=recalculated.new_paid,
            balance=GREATEST(recalculated.total_amount-recalculated.new_paid,0),
            status=CASE
                WHEN recalculated.new_paid <= 0 THEN '未付款'
                WHEN GREATEST(recalculated.total_amount-recalculated.new_paid,0) <= 0 THEN '已付款'
                ELSE '部分付款'
            END
        FROM recalculated
        WHERE sp.id=recalculated.id
        """,
        (payment_id,),
    )
    execute_db("DELETE FROM supplier_payment_settlements WHERE payment_id=%s", (payment_id,))


def post_customer_receipt_reverse_settlement(receipt_id, query_one, query_rows, execute_db, log_action, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    doc = query_one(
        """
        SELECT r.id, r.receipt_no, r.status, COALESCE(SUM(s.applied_amount),0) AS settled_amount
        FROM customer_receipts r
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        WHERE r.id=%s AND COALESCE(r.receipt_kind,'customer_receipt')=%s
        GROUP BY r.id
        """,
        (receipt_id, receipt_kind),
    )
    if not doc:
        flash(f"{config['label']}不存在。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_reverse_settlement"]:
        flash(f"当前{config['label']}不能反核销或已处理。", "warning")
        return redirect(f"{config['detail_base']}/{receipt_id}")
    rollback_amount = as_decimal(doc.get("settled_amount"))
    receipt_amount_row = query_one("SELECT amount FROM customer_receipts WHERE id=%s", (receipt_id,)) or {}
    receipt_amount = as_decimal(receipt_amount_row.get("amount"))
    _rollback_customer_receipt_settlements(receipt_id, query_rows, execute_db)
    execute_db("UPDATE customer_receipts SET status='已反核销', settled_amount=0, unapplied_amount=%s WHERE id=%s", (receipt_amount, receipt_id))
    _mark_cash_bank_journal_status(execute_db, "customer_receipt", doc.get("receipt_no"), "reversed", f"；{config['label']}已反核销")
    log_action(f"{config['label']}反核销", doc.get("receipt_no"), f"回滚应收核销 {rollback_amount}")
    flash(f"{config['label']} {doc.get('receipt_no')} 已反核销，回滚应收 {rollback_amount}。", "success")
    return redirect(f"{config['detail_base']}/{receipt_id}")


def post_customer_receipt_void(receipt_id, query_one, query_rows, execute_db, log_action, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    doc = query_one(
        """
        SELECT r.id, r.receipt_no, r.status, COALESCE(SUM(s.applied_amount),0) AS settled_amount
        FROM customer_receipts r
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        WHERE r.id=%s AND COALESCE(r.receipt_kind,'customer_receipt')=%s
        GROUP BY r.id
        """,
        (receipt_id, receipt_kind),
    )
    if not doc:
        flash(f"{config['label']}不存在。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_void"]:
        flash(f"{config['label']}已作废，不能重复作废。", "warning")
        return redirect(f"{config['detail_base']}/{receipt_id}")
    rollback_amount = as_decimal(doc.get("settled_amount"))
    if rollback_amount > 0:
        _rollback_customer_receipt_settlements(receipt_id, query_rows, execute_db)
    execute_db("UPDATE customer_receipts SET status='已作废' WHERE id=%s", (receipt_id,))
    _mark_cash_bank_journal_status(execute_db, "customer_receipt", doc.get("receipt_no"), "voided", f"；{config['label']}已作废")
    log_action(f"作废{config['label']}", doc.get("receipt_no"), f"作废{config['label']}，回滚应收核销 {rollback_amount}")
    flash(f"{config['label']} {doc.get('receipt_no')} 已作废，回滚应收 {rollback_amount}。", "success")
    return redirect(f"{config['detail_base']}/{receipt_id}")


def post_supplier_payment_reverse_settlement(payment_id, query_one, execute_db, log_action, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    doc = query_one(
        """
        SELECT p.id, p.payment_no, p.status, COALESCE(SUM(ps.applied_amount),0) AS settled_amount
        FROM supplier_payments p
        LEFT JOIN supplier_payment_settlements ps ON ps.payment_id=p.id
        WHERE p.id=%s AND COALESCE(p.payment_kind,'supplier_payment')=%s
        GROUP BY p.id
        """,
        (payment_id, payment_kind),
    )
    if not doc:
        flash(f"{config['label']}不存在。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_reverse_settlement"]:
        flash(f"当前{config['label']}不能反核销或已处理。", "warning")
        return redirect(f"{config['detail_base']}/{payment_id}")
    rollback_amount = as_decimal(doc.get("settled_amount"))
    payment_amount_row = query_one("SELECT amount FROM supplier_payments WHERE id=%s", (payment_id,)) or {}
    payment_amount = as_decimal(payment_amount_row.get("amount"))
    _rollback_supplier_payment_settlements(payment_id, execute_db)
    execute_db("UPDATE supplier_payments SET status='已反核销', settled_amount=0, unapplied_amount=%s WHERE id=%s", (payment_amount, payment_id))
    _mark_cash_bank_journal_status(execute_db, config["source_type"], doc.get("payment_no"), "reversed", f"；{config['label']}已反核销")
    log_action(f"{config['label']}反核销", doc.get("payment_no"), f"回滚应付核销 {rollback_amount}")
    flash(f"{config['label']} {doc.get('payment_no')} 已反核销，回滚应付 {rollback_amount}。", "success")
    return redirect(f"{config['detail_base']}/{payment_id}")


def post_supplier_payment_void(payment_id, query_one, execute_db, log_action, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    doc = query_one(
        """
        SELECT p.id, p.payment_no, p.status, COALESCE(SUM(ps.applied_amount),0) AS settled_amount
        FROM supplier_payments p
        LEFT JOIN supplier_payment_settlements ps ON ps.payment_id=p.id
        WHERE p.id=%s AND COALESCE(p.payment_kind,'supplier_payment')=%s
        GROUP BY p.id
        """,
        (payment_id, payment_kind),
    )
    if not doc:
        flash(f"{config['label']}不存在。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_void"]:
        flash(f"{config['label']}已作废，不能重复作废。", "warning")
        return redirect(f"{config['detail_base']}/{payment_id}")
    rollback_amount = as_decimal(doc.get("settled_amount"))
    if rollback_amount > 0:
        _rollback_supplier_payment_settlements(payment_id, execute_db)
    execute_db("UPDATE supplier_payments SET status='已作废' WHERE id=%s", (payment_id,))
    _mark_cash_bank_journal_status(execute_db, config["source_type"], doc.get("payment_no"), "voided", f"；{config['label']}已作废")
    log_action(f"作废{config['label']}", doc.get("payment_no"), f"作废{config['label']}，回滚应付核销 {rollback_amount}")
    flash(f"{config['label']} {doc.get('payment_no')} 已作废，回滚应付 {rollback_amount}。", "success")
    return redirect(f"{config['detail_base']}/{payment_id}")


def post_customer_receipt(query_one, query_rows, execute_db, execute_and_return, next_doc_no, log_action, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    customer_id = (request.form.get("customer_id") or "").strip()
    amount = _form_decimal("amount")
    receipt_lines, line_total, line_errors = _posted_customer_receipt_lines()
    if not customer_id.isdigit() or amount <= 0:
        flash(f"请选择客户并输入大于 0 的{config['amount_label']}。", "warning")
        return redirect(config["new_url"])
    if line_errors:
        for error in line_errors:
            flash(error, "warning")
        return redirect(f"{config['new_url']}?customer_id={customer_id}")
    if not receipt_lines:
        flash(f"请至少填写一行{config['line_section_title']}。", "warning")
        return redirect(f"{config['new_url']}?customer_id={customer_id}")
    if abs(line_total - amount) > Decimal("0.005"):
        flash(f"{config['line_section_title']}合计 {line_total} 必须等于{config['amount_label']} {amount}。", "warning")
        return redirect(f"{config['new_url']}?customer_id={customer_id}")
    validation_response = _cash_bank_accounts_validation_response(query_one, receipt_lines, f"{config['new_url']}?customer_id={customer_id}")
    if validation_response:
        return validation_response
    source_rows = _open_receivables(query_rows, int(customer_id)) if config["settlement_enabled"] else []
    applied_by_id, errors = _posted_customer_receipt_settlements(source_rows) if config["settlement_enabled"] else ({}, [])
    total_applied = sum(applied_by_id.values(), Decimal("0"))
    if total_applied > amount:
        errors.append(f"本次核销合计 {total_applied} 不能超过{config['amount_label']} {amount}。")
    if config["settlement_required"] and total_applied <= 0:
        errors.append("该单据必须选择至少一笔应收来源并填写本次核销。")
    if errors:
        for error in errors:
            flash(error, "warning")
        return redirect(f"{config['new_url']}?customer_id={customer_id}")
    first_source = next((row for row in source_rows if applied_by_id.get(row["id"], Decimal("0")) > 0), {})
    form_project_code = (request.form.get("project_code") or "").strip()
    form_cabinet_no = (request.form.get("cabinet_no") or "").strip()
    receipt_project_code = first_source.get("project_code") or form_project_code
    receipt_cabinet_no = first_source.get("cabinet_no") or form_cabinet_no
    receipt_no = next_doc_no(config["prefix"], "customer_receipts", "receipt_no")
    receipt = execute_and_return(
        """
        INSERT INTO customer_receipts
            (receipt_no, receipt_date, customer_id, amount, payment_method, bank_account,
             remark, created_by, source_type, source_id, source_no, receivable_id,
             cost_object_id, project_code, cabinet_no, status, receipt_kind, fund_direction)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'已确认',%s,%s)
        RETURNING id, receipt_no
        """,
        (receipt_no, request.form.get("receipt_date") or date.today().isoformat(), int(customer_id), amount, receipt_lines[0].get("payment_method"), receipt_lines[0].get("bank_account"), (request.form.get("remark") or "").strip(), session.get("user_id"), first_source.get("source_type") or config["source_type"], first_source.get("source_id"), first_source.get("source_no"), first_source.get("id"), first_source.get("cost_object_id"), receipt_project_code, receipt_cabinet_no, receipt_kind, config["direction"]),
    )
    receipt_id = returned_id(receipt)
    for line in receipt_lines:
        execute_db(
            """
            INSERT INTO customer_receipt_lines
                (receipt_id, line_no, payment_method, bank_account, amount, fee_amount, transaction_no, remark)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                receipt_id,
                line.get("line_no"),
                line.get("payment_method"),
                line.get("bank_account"),
                line.get("amount"),
                line.get("fee_amount"),
                line.get("transaction_no"),
                line.get("remark"),
            ),
        )
    for row in source_rows:
        applied = applied_by_id.get(row["id"], Decimal("0"))
        if applied <= 0:
            continue
        execute_db("INSERT INTO customer_receipt_settlements (receipt_id, receivable_id, applied_amount) VALUES (%s,%s,%s) ON CONFLICT (receipt_id, receivable_id) DO UPDATE SET applied_amount=EXCLUDED.applied_amount", (receipt_id, row["id"], applied))
        _recalculate_customer_receivable_from_settlements(row["id"], execute_db)
    partner_name = first_source.get("partner_name")
    if not partner_name:
        partner = query_one("SELECT name FROM customers WHERE id=%s", (int(customer_id),))
        partner_name = (partner or {}).get("name")
    _upsert_cash_bank_journal_for_funds_lines(
        query_one,
        execute_db,
        source_type="customer_receipt",
        source_id=receipt_id,
        source_no=receipt_no,
        doc_date=request.form.get("receipt_date") or date.today().isoformat(),
        direction=config["direction"],
        fund_lines=receipt_lines,
        partner_type="客户",
        partner_name=partner_name,
        project_code=receipt_project_code,
        cabinet_no=receipt_cabinet_no,
        summary=f"{config['cash_summary']} {receipt_no}，核销 {total_applied}",
        created_by=session.get("user_id"),
    )
    log_action(config["action_name"], receipt_no, f"{config['amount_label']} {amount}，核销 {total_applied}")
    unapplied_amount = max(amount - total_applied, Decimal("0"))
    flash(f"{config['flash_noun']} {receipt_no} 已确认，已核销 {total_applied}，未分配 {unapplied_amount}，已登记现金银行流水。", "success")
    execute_db("UPDATE customer_receipts SET settled_amount=%s, unapplied_amount=%s WHERE id=%s", (total_applied, unapplied_amount, receipt_id))
    if (request.form.get("save_action") or "").strip() == "save_new":
        return redirect(config["new_url"])
    return redirect(f"{config['detail_base']}/{receipt_id}")


def post_supplier_payment(query_one, query_rows, execute_db, execute_and_return, next_doc_no, log_action, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    supplier_id = (request.form.get("supplier_id") or "").strip()
    amount = _form_decimal("amount")
    if not supplier_id.isdigit() or amount <= 0:
        flash("Please select a supplier and enter a payment amount greater than 0.", "warning")
        return redirect(config["new_url"])
    payment_lines, line_total, line_errors = _posted_supplier_payment_lines()
    if line_errors:
        for error in line_errors:
            flash(error, "warning")
        return render_supplier_payment_entry(query_rows, payment_kind=payment_kind)
    if payment_lines and line_total != amount:
        flash(f"Funds line total {line_total} must equal payment amount {amount}.", "warning")
        return render_supplier_payment_entry(query_rows, payment_kind=payment_kind)

    payment_method = (request.form.get("payment_method") or "bank").strip()
    bank_account = (request.form.get("bank_account") or "").strip()
    if not payment_lines:
        payment_lines = [
            {
                "line_no": 1,
                "payment_method": payment_method,
                "bank_account": bank_account,
                "amount": amount,
                "fee_amount": Decimal("0"),
                "transaction_no": "",
                "remark": "",
            }
        ]
    validation_response = _cash_bank_accounts_validation_response(query_one, payment_lines, config["new_url"])
    if validation_response:
        return validation_response

    source_rows = _open_payables(query_rows, int(supplier_id)) if config["settlement_enabled"] else []
    applied_by_id = _insert_receipt_or_payment_settlements(source_rows, amount) if config["settlement_enabled"] else {}
    first_source = next((row for row in source_rows if applied_by_id.get(row["id"], Decimal("0")) > 0), source_rows[0] if source_rows else {})
    form_project_code = (request.form.get("project_code") or "").strip()
    form_cabinet_no = (request.form.get("cabinet_no") or "").strip()
    payment_project_code = first_source.get("project_code") or form_project_code
    payment_cabinet_no = first_source.get("cabinet_no") or form_cabinet_no
    supplier = query_one("SELECT name FROM suppliers WHERE id=%s", (int(supplier_id),)) or {}
    payment_no = next_doc_no(config["prefix"], "supplier_payments", "payment_no")
    doc_date = request.form.get("payment_date") or date.today().isoformat()
    payment = execute_and_return(
        """
        INSERT INTO supplier_payments
            (payment_no, payment_date, supplier_id, amount, payment_method, bank_account,
             operator_id, created_by, remark, source_type, source_id, source_no, payable_id,
             payment_kind, fund_direction, status, unapplied_amount)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s)
        RETURNING id, payment_no
        """,
        (payment_no, doc_date, int(supplier_id), amount, payment_method, payment_lines[0].get("bank_account"), session.get("user_id"), session.get("user_id"), (request.form.get("remark") or "").strip(), first_source.get("doc_type") or config["source_type"], first_source.get("doc_id"), first_source.get("doc_no"), first_source.get("id"), payment_kind, config["direction"], amount),
    )
    payment_id = returned_id(payment)
    for line in payment_lines:
        execute_db(
            """
            INSERT INTO supplier_payment_lines
                (payment_id, line_no, payment_method, bank_account, amount, fee_amount, transaction_no, remark)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (payment_id, line["line_no"], line["payment_method"], line["bank_account"], line["amount"], line["fee_amount"], line["transaction_no"], line["remark"]),
        )
    total_applied = Decimal("0")
    for row in source_rows:
        applied = applied_by_id.get(row["id"], Decimal("0"))
        if applied <= 0:
            continue
        execute_db("INSERT INTO supplier_payment_settlements (payment_id, payable_id, applied_amount) VALUES (%s,%s,%s) ON CONFLICT (payment_id, payable_id) DO UPDATE SET applied_amount=EXCLUDED.applied_amount", (payment_id, row["id"], applied))
        new_balance = max(as_decimal(row.get("balance")) - applied, Decimal("0"))
        status = "paid" if new_balance <= 0 else "partial_paid"
        execute_db("UPDATE supplier_payables SET paid_amount=COALESCE(paid_amount,0)+%s, balance=GREATEST(COALESCE(balance,0)-%s,0), status=%s WHERE id=%s", (applied, applied, status, row["id"]))
        total_applied += applied
    partner_name = first_source.get("partner_name") or supplier.get("name")
    _upsert_cash_bank_journal_for_funds_lines(
        query_one,
        execute_db,
        source_type=config["source_type"],
        source_id=payment_id,
        source_no=payment_no,
        doc_date=doc_date,
        direction=config["direction"],
        fund_lines=payment_lines,
        partner_type="supplier",
        partner_name=partner_name,
        project_code=payment_project_code,
        cabinet_no=payment_cabinet_no,
        summary=f"{config['cash_summary']} {payment_no}, settled {total_applied}",
        created_by=session.get("user_id"),
    )
    log_action(config["action_name"], payment_no, f"{config['amount_label']} {amount}, settled {total_applied}")
    flash(f"{config['label']} {payment_no} saved and cash/bank journal registered.", "success")
    execute_db(
        """
        UPDATE supplier_payments
        SET cost_object_id=%s, project_code=%s, cabinet_no=%s, settled_amount=%s, unapplied_amount=%s
        WHERE id=%s
        """,
        (
            first_source.get("cost_object_id"),
            payment_project_code,
            payment_cabinet_no,
            total_applied,
            max(amount - total_applied, Decimal("0")),
            payment_id,
        ),
    )
    return redirect(f"{config['detail_base']}/{payment_id}")

def _customer_receipt_edit_context(receipt_id, query_one, query_rows, receipt_kind=None):
    where_kind = "AND COALESCE(r.receipt_kind,'customer_receipt')=%s" if receipt_kind else ""
    params = (receipt_id, receipt_kind) if receipt_kind else (receipt_id,)
    doc = query_one(
        f"""
        SELECT r.*, COALESCE(SUM(s.applied_amount),0) AS settled_amount
        FROM customer_receipts r
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        WHERE r.id=%s
          {where_kind}
        GROUP BY r.id
        """,
        params,
    )
    if not doc:
        return None, []
    settlements = query_rows(
        """
        SELECT s.receivable_id, s.applied_amount, cr.source_type, cr.source_no, c.name AS partner_name,
               cr.receivable_date, cr.due_date, cr.total_amount, cr.received_amount,
               cr.balance, cr.project_code, cr.cabinet_no, cr.status
        FROM customer_receipt_settlements s
        JOIN customer_receivables cr ON cr.id=s.receivable_id
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE s.receipt_id=%s
        ORDER BY s.id
        """,
        (receipt_id,),
    )
    return doc, settlements


def _supplier_payment_edit_context(payment_id, query_one, query_rows, payment_kind=None):
    where_kind = "AND COALESCE(p.payment_kind,'supplier_payment')=%s" if payment_kind else ""
    params = (payment_id, payment_kind) if payment_kind else (payment_id,)
    doc = query_one(
        f"""
        SELECT p.*, COALESCE(SUM(s.applied_amount),0) AS settled_amount
        FROM supplier_payments p
        LEFT JOIN supplier_payment_settlements s ON s.payment_id=p.id
        WHERE p.id=%s
          {where_kind}
        GROUP BY p.id
        """,
        params,
    )
    if not doc:
        return None, []
    settlements = query_rows(
        """
        SELECT s.payable_id, s.applied_amount, sp.doc_no, sup.name AS partner_name,
               sp.doc_date, sp.amount, sp.paid_amount, sp.balance,
               sp.project_code, sp.cabinet_no, sp.status
        FROM supplier_payment_settlements s
        JOIN supplier_payables sp ON sp.id=s.payable_id
        LEFT JOIN suppliers sup ON sup.id=sp.supplier_id
        WHERE s.payment_id=%s
        ORDER BY s.id
        """,
        (payment_id,),
    )
    return doc, settlements


def post_customer_receipt_edit(receipt_id, query_one, query_rows, execute_db, log_action, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    doc, settlements = _customer_receipt_edit_context(receipt_id, query_one, query_rows, receipt_kind)
    if not doc:
        flash(f"{config['label']}不存在。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_edit"]:
        flash(f"只有未核销的草稿{config['label']}可以编辑；已确认、已核销、已作废单据请走反核销或作废流程。", "warning")
        return redirect(f"{config['detail_base']}/{receipt_id}")
    customer_id = (request.form.get("customer_id") or "").strip()
    amount = _form_decimal("amount")
    if not customer_id.isdigit() or amount <= 0:
        flash(f"请选择客户并输入大于 0 的{config['amount_label']}。", "warning")
        return render_customer_receipt_entry(query_rows, doc=doc, settlements=settlements, receipt_kind=receipt_kind)
    execute_db(
        """
        UPDATE customer_receipts
        SET receipt_date=%s, customer_id=%s, amount=%s, payment_method=%s,
            bank_account=%s, remark=%s
        WHERE id=%s
        """,
        (
            request.form.get("receipt_date") or date.today().isoformat(),
            int(customer_id),
            amount,
            (request.form.get("payment_method") or "").strip(),
            (request.form.get("bank_account") or "").strip(),
            (request.form.get("remark") or "").strip(),
            receipt_id,
        ),
    )
    # C-4: 同步重建资金明细子表 customer_receipt_lines
    funds_lines, line_total, line_errors = _posted_funds_lines()
    if line_errors:
        flash(f"资金明细行错误：{'; '.join(line_errors)}", "danger")
        return render_customer_receipt_entry(query_rows, doc=doc, settlements=settlements, receipt_kind=receipt_kind)
    execute_db("DELETE FROM customer_receipt_lines WHERE receipt_id=%s", (receipt_id,))
    if funds_lines:
        for idx, line in enumerate(funds_lines, start=1):
            execute_db(
                """
                INSERT INTO customer_receipt_lines
                    (receipt_id, line_no, payment_method, bank_account, amount,
                     fee_amount, transaction_no, remark)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    receipt_id,
                    line.get("line_no") or idx,
                    line.get("payment_method") or "",
                    line.get("bank_account") or "",
                    line.get("amount") or 0,
                    line.get("fee_amount") or 0,
                    line.get("transaction_no") or "",
                    line.get("remark") or "",
                ),
            )
        # 若行明细总额与主表金额不一致，以行明细总额为准更新主表
        if line_total > 0 and line_total != amount:
            execute_db("UPDATE customer_receipts SET amount=%s WHERE id=%s", (line_total, receipt_id))
            amount = line_total
    log_action(f"编辑{config['label']}", doc.get("receipt_no"), f"草稿{config['label']}金额更新为 {amount}")
    flash(f"{config['label']}草稿已保存。", "success")
    return redirect(f"{config['detail_base']}/{receipt_id}")


def post_supplier_payment_edit(payment_id, query_one, query_rows, execute_db, log_action, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    doc, settlements = _supplier_payment_edit_context(payment_id, query_one, query_rows, payment_kind)
    if not doc:
        flash(f"{config['label']}不存在。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_edit"]:
        flash(f"只有未核销的草稿{config['label']}可以编辑；已确认、已核销、已作废单据请走反核销或作废流程。", "warning")
        return redirect(f"{config['detail_base']}/{payment_id}")
    supplier_id = (request.form.get("supplier_id") or "").strip()
    amount = _form_decimal("amount")
    if not supplier_id.isdigit() or amount <= 0:
        flash(f"请选择供应商并输入大于 0 的{config['amount_label']}。", "warning")
        return render_supplier_payment_entry(query_rows, doc=doc, settlements=settlements, payment_kind=payment_kind)
    execute_db(
        """
        UPDATE supplier_payments
        SET payment_date=%s, supplier_id=%s, amount=%s, payment_method=%s,
            bank_account=%s, remark=%s
        WHERE id=%s
        """,
        (
            request.form.get("payment_date") or date.today().isoformat(),
            int(supplier_id),
            amount,
            (request.form.get("payment_method") or "").strip(),
            (request.form.get("bank_account") or "").strip(),
            (request.form.get("remark") or "").strip(),
            payment_id,
        ),
    )
    # C-4: 同步重建资金明细子表 supplier_payment_lines
    funds_lines, line_total, line_errors = _posted_funds_lines()
    if line_errors:
        flash(f"资金明细行错误：{'; '.join(line_errors)}", "danger")
        return render_supplier_payment_entry(query_rows, doc=doc, settlements=settlements, payment_kind=payment_kind)
    execute_db("DELETE FROM supplier_payment_lines WHERE payment_id=%s", (payment_id,))
    if funds_lines:
        for idx, line in enumerate(funds_lines, start=1):
            execute_db(
                """
                INSERT INTO supplier_payment_lines
                    (payment_id, line_no, payment_method, bank_account, amount,
                     fee_amount, transaction_no, remark)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    payment_id,
                    line.get("line_no") or idx,
                    line.get("payment_method") or "",
                    line.get("bank_account") or "",
                    line.get("amount") or 0,
                    line.get("fee_amount") or 0,
                    line.get("transaction_no") or "",
                    line.get("remark") or "",
                ),
            )
        if line_total > 0 and line_total != amount:
            execute_db("UPDATE supplier_payments SET amount=%s WHERE id=%s", (line_total, payment_id))
            amount = line_total
    log_action(f"编辑{config['label']}", doc.get("payment_no"), f"草稿{config['label']}金额更新为 {amount}")
    flash(f"{config['label']}草稿已保存。", "success")
    return redirect(f"{config['detail_base']}/{payment_id}")


def post_customer_receipt_delete(receipt_id, query_one, execute_db, log_action, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    doc = query_one(
        """
        SELECT r.id, r.receipt_no, r.status, COALESCE(SUM(s.applied_amount),0) AS settled_amount
        FROM customer_receipts r
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        WHERE r.id=%s AND COALESCE(r.receipt_kind,'customer_receipt')=%s
        GROUP BY r.id
        """,
        (receipt_id, receipt_kind),
    )
    if not doc:
        flash(f"{config['label']}不存在或已删除。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_delete"]:
        flash(f"财务单据不允许硬删除：只有未核销的草稿{config['label']}可删除；已确认或已核销请使用作废/反核销。", "warning")
        return redirect(f"{config['detail_base']}/{receipt_id}")
    execute_db("DELETE FROM cash_bank_journal_entries WHERE source_type=%s AND source_no=%s", ("customer_receipt", doc.get("receipt_no")))
    execute_db("DELETE FROM customer_receipt_settlements WHERE receipt_id=%s", (receipt_id,))
    execute_db("DELETE FROM customer_receipts WHERE id=%s", (receipt_id,))
    log_action(f"删除{config['label']}草稿", doc.get("receipt_no"), f"id={receipt_id}")
    flash(f"{config['label']}草稿已删除。", "success")
    return redirect(config["list_url"])


def post_supplier_payment_delete(payment_id, query_one, execute_db, log_action, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    doc = query_one(
        """
        SELECT p.id, p.payment_no, p.status, COALESCE(SUM(s.applied_amount),0) AS settled_amount
        FROM supplier_payments p
        LEFT JOIN supplier_payment_settlements s ON s.payment_id=p.id
        WHERE p.id=%s AND COALESCE(p.payment_kind,'supplier_payment')=%s
        GROUP BY p.id
        """,
        (payment_id, payment_kind),
    )
    if not doc:
        flash(f"{config['label']}不存在或已删除。", "warning")
        return redirect(config["list_url"])
    if not _funds_action_flags(doc)["can_delete"]:
        flash(f"财务单据不允许硬删除：只有未核销的草稿{config['label']}可删除；已确认或已核销请使用作废/反核销。", "warning")
        return redirect(f"{config['detail_base']}/{payment_id}")
    execute_db("DELETE FROM cash_bank_journal_entries WHERE source_type=%s AND source_no=%s", (config["source_type"], doc.get("payment_no")))
    execute_db("DELETE FROM supplier_payment_lines WHERE payment_id=%s", (payment_id,))
    execute_db("DELETE FROM supplier_payment_settlements WHERE payment_id=%s", (payment_id,))
    execute_db("DELETE FROM supplier_payments WHERE id=%s", (payment_id,))
    log_action(f"删除{config['label']}草稿", doc.get("payment_no"), f"id={payment_id}")
    flash(f"{config['label']}草稿已删除。", "success")
    return redirect(config["list_url"])


def render_customer_receipt_detail(receipt_id, query_one, query_rows, receipt_kind="customer_receipt"):
    config = _ar_receipt_config(receipt_kind)
    doc = query_one(
        """
        SELECT r.id, r.receipt_no, r.receipt_date, r.customer_id, r.source_no, r.project_code,
               r.cabinet_no, r.amount, r.payment_method, r.bank_account, r.remark, r.status,
               r.receipt_kind, r.created_at, r.created_by, r.source_type, r.source_id,
               r.receivable_id, r.cost_object_id, r.fund_direction,
               c.name AS partner_name, c.contact_person, c.phone AS partner_phone,
               COALESCE(SUM(s.applied_amount),0) AS settled_amount
        FROM customer_receipts r
        LEFT JOIN customers c ON c.id=r.customer_id
        LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
        WHERE r.id=%s AND COALESCE(r.receipt_kind,'customer_receipt')=%s
        GROUP BY r.id, r.receipt_no, r.receipt_date, r.customer_id, r.source_no, r.project_code,
                 r.cabinet_no, r.amount, r.payment_method, r.bank_account, r.remark, r.status,
                 r.receipt_kind, r.created_at, r.created_by, r.source_type, r.source_id,
                 r.receivable_id, r.cost_object_id, r.fund_direction,
                 c.name, c.contact_person, c.phone
        """,
        (receipt_id, receipt_kind),
    )
    if not doc:
        return render_template("simple_detail.html", title=config["detail_title"], row=None, back_url=config["list_url"], labels={})
    doc["unapplied_amount"] = max(as_decimal(doc.get("amount")) - as_decimal(doc.get("settled_amount")), Decimal("0"))
    action_flags = _funds_action_flags(doc)
    settlements = query_rows(
        """
        SELECT s.applied_amount, cr.source_type, cr.source_no, cr.receivable_date, cr.due_date,
               cr.total_amount, cr.balance, cr.project_code, cr.cabinet_no, cr.status
        FROM customer_receipt_settlements s
        JOIN customer_receivables cr ON cr.id=s.receivable_id
        WHERE s.receipt_id=%s
        ORDER BY s.id
        """,
        (receipt_id,),
    )
    receipt_lines = query_rows(
        """
        SELECT line_no, payment_method, bank_account, amount, fee_amount, transaction_no, remark
        FROM customer_receipt_lines
        WHERE receipt_id=%s
        ORDER BY line_no, id
        """,
        (receipt_id,),
    )
    attachments = query_rows(
        """
        SELECT id, file_name, stored_path, content_type, file_size, attachment_type, remark, uploaded_at
        FROM document_attachments
        WHERE subject_type='customer_receipt' AND subject_id=%s
        ORDER BY uploaded_at DESC, id DESC
        """,
        (receipt_id,),
    )
    logs = query_rows("SELECT username, action, target, remark, created_at FROM operation_logs WHERE target=%s ORDER BY created_at DESC, id DESC LIMIT 50", (doc.get("receipt_no"),))
    return render_template("finance_funds_detail.html", title=config["detail_title"], list_url=config["list_url"], new_url=config["new_url"], note_url=f"{config['detail_base']}/{receipt_id}/notes", edit_url=f"{config['detail_base']}/{receipt_id}/edit", delete_url=f"{config['detail_base']}/{receipt_id}/delete", reverse_url=f"{config['detail_base']}/{receipt_id}/reverse-settlement", void_url=f"{config['detail_base']}/{receipt_id}/void", action_flags=action_flags, doc=doc, doc_no=doc.get("receipt_no"), doc_date=doc.get("receipt_date"), partner_label="客户", amount_label=config["amount_label"], settled_label="已核销", unapplied_label="未分配", receipt_lines=receipt_lines, line_section_title=config["line_section_title"], line_account_label=config["line_account_label"], line_method_label=config["method_label"], line_amount_label=config["line_amount_label"], line_remark_label=config["line_remark_label"], settlements=settlements, attachments=attachments, attachment_upload_url=f"/customer-receipts/{receipt_id}/attachments", attachment_delete_prefix=f"/customer-receipts/{receipt_id}/attachments", logs=logs, settlement_columns=[("source_type", "来源类型"), ("source_no", "应收来源"), ("receivable_date", "应收日期"), ("due_date", "到期日"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("total_amount", "应收金额"), ("applied_amount", "本次核销"), ("balance", "当前余额"), ("status", "应收状态")])


def render_pending_collection_list(query_rows):
    keyword = (request.args.get("keyword") or "").strip()
    params = []
    where = ["COALESCE(cr.balance,0)>0"]
    if keyword:
        pattern = f"%{keyword}%"
        where.append("(cr.source_no ILIKE %s OR c.name ILIKE %s OR cr.project_code ILIKE %s OR cr.cabinet_no ILIKE %s OR cr.remark ILIKE %s)")
        params.extend([pattern] * 5)
    rows = query_rows(
        f"""
        SELECT cr.id, cr.source_no, cr.receivable_date, cr.due_date, c.name AS customer_name,
               cr.project_code, cr.cabinet_no, cr.total_amount, cr.received_amount, cr.balance, cr.status,
               CASE
                   WHEN cr.due_date IS NOT NULL AND cr.due_date < CURRENT_DATE THEN '已逾期，联系客户确认回款计划'
                   WHEN cr.due_date IS NOT NULL THEN '按到期日跟进回款'
                   ELSE '补齐到期日和收款责任人'
               END AS next_step
        FROM customer_receivables cr
        LEFT JOIN customers c ON c.id=cr.customer_id
        WHERE {' AND '.join(where)}
        ORDER BY cr.due_date NULLS FIRST, cr.receivable_date NULLS LAST, cr.id DESC
        LIMIT 300
        """,
        tuple(params),
    )
    return render_template(
        "simple_list.html",
        title="待收款清单",
        rows=rows,
        columns=[{"key": key, "label": label} for key, label in [("source_no", "应收来源"), ("receivable_date", "应收日期"), ("due_date", "到期日"), ("customer_name", "客户"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("total_amount", "应收金额"), ("received_amount", "已收"), ("balance", "待收金额"), ("status", "状态"), ("next_step", "下一步")]],
        detail_base="/receivables",
        keyword=keyword,
    )


def render_merged_collection_records(query_rows):
    keyword = (request.args.get("keyword") or "").strip()
    params = []
    where = ["COALESCE(r.receipt_kind,'customer_receipt') IN ('customer_receipt','advance_receipt','other_income')"]
    if keyword:
        pattern = f"%{keyword}%"
        where.append("(r.receipt_no ILIKE %s OR c.name ILIKE %s OR r.bank_account ILIKE %s OR r.project_code ILIKE %s OR r.cabinet_no ILIKE %s)")
        params.extend([pattern] * 5)
    rows = query_rows(
        f"""
        SELECT MIN(r.id) AS id, r.receipt_date, c.name AS customer_name,
               COALESCE(l.bank_account, r.bank_account, '-') AS bank_account,
               COALESCE(l.payment_method, r.payment_method, '-') AS payment_method,
               STRING_AGG(DISTINCT r.receipt_no, ' / ') AS receipt_no,
               COUNT(DISTINCT r.id) AS document_count,
               SUM(COALESCE(l.amount, r.amount, 0)) AS amount,
               STRING_AGG(DISTINCT NULLIF(l.transaction_no,''), ' / ') AS transaction_no,
               COALESCE(MAX(r.project_code), '-') AS project_code,
               COALESCE(MAX(r.cabinet_no), '-') AS cabinet_no
        FROM customer_receipts r
        LEFT JOIN customers c ON c.id=r.customer_id
        LEFT JOIN customer_receipt_lines l ON l.receipt_id=r.id
        WHERE {' AND '.join(where)}
        GROUP BY r.receipt_date, c.name, COALESCE(l.bank_account, r.bank_account, '-'), COALESCE(l.payment_method, r.payment_method, '-')
        ORDER BY r.receipt_date DESC NULLS LAST, MAX(r.id) DESC
        LIMIT 300
        """,
        tuple(params),
    )
    return render_template(
        "simple_list.html",
        title="合并收款记录列表",
        rows=rows,
        columns=[{"key": key, "label": label} for key, label in [("receipt_date", "收款日期"), ("customer_name", "客户"), ("bank_account", "资金账户/票据号"), ("payment_method", "收款方式"), ("receipt_no", "关联单据"), ("document_count", "单据数"), ("amount", "合并金额"), ("transaction_no", "交易号/票据号"), ("project_code", "项目号"), ("cabinet_no", "柜号")]],
        detail_base=None,
        keyword=keyword,
    )


def render_receivable_bill_list(query_rows):
    keyword = (request.args.get("keyword") or "").strip()
    params = []
    where = ["(l.payment_method ILIKE '%%票据%%' OR l.payment_method ILIKE '%%承兑%%' OR l.transaction_no ILIKE '%%票%%')"]
    if keyword:
        pattern = f"%{keyword}%"
        where.append("(r.receipt_no ILIKE %s OR c.name ILIKE %s OR l.transaction_no ILIKE %s OR l.bank_account ILIKE %s)")
        params.extend([pattern] * 4)
    rows = query_rows(
        f"""
        SELECT r.id, r.receipt_no, r.receipt_date, c.name AS customer_name,
               l.payment_method, l.bank_account, l.transaction_no, l.amount, l.fee_amount,
               r.project_code, r.cabinet_no, r.status
        FROM customer_receipt_lines l
        JOIN customer_receipts r ON r.id=l.receipt_id
        LEFT JOIN customers c ON c.id=r.customer_id
        WHERE {' AND '.join(where)}
        ORDER BY r.receipt_date DESC NULLS LAST, r.id DESC, l.line_no
        LIMIT 300
        """,
        tuple(params),
    )
    return render_template(
        "simple_list.html",
        title="应收票据",
        rows=rows,
        columns=[{"key": key, "label": label} for key, label in [("receipt_no", "来源单据"), ("receipt_date", "登记日期"), ("customer_name", "客户"), ("payment_method", "票据类型"), ("bank_account", "资金账户/票据号"), ("transaction_no", "交易号/票据号"), ("amount", "票据金额"), ("fee_amount", "手续费"), ("project_code", "项目号"), ("cabinet_no", "柜号"), ("status", "状态")]],
        detail_base=None,
        keyword=keyword,
    )


def render_supplier_payment_detail(payment_id, query_one, query_rows, payment_kind="supplier_payment"):
    config = _ap_payment_config(payment_kind)
    doc = query_one(
        """
        SELECT p.id, p.payment_no, p.payment_date, p.supplier_id, p.source_no, p.project_code,
               p.cabinet_no, p.amount, p.payment_method, p.bank_account, p.remark, p.status,
               p.payment_kind, p.created_at, p.created_by, p.source_type, p.source_id,
               p.operator_id, p.payable_id, p.cost_object_id, p.fund_direction,
               s.name AS partner_name, s.contact_person, s.phone AS partner_phone,
               COALESCE(SUM(ps.applied_amount),0) AS settled_amount
        FROM supplier_payments p
        LEFT JOIN suppliers s ON s.id=p.supplier_id
        LEFT JOIN supplier_payment_settlements ps ON ps.payment_id=p.id
        WHERE p.id=%s AND COALESCE(p.payment_kind,'supplier_payment')=%s
        GROUP BY p.id, p.payment_no, p.payment_date, p.supplier_id, p.source_no, p.project_code,
                 p.cabinet_no, p.amount, p.payment_method, p.bank_account, p.remark, p.status,
                 p.payment_kind, p.created_at, p.created_by, p.source_type, p.source_id,
                 p.operator_id, p.payable_id, p.cost_object_id, p.fund_direction,
                 s.name, s.contact_person, s.phone
        """,
        (payment_id, payment_kind),
    )
    if not doc:
        return render_template("simple_detail.html", title=config["detail_title"], row=None, back_url=config["list_url"], labels={})
    doc["unapplied_amount"] = max(as_decimal(doc.get("amount")) - as_decimal(doc.get("settled_amount")), Decimal("0"))
    action_flags = _funds_action_flags(doc)
    settlements = query_rows(
        """
        SELECT ps.applied_amount, sp.doc_no, sp.doc_date, sp.amount, sp.balance, sp.status
        FROM supplier_payment_settlements ps
        JOIN supplier_payables sp ON sp.id=ps.payable_id
        WHERE ps.payment_id=%s
        ORDER BY ps.id
        """,
        (payment_id,),
    )
    receipt_lines = query_rows(
        """
        SELECT line_no, payment_method, bank_account, amount, fee_amount, transaction_no, remark
        FROM supplier_payment_lines
        WHERE payment_id=%s
        ORDER BY line_no, id
        """,
        (payment_id,),
    )
    logs = query_rows("SELECT username, action, target, remark, created_at FROM operation_logs WHERE target=%s ORDER BY created_at DESC, id DESC LIMIT 50", (doc.get("payment_no"),))
    return render_template("finance_funds_detail.html", title=config["detail_title"], list_url=config["list_url"], new_url=config["new_url"], note_url=f"{config['detail_base']}/{payment_id}/notes", edit_url=f"{config['detail_base']}/{payment_id}/edit", delete_url=f"{config['detail_base']}/{payment_id}/delete", reverse_url=f"{config['detail_base']}/{payment_id}/reverse-settlement", void_url=f"{config['detail_base']}/{payment_id}/void", action_flags=action_flags, doc=doc, doc_no=doc.get("payment_no"), doc_date=doc.get("payment_date"), partner_label="供应商", amount_label=config["amount_label"], settled_label="已核销", unapplied_label="未分配", receipt_lines=receipt_lines, line_section_title=config["line_section_title"], line_account_label=config["line_account_label"], line_method_label=config["method_label"], line_amount_label=config["line_amount_label"], line_remark_label=config["line_remark_label"], settlements=settlements, logs=logs, settlement_columns=[("doc_no", "应付来源"), ("doc_date", "应付日期"), ("amount", "应付金额"), ("applied_amount", "本次核销"), ("balance", "当前余额"), ("status", "应付状态")])


def render_aging_analysis(query_rows):
    """应收应付账龄分析：按账龄分层着色"""
    now = date.today()
    aging_rows = query_rows(
        """
        SELECT '应收' AS kind, source_no AS doc_no, receivable_date AS doc_date,
               COALESCE(due_date, receivable_date) AS due_date,
               total_amount, received_amount AS settled_amount, balance, status, project_code, cabinet_no,
               CURRENT_DATE - COALESCE(due_date, receivable_date, CURRENT_DATE) AS age_days
        FROM customer_receivables
        WHERE COALESCE(balance,0) <> 0
        UNION ALL
        SELECT '应付' AS kind, doc_no, doc_date,
               COALESCE(next_follow_up_date, doc_date) AS due_date,
               amount AS total_amount, paid_amount AS settled_amount, balance, status, NULL AS project_code, NULL AS cabinet_no,
               CURRENT_DATE - COALESCE(next_follow_up_date, doc_date, CURRENT_DATE) AS age_days
        FROM supplier_payables
        WHERE COALESCE(balance,0) <> 0
        ORDER BY age_days DESC, balance DESC
        LIMIT 200
        """
    )
    for row in aging_rows:
        is_receivable = row["kind"] == "应收"
        row["detail_url"] = f"{'/receivables' if is_receivable else '/payables'}?keyword={row.get('doc_no') or ''}"
        settled = as_decimal(row.get("settled_amount"))
        balance_value = as_decimal(row.get("balance"))
        if balance_value <= 0:
            row["settlement_status"] = "已核销"
        elif settled > 0:
            row["settlement_status"] = "部分核销"
        else:
            row["settlement_status"] = "未核销"
        age_days = as_decimal(row.get("age_days"))
        if age_days < 0:
            row["aging_bucket"] = "未到期"
        elif age_days <= 30:
            row["aging_bucket"] = "0-30天"
        elif age_days <= 60:
            row["aging_bucket"] = "31-60天"
        elif age_days <= 90:
            row["aging_bucket"] = "61-90天"
        else:
            row["aging_bucket"] = "90天以上"

    receivable_balance = sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("kind") == "应收")
    payable_balance = sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("kind") == "应付")
    overdue_rows = [r for r in aging_rows if as_decimal(r.get("age_days")) > 0]
    overdue_amount = sum(as_decimal(r.get("balance")) for r in overdue_rows)
    if _is_tabular_export_request():
        return _csv_response(aging_rows, "finance-aging")

    return render_template(
        "finance_aging_report.html",
        title="应收应付账龄",
        subtitle=f"截至{now}，应收应付余额按账龄分层分析。",
        view_mode="aging",
        rows=aging_rows,
        metrics={
            "receivable_balance": receivable_balance,
            "payable_balance": payable_balance,
            "overdue_count": len(overdue_rows),
            "overdue_amount": overdue_amount,
        },
    )


def render_aging_buckets_summary(query_rows):
    """账龄区间汇总：按区间聚合统计"""
    now = date.today()
    aging_rows = query_rows(
        """
        SELECT '应收' AS kind, balance, project_code, cabinet_no,
               CURRENT_DATE - COALESCE(due_date, receivable_date, CURRENT_DATE) AS age_days
        FROM customer_receivables
        WHERE COALESCE(balance,0) <> 0
        UNION ALL
        SELECT '应付' AS kind, balance,
               NULL AS project_code, NULL AS cabinet_no,
               CURRENT_DATE - COALESCE(next_follow_up_date, doc_date, CURRENT_DATE) AS age_days
        FROM supplier_payables
        WHERE COALESCE(balance,0) <> 0
        """
    )
    for row in aging_rows:
        age_days = as_decimal(row.get("age_days"))
        if age_days < 0:
            row["aging_bucket"] = "未到期"
        elif age_days <= 30:
            row["aging_bucket"] = "0-30天"
        elif age_days <= 60:
            row["aging_bucket"] = "31-60天"
        elif age_days <= 90:
            row["aging_bucket"] = "61-90天"
        else:
            row["aging_bucket"] = "90天以上"

    buckets = [
        {
            "bucket": bucket,
            "receivable_amount": sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("aging_bucket") == bucket and r.get("kind") == "应收"),
            "payable_amount": sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("aging_bucket") == bucket and r.get("kind") == "应付"),
            "amount": sum(as_decimal(r.get("balance")) for r in aging_rows if r.get("aging_bucket") == bucket),
            "count": sum(1 for r in aging_rows if r.get("aging_bucket") == bucket),
        }
        for bucket in ("未到期", "0-30天", "31-60天", "61-90天", "90天以上")
    ]
    if _is_tabular_export_request():
        return _csv_response(buckets, "finance-aging-buckets")

    return render_template(
        "finance_aging_report.html",
        title="账龄区间汇总",
        subtitle=f"截至{now}，应收应付余额按账龄区间汇总。",
        view_mode="buckets",
        buckets=buckets,
    )


def render_partner_balance_detail(query_rows):
    """往来余额明细：按往来单位展示应收应付余额"""
    now = date.today()
    receivables = query_rows(
        """
        SELECT source_no AS doc_no, receivable_date AS doc_date, '应收' AS kind,
               total_amount, received_amount AS settled_amount, balance, status, project_code, cabinet_no
        FROM customer_receivables
        ORDER BY receivable_date DESC NULLS LAST, id DESC
        LIMIT 150
        """
    )
    payables = query_rows(
        """
        SELECT doc_no, doc_date, '应付' AS kind,
               amount AS total_amount, paid_amount AS settled_amount, balance, status, project_code, cabinet_no
        FROM supplier_payables
        ORDER BY doc_date DESC NULLS LAST, id DESC
        LIMIT 150
        """
    )
    rows = receivables + payables
    for row in rows:
        is_receivable = row["kind"] == "应收"
        row["detail_url"] = f"{'/receivables' if is_receivable else '/payables'}?keyword={row.get('doc_no') or ''}"
        settled = as_decimal(row.get("settled_amount"))
        balance_value = as_decimal(row.get("balance"))
        if balance_value <= 0:
            row["settlement_status"] = "已核销"
        elif settled > 0:
            row["settlement_status"] = "部分核销"
        else:
            row["settlement_status"] = "未核销"

    receivable_balance = sum(as_decimal(r.get("balance")) for r in rows if r.get("kind") == "应收")
    payable_balance = sum(as_decimal(r.get("balance")) for r in rows if r.get("kind") == "应付")
    receivable_settled = sum(as_decimal(r.get("settled_amount")) for r in rows if r.get("kind") == "应收")
    payable_settled = sum(as_decimal(r.get("settled_amount")) for r in rows if r.get("kind") == "应付")
    if _is_tabular_export_request():
        return _csv_response(rows, "finance-partner-balance")

    return render_template(
        "finance_aging_report.html",
        title="往来余额明细",
        subtitle=f"截至{now}，应收应付往来单位余额明细。",
        view_mode="balance",
        rows=rows,
        metrics={
            "receivable_balance": receivable_balance,
            "payable_balance": payable_balance,
            "receivable_settled": receivable_settled,
            "payable_settled": payable_settled,
        },
    )


def register_routes(app, deps):
    login_required = deps["login_required"]
    query_db = deps["query_db"]
    query_one = lambda sql, params=None: query_db(sql, params or (), one=True)
    query_rows = lambda sql, params=None: query_db(sql, params or ())
    execute_db = deps["execute_db"]
    execute_and_return = deps.get("execute_and_return") or (lambda sql, params=None: None)
    next_doc_no = deps.get("next_doc_no") or (lambda prefix, table, field: f"{prefix}{date.today():%Y%m%d}")
    log_action = deps.get("log_action") or (lambda *args, **kwargs: None)

    @app.get("/finance/todo-documents", endpoint="finance_todo_documents")
    @login_required
    def finance_todo_documents():
        return render_finance_todo_documents()

    @app.get("/finance/business-exceptions", endpoint="finance_business_exceptions")
    @login_required
    def finance_business_exceptions():
        return render_business_exceptions_report()

    @app.get("/finance/unbilled-sales", endpoint="finance_unbilled_sales")
    @login_required
    def finance_unbilled_sales():
        return render_unbilled_sales_report()

    @app.get("/finance/unreceived-purchase-invoices", endpoint="finance_unreceived_purchase_invoices")
    @login_required
    def finance_unreceived_purchase_invoices():
        return render_unreceived_purchase_invoice_report()

    @app.get("/finance/invoice-matching", endpoint="finance_invoice_matching")
    @login_required
    def finance_invoice_matching():
        return render_invoice_matching_report()

    @app.get("/finance/reports/output-tax", endpoint="finance_output_tax_report")
    @login_required
    def finance_output_tax_report():
        return render_output_tax_report()

    @app.get("/finance/reports/input-tax", endpoint="finance_input_tax_report")
    @login_required
    def finance_input_tax_report():
        return render_input_tax_report()

    @app.get("/finance/reports/tax-summary", endpoint="finance_tax_summary_report")
    @login_required
    def finance_tax_summary_report():
        return render_tax_summary_report()

    @app.get("/finance/bank-reconciliation", endpoint="finance_bank_reconciliation")
    @login_required
    def finance_bank_reconciliation():
        return render_bank_reconciliation_report(query_rows)

    # C-2: 银行对账单导入与匹配（新路由，不影响现有只读报告）
    @app.get("/finance/bank-statements", endpoint="finance_bank_statements_list")
    @login_required
    def finance_bank_statements_list():
        """银行对账单列表。"""
        account_id = request.args.get("account_id", type=int)
        status = request.args.get("status", "").strip() or None
        statements = list_bank_statements(query_db, account_id=account_id, status=status)
        accounts = query_rows(
            "SELECT id, account_code, account_name, bank_account_no FROM cash_bank_accounts WHERE status='active' ORDER BY account_code"
        )
        return render_template(
            "finance/bank_statements_list.html",
            statements=statements,
            accounts=[dict(a) for a in accounts or []],
            filters={"account_id": account_id, "status": status},
        )

    @app.get("/finance/bank-statements/import", endpoint="finance_bank_statement_import_form")
    @login_required
    def finance_bank_statement_import_form():
        """银行对账单 CSV 导入页面。"""
        accounts = query_rows(
            "SELECT id, account_code, account_name, bank_account_no FROM cash_bank_accounts WHERE status='active' ORDER BY account_code"
        )
        return render_template(
            "finance/bank_statement_import.html",
            accounts=[dict(a) for a in accounts or []],
        )

    @app.post("/finance/bank-statements/import", endpoint="finance_bank_statement_import")
    @login_required
    def finance_bank_statement_import():
        """处理银行对账单 CSV 上传。"""
        account_id = request.form.get("account_id", type=int)
        statement_date = request.form.get("statement_date")
        opening_balance = decimal_text(request.form.get("opening_balance", "0"))
        closing_balance = decimal_text(request.form.get("closing_balance", "0"))
        file = request.files.get("file")
        if not account_id or not statement_date or not file:
            flash("请选择银行账户、对账单日期并上传文件。", "danger")
            return redirect(url_for("finance_bank_statement_import_form"))
        rows, errors = read_validated_csv_upload(file)
        if errors:
            flash(f"文件校验失败：{'; '.join(errors[:5])}", "danger")
            return redirect(url_for("finance_bank_statement_import_form"))
        if not rows:
            flash("文件中没有数据行。", "danger")
            return redirect(url_for("finance_bank_statement_import_form"))
        # 解析行数据
        parsed_rows = []
        for idx, row in enumerate(rows, start=1):
            txn_date = csv_cell(row, "transaction_date", "交易日期", "日期")
            amount_str = csv_cell(row, "amount", "金额", "发生额")
            direction = csv_cell(row, "direction", "方向") or ""
            counterparty_name = csv_cell(row, "counterparty_name", "对方户名", "对方名称")
            counterparty_account = csv_cell(row, "counterparty_account", "对方账号")
            counterparty_bank = csv_cell(row, "counterparty_bank", "对方开户行")
            summary = csv_cell(row, "summary", "摘要", "备注")
            bank_reference = csv_cell(row, "bank_reference", "银行流水号", "流水号")
            amount = decimal_text(amount_str)
            if amount == 0:
                continue
            if not direction:
                direction = "in" if amount > 0 else "out"
            elif direction in ("收入", "借", "in", "IN"):
                direction = "in"
            elif direction in ("支出", "贷", "out", "OUT"):
                direction = "out"
            parsed_rows.append({
                "transaction_date": txn_date or statement_date,
                "amount": abs(amount),
                "direction": direction,
                "counterparty_name": counterparty_name,
                "counterparty_account": counterparty_account,
                "counterparty_bank": counterparty_bank,
                "summary": summary,
                "bank_reference": bank_reference,
            })
        if not parsed_rows:
            flash("解析后没有有效数据行。", "danger")
            return redirect(url_for("finance_bank_statement_import_form"))
        result = import_bank_statement_lines(
            query_db,
            execute_db,
            account_id=account_id,
            statement_date=statement_date,
            rows=parsed_rows,
            source_file=file.filename,
            imported_by=session.get("user_id"),
            opening_balance=opening_balance,
            closing_balance=closing_balance,
        )
        if result.get("statement_id"):
            flash(
                f"导入成功：{result['line_count']} 条明细，"
                f"收入合计 {result['total_deposits']:.2f}，"
                f"支出合计 {result['total_withdrawals']:.2f}。",
                "success",
            )
            return redirect(url_for("finance_bank_statement_detail", statement_id=result["statement_id"]))
        flash("导入失败。", "danger")
        return redirect(url_for("finance_bank_statement_import_form"))

    @app.get("/finance/bank-statements/<int:statement_id>", endpoint="finance_bank_statement_detail")
    @login_required
    def finance_bank_statement_detail(statement_id):
        """银行对账单详情与匹配视图。"""
        detail = get_statement_detail(query_db, statement_id=statement_id)
        if not detail.get("statement"):
            flash("对账单不存在。", "danger")
            return redirect(url_for("finance_bank_statements_list"))
        return render_template(
            "finance/bank_statement_detail.html",
            statement=detail["statement"],
            lines=detail["lines"],
            summary=detail["summary"],
        )

    @app.post("/finance/bank-statements/<int:statement_id>/auto-match", endpoint="finance_bank_statement_auto_match")
    @login_required
    def finance_bank_statement_auto_match(statement_id):
        """自动匹配对账单行。"""
        result = auto_match_statement_lines(
            query_db, execute_db, statement_id=statement_id, matched_by=session.get("user_id")
        )
        flash(
            f"自动匹配完成：匹配 {result['matched']} 条，未匹配 {result['unmatched']} 条。",
            "success" if result["matched"] > 0 else "info",
        )
        return redirect(url_for("finance_bank_statement_detail", statement_id=statement_id))

    @app.post("/finance/bank-statements/lines/<int:line_id>/match", endpoint="finance_bank_statement_manual_match")
    @login_required
    def finance_bank_statement_manual_match(line_id):
        """人工勾选匹配。"""
        journal_id = request.form.get("journal_id", type=int)
        if not journal_id:
            flash("请选择要匹配的日记账记录。", "danger")
            return redirect(request.referrer or url_for("finance_bank_statements_list"))
        result = manual_match_line(
            query_db, execute_db, line_id=line_id, journal_id=journal_id, matched_by=session.get("user_id")
        )
        flash(result.get("message", "操作完成"), "success" if result.get("success") else "danger")
        return redirect(request.referrer or url_for("finance_bank_statements_list"))

    @app.post("/finance/bank-statements/lines/<int:line_id>/unmatch", endpoint="finance_bank_statement_unmatch")
    @login_required
    def finance_bank_statement_unmatch(line_id):
        """取消匹配。"""
        result = unmatch_line(execute_db, line_id=line_id)
        flash(result.get("message", "操作完成"), "success" if result.get("success") else "danger")
        return redirect(request.referrer or url_for("finance_bank_statements_list"))

    @app.get("/finance/bank-statements/lines/<int:line_id>/unmatched-journals", endpoint="finance_bank_statement_unmatched_journals")
    @login_required
    def finance_bank_statement_unmatched_journals(line_id):
        """获取未匹配的日记账记录列表（供人工勾选）。"""
        line = query_one(
            "SELECT id, statement_id FROM bank_statement_lines WHERE id = %s",
            (line_id,),
        )
        if not line:
            return jsonify({"journals": []})
        account_id = query_one(
            "SELECT account_id FROM bank_statements WHERE id = %s",
            (line["statement_id"],),
        )
        if not account_id:
            return jsonify({"journals": []})
        journals = list_unmatched_journal_entries(
            query_db, account_id=account_id["account_id"], line_id=line_id
        )
        return jsonify({"journals": journals})

    # C-5: 外汇期末调整
    @app.get("/finance/fx-rates", endpoint="finance_fx_rates_list")
    @login_required
    def finance_fx_rates_list():
        """汇率历史列表。"""
        currency_code = request.args.get("currency_code", "").strip() or None
        rates = list_exchange_rates(query_db, currency_code=currency_code)
        currencies = query_rows(
            "SELECT code, name, exchange_rate, is_base FROM currencies WHERE status='active' ORDER BY code"
        )
        return render_template(
            "finance/fx_rates_list.html",
            rates=rates,
            currencies=[dict(c) for c in currencies or []],
            filter_currency=currency_code,
        )

    @app.post("/finance/fx-rates", endpoint="finance_fx_rate_create")
    @login_required
    def finance_fx_rate_create():
        """新增或更新汇率。"""
        currency_code = request.form.get("currency_code", "").strip()
        rate_date = request.form.get("rate_date", "").strip()
        rate_to_base = decimal_text(request.form.get("rate_to_base", "1"))
        rate_type = request.form.get("rate_type", "period_end").strip() or "period_end"
        source = request.form.get("source", "").strip()
        remark = request.form.get("remark", "").strip()
        if not currency_code or not rate_date or rate_to_base <= 0:
            flash("请填写币种、日期和大于 0 的汇率。", "danger")
            return redirect(url_for("finance_fx_rates_list"))
        upsert_exchange_rate(
            execute_db,
            currency_code=currency_code,
            rate_date=rate_date,
            rate_to_base=rate_to_base,
            rate_type=rate_type,
            source=source,
            remark=remark,
            created_by=session.get("user_id"),
        )
        flash(f"汇率已保存：{currency_code} @ {rate_date} = {rate_to_base}", "success")
        return redirect(url_for("finance_fx_rates_list"))

    @app.get("/finance/fx-adjustments", endpoint="finance_fx_adjustments_list")
    @login_required
    def finance_fx_adjustments_list():
        """外汇调整运行列表。"""
        runs = list_fx_adjustment_runs(query_db)
        return render_template("finance/fx_adjustments_list.html", runs=runs)

    @app.post("/finance/fx-adjustments/run", endpoint="finance_fx_adjustment_run")
    @login_required
    def finance_fx_adjustment_run():
        """执行外汇期末调整。"""
        period_year = request.form.get("period_year", type=int)
        period_month = request.form.get("period_month", type=int)
        adjustment_date = request.form.get("adjustment_date", "").strip() or None
        if not period_year or not period_month:
            flash("请填写期间年份和月份。", "danger")
            return redirect(url_for("finance_fx_adjustments_list"))
        result = run_fx_adjustment(
            query_db,
            execute_db,
            period_year=period_year,
            period_month=period_month,
            adjustment_date=adjustment_date,
            created_by=session.get("user_id"),
            execute_and_return=execute_and_return,
        )
        flash(
            f"外汇调整完成：{result['line_count']} 条明细，"
            f"应收调整 {result['ar_adjustment']:.2f}，"
            f"应付调整 {result['ap_adjustment']:.2f}，"
            f"汇兑损益合计 {result['total_gain_loss']:.2f}。",
            "success",
        )
        return redirect(url_for("finance_fx_adjustment_detail", run_id=result["run_id"]))

    @app.get("/finance/fx-adjustments/<int:run_id>", endpoint="finance_fx_adjustment_detail")
    @login_required
    def finance_fx_adjustment_detail(run_id):
        """外汇调整运行详情。"""
        detail = get_fx_adjustment_run_detail(query_db, run_id=run_id)
        if not detail.get("run"):
            flash("调整运行不存在。", "danger")
            return redirect(url_for("finance_fx_adjustments_list"))
        return render_template(
            "finance/fx_adjustment_detail.html",
            run=detail["run"],
            lines=detail["lines"],
        )

    @app.get("/finance/fund-daily", endpoint="finance_fund_daily")
    @login_required
    def finance_fund_daily():
        return render_fund_daily_report()

    @app.get("/finance/closing-checks", endpoint="finance_closing_checks")
    @login_required
    def finance_closing_checks():
        return render_closing_checks_report()

    @app.get("/finance/vouchers/generate", endpoint="finance_voucher_generation_preview")
    @login_required
    def finance_voucher_generation_preview():
        return render_voucher_generation_preview(query_rows)

    @app.get("/finance/vouchers/generate-batch", endpoint="finance_voucher_generate_batch_form")
    @login_required
    def finance_voucher_generate_batch_form():
        """C-1: 凭证受控生成 - 批量生成表单页面。"""
        sales_invoices = query_rows(
            """
            SELECT si.id, si.invoice_no, si.invoice_date,
                   COALESCE(si.amount_with_tax, si.amount, 0) AS amount,
                   c.name AS customer_name
            FROM sales_invoices si
            JOIN customers c ON si.customer_id = c.id
            WHERE COALESCE(si.status, '') NOT IN ('void', 'voided', 'cancelled')
              AND NOT EXISTS (
                  SELECT 1 FROM vouchers v
                  WHERE v.source_type = 'sales_invoice' AND v.source_id = si.id
              )
            ORDER BY si.invoice_date DESC LIMIT 50
            """
        )
        purchase_invoices = query_rows(
            """
            SELECT pi.id, pi.invoice_no, pi.invoice_date,
                   COALESCE(pi.amount_with_tax, pi.amount, 0) AS amount,
                   s.name AS supplier_name
            FROM purchase_invoices pi
            JOIN suppliers s ON pi.supplier_id = s.id
            WHERE COALESCE(pi.status, '') NOT IN ('void', 'voided', 'cancelled')
              AND NOT EXISTS (
                  SELECT 1 FROM vouchers v
                  WHERE v.source_type = 'purchase_invoice' AND v.source_id = pi.id
              )
            ORDER BY pi.invoice_date DESC LIMIT 50
            """
        )
        receipts = query_rows(
            """
            SELECT cr.id, cr.receipt_no, cr.receipt_date, cr.amount,
                   c.name AS customer_name
            FROM customer_receipts cr
            JOIN customers c ON cr.customer_id = c.id
            WHERE COALESCE(cr.status, '') NOT IN ('void', 'voided', 'cancelled')
              AND NOT EXISTS (
                  SELECT 1 FROM vouchers v
                  WHERE v.source_type = COALESCE(cr.receipt_kind, 'customer_receipt')
                    AND v.source_id = cr.id
              )
            ORDER BY cr.receipt_date DESC LIMIT 50
            """
        )
        payments = query_rows(
            """
            SELECT sp.id, sp.payment_no, sp.payment_date, sp.amount,
                   s.name AS supplier_name
            FROM supplier_payments sp
            JOIN suppliers s ON sp.supplier_id = s.id
            WHERE COALESCE(sp.status, '') NOT IN ('void', 'voided', 'cancelled')
              AND NOT EXISTS (
                  SELECT 1 FROM vouchers v
                  WHERE v.source_type = COALESCE(sp.payment_kind, 'supplier_payment')
                    AND v.source_id = sp.id
              )
            ORDER BY sp.payment_date DESC LIMIT 50
            """
        )
        return render_template(
            "finance/voucher_generate_batch.html",
            sales_invoices=sales_invoices or [],
            purchase_invoices=purchase_invoices or [],
            receipts=receipts or [],
            payments=payments or [],
        )

    @app.post("/finance/vouchers/generate-batch", endpoint="finance_voucher_generate_batch")
    @login_required
    def finance_voucher_generate_batch():
        """C-1: 凭证受控生成 - 批量生成凭证（草稿状态），操作员确认后过账。"""
        selected_items = request.form.getlist("selected_items")
        current_user_id = session.get("user_id")
        success_count = 0
        error_count = 0
        errors = []
        for item in selected_items:
            parts = item.split(":")
            if len(parts) != 2:
                continue
            source_type, source_id = parts[0], int(parts[1])
            try:
                result = generate_voucher_from_source(
                    query_db, execute_db, source_type, source_id, current_user_id
                )
                if result.get("success"):
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"{source_type}#{source_id}: {result.get('message', '未知错误')}")
            except Exception as exc:
                error_count += 1
                errors.append(f"{source_type}#{source_id}: {exc}")
        if success_count > 0:
            flash(f"成功生成 {success_count} 张凭证（草稿状态），请前往凭证列表复核并过账。", "success")
        if error_count > 0:
            flash(f"失败 {error_count} 条：{'; '.join(errors[:5])}", "danger")
        return redirect(url_for("finance_vouchers"))

    @app.get("/finance/settings", endpoint="finance_settings_overview")
    @login_required
    def finance_settings_overview():
        return render_finance_settings_overview()

    @app.get("/finance/inventory-accounting", endpoint="finance_inventory_accounting_home")
    @login_required
    def finance_inventory_accounting_home():
        return render_inventory_accounting_home()

    @app.get("/finance/inventory-reconciliation", endpoint="finance_inventory_reconciliation")
    @login_required
    def finance_inventory_reconciliation():
        return render_inventory_reconciliation_report()

    @app.get("/finance/project-costs", endpoint="finance_project_costs_standard")
    @login_required
    def finance_project_costs_standard():
        return redirect("/finance/reports/project-cost")

    @app.get("/finance/cabinet-costs", endpoint="finance_cabinet_costs_standard")
    @login_required
    def finance_cabinet_costs_standard():
        return redirect("/finance/reports/machine-cost")

    @app.get("/finance/work-order-costs", endpoint="finance_work_order_costs_standard")
    @login_required
    def finance_work_order_costs_standard():
        return render_cost_management_home()

    @app.get("/finance/cost-management", endpoint="finance_cost_management_home")
    @login_required
    def finance_cost_management_home():
        return render_cost_management_home()

    @app.get("/finance/reports/project-profit", endpoint="finance_project_profit_report")
    @login_required
    def finance_project_profit_report():
        return render_cost_management_home()

    @app.get("/finance/reports/cabinet-profit", endpoint="finance_cabinet_profit_report")
    @login_required
    def finance_cabinet_profit_report():
        return render_cost_management_home()

    def register_ar_receipt_document_routes(receipt_kind, list_endpoint, new_endpoint, detail_endpoint, edit_endpoint, delete_endpoint, reverse_endpoint, void_endpoint, note_endpoint):
        config = _ar_receipt_config(receipt_kind)

        @app.get(config["list_url"], endpoint=list_endpoint)
        @login_required
        def ar_receipt_list(receipt_kind=receipt_kind):
            return render_customer_receipt_list(query_rows, receipt_kind=receipt_kind)

        @app.route(config["new_url"], methods=["GET", "POST"], endpoint=new_endpoint)
        @login_required
        def ar_receipt_new(receipt_kind=receipt_kind):
            if request.method == "POST":
                def operation(cursor):
                    if not cursor:
                        return post_customer_receipt(query_one, query_rows, execute_db, execute_and_return, next_doc_no, log_action, receipt_kind=receipt_kind)
                    tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return = _transaction_callables(cursor)
                    tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
                    return post_customer_receipt(tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return, next_doc_no, tx_log_action, receipt_kind=receipt_kind)

                return _run_finance_funds_transaction(operation)
            return render_customer_receipt_entry(query_rows, receipt_kind=receipt_kind)

        @app.get(f"{config['detail_base']}/<int:receipt_id>", endpoint=detail_endpoint)
        @login_required
        def ar_receipt_detail(receipt_id, receipt_kind=receipt_kind):
            return render_customer_receipt_detail(receipt_id, query_one, query_rows, receipt_kind=receipt_kind)

        @app.route(f"{config['detail_base']}/<int:receipt_id>/edit", methods=["GET", "POST"], endpoint=edit_endpoint)
        @login_required
        def ar_receipt_edit(receipt_id, receipt_kind=receipt_kind):
            config = _ar_receipt_config(receipt_kind)
            if request.method == "POST":
                def operation(cursor):
                    if not cursor:
                        return post_customer_receipt_edit(receipt_id, query_one, query_rows, execute_db, log_action, receipt_kind=receipt_kind)
                    tx_query_one, tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
                    tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
                    return post_customer_receipt_edit(receipt_id, tx_query_one, tx_query_rows, tx_execute_db, tx_log_action, receipt_kind=receipt_kind)

                return _run_finance_funds_transaction(operation)
            doc, settlements = _customer_receipt_edit_context(receipt_id, query_one, query_rows, receipt_kind)
            if not doc:
                flash(f"{config['label']}不存在。", "warning")
                return redirect(config["list_url"])
            if not _funds_action_flags(doc)["can_edit"]:
                flash(f"只有未核销的草稿{config['label']}可以编辑；已确认、已核销、已作废单据请走反核销或作废流程。", "warning")
                return redirect(f"{config['detail_base']}/{receipt_id}")
            return render_customer_receipt_entry(query_rows, doc=doc, settlements=settlements, receipt_kind=receipt_kind)

        @app.post(f"{config['detail_base']}/<int:receipt_id>/delete", endpoint=delete_endpoint)
        @login_required
        def ar_receipt_delete(receipt_id, receipt_kind=receipt_kind):
            def operation(cursor):
                if not cursor:
                    return post_customer_receipt_delete(receipt_id, query_one, execute_db, log_action, receipt_kind=receipt_kind)
                tx_query_one, _tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
                tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
                return post_customer_receipt_delete(receipt_id, tx_query_one, tx_execute_db, tx_log_action, receipt_kind=receipt_kind)

            return _run_finance_funds_transaction(operation)

        @app.post(f"{config['detail_base']}/<int:receipt_id>/reverse-settlement", endpoint=reverse_endpoint)
        @login_required
        def ar_receipt_reverse_settlement(receipt_id, receipt_kind=receipt_kind):
            return post_customer_receipt_reverse_settlement(receipt_id, query_one, query_rows, execute_db, log_action, receipt_kind=receipt_kind)

        @app.post(f"{config['detail_base']}/<int:receipt_id>/void", endpoint=void_endpoint)
        @login_required
        def ar_receipt_void(receipt_id, receipt_kind=receipt_kind):
            return post_customer_receipt_void(receipt_id, query_one, query_rows, execute_db, log_action, receipt_kind=receipt_kind)

        @app.post(f"{config['detail_base']}/<int:receipt_id>/notes", endpoint=note_endpoint)
        @login_required
        def ar_receipt_note(receipt_id, receipt_kind=receipt_kind):
            config = _ar_receipt_config(receipt_kind)
            row = query_one("SELECT receipt_no FROM customer_receipts WHERE id=%s AND COALESCE(receipt_kind,'customer_receipt')=%s", (receipt_id, receipt_kind))
            if not row:
                flash(f"{config['label']}不存在。", "warning")
                return redirect(config["list_url"])
            note = (request.form.get("note") or "").strip()
            if not note:
                flash("请输入备注内容。", "warning")
                return redirect(f"{config['detail_base']}/{receipt_id}")
            log_action(f"{config['label']}备注", row.get("receipt_no"), note)
            flash("备注已保存。", "success")
            return redirect(f"{config['detail_base']}/{receipt_id}")

    register_ar_receipt_document_routes("customer_receipt", "customer_receipt_list", "customer_receipt_new", "customer_receipt_detail", "customer_receipt_edit", "customer_receipt_delete", "customer_receipt_reverse_settlement", "customer_receipt_void", "customer_receipt_note")
    register_ar_receipt_document_routes("advance_receipt", "customer_advance_receipt_list", "customer_advance_receipt_new", "customer_advance_receipt_detail", "customer_advance_receipt_edit", "customer_advance_receipt_delete", "customer_advance_receipt_reverse_settlement", "customer_advance_receipt_void", "customer_advance_receipt_note")
    register_ar_receipt_document_routes("receipt_refund", "customer_receipt_refund_list", "customer_receipt_refund_new", "customer_receipt_refund_detail", "customer_receipt_refund_edit", "customer_receipt_refund_delete", "customer_receipt_refund_reverse_settlement", "customer_receipt_refund_void", "customer_receipt_refund_note")
    register_ar_receipt_document_routes("advance_refund", "customer_advance_refund_list", "customer_advance_refund_new", "customer_advance_refund_detail", "customer_advance_refund_edit", "customer_advance_refund_delete", "customer_advance_refund_reverse_settlement", "customer_advance_refund_void", "customer_advance_refund_note")
    register_ar_receipt_document_routes("other_income", "customer_other_income_list", "customer_other_income_new", "customer_other_income_detail", "customer_other_income_edit", "customer_other_income_delete", "customer_other_income_reverse_settlement", "customer_other_income_void", "customer_other_income_note")
    register_ar_receipt_document_routes("other_income_refund", "customer_other_income_refund_list", "customer_other_income_refund_new", "customer_other_income_refund_detail", "customer_other_income_refund_edit", "customer_other_income_refund_delete", "customer_other_income_refund_reverse_settlement", "customer_other_income_refund_void", "customer_other_income_refund_note")

    @app.get("/finance/receivables/pending-collections", endpoint="finance_receivable_pending_collections")
    @login_required
    def finance_receivable_pending_collections():
        return render_pending_collection_list(query_rows)

    @app.get("/finance/receivables/merged-collections", endpoint="finance_receivable_merged_collections")
    @login_required
    def finance_receivable_merged_collections():
        return render_merged_collection_records(query_rows)

    @app.get("/finance/receivable-bills", endpoint="finance_receivable_bills")
    @login_required
    def finance_receivable_bills():
        return render_receivable_bill_list(query_rows)

    def register_ap_payment_document_routes(payment_kind, list_endpoint, new_endpoint, detail_endpoint, edit_endpoint, delete_endpoint, reverse_endpoint, void_endpoint, note_endpoint):
        config = _ap_payment_config(payment_kind)

        @app.get(config["list_url"], endpoint=list_endpoint)
        @login_required
        def ap_payment_list(payment_kind=payment_kind):
            return render_supplier_payment_list(query_rows, payment_kind=payment_kind)

        @app.route(config["new_url"], methods=["GET", "POST"], endpoint=new_endpoint)
        @login_required
        def ap_payment_new(payment_kind=payment_kind):
            if request.method == "POST":
                def operation(cursor):
                    if not cursor:
                        return post_supplier_payment(query_one, query_rows, execute_db, execute_and_return, next_doc_no, log_action, payment_kind=payment_kind)
                    tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return = _transaction_callables(cursor)
                    tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
                    return post_supplier_payment(tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return, next_doc_no, tx_log_action, payment_kind=payment_kind)

                return _run_finance_funds_transaction(operation)
            return render_supplier_payment_entry(query_rows, payment_kind=payment_kind)

        @app.get(f"{config['detail_base']}/<int:payment_id>", endpoint=detail_endpoint)
        @login_required
        def ap_payment_detail(payment_id, payment_kind=payment_kind):
            return render_supplier_payment_detail(payment_id, query_one, query_rows, payment_kind=payment_kind)

        @app.route(f"{config['detail_base']}/<int:payment_id>/edit", methods=["GET", "POST"], endpoint=edit_endpoint)
        @login_required
        def ap_payment_edit(payment_id, payment_kind=payment_kind):
            config = _ap_payment_config(payment_kind)
            if request.method == "POST":
                def operation(cursor):
                    if not cursor:
                        return post_supplier_payment_edit(payment_id, query_one, query_rows, execute_db, log_action, payment_kind=payment_kind)
                    tx_query_one, tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
                    tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
                    return post_supplier_payment_edit(payment_id, tx_query_one, tx_query_rows, tx_execute_db, tx_log_action, payment_kind=payment_kind)

                return _run_finance_funds_transaction(operation)
            doc, settlements = _supplier_payment_edit_context(payment_id, query_one, query_rows, payment_kind)
            if not doc:
                flash(f"{config['label']}不存在。", "warning")
                return redirect(config["list_url"])
            if not _funds_action_flags(doc)["can_edit"]:
                flash(f"只有未核销的草稿{config['label']}可以编辑；已确认、已核销、已作废单据请走反核销或作废流程。", "warning")
                return redirect(f"{config['detail_base']}/{payment_id}")
            return render_supplier_payment_entry(query_rows, doc=doc, settlements=settlements, payment_kind=payment_kind)

        @app.post(f"{config['detail_base']}/<int:payment_id>/delete", endpoint=delete_endpoint)
        @login_required
        def ap_payment_delete(payment_id, payment_kind=payment_kind):
            def operation(cursor):
                if not cursor:
                    return post_supplier_payment_delete(payment_id, query_one, execute_db, log_action, payment_kind=payment_kind)
                tx_query_one, _tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
                tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
                return post_supplier_payment_delete(payment_id, tx_query_one, tx_execute_db, tx_log_action, payment_kind=payment_kind)

            return _run_finance_funds_transaction(operation)

        @app.post(f"{config['detail_base']}/<int:payment_id>/reverse-settlement", endpoint=reverse_endpoint)
        @login_required
        def ap_payment_reverse_settlement(payment_id, payment_kind=payment_kind):
            return post_supplier_payment_reverse_settlement(payment_id, query_one, execute_db, log_action, payment_kind=payment_kind)

        @app.post(f"{config['detail_base']}/<int:payment_id>/void", endpoint=void_endpoint)
        @login_required
        def ap_payment_void(payment_id, payment_kind=payment_kind):
            return post_supplier_payment_void(payment_id, query_one, execute_db, log_action, payment_kind=payment_kind)

        @app.post(f"{config['detail_base']}/<int:payment_id>/notes", endpoint=note_endpoint)
        @login_required
        def ap_payment_note(payment_id, payment_kind=payment_kind):
            config = _ap_payment_config(payment_kind)
            row = query_one("SELECT payment_no FROM supplier_payments WHERE id=%s AND COALESCE(payment_kind,'supplier_payment')=%s", (payment_id, payment_kind))
            if not row:
                flash(f"{config['label']}不存在。", "warning")
                return redirect(config["list_url"])
            note = (request.form.get("note") or "").strip()
            if not note:
                flash("请输入备注内容。", "warning")
                return redirect(f"{config['detail_base']}/{payment_id}")
            log_action(f"{config['label']}备注", row.get("payment_no"), note)
            flash("备注已保存。", "success")
            return redirect(f"{config['detail_base']}/{payment_id}")

    register_ap_payment_document_routes("supplier_payment", "supplier_payment_list", "supplier_payment_new", "supplier_payment_detail", "supplier_payment_edit", "supplier_payment_delete", "supplier_payment_reverse_settlement", "supplier_payment_void", "supplier_payment_note")
    register_ap_payment_document_routes("advance_payment", "supplier_advance_payment_list", "supplier_advance_payment_new", "supplier_advance_payment_detail", "supplier_advance_payment_edit", "supplier_advance_payment_delete", "supplier_advance_payment_reverse_settlement", "supplier_advance_payment_void", "supplier_advance_payment_note")
    register_ap_payment_document_routes("payment_refund", "supplier_payment_refund_list", "supplier_payment_refund_new", "supplier_payment_refund_detail", "supplier_payment_refund_edit", "supplier_payment_refund_delete", "supplier_payment_refund_reverse_settlement", "supplier_payment_refund_void", "supplier_payment_refund_note")
    register_ap_payment_document_routes("advance_refund", "supplier_advance_refund_list", "supplier_advance_refund_new", "supplier_advance_refund_detail", "supplier_advance_refund_edit", "supplier_advance_refund_delete", "supplier_advance_refund_reverse_settlement", "supplier_advance_refund_void", "supplier_advance_refund_note")
    register_ap_payment_document_routes("other_expense", "supplier_other_expense_list", "supplier_other_expense_new", "supplier_other_expense_detail", "supplier_other_expense_edit", "supplier_other_expense_delete", "supplier_other_expense_reverse_settlement", "supplier_other_expense_void", "supplier_other_expense_note")
    register_ap_payment_document_routes("other_expense_refund", "supplier_other_expense_refund_list", "supplier_other_expense_refund_new", "supplier_other_expense_refund_detail", "supplier_other_expense_refund_edit", "supplier_other_expense_refund_delete", "supplier_other_expense_refund_reverse_settlement", "supplier_other_expense_refund_void", "supplier_other_expense_refund_note")

    # 角色守卫由 enforce_high_risk_access_controls before_request 统一执行（admin/manager/finance）
    @app.get("/finance/receivable-payable", endpoint="finance_receivable_payable_workbench")
    @login_required
    def finance_receivable_payable_workbench():
        return render_receivable_payable_workbench(query_one, query_rows)

    # 蓝图标准路由别名：先复用现有成熟页面，避免建立平行表或破坏原业务入口。
    def register_finance_detail_alias(alias_base, target_base, endpoint_key, include_edit=True):
        @app.get(f"{alias_base}/<int:record_id>", endpoint=f"finance_{endpoint_key}_detail_alias")
        @login_required
        def finance_detail_alias(record_id, target_base=target_base):
            return redirect(f"{target_base}/{record_id}")

        if include_edit:
            @app.get(f"{alias_base}/<int:record_id>/edit", endpoint=f"finance_{endpoint_key}_edit_alias")
            @login_required
            def finance_edit_alias(record_id, target_base=target_base):
                return redirect(f"{target_base}/{record_id}/edit")

    finance_detail_aliases = [
        ("/finance/receivables", "/receivables", "receivables", False),
        ("/finance/receipts", "/customer-receipts", "receipts", True),
        ("/finance/advance-receipts", "/customer-advance-receipts", "advance_receipts", True),
        ("/finance/receipt-refunds", "/customer-receipt-refunds", "receipt_refunds", True),
        ("/finance/advance-receipt-refunds", "/customer-advance-refunds", "advance_receipt_refunds", True),
        ("/finance/other-income", "/customer-other-income", "other_income", True),
        ("/finance/other-income-refunds", "/customer-other-income-refunds", "other_income_refunds", True),
        ("/finance/payables", "/payables", "payables", False),
        ("/finance/payments", "/payments", "payments", True),
        ("/finance/advance-payments", "/supplier-advance-payments", "advance_payments", True),
        ("/finance/payment-refunds", "/supplier-payment-refunds", "payment_refunds", True),
        ("/finance/advance-payment-refunds", "/supplier-advance-refunds", "advance_payment_refunds", True),
        ("/finance/other-expenses", "/supplier-other-expenses", "other_expenses", True),
        ("/finance/other-expense-refunds", "/supplier-other-expense-refunds", "other_expense_refunds", True),
        ("/finance/sales-invoices", "/sales-invoices", "sales_invoices", True),
        ("/finance/purchase-invoices", "/purchase-invoices", "purchase_invoices", True),
    ]
    for alias_base, target_base, endpoint_key, include_edit in finance_detail_aliases:
        register_finance_detail_alias(alias_base, target_base, endpoint_key, include_edit)

    @app.get("/finance/receivables", endpoint="finance_receivables_standard")
    @login_required
    def finance_receivables_standard():
        return redirect("/receivables")

    @app.get("/finance/receipts", endpoint="finance_receipts_standard")
    @login_required
    def finance_receipts_standard():
        return redirect("/customer-receipts")

    @app.get("/finance/receipts/new", endpoint="finance_receipts_new_standard")
    @login_required
    def finance_receipts_new_standard():
        return redirect("/customer-receipts/new")

    @app.get("/finance/advance-receipts", endpoint="finance_advance_receipts_standard")
    @login_required
    def finance_advance_receipts_standard():
        return redirect("/customer-advance-receipts")

    @app.get("/finance/advance-receipts/new", endpoint="finance_advance_receipts_new_standard")
    @login_required
    def finance_advance_receipts_new_standard():
        return redirect("/customer-advance-receipts/new")

    @app.get("/finance/receipt-refunds", endpoint="finance_receipt_refunds_standard")
    @login_required
    def finance_receipt_refunds_standard():
        return redirect("/customer-receipt-refunds")

    @app.get("/finance/receipt-refunds/new", endpoint="finance_receipt_refunds_new_standard")
    @login_required
    def finance_receipt_refunds_new_standard():
        return redirect("/customer-receipt-refunds/new")

    @app.get("/finance/advance-receipt-refunds", endpoint="finance_advance_receipt_refunds_standard")
    @login_required
    def finance_advance_receipt_refunds_standard():
        return redirect("/customer-advance-refunds")

    @app.get("/finance/advance-receipt-refunds/new", endpoint="finance_advance_receipt_refunds_new_standard")
    @login_required
    def finance_advance_receipt_refunds_new_standard():
        return redirect("/customer-advance-refunds/new")

    @app.get("/finance/other-income", endpoint="finance_other_income_standard")
    @login_required
    def finance_other_income_standard():
        return redirect("/customer-other-income")

    @app.get("/finance/other-income/new", endpoint="finance_other_income_new_standard")
    @login_required
    def finance_other_income_new_standard():
        return redirect("/customer-other-income/new")

    @app.get("/finance/other-income-refunds", endpoint="finance_other_income_refunds_standard")
    @login_required
    def finance_other_income_refunds_standard():
        return redirect("/customer-other-income-refunds")

    @app.get("/finance/other-income-refunds/new", endpoint="finance_other_income_refunds_new_standard")
    @login_required
    def finance_other_income_refunds_new_standard():
        return redirect("/customer-other-income-refunds/new")

    @app.get("/finance/payables", endpoint="finance_payables_standard")
    @login_required
    def finance_payables_standard():
        return redirect("/payables")

    @app.get("/finance/payment-requests", endpoint="finance_payment_requests_standard")
    @login_required
    def finance_payment_requests_standard():
        return render_payment_request_statistics_report(query_rows)

    @app.get("/finance/sales-invoices", endpoint="finance_sales_invoices_standard")
    @login_required
    def finance_sales_invoices_standard():
        return redirect("/sales-invoices")

    @app.get("/finance/sales-invoices/new", endpoint="finance_sales_invoices_new_standard")
    @login_required
    def finance_sales_invoices_new_standard():
        return redirect("/sales-invoices/new")

    @app.get("/finance/purchase-invoices", endpoint="finance_purchase_invoices_standard")
    @login_required
    def finance_purchase_invoices_standard():
        return redirect("/purchase-invoices")

    @app.get("/finance/purchase-invoices/new", endpoint="finance_purchase_invoices_new_standard")
    @login_required
    def finance_purchase_invoices_new_standard():
        return redirect("/purchase-invoices/new")

    @app.get("/finance/payments", endpoint="finance_payments_standard")
    @login_required
    def finance_payments_standard():
        return redirect("/payments")

    @app.get("/finance/payments/new", endpoint="finance_payments_new_standard")
    @login_required
    def finance_payments_new_standard():
        return redirect("/payments/new")

    @app.get("/finance/advance-payments", endpoint="finance_advance_payments_standard")
    @login_required
    def finance_advance_payments_standard():
        return redirect("/supplier-advance-payments")

    @app.get("/finance/advance-payments/new", endpoint="finance_advance_payments_new_standard")
    @login_required
    def finance_advance_payments_new_standard():
        return redirect("/supplier-advance-payments/new")

    @app.get("/finance/payment-refunds", endpoint="finance_payment_refunds_standard")
    @login_required
    def finance_payment_refunds_standard():
        return redirect("/supplier-payment-refunds")

    @app.get("/finance/payment-refunds/new", endpoint="finance_payment_refunds_new_standard")
    @login_required
    def finance_payment_refunds_new_standard():
        return redirect("/supplier-payment-refunds/new")

    @app.get("/finance/advance-payment-refunds", endpoint="finance_advance_payment_refunds_standard")
    @login_required
    def finance_advance_payment_refunds_standard():
        return redirect("/supplier-advance-refunds")

    @app.get("/finance/advance-payment-refunds/new", endpoint="finance_advance_payment_refunds_new_standard")
    @login_required
    def finance_advance_payment_refunds_new_standard():
        return redirect("/supplier-advance-refunds/new")

    @app.get("/finance/other-expenses", endpoint="finance_other_expenses_standard")
    @login_required
    def finance_other_expenses_standard():
        return redirect("/supplier-other-expenses")

    @app.get("/finance/other-expenses/new", endpoint="finance_other_expenses_new_standard")
    @login_required
    def finance_other_expenses_new_standard():
        return redirect("/supplier-other-expenses/new")

    @app.get("/finance/other-expense-refunds", endpoint="finance_other_expense_refunds_standard")
    @login_required
    def finance_other_expense_refunds_standard():
        return redirect("/supplier-other-expense-refunds")

    @app.get("/finance/other-expense-refunds/new", endpoint="finance_other_expense_refunds_new_standard")
    @login_required
    def finance_other_expense_refunds_new_standard():
        return redirect("/supplier-other-expense-refunds/new")

    @app.get("/finance/bank-journal", endpoint="finance_bank_journal_standard")
    @login_required
    def finance_bank_journal_standard():
        return redirect("/finance/cash-bank/journal?account_type=bank")

    @app.get("/finance/cash-journal", endpoint="finance_cash_journal_standard")
    @login_required
    def finance_cash_journal_standard():
        return redirect("/finance/cash-bank/journal?account_type=cash")

    @app.route("/finance/period-close", methods=["GET", "POST"], endpoint="finance_period_close")
    @login_required
    def finance_period_close():
        if request.method == "POST":
            return post_finance_period_close(query_one, execute_db, log_action)
        return render_finance_period_close(query_one, query_rows, execute_db)

    @app.route("/finance/exchange-adjustment", methods=["GET", "POST"], endpoint="finance_exchange_adjustment")
    @login_required
    def finance_exchange_adjustment():
        if request.method == "POST":
            return post_finance_exchange_adjustment(query_one, query_rows, execute_db, execute_and_return, log_action)
        return render_finance_exchange_adjustment(query_one, query_rows)

    @app.get("/finance/exchange-adjustments", endpoint="finance_exchange_adjustment_list")
    @login_required
    def finance_exchange_adjustment_list():
        return render_finance_exchange_adjustment_list(query_rows)

    @app.post("/finance/exchange-adjustments/<int:adjustment_id>/audit", endpoint="finance_exchange_adjustment_audit")
    @login_required
    def finance_exchange_adjustment_audit(adjustment_id):
        return post_finance_exchange_adjustment_audit(adjustment_id, query_one, query_rows, execute_db, execute_and_return, log_action)

    @app.post("/finance/period-close/profit-loss-transfer", endpoint="profit_loss_transfer")
    @login_required
    def profit_loss_transfer():
        return post_profit_loss_transfer(query_one, query_rows, execute_db, execute_and_return, log_action)

    @app.get("/finance/financial-statements", endpoint="financial_statements")
    @login_required
    def financial_statements():
        return render_financial_statements(query_one, query_rows, execute_db)

    # ---- 往来账龄报表 ----
    @app.get("/finance/reports/aging", endpoint="finance_aging_report")
    @login_required
    def finance_aging_report():
        return render_aging_analysis(query_rows)

    @app.get("/finance/reports/aging-buckets", endpoint="finance_aging_buckets")
    @login_required
    def finance_aging_buckets():
        return render_aging_buckets_summary(query_rows)

    @app.get("/finance/reports/balance", endpoint="finance_partner_balance")
    @login_required
    def finance_partner_balance():
        return render_partner_balance_detail(query_rows)

    # ---- 会计总账查询 ----
    # ---- 往来核销、对账和智能收付款 ----
    @app.get("/finance/reports/receivable-detail", endpoint="finance_receivable_detail_report")
    @login_required
    def finance_receivable_detail_report():
        return render_receivable_detail_report(query_rows)

    @app.get("/finance/reports/payable-detail", endpoint="finance_payable_detail_report")
    @login_required
    def finance_payable_detail_report():
        return render_payable_detail_report(query_rows)

    @app.get("/finance/reports/receivable-summary", endpoint="finance_receivable_summary_report")
    @login_required
    def finance_receivable_summary_report():
        return render_receivable_summary_report(query_rows)

    @app.get("/finance/reports/payable-summary", endpoint="finance_payable_summary_report")
    @login_required
    def finance_payable_summary_report():
        return render_payable_summary_report(query_rows)

    @app.get("/finance/reports/payment-request-statistics", endpoint="finance_payment_request_statistics_report")
    @login_required
    def finance_payment_request_statistics_report():
        return render_payment_request_statistics_report(query_rows)

    @app.get("/finance/reports/receivable-warning", endpoint="finance_receivable_warning_report")
    @login_required
    def finance_receivable_warning_report():
        return render_receivable_warning_report(query_rows)

    @app.get("/finance/reports/payable-warning", endpoint="finance_payable_warning_report")
    @login_required
    def finance_payable_warning_report():
        return render_payable_warning_report(query_rows)

    @app.get("/finance/reports/bad-debt-reserve-balance", endpoint="finance_bad_debt_reserve_balance_report")
    @login_required
    def finance_bad_debt_reserve_balance_report():
        return render_bad_debt_reserve_balance_report(query_rows)

    @app.get("/finance/reports/enterprise-income-expense-detail", endpoint="finance_enterprise_income_expense_detail_report")
    @login_required
    def finance_enterprise_income_expense_detail_report():
        return render_enterprise_income_expense_detail_report(query_rows)

    @app.get("/finance/reports/account-income-expense-detail", endpoint="finance_account_income_expense_detail_report")
    @login_required
    def finance_account_income_expense_detail_report():
        return render_account_income_expense_detail_report(query_rows)

    @app.get("/finance/reports/other-income-expense-detail", endpoint="finance_other_income_expense_detail_report")
    @login_required
    def finance_other_income_expense_detail_report():
        return render_other_income_expense_detail_report(query_rows)

    @app.get("/finance/reports/account-balance", endpoint="finance_fund_account_balance_report")
    @login_required
    def finance_fund_account_balance_report():
        return render_fund_account_balance_report(query_rows)

    @app.get("/finance/reports/cash-bank-balance", endpoint="finance_cash_bank_balance_report")
    @login_required
    def finance_cash_bank_balance_report():
        return render_fund_account_balance_report(query_rows)

    @app.get("/finance/reports/cash-bank-transactions", endpoint="finance_cash_bank_transactions_report")
    @login_required
    def finance_cash_bank_transactions_report():
        return render_account_income_expense_detail_report(query_rows)

    @app.get("/finance/reports/credit-management", endpoint="finance_credit_management_report")
    @login_required
    def finance_credit_management_report():
        return render_credit_management_report(query_rows)

    @app.get("/finance/credit-management", endpoint="finance_credit_management")
    @login_required
    def finance_credit_management():
        return render_credit_management_report(query_rows)

    @app.get("/finance/reports/account-aging-analysis", endpoint="finance_account_aging_analysis_report")
    @login_required
    def finance_account_aging_analysis_report():
        return render_account_aging_analysis_report(query_rows)

    @app.get("/finance/reports/payment-flow-summary", endpoint="finance_payment_flow_summary_report")
    @login_required
    def finance_payment_flow_summary_report():
        return render_enterprise_income_expense_detail_report(query_rows)

    @app.get("/finance/reports/project-capital-occupation", endpoint="finance_project_capital_occupation_report")
    @login_required
    def finance_project_capital_occupation_report():
        return render_project_capital_occupation_report(query_rows)

    @app.get("/finance/settlement-schemes", endpoint="finance_settlement_schemes")
    @login_required
    def finance_settlement_schemes():
        return render_auto_settlement_schemes(query_rows)

    @app.get("/finance/settlement-runs", endpoint="finance_settlement_runs")
    @login_required
    def finance_settlement_runs():
        return render_auto_settlement_runs(query_rows)

    @app.get("/finance/manual-settlement", endpoint="finance_manual_settlement")
    @login_required
    def finance_manual_settlement():
        return render_manual_settlement_console(query_rows)

    @app.get("/finance/smart-collections", endpoint="finance_smart_collections")
    @login_required
    def finance_smart_collections():
        return render_smart_collection_queue(query_rows)

    @app.get("/finance/smart-payments", endpoint="finance_smart_payments")
    @login_required
    def finance_smart_payments():
        return render_smart_payment_queue(query_rows)

    @app.get("/finance/reports/customer-vendor-matching-statement", endpoint="finance_customer_vendor_matching_statement")
    @login_required
    def finance_customer_vendor_matching_statement():
        return render_counterparty_matching_statement(query_rows)

    @app.get("/finance/reports/statement-history", endpoint="finance_statement_history")
    @login_required
    def finance_statement_history():
        return render_statement_history(query_rows)

    @app.get("/finance/statement-templates", endpoint="finance_statement_templates")
    @login_required
    def finance_statement_templates():
        return render_statement_templates()

    @app.get("/finance/detail-ledger", endpoint="detail_ledger")
    @login_required
    def detail_ledger():
        return render_detail_ledger(query_rows, query_one)

    @app.route("/finance/opening-balances", methods=["GET", "POST"], endpoint="opening_balances")
    @login_required
    def opening_balances():
        if request.method == "POST":
            def operation(cursor):
                tx_query_one, _tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
                tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
                return post_opening_balances(tx_query_one, tx_execute_db, tx_log_action)
            return _run_finance_funds_transaction(operation)
        return render_opening_balances(query_rows, query_one, execute_db)

    @app.get("/finance/general-ledger", endpoint="general_ledger")
    @login_required
    def general_ledger():
        return render_general_ledger(query_rows, query_one)

    @app.get("/finance/account-balance", endpoint="account_balance_summary")
    @login_required
    def account_balance_summary():
        return render_account_balance_summary(query_rows, query_one)

    @app.get("/finance/trial-balance", endpoint="trial_balance")
    @login_required
    def trial_balance():
        return render_trial_balance(query_rows, query_one)

    # ---- 凭证路由 ----

    @app.route("/finance/cash-bank/accounts", methods=["GET", "POST"], endpoint="cash_bank_accounts")
    @login_required
    def cash_bank_accounts():
        if request.method == "POST":
            return post_cash_bank_account(execute_db, log_action)
        return render_cash_bank_accounts(query_rows, query_one)

    @app.get("/finance/cash-bank/journal", endpoint="cash_bank_journal")
    @login_required
    def cash_bank_journal():
        return render_cash_bank_journal(query_rows)

    # ---- 记账凭证 CRUD ----
    @app.get("/finance/vouchers", endpoint="finance_vouchers")
    @login_required
    def finance_vouchers():
        return render_voucher_list(query_rows)

    @app.get("/finance/vouchers/new", endpoint="finance_voucher_new")
    @login_required
    def finance_voucher_new():
        return render_voucher_form(query_rows, query_one, execute_db)

    @app.get("/finance/vouchers/<int:voucher_id>", endpoint="finance_voucher_detail")
    @login_required
    def finance_voucher_detail(voucher_id):
        return render_voucher_form(query_rows, query_one, execute_db, voucher_id)

    @app.get("/finance/vouchers/<int:voucher_id>/edit", endpoint="finance_voucher_edit")
    @login_required
    def finance_voucher_edit(voucher_id):
        return render_voucher_form(query_rows, query_one, execute_db, voucher_id)

    @app.post("/finance/vouchers/save", endpoint="finance_voucher_save")
    @login_required
    def finance_voucher_save():
        def operation(cursor):
            tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return = _transaction_callables(cursor)
            tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
            return save_voucher(tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return, next_doc_no, tx_log_action)

        return _run_finance_funds_transaction(operation)

    @app.post("/finance/vouchers/<int:voucher_id>/save", endpoint="finance_voucher_save_edit")
    @login_required
    def finance_voucher_save_edit(voucher_id):
        def operation(cursor):
            tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return = _transaction_callables(cursor)
            tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
            return save_voucher(tx_query_one, tx_query_rows, tx_execute_db, tx_execute_and_return, next_doc_no, tx_log_action, voucher_id)

        return _run_finance_funds_transaction(operation)

    @app.post("/finance/vouchers/<int:voucher_id>/post", endpoint="finance_voucher_post")
    @login_required
    def finance_voucher_post(voucher_id):
        def operation(cursor):
            tx_query_one, tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
            tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
            return post_voucher_to_gl(voucher_id, tx_query_one, tx_query_rows, tx_execute_db, tx_log_action)

        return _run_finance_funds_transaction(operation)

    @app.post("/finance/vouchers/<int:voucher_id>/unreview", endpoint="finance_voucher_unreview")
    @login_required
    def finance_voucher_unreview(voucher_id):
        return unreview_voucher(voucher_id, query_one, execute_db, log_action)

    @app.post("/finance/vouchers/<int:voucher_id>/reverse-post", endpoint="finance_voucher_reverse_post")
    @login_required
    def finance_voucher_reverse_post(voucher_id):
        def operation(cursor):
            tx_query_one, _tx_query_rows, tx_execute_db, _tx_execute_and_return = _transaction_callables(cursor)
            tx_log_action = lambda action, target="", remark="": _finance_transaction_log_action(tx_execute_db, action, target, remark)
            return reverse_post_voucher(voucher_id, tx_query_one, tx_execute_db, tx_log_action)

        return _run_finance_funds_transaction(operation)

    @app.post("/finance/vouchers/<int:voucher_id>/void", endpoint="finance_voucher_void")
    @login_required
    def finance_voucher_void(voucher_id):
        return void_voucher(voucher_id, query_one, execute_db, log_action)

    @app.get("/api/accounts/search", endpoint="api_accounts_search")
    @login_required
    def api_accounts_search():
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"accounts": []})
        accounts = query_rows(
            "SELECT id, code, name, account_type FROM chart_of_accounts WHERE status='active' AND (code ILIKE %s OR name ILIKE %s) ORDER BY code LIMIT 20",
            (f"%{q}%", f"%{q}%"),
        )
        return jsonify({"accounts": accounts})

    @app.get("/api/accounts/all", endpoint="api_accounts_all")
    @login_required
    def api_accounts_all():
        accounts = query_rows(
            "SELECT id, code, name, account_type FROM chart_of_accounts WHERE status='active' ORDER BY code"
        )
        return jsonify({"accounts": accounts})
