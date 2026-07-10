"""Warehouse master routes: warehouse, location, and unit list/form."""
from flask import render_template

from .display_helpers import _clean_display_text, _filter_operator_rows


_WAREHOUSE_NON_BUSINESS_MARKERS = (
    "delete warehouse",
    "test",
    "lifecycle",
    "测试仓",
    "测试库",
    "随机测试",
    "随机",
)


def _filter_master_rows(rows, *fields):
    clean = []
    for row in _filter_operator_rows(rows, *fields):
        text = " ".join(str(row.get(field) or "").strip().lower() for field in fields)
        if any(marker in text for marker in _WAREHOUSE_NON_BUSINESS_MARKERS):
            continue
        clean.append(row)
    return clean


def _clean_rows(rows, *fields):
    for row in rows or []:
        for field in fields:
            row[field] = _clean_display_text(row.get(field))
    return rows


def _keyword_clause(alias, fields, keyword):
    if not keyword:
        return "", []
    parts = [f"{alias}.{field} ILIKE %s" for field in fields]
    return "(" + " OR ".join(parts) + ")", [f"%{keyword}%"] * len(fields)


def render_warehouse_dashboard(query_rows, query_one, count_rows, render_dashboard, columns, request_args, back_url="/warehouse"):
    keyword = (request_args.get("keyword") or request_args.get("q") or request_args.get("search") or "").strip()
    where_parts = []
    params = []
    keyword_clause, keyword_params = _keyword_clause("w", ["code", "name", "warehouse_type", "status", "remark"], keyword)
    if keyword_clause:
        where_parts.append(keyword_clause)
        params.extend(keyword_params)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    active_locations = count_rows("locations", "COALESCE(is_active, true)=true")
    warehouses_with_locations = query_one("SELECT COUNT(DISTINCT warehouse_id) AS value FROM locations WHERE warehouse_id IS NOT NULL") or {}
    metrics = [
        {"label": "仓库数", "value": count_rows("warehouses"), "hint": "仓库档案总数"},
        {"label": "有库位仓库", "value": warehouses_with_locations.get("value", 0), "hint": "已配置库位的仓库"},
        {"label": "库位数", "value": count_rows("locations"), "hint": "全部库位档案"},
        {"label": "启用仓库", "value": count_rows("warehouses", "COALESCE(status,'启用') NOT IN ('停用','disabled')"), "hint": "可用于业务单据"},
    ]
    shortcuts = []
    warehouses = query_rows(
        f"""
        SELECT w.id, w.code, w.name, w.warehouse_type, w.status, w.remark,
               wc.name AS category_name,
               dl.code || ' / ' || dl.name AS default_location_name,
               COALESCE(loc.location_count, 0) AS location_count,
               COALESCE(loc.active_location_count, 0) AS active_location_count,
               CASE WHEN COALESCE(loc.active_location_count, 0) > 0 THEN '启用' ELSE '待配置库位' END AS config_status
        FROM warehouses w
        LEFT JOIN warehouse_categories wc ON wc.id=w.category_id
        LEFT JOIN locations dl ON dl.id=w.default_location_id
        LEFT JOIN (
            SELECT warehouse_id,
                   COUNT(*) AS location_count,
                   COUNT(*) FILTER (WHERE COALESCE(is_active, true)) AS active_location_count
            FROM locations
            GROUP BY warehouse_id
        ) loc ON loc.warehouse_id=w.id
        {where_sql}
        ORDER BY w.code NULLS LAST, w.id DESC
        LIMIT 100
        """,
        tuple(params),
    )
    warehouses = _filter_master_rows(warehouses, "code", "name", "warehouse_type", "status", "category_name", "default_location_name", "remark")
    warehouses = _clean_rows(warehouses, "code", "name", "warehouse_type", "status", "category_name", "default_location_name", "remark", "config_status")
    for row in warehouses:
        row["detail_url"] = f"/warehouse/{row.get('id')}"
        row["edit_url"] = f"/warehouse/{row.get('id')}/edit"
    location_rows = query_rows(
        """
        SELECT l.id, l.code, l.name, l.location_type, w.name AS warehouse_name,
               COALESCE(l.status, CASE WHEN COALESCE(l.is_active, true) THEN '启用' ELSE '停用' END) AS status_label,
               l.remark
        FROM locations l
        LEFT JOIN warehouses w ON w.id=l.warehouse_id
        ORDER BY w.code NULLS LAST, l.code
        LIMIT 100
        """
    )
    location_rows = _filter_master_rows(location_rows, "code", "name", "location_type", "warehouse_name", "remark")
    location_rows = _clean_rows(location_rows, "code", "name", "location_type", "warehouse_name", "status_label", "remark")
    for row in location_rows:
        row["detail_url"] = f"/locations/{row.get('id')}"
        row["edit_url"] = f"/locations/{row.get('id')}/edit"
    return render_dashboard(
        "仓库档案",
        "维护仓库编码、名称、库位配置和启停状态；库存余额、金额和流水请到库存查询页面处理。",
        metrics,
        shortcuts,
        [
            {
                "title": "仓库列表",
                "rows": warehouses,
                "columns": columns(("code", "编码"), ("name", "仓库"), ("category_name", "分类"), ("warehouse_type", "类型"), ("status", "状态"), ("default_location_name", "默认库位"), ("location_count", "库位数"), ("active_location_count", "启用库位"), ("config_status", "配置状态"), ("remark", "备注")),
                "detail_base": back_url,
                "detail_label": "仓库详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/warehouse/new",
                "import_url": "/warehouse/import",
                "template_url": "/warehouse/download_template",
                "export_url": "/export/warehouses",
            },
            {
                "title": "库位配置",
                "rows": location_rows,
                "columns": columns(("code", "库位编码"), ("name", "库位"), ("location_type", "类型"), ("warehouse_name", "所属仓库"), ("status_label", "状态"), ("remark", "备注")),
                "detail_base": "/locations",
                "detail_label": "库位详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/location/new",
            },
        ],
    )


def render_location_dashboard(query_rows, query_one, count_rows, render_dashboard, columns, request_args, back_url="/locations"):
    keyword = (request_args.get("keyword") or request_args.get("q") or "").strip()
    warehouse_id = (request_args.get("warehouse_id") or "").strip()
    where_parts = []
    params = []
    keyword_clause, keyword_params = _keyword_clause("l", ["code", "name", "location_type", "status", "remark"], keyword)
    if keyword_clause:
        where_parts.append(f"({keyword_clause} OR w.name ILIKE %s)")
        params.extend(keyword_params + [f"%{keyword}%"])
    if warehouse_id.isdigit():
        where_parts.append("l.warehouse_id=%s")
        params.append(int(warehouse_id))
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    summary = query_one(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE COALESCE(status, CASE WHEN COALESCE(is_active, true) THEN '启用' ELSE '停用' END) NOT IN ('停用','disabled')) AS active_count,
               COUNT(DISTINCT warehouse_id) AS warehouse_count
        FROM locations
        """
    ) or {}
    metrics = [
        {"label": "库位数", "value": summary.get("total", 0), "hint": "全部库位"},
        {"label": "启用库位", "value": summary.get("active_count", 0), "hint": "可用于业务单据"},
        {"label": "覆盖仓库", "value": summary.get("warehouse_count", 0), "hint": "已建库位的仓库数"},
        {"label": "未分配库位", "value": count_rows("locations", "warehouse_id IS NULL"), "hint": "需要补充所属仓库"},
    ]
    shortcuts = []
    rows = query_rows(
        f"""
        SELECT l.id, l.code, l.name, l.location_type, l.is_active, l.status, l.remark,
               w.id AS warehouse_id, w.name AS warehouse_name,
               COALESCE(l.status, CASE WHEN COALESCE(l.is_active, true) THEN '启用' ELSE '停用' END) AS status_label
        FROM locations l
        LEFT JOIN warehouses w ON w.id=l.warehouse_id
        {where_sql}
        ORDER BY w.name NULLS LAST, l.code
        LIMIT 200
        """,
        tuple(params),
    )
    rows = _filter_master_rows(rows, "code", "name", "location_type", "warehouse_name", "remark")
    rows = _clean_rows(rows, "code", "name", "location_type", "warehouse_name", "status_label", "remark")
    for row in rows:
        row["detail_url"] = f"/locations/{row.get('id')}"
        row["edit_url"] = f"/locations/{row.get('id')}/edit"
    return render_dashboard(
        "库位档案",
        "维护库位编码、所属仓库和启停状态；库存余额和流水请到库存查询页面处理。",
        metrics,
        shortcuts,
        [
            {
                "title": "库位列表",
                "rows": rows,
                "columns": columns(("code", "编码"), ("name", "库位"), ("location_type", "类型"), ("warehouse_name", "所属仓库"), ("status_label", "状态"), ("remark", "备注")),
                "detail_base": back_url,
                "detail_label": "库位详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/location/new",
                "import_url": "/location/import",
                "template_url": "/location/download_template",
                "export_url": "/export/locations",
            }
        ],
    )


def render_warehouse_detail(warehouse_id, query_one, query_rows, count_rows, back_url="/warehouse"):
    warehouse = query_one(
        """
        SELECT w.*, wc.name AS category_name, dl.code || ' / ' || dl.name AS default_location_name
        FROM warehouses w
        LEFT JOIN warehouse_categories wc ON wc.id=w.category_id
        LEFT JOIN locations dl ON dl.id=w.default_location_id
        WHERE w.id=%s
        """,
        (warehouse_id,),
    )
    if not warehouse:
        return render_template("simple_detail.html", title="仓库详情", row=None, back_url=back_url, labels={})
    location_summary = query_one(
        """
        SELECT COUNT(*) AS location_count,
               COUNT(*) FILTER (WHERE COALESCE(is_active, true)) AS active_location_count
        FROM locations
        WHERE warehouse_id=%s
        """,
        (warehouse_id,),
    ) or {}
    context = {
        "back_url": back_url,
        "delete_url": f"/warehouse/{warehouse_id}/delete",
        "warehouse": warehouse,
        "metrics": [
            {"label": "库位数", "value": location_summary.get("location_count", 0), "hint": "当前仓库库位"},
            {"label": "启用库位", "value": location_summary.get("active_location_count", 0), "hint": "可用于业务单据"},
            {"label": "销售订单引用", "value": count_rows("sales_orders", "warehouse_id=%s", (warehouse_id,)), "hint": "使用该仓库的销售订单"},
            {"label": "采购单引用", "value": count_rows("purchase_orders", "warehouse_id=%s", (warehouse_id,)), "hint": "使用该仓库的采购单"},
        ],
        "locations": query_rows(
            """
            SELECT l.id, l.code, l.name, l.location_type, l.is_active,
                   COALESCE(l.status, CASE WHEN COALESCE(l.is_active, true) THEN '启用' ELSE '停用' END) AS status_label,
                   l.remark
            FROM locations l
            WHERE l.warehouse_id=%s
            ORDER BY l.code
            LIMIT 100
            """,
            (warehouse_id,),
        ),
    }
    context["locations"] = _filter_master_rows(context["locations"], "code", "name", "remark")
    context["locations"] = _clean_rows(context["locations"], "code", "name", "location_type", "status_label", "remark")
    return render_template("warehouse_trace_detail.html", **context)


def render_location_detail(location_id, query_one, query_rows, columns, qty_metric, money_metric, back_url="/locations"):
    location = query_one(
        """
        SELECT l.*, w.id AS warehouse_id, w.code AS warehouse_code, w.name AS warehouse_name
        FROM locations l
        LEFT JOIN warehouses w ON w.id=l.warehouse_id
        WHERE l.id=%s
        """,
        (location_id,),
    )
    if not location:
        return render_template("simple_detail.html", title="库位详情", row=None, back_url=back_url, labels={})
    summary = query_one(
        """
        SELECT COUNT(DISTINCT product_id) AS product_count,
               COALESCE(SUM(quantity), 0) AS stock_qty,
               COALESCE(SUM(locked_qty), 0) AS locked_qty,
               COALESCE(SUM(quantity * COALESCE(unit_cost, 0)), 0) AS stock_value
        FROM inventory_balances
        WHERE location_id=%s
        """,
        (location_id,),
    ) or {}
    status_label = location.get("status") or ("启用" if location.get("is_active", True) else "停用")
    metrics = [
        {"label": "物料数", "value": summary.get("product_count", 0), "hint": "当前库位"},
        {"label": "库存数量", "value": qty_metric(summary.get("stock_qty", 0)), "hint": f"锁定 {qty_metric(summary.get('locked_qty', 0))}"},
        {"label": "库存金额", "value": money_metric(summary.get("stock_value", 0)), "hint": "按余额成本估算"},
        {"label": "状态", "value": status_label, "hint": "库位可用状态"},
    ]
    info_rows = [
        ("编码", location.get("code")),
        ("名称", location.get("name")),
        ("所属仓库", location.get("warehouse_name")),
        ("仓库编码", location.get("warehouse_code")),
        ("库位类型", location.get("location_type")),
        ("状态", status_label),
        ("备注", location.get("remark")),
    ]
    sections = [
        {
            "title": "库存余额",
            "rows": query_rows(
                """
                SELECT ib.id, p.code AS product_code, p.name AS product_name, p.specification,
                       ib.lot_no, ib.cabinet_no, ib.quantity, ib.locked_qty, ib.unit_cost
                FROM inventory_balances ib
                LEFT JOIN products p ON p.id=ib.product_id
                WHERE ib.location_id=%s
                ORDER BY ib.quantity DESC, ib.id DESC
                LIMIT 80
                """,
                (location_id,),
            ),
            "columns": columns(("product_code", "物料编码"), ("product_name", "物料名称"), ("specification", "规格"), ("lot_no", "批号"), ("cabinet_no", "柜号"), ("quantity", "数量"), ("locked_qty", "锁定"), ("unit_cost", "单位成本")),
            "detail_base": "/inventory/detail",
        },
        {
            "title": "最近库存流水",
            "rows": query_rows(
                """
                SELECT st.id, st.transaction_date, st.transaction_type, p.code AS product_code,
                       p.name AS product_name, st.quantity, st.reference_no, st.lot_no, st.cabinet_no
                FROM stock_transactions st
                LEFT JOIN products p ON p.id=st.product_id
                WHERE st.location_id=%s
                ORDER BY st.id DESC
                LIMIT 60
                """,
                (location_id,),
            ),
            "columns": columns(("transaction_date", "日期"), ("transaction_type", "类型"), ("product_code", "物料编码"), ("product_name", "物料名称"), ("quantity", "数量"), ("reference_no", "来源"), ("lot_no", "批号"), ("cabinet_no", "柜号")),
            "detail_base": "/transactions",
        },
    ]
    return render_template(
        "basic_data_detail.html",
        title="库位详情",
        kind="location",
        record=location,
        record_name=f"{location.get('code') or ''} {location.get('name') or ''}".strip(),
        record_id=location_id,
        back_url=back_url,
        edit_url=f"/location/{location_id}/edit",
        delete_url=f"/location/{location_id}/delete",
        info_rows=info_rows,
        metrics=metrics,
        sections=sections,
    )
