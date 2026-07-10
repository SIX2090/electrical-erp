"""Document print routes: print template rendering and print preview."""
from datetime import datetime
from decimal import Decimal
import re

from flask import render_template
from markupsafe import escape as _html_escape
from markupsafe import Markup as _Markup


DETAIL_FIELDS = {"物料编码", "物料名称", "规格型号", "单位", "数量", "单价", "含税金额", "备注"}


def _clean_token(value):
    return str(value or "").strip()


def _format_decimal(value, places=2):
    try:
        return f"{Decimal(str(value or 0)):.{places}f}"
    except Exception:
        return str(value or "")


def _replace_tokens(value, mapping):
    """Substitute {{token}} placeholders with business data.

    Business data values (from `mapping`) are HTML-escaped so that any
    user-controlled text (customer name, product name, remark, etc.) cannot
    be rendered as HTML. Admin-authored HTML in `value` (the cell template)
    is preserved unchanged so legitimate layout tags (<b>, <u>, <br>) still
    render when the result is later marked ``|safe``.

    The return value is wrapped as :class:`markupsafe.Markup` so Jinja does
    not double-escape the already-escaped business data when the caller uses
    ``{{ cell.value }}`` without ``|safe``.
    """
    text = str(value or "")

    def repl(match):
        token = _clean_token(match.group(1))
        return str(_html_escape(str(mapping.get(token, ""))))

    return _Markup(re.sub(r"\{\{\s*(.*?)\s*\}\}", repl, text))


def _style_to_css(style, col):
    style = style or {}
    css = []
    if style.get("merged") and style.get("colSpan"):
        css.append(f"grid-column:{col} / span {int(style.get('colSpan') or 1)}")
    else:
        css.append(f"grid-column:{col}")
    if style.get("fontFamily"):
        css.append(f"font-family:{style['fontFamily']}")
    if style.get("fontSize"):
        css.append(f"font-size:{style['fontSize']}pt")
    if style.get("fontWeight"):
        css.append(f"font-weight:{style['fontWeight']}")
    if style.get("fontStyle"):
        css.append(f"font-style:{style['fontStyle']}")
    if style.get("textDecoration"):
        css.append(f"text-decoration:{style['textDecoration']}")
    if style.get("color"):
        css.append(f"color:{style['color']}")
    if style.get("textAlign"):
        css.append(f"text-align:{style['textAlign']}")
    if style.get("border"):
        css.append("border:1px solid #111827")
    if style.get("borderTop"):
        css.append(f"border-top:{style['borderTop']}")
    if style.get("borderRight"):
        css.append(f"border-right:{style['borderRight']}")
    if style.get("borderBottom"):
        css.append(f"border-bottom:{style['borderBottom']}")
    if style.get("borderLeft"):
        css.append(f"border-left:{style['borderLeft']}")
    return ";".join(css)


def _template_tokens(value):
    return {_clean_token(match.group(1)) for match in re.finditer(r"\{\{\s*(.*?)\s*\}\}", str(value or ""))}


def _build_print_template_grid(template, doc):
    layout = template.get("layout_json") or {}
    cells = layout.get("cells") or {}
    styles = layout.get("cell_styles") or {}
    col_widths = layout.get("col_widths") or {}
    grid_cols = int(layout.get("grid_cols") or 8)
    grid_rows = int(layout.get("grid_rows") or 20)
    columns = " ".join(f"minmax(0,{int(col_widths.get(str(col), 92))}fr)" for col in range(1, grid_cols + 1))

    header_map = {
        "单据编号": doc.get("number") or "",
        "单据日期": doc.get("date") or "",
        "供应商名称": doc.get("partner_name") or "",
        "客户名称": doc.get("partner_name") or "",
        "联系人": doc.get("contact_person") or "",
        "联系电话": doc.get("partner_phone") or "",
        "项目号": doc.get("project_code") or "",
        "柜号": doc.get("cabinet_no") or "",
        "仓库": doc.get("warehouse_name") or "",
        "业务员": doc.get("business_user") or "",
        "部门": doc.get("department") or "",
        "制单人": doc.get("created_by_name") or "",
        "审核人": doc.get("approved_by_name") or "",
        "数量合计": _format_decimal(doc.get("total_quantity"), 2),
        "金额合计": _format_decimal(doc.get("total_amount"), 2),
        "大写金额": doc.get("amount_upper") or "",
        "仓库签字": "",
        "主管签字": "",
        "经办人签字": "",
        "备注": doc.get("remark") or "",
    }
    detail_maps = []
    for row in doc.get("rows") or []:
        detail_maps.append(
            {
                "物料编码": row.get("product_code") or "",
                "物料名称": row.get("product_name") or "",
                "规格型号": row.get("specification") or "",
                "单位": row.get("unit") or "",
                "数量": _format_decimal(row.get("quantity"), 2),
                "单价": _format_decimal(row.get("unit_price"), 2),
                "含税金额": _format_decimal(row.get("amount_with_tax") or row.get("amount"), 2),
                "备注": row.get("remark") or row.get("lot_no") or "",
            }
        )

    source_rows = []
    detail_source_rows = set()
    for row in range(1, grid_rows + 1):
        row_keys = [f"{row}-{col}" for col in range(1, grid_cols + 1)]
        row_has_content = any(
            cells.get(key)
            or (styles.get(key) or {}).get("border")
            or (styles.get(key) or {}).get("borderTop")
            or (styles.get(key) or {}).get("borderRight")
            or (styles.get(key) or {}).get("borderBottom")
            or (styles.get(key) or {}).get("borderLeft")
            for key in row_keys
        )
        row_tokens = set()
        for key in row_keys:
            row_tokens.update(_template_tokens(cells.get(key, "")))
        if row_tokens & DETAIL_FIELDS:
            detail_source_rows.add(row)
            row_has_content = True
        if row_has_content:
            source_rows.append(row)

    rendered = []
    output_row = 0
    for row in source_rows:
        repeat_maps = detail_maps if row in detail_source_rows else [header_map]
        if row in detail_source_rows and not repeat_maps:
            repeat_maps = [{field: "" for field in DETAIL_FIELDS}]
        for mapping in repeat_maps:
            output_row += 1
            for col in range(1, grid_cols + 1):
                key = f"{row}-{col}"
                style = styles.get(key) or {}
                if style.get("covered"):
                    continue
                value = _replace_tokens(cells.get(key, ""), mapping)
                has_border = any(style.get(key) for key in ("border", "borderTop", "borderRight", "borderBottom", "borderLeft"))
                if not value and not has_border:
                    continue
                rendered.append(
                    {
                        "row": output_row,
                        "col": col,
                        "value": value,
                        "css": _style_to_css(style, col),
                        "border": bool(has_border),
                        "numeric": bool(re.fullmatch(r"-?\d+(?:\.\d+)?", str(value).strip())),
                    }
                )
    return {"columns": columns, "cells": rendered, "template": template}


def build_template_grid_for_document(document_type, doc, query_one):
    template = query_one(
        """
        SELECT *
        FROM print_templates
        WHERE document_type=%s AND status='enabled' AND is_default=TRUE
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (document_type,),
    )
    return _build_print_template_grid(template, doc) if template else None


def render_document_print(kind, order_id, query_one, query_rows, as_decimal):
    if kind == "sales":
        order = query_one(
            """
            SELECT so.*, c.name AS partner_name, c.contact_person, c.phone AS partner_phone,
                   w.name AS warehouse_name
            FROM sales_orders so
            LEFT JOIN customers c ON c.id=so.customer_id
            LEFT JOIN warehouses w ON w.id=so.warehouse_id
            WHERE so.id=%s
            """,
            (order_id,),
        )
        items = query_rows(
            """
            SELECT p.code AS product_code, p.name AS product_name, p.specification,
                   COALESCE(p.unit, '') AS unit, soi.quantity, soi.unit_price, soi.amount,
                   soi.tax_rate, soi.tax_amount, soi.amount_with_tax, soi.lot_no
            FROM sales_order_items soi
            LEFT JOIN products p ON p.id=soi.product_id
            WHERE soi.order_id=%s
            ORDER BY soi.id
            """,
            (order_id,),
        )
        title = "销售订单"
        date_value = order.get("order_date") if order else ""
        date_label = "订单日期"
        partner_label = "客户"
        extra_date_label = "交货日期"
        extra_date = order.get("delivery_date") if order else ""
        back_url = f"/sales/{order_id}"
    else:
        order = query_one(
            """
            SELECT po.*, s.name AS partner_name, s.contact_person, s.phone AS partner_phone,
                   w.name AS warehouse_name
            FROM purchase_orders po
            LEFT JOIN suppliers s ON s.id=po.supplier_id
            LEFT JOIN warehouses w ON w.id=po.warehouse_id
            WHERE po.id=%s
            """,
            (order_id,),
        )
        items = query_rows(
            """
            SELECT p.code AS product_code, p.name AS product_name, p.specification,
                   COALESCE(p.unit, '') AS unit, poi.quantity, poi.unit_price, poi.amount,
                   poi.tax_rate, poi.tax_amount, poi.amount_with_tax, poi.lot_no
            FROM purchase_order_items poi
            LEFT JOIN products p ON p.id=poi.product_id
            WHERE poi.order_id=%s
            ORDER BY poi.id
            """,
            (order_id,),
        )
        title = "采购订单"
        date_value = order.get("order_date") if order else ""
        date_label = "订单日期"
        partner_label = "供应商"
        extra_date_label = "预计到货"
        extra_date = order.get("expected_date") if order else ""
        back_url = f"/purchase_order/{order_id}"

    if not order:
        return render_template("simple_detail.html", title="单据不存在", row=None, back_url="/")

    doc = {
        "title": title,
        "subtitle": "机床 ERP 单据打印",
        "number": order.get("order_no"),
        "number_label": "单据编号",
        "date": date_value,
        "date_label": date_label,
        "status_label": order.get("status") or "未定",
        "info": [
            (partner_label, order.get("partner_name")),
            ("联系人", order.get("contact_person")),
            ("电话", order.get("partner_phone")),
            ("项目号", order.get("project_code")),
            ("柜号", order.get("cabinet_no")),
            ("仓库", order.get("warehouse_name")),
            (extra_date_label, extra_date),
        ],
        "columns": [
            ("product_code", "物料编码", ""),
            ("product_name", "物料名称", ""),
            ("specification", "规格", ""),
            ("unit", "单位", "center"),
            ("quantity", "数量", "right"),
            ("unit_price", "单价", "right money"),
            ("amount", "金额", "right money"),
            ("tax_rate", "税率", "right"),
            ("amount_with_tax", "含税金额", "right money"),
            ("lot_no", "批号", ""),
        ],
        "rows": items,
        "total_quantity": sum((as_decimal(row.get("quantity")) for row in items), Decimal("0")),
        "total_amount": order.get("amount_with_tax") or order.get("total_amount"),
        "remark": order.get("remark"),
        "signatures": ["制单", "审核", "仓库", "财务"],
        "print_time": datetime.now(),
        "back_url": back_url,
    }
    doc["partner_name"] = order.get("partner_name")
    doc["contact_person"] = order.get("contact_person")
    doc["partner_phone"] = order.get("partner_phone")
    doc["project_code"] = order.get("project_code")
    doc["cabinet_no"] = order.get("cabinet_no")
    doc["warehouse_name"] = order.get("warehouse_name")
    doc["business_user"] = order.get("business_user") or ""
    doc["department"] = order.get("department") or ""
    doc["created_by_name"] = order.get("created_by_name") or ""
    doc["approved_by_name"] = order.get("approved_by_name") or ""
    doc_type = "sales_order" if kind == "sales" else "purchase_order"
    template_grid = build_template_grid_for_document(doc_type, doc, query_one)
    return render_template("document_print.html", doc=doc, template_grid=template_grid)
