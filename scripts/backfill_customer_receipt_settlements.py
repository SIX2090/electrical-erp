from decimal import Decimal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import get_db_config
from services.app_runtime import connect_db


def as_decimal(value):
    return Decimal(str(value or 0))


def recalculate_receivable(cur, receivable_id):
    cur.execute(
        """
        SELECT COALESCE(SUM(s.applied_amount),0) AS settled
        FROM customer_receipt_settlements s
        JOIN customer_receipts r ON r.id=s.receipt_id
        WHERE s.receivable_id=%s
          AND COALESCE(r.status,'') NOT IN ('已作废','已反核销','void','voided','cancelled')
        """,
        (receivable_id,),
    )
    settled = as_decimal(cur.fetchone()["settled"])
    cur.execute("SELECT total_amount FROM customer_receivables WHERE id=%s", (receivable_id,))
    total = as_decimal(cur.fetchone()["total_amount"])
    balance = max(total - settled, Decimal("0"))
    if settled <= 0:
        status = "未收款"
    elif balance <= 0:
        status = "已收款"
    else:
        status = "部分收款"
    cur.execute(
        """
        UPDATE customer_receivables
        SET received_amount=%s, balance=%s, status=%s
        WHERE id=%s
        """,
        (settled, balance, status, receivable_id),
    )


def main():
    inserted = 0
    touched = set()
    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.customer_id, r.amount, r.receipt_date
                FROM customer_receipts r
                LEFT JOIN customer_receipt_settlements s ON s.receipt_id=r.id
                WHERE s.id IS NULL
                  AND COALESCE(r.amount,0)>0
                  AND r.customer_id IS NOT NULL
                  AND COALESCE(r.status,'') NOT IN ('已作废','已反核销','void','voided','cancelled')
                ORDER BY r.receipt_date NULLS LAST, r.id
                """
            )
            receipts = cur.fetchall()
            for receipt in receipts:
                remaining = as_decimal(receipt["amount"])
                cur.execute(
                    """
                    SELECT id, COALESCE(total_amount,0) AS total_amount,
                           COALESCE(received_amount,0) AS received_amount,
                           COALESCE(balance,0) AS balance
                    FROM customer_receivables
                    WHERE customer_id=%s
                      AND COALESCE(total_amount,0)>0
                    ORDER BY
                      CASE WHEN COALESCE(balance,0)>0 THEN 0 ELSE 1 END,
                      due_date NULLS LAST,
                      receivable_date NULLS LAST,
                      id
                    """,
                    (receipt["customer_id"],),
                )
                for recv in cur.fetchall():
                    if remaining <= 0:
                        break
                    open_balance = as_decimal(recv["balance"])
                    if open_balance <= 0:
                        continue
                    applied = min(remaining, open_balance)
                    cur.execute(
                        """
                        INSERT INTO customer_receipt_settlements
                            (receipt_id, receivable_id, applied_amount)
                        VALUES (%s,%s,%s)
                        ON CONFLICT (receipt_id, receivable_id)
                        DO UPDATE SET applied_amount=EXCLUDED.applied_amount
                        """,
                        (receipt["id"], recv["id"], applied),
                    )
                    inserted += 1
                    touched.add(recv["id"])
                    remaining -= applied
            for receivable_id in touched:
                recalculate_receivable(cur, receivable_id)
        conn.commit()
    print(f"customer_receipt_settlement_backfill_inserted={inserted}")
    print(f"customer_receivables_recalculated={len(touched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
