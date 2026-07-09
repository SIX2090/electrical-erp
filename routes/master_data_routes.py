"""Master data routes: unified master data list and detail pages."""
MASTER_DATA_DIRTY_MARKERS = (
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
    "delete warehouse",
    "lifecycle customer",
    "test",
    "测试仓",
    "测试库位",
    "测试部门",
    "测试员工",
)


def _clean_master_rows(rows, *fields):
    clean = []
    for row in rows or []:
        text = " ".join(str(row.get(field) or "").strip().lower() for field in fields)
        if any(marker in text for marker in MASTER_DATA_DIRTY_MARKERS):
            continue
        clean.append(row)
    return clean


def _is_blank(value):
    if value is None:
        return True
    return str(value).strip() in {"", "0", "0.0", "0.00"}


def _missing_labels(row, field_labels):
    missing = [label for field, label in field_labels if _is_blank(row.get(field))]
    return "、".join(missing) if missing else "待复核"


def _add_queue_context(rows, owner, next_step, blocked_reason, downstream_impact, edit_prefix, field_labels):
    for row in rows or []:
        row["owner"] = owner
        row["next_step"] = next_step
        row["blocked_reason"] = blocked_reason
        row["downstream_impact"] = downstream_impact
        row["missing_fields"] = _missing_labels(row, field_labels)
        row["detail_url"] = f"{edit_prefix}/{row.get('id')}/edit"
    return rows


def render_master_data_dashboard(query_rows, count_rows, sum_value, money_metric, render_dashboard, columns):
    # Boundary marker: 待处理队列, 安全库存, 默认仓库, 信用信息, 结算资料.
    material_gaps = _clean_master_rows(
        query_rows(
            """
            SELECT id, code AS product_code, name AS product_name, specification, unit, item_type,
                   COALESCE(category, '') AS category, safety_stock, default_warehouse,
                   default_supplier_name
            FROM products
            WHERE COALESCE(code,'') = ''
               OR COALESCE(name,'') = ''
               OR COALESCE(specification,'') = ''
               OR COALESCE(unit,'') = ''
               OR COALESCE(category,'') = ''
               OR COALESCE(safety_stock, 0) = 0
               OR COALESCE(default_warehouse,'') = ''
               OR COALESCE(default_supplier_name,'') = ''
            ORDER BY id DESC
            LIMIT 30
            """
        ),
        "product_code",
        "product_name",
        "specification",
        "category",
        "default_supplier_name",
        "default_warehouse",
    )
    material_gaps = _add_queue_context(
        material_gaps,
        "物料管理员",
        "补齐规格、单位、分类、默认供应商、默认仓库和安全库存",
        "主数据不完整",
        "影响 BOM、MRP、采购建议和库存执行",
        "/material",
        [
            ("product_code", "物料编码"),
            ("product_name", "物料名称"),
            ("specification", "规格型号"),
            ("unit", "基本单位"),
            ("category", "物料分类"),
            ("default_supplier_name", "默认供应商"),
            ("default_warehouse", "默认仓库"),
            ("safety_stock", "安全库存"),
        ],
    )

    customer_gaps = _clean_master_rows(
        query_rows(
            """
            SELECT id, name, contact_person, phone, customer_level,
                   COALESCE(credit_limit, 0) AS credit_limit,
                   COALESCE(ar.receivable_balance, 0) AS receivable_balance
            FROM customers c
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(balance), 0) AS receivable_balance
                FROM customer_receivables cr
                WHERE cr.customer_id=c.id
            ) ar ON TRUE
            WHERE COALESCE(c.name,'') = ''
               OR COALESCE(c.contact_person,'') = ''
               OR COALESCE(c.phone,'') = ''
               OR COALESCE(c.customer_level,'') = ''
               OR COALESCE(c.credit_limit, 0) = 0
            ORDER BY COALESCE(ar.receivable_balance, 0) DESC, c.id DESC
            LIMIT 20
            """
        ),
        "name",
        "contact_person",
        "phone",
        "customer_level",
    )
    customer_gaps = _add_queue_context(
        customer_gaps,
        "销售内勤",
        "补客户等级、联系人、电话、信用额度和付款条件备注",
        "客户信用资料缺关键字段",
        "影响销售下单、发货、应收跟进和信用预警",
        "/customer",
        [
            ("name", "客户名称"),
            ("contact_person", "联系人"),
            ("phone", "电话"),
            ("customer_level", "客户等级"),
            ("credit_limit", "信用额度"),
        ],
    )

    supplier_gaps = _clean_master_rows(
        query_rows(
            """
            SELECT id, name, contact_person, phone, address, lead_time_days,
                   COALESCE(po.pending_qty, 0) AS pending_qty,
                   COALESCE(ap.payable_balance, 0) AS payable_balance
            FROM suppliers s
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0)), 0) AS pending_qty
                FROM purchase_orders po
                LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
                WHERE po.supplier_id=s.id
            ) po ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(balance), 0) AS payable_balance
                FROM supplier_payables sp
                WHERE sp.supplier_id=s.id
            ) ap ON TRUE
            WHERE COALESCE(s.name,'') = ''
               OR COALESCE(s.contact_person,'') = ''
               OR COALESCE(s.phone,'') = ''
               OR COALESCE(s.address,'') = ''
               OR COALESCE(s.lead_time_days, 0) = 0
            ORDER BY COALESCE(po.pending_qty, 0) DESC, COALESCE(ap.payable_balance, 0) DESC, s.id DESC
            LIMIT 20
            """
        ),
        "name",
        "contact_person",
        "phone",
        "address",
    )
    supplier_gaps = _add_queue_context(
        supplier_gaps,
        "采购员",
        "补联系人、电话、默认交期、收票/结算地址和付款条件备注",
        "供应商结算资料不完整",
        "影响采购跟单、委外协同和应付对账",
        "/supplier",
        [
            ("name", "供应商名称"),
            ("contact_person", "联系人"),
            ("phone", "电话"),
            ("address", "结算/收票地址"),
            ("lead_time_days", "默认交期"),
        ],
    )

    warehouse_gaps = _clean_master_rows(
        query_rows(
            """
            SELECT w.id, w.code, w.name,
                   COALESCE(loc.location_count, 0) AS location_count,
                   COALESCE(loc.active_location_count, 0) AS active_location_count
            FROM warehouses w
            LEFT JOIN (
                SELECT warehouse_id,
                       COUNT(*) AS location_count,
                       COUNT(*) FILTER (WHERE COALESCE(is_active, true)) AS active_location_count
                FROM locations
                GROUP BY warehouse_id
            ) loc ON loc.warehouse_id=w.id
            WHERE COALESCE(w.code,'') = ''
               OR COALESCE(w.name,'') = ''
               OR COALESCE(loc.location_count, 0) = 0
               OR COALESCE(loc.active_location_count, 0) = 0
            ORDER BY w.id DESC
            LIMIT 20
            """
        ),
        "code",
        "name",
    )
    warehouse_gaps = _add_queue_context(
        warehouse_gaps,
        "仓库主管",
        "补仓库编码、启用库位和收发存口径",
        "仓库/库位不可用",
        "影响入库、出库、调拨、盘点",
        "/warehouse",
        [
            ("code", "仓库编码"),
            ("name", "仓库名称"),
            ("location_count", "库位"),
            ("active_location_count", "启用库位"),
        ],
    )

    metrics = [
        {"label": "主数据待处理", "value": len(material_gaps) + len(customer_gaps) + len(supplier_gaps) + len(warehouse_gaps), "hint": "不会自动填值，只提示人工维护"},
        {"label": "物料档案", "value": count_rows("products"), "hint": "影响 BOM/MRP/采购/库存"},
        {"label": "客户/供应商", "value": f"{count_rows('customers')}/{count_rows('suppliers')}", "hint": "影响销售、采购和往来"},
        {"label": "仓库/库位", "value": f"{count_rows('warehouses')}/{count_rows('locations')}", "hint": "影响所有库存单据"},
    ]
    shortcuts = [
        {"label": "物料档案", "url": "/material", "icon": "bi-box"},
        {"label": "客户档案", "url": "/customer", "icon": "bi-people"},
        {"label": "供应商档案", "url": "/supplier", "icon": "bi-building"},
        {"label": "仓库档案", "url": "/warehouse", "icon": "bi-houses"},
        {"label": "库位档案", "url": "/locations", "icon": "bi-pin-map"},
        {"label": "物料分类", "url": "/categories/product", "icon": "bi-tags"},
    ]
    return render_dashboard(
        "基础资料质量工作台",
        "围绕物料、客户、供应商、仓库和库位的待补齐队列。系统只展示缺口和维护入口，不自动乱填业务主数据。",
        metrics,
        shortcuts,
        [
            {
                "title": "主数据待处理",
                "count_label": "按档案类型汇总",
                "cards": [
                    {
                        "title": "物料主数据",
                        "count": len(material_gaps),
                        "owner": "物料管理员",
                        "next_step": "维护默认供应商、默认仓库、安全库存和分类",
                        "downstream_impact": "BOM/MRP/采购/库存",
                        "url": "/material",
                    },
                    {
                        "title": "客户信用资料",
                        "count": len(customer_gaps),
                        "owner": "销售内勤",
                        "next_step": "维护客户等级、联系人、电话和信用额度",
                        "downstream_impact": "销售下单/发货/应收",
                        "url": "/customer",
                    },
                    {
                        "title": "供应商结算资料",
                        "count": len(supplier_gaps),
                        "owner": "采购员",
                        "next_step": "维护联系人、电话、默认交期和结算资料",
                        "downstream_impact": "采购跟单/委外协同/应付",
                        "url": "/supplier",
                    },
                    {
                        "title": "仓库/库位",
                        "count": len(warehouse_gaps),
                        "owner": "仓库主管",
                        "next_step": "维护仓库编码、启用库位和收发存口径",
                        "downstream_impact": "入库/出库/调拨/盘点",
                        "url": "/warehouse",
                    },
                ],
            },
            {
                "title": "物料补齐队列",
                "count_label": "默认供应商、默认仓库、安全库存等维护提示",
                "rows": material_gaps,
                "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格型号"), ("unit", "单位"), ("category", "分类"), ("missing_fields", "待补齐字段"), ("owner", "责任人"), ("next_step", "下一步"), ("downstream_impact", "影响范围")),
                "detail_base": "/material",
                "import_url": "/material/import",
                "template_url": "/material/download_template",
                "empty_text": "暂无需要优先补齐的物料基础资料。",
            },
            {
                "title": "客户信用资料队列",
                "count_label": "客户信用、等级和联系方式维护提示",
                "rows": customer_gaps,
                "columns": columns(("name", "客户"), ("contact_person", "联系人"), ("phone", "电话"), ("customer_level", "等级"), ("credit_limit", "信用额度"), ("receivable_balance", "应收余额"), ("missing_fields", "待补齐字段"), ("owner", "责任人"), ("next_step", "下一步")),
                "detail_base": "/customer",
                "import_url": "/customer/import",
                "template_url": "/customer/download_template",
                "empty_text": "暂无需要优先补齐的客户信用资料。",
            },
            {
                "title": "供应商结算资料队列",
                "count_label": "供应商联系方式、默认交期和结算资料维护提示",
                "rows": supplier_gaps,
                "columns": columns(("name", "供应商"), ("contact_person", "联系人"), ("phone", "电话"), ("lead_time_days", "默认交期"), ("pending_qty", "采购未到"), ("payable_balance", "应付余额"), ("missing_fields", "待补齐字段"), ("owner", "责任人"), ("next_step", "下一步")),
                "detail_base": "/supplier",
                "import_url": "/supplier/import",
                "template_url": "/supplier/download_template",
                "empty_text": "暂无需要优先补齐的供应商资料。",
            },
            {
                "title": "仓库库位补齐队列",
                "count_label": "默认仓库和可用库位维护提示",
                "rows": warehouse_gaps,
                "columns": columns(("code", "仓库编码"), ("name", "仓库名称"), ("location_count", "库位数"), ("active_location_count", "启用库位"), ("missing_fields", "待补齐字段"), ("owner", "责任人"), ("next_step", "下一步"), ("downstream_impact", "影响范围")),
                "detail_base": "/warehouse",
                "import_url": "/warehouse/import",
                "template_url": "/warehouse/download_template",
                "empty_text": "暂无需要优先补齐的仓库库位资料。",
            },
        ],
    )
