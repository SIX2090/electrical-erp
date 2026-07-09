# -*- coding: utf-8 -*-
"""
C-2: 银行对账单导入与匹配服务
支持 CSV 导入、自动匹配银行日记账、人工勾选
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def import_bank_statement_lines(
    query_db,
    execute_db,
    *,
    account_id: int,
    statement_date,
    rows: List[Dict[str, Any]],
    source_file: str = "",
    imported_by: Optional[int] = None,
    opening_balance: Decimal = Decimal("0"),
    closing_balance: Decimal = Decimal("0"),
) -> Dict[str, Any]:
    """导入银行对账单明细行，创建 bank_statements + bank_statement_lines 记录。

    Args:
        rows: 每行含 transaction_date, amount, direction, counterparty_name,
              counterparty_account, counterparty_bank, summary, bank_reference

    Returns:
        {"statement_id": int, "line_count": int, "total_deposits": Decimal,
         "total_withdrawals": Decimal}
    """
    if not rows:
        return {"statement_id": None, "line_count": 0, "total_deposits": 0, "total_withdrawals": 0}

    period_year = None
    period_month = None
    if statement_date:
        if isinstance(statement_date, str):
            try:
                parsed = datetime.strptime(statement_date[:10], "%Y-%m-%d").date()
            except ValueError:
                parsed = date.today()
        else:
            parsed = statement_date
        period_year = parsed.year
        period_month = parsed.month

    total_deposits = Decimal("0")
    total_withdrawals = Decimal("0")
    for row in rows:
        amount = _to_decimal(row.get("amount"))
        if row.get("direction") == "in":
            total_deposits += amount
        else:
            total_withdrawals += amount

    stmt_row = execute_db(
        """
        INSERT INTO bank_statements
            (statement_no, account_id, statement_date, period_year, period_month,
             opening_balance, closing_balance, total_deposits, total_withdrawals,
             status, source_file, imported_by, imported_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'imported', %s, %s, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            _generate_statement_no(query_db, statement_date),
            account_id,
            statement_date,
            period_year,
            period_month,
            opening_balance,
            closing_balance,
            total_deposits,
            total_withdrawals,
            source_file,
            imported_by,
        ),
    ) or {}
    statement_id = stmt_row.get("id")
    if not statement_id:
        return {"statement_id": None, "line_count": 0, "total_deposits": 0, "total_withdrawals": 0}

    for idx, row in enumerate(rows, start=1):
        txn_date = row.get("transaction_date") or statement_date
        amount = _to_decimal(row.get("amount"))
        direction = row.get("direction") or ("in" if amount >= 0 else "out")
        execute_db(
            """
            INSERT INTO bank_statement_lines
                (statement_id, line_no, transaction_date, amount, direction,
                 counterparty_name, counterparty_account, counterparty_bank,
                 summary, bank_reference, match_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'unmatched')
            """,
            (
                statement_id,
                idx,
                txn_date,
                amount,
                direction,
                row.get("counterparty_name"),
                row.get("counterparty_account"),
                row.get("counterparty_bank"),
                row.get("summary"),
                row.get("bank_reference"),
            ),
        )

    return {
        "statement_id": statement_id,
        "line_count": len(rows),
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
    }


def _generate_statement_no(query_db, statement_date) -> str:
    """生成银行对账单号，格式 BS-YYYYMMDD-NNN，NNN 为当天序号。"""
    if statement_date:
        if isinstance(statement_date, str):
            try:
                parsed = datetime.strptime(statement_date[:10], "%Y-%m-%d").date()
            except ValueError:
                parsed = date.today()
        else:
            parsed = statement_date
    else:
        parsed = date.today()
    date_str = parsed.strftime("%Y%m%d")
    prefix = f"BS-{date_str}-"
    row = query_db(
        "SELECT statement_no FROM bank_statements WHERE statement_no LIKE %s ORDER BY statement_no DESC LIMIT 1",
        (prefix + "%",),
        one=True,
    )
    seq = 1
    if row and row.get("statement_no"):
        try:
            tail = row["statement_no"].rsplit("-", 1)[-1]
            seq = int(tail) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:03d}"


def auto_match_statement_lines(query_db, execute_db, *, statement_id: int, matched_by: Optional[int] = None) -> Dict[str, Any]:
    """自动匹配银行对账单行与银行日记账记录。

    匹配规则（按优先级）：
    1. 金额 + 方向 + 日期精确匹配
    2. 金额 + 方向匹配（日期容差 3 天）
    3. 金额 + 方向 + 对方名称模糊匹配

    Returns:
        {"matched": int, "unmatched": int, "details": list}
    """
    lines = query_db(
        """
        SELECT id, line_no, transaction_date, amount, direction,
               counterparty_name, summary
        FROM bank_statement_lines
        WHERE statement_id = %s AND match_status = 'unmatched'
        ORDER BY line_no
        """,
        (statement_id,),
    ) or []

    matched_count = 0
    unmatched_count = 0
    details = []

    for line in lines:
        line_id = line["id"]
        amount = _to_decimal(line.get("amount"))
        direction = line.get("direction")
        txn_date = line.get("transaction_date")

        # 规则 1: 金额 + 方向 + 日期精确匹配
        journal = query_db(
            """
            SELECT j.id, j.entry_date, j.amount, j.direction, j.summary,
                   j.partner_name
            FROM cash_bank_journal_entries j
            WHERE j.account_id = (SELECT account_id FROM bank_statements WHERE id = %s)
              AND j.amount = %s
              AND j.direction = %s
              AND j.entry_date = %s
              AND j.status = 'confirmed'
              AND NOT EXISTS (
                  SELECT 1 FROM bank_statement_lines bsl
                  WHERE bsl.matched_journal_id = j.id
                    AND bsl.match_status = 'matched'
              )
            LIMIT 1
            """,
            (statement_id, amount, direction, txn_date),
        )
        match_method = "exact_amount_date"

        # 规则 2: 金额 + 方向 + 日期容差 3 天
        if not journal:
            journal = query_db(
                """
                SELECT j.id, j.entry_date, j.amount, j.direction, j.summary,
                       j.partner_name
                FROM cash_bank_journal_entries j
                WHERE j.account_id = (SELECT account_id FROM bank_statements WHERE id = %s)
                  AND j.amount = %s
                  AND j.direction = %s
                  AND j.status = 'confirmed'
                  AND ABS(j.entry_date - %s) <= 3
                  AND NOT EXISTS (
                      SELECT 1 FROM bank_statement_lines bsl
                      WHERE bsl.matched_journal_id = j.id
                        AND bsl.match_status = 'matched'
                  )
                ORDER BY ABS(j.entry_date - %s)
                LIMIT 1
                """,
                (statement_id, amount, direction, txn_date, txn_date),
            )
            match_method = "amount_date_tolerance"

        # 规则 3: 金额 + 方向 + 对方名称模糊匹配
        if not journal and line.get("counterparty_name"):
            journal = query_db(
                """
                SELECT j.id, j.entry_date, j.amount, j.direction, j.summary,
                       j.partner_name
                FROM cash_bank_journal_entries j
                WHERE j.account_id = (SELECT account_id FROM bank_statements WHERE id = %s)
                  AND j.amount = %s
                  AND j.direction = %s
                  AND j.status = 'confirmed'
                  AND j.partner_name ILIKE %s
                  AND NOT EXISTS (
                      SELECT 1 FROM bank_statement_lines bsl
                      WHERE bsl.matched_journal_id = j.id
                        AND bsl.match_status = 'matched'
                  )
                LIMIT 1
                """,
                (statement_id, amount, direction, f"%{line['counterparty_name']}%"),
            )
            match_method = "amount_partner_name"

        if journal:
            j = journal[0] if isinstance(journal, list) else journal
            execute_db(
                """
                UPDATE bank_statement_lines
                SET match_status = 'matched',
                    matched_journal_id = %s,
                    matched_at = CURRENT_TIMESTAMP,
                    matched_by = %s,
                    match_method = %s,
                    match_score = 100.0
                WHERE id = %s
                """,
                (j["id"], matched_by, match_method, line_id),
            )
            matched_count += 1
            details.append({
                "line_id": line_id,
                "line_no": line.get("line_no"),
                "journal_id": j["id"],
                "method": match_method,
                "amount": amount,
            })
        else:
            unmatched_count += 1

    return {"matched": matched_count, "unmatched": unmatched_count, "details": details}


def manual_match_line(query_db, execute_db, *, line_id: int, journal_id: int, matched_by: Optional[int] = None) -> Dict[str, Any]:
    """人工勾选匹配单行。"""
    line = query_db(
        "SELECT id, statement_id FROM bank_statement_lines WHERE id = %s",
        (line_id,),
        one=True,
    )
    if not line:
        return {"success": False, "message": "对账单行不存在"}

    journal = query_db(
        "SELECT id FROM cash_bank_journal_entries WHERE id = %s AND status = 'confirmed'",
        (journal_id,),
        one=True,
    )
    if not journal:
        return {"success": False, "message": "银行日记账记录不存在或未确认"}

    # 检查该日记账是否已被其他行匹配
    existing = query_db(
        "SELECT id FROM bank_statement_lines WHERE matched_journal_id = %s AND match_status = 'matched' AND id != %s",
        (journal_id, line_id),
        one=True,
    )
    if existing:
        return {"success": False, "message": "该日记账记录已被其他对账单行匹配"}

    execute_db(
        """
        UPDATE bank_statement_lines
        SET match_status = 'matched',
            matched_journal_id = %s,
            matched_at = CURRENT_TIMESTAMP,
            matched_by = %s,
            match_method = 'manual',
            match_score = 100.0
        WHERE id = %s
        """,
        (journal_id, matched_by, line_id),
    )
    return {"success": True, "message": "匹配成功"}


def unmatch_line(execute_db, *, line_id: int) -> Dict[str, Any]:
    """取消匹配。"""
    execute_db(
        """
        UPDATE bank_statement_lines
        SET match_status = 'unmatched',
            matched_journal_id = NULL,
            matched_at = NULL,
            matched_by = NULL,
            match_method = NULL,
            match_score = NULL
        WHERE id = %s
        """,
        (line_id,),
    )
    return {"success": True, "message": "已取消匹配"}


def get_statement_detail(query_db, *, statement_id: int) -> Dict[str, Any]:
    """获取对账单详情及匹配汇总。"""
    stmt = query_db(
        """
        SELECT bs.*, cba.account_name, cba.account_code, cba.bank_name,
               cba.bank_account_no
        FROM bank_statements bs
        JOIN cash_bank_accounts cba ON bs.account_id = cba.id
        WHERE bs.id = %s
        """,
        (statement_id,),
        one=True,
    )
    if not stmt:
        return {"statement": None, "lines": [], "summary": {}}

    lines = query_db(
        """
        SELECT bsl.*,
               j.entry_no AS journal_entry_no,
               j.source_type AS journal_source_type,
               j.source_no AS journal_source_no,
               j.summary AS journal_summary,
               j.partner_name AS journal_partner_name
        FROM bank_statement_lines bsl
        LEFT JOIN cash_bank_journal_entries j ON bsl.matched_journal_id = j.id
        WHERE bsl.statement_id = %s
        ORDER BY bsl.line_no
        """,
        (statement_id,),
    ) or []

    matched_lines = [l for l in lines if l.get("match_status") == "matched"]
    unmatched_lines = [l for l in lines if l.get("match_status") == "unmatched"]
    matched_amount = sum(_to_decimal(l.get("amount")) for l in matched_lines)
    unmatched_amount = sum(_to_decimal(l.get("amount")) for l in unmatched_lines)

    return {
        "statement": dict(stmt),
        "lines": [dict(l) for l in lines],
        "summary": {
            "total_lines": len(lines),
            "matched": len(matched_lines),
            "unmatched": len(unmatched_lines),
            "matched_amount": matched_amount,
            "unmatched_amount": unmatched_amount,
            "match_rate": (len(matched_lines) / len(lines) * 100) if lines else 0,
        },
    }


def list_bank_statements(query_db, *, account_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """列出银行对账单。"""
    params = []
    where_clauses = []
    if account_id:
        where_clauses.append("bs.account_id = %s")
        params.append(account_id)
    if status:
        where_clauses.append("bs.status = %s")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(limit)
    rows = query_db(
        f"""
        SELECT bs.id, bs.statement_no, bs.statement_date, bs.period_year,
               bs.period_month, bs.opening_balance, bs.closing_balance,
               bs.total_deposits, bs.total_withdrawals, bs.status,
               bs.source_file, bs.imported_at,
               cba.account_name, cba.account_code, cba.bank_account_no,
               (SELECT COUNT(*) FROM bank_statement_lines bsl WHERE bsl.statement_id = bs.id) AS total_lines,
               (SELECT COUNT(*) FROM bank_statement_lines bsl WHERE bsl.statement_id = bs.id AND bsl.match_status = 'matched') AS matched_lines
        FROM bank_statements bs
        JOIN cash_bank_accounts cba ON bs.account_id = cba.id
        {where_sql}
        ORDER BY bs.statement_date DESC, bs.id DESC
        LIMIT %s
        """,
        tuple(params),
    ) or []
    return [dict(r) for r in rows]


def list_unmatched_journal_entries(query_db, *, account_id: int, line_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """列出未匹配的银行日记账记录，供人工勾选。"""
    rows = query_db(
        """
        SELECT j.id, j.entry_no, j.entry_date, j.amount, j.direction,
               j.source_type, j.source_no, j.summary, j.partner_name
        FROM cash_bank_journal_entries j
        WHERE j.account_id = %s
          AND j.status = 'confirmed'
          AND NOT EXISTS (
              SELECT 1 FROM bank_statement_lines bsl
              WHERE bsl.matched_journal_id = j.id
                AND bsl.match_status = 'matched'
                AND (%s IS NULL OR bsl.id != %s)
          )
        ORDER BY j.entry_date DESC, j.id DESC
        LIMIT %s
        """,
        (account_id, line_id, line_id, limit),
    ) or []
    return [dict(r) for r in rows]


def _to_decimal(value, default=Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return default
