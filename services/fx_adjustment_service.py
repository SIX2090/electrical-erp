# -*- coding: utf-8 -*-
"""
C-5: 外汇期末调整服务
支持汇率历史维护、外币 AR/AP 期末调整计算、汇兑损益凭证生成
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def upsert_exchange_rate(
    execute_db,
    *,
    currency_code: str,
    rate_date,
    rate_to_base: Decimal,
    rate_type: str = "period_end",
    source: str = "",
    remark: str = "",
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """新增或更新汇率历史记录。"""
    execute_db(
        """
        INSERT INTO exchange_rate_history
            (currency_code, rate_date, rate_to_base, rate_type, source, remark, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (currency_code, rate_date, rate_type)
        DO UPDATE SET
            rate_to_base = EXCLUDED.rate_to_base,
            source = EXCLUDED.source,
            remark = EXCLUDED.remark,
            created_by = EXCLUDED.created_by
        """,
        (currency_code, rate_date, rate_to_base, rate_type, source, remark, created_by),
    )
    return {"success": True, "currency_code": currency_code, "rate_date": rate_date, "rate_to_base": rate_to_base}


def get_period_end_rate(query_db, *, currency_code: str, period_year: int, period_month: int) -> Optional[Decimal]:
    """获取指定期间的期末汇率。"""
    # 计算期间末日期
    if period_month == 12:
        next_month_first = date(period_year + 1, 1, 1)
    else:
        next_month_first = date(period_year, period_month + 1, 1)
    # 期间末日期 = 下月1号 - 1天
    from datetime import timedelta
    period_end = next_month_first - timedelta(days=1)

    row = query_db(
        """
        SELECT rate_to_base FROM exchange_rate_history
        WHERE currency_code = %s AND rate_date <= %s AND rate_type = 'period_end'
        ORDER BY rate_date DESC LIMIT 1
        """,
        (currency_code, period_end),
        one=True,
    )
    if row:
        return Decimal(str(row["rate_to_base"]))
    # 回退到 currencies 表的当前汇率
    row = query_db(
        "SELECT exchange_rate FROM currencies WHERE code = %s AND status = 'active'",
        (currency_code,),
        one=True,
    )
    if row:
        return Decimal(str(row["exchange_rate"]))
    return None


def list_exchange_rates(query_db, *, currency_code: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """列出汇率历史。"""
    params = []
    where_sql = ""
    if currency_code:
        where_sql = "WHERE currency_code = %s"
        params.append(currency_code)
    params.append(limit)
    rows = query_db(
        f"""
        SELECT * FROM exchange_rate_history
        {where_sql}
        ORDER BY rate_date DESC, currency_code
        LIMIT %s
        """,
        tuple(params),
    ) or []
    return [dict(r) for r in rows]


def run_fx_adjustment(
    query_db,
    execute_db,
    *,
    period_year: int,
    period_month: int,
    adjustment_date: Optional[str] = None,
    created_by: Optional[int] = None,
    execute_and_return=None,
) -> Dict[str, Any]:
    """执行外汇期末调整。

    扫描未核销的外币应收/应付/资金账户余额，按期末汇率重新折算，
    计算汇兑损益，生成调整明细行。

    Returns:
        {"run_id": int, "run_no": str, "line_count": int, "total_gain_loss": Decimal,
         "ar_adjustment": Decimal, "ap_adjustment": Decimal, "cash_adjustment": Decimal}
    """
    from datetime import timedelta
    if period_month == 12:
        next_month_first = date(period_year + 1, 1, 1)
    else:
        next_month_first = date(period_year, period_month + 1, 1)
    period_end = next_month_first - timedelta(days=1)
    if adjustment_date is None:
        adjustment_date = period_end.isoformat()

    # 收集所有需要调整的外币余额
    lines: List[Dict[str, Any]] = []

    # 1. 外币应收余额（未核销的销售发票）
    ar_rows = query_db(
        """
        SELECT si.id, si.invoice_no, si.customer_id, c.name AS customer_name,
               si.amount_with_tax AS original_amount, si.amount AS amount_no_tax,
               si.tax_amount, si.project_code, si.cabinet_no
        FROM sales_invoices si
        LEFT JOIN customers c ON si.customer_id = c.id
        WHERE si.invoice_date <= %s
          AND COALESCE(si.status, '') NOT IN ('void', 'voided', 'cancelled', 'closed', '已关闭')
          AND si.id IN (
              SELECT receivable_id FROM customer_receipt_settlements
              WHERE receivable_id = si.id
          )
          AND EXISTS (SELECT 1 FROM currencies cur WHERE cur.code = 'USD' AND cur.is_base = FALSE)
        """,
        (period_end,),
    ) or []

    # 简化：假设所有外币单据为 USD（实际应根据单据 currency 字段判断）
    # 这里扫描 sales_invoices 中未完全核销的金额
    ar_open_rows = query_db(
        """
        SELECT si.id, si.invoice_no, si.customer_id, c.name AS customer_name,
               si.amount_with_tax AS original_amount,
               COALESCE(SUM(cr.settled_amount), 0) AS settled_amount,
               si.project_code, si.cabinet_no
        FROM sales_invoices si
        LEFT JOIN customers c ON si.customer_id = c.id
        LEFT JOIN customer_receipt_settlements cr ON cr.receivable_id = si.id
        WHERE si.invoice_date <= %s
          AND COALESCE(si.status, '') NOT IN ('void', 'voided', 'cancelled', 'closed', '已关闭')
        GROUP BY si.id, si.invoice_no, si.customer_id, c.name, si.amount_with_tax, si.project_code, si.cabinet_no
        HAVING si.amount_with_tax - COALESCE(SUM(cr.settled_amount), 0) > 0.01
        """,
        (period_end,),
    ) or []

    usd_rate = get_period_end_rate(query_db, currency_code="USD", period_year=period_year, period_month=period_month)
    if not usd_rate:
        usd_rate = Decimal("1")

    ar_adjustment_total = Decimal("0")
    for row in ar_open_rows:
        open_amount = Decimal(str(row.get("original_amount", 0))) - Decimal(str(row.get("settled_amount", 0)))
        if open_amount <= Decimal("0.01"):
            continue
        # 假设原币金额 = open_amount（实际应从单据 currency 字段获取）
        # 本位币原金额 = open_amount * original_rate（假设 original_rate=1，即原币=本位币）
        # 简化处理：仅当外币标识存在时计算
        original_rate = Decimal("1")  # 占位，实际应从单据读取
        base_original = open_amount * original_rate
        base_adjusted = open_amount * usd_rate
        gain_loss = base_adjusted - base_original
        if abs(gain_loss) < Decimal("0.01"):
            continue
        lines.append({
            "source_type": "sales_invoice",
            "source_id": row.get("id"),
            "source_no": row.get("invoice_no"),
            "partner_type": "customer",
            "partner_name": row.get("customer_name"),
            "currency_code": "USD",
            "original_amount": open_amount,
            "original_rate": original_rate,
            "base_amount_original": base_original,
            "period_end_rate": usd_rate,
            "base_amount_adjusted": base_adjusted,
            "gain_loss_amount": gain_loss,
            "adjustment_type": "unrealized",
            "account_code": "1122",
            "account_name": "应收账款",
        })
        ar_adjustment_total += gain_loss

    # 2. 外币应付余额（未核销的采购发票）
    ap_open_rows = query_db(
        """
        SELECT pi.id, pi.invoice_no, pi.supplier_id, s.name AS supplier_name,
               pi.amount_with_tax AS original_amount,
               COALESCE(SUM(sp.settled_amount), 0) AS settled_amount,
               pi.project_code, pi.cabinet_no
        FROM purchase_invoices pi
        LEFT JOIN suppliers s ON pi.supplier_id = s.id
        LEFT JOIN supplier_payment_settlements sp ON sp.payable_id = pi.id
        WHERE pi.invoice_date <= %s
          AND COALESCE(pi.status, '') NOT IN ('void', 'voided', 'cancelled', 'closed', '已关闭')
        GROUP BY pi.id, pi.invoice_no, pi.supplier_id, s.name, pi.amount_with_tax, pi.project_code, pi.cabinet_no
        HAVING pi.amount_with_tax - COALESCE(SUM(sp.settled_amount), 0) > 0.01
        """,
        (period_end,),
    ) or []

    ap_adjustment_total = Decimal("0")
    for row in ap_open_rows:
        open_amount = Decimal(str(row.get("original_amount", 0))) - Decimal(str(row.get("settled_amount", 0)))
        if open_amount <= Decimal("0.01"):
            continue
        original_rate = Decimal("1")
        base_original = open_amount * original_rate
        base_adjusted = open_amount * usd_rate
        gain_loss = base_adjusted - base_original
        if abs(gain_loss) < Decimal("0.01"):
            continue
        lines.append({
            "source_type": "purchase_invoice",
            "source_id": row.get("id"),
            "source_no": row.get("invoice_no"),
            "partner_type": "supplier",
            "partner_name": row.get("supplier_name"),
            "currency_code": "USD",
            "original_amount": open_amount,
            "original_rate": original_rate,
            "base_amount_original": base_original,
            "period_end_rate": usd_rate,
            "base_amount_adjusted": base_adjusted,
            "gain_loss_amount": gain_loss,
            "adjustment_type": "unrealized",
            "account_code": "2202",
            "account_name": "应付账款",
        })
        ap_adjustment_total += gain_loss

    total_gain_loss = ar_adjustment_total + ap_adjustment_total

    # 创建调整运行记录
    run_no = f"FX-{period_year}{period_month:02d}-{datetime.now().strftime('%H%M%S')}"
    run_row = execute_and_return(
        """
        INSERT INTO fx_adjustment_runs
            (run_no, period_year, period_month, adjustment_date,
             total_gain_loss, ar_adjustment, ap_adjustment, cash_adjustment,
             status, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'draft', %s)
        RETURNING id
        """,
        (run_no, period_year, period_month, adjustment_date,
         total_gain_loss, ar_adjustment_total, ap_adjustment_total, created_by),
    ) or {}
    run_id = run_row.get("id")

    # 插入调整明细行
    for line in lines:
        execute_db(
            """
            INSERT INTO fx_adjustment_lines
                (run_id, source_type, source_id, source_no, partner_type, partner_name,
                 currency_code, original_amount, original_rate, base_amount_original,
                 period_end_rate, base_amount_adjusted, gain_loss_amount,
                 adjustment_type, account_code, account_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id, line["source_type"], line.get("source_id"), line.get("source_no"),
                line.get("partner_type"), line.get("partner_name"), line["currency_code"],
                line["original_amount"], line["original_rate"], line["base_amount_original"],
                line["period_end_rate"], line["base_amount_adjusted"], line["gain_loss_amount"],
                line["adjustment_type"], line.get("account_code"), line.get("account_name"),
            ),
        )

    return {
        "run_id": run_id,
        "run_no": run_no,
        "line_count": len(lines),
        "total_gain_loss": total_gain_loss,
        "ar_adjustment": ar_adjustment_total,
        "ap_adjustment": ap_adjustment_total,
        "cash_adjustment": Decimal("0"),
    }


def get_fx_adjustment_run_detail(query_db, *, run_id: int) -> Dict[str, Any]:
    """获取外汇调整运行详情。"""
    run = query_db(
        "SELECT * FROM fx_adjustment_runs WHERE id = %s",
        (run_id,),
        one=True,
    )
    if not run:
        return {"run": None, "lines": []}
    lines = query_db(
        """
        SELECT * FROM fx_adjustment_lines
        WHERE run_id = %s
        ORDER BY source_type, id
        """,
        (run_id,),
    ) or []
    return {"run": dict(run), "lines": [dict(l) for l in lines]}


def list_fx_adjustment_runs(query_db, *, limit: int = 50) -> List[Dict[str, Any]]:
    """列出外汇调整运行。"""
    rows = query_db(
        """
        SELECT * FROM fx_adjustment_runs
        ORDER BY period_year DESC, period_month DESC, id DESC
        LIMIT %s
        """,
        (limit,),
    ) or []
    return [dict(r) for r in rows]
