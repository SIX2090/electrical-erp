from __future__ import annotations


def upsert_purchase_order_payable(
    execute_db,
    *,
    supplier_id,
    payable_no=None,
    doc_id,
    doc_no,
    doc_date,
    amount,
    balance,
    unpaid_status,
    paid_status,
    finance_remark,
    next_follow_up_date=None,
    doc_type="purchase_order",
) -> None:
    # supplier_payables_doc_uidx 是 partial unique index (WHERE doc_type IS NOT NULL AND doc_id IS NOT NULL),
    # 无法直接用 ON CONFLICT (doc_type, doc_id) DO UPDATE 引用。
    # 改为先 INSERT ON CONFLICT DO NOTHING（不指定目标，可匹配任意唯一约束含 partial index），
    # 再 UPDATE 保证字段（含基于 paid_amount 的 balance/status 重算）一致。
    execute_db(
        """
        INSERT INTO supplier_payables
            (supplier_id, payable_no, doc_type, doc_id, doc_no, doc_date, amount, paid_amount, balance,
             status, finance_remark, next_follow_up_date)
        VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,
        (
            supplier_id,
            payable_no,
            doc_type,
            doc_id,
            doc_no,
            doc_date,
            amount,
            balance,
            unpaid_status,
            finance_remark,
            next_follow_up_date,
        ),
    )
    execute_db(
        """
        UPDATE supplier_payables
        SET supplier_id=%s,
            doc_no=%s,
            doc_date=%s,
            amount=%s,
            balance=GREATEST(%s-COALESCE(paid_amount,0),0),
            status=CASE WHEN GREATEST(%s-COALESCE(paid_amount,0),0)=0 THEN %s ELSE %s END,
            finance_remark=%s,
            next_follow_up_date=%s
        WHERE doc_type=%s AND doc_id=%s
        """,
        (
            supplier_id,
            doc_no,
            doc_date,
            amount,
            amount,
            amount,
            paid_status,
            unpaid_status,
            finance_remark,
            next_follow_up_date,
            doc_type,
            doc_id,
        ),
    )


def update_purchase_order_payable(
    execute_db,
    *,
    supplier_id,
    doc_id,
    doc_date,
    amount,
    paid_status,
    next_follow_up_date=None,
) -> None:
    execute_db(
        """
        UPDATE supplier_payables
        SET supplier_id=%s, doc_date=%s, amount=%s,
            balance=GREATEST(%s-COALESCE(paid_amount,0),0),
            status=CASE WHEN GREATEST(%s-COALESCE(paid_amount,0),0)=0 THEN %s ELSE status END,
            next_follow_up_date=%s
        WHERE doc_type='purchase_order' AND doc_id=%s
        """,
        (
            supplier_id,
            doc_date,
            amount,
            amount,
            amount,
            paid_status,
            next_follow_up_date,
            doc_id,
        ),
    )


def insert_purchase_order_payable(
    execute_db,
    *,
    supplier_id,
    payable_no=None,
    doc_id,
    doc_no,
    doc_date,
    amount,
    balance,
    status,
    finance_remark,
    next_follow_up_date=None,
    doc_type="purchase_order",
) -> None:
    execute_db(
        """
        INSERT INTO supplier_payables
            (supplier_id, payable_no, doc_type, doc_id, doc_no, doc_date, amount, paid_amount, balance,
             status, finance_remark, next_follow_up_date)
        VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s)
        """,
        (
            supplier_id,
            payable_no,
            doc_type,
            doc_id,
            doc_no,
            doc_date,
            amount,
            balance,
            status,
            finance_remark,
            next_follow_up_date,
        ),
    )


def apply_supplier_payment_to_payable(
    execute_db,
    *,
    payable_id,
    applied_amount,
    paid_status,
    partial_status,
    new_balance,
) -> None:
    # status 基于更新后的 balance 原子判定，避免并发付款时状态计算过期
    execute_db(
        """
        UPDATE supplier_payables
        SET paid_amount=COALESCE(paid_amount,0)+%s,
            balance=GREATEST(COALESCE(balance,0)-%s,0),
            status=CASE WHEN GREATEST(COALESCE(balance,0)-%s,0)=0 THEN %s ELSE %s END
        WHERE id=%s
        """,
        (applied_amount, applied_amount, applied_amount, paid_status, partial_status, payable_id),
    )


def upsert_purchase_invoice_payable(
    execute_db,
    *,
    supplier_id,
    payable_no=None,
    doc_id,
    doc_no,
    doc_date,
    amount,
    balance,
    status,
    paid_status,
    unpaid_status,
    finance_remark,
    project_code=None,
    serial_no=None,
) -> None:
    # 同 upsert_purchase_order_payable：partial unique index 无法用 ON CONFLICT (doc_type, doc_id) DO UPDATE，
    # 改为 INSERT ON CONFLICT DO NOTHING + UPDATE。
    execute_db(
        """
        INSERT INTO supplier_payables
            (supplier_id, payable_no, doc_type, doc_id, doc_no, doc_date, amount, paid_amount,
             balance, status, finance_remark, project_code, serial_no)
        VALUES (%s,%s,'purchase_invoice',%s,%s,%s,%s,0,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,
        (
            supplier_id,
            payable_no,
            doc_id,
            doc_no,
            doc_date,
            amount,
            balance,
            status,
            finance_remark,
            project_code,
            serial_no,
        ),
    )
    execute_db(
        """
        UPDATE supplier_payables
        SET supplier_id=%s,
            doc_no=%s,
            doc_date=%s,
            amount=%s,
            balance=GREATEST(%s-COALESCE(paid_amount,0),0),
            status=CASE WHEN GREATEST(%s-COALESCE(paid_amount,0),0)=0 THEN %s ELSE %s END,
            finance_remark=%s,
            project_code=%s,
            serial_no=%s
        WHERE doc_type='purchase_invoice' AND doc_id=%s
        """,
        (
            supplier_id,
            doc_no,
            doc_date,
            amount,
            amount,
            amount,
            paid_status,
            unpaid_status,
            finance_remark,
            project_code,
            serial_no,
            doc_id,
        ),
    )


def finish_purchase_invoice_payable(
    execute_db,
    *,
    doc_id,
    status,
    remark,
) -> None:
    execute_db(
        """
        UPDATE supplier_payables
        SET status=%s, balance=0, paid_amount=COALESCE(amount,0),
            finance_remark=COALESCE(finance_remark,'') || %s
        WHERE doc_type='purchase_invoice' AND doc_id=%s
        """,
        (status, remark, doc_id),
    )


def void_purchase_order_payable(
    execute_db,
    *,
    doc_id,
    status,
    remark,
) -> None:
    execute_db(
        """
        UPDATE supplier_payables
        SET status=%s, balance=0, paid_amount=COALESCE(amount,0),
            finance_remark=COALESCE(finance_remark,'') || %s
        WHERE doc_type='purchase_order' AND doc_id=%s
        """,
        (status, remark, doc_id),
    )
