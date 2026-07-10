"""Material master routes: material list, material form, and material import/export."""
from flask import render_template


MATERIAL_NON_BUSINESS_MARKERS = (
    "imported material",
    "transfer fail",
    "negative block material",
    "inventory accuracy",
    "multi line material",
    "inv-acc",
    "ml-",
    "req material",
    "reg material",
    "adjust a",
    "adjust b",
    "audit",
    "test",
    "lifecycle",
)

MATERIAL_CATEGORY_NON_BUSINESS_MARKERS = (
    "imp-cat-",
    "test",
    "pytest",
    "lifecycle",
)


def _looks_non_business_material(row, *fields):
    text = " ".join(str(row.get(field) or "").strip().lower() for field in fields)
    return any(marker in text for marker in MATERIAL_NON_BUSINESS_MARKERS)


def _filter_material_rows(rows, *fields):
    return [row for row in (rows or []) if not _looks_non_business_material(row, *fields)]


def _category_text_business_where(alias):
    prefix = f"{alias}." if alias else ""
    text_expr = f"LOWER(CONCAT_WS(' ', {prefix}code, {prefix}name, {prefix}remark))" if alias == "pc" else f"LOWER(COALESCE({prefix}category, ''))"
    clauses = [f"{text_expr} NOT LIKE %s" for _marker in MATERIAL_CATEGORY_NON_BUSINESS_MARKERS]
    return " AND ".join(clauses), tuple(f"%{marker.lower()}%" for marker in MATERIAL_CATEGORY_NON_BUSINESS_MARKERS)


def render_material_form(product_id=None, query_one=None, query_rows=None, back_url="/material"):
    product = query_one("SELECT * FROM products WHERE id=%s", (product_id,)) if product_id else None
    categories = []
    if query_rows:
        categories = query_rows(
            """
            SELECT id, code, name
            FROM product_categories
            ORDER BY code NULLS LAST, name
            LIMIT 300
            """,
            (),
        )
        suppliers = query_rows("SELECT id, name FROM suppliers WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY name LIMIT 500", ())
        warehouses = query_rows("SELECT id, name FROM warehouses WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY name LIMIT 300", ())
        locations = query_rows("SELECT id, code || ' / ' || name AS name FROM locations WHERE COALESCE(is_active, TRUE)=TRUE AND COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY code LIMIT 500", ())
    else:
        suppliers = []
        warehouses = []
        locations = []
    category_options = [
        {
            "id": row.get("id"),
            "name": f"{row.get('name') or ''}（{row.get('code')}）" if row.get("code") else row.get("name"),
        }
        for row in categories
    ]
    return render_template(
        "operation_form.html",
        title="编辑物料" if product else "新增物料",
        subtitle="维护物料基础、单位、采购、库存、生产和计划字段。",
        back_url=back_url,
        action_url=f"/material/{product_id}/edit" if product else "/material/new",
        sections=[
            {
                "title": "基础信息",
                "fields": [
                    {"name": "code", "label": "物料编码（新增可留空）", "required": bool(product), "value": product.get("code") if product else ""},
                    {"name": "name", "label": "物料名称", "required": True, "value": product.get("name") if product else ""},
                    {"name": "specification", "label": "规格型号", "value": product.get("specification") if product else ""},
                    {"name": "item_type", "label": "物料类型", "value": product.get("item_type") if product else "原材料"},
                    {"name": "category_id", "label": "物料分类", "type": "select", "options": category_options, "value": product.get("category_id") if product else ""},
                    {"name": "category", "label": "分类", "value": product.get("category") if product else ""},
                    {"name": "barcode", "label": "条码/助记码", "value": product.get("barcode") if product else ""},
                    {"name": "drawing_no", "label": "图号", "value": product.get("drawing_no") if product else ""},
                    {"name": "material_grade", "label": "材质", "value": product.get("material_grade") if product else ""},
                    {"name": "brand", "label": "品牌", "value": product.get("brand") if product else ""},
                    {"name": "origin_place", "label": "产地", "value": product.get("origin_place") if product else ""},
                    {"name": "status", "label": "状态", "value": product.get("status") if product else "启用"},
                ],
            },
            {
                "title": "单位信息",
                "fields": [
                    {"name": "unit", "label": "基本单位", "value": product.get("unit") if product else "PCS"},
                    {"name": "aux_unit", "label": "辅助单位", "value": product.get("aux_unit") if product else ""},
                    {"name": "conversion_rate", "label": "换算率", "type": "number", "step": "0.0001", "value": product.get("conversion_rate") if product else "1"},
                ],
            },
            {
                "title": "采购信息",
                "fields": [
                    {"name": "default_supplier_name", "label": "默认供应商", "value": product.get("default_supplier_name") if product else ""},
                    {"name": "default_supplier_id", "label": "默认供应商档案", "type": "select", "options": suppliers, "value": product.get("default_supplier_id") if product else ""},
                    {"name": "purchase_lead_days", "label": "采购提前期天数", "type": "number", "step": "1", "value": product.get("purchase_lead_days") if product else "0"},
                    {"name": "min_order_qty", "label": "最小采购量", "type": "number", "step": "0.01", "value": product.get("min_order_qty") if product else "0"},
                    {"name": "default_tax_rate", "label": "默认税率%", "type": "number", "step": "0.01", "value": product.get("default_tax_rate") if product else "13"},
                ],
            },
            {
                "title": "库存信息",
                "fields": [
                    {"name": "standard_price", "label": "标准价", "type": "number", "step": "0.01", "value": product.get("standard_price") if product else "0"},
                    {"name": "safety_stock", "label": "安全库存", "type": "number", "step": "0.01", "value": product.get("safety_stock") if product else "0"},
                    {"name": "default_warehouse", "label": "默认仓库", "value": product.get("default_warehouse") if product else ""},
                    {"name": "default_warehouse_id", "label": "默认仓库档案", "type": "select", "options": warehouses, "value": product.get("default_warehouse_id") if product else ""},
                    {"name": "default_location", "label": "默认库位", "value": product.get("default_location") if product else ""},
                    {"name": "default_location_id", "label": "默认库位档案", "type": "select", "options": locations, "value": product.get("default_location_id") if product else ""},
                    {"name": "cost_method", "label": "计价方法", "value": product.get("cost_method") if product else "移动加权"},
                    {"name": "shelf_life_days", "label": "保质期天数", "type": "number", "step": "1", "value": product.get("shelf_life_days") if product else "0"},
                    {"name": "batch_control", "label": "批次控制", "type": "select", "options": [{"id": "true", "name": "是"}, {"id": "false", "name": "否"}], "value": "true" if (product and product.get("batch_control")) else "false"},
                    {"name": "serial_control", "label": "序列号控制", "type": "select", "options": [{"id": "true", "name": "是"}, {"id": "false", "name": "否"}], "value": "true" if (product and product.get("serial_control")) else "false"},
                    {"name": "inspection_required", "label": "来料/入库检验", "type": "select", "options": [{"id": "true", "name": "是"}, {"id": "false", "name": "否"}], "value": "true" if (product and product.get("inspection_required")) else "false"},
                    {"name": "abc_class", "label": "ABC分类", "value": product.get("abc_class") if product else ""},
                ],
            },
            {
                "title": "计划与生产信息",
                "fields": [
                    {"name": "net_weight", "label": "净重", "type": "number", "step": "0.001", "value": product.get("net_weight") if product else "0"},
                    {"name": "gross_weight", "label": "毛重", "type": "number", "step": "0.001", "value": product.get("gross_weight") if product else "0"},
                    {"name": "length_mm", "label": "长(mm)", "type": "number", "step": "0.01", "value": product.get("length_mm") if product else "0"},
                    {"name": "width_mm", "label": "宽(mm)", "type": "number", "step": "0.01", "value": product.get("width_mm") if product else "0"},
                    {"name": "height_mm", "label": "高(mm)", "type": "number", "step": "0.01", "value": product.get("height_mm") if product else "0"},
                ],
            },
            {
                "title": "备注",
                "fields": [
                    {"name": "remark", "label": "备注", "type": "textarea", "value": product.get("remark") if product else ""},
                ],
            }
        ],
    )

def render_material_dashboard(
    query_rows,
    count_rows,
    filter_clean_rows,
    clean_display_text,
    status_label,
    request_args,
    back_url="/material",
):
    keyword = (request_args.get("keyword") or request_args.get("q") or "").strip()
    item_type = (request_args.get("item_type") or "").strip()
    category = (request_args.get("category") or "").strip()
    status = (request_args.get("status") or "").strip()
    unit = (request_args.get("unit") or "").strip()
    control = (request_args.get("control") or "").strip()
    supplier_state = (request_args.get("supplier_state") or "").strip()
    sort_by = (request_args.get("sort") or "id").strip()
    sort_order = (request_args.get("order") or "desc").strip().lower()
    try:
        page = max(int(request_args.get("page") or 1), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request_args.get("per_page") or 50)
    except (TypeError, ValueError):
        per_page = 50
    per_page = min(max(per_page, 20), 200)
    offset = (page - 1) * per_page

    where_parts = []
    params = []
    if keyword:
        where_parts.append("(p.code ILIKE %s OR p.name ILIKE %s OR p.specification ILIKE %s OR p.drawing_no ILIKE %s)")
        params.extend([f"%{keyword}%"] * 4)
    if item_type:
        where_parts.append("COALESCE(p.item_type, '') = %s")
        params.append(item_type)
    if category:
        if category.isdigit():
            where_parts.append("p.category_id = %s")
            params.append(int(category))
        else:
            where_parts.append("(COALESCE(p.category, '') = %s OR COALESCE(pc.name, '') = %s)")
            params.extend([category, category])
    if status:
        if status == "audited":
            where_parts.append("COALESCE(p.status, '') NOT IN ('未提交', '草稿', 'draft')")
        elif status == "draft":
            where_parts.append("COALESCE(p.status, '') IN ('未提交', '草稿', 'draft')")
        else:
            where_parts.append("COALESCE(p.status, '') = %s")
            params.append(status)
    if unit:
        where_parts.append("COALESCE(p.unit, '') = %s")
        params.append(unit)
    if control == "batch":
        where_parts.append("COALESCE(p.batch_control, false)=true")
    elif control == "cabinet":
        where_parts.append("COALESCE(p.serial_control, false)=true")
    elif control == "inspection":
        where_parts.append("COALESCE(p.inspection_required, false)=true")
    elif control == "none":
        where_parts.append(
            "COALESCE(p.batch_control, false)=false AND COALESCE(p.serial_control, false)=false AND COALESCE(p.inspection_required, false)=false"
        )
    if supplier_state == "set":
        where_parts.append("COALESCE(p.default_supplier_name, '') <> ''")
    elif supplier_state == "missing":
        where_parts.append("COALESCE(p.default_supplier_name, '') = ''")
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    sort_columns = {
        "id": "p.id",
        "code": "p.code",
        "name": "p.name",
        "specification": "p.specification",
        "status": "p.status",
        "unit": "p.unit",
        "category": "COALESCE(pc.name, p.category, p.item_type)",
        "tax": "p.default_tax_rate",
        "supplier": "p.default_supplier_name",
    }
    sort_expr = sort_columns.get(sort_by, "p.id")
    sort_order = "asc" if sort_order == "asc" else "desc"
    order_sql = f"ORDER BY {sort_expr} {sort_order.upper()} NULLS LAST, p.id DESC"
    total_row = query_rows(
        f"""
        SELECT COUNT(*) AS total_count
        FROM products p
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        {where_sql}
        """,
        tuple(params),
    )
    total_count = int((total_row[0] or {}).get("total_count") or 0) if total_row else 0
    total_pages = max((total_count + per_page - 1) // per_page, 1)
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    metrics = [
        {"label": "物料总数", "value": count_rows("products"), "hint": "档案维护范围内的全部物料"},
        {
            "label": "已分类",
            "value": count_rows("products", "COALESCE(category,'') <> '' OR category_id IS NOT NULL"),
            "hint": "已维护分类或分类名称",
        },
        {
            "label": "有默认供应商",
            "value": count_rows("products", "COALESCE(default_supplier_name,'') <> ''"),
            "hint": "采购主数据已维护",
        },
        {
            "label": "启用物料",
            "value": count_rows("products", "COALESCE(status,'') NOT IN ('停用','disabled')"),
            "hint": "当前可用于业务单据",
        },
    ]
    products = query_rows(
        f"""
        SELECT p.id, p.code, p.name, p.specification, p.unit, p.category, p.item_type,
               p.category_id, pc.name AS category_name,
               p.status, p.standard_price, p.safety_stock, p.default_supplier_name,
               COALESCE(ds.name, p.default_supplier_name) AS default_supplier_display,
               dw.name AS default_warehouse_display,
               dl.code || ' / ' || dl.name AS default_location_display,
               p.drawing_no, p.material_grade, p.brand, p.default_tax_rate,
               p.serial_control, p.batch_control, p.inspection_required
        FROM products p
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN suppliers ds ON ds.id=p.default_supplier_id
        LEFT JOIN warehouses dw ON dw.id=p.default_warehouse_id
        LEFT JOIN locations dl ON dl.id=p.default_location_id
        {where_sql}
        {order_sql}
        LIMIT %s OFFSET %s
        """,
        tuple(params + [per_page, offset]),
    )
    products = filter_clean_rows(
        products,
        "code",
        "name",
        "category",
        "item_type",
        "specification",
        "default_supplier_display",
        "default_warehouse_display",
        "default_location_display",
    )
    products = _filter_material_rows(products, "code", "name", "category", "item_type", "specification", "default_supplier_display")
    for row in products:
        row["display_status"] = status_label(row.get("status"))
        row["display_category"] = clean_display_text(row.get("category_name") or row.get("category") or row.get("item_type"), "-")

    item_types = query_rows(
        """
        SELECT item_type, COUNT(*) AS count
        FROM products
        WHERE COALESCE(item_type, '') <> ''
        GROUP BY item_type
        ORDER BY count DESC, item_type
        LIMIT 30
        """
    )
    item_types = filter_clean_rows(item_types, "item_type")
    item_types = _filter_material_rows(item_types, "item_type")
    category_business_where, category_business_params = _category_text_business_where("pc")
    categories = query_rows(
        """
        SELECT pc.id, pc.name AS category, COUNT(p.id) AS count, 'master' AS source
        FROM product_categories pc
        LEFT JOIN products p ON p.category_id=pc.id
        WHERE {category_business_where}
        GROUP BY pc.id, pc.name
        ORDER BY pc.name
        LIMIT 100
        """.format(category_business_where=category_business_where),
        category_business_params,
    )
    categories = filter_clean_rows(categories, "category")
    categories = _filter_material_rows(categories, "category")
    unbound_categories = []
    units = query_rows(
        """
        SELECT unit, COUNT(*) AS count
        FROM products
        WHERE COALESCE(unit, '') <> ''
        GROUP BY unit
        ORDER BY count DESC, unit
        LIMIT 80
        """
    )
    units = filter_clean_rows(units, "unit")
    units = _filter_material_rows(units, "unit")
    statuses = query_rows(
        """
        SELECT status, COUNT(*) AS count
        FROM products
        WHERE COALESCE(status, '') <> ''
        GROUP BY status
        ORDER BY count DESC, status
        LIMIT 30
        """
    )
    statuses = filter_clean_rows(statuses, "status")
    statuses = _filter_material_rows(statuses, "status")
    return render_template(
        "material_dashboard.html",
        title="物料档案",
        subtitle="维护编码、名称、规格、分类、单位、图号、材质、品牌等主数据；库存余额和库存流水请到库存模块查看。",
        metrics=metrics,
        shortcuts=[],
        products=products,
        item_types=item_types,
        categories=categories,
        unbound_categories=unbound_categories,
        filters={
            "keyword": keyword,
            "item_type": item_type,
            "category": category,
            "status": status,
            "unit": unit,
            "control": control,
            "supplier_state": supplier_state,
            "sort": sort_by,
            "order": sort_order,
        },
        filter_options={
            "units": units,
            "statuses": statuses,
            "controls": [
                {"value": "batch", "label": "批次"},
                {"value": "serial", "label": "序列号"},
                {"value": "inspection", "label": "入库检验"},
                {"value": "none", "label": "无控制"},
            ],
            "supplier_states": [
                {"value": "set", "label": "已维护供应商"},
                {"value": "missing", "label": "缺默认供应商"},
            ],
        },
        pagination={
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "offset": offset,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": max(page - 1, 1),
            "next_page": min(page + 1, total_pages),
            "page_window": list(range(max(1, page - 2), min(total_pages, page + 2) + 1)),
            "per_page_options": [20, 50, 100, 200],
        },
        back_url=back_url,
    )


def render_material_detail(
    product_id,
    query_one,
    query_rows,
    money_metric,
    qty_metric,
    material_attachments,
    back_url="/material",
):
    product = query_one(
        """
        SELECT p.*, pc.name AS category_name,
               COALESCE(ds.name, p.default_supplier_name) AS default_supplier_display,
               dw.name AS default_warehouse_display,
               dl.code || ' / ' || dl.name AS default_location_display
        FROM products p
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN suppliers ds ON ds.id=p.default_supplier_id
        LEFT JOIN warehouses dw ON dw.id=p.default_warehouse_id
        LEFT JOIN locations dl ON dl.id=p.default_location_id
        WHERE p.id=%s
        """,
        (product_id,),
    )
    if not product:
        return render_template("simple_detail.html", title="物料详情", row=None, back_url=back_url, labels={})

    purchase = query_one(
        """
        SELECT COALESCE(SUM(quantity), 0) AS ordered_qty,
               COALESCE(SUM(received_qty), 0) AS received_qty,
               COALESCE(SUM(amount), 0) AS amount
        FROM purchase_order_items
        WHERE product_id=%s
        """,
        (product_id,),
    ) or {}
    sales = query_one(
        """
        SELECT COALESCE(SUM(quantity), 0) AS ordered_qty,
               COALESCE(SUM(shipped_qty), 0) AS shipped_qty,
               COALESCE(SUM(amount), 0) AS amount
        FROM sales_order_items
        WHERE product_id=%s
        """,
        (product_id,),
    ) or {}

    context = {
        "back_url": back_url,
        "delete_url": f"/material/{product_id}/delete",
        "product": product,
        "metrics": [
            {"label": "物料状态", "value": product.get("status") or "-", "hint": "启用/停用"},
            {"label": "标准价", "value": money_metric(product.get("standard_price", 0)), "hint": "主数据参考价格"},
            {
                "label": "采购未收",
                "value": qty_metric((purchase.get("ordered_qty", 0) or 0) - (purchase.get("received_qty", 0) or 0)),
                "hint": "采购数量 - 已收",
            },
            {
                "label": "销售未发",
                "value": qty_metric((sales.get("ordered_qty", 0) or 0) - (sales.get("shipped_qty", 0) or 0)),
                "hint": "销售数量 - 已发",
            },
        ],
        "parent_boms": query_rows(
            """
            SELECT b.id, b.bom_no, b.version, b.status, b.bom_type, b.effective_date,
                   COUNT(bi.id) AS item_count
            FROM boms b
            LEFT JOIN bom_items bi ON bi.bom_id=b.id
            WHERE b.product_id=%s
            GROUP BY b.id
            ORDER BY b.id DESC
            LIMIT 30
            """,
            (product_id,),
        ),
        "used_in_boms": query_rows(
            """
            SELECT b.id, b.bom_no, b.version, b.status, parent.code AS parent_code,
                   parent.name AS parent_name, bi.quantity, COALESCE(bi.unit, p.unit) AS unit, bi.loss_rate
            FROM bom_items bi
            LEFT JOIN boms b ON b.id=bi.bom_id
            LEFT JOIN products parent ON parent.id=b.product_id
            LEFT JOIN products p ON p.id=bi.product_id
            WHERE bi.product_id=%s
            ORDER BY b.id DESC, bi.id DESC
            LIMIT 50
            """,
            (product_id,),
        ),
        "purchase_items": query_rows(
            """
            SELECT poi.id, po.order_no, po.order_date, po.status, s.name AS supplier_name,
                   po.project_code, po.cabinet_no, poi.quantity, poi.received_qty, poi.unit_price, poi.amount
            FROM purchase_order_items poi
            LEFT JOIN purchase_orders po ON po.id=poi.order_id
            LEFT JOIN suppliers s ON s.id=po.supplier_id
            WHERE poi.product_id=%s
            ORDER BY poi.id DESC
            LIMIT 50
            """,
            (product_id,),
        ),
        "sales_items": query_rows(
            """
            SELECT soi.id, so.order_no, so.order_date, so.status, c.name AS customer_name,
                   so.project_code, so.cabinet_no, soi.quantity, soi.shipped_qty, soi.unit_price, soi.amount
            FROM sales_order_items soi
            LEFT JOIN sales_orders so ON so.id=soi.order_id
            LEFT JOIN customers c ON c.id=so.customer_id
            WHERE soi.product_id=%s
            ORDER BY soi.id DESC
            LIMIT 50
            """,
            (product_id,),
        ),
        "work_orders": query_rows(
            """
            SELECT wo.id, wo.wo_no, wo.wo_date, wo.status, wo.project_code, wo.cabinet_no,
                   wo.quantity, wo.planned_start_date, wo.planned_end_date
            FROM work_orders wo
            WHERE wo.product_id=%s
            ORDER BY wo.id DESC
            LIMIT 50
            """,
            (product_id,),
        ),
        "attachments": material_attachments(product_id),
    }
    return render_template("material_trace_detail.html", **context)

