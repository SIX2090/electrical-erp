import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import get_db_config
from services.app_runtime import connect_db


def account_id_for(cur, label, source_no):
    name = (label or "").strip()
    if not name:
        raise RuntimeError(f"missing_cash_bank_account source_no={source_no}")
    cur.execute(
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
        (name, name, name),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"cash_bank_account_not_found source_no={source_no} account={name}")
    return row["id"]


def entry_no_for(prefix, source_no, line_no, line_count):
    return f"{prefix}-{source_no}-{line_no}" if line_count > 1 else f"{prefix}-{source_no}"


def insert_journal(cur, row, source_type, direction, line_count=1):
    source_no = row["source_no"]
    account_id = account_id_for(cur, row.get("bank_account") or row.get("payment_method"), source_no)
    prefix = "CBR" if direction == "in" else "CBP"
    line_no = row.get("line_no") or 1
    cur.execute(
        """
        INSERT INTO cash_bank_journal_entries
            (account_id, entry_date, entry_no, source_type, source_no, direction, amount,
             partner_type, partner_name, project_code, serial_no, summary, status, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s)
        """,
        (
            account_id,
            row["doc_date"],
            entry_no_for(prefix, source_no, line_no, line_count),
            source_type,
            source_no,
            direction,
            row["amount"],
            row["partner_type"],
            row["partner_name"],
            row.get("project_code"),
            row.get("serial_no"),
            row["summary"],
            row.get("created_by"),
        ),
    )
    return 1


def main():
    inserted = 0
    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM (
                    SELECT r.id, r.receipt_no AS source_no, r.receipt_date AS doc_date,
                           COALESCE(l.amount, r.amount) AS amount,
                           COALESCE(l.payment_method, r.payment_method) AS payment_method,
                           COALESCE(NULLIF(l.bank_account,''), r.bank_account) AS bank_account,
                           COALESCE(l.line_no, 1) AS line_no,
                           COALESCE(r.receipt_kind, 'customer_receipt') AS source_type,
                           COUNT(*) OVER (PARTITION BY r.receipt_no) AS line_count,
                           r.project_code, r.serial_no,
                           r.created_by, c.name AS partner_name, 'customer' AS partner_type,
                           'cash bank journal backfilled from historical receipt' AS summary
                    FROM customer_receipts r
                    LEFT JOIN customer_receipt_lines l ON l.receipt_id=r.id
                    LEFT JOIN customers c ON c.id=r.customer_id
                    WHERE COALESCE(r.status,'') NOT IN ('void','voided','cancelled')
                      AND COALESCE(r.receipt_no,'')<>''
                      AND NOT EXISTS (
                          SELECT 1 FROM cash_bank_journal_entries j
                          WHERE j.source_type=COALESCE(r.receipt_kind, 'customer_receipt') AND j.source_no=r.receipt_no
                      )
                ) q
                WHERE amount > 0
                ORDER BY id, line_no
                """
            )
            for row in cur.fetchall():
                inserted += insert_journal(cur, row, row.get("source_type") or "customer_receipt", "in", int(row.get("line_count") or 1))
            cur.execute(
                """
                SELECT *
                FROM (
                    SELECT p.id, p.payment_no AS source_no, p.payment_date AS doc_date,
                           COALESCE(l.amount, p.amount) AS amount,
                           COALESCE(l.payment_method, p.payment_method) AS payment_method,
                           COALESCE(NULLIF(l.bank_account,''), p.bank_account) AS bank_account,
                           COALESCE(l.line_no, 1) AS line_no,
                           COALESCE(p.payment_kind, 'supplier_payment') AS source_type,
                           COUNT(*) OVER (PARTITION BY p.payment_no) AS line_count,
                           p.project_code, p.serial_no,
                           p.created_by, s.name AS partner_name, 'supplier' AS partner_type,
                           'cash bank journal backfilled from historical payment' AS summary
                    FROM supplier_payments p
                    LEFT JOIN supplier_payment_lines l ON l.payment_id=p.id
                    LEFT JOIN suppliers s ON s.id=p.supplier_id
                    WHERE COALESCE(p.status,'') NOT IN ('void','voided','cancelled')
                      AND COALESCE(p.payment_no,'')<>''
                      AND NOT EXISTS (
                          SELECT 1 FROM cash_bank_journal_entries j
                          WHERE j.source_type=COALESCE(p.payment_kind,'supplier_payment') AND j.source_no=p.payment_no
                      )
                ) q
                WHERE amount > 0
                ORDER BY id, line_no
                """
            )
            for row in cur.fetchall():
                inserted += insert_journal(cur, row, row.get("source_type") or "supplier_payment", "out", int(row.get("line_count") or 1))
        conn.commit()
    print(f"cash_bank_journal_backfill_inserted={inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
