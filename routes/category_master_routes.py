"""Category master routes: material category and classification list/form."""
from flask import render_template, request


CATEGORY_NON_BUSINESS_MARKERS = (
    "imp-cat-",
    "test",
    "lifecycle",
    "\u7531\u7269\u6599\u5bfc\u5165\u81ea\u52a8\u521b\u5efa",
)


def _filter_category_rows(rows, *fields):
    clean = []
    for row in rows or []:
        text = " ".join(str(row.get(field) or "").strip().lower() for field in fields)
        if any(marker in text for marker in CATEGORY_NON_BUSINESS_MARKERS):
            continue
        clean.append(row)
    return clean


def _category_business_filter(alias=None):
    prefix = f"{alias}." if alias else ""
    text_expr = f"LOWER(CONCAT_WS(' ', {prefix}code, {prefix}name, {prefix}remark))"
    clauses = [f"{text_expr} NOT LIKE %s" for _marker in CATEGORY_NON_BUSINESS_MARKERS]
    return " AND ".join(clauses), tuple(f"%{marker.lower()}%" for marker in CATEGORY_NON_BUSINESS_MARKERS)


CATEGORY_TYPES = {
    "product": {
        "table": "product_categories",
        "title": "物料分类",
        "subject_table": "products",
        "subject_label": "物料",
        "subject_link": "/material",
        "subtitle": "维护物料分类档案，用于物料档案归类、筛选和报表汇总。",
        "back_url": "/categories/product",
    },
    "customer": {
        "table": "customer_categories",
        "title": "客户分类",
        "subject_table": "customers",
        "subject_label": "客户",
        "subject_link": "/customer",
        "subtitle": "维护重点客户、潜在客户、行业等客户分类。",
        "back_url": "/categories/customer",
    },
    "supplier": {
        "table": "supplier_categories",
        "title": "供应商分类",
        "subject_table": "suppliers",
        "subject_label": "供应商",
        "subject_link": "/supplier",
        "subtitle": "维护核心供应商、备选供应商、外协供应商等分类。",
        "back_url": "/categories/supplier",
    },
    "warehouse": {
        "table": "warehouse_categories",
        "title": "仓库分类",
        "subject_table": "warehouses",
        "subject_label": "仓库",
        "subject_link": "/warehouse",
        "subtitle": "维护原材料、装配、成品、隔离等仓库分类。",
        "back_url": "/categories/warehouse",
    },
}


def category_kind_for_path(path):
    if not path:
        return None
    if path.startswith("/categories/product"):
        return "product"
    if path.startswith("/categories/customer"):
        return "customer"
    if path.startswith("/categories/supplier"):
        return "supplier"
    if path.startswith("/categories/warehouse"):
        return "warehouse"
    return None


def render_category_dashboard(kind, query_rows, count_rows, render_dashboard, columns, back_url=None):
    config = CATEGORY_TYPES.get(kind)
    if not config:
        return None
    table = config["table"]
    subject_table = config["subject_table"]
    back_url = back_url or config["back_url"]
    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    business_where, business_params = _category_business_filter("c")
    where_parts = [business_where]
    params = list(business_params)
    if keyword:
        where_parts.append("(c.code ILIKE %s OR c.name ILIKE %s OR c.remark ILIKE %s)")
        params.extend([f"%{keyword}%"] * 3)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    raw_category_count = count_rows(table)
    business_count_where, business_count_params = _category_business_filter()
    business_category_count = count_rows(table, business_count_where, business_count_params)
    hidden_category_count = max(raw_category_count - business_category_count, 0)
    top_level_where = f"parent_id IS NULL AND {business_count_where}"
    metrics = [
        {"label": "业务分类数", "value": business_category_count, "hint": "列表维护口径"},
        {"label": "原始记录数", "value": raw_category_count, "hint": "含测试/临时导入"},
        {"label": "顶层业务分类", "value": count_rows(table, top_level_where, business_count_params), "hint": "无上级"},
        {"label": "已绑定记录", "value": count_rows(subject_table, "category_id IS NOT NULL"), "hint": f"已分类的{config['subject_label']}"},
        {"label": "未分类记录", "value": count_rows(subject_table, "category_id IS NULL"), "hint": f"未分类的{config['subject_label']}"},
    ]
    shortcuts = []
    rows = query_rows(
        f"""
        SELECT c.id, c.code, c.name, c.remark,
               parent.name AS parent_name,
               COALESCE(usage.subject_count, 0) AS subject_count
        FROM {table} c
        LEFT JOIN {table} parent ON parent.id=c.parent_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS subject_count FROM {subject_table} s WHERE s.category_id=c.id
        ) usage ON TRUE
        {where_sql}
        ORDER BY parent.name NULLS FIRST, c.name
        LIMIT 200
        """,
        tuple(params),
    )
    rows = _filter_category_rows(rows, "code", "name", "remark")
    for row in rows:
        row["detail_url"] = f"/categories/{kind}/{row.get('id')}"
        row["edit_url"] = f"/categories/{kind}/{row.get('id')}/edit"
    sections = [
        {
            "title": f"{config['title']}列表",
            "rows": rows,
            "count_label": f"显示 {len(rows)} 条业务分类，已隐藏 {hidden_category_count} 条测试/临时导入记录",
            "filters": [
                {
                    "name": "keyword",
                    "label": "查询",
                    "value": keyword,
                    "placeholder": "分类编码 / 名称 / 备注",
                }
            ],
            "columns": columns(("code", "编码"), ("name", "名称"), ("parent_name", "上级"), ("subject_count", config["subject_label"] + "数"), ("remark", "备注")),
            "detail_base": back_url,
            "detail_label": "分类详情",
            "edit_label": "编辑",
            "disable_table_tools": True,
            "add_url": f"/categories/{kind}/new",
            "import_url": f"/categories/{kind}/import",
            "template_url": f"/categories/{kind}/download_template",
            "export_url": f"/export/{kind}-categories",
        }
    ]
    return render_dashboard(config["title"], config["subtitle"], metrics, shortcuts, sections)


def _category_subject_rows(config, query_rows, category_id, columns):
    subject_table = config["subject_table"]
    if subject_table == "products":
        return (
            query_rows(
                "SELECT id, code, name, specification, unit, status FROM products WHERE category_id=%s ORDER BY code LIMIT 100",
                (category_id,),
            ),
            columns(("code", "编码"), ("name", "名称"), ("specification", "规格"), ("unit", "单位"), ("status", "状态")),
        )
    if subject_table == "customers":
        return (
            query_rows(
                "SELECT id, name, contact_person, phone, customer_level FROM customers WHERE category_id=%s ORDER BY name LIMIT 100",
                (category_id,),
            ),
            columns(("name", "客户"), ("contact_person", "联系人"), ("phone", "电话"), ("customer_level", "等级")),
        )
    if subject_table == "suppliers":
        return (
            query_rows(
                "SELECT id, name, contact_person, phone FROM suppliers WHERE category_id=%s ORDER BY name LIMIT 100",
                (category_id,),
            ),
            columns(("name", "供应商"), ("contact_person", "联系人"), ("phone", "电话")),
        )
    return (
        query_rows(
            "SELECT id, code, name, remark FROM warehouses WHERE category_id=%s ORDER BY code LIMIT 100",
            (category_id,),
        ),
        columns(("code", "编码"), ("name", "仓库"), ("remark", "备注")),
    )


def render_category_detail(kind, category_id, query_one, query_rows, columns, back_url=None):
    config = CATEGORY_TYPES.get(kind)
    if not config:
        return None
    table = config["table"]
    back_url = back_url or config["back_url"]
    record = query_one(
        f"""
        SELECT c.*, parent.name AS parent_name, parent.code AS parent_code
        FROM {table} c
        LEFT JOIN {table} parent ON parent.id=c.parent_id
        WHERE c.id=%s
        """,
        (category_id,),
    )
    if not record:
        return render_template("simple_detail.html", title=f"{config['title']}详情", row=None, back_url=back_url, labels={})
    if _filter_category_rows([record], "code", "name", "remark") == []:
        return render_template("simple_detail.html", title=f"{config['title']}详情", row=None, back_url=back_url, labels={})
    children = query_rows(
        f"""
        SELECT id, code, name, remark FROM {table} WHERE parent_id=%s ORDER BY name LIMIT 100
        """,
        (category_id,),
    )
    children = _filter_category_rows(children, "code", "name", "remark")
    subjects, subject_columns = _category_subject_rows(config, query_rows, category_id, columns)
    subjects = _filter_category_rows(subjects, "code", "name", "remark", "contact_person", "phone", "customer_level")
    info_rows = [
        ("编码", record.get("code")),
        ("名称", record.get("name")),
        ("上级分类", record.get("parent_name")),
        ("备注", record.get("remark")),
    ]
    metrics = [
        {"label": f"{config['subject_label']}数", "value": len(subjects), "hint": "属于本分类"},
        {"label": "下级分类", "value": len(children), "hint": "直属子分类"},
        {"label": "上级分类", "value": record.get("parent_name") or "-", "hint": "上级分类"},
        {"label": "编码", "value": record.get("code") or "-", "hint": "分类编码"},
    ]
    sections = [
        {
            "title": f"本分类下的{config['subject_label']}",
            "rows": subjects,
            "columns": subject_columns,
            "detail_base": config["subject_link"],
        },
        {
            "title": "下级分类",
            "rows": children,
            "columns": columns(("code", "编码"), ("name", "名称"), ("remark", "备注")),
            "detail_base": back_url,
        },
    ]
    return render_template(
        "basic_data_detail.html",
        title=f"{config['title']}详情",
        kind=f"category_{kind}",
        record=record,
        record_name=record.get("name") or "",
        record_id=category_id,
        back_url=back_url,
        edit_url=f"/categories/{kind}/{category_id}/edit",
        info_rows=info_rows,
        metrics=metrics,
        sections=sections,
    )
