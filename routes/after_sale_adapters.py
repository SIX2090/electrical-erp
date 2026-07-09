"""After-sale adapter functions re-exported from after_sale_routes for backward compatibility."""
from routes.after_sale_routes import (
    render_after_sale_dashboard,
    render_service_card_detail,
    render_service_order_detail,
    render_service_rma_detail,
)


def render_after_sale_dashboard_adapter(query_rows, count_rows, columns, render_module_dashboard):
    return render_after_sale_dashboard(query_rows, count_rows, columns, render_module_dashboard)


def render_service_card_detail_adapter(
    card_id,
    query_one,
    query_rows,
    document_attachments,
    document_activity_logs,
    back_url="/service-cards",
):
    return render_service_card_detail(card_id, query_one, query_rows, document_attachments, document_activity_logs, back_url)


def render_service_order_detail_adapter(
    order_id,
    query_one,
    query_rows,
    as_decimal,
    product_options,
    document_attachments,
    document_activity_logs,
    load_custom_payload,
    back_url="/service-orders",
):
    return render_service_order_detail(
        order_id,
        query_one,
        query_rows,
        as_decimal,
        product_options,
        document_attachments,
        document_activity_logs,
        load_custom_payload,
        back_url,
    )


def render_service_rma_detail_adapter(
    rma_id,
    query_one,
    as_decimal,
    document_attachments,
    document_activity_logs,
    back_url="/service-rmas",
):
    return render_service_rma_detail(rma_id, query_one, as_decimal, document_attachments, document_activity_logs, back_url)
