"""Module report adapters: wrap report renderers with request context."""
from routes.module_report_helpers import render_module_report


def render_module_report_adapter(
    kind,
    config_builder,
    csv_response,
    template_renderer,
    args,
    path,
    not_found_title="\u62a5\u8868\u4e0d\u5b58\u5728",
):
    return render_module_report(
        kind,
        config_builder,
        csv_response,
        template_renderer,
        args,
        path,
        not_found_title=not_found_title,
    )
