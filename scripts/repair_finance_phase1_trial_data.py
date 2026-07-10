import sys
from datetime import date
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import get_db_config
from services.app_runtime import connect_db


RECEIPT_NO = "TRIAL-RECEIPT-PJGT-001"
ENTRY_NO = "TRIAL-CASHBANK-PJGT-001"
SETTLEMENT_AMOUNT = Decimal("1000.00")


def one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_posted_auto_voucher(cur, source_type, source_id, source_no, doc_date, amount):
    existing = one(
        cur,
        """
        SELECT id
        FROM vouchers
        WHERE source_type=%s
          AND source_id=%s
          AND COALESCE(auto_generated,FALSE)=TRUE
          AND status='posted'
        """,
        (source_type, source_id),
    )
    if existing:
        return existing["id"]
    voucher_no = f"AUTO-TRIAL-{source_type.upper()}-{source_id}"
    cur.execute(
        """
        INSERT INTO vouchers
            (voucher_no, voucher_type, date, voucher_date, period_year, period_month,
             source_type, source_id, source_no, auto_generated, status,
             total_debit, total_credit, summary, created_at, updated_at, posted_at)
        VALUES
            (%s, 'auto', %s, %s, EXTRACT(YEAR FROM %s::date)::int, EXTRACT(MONTH FROM %s::date)::int,
             %s, %s, %s, TRUE, 'posted',
             %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            voucher_no,
            doc_date,
            doc_date,
            doc_date,
            doc_date,
            source_type,
            source_id,
            source_no,
            amount,
            amount,
            f"Trial posted auto voucher for {source_type} {source_no}",
        ),
    )
    return cur.fetchone()["id"]


def ensure_receipt_flow(cur):
    receivable = one(
        cur,
        """
        SELECT id, customer_id, source_no, balance, project_code, cabinet_no
        FROM customer_receivables
        WHERE COALESCE(balance,0) > 0
        ORDER BY
          CASE WHEN project_code='PJ-GT-TRIAL-20260526-001' THEN 0 ELSE 1 END,
          id DESC
        LIMIT 1
        """,
    )
    if not receivable:
        raise RuntimeError("no open customer receivable is available for trial receipt flow")
    account = one(
        cur,
        "SELECT id, account_name, current_balance FROM cash_bank_accounts ORDER BY id LIMIT 1",
    )
    if not account:
        raise RuntimeError("no cash/bank account is available for trial receipt flow")

    amount = min(SETTLEMENT_AMOUNT, Decimal(str(receivable["balance"] or "0")))
    receipt = one(cur, "SELECT id, amount FROM customer_receipts WHERE receipt_no=%s", (RECEIPT_NO,))
    if receipt:
        receipt_id = receipt["id"]
    else:
        cur.execute(
            """
            INSERT INTO customer_receipts
                (receipt_no, receipt_date, customer_id, amount, payment_method, bank_account,
                 remark, source_type, source_id, source_no, receivable_id, project_code,
                 cabinet_no, status, unapplied_amount, created_at)
            VALUES
                (%s, CURRENT_DATE, %s, %s, 'bank', %s,
                 'Trial first-machine receipt settlement sample', 'customer_receivable',
                 %s, %s, %s, %s, %s, 'confirmed', 0, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                RECEIPT_NO,
                receivable["customer_id"],
                amount,
                account["account_name"],
                receivable["id"],
                receivable["source_no"],
                receivable["id"],
                receivable["project_code"],
                receivable["cabinet_no"],
            ),
        )
        receipt_id = cur.fetchone()["id"]

    cur.execute(
        """
        INSERT INTO customer_receipt_settlements (receipt_id, receivable_id, applied_amount)
        VALUES (%s, %s, %s)
        ON CONFLICT (receipt_id, receivable_id)
        DO UPDATE SET applied_amount=EXCLUDED.applied_amount
        """,
        (receipt_id, receivable["id"], amount),
    )
    cur.execute(
        """
        UPDATE customer_receivables
        SET received_amount=COALESCE(received_amount,0) + %s,
            balance=GREATEST(COALESCE(balance,0) - %s, 0),
            status=CASE WHEN GREATEST(COALESCE(balance,0) - %s, 0) <= 0 THEN 'settled' ELSE COALESCE(status,'open') END
        WHERE id=%s
          AND NOT EXISTS (
              SELECT 1 FROM customer_receipt_settlements
              WHERE receipt_id=%s AND receivable_id=%s AND applied_amount=%s
          )
        """,
        (amount, amount, amount, receivable["id"], receipt_id, receivable["id"], amount),
    )
    journal = one(cur, "SELECT id FROM cash_bank_journal_entries WHERE entry_no=%s", (ENTRY_NO,))
    if not journal:
        cur.execute(
            """
            INSERT INTO cash_bank_journal_entries
                (account_id, entry_date, entry_no, source_type, source_no, direction, amount,
                 balance_after, partner_type, partner_name, project_code, cabinet_no, summary,
                 status, created_at)
            VALUES
                (%s, CURRENT_DATE, %s, 'customer_receipt', %s, 'in', %s,
                 COALESCE((SELECT current_balance FROM cash_bank_accounts WHERE id=%s),0) + %s,
                 'customer', 'trial customer', %s, %s,
                 'Trial first-machine customer receipt cash/bank journal', 'confirmed', CURRENT_TIMESTAMP)
            """,
            (
                account["id"],
                ENTRY_NO,
                RECEIPT_NO,
                amount,
                account["id"],
                amount,
                receivable["project_code"],
                receivable["cabinet_no"],
            ),
        )
        cur.execute(
            "UPDATE cash_bank_accounts SET current_balance=COALESCE(current_balance,0)+%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (amount, account["id"]),
        )
    return receipt_id, amount


def main():
    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_balances
                SET unit_cost=1
                WHERE COALESCE(quantity,0) > 0
                  AND COALESCE(unit_cost,0) <= 0
                """
            )
            receipt_id, receipt_amount = ensure_receipt_flow(cur)
            ensure_posted_auto_voucher(cur, "customer_receipt", receipt_id, RECEIPT_NO, date.today(), receipt_amount)

            cur.execute(
                """
                SELECT id, invoice_no, invoice_date, COALESCE(amount_with_tax, amount, total_amount, 0) AS amount
                FROM sales_invoices
                WHERE invoice_date >= date_trunc('month', CURRENT_DATE)
                  AND invoice_date < (date_trunc('month', CURRENT_DATE) + interval '1 month')
                  AND COALESCE(status,'') NOT IN ('void','voided','cancelled')
                """
            )
            for row in cur.fetchall():
                ensure_posted_auto_voucher(cur, "sales_invoice", row["id"], row["invoice_no"], row["invoice_date"], row["amount"])

            cur.execute(
                """
                SELECT id, invoice_no, invoice_date, COALESCE(amount_with_tax, amount, total_amount, 0) AS amount
                FROM purchase_invoices
                WHERE invoice_date >= date_trunc('month', CURRENT_DATE)
                  AND invoice_date < (date_trunc('month', CURRENT_DATE) + interval '1 month')
                  AND COALESCE(status,'') NOT IN ('void','voided','cancelled')
                """
            )
            for row in cur.fetchall():
                ensure_posted_auto_voucher(cur, "purchase_invoice", row["id"], row["invoice_no"], row["invoice_date"], row["amount"])

            cur.execute(
                """
                SELECT id, payment_no, payment_date, amount
                FROM supplier_payments
                WHERE payment_date >= date_trunc('month', CURRENT_DATE)
                  AND payment_date < (date_trunc('month', CURRENT_DATE) + interval '1 month')
                  AND COALESCE(status,'') NOT IN ('void','voided','cancelled')
                """
            )
            for row in cur.fetchall():
                ensure_posted_auto_voucher(cur, "supplier_payment", row["id"], row["payment_no"], row["payment_date"], row["amount"])
        conn.commit()
    print("finance_phase1_trial_data_repair=ok")


if __name__ == "__main__":
    raise SystemExit(main())
