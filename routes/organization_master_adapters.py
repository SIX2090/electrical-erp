"""Organization master adapters: re-export department and employee renderers."""
from flask import request

from routes.organization_master_routes import (
    render_department_dashboard,
    render_department_detail,
    render_employee_dashboard,
    render_employee_detail,
    render_unit_dashboard,
    render_unit_detail,
)


def render_unit_dashboard_adapter(query_rows, query_one, count_rows, render_dashboard, columns, back_url="/unit"):
    return render_unit_dashboard(query_rows, query_one, count_rows, render_dashboard, columns, request.args, back_url)


def render_unit_detail_adapter(unit_id, query_one, query_rows, columns, back_url="/unit"):
    return render_unit_detail(unit_id, query_one, query_rows, columns, back_url)


def render_department_dashboard_adapter(query_rows, count_rows, render_dashboard, columns, back_url="/department"):
    return render_department_dashboard(query_rows, count_rows, render_dashboard, columns, request.args, back_url)


def render_department_detail_adapter(department_id, query_one, query_rows, columns, back_url="/department"):
    return render_department_detail(department_id, query_one, query_rows, columns, back_url)


def render_employee_dashboard_adapter(query_rows, count_rows, render_dashboard, columns, back_url="/employee"):
    return render_employee_dashboard(query_rows, count_rows, render_dashboard, columns, request.args, back_url)


def render_employee_detail_adapter(employee_id, query_one, query_rows, columns, back_url="/employee"):
    return render_employee_detail(employee_id, query_one, query_rows, columns, back_url)
