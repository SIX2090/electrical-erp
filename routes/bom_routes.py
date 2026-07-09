"""BOM module routes: BOM list, BOM detail, version management, and BOM export."""
import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlencode

from flask import Response, flash, redirect, render_template, request, url_for

from routes.display_helpers import _looks_corrupt_text
from routes.read_query_helpers import _export_format, _xlsx_response
from services.transaction_utils import cursor_db_helpers


BOM_TYPE_LABELS = {
    "engineering": "工程BOM",
    "ebom": "工程BOM",
    "process": "工艺BOM",
    "pbom": "工艺BOM",
    "production": "制造BOM",
    "manufacturing": "制造BOM",
    "mbom": "制造BOM",
    "sales": "销售BOM",
    "sbom": "销售BOM",
}

BOM_STATUS_LABELS = {
    "draft": "草稿",
    "pending": "审核中",
    "reviewing": "审核中",
    "approved": "已发布",
    "released": "已发布",
    "active": "已发布",
    "frozen": "已冻结",
    "obsolete": "已作废",
    "void": "已作废",
    "disabled": "已作废",
    "草稿": "草稿",
    "审核中": "审核中",
    "已审核": "已发布",
    "已发布": "已发布",
    "启用": "已发布",
    "已冻结": "已冻结",
    "已作废": "已作废",
    "停用": "已作废",
}

FORM_EDITABLE_BOM_STATUS_OPTIONS = [("draft", "草稿"), ("pending", "审核中")]

ECN_STATUS_LABELS = {
    "draft": "草稿",
    "submitted": "已提交",
    "approved": "已审核",
    "closed": "已关闭",
    "voided": "已作废",
}


def _bom_type_label(value):
    text = str(value or "").strip()
    return BOM_TYPE_LABELS.get(text.lower(), text or "-")


def _bom_status_label(value):
    text = str(value or "").strip()
    return BOM_STATUS_LABELS.get(text.lower(), BOM_STATUS_LABELS.get(text, text or "未定"))


def _bom_status_key(status):
    text = str(status or "").strip().lower()
    if text in {"approved", "released", "active", "已发布", "已审核", "启用"}:
        return "released"
    if text in {"frozen", "已冻结"}:
        return "frozen"
    if text in {"obsolete", "void", "disabled", "已作废", "停用"}:
        return "obsolete"
    return "draft"


def _bom_form_status_key(status):
    text = str(status or "").strip().lower()
    if text in {"draft", "草稿"}:
        return "draft"
    if text in {"pending", "reviewing", "审核中"}:
        return "pending"
    return ""


def _bom_dirty(value):
    return _looks_corrupt_text(value)


def _bom_display(value, fallback="-"):
    if value is None or value == "" or _bom_dirty(value):
        return fallback
    return value


def _text(name):
    return (request.form.get(name) or "").strip()


def _request_text(name, source=None):
    holder = source if source is not None else request.values
    return (holder.get(name) or "").strip()


def _value_from_list(values, index, default=""):
    return (values[index] if index < len(values) else default or "").strip()


def _decimal_from_value(value, default=Decimal("0")):
    try:
        if value is None or str(value).strip() == "":
            return default
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return default


def _format_decimal_for_form(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:f}".rstrip("0").rstrip(".")
    return str(value)


def _bom_requirement_with_loss(quantity, loss_rate):
    qty = _decimal_from_value(quantity, Decimal("0"))
    loss = _decimal_from_value(loss_rate, Decimal("0"))
    return qty * (Decimal("1") + loss / Decimal("100"))


def _annotate_bom_form_items(form_state, products):
    product_map = {str(product.get("id")): dict(product) for product in products}
    for index, item in enumerate(form_state.get("items") or [], start=1):
        product = product_map.get(str(item.get("product_id") or ""))
        item["source_line_no"] = item.get("source_line_no") or str(index)
        item["product_code"] = (product or {}).get("code") or ""
        item["product_name"] = (product or {}).get("name") or ""
        item["specification"] = (product or {}).get("specification") or ""
        if not str(item.get("unit") or "").strip() and product:
            item["unit"] = product.get("unit") or ""
        item["requirement_with_loss"] = _format_decimal_for_form(_bom_requirement_with_loss(item.get("quantity"), item.get("loss_rate")))
    return form_state


def _compose_bom_change_remark(remark, change_reason="", source_bom_no=""):
    base = str(remark or "").strip()
    reason = str(change_reason or "").strip()
    source = str(source_bom_no or "").strip()
    if not reason:
        return base
    prefix = f"变更说明（来源BOM：{source}）" if source else "变更说明"
    change_text = f"{prefix}：{reason}"
    return f"{base}\n{change_text}" if base else change_text


def _date_range_overlap(start_a, end_a, start_b, end_b):
    min_date = "0001-01-01"
    max_date = "9999-12-31"
    a_start = str(start_a or min_date)
    a_end = str(end_a or max_date)
    b_start = str(start_b or min_date)
    b_end = str(end_b or max_date)
    return a_start <= b_end and b_start <= a_end


def _csv_response(filename, rows):
    if _export_format() == "xlsx":
        return _xlsx_response(rows, filename.rsplit(".", 1)[0])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return Response(output.getvalue().encode("utf-8-sig"), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


def _ensure_bom_ecn_tables(execute_db):
    """Schema is managed by services/schema_migrations.py.

    Compatibility marker for audits: CREATE TABLE IF NOT EXISTS bom_engineering_changes.
    Required migration marker: change_reason TEXT NOT NULL.
    Runtime route registration must not execute DDL.
    """
    return



def _ecn_status_label(value):
    text = str(value or "").strip().lower()
    return ECN_STATUS_LABELS.get(text, text or "未定")


def _ecn_status_key(value):
    text = str(value or "").strip().lower()
    if text in ECN_STATUS_LABELS:
        return text
    return "draft"


def _next_ecn_no(query_one):
    prefix = f"ECN-{date.today().strftime('%Y%m%d')}"
    row = query_one("SELECT COUNT(*) AS value FROM bom_engineering_changes WHERE ecn_no LIKE %s", (f"{prefix}-%",))
    return f"{prefix}-{int((row or {}).get('value') or 0) + 1:03d}"


def _ecn_list_filters():
    return {
        "keyword": _request_text("keyword"),
        "status": _request_text("status"),
        "bom_no": _request_text("bom_no"),
    }


def _ecn_bom_label(row, prefix):
    parts = [row.get(f"{prefix}_bom_no"), row.get(f"{prefix}_version"), row.get(f"{prefix}_product_code"), row.get(f"{prefix}_product_name")]
    return " / ".join(str(part) for part in parts if part) or "-"


def _ecn_list_rows(query_rows, filters, limit=100):
    where_parts = []
    params = []
    keyword = filters.get("keyword")
    if keyword:
        where_parts.append(
            """
            (ec.ecn_no ILIKE %s OR ec.title ILIKE %s OR ec.change_reason ILIKE %s
             OR COALESCE(src.bom_no,'') ILIKE %s OR COALESCE(tgt.bom_no,'') ILIKE %s)
            """
        )
        params.extend([f"%{keyword}%"] * 5)
    if filters.get("status"):
        where_parts.append("ec.status=%s")
        params.append(filters["status"])
    if filters.get("bom_no"):
        where_parts.append("(COALESCE(src.bom_no,'') ILIKE %s OR COALESCE(tgt.bom_no,'') ILIKE %s)")
        params.extend([f"%{filters['bom_no']}%"] * 2)
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    rows = query_rows(
        f"""
        SELECT ec.*, src.bom_no AS source_bom_no, src.version AS source_version,
               sp.code AS source_product_code, sp.name AS source_product_name,
               tgt.bom_no AS target_bom_no, tgt.version AS target_version,
               tp.code AS target_product_code, tp.name AS target_product_name
        FROM bom_engineering_changes ec
        LEFT JOIN boms src ON src.id=ec.source_bom_id
        LEFT JOIN products sp ON sp.id=src.product_id
        LEFT JOIN boms tgt ON tgt.id=ec.target_bom_id
        LEFT JOIN products tp ON tp.id=tgt.product_id
        {where_sql}
        ORDER BY ec.id DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    result = []
    for row in rows:
        item = dict(row)
        item["status_label"] = _ecn_status_label(item.get("status"))
        item["source_bom_label"] = _ecn_bom_label(item, "source")
        item["target_bom_label"] = _ecn_bom_label(item, "target")
        result.append(item)
    return result


def _bom_list_filters():
    return {
        "keyword": (request.args.get("keyword") or request.args.get("q") or request.args.get("search") or "").strip(),
        "bom_no": (request.args.get("bom_no") or "").strip(),
        "product_code": (request.args.get("product_code") or "").strip(),
        "product_name": (request.args.get("product_name") or "").strip(),
        "specification": (request.args.get("specification") or "").strip(),
        "bom_type": (request.args.get("bom_type") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
    }


def _bom_list_query(query_rows, filters, limit=100):
    where_parts = []
    params = []
    keyword = filters.get("keyword", "")
    if keyword:
        where_parts.append(
            """
            (b.bom_no ILIKE %s OR b.version ILIKE %s OR COALESCE(b.bom_type,'') ILIKE %s
             OR COALESCE(b.status,'') ILIKE %s OR COALESCE(p.code,'') ILIKE %s
             OR COALESCE(p.name,'') ILIKE %s OR COALESCE(p.specification,'') ILIKE %s)
            """
        )
        params.extend([f"%{keyword}%"] * 7)
    for key, column in (("bom_no", "b.bom_no"), ("product_code", "p.code"), ("product_name", "p.name"), ("specification", "p.specification")):
        if filters.get(key):
            where_parts.append(f"COALESCE({column}, '') ILIKE %s")
            params.append(f"%{filters[key]}%")
    if filters.get("bom_type"):
        where_parts.append("COALESCE(b.bom_type, '') = %s")
        params.append(filters["bom_type"])
    if filters.get("status"):
        where_parts.append("COALESCE(b.status, '') = %s")
        params.append(filters["status"])
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    rows = query_rows(
        f"""
        SELECT b.id, b.bom_no, b.version, b.status, b.bom_type, b.effective_date,
               b.expiry_date, p.code AS product_code, p.name AS product_name,
               p.specification AS product_specification, COALESCE(COUNT(bi.id),0) AS item_count
        FROM boms b
        LEFT JOIN products p ON p.id=b.product_id
        LEFT JOIN bom_items bi ON bi.bom_id=b.id
        {where_sql}
        GROUP BY b.id, p.code, p.name, p.specification
        ORDER BY b.id DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    result = []
    for row in rows:
        item = dict(row)
        item["bom_type_label"] = _bom_type_label(item.get("bom_type"))
        item["status_label"] = _bom_status_label(item.get("status"))
        item["product_display"] = " ".join(part for part in (item.get("product_code"), item.get("product_name"), item.get("product_specification")) if part) or "物料档案缺失"
        result.append(item)
    return result


def render_bom_dashboard(query_rows, columns, back_url="/bom"):
    filters = _bom_list_filters()
    export_requested = _export_format() == "xlsx" or request.args.get("export") == "csv"
    rows = _bom_list_query(query_rows, filters, limit=1000 if export_requested else 100)
    if export_requested:
        out = [["BOM编号", "适用产品", "产品编码", "产品名称", "规格", "类型", "版本", "状态", "生效日期", "子项数"]]
        for row in rows:
            out.append([row.get("bom_no") or "", row.get("product_display") or "", row.get("product_code") or "", row.get("product_name") or "", row.get("product_specification") or "", row.get("bom_type_label") or "", row.get("version") or "", row.get("status_label") or "", row.get("effective_date") or "", row.get("item_count") or 0])
        return _csv_response("bom-list.csv", out)
    export_query = urlencode({key: value for key, value in filters.items() if value})
    return render_template(
        "bom_list.html",
        title="工程BOM",
        subtitle="工程BOM主数据清单：用于查询产品结构、版本、用量和损耗；本页只读。",
        rows=rows,
        filters=filters,
        active_filter_count=sum(1 for value in filters.values() if value),
        bom_type_options=[("", "全部类型"), ("engineering", "工程BOM"), ("process", "工艺BOM"), ("production", "制造BOM"), ("sales", "销售BOM")],
        status_options=[("", "全部状态"), ("draft", "草稿"), ("pending", "审核中"), ("released", "已发布"), ("frozen", "已冻结"), ("obsolete", "已作废")],
        export_url="/bom?" + (export_query + "&" if export_query else "") + "export=csv",
        back_url=back_url,
    )


def _find_bom_by_key(bom_key, query_one):
    if str(bom_key).isdigit():
        row = query_one("SELECT * FROM boms WHERE id=%s", (int(bom_key),))
        if row:
            return dict(row)
    row = query_one("SELECT * FROM boms WHERE bom_no=%s", (bom_key,))
    return dict(row) if row else None


def _product_master(product_id, query_one):
    if not str(product_id or "").isdigit():
        return None
    row = query_one("SELECT id, code, name, specification, unit FROM products WHERE id=%s", (int(product_id),))
    return dict(row) if row else None


def _product_by_code(code, query_one):
    row = query_one("SELECT id, code, name, specification, unit FROM products WHERE code=%s", (code,))
    return dict(row) if row else None


def _product_label(product):
    if not product:
        return "物料档案缺失"
    return " / ".join(part for part in [product.get("code"), product.get("name")] if part) or str(product.get("id") or "物料档案缺失")


def _bom_version_date_conflict(form_state, query_rows, current_bom_id=None):
    product_id = str(form_state.get("product_id") or "").strip()
    if not product_id.isdigit():
        return None
    rows = query_rows(
        """
        SELECT id, bom_no, version, effective_date, expiry_date
        FROM boms
        WHERE product_id=%s
          AND COALESCE(status, '') NOT IN ('obsolete', 'void', 'disabled', '已作废', '停用')
          AND (%s IS NULL OR id<>%s)
        """,
        (int(product_id), current_bom_id, current_bom_id),
    )
    for row in rows:
        if _date_range_overlap(form_state.get("effective_date"), form_state.get("expiry_date"), row.get("effective_date"), row.get("expiry_date")):
            return dict(row)
    return None


def _detail_bom(bom, query_one, query_rows=None):
    row = query_one(
        """
        SELECT b.*, p.code AS product_code, p.name AS product_name,
               p.specification AS product_specification, p.unit AS product_unit
        FROM boms b
        LEFT JOIN products p ON p.id=b.product_id
        WHERE b.id=%s
        """,
        (bom["id"],),
    )
    item = dict(row)
    item["status_key"] = _bom_status_key(item.get("status"))
    item["bom_type_label"] = _bom_type_label(item.get("bom_type"))
    item["status_label"] = _bom_status_label(item.get("status"))
    item["product_name_dirty"] = _bom_dirty(item.get("product_name"))
    item["product_specification_dirty"] = _bom_dirty(item.get("product_specification"))
    item["product_unit_dirty"] = _bom_dirty(item.get("product_unit"))
    item["remark_dirty"] = _bom_dirty(item.get("remark"))
    item["product_name_display"] = _bom_display(item.get("product_name"), "产品名称异常" if item.get("product_code") else "物料档案缺失")
    item["product_specification_display"] = _bom_display(item.get("product_specification"))
    item["product_unit_display"] = _bom_display(item.get("product_unit"))
    item["remark_display"] = _bom_display(item.get("remark"), "备注异常" if item.get("remark") else "")
    item["can_freeze"] = _bom_status_key(item.get("status")) in {"draft", "released"}
    item["can_obsolete"] = _bom_status_key(item.get("status")) in {"draft", "released", "frozen"}
    item["can_restore_draft"] = _bom_status_key(item.get("status")) == "frozen"
    item["version_date_conflict"] = _bom_version_date_conflict({"product_id": item.get("product_id"), "effective_date": item.get("effective_date"), "expiry_date": item.get("expiry_date")}, query_rows, item.get("id")) if query_rows else None
    return item


def _bom_items(bom_id, query_rows):
    rows = query_rows(
        """
        SELECT bi.*, p.code AS product_code, p.name AS product_name,
               p.specification, COALESCE(NULLIF(bi.unit,''), p.unit, '') AS display_unit,
               COALESCE(bi.quantity,0) * (1 + COALESCE(bi.loss_rate,0) / 100.0) AS requirement_with_loss
        FROM bom_items bi
        LEFT JOIN products p ON p.id=bi.product_id
        WHERE bi.bom_id=%s
        ORDER BY bi.id
        """,
        (bom_id,),
    )
    result = []
    for row in rows:
        item = dict(row)
        item["product_name_dirty"] = _bom_dirty(item.get("product_name"))
        item["specification_dirty"] = _bom_dirty(item.get("specification"))
        item["display_unit_dirty"] = _bom_dirty(item.get("display_unit"))
        item["remark_dirty"] = _bom_dirty(item.get("remark"))
        item["product_name_display"] = _bom_display(item.get("product_name"), "物料档案缺失")
        item["specification_display"] = _bom_display(item.get("specification"))
        item["display_unit_display"] = _bom_display(item.get("display_unit"))
        item["remark_display"] = _bom_display(item.get("remark"), "")
        result.append(item)
    return result


def _bom_readonly_drilldown(detail, items, query_rows):
    child_product_ids = [int(item["product_id"]) for item in items if str(item.get("product_id") or "").isdigit()]
    product_ids = list(dict.fromkeys(([int(detail["product_id"])] if str(detail.get("product_id") or "").isdigit() else []) + child_product_ids))
    bom_keyword = detail.get("bom_no") or detail.get("product_code") or ""
    product_keyword = detail.get("product_code") or detail.get("bom_no") or ""
    child_keyword = detail.get("product_code") or ""
    links = {
        "kitting": f"/engineering/kitting?keyword={quote(product_keyword)}" if product_keyword else "/engineering/kitting",
        "work_orders": f"/work-orders?keyword={quote(bom_keyword)}" if bom_keyword else "/work-orders",
        "mrp": f"/production-enhance/mrp-requirements?keyword={quote(child_keyword)}" if child_keyword else "/production-enhance/mrp-requirements",
        "purchase_requests": f"/purchase_request?keyword={quote(child_keyword)}" if child_keyword else "/purchase_request",
        "purchase_orders": f"/purchase-orders?keyword={quote(child_keyword)}" if child_keyword else "/purchase-orders",
        "bom_list": f"/bom?product_code={quote(detail.get('product_code') or '')}" if detail.get("product_code") else "/bom",
    }
    work_order_summary = query_rows(
        """
        SELECT COUNT(*) AS order_count,
               COALESCE(SUM(COALESCE(quantity, 0)), 0) AS planned_qty,
               COUNT(*) FILTER (WHERE COALESCE(status, '') NOT IN ('已完工','已完成','已关闭','已作废','closed','completed','cancelled','void')) AS open_count
        FROM work_orders
        WHERE bom_id=%s OR product_id=%s
        """,
        (detail.get("id"), detail.get("product_id")),
    )[0]
    recent_work_orders = query_rows(
        """
        SELECT id, wo_no, status, production_stage, project_code, serial_no, quantity, planned_end_date
        FROM work_orders
        WHERE bom_id=%s OR product_id=%s
        ORDER BY id DESC
        LIMIT 8
        """,
        (detail.get("id"), detail.get("product_id")),
    )
    mrp_summary = {"requirement_count": 0, "requirement_qty": 0, "shortage_qty": 0, "earliest_date": None}
    mrp_rows = []
    purchase_summary = {"request_count": 0, "request_qty": 0, "order_count": 0, "pending_qty": 0}
    purchase_rows = []
    if product_ids:
        mrp_summary = query_rows(
            """
            SELECT COUNT(*) AS requirement_count,
                   COALESCE(SUM(COALESCE(quantity, 0)), 0) AS requirement_qty,
                   COALESCE(SUM(COALESCE(shortage_quantity, 0)), 0) AS shortage_qty,
                   MIN(requirement_date) AS earliest_date
            FROM mrp_requirements
            WHERE product_id = ANY(%s)
            """,
            (product_ids,),
        )[0]
        mrp_rows = query_rows(
            """
            SELECT mr.id, mr.requirement_date, mr.project_code, mr.serial_no,
                   p.code AS product_code, p.name AS product_name,
                   mr.quantity, mr.available_quantity, mr.shortage_quantity, mr.status
            FROM mrp_requirements mr
            LEFT JOIN products p ON p.id=mr.product_id
            WHERE mr.product_id = ANY(%s)
            ORDER BY COALESCE(mr.shortage_quantity, 0) DESC, mr.requirement_date NULLS LAST, mr.id DESC
            LIMIT 8
            """,
            (product_ids,),
        )
        purchase_summary = query_rows(
            """
            WITH req AS (
                SELECT COUNT(DISTINCT pr.id) AS request_count,
                       COALESCE(SUM(COALESCE(pri.quantity, 0)), 0) AS request_qty
                FROM purchase_requisition_items pri
                LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
                WHERE pri.product_id = ANY(%s)
                  AND COALESCE(pr.status, '') NOT IN ('已作废','作废','cancelled','rejected','已驳回')
            ),
            po AS (
                SELECT COUNT(DISTINCT po.id) AS order_count,
                       COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0) AS pending_qty
                FROM purchase_order_items poi
                LEFT JOIN purchase_orders po ON po.id=poi.order_id
                WHERE poi.product_id = ANY(%s)
                  AND COALESCE(po.status, '') NOT IN ('已作废','作废','cancelled','已关闭')
            )
            SELECT req.request_count, req.request_qty, po.order_count, po.pending_qty
            FROM req CROSS JOIN po
            """,
            (product_ids, product_ids),
        )[0]
        purchase_rows = query_rows(
            """
            SELECT po.id, po.order_no, po.status, po.project_code, po.serial_no,
                   p.code AS product_code, p.name AS product_name,
                   poi.quantity, poi.received_qty,
                   GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0) AS pending_qty
            FROM purchase_order_items poi
            LEFT JOIN purchase_orders po ON po.id=poi.order_id
            LEFT JOIN products p ON p.id=poi.product_id
            WHERE poi.product_id = ANY(%s)
            ORDER BY po.id DESC NULLS LAST, poi.id DESC
            LIMIT 8
            """,
            (product_ids,),
        )
    used_by_boms = query_rows(
        """
        SELECT parent_bom.id, parent_bom.bom_no, parent_bom.version, parent_bom.status,
               p.code AS product_code, p.name AS product_name
        FROM bom_items bi
        JOIN boms parent_bom ON parent_bom.id=bi.bom_id
        LEFT JOIN products p ON p.id=parent_bom.product_id
        WHERE bi.product_id=%s AND parent_bom.id<>%s
        ORDER BY parent_bom.id DESC
        LIMIT 8
        """,
        (detail.get("product_id"), detail.get("id")),
    )
    return {
        "links": links,
        "work_order_summary": dict(work_order_summary),
        "recent_work_orders": [dict(row) for row in recent_work_orders],
        "mrp_summary": dict(mrp_summary),
        "mrp_rows": [dict(row) for row in mrp_rows],
        "purchase_summary": dict(purchase_summary),
        "purchase_rows": [dict(row) for row in purchase_rows],
        "used_by_boms": [dict(row) for row in used_by_boms],
    }


def _ecn_impact_summary(bom, items, query_rows):
    if not bom:
        return {
            "work_order_summary": {"order_count": 0, "open_count": 0, "planned_qty": 0},
            "mrp_summary": {"requirement_count": 0, "shortage_qty": 0},
            "purchase_summary": {"order_count": 0, "pending_qty": 0},
            "recent_work_orders": [],
            "mrp_rows": [],
            "purchase_rows": [],
        }
    child_product_ids = [int(item["product_id"]) for item in items if str(item.get("product_id") or "").isdigit()]
    product_ids = list(dict.fromkeys(([int(bom["product_id"])] if str(bom.get("product_id") or "").isdigit() else []) + child_product_ids))
    work_order_summary = query_rows(
        """
        SELECT COUNT(*) AS order_count,
               COUNT(*) FILTER (WHERE COALESCE(status, '') NOT IN ('已完工','已完成','已关闭','已作废','closed','completed','cancelled','void')) AS open_count,
               COALESCE(SUM(COALESCE(quantity, 0)), 0) AS planned_qty
        FROM work_orders
        WHERE bom_id=%s OR product_id=%s
        """,
        (bom.get("id"), bom.get("product_id")),
    )[0]
    recent_work_orders = query_rows(
        """
        SELECT id, wo_no, status, project_code, serial_no, quantity, planned_end_date
        FROM work_orders
        WHERE bom_id=%s OR product_id=%s
        ORDER BY id DESC
        LIMIT 6
        """,
        (bom.get("id"), bom.get("product_id")),
    )
    mrp_summary = {"requirement_count": 0, "shortage_qty": 0}
    mrp_rows = []
    purchase_summary = {"order_count": 0, "pending_qty": 0}
    purchase_rows = []
    if product_ids:
        mrp_summary = query_rows(
            """
            SELECT COUNT(*) AS requirement_count,
                   COALESCE(SUM(COALESCE(shortage_quantity, 0)), 0) AS shortage_qty
            FROM mrp_requirements
            WHERE product_id = ANY(%s)
            """,
            (product_ids,),
        )[0]
        mrp_rows = query_rows(
            """
            SELECT mr.id, mr.requirement_date, mr.project_code, mr.serial_no,
                   p.code AS product_code, p.name AS product_name,
                   mr.quantity, mr.shortage_quantity, mr.status
            FROM mrp_requirements mr
            LEFT JOIN products p ON p.id=mr.product_id
            WHERE mr.product_id = ANY(%s)
            ORDER BY COALESCE(mr.shortage_quantity, 0) DESC, mr.id DESC
            LIMIT 6
            """,
            (product_ids,),
        )
        purchase_summary = query_rows(
            """
            SELECT COUNT(DISTINCT po.id) AS order_count,
                   COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0) AS pending_qty
            FROM purchase_order_items poi
            LEFT JOIN purchase_orders po ON po.id=poi.order_id
            WHERE poi.product_id = ANY(%s)
              AND COALESCE(po.status, '') NOT IN ('已作废','作废','cancelled','已关闭')
            """,
            (product_ids,),
        )[0]
        purchase_rows = query_rows(
            """
            SELECT po.id, po.order_no, po.status, p.code AS product_code, p.name AS product_name,
                   poi.quantity, poi.received_qty,
                   GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0) AS pending_qty
            FROM purchase_order_items poi
            LEFT JOIN purchase_orders po ON po.id=poi.order_id
            LEFT JOIN products p ON p.id=poi.product_id
            WHERE poi.product_id = ANY(%s)
            ORDER BY po.id DESC NULLS LAST, poi.id DESC
            LIMIT 6
            """,
            (product_ids,),
        )
    return {
        "work_order_summary": dict(work_order_summary),
        "recent_work_orders": [dict(row) for row in recent_work_orders],
        "mrp_summary": dict(mrp_summary),
        "mrp_rows": [dict(row) for row in mrp_rows],
        "purchase_summary": dict(purchase_summary),
        "purchase_rows": [dict(row) for row in purchase_rows],
    }


def _bom_contains_product(bom_id, product_id, query_one, visited=None, depth=0, max_depth=8):
    if not bom_id or not product_id or depth >= max_depth:
        return False
    visited = set(visited or set())
    if int(bom_id) in visited:
        return False
    visited.add(int(bom_id))
    if query_one("SELECT id FROM bom_items WHERE bom_id=%s AND product_id=%s LIMIT 1", (int(bom_id), int(product_id))):
        return True
    row = query_one(
        """
        SELECT STRING_AGG(child_bom.id::text, ',') AS child_bom_ids
        FROM bom_items bi
        JOIN boms child_bom ON child_bom.product_id=bi.product_id
        WHERE bi.bom_id=%s
        """,
        (int(bom_id),),
    )
    for child_bom_id in str((row or {}).get("child_bom_ids") or "").split(","):
        if child_bom_id.strip().isdigit() and _bom_contains_product(int(child_bom_id), int(product_id), query_one, visited=visited, depth=depth + 1, max_depth=max_depth):
            return True
    return False


def _child_product_creates_cycle(parent_product_id, child_product_id, query_one, current_bom_id=None):
    row = query_one("SELECT STRING_AGG(id::text, ',') AS bom_ids FROM boms WHERE product_id=%s AND (%s IS NULL OR id<>%s)", (int(child_product_id), current_bom_id, current_bom_id))
    for child_bom_id in str((row or {}).get("bom_ids") or "").split(","):
        if child_bom_id.strip().isdigit() and _bom_contains_product(int(child_bom_id), int(parent_product_id), query_one):
            return True
    return False


def _posted_bom_form_state():
    product_ids = request.form.getlist("item_product_id")
    quantities = request.form.getlist("item_quantity")
    units = request.form.getlist("item_unit")
    losses = request.form.getlist("item_loss_rate")
    optionals = set(request.form.getlist("item_optional"))
    remarks = request.form.getlist("item_remark")
    row_count = max(3, len(product_ids), len(quantities), len(units), len(losses), len(remarks))
    items = []
    for index in range(row_count):
        items.append({"product_id": _value_from_list(product_ids, index), "quantity": _value_from_list(quantities, index), "unit": _value_from_list(units, index), "loss_rate": _value_from_list(losses, index, "0") or "0", "is_optional": str(index) in optionals, "remark": _value_from_list(remarks, index)})
    return {"product_id": _text("product_id"), "bom_no": _text("bom_no"), "version": _text("version") or "V1.0", "bom_type": _text("bom_type") or "engineering", "status": _text("status") or "draft", "effective_date": _text("effective_date"), "expiry_date": _text("expiry_date"), "remark": _text("remark"), "change_reason": _text("change_reason"), "source_bom_no": _text("source_bom_no"), "items": items}


def _validate_bom_form_state(form_state, query_one, query_rows, current_bom_id=None):
    errors = []
    form_status = _bom_form_status_key(form_state.get("status"))
    if form_status:
        form_state["status"] = form_status
    else:
        errors.append("新增/修改表单只能保存为草稿或审核中；发布、冻结、作废请在详情页操作。")
    parent_product_id = str(form_state.get("product_id") or "").strip()
    parent_product = _product_master(parent_product_id, query_one)
    if not parent_product:
        errors.append("请选择适用产品。")
    elif not str(parent_product.get("specification") or "").strip():
        errors.append(f"适用产品 {_product_label(parent_product)} 缺少规格，不能保存BOM。")
    if not form_state.get("bom_no"):
        errors.append("请填写BOM编号。")
    else:
        duplicate = query_one("SELECT id FROM boms WHERE bom_no=%s", (form_state["bom_no"],))
        if duplicate and (current_bom_id is None or int(duplicate["id"]) != int(current_bom_id)):
            errors.append("BOM编号已存在，请换一个编号。")
    if form_state.get("effective_date") and form_state.get("expiry_date") and str(form_state["effective_date"]) > str(form_state["expiry_date"]):
        errors.append("生效日期不能晚于失效日期。")
    conflict = _bom_version_date_conflict(form_state, query_rows, current_bom_id)
    if conflict:
        errors.append(f"同一产品BOM有效期与 {conflict.get('bom_no')} / {conflict.get('version')} 重叠。")

    valid_items = []
    seen = {}
    for index, item in enumerate(form_state.get("items") or [], start=1):
        if not any(str(item.get(field) or "").strip() for field in ("product_id", "quantity", "unit", "remark")) and not item.get("is_optional"):
            continue
        product_id = str(item.get("product_id") or "").strip()
        product = _product_master(product_id, query_one)
        if not product:
            errors.append(f"第{index}行物料不存在。")
            continue
        if parent_product and int(product_id) == int(parent_product["id"]):
            errors.append(f"第{index}行子件不能与适用产品相同。")
            continue
        if parent_product and _child_product_creates_cycle(parent_product["id"], product["id"], query_one, current_bom_id):
            errors.append(f"第{index}行会形成循环BOM。")
            continue
        if not str(product.get("specification") or "").strip():
            errors.append(f"第{index}行物料 {_product_label(product)} 缺少规格，请先维护物料档案。")
            continue
        if product_id in seen:
            errors.append(f"第{index}行物料重复。")
            continue
        seen[product_id] = index
        qty = _decimal_from_value(item.get("quantity"), None)
        if qty is None or qty <= 0:
            errors.append(f"第{index}行数量必须大于0。")
            continue
        loss_rate = _decimal_from_value(item.get("loss_rate"), None)
        if loss_rate is None or loss_rate < 0 or loss_rate > 100:
            errors.append(f"第{index}行损耗率必须在0到100之间。")
            continue
        item_unit = str(item.get("unit") or "").strip()
        master_unit = str(product.get("unit") or "").strip()
        if not master_unit:
            errors.append(f"第{index}行物料 {_product_label(product)} 缺少默认单位，请先维护物料档案。")
            continue
        if not item_unit:
            item_unit = master_unit
        elif item_unit != master_unit:
            errors.append(f"第{index}行单位必须与物料档案单位一致：{master_unit}。")
            continue
        valid_items.append({"product_id": int(product_id), "quantity": qty, "unit": item_unit, "loss_rate": loss_rate, "is_optional": bool(item.get("is_optional")), "remark": str(item.get("remark") or "").strip()})
    if not valid_items:
        errors.append("至少需要录入一行有效BOM子件。")
    return valid_items, errors


def _blank_bom_item_state():
    return {"product_id": "", "quantity": "", "unit": "", "loss_rate": "0", "is_optional": False, "remark": "", "source_line_no": ""}


def _blank_bom_form_state():
    return {"product_id": "", "bom_no": "", "version": "V1.0", "bom_type": "engineering", "status": "draft", "effective_date": "", "expiry_date": "", "remark": "", "change_reason": "", "source_bom_no": "", "items": [_blank_bom_item_state() for _ in range(3)]}


def render_bom_form(query_rows, form_state=None, form_errors=None, mode="new", bom=None):
    products = query_rows("SELECT id, code, name, specification, unit FROM products WHERE COALESCE(code, '') NOT LIKE '%%?%%' ORDER BY code LIMIT 500")
    form_state = _annotate_bom_form_items(form_state or _blank_bom_form_state(), products)
    return render_template("bom_form.html", products=products, bom_type_options=[("engineering", "工程BOM"), ("process", "工艺BOM"), ("production", "制造BOM"), ("sales", "销售BOM")], status_options=FORM_EDITABLE_BOM_STATUS_OPTIONS, form_state=form_state, form_errors=form_errors or [], mode=mode, bom=bom, ecn_no=request.values.get("ecn_no", ""))


def _insert_bom_items(bom_id, item_rows, execute_db):
    for item in item_rows:
        execute_db("INSERT INTO bom_items (bom_id, product_id, quantity, unit, remark, loss_rate, is_optional) VALUES (%s,%s,%s,%s,%s,%s,%s)", (bom_id, item["product_id"], item["quantity"], item["unit"], item["remark"], item["loss_rate"], item["is_optional"]))


def create_bom_from_form(query_one, query_rows, execute_db, execute_and_return, log_action=None):
    form_state = _posted_bom_form_state()
    item_rows, errors = _validate_bom_form_state(form_state, query_one, query_rows)
    if errors:
        flash("BOM保存失败，请按提示修正后再保存。", "warning")
        return None, form_state, errors
    if form_state.get("source_bom_no"):
        form_state["status"] = "draft"
    bom = execute_and_return("INSERT INTO boms (product_id, bom_no, version, bom_type, status, effective_date, expiry_date, remark) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, bom_no", (int(form_state["product_id"]), form_state["bom_no"], form_state["version"], form_state["bom_type"], form_state["status"], form_state["effective_date"] or None, form_state["expiry_date"] or None, _compose_bom_change_remark(form_state.get("remark"), form_state.get("change_reason"), form_state.get("source_bom_no"))))
    _insert_bom_items(bom["id"], item_rows, execute_db)
    _update_ecn_target(_text("ecn_no"), bom["id"], execute_db, log_action)
    if log_action:
        log_action("复制升版BOM" if form_state.get("source_bom_no") else "新增BOM", form_state["bom_no"], f"version={form_state['version']}; source={form_state.get('source_bom_no') or '-'}")
    flash("BOM已保存。", "success")
    return bom, form_state, []


def _bom_form_state_from_db(bom, query_rows):
    rows = query_rows("SELECT id, product_id, quantity, unit, loss_rate, is_optional, remark FROM bom_items WHERE bom_id=%s ORDER BY id", (bom["id"],))
    items = [{"product_id": str(row.get("product_id") or ""), "quantity": _format_decimal_for_form(row.get("quantity")), "unit": row.get("unit") or "", "loss_rate": _format_decimal_for_form(row.get("loss_rate") if row.get("loss_rate") is not None else Decimal("0")), "is_optional": bool(row.get("is_optional")), "remark": row.get("remark") or "", "source_line_no": str(row.get("id") or "")} for row in rows]
    while len(items) < 3:
        items.append(_blank_bom_item_state())
    return {"product_id": str(bom.get("product_id") or ""), "bom_no": bom.get("bom_no") or "", "version": bom.get("version") or "V1.0", "bom_type": bom.get("bom_type") or "engineering", "status": bom.get("status") or "draft", "effective_date": str(bom.get("effective_date") or ""), "expiry_date": str(bom.get("expiry_date") or ""), "remark": bom.get("remark") or "", "change_reason": "", "source_bom_no": "", "items": items}


def _suggest_copy_bom_no(bom_no, query_one):
    base = f"{bom_no}-COPY"
    candidate = base
    suffix = 2
    while query_one("SELECT id FROM boms WHERE bom_no=%s", (candidate,)):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _suggest_next_bom_version(version):
    text = str(version or "").strip()
    if not text:
        return "V1.0"
    prefix = "V" if text[:1].upper() == "V" else ""
    number = text[1:] if prefix else text
    parts = number.split(".")
    if parts and all(part.isdigit() for part in parts if part):
        parts[-1] = str(int(parts[-1] or "0") + 1)
        return f"{prefix}{'.'.join(parts)}"
    return f"{text}-NEW"


def _copy_bom_form_state(bom, query_rows, query_one, upgrade=False):
    form_state = _bom_form_state_from_db(bom, query_rows)
    form_state["bom_no"] = _suggest_copy_bom_no(bom.get("bom_no") or "BOM", query_one)
    if upgrade:
        form_state["version"] = _suggest_next_bom_version(bom.get("version"))
    form_state["status"] = "draft"
    form_state["source_bom_no"] = bom.get("bom_no") or ""
    return form_state


def _find_ecn_by_key(ecn_key, query_one):
    if str(ecn_key).isdigit():
        row = query_one("SELECT * FROM bom_engineering_changes WHERE id=%s", (int(ecn_key),))
        if row:
            return dict(row)
    row = query_one("SELECT * FROM bom_engineering_changes WHERE ecn_no=%s", (ecn_key,))
    return dict(row) if row else None


def _posted_ecn_form_state(query_one):
    source_bom_key = _text("source_bom_key")
    target_bom_key = _text("target_bom_key")
    source_bom = _find_bom_by_key(source_bom_key, query_one) if source_bom_key else None
    target_bom = _find_bom_by_key(target_bom_key, query_one) if target_bom_key else None
    materials = request.form.getlist("detail_material[]")
    specifications = request.form.getlist("detail_specification[]")
    units = request.form.getlist("detail_unit[]")
    old_values = request.form.getlist("detail_old_value[]")
    new_values = request.form.getlist("detail_new_value[]")
    details = []
    for idx in range(len(materials)):
        material = (materials[idx] or "").strip() if idx < len(materials) else ""
        specification = (specifications[idx] or "").strip() if idx < len(specifications) else ""
        unit = (units[idx] or "").strip() if idx < len(units) else ""
        old_value = (old_values[idx] or "").strip() if idx < len(old_values) else ""
        new_value = (new_values[idx] or "").strip() if idx < len(new_values) else ""
        if not any([material, specification, unit, old_value, new_value]):
            continue
        details.append({
            "material": material,
            "specification": specification,
            "unit": unit,
            "old_value": old_value,
            "new_value": new_value,
        })
    return {
        "ecn_no": _text("ecn_no"),
        "title": _text("title"),
        "change_reason": _text("change_reason"),
        "owner": _text("owner"),
        "requested_date": _text("requested_date"),
        "status": _text("status") or "draft",
        "source_bom_key": source_bom_key,
        "target_bom_key": target_bom_key,
        "source_bom": source_bom,
        "target_bom": target_bom,
        "impact_summary": _text("impact_summary"),
        "details": details,
    }


def _validate_ecn_form_state(form_state, query_one, current_ecn_id=None):
    errors = []
    status = _ecn_status_key(form_state.get("status"))
    if status not in {"draft", "submitted"}:
        errors.append("工程变更单录入页只能保存为草稿或已提交；审核、关闭、作废请在详情页操作。")
    form_state["status"] = status
    if not form_state.get("ecn_no"):
        errors.append("请填写工程变更单号。")
    else:
        duplicate = query_one("SELECT id FROM bom_engineering_changes WHERE ecn_no=%s", (form_state["ecn_no"],))
        if duplicate and (current_ecn_id is None or int(duplicate["id"]) != int(current_ecn_id)):
            errors.append("工程变更单号已存在。")
    if not form_state.get("title"):
        errors.append("请填写变更主题。")
    if not form_state.get("change_reason"):
        errors.append("请填写变更原因。")
    if not form_state.get("source_bom"):
        errors.append("请选择影响BOM。")
    return errors


def _ecn_form_context(query_rows, query_one, form_state=None, ecn=None, errors=None, mode="new"):
    bom_options = query_rows(
        """
        SELECT b.id, b.bom_no, b.version, b.status, b.bom_type,
               p.code AS product_code, p.name AS product_name, p.specification
        FROM boms b
        LEFT JOIN products p ON p.id=b.product_id
        ORDER BY b.id DESC
        LIMIT 500
        """
    )
    source_bom = (form_state or {}).get("source_bom") or (_find_bom_by_key((form_state or {}).get("source_bom_key"), query_one) if (form_state or {}).get("source_bom_key") else None)
    source_items = _bom_items(source_bom["id"], query_rows) if source_bom else []
    source_detail = _detail_bom(source_bom, query_one, query_rows) if source_bom else None
    impact = _ecn_impact_summary(source_detail or source_bom, source_items, query_rows) if source_bom else None
    return {
        "bom_options": bom_options,
        "status_options": [("draft", "草稿"), ("submitted", "已提交")],
        "form_state": form_state or {"ecn_no": _next_ecn_no(query_one), "title": "", "change_reason": "", "owner": "", "requested_date": str(date.today()), "status": "draft", "source_bom_key": "", "target_bom_key": "", "impact_summary": ""},
        "ecn": ecn,
        "errors": errors or [],
        "mode": mode,
        "source_bom": source_detail,
        "impact": impact,
    }


def update_bom_from_form(bom, query_one, query_rows, execute_db, log_action=None, run_in_transaction=None):
    form_state = _posted_bom_form_state()
    item_rows, errors = _validate_bom_form_state(form_state, query_one, query_rows, current_bom_id=bom["id"])
    if errors:
        flash("BOM修改失败，请按提示修正后再保存。", "warning")
        return False, form_state, errors
    if _bom_status_key(bom.get("status")) != "draft":
        flash("当前BOM状态不允许修改。", "warning")
        return False, form_state, ["只有草稿状态的BOM允许修改。"]
    def operation(cursor):
        tx_query_one = query_one
        tx_execute_db = execute_db
        if cursor is not None:
            tx_query, tx_execute_db, _tx_execute_and_return = cursor_db_helpers(cursor)
            tx_query_one = lambda sql, params=None: tx_query(sql, params, one=True)
        locked_bom = tx_query_one("SELECT id, status FROM boms WHERE id=%s FOR UPDATE", (bom["id"],))
        if not locked_bom:
            raise ValueError("BOM not found.")
        if _bom_status_key(locked_bom.get("status")) != "draft":
            raise ValueError("BOM is no longer editable.")
        tx_execute_db("UPDATE boms SET product_id=%s, bom_no=%s, version=%s, bom_type=%s, status=%s, effective_date=%s, expiry_date=%s, remark=%s WHERE id=%s", (int(form_state["product_id"]), form_state["bom_no"], form_state["version"], form_state["bom_type"], form_state["status"], form_state["effective_date"] or None, form_state["expiry_date"] or None, _compose_bom_change_remark(form_state.get("remark"), form_state.get("change_reason")), bom["id"]))
        tx_execute_db("DELETE FROM bom_items WHERE bom_id=%s", (bom["id"],))
        _insert_bom_items(bom["id"], item_rows, tx_execute_db)

    if run_in_transaction:
        run_in_transaction(operation)
    else:
        operation(None)
    if log_action:
        log_action("修改BOM", form_state["bom_no"], f"version={form_state['version']}; change_reason={'yes' if form_state.get('change_reason') else 'no'}")
    flash("BOM已修改。", "success")
    return True, form_state, []


def _set_bom_status(bom, status, execute_db, log_action=None, action="BOM状态", remark=""):
    execute_db("UPDATE boms SET status=%s WHERE id=%s", (status, bom["id"]))
    if log_action:
        log_action(action, bom["bom_no"], remark or f"status={status}")


def _update_ecn_target(ecn_no, target_bom_id, execute_db, log_action=None):
    if not ecn_no or not target_bom_id:
        return
    execute_db("UPDATE bom_engineering_changes SET target_bom_id=%s, updated_at=CURRENT_TIMESTAMP WHERE ecn_no=%s", (target_bom_id, ecn_no))
    if log_action:
        log_action("工程变更关联升版BOM", ecn_no, f"target_bom_id={target_bom_id}")


def _set_ecn_status(ecn, status, execute_db, log_action=None, remark=""):
    execute_db("UPDATE bom_engineering_changes SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s", (status, ecn["id"]))
    if log_action:
        log_action("工程变更状态", ecn["ecn_no"], remark or f"status={status}")


def render_ecn_list(query_rows, query_one, execute_db=None):
    _ensure_bom_ecn_tables(execute_db)
    filters = _ecn_list_filters()
    rows = _ecn_list_rows(query_rows, filters)
    export_query = urlencode({key: value for key, value in filters.items() if value})
    return render_template(
        "bom_ecn_list.html",
        rows=rows,
        filters=filters,
        active_filter_count=sum(1 for value in filters.values() if value),
        status_options=[("", "全部状态"), ("draft", "草稿"), ("submitted", "已提交"), ("approved", "已审核"), ("closed", "已关闭"), ("voided", "已作废")],
        export_url="/bom/ecn?" + (export_query + "&" if export_query else "") + "export=csv",
    )


def render_ecn_detail(ecn_key, query_one, query_rows, execute_db=None):
    _ensure_bom_ecn_tables(execute_db)
    ecn = _find_ecn_by_key(ecn_key, query_one)
    if not ecn:
        return render_template("bom_ecn_detail.html", ecn=None, source_bom=None, target_bom=None, source_items=[], target_items=[], impact=None)
    if str(ecn_key).isdigit() and ecn.get("ecn_no"):
        return redirect(url_for("bom_ecn_detail", ecn_key=ecn["ecn_no"]))
    source_bom = _detail_bom(_find_bom_by_key(ecn.get("source_bom_id"), query_one), query_one, query_rows) if ecn.get("source_bom_id") else None
    target_bom = _detail_bom(_find_bom_by_key(ecn.get("target_bom_id"), query_one), query_one, query_rows) if ecn.get("target_bom_id") else None
    source_items = _bom_items(source_bom["id"], query_rows) if source_bom else []
    target_items = _bom_items(target_bom["id"], query_rows) if target_bom else []
    impact = _ecn_impact_summary(source_bom, source_items, query_rows) if source_bom else None
    ecn["status_key"] = _ecn_status_key(ecn.get("status"))
    ecn["status_label"] = _ecn_status_label(ecn.get("status"))
    return render_template("bom_ecn_detail.html", ecn=ecn, source_bom=source_bom, target_bom=target_bom, source_items=source_items, target_items=target_items, impact=impact)


def render_bom_detail(bom_key, query_one, query_rows, detail_endpoint="bom_detail", back_url="/bom"):
    bom = _find_bom_by_key(bom_key, query_one)
    if not bom:
        return render_template("bom_trace_detail.html", bom=None, items=[], back_url=back_url, quality_issues=[])
    if str(bom_key).isdigit() and bom.get("bom_no"):
        return redirect(url_for(detail_endpoint, bom_key=bom["bom_no"]))
    detail = _detail_bom(bom, query_one, query_rows)
    items = _bom_items(bom["id"], query_rows)
    bom_drilldown = _bom_readonly_drilldown(detail, items, query_rows)
    version_rows = query_rows(
        """
        SELECT b.id, b.bom_no, b.version, b.status, b.bom_type,
               b.effective_date, b.expiry_date,
               COALESCE(COUNT(bi.id), 0) AS item_count
        FROM boms b
        LEFT JOIN bom_items bi ON bi.bom_id=b.id
        WHERE b.product_id=%s
        GROUP BY b.id
        ORDER BY CASE WHEN b.id=%s THEN 0 ELSE 1 END, b.effective_date DESC NULLS LAST, b.id DESC
        LIMIT 30
        """,
        (bom.get("product_id"), bom.get("id")),
    )
    versions = []
    for version_row in version_rows:
        version = dict(version_row)
        version["is_current"] = int(version.get("id") or 0) == int(bom.get("id") or 0)
        version["status_label"] = _bom_status_label(version.get("status"))
        version["bom_type_label"] = _bom_type_label(version.get("bom_type"))
        version["detail_url"] = url_for("bom_detail", bom_key=version.get("bom_no") or version.get("id"))
        version["copy_upgrade_url"] = url_for("bom_copy", bom_key=version.get("bom_no") or version.get("id"), upgrade=1)
        version["date_conflict"] = bool(not version["is_current"] and _date_range_overlap(detail.get("effective_date"), detail.get("expiry_date"), version.get("effective_date"), version.get("expiry_date")))
        versions.append(version)
    history = query_rows(
        """
        SELECT id, username, action, target, remark, created_at
        FROM operation_logs
        WHERE action IN ('新增BOM', '修改BOM', '复制升版BOM', '导入BOM', '审核BOM', '反审核BOM', '冻结BOM', '作废BOM', '恢复BOM草稿')
          AND (target=%s OR target LIKE %s OR remark ILIKE %s)
        ORDER BY created_at DESC, id DESC
        LIMIT 30
        """,
        (bom.get("bom_no") or "", f"{bom.get('bom_no') or ''} -> %", f"%{bom.get('bom_no') or ''}%"),
    )
    quality_issues = []
    if detail.get("version_date_conflict"):
        quality_issues.append(f"有效期与 {detail['version_date_conflict'].get('bom_no')} 重叠。")
    return render_template("bom_trace_detail.html", bom=detail, items=items, bom_versions=versions, bom_history=history, bom_drilldown=bom_drilldown, back_url=back_url, quality_issues=quality_issues)


def _preferred_child_bom(product_id, query_one):
    row = query_one(
        """
        SELECT id
        FROM boms
        WHERE product_id=%s
        ORDER BY CASE WHEN COALESCE(status, '') IN ('released', 'approved', 'active', '已发布', '已审核', '启用') THEN 0 ELSE 1 END,
                 COALESCE(effective_date, '1900-01-01') DESC,
                 id DESC
        LIMIT 1
        """,
        (product_id,),
    )
    return int(row["id"]) if row else None


def _build_bom_structure_node(bom_id, query_one, query_rows, visited=None, depth=1, max_depth=8):
    visited = set(visited or set())
    bom = query_one("SELECT * FROM boms WHERE id=%s", (bom_id,))
    if not bom:
        return None
    detail = _detail_bom(dict(bom), query_one, query_rows)
    node = {"bom": detail, "items": [], "depth": depth, "cycle": False, "max_depth_reached": False}
    if bom_id in visited:
        node["cycle"] = True
        return node
    if depth > max_depth:
        node["max_depth_reached"] = True
        return node
    next_visited = set(visited)
    next_visited.add(bom_id)
    for item in _bom_items(bom_id, query_rows):
        child_bom_id = _preferred_child_bom(item.get("product_id"), query_one)
        item["child_bom"] = None
        item["child_cycle"] = False
        if child_bom_id:
            if child_bom_id in next_visited:
                child_bom = query_one("SELECT * FROM boms WHERE id=%s", (child_bom_id,))
                item["child_bom"] = {"bom": _detail_bom(dict(child_bom), query_one, query_rows) if child_bom else None, "items": [], "depth": depth + 1, "cycle": True, "max_depth_reached": False}
                item["child_cycle"] = True
            else:
                item["child_bom"] = _build_bom_structure_node(child_bom_id, query_one, query_rows, visited=next_visited, depth=depth + 1, max_depth=max_depth)
        node["items"].append(item)
    return node


def _annotate_structure_issues(node):
    if not node:
        return {"total_nodes": 0, "total_items": 0, "issue_nodes": 0, "cycle_count": 0}
    total_nodes = 1
    total_items = len(node.get("items") or [])
    issue_nodes = 1 if node.get("cycle") or node.get("max_depth_reached") else 0
    cycle_count = 1 if node.get("cycle") else 0
    node["has_issue"] = bool(issue_nodes)
    for item in node.get("items") or []:
        item["has_issue"] = bool(item.get("child_cycle") or any(item.get(flag) for flag in ("product_name_dirty", "specification_dirty", "display_unit_dirty", "remark_dirty")))
        child = item.get("child_bom")
        if child:
            child_stats = _annotate_structure_issues(child)
            total_nodes += child_stats["total_nodes"]
            total_items += child_stats["total_items"]
            issue_nodes += child_stats["issue_nodes"]
            cycle_count += child_stats["cycle_count"]
            item["has_issue"] = item["has_issue"] or child.get("has_issue", False)
    return {"total_nodes": total_nodes, "total_items": total_items, "issue_nodes": issue_nodes, "cycle_count": cycle_count}


def _flatten_bom_structure(node, rows=None):
    rows = rows if rows is not None else []
    if not node:
        return rows
    bom = node.get("bom") or {}
    for item in node.get("items") or []:
        child = item.get("child_bom")
        child_bom = child.get("bom") if child else {}
        rows.append([node.get("depth"), bom.get("bom_no") or "", bom.get("product_code") or "", item.get("product_code") or "", item.get("product_name_display") or "", item.get("specification_display") or "", item.get("quantity") or "", item.get("display_unit_display") or "", item.get("loss_rate") or "", child_bom.get("bom_no") if child_bom else "", "异常" if item.get("has_issue") else ""])
        if child:
            _flatten_bom_structure(child, rows)
    return rows


def render_bom_structure(bom_key, query_one, query_rows):
    bom = _find_bom_by_key(bom_key, query_one)
    if not bom:
        return render_template("bom_structure.html", root=None, bom_key=bom_key)
    if str(bom_key).isdigit() and bom.get("bom_no"):
        return redirect(url_for("bom_structure", bom_key=bom["bom_no"]))
    root = _build_bom_structure_node(int(bom["id"]), query_one, query_rows)
    stats = _annotate_structure_issues(root)
    if _export_format() == "xlsx" or request.args.get("export") == "csv":
        rows = [["层级", "BOM编号", "父项编码", "物料编码", "物料名称", "规格", "数量", "单位", "损耗率%", "下级BOM", "异常"]]
        rows.extend(_flatten_bom_structure(root))
        bom_no = ((root or {}).get("bom") or {}).get("bom_no") or "bom-structure"
        return _csv_response(f"bom-structure-{bom_no}.csv", rows)
    issue_only = request.args.get("view") in {"issues", "issue", "abnormal"}
    return render_template("bom_structure.html", root=root, bom_key=bom.get("bom_no") or bom_key, stats=stats, issue_only=issue_only)


def render_bom_detail_export(bom_key, query_one, query_rows):
    bom = _find_bom_by_key(bom_key, query_one)
    if not bom:
        flash("未找到BOM，无法导出明细。", "warning")
        return redirect("/bom")
    detail = _detail_bom(bom, query_one, query_rows)
    items = _bom_items(bom["id"], query_rows)
    rows = [
        ["BOM编号", detail.get("bom_no") or ""],
        ["版本", detail.get("version") or ""],
        [],
        ["物料编码", "物料名称", "规格", "数量", "单位", "损耗率%", "备注"],
    ]
    rows.extend([[item.get("product_code") or "", item.get("product_name_display") or "", item.get("specification_display") or "", item.get("quantity") or "", item.get("display_unit_display") or "", item.get("loss_rate") or "", item.get("remark_display") or ""] for item in items])
    return _csv_response(f"bom-{detail.get('bom_no') or detail.get('id')}.csv", rows)


def _parse_bom_import_csv(upload):
    if not upload or not upload.filename:
        return None, ["请选择CSV文件。"]
    raw = upload.read()
    if not raw:
        return None, ["CSV文件为空。"]
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        return None, ["CSV文件编码无法识别，请使用UTF-8或Excel CSV。"]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return None, ["CSV缺少表头。"]
    rows = [(line_no, row) for line_no, row in enumerate(reader, start=2) if any(str(value or "").strip() for value in row.values())]
    if not rows:
        return None, ["CSV没有有效数据行。"]
    return rows, []


def _csv_cell(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def import_bom_from_csv(upload, query_one, query_rows, execute_db, execute_and_return, log_action=None):
    csv_rows, errors = _parse_bom_import_csv(upload)
    if errors:
        return None, errors
    grouped = {}
    for line_no, row in csv_rows:
        bom_no = _csv_cell(row, "BOM编号", "bom_no", "BOM No")
        grouped.setdefault(bom_no, []).append((line_no, row))
    if len(grouped) != 1 or not next(iter(grouped), ""):
        return None, ["一次导入只允许创建一个BOM编号。"]
    bom_no, rows = next(iter(grouped.items()))
    if query_one("SELECT id FROM boms WHERE bom_no=%s", (bom_no,)):
        return None, [f"BOM编号 {bom_no} 已存在，导入不会覆盖已有BOM。"]
    header = rows[0][1]
    parent_code = _csv_cell(header, "适用产品编码", "父项编码", "产品编码", "parent_code")
    parent = _product_by_code(parent_code, query_one)
    if not parent:
        return None, [f"适用产品编码 {parent_code} 不存在。"]
    form_state = {
        "product_id": str(parent["id"]),
        "bom_no": bom_no,
        "version": _csv_cell(header, "版本", "version") or "V1.0",
        "bom_type": _csv_cell(header, "BOM类型", "类型", "bom_type") or "engineering",
        "status": "draft",
        "effective_date": _csv_cell(header, "生效日期", "effective_date"),
        "expiry_date": _csv_cell(header, "失效日期", "expiry_date"),
        "items": [],
    }
    for line_no, row in rows:
        child_code = _csv_cell(row, "子件编码", "子项编码", "物料编码", "child_code")
        child = _product_by_code(child_code, query_one)
        if not child:
            errors.append(f"第{line_no}行：子件编码 {child_code} 不存在。")
            continue
        form_state["items"].append({"product_id": str(child["id"]), "quantity": _csv_cell(row, "数量", "用量", "quantity"), "unit": _csv_cell(row, "单位", "unit"), "loss_rate": _csv_cell(row, "损耗率%", "损耗率", "loss_rate") or "0", "is_optional": _csv_cell(row, "可选替代", "is_optional") in {"是", "1", "true", "Y", "y"}, "remark": _csv_cell(row, "备注", "remark")})
    item_rows, validation_errors = _validate_bom_form_state(form_state, query_one, query_rows)
    errors.extend(validation_errors)
    if errors:
        return None, errors
    bom = execute_and_return("INSERT INTO boms (product_id, bom_no, version, bom_type, status, effective_date, expiry_date, remark) VALUES (%s,%s,%s,%s,'draft',%s,%s,%s) RETURNING id, bom_no", (int(form_state["product_id"]), form_state["bom_no"], form_state["version"], form_state["bom_type"], form_state["effective_date"] or None, form_state["expiry_date"] or None, "CSV导入创建草稿BOM"))
    _insert_bom_items(bom["id"], item_rows, execute_db)
    if log_action:
        log_action("导入BOM", bom["bom_no"], f"version={form_state['version']}; lines={len(item_rows)}")
    return bom, []


def register_bom_routes(app, login_required, query_rows, query_one, columns, execute_db=None, execute_and_return=None, log_action=None):
    @app.get("/bom", endpoint="bom_list")
    @login_required
    def bom_list():
        return render_bom_dashboard(query_rows, columns)

    @app.get("/bom/ecn", endpoint="bom_ecn_list")
    @login_required
    def bom_ecn_list():
        _ensure_bom_ecn_tables(execute_db)
        if _export_format() == "xlsx" or request.args.get("export") == "csv":
            filters = _ecn_list_filters()
            out = [["工程变更单号", "主题", "状态", "影响BOM", "升版BOM", "负责人", "申请日期"]]
            for row in _ecn_list_rows(query_rows, filters, limit=1000):
                out.append([row.get("ecn_no") or "", row.get("title") or "", row.get("status_label") or "", row.get("source_bom_label") or "", row.get("target_bom_label") or "", row.get("owner") or "", row.get("requested_date") or ""])
            return _csv_response("bom-ecn-list.csv", out)
        return render_ecn_list(query_rows, query_one, execute_db)

    @app.route("/bom/ecn/new", methods=["GET", "POST"], endpoint="bom_ecn_new")
    @login_required
    def bom_ecn_new():
        _ensure_bom_ecn_tables(execute_db)
        if not execute_db or not execute_and_return:
            flash("工程变更保存接口未启用。", "danger")
            return redirect("/bom/ecn")
        if request.method == "POST":
            form_state = _posted_ecn_form_state(query_one)
            errors = _validate_ecn_form_state(form_state, query_one)
            if errors:
                return render_template("bom_ecn_form.html", **_ecn_form_context(query_rows, query_one, form_state, errors=errors))
            ecn = execute_and_return(
                """
                INSERT INTO bom_engineering_changes
                    (ecn_no, title, change_reason, status, owner, requested_date, source_bom_id, target_bom_id, impact_summary)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, ecn_no
                """,
                (form_state["ecn_no"], form_state["title"], form_state["change_reason"], form_state["status"], form_state["owner"] or None, form_state["requested_date"] or None, form_state["source_bom"]["id"], (form_state.get("target_bom") or {}).get("id"), form_state["impact_summary"] or None),
            )
            for detail in form_state.get("details", []):
                execute_db(
                    """
                    INSERT INTO bom_engineering_change_details
                        (ecn_id, material, specification, unit, old_value, new_value)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (ecn["id"], detail["material"], detail["specification"], detail["unit"], detail["old_value"], detail["new_value"]),
                )
            if log_action:
                log_action("新增工程变更单", ecn["ecn_no"], f"source_bom={form_state['source_bom'].get('bom_no')}")
            flash("工程变更单已保存。", "success")
            return redirect(url_for("bom_ecn_detail", ecn_key=ecn["ecn_no"]))
        form_state = {"ecn_no": _next_ecn_no(query_one), "title": "", "change_reason": "", "owner": "", "requested_date": str(date.today()), "status": "draft", "source_bom_key": request.args.get("source_bom", ""), "target_bom_key": "", "impact_summary": ""}
        if form_state["source_bom_key"]:
            form_state["source_bom"] = _find_bom_by_key(form_state["source_bom_key"], query_one)
        return render_template("bom_ecn_form.html", **_ecn_form_context(query_rows, query_one, form_state))

    @app.route("/bom/ecn/<path:ecn_key>/edit", methods=["GET", "POST"], endpoint="bom_ecn_edit")
    @login_required
    def bom_ecn_edit(ecn_key):
        _ensure_bom_ecn_tables(execute_db)
        ecn = _find_ecn_by_key(ecn_key, query_one)
        if not ecn:
            return render_template("bom_ecn_detail.html", ecn=None, source_bom=None, target_bom=None, source_items=[], target_items=[], impact=None)
        if _ecn_status_key(ecn.get("status")) not in {"draft", "submitted"}:
            flash("只有草稿或已提交的工程变更单允许修改。", "warning")
            return redirect(url_for("bom_ecn_detail", ecn_key=ecn["ecn_no"]))
        if request.method == "POST":
            form_state = _posted_ecn_form_state(query_one)
            errors = _validate_ecn_form_state(form_state, query_one, ecn["id"])
            if errors:
                return render_template("bom_ecn_form.html", **_ecn_form_context(query_rows, query_one, form_state, ecn=ecn, errors=errors, mode="edit"))
            def operation(cursor):
                tx_query, tx_execute_db, _tx_execute_and_return = cursor_db_helpers(cursor)
                tx_query_one = lambda sql, params=None: tx_query(sql, params, one=True)
                locked_ecn = tx_query_one("SELECT id, status FROM bom_engineering_changes WHERE id=%s FOR UPDATE", (ecn["id"],))
                if not locked_ecn:
                    raise ValueError("ECN not found.")
                if _ecn_status_key(locked_ecn.get("status")) not in {"draft", "submitted"}:
                    raise ValueError("ECN is no longer editable.")
                tx_execute_db(
                    """
                    UPDATE bom_engineering_changes
                    SET ecn_no=%s, title=%s, change_reason=%s, status=%s, owner=%s,
                        requested_date=%s, source_bom_id=%s, target_bom_id=%s,
                        impact_summary=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                    """,
                    (form_state["ecn_no"], form_state["title"], form_state["change_reason"], form_state["status"], form_state["owner"] or None, form_state["requested_date"] or None, form_state["source_bom"]["id"], (form_state.get("target_bom") or {}).get("id"), form_state["impact_summary"] or None, ecn["id"]),
                )
                tx_execute_db("DELETE FROM bom_engineering_change_details WHERE ecn_id=%s", (ecn["id"],))
                for detail in form_state.get("details", []):
                    tx_execute_db(
                        """
                        INSERT INTO bom_engineering_change_details
                            (ecn_id, material, specification, unit, old_value, new_value)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (ecn["id"], detail["material"], detail["specification"], detail["unit"], detail["old_value"], detail["new_value"]),
                    )

            app.extensions["run_in_transaction"](operation)
            if log_action:
                log_action("修改工程变更单", form_state["ecn_no"], f"status={form_state['status']}")
            flash("工程变更单已修改。", "success")
            return redirect(url_for("bom_ecn_detail", ecn_key=form_state["ecn_no"]))
        form_state = {
            "ecn_no": ecn.get("ecn_no") or "",
            "title": ecn.get("title") or "",
            "change_reason": ecn.get("change_reason") or "",
            "owner": ecn.get("owner") or "",
            "requested_date": str(ecn.get("requested_date") or ""),
            "status": ecn.get("status") or "draft",
            "source_bom_key": str(ecn.get("source_bom_id") or ""),
            "target_bom_key": str(ecn.get("target_bom_id") or ""),
            "impact_summary": ecn.get("impact_summary") or "",
        }
        form_state["source_bom"] = _find_bom_by_key(form_state["source_bom_key"], query_one) if form_state["source_bom_key"] else None
        form_state["target_bom"] = _find_bom_by_key(form_state["target_bom_key"], query_one) if form_state["target_bom_key"] else None
        return render_template("bom_ecn_form.html", **_ecn_form_context(query_rows, query_one, form_state, ecn=ecn, mode="edit"))

    @app.post("/bom/ecn/<path:ecn_key>/<action>", endpoint="bom_ecn_action")
    @login_required
    def bom_ecn_action(ecn_key, action):
        _ensure_bom_ecn_tables(execute_db)
        ecn = _find_ecn_by_key(ecn_key, query_one)
        if ecn:
            current = _ecn_status_key(ecn.get("status"))
            transitions = {
                "submit": ({"draft"}, "submitted", "提交工程变更"),
                "approve": ({"submitted"}, "approved", "审核工程变更"),
                "close": ({"approved"}, "closed", "关闭工程变更"),
                "void": ({"draft", "submitted"}, "voided", "作废工程变更"),
            }
            allowed, next_status, label = transitions.get(action, (set(), current, "工程变更状态"))
            if current in allowed:
                _set_ecn_status(ecn, next_status, execute_db, log_action, label)
                flash(f"工程变更单已{_ecn_status_label(next_status)}。", "success")
            else:
                flash("当前状态不允许执行该操作。", "warning")
        return redirect(url_for("bom_ecn_detail", ecn_key=(ecn or {}).get("ecn_no", ecn_key)))

    @app.get("/bom/ecn/<path:ecn_key>", endpoint="bom_ecn_detail")
    @login_required
    def bom_ecn_detail(ecn_key):
        return render_ecn_detail(ecn_key, query_one, query_rows, execute_db)

    @app.get("/bom/import-template", endpoint="bom_import_template")
    @login_required
    def bom_import_template():
        return _csv_response("bom-import-template.csv", [["BOM编号", "适用产品编码", "版本", "BOM类型", "生效日期", "失效日期", "子件编码", "数量", "单位", "损耗率%", "可选替代", "备注"], ["BOM-LM-MG-V1", "CP-LM-MG", "V1.0", "engineering", "2026-01-01", "", "WL-BASE-001", "1", "件", "0", "否", "示例行，导入前删除"]])

    @app.route("/bom/import", methods=["GET", "POST"], endpoint="bom_import")
    @login_required
    def bom_import():
        errors = []
        if request.method == "POST":
            if not execute_db or not execute_and_return:
                errors = ["BOM导入接口未启用。"]
            else:
                bom, errors = import_bom_from_csv(request.files.get("file"), query_one, query_rows, execute_db, execute_and_return, log_action)
                if bom:
                    flash("BOM导入成功。", "success")
                    return redirect(url_for("bom_detail", bom_key=bom["bom_no"]))
        return render_template("bom_import.html", errors=errors)

    @app.route("/bom/new", methods=["GET", "POST"], endpoint="bom_new")
    @login_required
    def bom_new():
        if request.method == "POST":
            if not execute_db or not execute_and_return:
                flash("BOM保存接口未启用。", "danger")
                return redirect("/bom")
            bom, form_state, form_errors = create_bom_from_form(query_one, query_rows, execute_db, execute_and_return, log_action)
            if bom:
                return redirect(url_for("bom_detail", bom_key=bom["bom_no"]))
            return render_bom_form(query_rows, form_state, form_errors)
        return render_bom_form(query_rows)

    @app.route("/bom/<path:bom_key>/edit", methods=["GET", "POST"], endpoint="bom_edit")
    @login_required
    def bom_edit(bom_key):
        bom = _find_bom_by_key(bom_key, query_one)
        if not bom:
            return render_template("bom_trace_detail.html", bom=None, items=[], back_url="/bom", quality_issues=[])
        if _bom_status_key(bom.get("status")) != "draft":
            flash("只有草稿BOM允许修改；已发布BOM请复制升版为草稿。", "warning")
            return redirect(url_for("bom_detail", bom_key=bom["bom_no"]))
        if request.method == "POST":
            runner = app.extensions.get("run_in_transaction")
            if runner:
                def operation(cursor):
                    tx_query, tx_execute_db, _tx_execute_and_return = cursor_db_helpers(cursor)
                    tx_query_one = lambda sql, params=None: tx_query(sql, params, one=True)
                    tx_query_rows = lambda sql, params=None: tx_query(sql, params)
                    locked_bom = tx_query_one("SELECT * FROM boms WHERE id=%s FOR UPDATE", (bom["id"],))
                    if not locked_bom:
                        return False, _posted_bom_form_state(), ["BOM not found."]
                    return update_bom_from_form(locked_bom, tx_query_one, tx_query_rows, tx_execute_db, None)

                saved, form_state, form_errors = runner(operation)
                if saved and log_action:
                    log_action("修改BOM", form_state["bom_no"], f"version={form_state['version']}; change_reason={'yes' if form_state.get('change_reason') else 'no'}")
            else:
                saved, form_state, form_errors = update_bom_from_form(
                    bom,
                    query_one,
                    query_rows,
                    execute_db,
                    log_action,
                    run_in_transaction=app.extensions.get("run_in_transaction"),
                )
            if saved:
                return redirect(url_for("bom_detail", bom_key=form_state["bom_no"]))
            return render_bom_form(query_rows, form_state, form_errors, mode="edit", bom=bom)
        return render_bom_form(query_rows, _bom_form_state_from_db(bom, query_rows), [], mode="edit", bom=bom)

    @app.get("/bom/<path:bom_key>/copy", endpoint="bom_copy")
    @login_required
    def bom_copy(bom_key):
        bom = _find_bom_by_key(bom_key, query_one)
        if not bom:
            return render_template("bom_trace_detail.html", bom=None, items=[], back_url="/bom", quality_issues=[])
        upgrade = request.args.get("upgrade") == "1" or _bom_status_key(bom.get("status")) == "released"
        return render_bom_form(query_rows, _copy_bom_form_state(bom, query_rows, query_one, upgrade), [], mode="copy", bom=bom)

    @app.post("/bom/<path:bom_key>/approve", endpoint="bom_approve")
    @login_required
    def bom_approve_route(bom_key):
        bom = _find_bom_by_key(bom_key, query_one)
        if bom and _bom_status_key(bom.get("status")) == "draft":
            _set_bom_status(bom, "released", execute_db, log_action, "审核BOM", _text("opinion") or "审核通过")
        return redirect(url_for("bom_detail", bom_key=(bom or {}).get("bom_no", bom_key)))

    @app.post("/bom/<path:bom_key>/unapprove", endpoint="bom_unapprove")
    @login_required
    def bom_unapprove_route(bom_key):
        bom = _find_bom_by_key(bom_key, query_one)
        if bom and _bom_status_key(bom.get("status")) == "released":
            _set_bom_status(bom, "draft", execute_db, log_action, "反审核BOM", _text("reason") or "反审核")
        return redirect(url_for("bom_detail", bom_key=(bom or {}).get("bom_no", bom_key)))

    @app.post("/bom/<path:bom_key>/freeze", endpoint="bom_freeze")
    @login_required
    def bom_freeze_route(bom_key):
        bom = _find_bom_by_key(bom_key, query_one)
        if bom and _bom_status_key(bom.get("status")) in {"draft", "released"}:
            _set_bom_status(bom, "frozen", execute_db, log_action, "冻结BOM")
        return redirect(url_for("bom_detail", bom_key=(bom or {}).get("bom_no", bom_key)))

    @app.post("/bom/<path:bom_key>/obsolete", endpoint="bom_obsolete")
    @login_required
    def bom_obsolete_route(bom_key):
        bom = _find_bom_by_key(bom_key, query_one)
        if bom and _bom_status_key(bom.get("status")) in {"draft", "released", "frozen"}:
            _set_bom_status(bom, "obsolete", execute_db, log_action, "作废BOM")
        return redirect(url_for("bom_detail", bom_key=(bom or {}).get("bom_no", bom_key)))

    @app.post("/bom/<path:bom_key>/restore-draft", endpoint="bom_restore_draft")
    @login_required
    def bom_restore_draft_route(bom_key):
        bom = _find_bom_by_key(bom_key, query_one)
        if bom and _bom_status_key(bom.get("status")) == "frozen":
            _set_bom_status(bom, "draft", execute_db, log_action, "恢复BOM草稿")
        return redirect(url_for("bom_detail", bom_key=(bom or {}).get("bom_no", bom_key)))

    @app.get("/bom/<path:bom_key>/export", endpoint="bom_detail_export")
    @login_required
    def bom_detail_export(bom_key):
        return render_bom_detail_export(bom_key, query_one, query_rows)

    @app.get("/bom/<path:bom_key>/structure", endpoint="bom_structure")
    @login_required
    def bom_structure(bom_key):
        return render_bom_structure(bom_key, query_one, query_rows)

    @app.get("/bom/<path:bom_key>", endpoint="bom_detail")
    @login_required
    def bom_detail(bom_key):
        return render_bom_detail(bom_key, query_one, query_rows)
