"""Master data form adapters: re-export form renderers for master data entities."""
from routes.master_data_form_routes import (
    render_category_form,
    render_customer_form,
    render_department_form,
    render_employee_form,
    render_location_form,
    render_cabinet_master_form,
    render_project_master_form,
    render_supplier_form,
    render_unit_form,
    render_warehouse_form,
)


def render_customer_form_adapter(query_one, query_rows, customer_id=None):
    return render_customer_form(query_one, query_rows, customer_id)


def render_supplier_form_adapter(query_one, query_rows, supplier_id=None):
    return render_supplier_form(query_one, query_rows, supplier_id)


def render_warehouse_form_adapter(query_one, query_rows, warehouse_id=None):
    return render_warehouse_form(query_one, query_rows, warehouse_id)


def render_location_form_adapter(query_one, query_rows, location_id=None):
    return render_location_form(query_one, query_rows, location_id)


def render_unit_form_adapter(query_one, query_rows, unit_id=None):
    return render_unit_form(query_one, query_rows, unit_id)


def render_department_form_adapter(query_one, query_rows, department_id=None):
    return render_department_form(query_one, query_rows, department_id)


def render_employee_form_adapter(query_one, query_rows, employee_id=None):
    return render_employee_form(query_one, query_rows, employee_id)


def render_project_master_form_adapter(query_one, query_rows, project_id=None):
    return render_project_master_form(query_one, query_rows, project_id)


def render_cabinet_master_form_adapter(query_one, query_rows, machine_id=None):
    return render_cabinet_master_form(query_one, query_rows, machine_id)


def render_category_form_adapter(query_one, query_rows, kind, category_id=None):
    return render_category_form(query_one, query_rows, kind, category_id)
