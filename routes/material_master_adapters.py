"""Material master adapters: re-export material form and detail renderers."""
from routes.material_master_routes import render_material_detail, render_material_form


def render_material_form_adapter(product_id, query_one, query_rows=None):
    return render_material_form(product_id, query_one=query_one, query_rows=query_rows)


def render_material_detail_adapter(
    product_id,
    query_one,
    query_rows,
    money_metric,
    qty_metric,
    material_attachments,
    back_url="/material",
):
    return render_material_detail(
        product_id,
        query_one,
        query_rows,
        money_metric,
        qty_metric,
        material_attachments,
        back_url,
    )
