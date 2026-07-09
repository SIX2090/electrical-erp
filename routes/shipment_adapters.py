"""Shipment adapters: re-export shipment detail and print renderers."""
from routes.shipment_routes import render_shipment_detail, render_shipment_print


def render_shipment_detail_adapter(
    shipment_id,
    query_one,
    query_rows,
    as_decimal,
    qty_metric,
    money_metric,
    document_attachments,
    document_activity_logs,
    back_url="/shipments",
):
    return render_shipment_detail(
        shipment_id,
        query_one,
        query_rows,
        as_decimal,
        qty_metric,
        money_metric,
        document_attachments,
        document_activity_logs,
        back_url,
    )


def render_shipment_print_adapter(shipment_id, query_one, query_rows, as_decimal):
    return render_shipment_print(shipment_id, query_one, query_rows, as_decimal)
