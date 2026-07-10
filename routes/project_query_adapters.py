"""Project query adapters: wrap project kit summary and finance summary renderers."""
from routes.project_query_helpers import (
    build_kit_summary,
    project_finance_summary,
    project_items_without_bom,
    project_kit_rows,
)


def build_kit_summary_adapter(rows, no_bom_items, as_decimal, qty_metric):
    return build_kit_summary(rows, no_bom_items, as_decimal=as_decimal, qty_metric=qty_metric)


def project_kit_rows_adapter(order_id, project_code, cabinet_no, cost_object_id, safe_rows):
    return project_kit_rows(
        order_id,
        project_code,
        cabinet_no,
        cost_object_id,
        safe_rows=safe_rows,
    )


def project_items_without_bom_adapter(order_id, safe_rows):
    return project_items_without_bom(order_id, safe_rows=safe_rows)


def project_finance_summary_adapter(order, project_code, cabinet_no, cost_object_id, safe_one, as_decimal):
    return project_finance_summary(
        order,
        project_code,
        cabinet_no,
        cost_object_id,
        safe_one=safe_one,
        as_decimal=as_decimal,
    )
