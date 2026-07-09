"""Purchase receipt adapters: re-export purchase receipt detail and print renderers."""
from routes.purchase_receipt_routes import render_purchase_receipt_detail, render_purchase_receipt_print


def render_purchase_receipt_detail_adapter(
    receipt_id,
    query_one,
    query_rows,
    count_rows,
    as_decimal,
    receipt_display_amount,
    qty_metric,
    money_metric,
    document_attachments,
    document_activity_logs,
    back_url="/purchase_receipts",
):
    return render_purchase_receipt_detail(
        receipt_id,
        query_one,
        query_rows,
        count_rows,
        as_decimal,
        receipt_display_amount,
        qty_metric,
        money_metric,
        document_attachments,
        document_activity_logs,
        back_url,
    )


def render_purchase_receipt_print_adapter(receipt_id, query_one, query_rows, as_decimal):
    return render_purchase_receipt_print(receipt_id, query_one, query_rows, as_decimal)
