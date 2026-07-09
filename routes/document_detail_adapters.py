"""Document detail adapters: wrap order detail renderers with request context."""
from routes.document_print_routes import render_document_print
from routes.order_detail_routes import render_purchase_order_detail, render_sales_order_detail


def render_sales_order_detail_adapter(
    order_id,
    query_one,
    query_rows,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/sales-orders",
):
    return render_sales_order_detail(
        order_id,
        query_one,
        query_rows,
        columns,
        document_attachments,
        document_activity_logs,
        back_url,
    )


def render_purchase_order_detail_adapter(
    order_id,
    query_one,
    query_rows,
    columns,
    document_attachments,
    document_activity_logs,
    back_url="/purchase-orders",
):
    return render_purchase_order_detail(
        order_id,
        query_one,
        query_rows,
        columns,
        document_attachments,
        document_activity_logs,
        back_url,
    )


def render_document_print_adapter(kind, order_id, query_one, query_rows, as_decimal):
    return render_document_print(kind, order_id, query_one, query_rows, as_decimal)
