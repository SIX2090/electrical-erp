"""Report render helpers: dispatch data-backed report sections and render module/section reports."""
from routes.read_query_helpers import _csv_response
from routes.module_report_data import build_module_report_config
from routes.report_routes import (
    REPORT_SECTIONS,
    render_clean_module_report,
    render_clean_section_report,
    render_report_center,
)

DATA_BACKED_REPORT_KINDS = {"sales", "purchase", "inventory", "production", "subcontract", "finance", "service"}


def _report_kind_for_path(path):
    for kind, config in REPORT_SECTIONS.items():
        if kind not in DATA_BACKED_REPORT_KINDS:
            continue
        if any(report_path == path for report_path, _title, _words in config["sections"]):
            return kind
    if path.startswith("/finance/inventory-cost/"):
        return "inventory"
    return None


DATA_BACKED_REPORT_PATHS = {
    report_path
    for kind, config in REPORT_SECTIONS.items()
    if kind in DATA_BACKED_REPORT_KINDS
    for report_path, _title, _words in config["sections"]
}
DATA_BACKED_REPORT_PATHS.update(
    {
        "/finance/inventory-cost/summary",
        "/finance/inventory-cost/detail",
    }
)


def _render_clean_module_report(kind):
    if kind in DATA_BACKED_REPORT_KINDS:
        if kind == "finance":
            from flask import request
            if request.path == "/finance/reports":
                return render_clean_module_report(_csv_response, kind)
        from flask import render_template, request
        from routes.module_report_adapters import render_module_report_adapter
        from routes.registry import _module_report_config

        return render_module_report_adapter(
            kind,
            _module_report_config,
            _csv_response,
            render_template,
            request.args,
            request.path,
            not_found_title="\u62a5\u8868\u4e0d\u5b58\u5728",
        )
    if kind == "inventory_data_backed":
        from flask import render_template, request
        from routes.module_report_adapters import render_module_report_adapter
        from routes.registry import _module_report_config

        return render_module_report_adapter(
            "inventory",
            _module_report_config,
            _csv_response,
            render_template,
            request.args,
            request.path,
            not_found_title="\u62a5\u8868\u4e0d\u5b58\u5728",
        )
    return render_clean_module_report(_csv_response, kind)


def _render_report_center():
    return render_report_center(_csv_response)


def _render_clean_section_report(path):
    if path in DATA_BACKED_REPORT_PATHS:
        from flask import render_template, request
        from routes.module_report_adapters import render_module_report_adapter

        class SectionArgs:
            def __init__(self, args, section_path, scope_filter=None):
                self.args = args
                self.section_path = section_path
                self.scope_filter = scope_filter

            def get(self, key, default=None):
                if key == "_section_path":
                    return self.section_path
                if key == "_data_scope_filter":
                    return self.scope_filter
                return self.args.get(key, default)

        from routes.registry import _as_decimal, _columns, _data_scope_filter, _money_metric, _qty_metric, _safe_rows, _sum_value
        section_args = SectionArgs(request.args, path, _data_scope_filter)

        report_kind = _report_kind_for_path(path)
        if not report_kind:
            report_kind = "inventory" if path.startswith("/finance/inventory-cost/") else ("finance" if path.startswith("/finance/") else "inventory")
        return render_module_report_adapter(
            report_kind,
            lambda kind: build_module_report_config(
                kind,
                _safe_rows,
                _sum_value,
                _as_decimal,
                _money_metric,
                _qty_metric,
                _columns,
                section_args,
            ),
            _csv_response,
            render_template,
            section_args,
            request.path,
            not_found_title="\u62a5\u8868\u4e0d\u5b58\u5728",
        )
    return render_clean_section_report(_csv_response, path)
