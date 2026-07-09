"""System health adapters: re-export data health dashboard and master data health detail renderers."""
from routes.system_health_routes import render_data_health_dashboard, render_master_data_health_detail


def render_data_health_dashboard_adapter(
    render_module_dashboard,
    columns,
    safe_rows,
    count_rows,
    table_columns,
    has_table,
    database_health_rows,
    route_health_rows,
    recent_error_rows,
    backup_status,
    backup_rows,
    clean_text=None,
):
    return render_data_health_dashboard(
        render_module_dashboard,
        columns,
        safe_rows,
        count_rows,
        table_columns,
        has_table,
        database_health_rows,
        route_health_rows,
        recent_error_rows,
        backup_status,
        backup_rows,
        clean_text,
    )


def render_master_data_health_detail_adapter(check_key, safe_rows, columns, render_module_dashboard):
    return render_master_data_health_detail(check_key, safe_rows, columns, render_module_dashboard)
