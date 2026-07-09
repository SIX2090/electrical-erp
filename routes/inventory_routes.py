"""Inventory module routes: dashboard, stock balance, transactions, and adjustments."""
from decimal import Decimal
from datetime import datetime

from flask import g, render_template, request

from .document_print_routes import build_template_grid_for_document


def as_decimal(value):
    try:
        return Decimal(str(value if value is not None else "0"))
    except Exception:
        return Decimal("0")


def money_metric(value):
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def qty_metric(value):
    try:
        return f"{float(value or 0):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "0"


def manufacturing_control_text(row):
    labels = []
    if row.get("batch_control"):
        labels.append("批次")
    if row.get("serial_control"):
        labels.append("序列")
    if row.get("inspection_required"):
        labels.append("需检")
    return " / ".join(labels) if labels else "-"


def bom_display_text(row):
    parts = [row.get("default_bom_no"), row.get("default_bom_version")]
    return " / ".join(str(part) for part in parts if part) or "-"


def inventory_filter_context(args=None):
    args = args or request.args
    keyword = (args.get("keyword") or args.get("q") or args.get("search") or "").strip()
    warehouse_id = (args.get("warehouse_id") or "").strip()
    project_code = (args.get("project_code") or "").strip()
    stock_state = (args.get("stock_state") or "").strip()
    where_parts = []
    params = []
    if keyword:
        where_parts.append(
            """
            (p.code ILIKE %s OR p.name ILIKE %s OR p.specification ILIKE %s
             OR ib.project_code ILIKE %s OR ib.lot_no ILIKE %s OR ib.serial_no ILIKE %s OR w.name ILIKE %s OR l.code ILIKE %s)
            """
        )
        params.extend([f"%{keyword}%"] * 8)
    if project_code:
        where_parts.append("ib.project_code ILIKE %s")
        params.append(f"%{project_code}%")
    if warehouse_id.isdigit():
        where_parts.append("ib.warehouse_id=%s")
        params.append(int(warehouse_id))
    if stock_state == "locked":
        where_parts.append("COALESCE(ib.locked_qty,0) > 0")
    elif stock_state == "available":
        where_parts.append("GREATEST(COALESCE(ib.quantity,0)-COALESCE(ib.locked_qty,0),0) > 0")
    elif stock_state == "zero":
        where_parts.append("COALESCE(ib.quantity,0) <= 0")
    elif stock_state == "low":
        where_parts.append("COALESCE(p.safety_stock,0) > 0 AND COALESCE(total_stock.stock_qty,0) < COALESCE(p.safety_stock,0)")
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return keyword, warehouse_id, project_code, stock_state, where_sql, tuple(params)


def stock_transaction_filter_context(args=None):
    args = args or request.args
    keyword = (args.get("keyword") or args.get("q") or args.get("search") or "").strip()
    tx_type = (args.get("transaction_type") or "").strip()
    project_code = (args.get("project_code") or "").strip()
    date_from = (args.get("date_from") or args.get("date_start") or "").strip()
    date_to = (args.get("date_to") or args.get("date_end") or "").strip()
    where_parts = []
    params = []
    if keyword:
        where_parts.append(
            "(p.code ILIKE %s OR p.name ILIKE %s OR st.reference_no ILIKE %s OR st.project_code ILIKE %s OR st.lot_no ILIKE %s OR st.serial_no ILIKE %s)"
        )
        params.extend([f"%{keyword}%"] * 6)
    if tx_type:
        where_parts.append("COALESCE(st.transaction_type, '')=%s")
        params.append(tx_type)
    if project_code:
        where_parts.append("st.project_code ILIKE %s")
        params.append(f"%{project_code}%")
    if date_from:
        where_parts.append("st.transaction_date >= %s")
        params.append(date_from)
    if date_to:
        where_parts.append("st.transaction_date <= %s")
        params.append(date_to)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return keyword, tx_type, project_code, where_sql, tuple(params), date_from, date_to


def render_inventory_dashboard(query_rows, query_one):
    keyword, warehouse_id, project_code, stock_state, where_sql, params = inventory_filter_context()
    stock_summary = query_one(
        """
        SELECT COUNT(DISTINCT product_id) AS product_count,
               COUNT(*) AS balance_rows,
               COALESCE(SUM(quantity), 0) AS stock_qty,
               COALESCE(SUM(locked_qty), 0) AS locked_qty,
               COALESCE(SUM(quantity * COALESCE(unit_cost,0)), 0) AS stock_value
        FROM inventory_balances
        """
    ) or {}
    low_stock_count = query_one(
        """
        WITH stock AS (
            SELECT product_id, COALESCE(SUM(quantity), 0) AS stock_qty
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT COUNT(*) AS value
        FROM products p
        LEFT JOIN stock ON stock.product_id=p.id
        WHERE COALESCE(p.safety_stock,0) > 0 AND COALESCE(stock.stock_qty,0) < COALESCE(p.safety_stock,0)
        """
    ) or {}
    pending_post_count = query_one(
        """
        WITH pending_docs AS (
            SELECT adj_no AS doc_no FROM inventory_adjustments
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            UNION ALL
            SELECT transfer_no AS doc_no FROM transfer_orders
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            UNION ALL
            SELECT check_no AS doc_no FROM inventory_check_orders
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
        )
        SELECT COUNT(DISTINCT doc_no) AS value FROM pending_docs
        """
    ) or {}
    project_gap_count = query_one(
        """
        SELECT COUNT(*) AS value
        FROM mrp_requirements
        WHERE COALESCE(shortage_quantity, 0) > 0
          AND (COALESCE(project_code, '') <> '' OR COALESCE(serial_no, '') <> '')
        """
    ) or {}
    metrics = [
        {"label": "待过账单据", "value": pending_post_count.get("value", 0), "hint": "调拨、盘点、调整需先闭环"},
        {"label": "库存异常", "value": low_stock_count.get("value", 0), "hint": "低于安全库存或可用不足"},
        {"label": "项目/机号缺口", "value": project_gap_count.get("value", 0), "hint": "按 MRP 缺料追踪"},
        {"label": "库存金额", "value": money_metric(stock_summary.get("stock_value", 0)), "hint": f"库存数量 {qty_metric(stock_summary.get('stock_qty', 0))}"},
    ]
    pending_documents = query_rows(
        """
        WITH docs AS (
            SELECT MIN(id) AS id, '库存调整' AS doc_type, adj_no AS doc_no, MAX(adj_date) AS doc_date,
                   MAX(project_code) AS project_code, MAX(serial_no) AS serial_no, MAX(status) AS status,
                   COUNT(*) AS line_count, SUM(ABS(COALESCE(diff_quantity,0))) AS qty,
                   '/adjustments' AS detail_base
            FROM inventory_adjustments
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            GROUP BY adj_no
            UNION ALL
            SELECT tr.id, '库存调拨', tr.transfer_no, tr.transfer_date,
                   tr.project_code, NULL::VARCHAR AS serial_no, tr.status,
                   COALESCE(items.line_count, 0), COALESCE(items.qty, 0), '/transfers'
            FROM transfer_orders tr
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS line_count, SUM(COALESCE(quantity,0)) AS qty
                FROM transfer_order_items ti
                WHERE ti.transfer_id=tr.id
            ) items ON TRUE
            WHERE COALESCE(tr.status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            UNION ALL
            SELECT ico.id, '库存盘点', ico.check_no, ico.check_date,
                   ico.project_code, NULL::VARCHAR AS serial_no, ico.status,
                   COALESCE(items.line_count, 0), COALESCE(items.qty, 0), '/inventory_checks'
            FROM inventory_check_orders ico
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS line_count, SUM(ABS(COALESCE(diff_qty,0))) AS qty
                FROM inventory_check_order_items ci
                WHERE ci.check_id=ico.id
            ) items ON TRUE
            WHERE COALESCE(ico.status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
        )
        SELECT *,
               CASE
                   WHEN doc_type='库存调拨' THEN '确认调出/调入仓库并过账'
                   WHEN doc_type='库存盘点' THEN '复核差异并生成过账'
                   ELSE '复核差异原因并过账'
               END AS next_step,
               '仓库主管' AS owner_role,
               CASE
                   WHEN COALESCE(project_code,'')='' THEN '缺项目号，无法追踪项目库存'
                   ELSE '等待仓库审核/过账'
               END AS blocked_reason,
               '影响可用库存、领料、完工入库和成本核算' AS downstream_impact
        FROM docs
        ORDER BY doc_date DESC NULLS LAST, id DESC
        LIMIT 30
        """
    )
    for row in pending_documents:
        row["detail_url"] = f"{row.get('detail_base')}/{row.get('id')}"
    balances = query_rows(
        f"""
        WITH total_stock AS (
            SELECT product_id, COALESCE(SUM(quantity), 0) AS stock_qty
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT ib.id, ib.product_id, p.code AS product_code, p.name AS product_name,
               p.specification, COALESCE(p.unit, '') AS unit, p.safety_stock,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               ib.project_code,
               ib.lot_no, ib.serial_no, ib.quantity, ib.locked_qty,
               GREATEST(COALESCE(ib.quantity,0)-COALESCE(ib.locked_qty,0),0) AS available_qty,
               ib.unit_cost, COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) AS stock_value,
               CASE
                   WHEN COALESCE(ib.quantity,0) <= 0 THEN '零库存'
                   WHEN COALESCE(p.safety_stock,0) > 0 AND COALESCE(total_stock.stock_qty,0) < COALESCE(p.safety_stock,0) THEN '低库存'
                   WHEN COALESCE(ib.locked_qty,0) > 0 THEN '有锁定'
                   ELSE '正常'
               END AS stock_state
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        LEFT JOIN total_stock ON total_stock.product_id=ib.product_id
        {where_sql}
        ORDER BY
            CASE
                WHEN COALESCE(p.safety_stock,0) > 0 AND COALESCE(total_stock.stock_qty,0) < COALESCE(p.safety_stock,0) THEN 0
                WHEN COALESCE(ib.locked_qty,0) > 0 THEN 1
                ELSE 2
            END,
            ib.id DESC
        LIMIT 120
        """,
        params,
    )
    low_stock_rows = query_rows(
        """
        WITH stock AS (
            SELECT product_id,
                   COALESCE(SUM(quantity), 0) AS stock_qty,
                   COALESCE(SUM(locked_qty), 0) AS locked_qty
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT p.id, p.code AS product_code, p.name AS product_name, p.specification,
               p.unit, p.safety_stock,
               COALESCE(stock.stock_qty, 0) AS stock_qty,
               GREATEST(COALESCE(p.safety_stock,0)-COALESCE(stock.stock_qty,0),0) AS shortage_qty,
               p.default_supplier_name
        FROM products p
        LEFT JOIN stock ON stock.product_id=p.id
        WHERE COALESCE(p.safety_stock,0) > 0
          AND COALESCE(stock.stock_qty,0) < COALESCE(p.safety_stock,0)
        ORDER BY shortage_qty DESC, p.code
        LIMIT 50
        """
    )
    transactions = query_rows(
        """
        SELECT st.id, st.transaction_date, st.transaction_type, p.code AS product_code,
               p.name AS product_name, w.name AS warehouse_name, l.code AS location_code,
               st.quantity, st.unit_cost, st.reference_no, st.lot_no, st.serial_no, st.project_code
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        LEFT JOIN warehouses w ON w.id=st.warehouse_id
        LEFT JOIN locations l ON l.id=st.location_id
        ORDER BY st.id DESC
        LIMIT 40
        """
    )
    alerts = query_rows(
        """
        SELECT ia.id, ia.alert_type, ia.alert_level, ia.current_qty, ia.threshold_qty,
               ia.is_resolved, ia.created_at, p.code AS product_code, p.name AS product_name,
               w.name AS warehouse_name
        FROM inventory_alerts ia
        LEFT JOIN products p ON p.id=ia.product_id
        LEFT JOIN warehouses w ON w.id=ia.warehouse_id
        WHERE COALESCE(ia.is_resolved, FALSE)=FALSE
        ORDER BY ia.created_at DESC NULLS LAST, ia.id DESC
        LIMIT 40
        """
    )
    batches = query_rows(
        """
        SELECT bt.id, bt.lot_no, p.code AS product_code, p.name AS product_name,
               w.name AS warehouse_name, bt.location, bt.location_id, bt.project_code, bt.serial_no, bt.quantity_available,
               bt.expiry_date, bt.supplier_id, bt.source_order_no, bt.status
        FROM batch_tracking bt
        LEFT JOIN products p ON p.id=bt.product_id
        LEFT JOIN warehouses w ON w.id=bt.warehouse_id
        WHERE COALESCE(bt.quantity_available, 0) <> 0
        ORDER BY bt.expiry_date NULLS LAST, bt.id DESC
        LIMIT 40
        """
    )
    return render_template(
        "inventory_dashboard.html",
        title="库存工作台",
        subtitle="库存余额、批次机号和出入库流水",
        metrics=metrics,
        pending_documents=pending_documents,
        balances=balances,
        low_stock_rows=low_stock_rows,
        transactions=transactions,
        alerts=alerts,
        batches=batches,
        warehouses=query_rows("SELECT id, name FROM warehouses ORDER BY name LIMIT 200"),
        filters={"keyword": keyword, "warehouse_id": warehouse_id, "project_code": project_code, "stock_state": stock_state},
    )


def render_inventory_balance_dashboard(query_rows, back_url="/inventory/detail", title="库存明细"):
    keyword, warehouse_id, project_code, stock_state, where_sql, params = inventory_filter_context()
    rows = query_rows(
        f"""
        WITH total_stock AS (
            SELECT product_id, COALESCE(SUM(quantity), 0) AS stock_qty
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT ib.id, p.code AS product_code, p.name AS product_name, p.specification,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               ib.project_code,
               ib.lot_no, ib.serial_no, ib.quantity, ib.locked_qty,
               GREATEST(COALESCE(ib.quantity,0)-COALESCE(ib.locked_qty,0),0) AS available_qty,
               ib.unit_cost, COALESCE(ib.quantity,0) * COALESCE(ib.unit_cost,0) AS stock_value,
               ib.expire_date, ib.updated_at,
               CASE
                   WHEN COALESCE(ib.quantity,0) <= 0 THEN '零库存'
                   WHEN COALESCE(p.safety_stock,0) > 0 AND COALESCE(total_stock.stock_qty,0) < COALESCE(p.safety_stock,0) THEN '低库存'
                   WHEN COALESCE(ib.locked_qty,0) > 0 THEN '有锁定'
                   ELSE '正常'
               END AS stock_state
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        LEFT JOIN total_stock ON total_stock.product_id=ib.product_id
        {where_sql}
        ORDER BY ib.id DESC
        LIMIT 300
        """,
        params,
    )
    return render_template(
        "inventory_balance_dashboard.html",
        title=title,
        subtitle="按物料、项目号、仓库、库位、批号、机号查看可用库存。",
        rows=rows,
        warehouses=query_rows("SELECT id, name FROM warehouses ORDER BY name LIMIT 200"),
        filters={"keyword": keyword, "warehouse_id": warehouse_id, "project_code": project_code, "stock_state": stock_state},
        back_url=back_url,
    )


def render_stock_transaction_dashboard(query_rows, clean_rows=None, clean_text=None):
    keyword, tx_type, project_code, where_sql, params, date_from, date_to = stock_transaction_filter_context()
    clean_rows = clean_rows or (lambda rows, *keys: rows)
    clean_text = clean_text or (lambda value, default="-": value or default)
    rows = query_rows(
        f"""
        SELECT st.id, st.transaction_date, st.transaction_type, p.code AS product_code,
               p.name AS product_name, w.name AS warehouse_name, l.code AS location_code,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               st.quantity, st.unit_cost, st.reference_no, st.source_type, st.lot_no, st.serial_no, st.project_code, st.remark
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        LEFT JOIN warehouses w ON w.id=st.warehouse_id
        LEFT JOIN locations l ON l.id=st.location_id
        {where_sql}
        ORDER BY st.id DESC
        LIMIT 300
        """,
        params,
    )
    rows = clean_rows(rows, "transaction_type", "product_code", "product_name", "remark")
    for row in rows:
        row["transaction_type"] = clean_text(row.get("transaction_type"), "未知类型")
    types = clean_rows(
        query_rows(
            """
            SELECT transaction_type, COUNT(*) AS count
            FROM stock_transactions
            WHERE COALESCE(transaction_type, '') <> ''
            GROUP BY transaction_type
            ORDER BY count DESC, transaction_type
            """
        ),
        "transaction_type",
    )
    return render_template(
        "inventory_transactions.html",
        title="库存流水",
        subtitle="按来源单号、物料、项目号、批号、机号追踪出入库。",
        rows=rows,
        types=types,
        filters={"keyword": keyword, "transaction_type": tx_type, "project_code": project_code, "date_from": date_from, "date_to": date_to},
    )


def inventory_document_product_options(query_rows, clean_rows=None):
    rows = query_rows(
        """
        SELECT p.id, p.code, p.name, p.specification, p.unit, p.standard_price,
               COALESCE(stock.available_qty, 0) AS available_qty,
               COALESCE(stock.unit_cost, p.standard_price, 0) AS unit_cost,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               CONCAT_WS(' / ', NULLIF(p.code,''), NULLIF(p.name,''), NULLIF(p.specification,'')) AS display_name
        FROM products p
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                SUM(COALESCE(ib.quantity,0)-COALESCE(ib.locked_qty,0)) AS available_qty,
                MAX(NULLIF(ib.unit_cost, 0)) AS unit_cost
            FROM inventory_balances ib
            WHERE ib.product_id=p.id
        ) stock ON TRUE
        WHERE COALESCE(p.status, '') NOT IN ('禁用','disabled')
        ORDER BY p.id DESC
        LIMIT 3000
        """
    )
    if clean_rows:
        rows = clean_rows(rows, "code", "name", "specification")
    return rows


def _inventory_form_options(query_rows, product_options=None, clean_rows=None):
    if callable(product_options):
        product_rows = product_options()
    elif product_options is not None:
        product_rows = product_options
    else:
        product_rows = inventory_document_product_options(query_rows, clean_rows)
    warehouses = query_rows(
        """
        SELECT id, code, name
        FROM warehouses
        WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
        ORDER BY id DESC
        LIMIT 1000
        """
    )
    locations = query_rows(
        """
        SELECT id, warehouse_id, code, code || ' / ' || name AS name
        FROM locations
        WHERE COALESCE(is_active, TRUE)=TRUE
        ORDER BY code
        LIMIT 1000
        """
    )
    if clean_rows:
        warehouses = clean_rows(warehouses, "code", "name")
        locations = clean_rows(locations, "code", "name")
    return {
        "warehouses": warehouses,
        "locations": locations,
        "product_options": product_rows,
        "material_opening": {
            "title": "物料期初",
            "action_url": "/inventory/opening/new",
            "prefix": "MO",
            "placeholder": "录入上线盘点库存、批号、机号、项目号和期初单位成本。",
            "back_url": "/inventory/opening",
            "allow_unit_cost_edit": True,
            "grid_key": "material_opening_items",
        },
    }


def render_inventory_movement_form(direction, query_rows, next_doc_no, product_options=None, clean_rows=None, movement_kind=None):
    is_inbound = direction == "in"
    movement_kind = movement_kind or ("other_inbound" if is_inbound else "other_outbound")
    if movement_kind in {"other_inbound", "other_outbound"}:
        g.toolbar_extras = []
    configs = {
        "sales_return": {
            "title": "出库退货入库",
            "action_url": "/inventory/inbound/new?return_type=sales_return",
            "prefix": "SRI",
            "placeholder": "例如：客户退货、发货退回、售后返件",
        },
        "purchase_return": {
            "title": "入库退货出库",
            "action_url": "/inventory/outbound/new?return_type=purchase_return",
            "prefix": "PRO",
            "placeholder": "例如：来料不良退供应商、采购退货出库",
        },
        "other_inbound": {
            "title": "其他入库",
            "action_url": "/inventory/inbound/new",
            "prefix": "OI",
            "placeholder": "例如：盘盈入库、样品入库、借用归还",
        },
        "other_outbound": {
            "title": "其他出库",
            "action_url": "/inventory/outbound/new",
            "prefix": "OO",
            "placeholder": "例如：生产辅料领用、部门领用、费用领料、报废出库",
        },
    }
    config = configs.get(movement_kind) or configs["other_inbound" if is_inbound else "other_outbound"]
    context = _inventory_form_options(query_rows, product_options, clean_rows)
    context.update(
        {
            "is_inbound": is_inbound,
            "title": config["title"],
            "action_url": config["action_url"],
            "reference_no": next_doc_no(
                config["prefix"],
                "inventory_movement_documents" if movement_kind in {"other_inbound", "other_outbound"} else "stock_transactions",
                "doc_no" if movement_kind in {"other_inbound", "other_outbound"} else "reference_no",
            ),
            "remark_placeholder": config["placeholder"],
            "movement_kind": movement_kind,
            "back_url": config.get("back_url", "/inventory/detail"),
            "allow_unit_cost_edit": bool(config.get("allow_unit_cost_edit")),
            "grid_key": config.get("grid_key") or ("other_inbound_items" if is_inbound else "other_outbound_items"),
        }
    )
    return render_template("inventory_movement_form.html", **context)


def render_inventory_adjustment_form(query_rows, product_options=None, clean_rows=None, order=None, items=None, action_url="/adjustments/new", mode="new"):
    g.toolbar_extras = []
    context = _inventory_form_options(query_rows, product_options, clean_rows)
    context.update({"order": order or {}, "items": items or [], "action_url": action_url, "mode": mode})
    return render_template("inventory_adjustment_form.html", **context)


def render_inventory_transfer_form(query_rows, product_options=None, clean_rows=None, order=None, items=None, action_url="/transfers/new", mode="new"):
    g.toolbar_extras = []
    context = _inventory_form_options(query_rows, product_options, clean_rows)
    context.update({"order": order or {}, "items": items or [], "action_url": action_url, "mode": mode})
    return render_template("inventory_transfer_form.html", **context)


def render_inventory_check_form(query_rows, product_options=None, clean_rows=None, order=None, items=None, action_url="/inventory_checks/new", mode="new"):
    g.toolbar_extras = []
    context = _inventory_form_options(query_rows, product_options, clean_rows)
    context.update({"order": order or {}, "items": items or [], "action_url": action_url, "mode": mode})
    return render_template("inventory_check_form.html", **context)


def render_inventory_balance_detail(query_one, query_rows, balance_id, back_url="/inventory/detail"):
    balance = query_one(
        """
        SELECT ib.*, p.code AS product_code, p.name AS product_name, p.specification, p.unit,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        WHERE ib.id=%s
        """,
        (balance_id,),
    )
    if not balance:
        return render_template("simple_detail.html", title="库存明细", row=None, back_url=back_url, labels={})
    transactions = query_rows(
        """
        SELECT id, transaction_date, transaction_type, quantity, unit_cost, reference_no, lot_no, serial_no, remark
        FROM stock_transactions
        WHERE product_id=%s
          AND COALESCE(warehouse_id, 0)=COALESCE(%s, 0)
          AND COALESCE(location_id, 0)=COALESCE(%s, 0)
          AND COALESCE(lot_no, '')=COALESCE(%s, '')
          AND COALESCE(serial_no, '')=COALESCE(%s, '')
        ORDER BY id DESC
        LIMIT 80
        """,
        (
            balance.get("product_id"),
            balance.get("warehouse_id"),
            balance.get("location_id"),
            balance.get("lot_no"),
            balance.get("serial_no"),
        ),
    )
    quantity = as_decimal(balance.get("quantity"))
    locked_qty = as_decimal(balance.get("locked_qty"))
    unit_cost = as_decimal(balance.get("unit_cost"))
    return render_template(
        "inventory_balance_detail.html",
        back_url=back_url,
        balance=balance,
        metrics=[
            {"label": "库存数量", "value": qty_metric(quantity), "hint": balance.get("unit") or ""},
            {"label": "可用数量", "value": qty_metric(quantity - locked_qty), "hint": "库存 - 锁定"},
            {"label": "单位成本", "value": money_metric(unit_cost), "hint": "当前余额成本"},
            {"label": "库存金额", "value": money_metric(quantity * unit_cost), "hint": "数量 * 单位成本"},
        ],
        transactions=transactions,
    )


def stock_transactions_for_reference(query_rows, reference_no, source_type=None):
    if not reference_no:
        return []
    source_filter = "AND COALESCE(st.source_type,'')=COALESCE(%s,'')" if source_type else ""
    params = (reference_no, source_type) if source_type else (reference_no,)
    return query_rows(
        f"""
        SELECT st.id, st.transaction_date, st.transaction_type, st.quantity, st.unit_cost,
               COALESCE(st.amount, COALESCE(st.quantity,0) * COALESCE(st.unit_cost,0)) AS amount,
               st.reference_no, st.source_type, st.lot_no, st.serial_no, st.location, st.remark,
               p.code AS product_code, p.name AS product_name, p.specification, p.unit,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        LEFT JOIN warehouses w ON w.id=st.warehouse_id
        LEFT JOIN locations l ON l.id=st.location_id
        WHERE st.reference_no=%s
        {source_filter}
        ORDER BY st.id DESC
        """,
        params,
    )


def render_inventory_adjustment_detail(
    adjustment_id,
    query_one,
    query_rows,
    as_decimal_value,
    document_attachments,
    document_activity_logs,
    load_custom_payload,
    back_url="/adjustments",
):
    order = query_one(
        """
        SELECT ia.*, ia.adj_no AS doc_no,
               p.code AS product_code, p.name AS product_name, p.specification, p.unit,
               w.name AS warehouse_name, l.code AS location_code, l.name AS location_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required
        FROM inventory_adjustments ia
        LEFT JOIN products p ON p.id=ia.product_id
        LEFT JOIN warehouses w ON w.id=ia.warehouse_id
        LEFT JOIN locations l ON l.id=ia.location_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE ia.id=%s
        """,
        (adjustment_id,),
    )
    if not order:
        return render_template("simple_detail.html", title="库存调整详情", row=None, back_url=back_url, labels={})
    items = query_rows(
        """
        SELECT ia.*, p.code AS product_code, p.name AS product_name, p.specification, p.unit,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               ia.diff_quantity AS quantity,
               (COALESCE(ia.diff_quantity,0) * COALESCE(ia.unit_cost,0)) AS amount
        FROM inventory_adjustments ia
        LEFT JOIN products p ON p.id=ia.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE ia.adj_no=%s
        ORDER BY ia.id
        """,
        (order.get("doc_no"),),
    )
    return render_template(
        "inventory_document_detail.html",
        doc_type="adjustment",
        title="库存调整详情",
        back_url=back_url,
        order=order,
        number=order.get("doc_no"),
        date=order.get("adj_date"),
        items=items,
        transactions=stock_transactions_for_reference(query_rows, order.get("doc_no"), "inventory_adjustment"),
        print_url=f"/adjustments/{adjustment_id}/print",
        doc_kind="inventory_adjustment",
        action_prefix="/adjustments",
        attachments=document_attachments("inventory_adjustment", adjustment_id),
        activity_logs=document_activity_logs("inventory_adjustment", order),
        custom_fields_payload=load_custom_payload("inventory_adjustment", adjustment_id),
    )


def render_inventory_transfer_detail(
    transfer_id,
    query_one,
    query_rows,
    ensure_transfer_items,
    document_attachments,
    document_activity_logs,
    load_custom_payload,
    back_url="/transfers",
):
    ensure_transfer_items()
    order = query_one(
        """
        SELECT tr.*, fw.name AS from_warehouse_name, tw.name AS to_warehouse_name,
               fl.code AS from_location_code, fl.name AS from_location_name,
               tl.code AS to_location_code, tl.name AS to_location_name
        FROM transfer_orders tr
        LEFT JOIN warehouses fw ON fw.id=tr.from_warehouse_id
        LEFT JOIN warehouses tw ON tw.id=tr.to_warehouse_id
        LEFT JOIN locations fl ON fl.id=tr.from_location_id
        LEFT JOIN locations tl ON tl.id=tr.to_location_id
        WHERE tr.id=%s
        """,
        (transfer_id,),
    )
    if not order:
        return render_template("simple_detail.html", title="库存调拨详情", row=None, back_url=back_url, labels={})
    items = query_rows(
        """
        SELECT ti.*, p.code AS product_code, p.name AS product_name, p.specification, p.unit,
               fwl.name AS from_warehouse_name, twl.name AS to_warehouse_name,
               fl.code AS from_location_code, fl.name AS from_location_name,
               tl.code AS to_location_code, tl.name AS to_location_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               (COALESCE(ti.quantity,0) * COALESCE(ti.unit_cost,0)) AS amount
        FROM transfer_order_items ti
        LEFT JOIN products p ON p.id=ti.product_id
        LEFT JOIN warehouses fwl ON fwl.id=ti.from_warehouse_id
        LEFT JOIN warehouses twl ON twl.id=ti.to_warehouse_id
        LEFT JOIN locations fl ON fl.id=ti.from_location_id
        LEFT JOIN locations tl ON tl.id=ti.to_location_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE ti.transfer_id=%s
        ORDER BY ti.id
        """,
        (transfer_id,),
    )
    # E-1: Cross-warehouse transfer approval info (now line-level: any line cross-warehouse)
    is_cross_warehouse = any(
        (row.get("from_warehouse_id") and row.get("to_warehouse_id")
         and row.get("from_warehouse_id") != row.get("to_warehouse_id"))
        for row in items
    )
    approval_status = order.get("approval_status") or "not_required"
    approval_actions = {}
    if is_cross_warehouse and order.get("status") in ("待过账", "草稿", "", None):
        approval_actions["can_post"] = True
    else:
        approval_actions["can_post"] = order.get("status") in ("待过账", "草稿", "", None)

    approval_labels = {
        "not_required": "无需审批" if not is_cross_warehouse else "未提交",
        "submitted": "待审批",
        "approved": "已批准",
        "rejected": "已驳回",
    }
    approval_status_display = approval_labels.get(approval_status, approval_status)

    return render_template(
        "inventory_document_detail.html",
        doc_type="transfer",
        title="库存调拨详情",
        back_url=back_url,
        order=order,
        number=order.get("transfer_no"),
        date=order.get("transfer_date"),
        items=items,
        transactions=stock_transactions_for_reference(query_rows, order.get("transfer_no"), "inventory_transfer"),
        print_url=f"/transfers/{transfer_id}/print",
        doc_kind="inventory_transfer",
        action_prefix="/transfers",
        attachments=document_attachments("inventory_transfer", transfer_id),
        activity_logs=document_activity_logs("inventory_transfer", order),
        custom_fields_payload=load_custom_payload("inventory_transfer", transfer_id),
        is_cross_warehouse=is_cross_warehouse,
        approval_status=approval_status,
        approval_status_display=approval_status_display,
        approval_actions=approval_actions,
    )


def render_inventory_check_detail(
    check_id,
    query_one,
    query_rows,
    ensure_check_items,
    document_attachments,
    document_activity_logs,
    load_custom_payload,
    back_url="/inventory_checks",
):
    ensure_check_items()
    order = query_one(
        """
        SELECT ico.*, l.code AS location_code, l.name AS location_name
        FROM inventory_check_orders ico
        LEFT JOIN locations l ON l.id=ico.location_id
        WHERE ico.id=%s
        """,
        (check_id,),
    )
    if not order:
        return render_template("simple_detail.html", title="库存盘点详情", row=None, back_url=back_url, labels={})
    items = query_rows(
        """
        SELECT ci.*, p.code AS product_code, p.name AS product_name, p.specification, p.unit,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               lw.name AS line_warehouse_name,
               COALESCE(ll.code, ll.name) AS line_location_code,
               (COALESCE(ci.diff_qty,0) * COALESCE(ci.unit_cost,0)) AS amount
        FROM inventory_check_order_items ci
        LEFT JOIN products p ON p.id=ci.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN warehouses lw ON lw.id=ci.line_warehouse_id
        LEFT JOIN locations ll ON ll.id=ci.line_location_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        WHERE ci.check_id=%s
        ORDER BY ci.id
        """,
        (check_id,),
    )
    return render_template(
        "inventory_document_detail.html",
        doc_type="check",
        title="库存盘点详情",
        back_url=back_url,
        order=order,
        number=order.get("check_no"),
        date=order.get("check_date"),
        items=items,
        transactions=stock_transactions_for_reference(query_rows, order.get("check_no"), "inventory_check"),
        print_url=f"/inventory_checks/{check_id}/print",
        doc_kind="inventory_check",
        action_prefix="/inventory_checks",
        attachments=document_attachments("inventory_check", check_id),
        activity_logs=document_activity_logs("inventory_check", order),
        custom_fields_payload=load_custom_payload("inventory_check", check_id),
        difference_summary={
            "title": "盘点差异分析",
            "profit_qty": sum((as_decimal(item.get("diff_qty")) for item in items if as_decimal(item.get("diff_qty")) > 0), Decimal("0")),
            "loss_qty": sum((abs(as_decimal(item.get("diff_qty"))) for item in items if as_decimal(item.get("diff_qty")) < 0), Decimal("0")),
            "difference_amount": sum((as_decimal(item.get("amount")) for item in items), Decimal("0")),
            "hint": "盘盈、盘亏和差异金额需复核原因后再过账。",
        },
    )



def render_inventory_document_print(
    doc_type,
    record_id,
    query_one,
    query_rows,
    as_decimal,
    ensure_transfer_items,
    ensure_check_items,
):
    if doc_type == "adjustment":
        order = query_one(
            """
            SELECT ia.*, ia.adj_no AS doc_no,
                   p.code AS product_code, p.name AS product_name, p.specification, p.unit,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required
            FROM inventory_adjustments ia
            LEFT JOIN products p ON p.id=ia.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            WHERE ia.id=%s
            """,
            (record_id,),
        )
        if not order:
            return render_template("simple_detail.html", title="库存调整打印", row=None, back_url="/adjustments", labels={})
        rows = [
            {
                "product_code": order.get("product_code"),
                "product_name": order.get("product_name"),
                "specification": order.get("specification"),
                "product_family": order.get("product_family"),
                "bom_display": bom_display_text(order),
                "control_display": manufacturing_control_text(order),
                "default_bom_no": order.get("default_bom_no"),
                "default_bom_version": order.get("default_bom_version"),
                "batch_control": order.get("batch_control"),
                "serial_control": order.get("serial_control"),
                "inspection_required": order.get("inspection_required"),
                "quantity": order.get("diff_quantity"),
                "unit": order.get("unit"),
                "unit_cost": order.get("unit_cost"),
                "lot_no": order.get("lot_no"),
                "serial_no": order.get("reference_no"),
                "amount": as_decimal(order.get("diff_quantity")) * as_decimal(order.get("unit_cost")),
            }
        ]
        title, number, date, status = "库存调整单", order.get("doc_no"), order.get("adj_date"), order.get("status")
        info = [("调整类型", order.get("adj_type")), ("备注", order.get("remark"))]
        remark = order.get("remark")
    elif doc_type == "transfer":
        ensure_transfer_items()
        order = query_one(
            """
            SELECT tr.*, fw.name AS from_warehouse_name, tw.name AS to_warehouse_name
            FROM transfer_orders tr
            LEFT JOIN warehouses fw ON fw.id=tr.from_warehouse_id
            LEFT JOIN warehouses tw ON tw.id=tr.to_warehouse_id
            WHERE tr.id=%s
            """,
            (record_id,),
        )
        if not order:
            return render_template("simple_detail.html", title="库存调拨打印", row=None, back_url="/transfers", labels={})
        rows = query_rows(
            """
            SELECT ti.quantity, ti.unit_cost, ti.lot_no, ti.serial_no,
                   p.code AS product_code, p.name AS product_name, p.specification, p.unit,
                   fwl.name AS from_warehouse_name, twl.name AS to_warehouse_name,
                   fl.code AS from_location_code, tl.code AS to_location_code,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required,
                   (COALESCE(ti.quantity,0) * COALESCE(ti.unit_cost,0)) AS amount
            FROM transfer_order_items ti
            LEFT JOIN products p ON p.id=ti.product_id
            LEFT JOIN warehouses fwl ON fwl.id=ti.from_warehouse_id
            LEFT JOIN warehouses twl ON twl.id=ti.to_warehouse_id
            LEFT JOIN locations fl ON fl.id=ti.from_location_id
            LEFT JOIN locations tl ON tl.id=ti.to_location_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            WHERE ti.transfer_id=%s
            ORDER BY ti.id
            """,
            (record_id,),
        )
        for row in rows:
            row["bom_display"] = bom_display_text(row)
            row["control_display"] = manufacturing_control_text(row)
        title, number, date, status = "库存调拨单", order.get("transfer_no"), order.get("transfer_date"), order.get("status")
        info = [("项目号", order.get("project_code")), ("备注", order.get("remark"))]
        remark = order.get("remark")
    else:
        ensure_check_items()
        order = query_one("SELECT * FROM inventory_check_orders WHERE id=%s", (record_id,))
        if not order:
            return render_template("simple_detail.html", title="库存盘点打印", row=None, back_url="/inventory_checks", labels={})
        rows = query_rows(
            """
            SELECT ci.book_qty, ci.actual_qty, ci.diff_qty AS quantity, ci.unit_cost,
                   ci.lot_no, ci.serial_no, p.code AS product_code, p.name AS product_name,
                   p.specification, p.unit,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required,
                   lw.name AS line_warehouse_name,
                   COALESCE(ll.code, ll.name) AS line_location_code,
                   (COALESCE(ci.diff_qty,0) * COALESCE(ci.unit_cost,0)) AS amount
            FROM inventory_check_order_items ci
            LEFT JOIN products p ON p.id=ci.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN warehouses lw ON lw.id=ci.line_warehouse_id
            LEFT JOIN locations ll ON ll.id=ci.line_location_id
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            WHERE ci.check_id=%s
            ORDER BY ci.id
            """,
            (record_id,),
        )
        for row in rows:
            row["bom_display"] = bom_display_text(row)
            row["control_display"] = manufacturing_control_text(row)
        title, number, date, status = "库存盘点单", order.get("check_no"), order.get("check_date"), order.get("status")
        info = [("过账时间", order.get("posted_at"))]
        remark = order.get("remark")
    document_type = {
        "adjustment": "inventory_adjustment",
        "transfer": "inventory_transfer",
        "check": "inventory_check",
    }.get(doc_type, doc_type)
    doc = {
        "title": title,
        "subtitle": "机床 ERP 单据打印",
        "number": number,
        "date": date,
        "status_label": status or "",
        "info": info,
        "columns": [
            ("product_code", "物料编码", ""),
            ("product_name", "物料名称", ""),
            ("specification", "规格", ""),
            ("product_family", "产品分类", ""),
            ("bom_display", "BOM版本", ""),
            ("control_display", "管控", ""),
            ("quantity", "数量/差异", "right"),
            ("unit", "单位", "center"),
            ("unit_cost", "单价/成本", "money right"),
            ("amount", "金额", "money right"),
            ("lot_no", "批号", ""),
            ("serial_no", "机号", ""),
        ],
        "rows": rows,
        "total_quantity": sum((as_decimal(row.get("quantity")) for row in rows), Decimal("0")),
        "total_amount": sum((as_decimal(row.get("amount")) for row in rows), Decimal("0")),
        "remark": remark,
        "signatures": ["制单", "仓库", "审核", "财务"],
        "print_time": datetime.now(),
    }
    template_grid = build_template_grid_for_document(document_type, doc, query_one)
    return render_template("document_print.html", doc=doc, template_grid=template_grid)


def _inventory_option_enabled(query_one, key, default=False):
    try:
        row = query_one("SELECT option_value FROM system_options WHERE option_key=%s LIMIT 1", (key,))
    except Exception:
        try:
            row = query_one("SELECT value FROM system_options WHERE key=%s LIMIT 1", (key,))
        except Exception:
            row = None
    value = (row or {}).get("option_value", (row or {}).get("value"))
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "启用", "允许", "开启"}


def render_inventory_dashboard_legacy_unused(query_rows, query_one):
    stock_summary = query_one(
        """
        SELECT COUNT(DISTINCT product_id) AS product_count,
               COUNT(*) AS balance_rows,
               COALESCE(SUM(quantity), 0) AS stock_qty,
               COALESCE(SUM(locked_qty), 0) AS locked_qty,
               COALESCE(SUM(quantity * COALESCE(unit_cost,0)), 0) AS stock_value
        FROM inventory_balances
        """
    ) or {}
    low_stock_count = query_one(
        """
        WITH stock AS (
            SELECT product_id, COALESCE(SUM(quantity), 0) AS stock_qty
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT COUNT(*) AS value
        FROM products p
        LEFT JOIN stock ON stock.product_id=p.id
        WHERE COALESCE(p.safety_stock,0) > 0 AND COALESCE(stock.stock_qty,0) < COALESCE(p.safety_stock,0)
        """
    ) or {}
    pending_post_count = query_one(
        """
        WITH pending_docs AS (
            SELECT adj_no AS doc_no FROM inventory_adjustments
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            UNION ALL
            SELECT transfer_no AS doc_no FROM transfer_orders
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            UNION ALL
            SELECT check_no AS doc_no FROM inventory_check_orders
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
        )
        SELECT COUNT(DISTINCT doc_no) AS value FROM pending_docs
        """
    ) or {}
    project_gap_count = query_one(
        """
        SELECT COUNT(*) AS value
        FROM mrp_requirements
        WHERE COALESCE(shortage_quantity, 0) > 0
          AND (COALESCE(project_code, '') <> '' OR COALESCE(serial_no, '') <> '')
        """
    ) or {}
    negative_count = query_one("SELECT COUNT(*) AS value FROM inventory_balances WHERE COALESCE(quantity,0) < 0") or {}
    allow_negative_stock = _inventory_option_enabled(query_one, "allow_negative_stock", False)
    negative_policy = "allow_negative_stock=开启：系统允许负库存，需每日复核" if allow_negative_stock else "allow_negative_stock=关闭：负库存必须优先处理"
    metrics = [
        {"label": "待过账单据", "value": pending_post_count.get("value", 0), "hint": "调拨、盘点、调整需审核过账"},
        {"label": "低于安全库存", "value": low_stock_count.get("value", 0), "hint": "需要采购、生产或替代料处理"},
        {"label": "负库存风险", "value": negative_count.get("value", 0), "hint": negative_policy},
        {"label": "项目/机号缺口", "value": project_gap_count.get("value", 0), "hint": "按 MRP 缺料追溯"},
    ]
    pending_documents = query_rows(
        """
        WITH docs AS (
            SELECT MIN(id) AS id, '库存调整' AS doc_type, adj_no AS doc_no, MAX(adj_date) AS doc_date,
                   MAX(project_code) AS project_code, MAX(serial_no) AS serial_no, MAX(status) AS status,
                   COUNT(*) AS line_count, SUM(ABS(COALESCE(diff_quantity,0))) AS qty,
                   '/adjustments' AS detail_base
            FROM inventory_adjustments
            WHERE COALESCE(status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            GROUP BY adj_no
            UNION ALL
            SELECT tr.id, '库存调拨', tr.transfer_no, tr.transfer_date,
                   tr.project_code, NULL::VARCHAR AS serial_no, tr.status,
                   COALESCE(items.line_count, 0), COALESCE(items.qty, 0), '/transfers'
            FROM transfer_orders tr
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS line_count, SUM(COALESCE(quantity,0)) AS qty
                FROM transfer_order_items ti
                WHERE ti.transfer_id=tr.id
            ) items ON TRUE
            WHERE COALESCE(tr.status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
            UNION ALL
            SELECT ico.id, '库存盘点', ico.check_no, ico.check_date,
                   ico.project_code, NULL::VARCHAR AS serial_no, ico.status,
                   COALESCE(items.line_count, 0), COALESCE(items.qty, 0), '/inventory_checks'
            FROM inventory_check_orders ico
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS line_count, SUM(ABS(COALESCE(diff_qty,0))) AS qty
                FROM inventory_check_order_items ci
                WHERE ci.check_id=ico.id
            ) items ON TRUE
            WHERE COALESCE(ico.status, '') NOT IN ('已过账','已关闭','已取消','posted','closed','cancelled')
        )
        SELECT *,
               CASE
                   WHEN doc_type='库存调拨' THEN '确认调出/调入仓库并过账'
                   WHEN doc_type='库存盘点' THEN '复核盘点差异并过账'
                   ELSE '补齐调整原因，审批后过账'
               END AS next_step,
               '仓库主管' AS owner_role,
               CASE
                   WHEN COALESCE(project_code,'')='' THEN '缺项目号，项目库存追溯不完整'
                   ELSE '等待仓库审核/过账'
               END AS blocked_reason,
               '影响可用库存、领料、完工入库和成本核算' AS downstream_impact
        FROM docs
        ORDER BY doc_date DESC NULLS LAST, id DESC
        LIMIT 30
        """
    )
    for row in pending_documents:
        row["detail_url"] = f"{row.get('detail_base')}/{row.get('id')}"
    low_stock_rows = query_rows(
        """
        WITH stock AS (
            SELECT product_id, COALESCE(SUM(quantity), 0) AS stock_qty
            FROM inventory_balances
            GROUP BY product_id
        )
        SELECT p.id, p.code AS product_code, p.name AS product_name, p.specification,
               p.unit, p.safety_stock,
               COALESCE(stock.stock_qty, 0) AS stock_qty,
               GREATEST(COALESCE(p.safety_stock,0)-COALESCE(stock.stock_qty,0),0) AS shortage_qty,
               p.default_supplier_name
        FROM products p
        LEFT JOIN stock ON stock.product_id=p.id
        WHERE COALESCE(p.safety_stock,0) > 0
          AND COALESCE(stock.stock_qty,0) < COALESCE(p.safety_stock,0)
        ORDER BY shortage_qty DESC, p.code
        LIMIT 30
        """
    )
    negative_rows = query_rows(
        """
        SELECT ib.id, p.code AS product_code, p.name AS product_name, w.name AS warehouse_name,
               l.code AS location_code, ib.project_code, ib.lot_no, ib.serial_no, ib.quantity
        FROM inventory_balances ib
        LEFT JOIN products p ON p.id=ib.product_id
        LEFT JOIN warehouses w ON w.id=ib.warehouse_id
        LEFT JOIN locations l ON l.id=ib.location_id
        WHERE COALESCE(ib.quantity,0) < 0
        ORDER BY ib.quantity ASC, ib.id DESC
        LIMIT 30
        """
    )
    alerts = query_rows(
        """
        SELECT ia.id, ia.alert_type, ia.alert_level, ia.current_qty, ia.threshold_qty,
               ia.created_at, p.code AS product_code, p.name AS product_name,
               w.name AS warehouse_name
        FROM inventory_alerts ia
        LEFT JOIN products p ON p.id=ia.product_id
        LEFT JOIN warehouses w ON w.id=ia.warehouse_id
        WHERE COALESCE(ia.is_resolved, FALSE)=FALSE
        ORDER BY ia.created_at DESC NULLS LAST, ia.id DESC
        LIMIT 30
        """
    )
    return render_template(
        "inventory_dashboard.html",
        title="库存工作台",
        subtitle="按待办、异常、责任人和下一步推进库存闭环；明细和单据列表请进入独立列表页。",
        metrics=metrics,
        pending_documents=pending_documents,
        low_stock_rows=low_stock_rows,
        negative_rows=negative_rows,
        alerts=alerts,
        allow_negative_stock=allow_negative_stock,
        negative_policy=negative_policy,
        stock_summary=stock_summary,
    )
