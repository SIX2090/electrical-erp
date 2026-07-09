"""Order form adapters: wrap sales/purchase order form renderers with request context."""
from routes.order_form_routes import render_purchase_order_form, render_sales_order_form


def render_sales_order_form_adapter(
    order_id,
    query_one,
    query_rows,
    product_options,
    load_custom_payload,
):
    return render_sales_order_form(
        order_id,
        query_one,
        query_rows,
        product_options,
        load_custom_payload,
    )


def render_purchase_order_form_adapter(
    order_id,
    query_one,
    query_rows,
    product_options,
    load_custom_payload,
):
    return render_purchase_order_form(
        order_id,
        query_one,
        query_rows,
        product_options,
        load_custom_payload,
    )
