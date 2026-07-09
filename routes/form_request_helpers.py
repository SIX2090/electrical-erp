"""Form request helpers: parse and validate form data for document entry pages."""
from flask import request

from routes.value_conversion_helpers import as_decimal


def form_text(name, default=""):
    return (request.form.get(name) or default or "").strip()


def form_int(name):
    value = form_text(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def form_decimal(name, default="0"):
    return as_decimal(form_text(name), default)


def form_bool(name, default=False):
    value = form_text(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on", "启用", "开启", "允许"}
