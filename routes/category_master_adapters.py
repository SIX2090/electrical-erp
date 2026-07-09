"""Category master adapter functions re-exported from category_master_routes."""
from routes.category_master_routes import (
    category_kind_for_path,
    render_category_dashboard,
    render_category_detail,
)


def category_kind_for_path_adapter(path):
    return category_kind_for_path(path)


def render_category_dashboard_adapter(kind, query_rows, count_rows, render_dashboard, columns, back_url=None):
    return render_category_dashboard(kind, query_rows, count_rows, render_dashboard, columns, back_url)


def render_category_detail_adapter(kind, category_id, query_one, query_rows, columns, back_url=None):
    return render_category_detail(kind, category_id, query_one, query_rows, columns, back_url)
