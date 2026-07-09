"""Module report helpers: filter parsing and report rendering for module report pages."""
REPORT_FILTER_KEYS = ("date_start", "date_end", "status", "keyword", "project")


def report_filters(args):
    """Return normalized report filter values from a Flask-style args mapping."""

    return {
        "date_start": (args.get("date_start") or "").strip(),
        "date_end": (args.get("date_end") or "").strip(),
        "status": (args.get("status") or "").strip(),
        "keyword": (args.get("keyword") or args.get("q") or "").strip(),
        "project": (args.get("project") or "").strip(),
    }


def report_where(filters, date_expr, text_exprs=(), status_expr=None, project_exprs=()):
    """Build the read-only WHERE clause used by module reports."""

    where = []
    params = []
    if filters["date_start"]:
        where.append(f"{date_expr} >= %s")
        params.append(filters["date_start"])
    if filters["date_end"]:
        where.append(f"{date_expr} <= %s")
        params.append(filters["date_end"])
    if filters["status"] and status_expr:
        where.append(f"{status_expr} ILIKE %s")
        params.append(f"%{filters['status']}%")
    if filters["keyword"] and text_exprs:
        where.append("(" + " OR ".join(f"{expr} ILIKE %s" for expr in text_exprs) + ")")
        params.extend([f"%{filters['keyword']}%"] * len(text_exprs))
    if filters["project"] and project_exprs:
        where.append("(" + " OR ".join(f"{expr} ILIKE %s" for expr in project_exprs) + ")")
        params.extend([f"%{filters['project']}%"] * len(project_exprs))
    return (" WHERE " + " AND ".join(where)) if where else "", tuple(params)


def report_where_from_args(args, date_expr, text_exprs=(), status_expr=None, project_exprs=()):
    """Build filters plus WHERE clause from request args without importing Flask."""

    filters = report_filters(args)
    where, params = report_where(filters, date_expr, text_exprs, status_expr, project_exprs)
    return where, params, filters


def module_report_export_url(path, filters):
    query = "&".join(f"{key}={value}" for key, value in filters.items() if value)
    export_url = path + "?" + query
    return export_url + ("&" if "?" in export_url and not export_url.endswith("?") else "") + "export=csv"


def module_report_xlsx_export_url(path, filters):
    query = "&".join(f"{key}={value}" for key, value in filters.items() if value)
    export_url = path + "?" + query
    return export_url + ("&" if "?" in export_url and not export_url.endswith("?") else "") + "export=xlsx"


def flatten_report_section_rows(config):
    rows = []
    for section in config.get("sections", ()):
        rows.extend(section.get("rows") or ())
    return rows


def render_module_report(
    kind,
    config_builder,
    csv_response,
    template_renderer,
    args,
    path,
    not_found_title="\u62a5\u8868\u4e0d\u5b58\u5728",
):
    """Render a data-backed module report using injected read-only dependencies."""

    config = config_builder(kind)
    if not config:
        return template_renderer("simple_detail.html", title=not_found_title, row=None, back_url="/", labels={})
    section_path = args.get("_section_path") if hasattr(args, "get") else None
    if section_path:
        matched_sections = [section for section in config.get("sections", ()) if section.get("url") == section_path]
        if matched_sections:
            config = dict(config)
            config["title"] = matched_sections[0].get("title") or config["title"]
            config["sections"] = matched_sections
        else:
            catalog_entry = _report_catalog_entry(section_path)
            if catalog_entry:
                _url, report_title, _words = catalog_entry
                base_section = {"rows": (), "columns": ()}
                base_section["title"] = report_title
                base_section["url"] = None
                config = dict(config)
                config["title"] = report_title
                config["sections"] = [base_section]
    if args.get("export") in {"csv", "xlsx", "excel"} or args.get("format") in {"csv", "xlsx", "excel"}:
        return csv_response(flatten_report_section_rows(config), config["title"])
    export_url = module_report_export_url(path, config["filters"])
    export_xlsx_url = module_report_xlsx_export_url(path, config["filters"])
    return template_renderer("module_report.html", export_url=export_url, export_xlsx_url=export_xlsx_url, **config)


def _report_catalog_entry(path):
    from routes.report_routes import REPORT_SECTIONS

    for report_config in REPORT_SECTIONS.values():
        for report_url, report_title, report_words in report_config.get("sections", ()):
            if report_url == path:
                return report_url, report_title, report_words
    return None
