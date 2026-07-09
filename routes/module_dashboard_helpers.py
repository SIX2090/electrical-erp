"""Module dashboard helpers: render module center pages with metrics and shortcuts."""
from flask import render_template


def render_module_dashboard(title, subtitle, metrics, shortcuts, sections):
    return render_template(
        "module_dashboard.html",
        title=title,
        subtitle=subtitle,
        metrics=metrics,
        shortcuts=shortcuts,
        sections=sections,
    )
