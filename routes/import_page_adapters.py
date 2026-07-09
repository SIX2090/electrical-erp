"""Import page adapters: re-export import page renderers from import_page_helpers."""
from routes.import_page_helpers import (
    basic_import_template_response,
    category_import_template_response,
    material_import_template_response,
    render_basic_import_page,
    render_category_import_page,
    render_material_import_page,
)


def render_material_import_page_adapter(precheck_report=None):
    return render_material_import_page(precheck_report)


def material_import_template_response_adapter(csv_response):
    return material_import_template_response(csv_response)


def render_basic_import_page_adapter(kind, configs, precheck_report=None):
    return render_basic_import_page(kind, configs, precheck_report)


def basic_import_template_response_adapter(kind, configs, csv_response, flash_message, redirect_to):
    return basic_import_template_response(kind, configs, csv_response, flash_message, redirect_to)


def render_category_import_page_adapter(kind, category_types):
    return render_category_import_page(kind, category_types)


def category_import_template_response_adapter(kind, category_types, csv_response):
    return category_import_template_response(kind, category_types, csv_response)
