"""Print template routes: print template list, editor, and preview."""
from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

import bleach
from flask import flash, redirect, render_template, request, url_for


DOCUMENT_TYPES = [
    ("purchase_order", "采购订单", "采购"),
    ("sales_order", "销售订单", "销售"),
    ("purchase_receipt", "采购入库单", "库存"),
    ("shipment", "销售出库单", "销售"),
    ("subcontract_order", "委外加工单", "委外"),
    ("subcontract_issue", "委外发料单", "委外"),
    ("subcontract_receive", "委外收货单", "委外"),
    ("inventory_transfer", "库存调拨单", "库存"),
    ("voucher", "会计凭证", "财务"),
]

FIELD_GROUPS = [
    {
        "title": "往来单位字段",
        "fields": ["供应商名称", "客户名称", "联系人", "联系电话", "地址", "税号"],
    },
    {
        "title": "单据头字段",
        "fields": ["单据编号", "单据日期", "项目号", "机号", "部门", "业务员", "制单人", "审核人"],
    },
    {
        "title": "明细字段",
        "fields": ["物料编码", "物料名称", "规格型号", "单位", "数量", "单价", "含税金额", "备注"],
    },
    {
        "title": "合计与签字",
        "fields": ["数量合计", "金额合计", "大写金额", "仓库签字", "主管签字", "经办人签字"],
    },
]


DEFAULT_LAYOUT = {
    "paper": "A4",
    "orientation": "portrait",
    "grid_rows": 20,
    "grid_cols": 12,
    "version": 1,
}


SAFE_HTML_TAGS = {
    "a", "b", "br", "caption", "div", "em", "h1", "h2", "h3", "h4",
    "header", "footer", "hr", "i", "img", "li", "main", "ol", "p",
    "section", "small", "span", "strong", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "u", "ul",
}
SAFE_VOID_TAGS = {"br", "hr", "img"}
SAFE_GLOBAL_ATTRS = {
    "align", "alt", "class", "colspan", "data-cell", "data-field",
    "data-row", "height", "rowspan", "style", "title", "valign", "width",
}
SAFE_TAG_ATTRS = {
    "a": {"href", "target", "rel"},
    "img": {"src"},
}
BLOCKED_HTML_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta"}
UNSAFE_CSS_PATTERN = re.compile(r"(expression\s*\(|javascript:|behavior\s*:|-moz-binding|[<>])", re.IGNORECASE)
# 预处理：完全移除危险标签及其内容（避免 bleach strip 后内容残留）
_PRE_STRIP_PATTERN = re.compile(
    r"<(?:script|style|iframe|object|embed|link|meta)\b[^>]*>.*?</(?:script|style|iframe|object|embed|link|meta)>",
    re.IGNORECASE | re.DOTALL,
)


def _safe_url(value):
    text = (value or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if lower.startswith(("javascript:", "vbscript:", "data:text/html")):
        return ""
    if lower.startswith("data:"):
        return text if lower.startswith(("data:image/png", "data:image/jpeg", "data:image/gif", "data:image/webp")) else ""
    parsed = urlsplit(text)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return ""
    return text


def _safe_style(value):
    declarations = []
    for declaration in str(value or "").split(";"):
        if ":" not in declaration:
            continue
        name, raw = declaration.split(":", 1)
        name = name.strip().lower()
        raw = raw.strip()
        if not name or not raw or UNSAFE_CSS_PATTERN.search(raw):
            continue
        if "url(" in raw.lower() and "data:image/" not in raw.lower():
            continue
        declarations.append(f"{name}:{raw}")
    return ";".join(declarations)


class _SafeHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.block_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in BLOCKED_HTML_TAGS:
            self.block_depth += 1
            return
        if self.block_depth or tag not in SAFE_HTML_TAGS:
            return
        allowed_attrs = SAFE_GLOBAL_ATTRS | SAFE_TAG_ATTRS.get(tag, set())
        clean_attrs = []
        for name, value in attrs:
            name = (name or "").lower()
            if not name or name.startswith("on") or name not in allowed_attrs:
                continue
            if name in {"href", "src"}:
                value = _safe_url(value)
                if not value:
                    continue
            elif name == "style":
                value = _safe_style(value)
                if not value:
                    continue
            clean_attrs.append(f'{name}="{escape(str(value or ""), quote=True)}"')
        attr_text = f" {' '.join(clean_attrs)}" if clean_attrs else ""
        suffix = " /" if tag in SAFE_VOID_TAGS else ""
        self.parts.append(f"<{tag}{attr_text}{suffix}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in BLOCKED_HTML_TAGS and self.block_depth:
            self.block_depth -= 1
            return
        if self.block_depth or tag not in SAFE_HTML_TAGS or tag in SAFE_VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.block_depth:
            self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.block_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self.block_depth:
            self.parts.append(f"&#{name};")


def sanitize_template_html(value):
    text = str(value or "")
    # 预处理：完全移除危险标签及其内容
    text = _PRE_STRIP_PATTERN.sub("", text)
    # 第一道：bleach 专业净化，按白名单过滤标签和属性，限制 URL 协议
    bleach_attributes = {
        tag: list(SAFE_GLOBAL_ATTRS | SAFE_TAG_ATTRS.get(tag, set()))
        for tag in SAFE_HTML_TAGS
    }
    cleaned = bleach.clean(
        text,
        tags=SAFE_HTML_TAGS,
        attributes=bleach_attributes,
        protocols=["http", "https"],
        strip=True,
    )
    # 第二道：现有 parser 对 style CSS 和 href/src 做细粒度过滤
    parser = _SafeHtmlParser()
    parser.feed(cleaned)
    parser.close()
    return "".join(parser.parts)


def _sanitize_layout(layout):
    layout = dict(layout or {})
    cells = layout.get("cells") if isinstance(layout.get("cells"), dict) else {}
    layout["cells"] = {
        str(key): sanitize_template_html(value)
        for key, value in cells.items()
        if str(value or "").strip()
    }
    return layout


def _default_grid_layout(document_label: str) -> dict:
    cells = {
        "1-1": document_label,
        "3-1": "单据编号",
        "3-2": "{{ 单据编号 }}",
        "3-4": "单据日期",
        "3-5": "{{ 单据日期 }}",
        "3-7": "项目号",
        "3-8": "{{ 项目号 }}",
        "4-1": "往来单位",
        "4-2": "{{ 供应商名称 }}",
        "4-4": "机号",
        "4-5": "{{ 机号 }}",
        "4-7": "业务员",
        "4-8": "{{ 业务员 }}",
        "6-1": "物料编码",
        "6-2": "物料名称",
        "6-3": "规格型号",
        "6-4": "单位",
        "6-5": "数量",
        "6-6": "单价",
        "6-7": "含税金额",
        "6-8": "备注",
        "7-1": "{{ 物料编码 }}",
        "7-2": "{{ 物料名称 }}",
        "7-3": "{{ 规格型号 }}",
        "7-4": "{{ 单位 }}",
        "7-5": "{{ 数量 }}",
        "7-6": "{{ 单价 }}",
        "7-7": "{{ 含税金额 }}",
        "7-8": "{{ 备注 }}",
        "14-1": "数量合计",
        "14-2": "{{ 数量合计 }}",
        "14-4": "金额合计",
        "14-5": "{{ 金额合计 }}",
        "14-7": "大写金额",
        "14-8": "{{ 大写金额 }}",
        "17-1": "制单人",
        "17-2": "{{ 制单人 }}",
        "17-4": "审核人",
        "17-5": "{{ 审核人 }}",
        "17-7": "主管签字",
        "17-8": "{{ 主管签字 }}",
    }
    cell_styles = {
        "1-1": {"fontWeight": "700", "textAlign": "center", "fontSize": "18", "merged": True, "colSpan": 8},
        "1-2": {"covered": True, "mergeAnchor": "1-1"},
        "1-3": {"covered": True, "mergeAnchor": "1-1"},
        "1-4": {"covered": True, "mergeAnchor": "1-1"},
        "1-5": {"covered": True, "mergeAnchor": "1-1"},
        "1-6": {"covered": True, "mergeAnchor": "1-1"},
        "1-7": {"covered": True, "mergeAnchor": "1-1"},
        "1-8": {"covered": True, "mergeAnchor": "1-1"},
        "6-1": {"fontWeight": "700", "textAlign": "center", "border": True},
        "6-2": {"fontWeight": "700", "textAlign": "center", "border": True},
        "6-3": {"fontWeight": "700", "textAlign": "center", "border": True},
        "6-4": {"fontWeight": "700", "textAlign": "center", "border": True},
        "6-5": {"fontWeight": "700", "textAlign": "center", "border": True},
        "6-6": {"fontWeight": "700", "textAlign": "center", "border": True},
        "6-7": {"fontWeight": "700", "textAlign": "center", "border": True},
        "6-8": {"fontWeight": "700", "textAlign": "center", "border": True},
    }
    for row in range(7, 13):
        for col in range(1, 9):
            cell_styles[f"{row}-{col}"] = {"border": True}
    cell_styles["14-5"] = {"merged": True, "colSpan": 2}
    cell_styles["14-6"] = {"covered": True, "mergeAnchor": "14-5"}
    return {
        **DEFAULT_LAYOUT,
        "grid_cols": 8,
        "cells": cells,
        "cell_styles": cell_styles,
        "col_widths": {"1": 85, "2": 120, "3": 90, "4": 60, "5": 65, "6": 85, "7": 120, "8": 90},
        "version": 6,
    }


def _normalize_layout(layout_json, document_type: str) -> dict:
    if isinstance(layout_json, str):
        try:
            layout_json = json.loads(layout_json)
        except ValueError:
            layout_json = {}
    layout = {**DEFAULT_LAYOUT, **(layout_json or {})}
    if not layout.get("cells"):
        layout = _default_grid_layout(_document_label(document_type))
    return _sanitize_layout(layout)


def _initial_html(document_label: str) -> str:
    return f"""<div class="print-sheet-title">{document_label}</div>
<div class="print-sheet-meta">
    <span>单据编号：{{{{ 单据编号 }}}}</span>
    <span>单据日期：{{{{ 单据日期 }}}}</span>
    <span>项目号：{{{{ 项目号 }}}}</span>
    <span>机号：{{{{ 机号 }}}}</span>
</div>
<table class="print-sheet-lines">
    <thead>
        <tr>
            <th>物料编码</th>
            <th>物料名称</th>
            <th>规格型号</th>
            <th>单位</th>
            <th>数量</th>
            <th>备注</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>{{{{ 物料编码 }}}}</td>
            <td>{{{{ 物料名称 }}}}</td>
            <td>{{{{ 规格型号 }}}}</td>
            <td>{{{{ 单位 }}}}</td>
            <td>{{{{ 数量 }}}}</td>
            <td>{{{{ 备注 }}}}</td>
        </tr>
    </tbody>
</table>
<div class="print-sheet-sign">
    <span>制单人：{{{{ 制单人 }}}}</span>
    <span>审核人：{{{{ 审核人 }}}}</span>
    <span>主管签字：</span>
</div>"""


DOCUMENT_TYPES = [
    ("purchase_order", "采购订单", "采购"),
    ("sales_order", "销售订单", "销售"),
    ("purchase_receipt", "采购入库单", "库存"),
    ("shipment", "销售出库单", "销售"),
    ("subcontract_order", "委外加工单", "委外"),
    ("subcontract_issue", "委外发料单", "委外"),
    ("subcontract_receive", "委外收货单", "委外"),
    ("inventory_transfer", "库存调拨单", "库存"),
    ("voucher", "会计凭证", "财务"),
]

FIELD_GROUPS = [
    {
        "title": "往来单位字段",
        "fields": ["供应商名称", "客户名称", "联系人", "联系电话", "地址", "税号"],
    },
    {
        "title": "单据头字段",
        "fields": ["单据编号", "单据日期", "项目号", "机号", "部门", "业务员", "制单人", "审核人"],
    },
    {
        "title": "明细字段",
        "fields": ["物料编码", "物料名称", "规格型号", "单位", "数量", "单价", "含税金额", "备注"],
    },
    {
        "title": "合计与签字",
        "fields": ["数量合计", "金额合计", "大写金额", "仓库签字", "主管签字", "经办人签字"],
    },
]


def _default_grid_layout(document_label: str) -> dict:
    cells = {
        "1-1": document_label,
        "3-1": "单据编号",
        "3-2": "{{ 单据编号 }}",
        "3-4": "单据日期",
        "3-5": "{{ 单据日期 }}",
        "3-7": "项目号",
        "3-8": "{{ 项目号 }}",
        "4-1": "往来单位",
        "4-2": "{{ 供应商名称 }}",
        "4-4": "机号",
        "4-5": "{{ 机号 }}",
        "4-7": "业务员",
        "4-8": "{{ 业务员 }}",
        "6-1": "物料编码",
        "6-2": "物料名称",
        "6-3": "规格型号",
        "6-4": "单位",
        "6-5": "数量",
        "6-6": "单价",
        "6-7": "含税金额",
        "6-8": "备注",
        "7-1": "{{ 物料编码 }}",
        "7-2": "{{ 物料名称 }}",
        "7-3": "{{ 规格型号 }}",
        "7-4": "{{ 单位 }}",
        "7-5": "{{ 数量 }}",
        "7-6": "{{ 单价 }}",
        "7-7": "{{ 含税金额 }}",
        "7-8": "{{ 备注 }}",
        "14-1": "数量合计",
        "14-2": "{{ 数量合计 }}",
        "14-4": "金额合计",
        "14-5": "{{ 金额合计 }}",
        "14-7": "大写金额",
        "14-8": "{{ 大写金额 }}",
        "17-1": "制单人",
        "17-2": "{{ 制单人 }}",
        "17-4": "审核人",
        "17-5": "{{ 审核人 }}",
        "17-7": "主管签字",
        "17-8": "{{ 主管签字 }}",
    }
    cell_styles = {
        "1-1": {"fontWeight": "700", "textAlign": "center", "fontSize": "18", "merged": True, "colSpan": 8},
        "1-2": {"covered": True, "mergeAnchor": "1-1"},
        "1-3": {"covered": True, "mergeAnchor": "1-1"},
        "1-4": {"covered": True, "mergeAnchor": "1-1"},
        "1-5": {"covered": True, "mergeAnchor": "1-1"},
        "1-6": {"covered": True, "mergeAnchor": "1-1"},
        "1-7": {"covered": True, "mergeAnchor": "1-1"},
        "1-8": {"covered": True, "mergeAnchor": "1-1"},
    }
    for col in range(1, 9):
        cell_styles[f"6-{col}"] = {"fontWeight": "700", "textAlign": "center", "border": True}
    for row in range(7, 13):
        for col in range(1, 9):
            cell_styles[f"{row}-{col}"] = {"border": True}
    cell_styles["14-5"] = {"merged": True, "colSpan": 2}
    cell_styles["14-6"] = {"covered": True, "mergeAnchor": "14-5"}
    return {
        **DEFAULT_LAYOUT,
        "grid_cols": 8,
        "cells": cells,
        "cell_styles": cell_styles,
        "col_widths": {"1": 90, "2": 115, "3": 115, "4": 72, "5": 72, "6": 72, "7": 105, "8": 115},
        "version": 3,
    }

DOCUMENT_TYPES = [
    ("quotation", "报价单", "销售"),
    ("sales_order", "销售订单", "销售"),
    ("shipment", "销售发货单", "销售"),
    ("sales_return", "销售退货单", "销售"),
    ("sales_invoice", "销售发票登记", "财务"),
    ("purchase_order", "采购订单", "采购"),
    ("purchase_receipt", "采购入库单", "采购"),
    ("purchase_return", "采购退货单", "采购"),
    ("purchase_invoice", "采购发票登记", "财务"),
    ("supplier_quote", "供应商报价单", "采购"),
    ("subcontract_order", "委外加工单", "委外"),
    ("subcontract_issue", "委外发料单", "委外"),
    ("subcontract_receive", "委外收货单", "委外"),
    ("inventory_adjustment", "库存调整单", "库存"),
    ("inventory_transfer", "库存调拨单", "库存"),
    ("inventory_check", "库存盘点单", "库存"),
    ("inventory_assembly", "组装单", "库存"),
    ("inventory_disassembly", "拆卸单", "库存"),
    ("work_order", "生产工单", "生产"),
    ("work_order_issue", "工单领料单", "生产"),
    ("work_order_completion", "工单完工入库单", "生产"),
    ("work_order_requisition", "生产领料申请单", "生产"),
    ("quality_inspection", "质量检验单", "生产"),
    ("service_card", "设备服务档案", "售后"),
    ("service_order", "服务单", "售后"),
    ("service_rma", "RMA单", "售后"),
    ("voucher", "会计凭证", "财务"),
]


def _document_label(document_type: str) -> str:
    for value, label, _category in DOCUMENT_TYPES:
        if value == document_type:
            return label
    return document_type or "-"


def _initial_html(document_label: str) -> str:
    return f"""<div class="print-sheet-title">{document_label}</div>
<div class="print-sheet-meta">
    <span>单据编号：{{{{ 单据编号 }}}}</span>
    <span>单据日期：{{{{ 单据日期 }}}}</span>
    <span>项目号：{{{{ 项目号 }}}}</span>
    <span>机号：{{{{ 机号 }}}}</span>
</div>
<table class="print-sheet-lines">
    <thead>
        <tr>
            <th>物料编码</th>
            <th>物料名称</th>
            <th>规格型号</th>
            <th>单位</th>
            <th>数量</th>
            <th>备注</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>{{{{ 物料编码 }}}}</td>
            <td>{{{{ 物料名称 }}}}</td>
            <td>{{{{ 规格型号 }}}}</td>
            <td>{{{{ 单位 }}}}</td>
            <td>{{{{ 数量 }}}}</td>
            <td>{{{{ 备注 }}}}</td>
        </tr>
    </tbody>
</table>
<div class="print-sheet-sign">
    <span>制单人：{{{{ 制单人 }}}}</span>
    <span>审核人：{{{{ 审核人 }}}}</span>
    <span>主管签字：</span>
</div>"""


DOCUMENT_TYPES = [
    ("purchase_order", "采购订单", "采购"),
    ("sales_order", "销售订单", "销售"),
    ("purchase_receipt", "采购入库单", "库存"),
    ("shipment", "销售出库单", "销售"),
    ("subcontract_order", "委外加工单", "委外"),
    ("subcontract_issue", "委外发料单", "委外"),
    ("subcontract_receive", "委外收货单", "委外"),
    ("inventory_transfer", "库存调拨单", "库存"),
    ("voucher", "会计凭证", "财务"),
]

FIELD_GROUPS = [
    {"title": "往来单位字段", "fields": ["供应商名称", "客户名称", "联系人", "联系电话", "地址", "税号"]},
    {"title": "单据头字段", "fields": ["单据编号", "单据日期", "项目号", "机号", "仓库", "部门", "业务员", "制单人", "审核人"]},
    {"title": "明细字段", "fields": ["物料编码", "物料名称", "规格型号", "单位", "数量", "单价", "含税金额", "备注"]},
    {"title": "合计与签字", "fields": ["数量合计", "金额合计", "大写金额", "仓库签字", "主管签字", "经办人签字"]},
]


def _document_label(document_type: str) -> str:
    for value, label, _category in DOCUMENT_TYPES:
        if value == document_type:
            return label
    return document_type or "-"


def _default_grid_layout(document_label: str) -> dict:
    cells = {
        "1-1": document_label,
        "3-1": "单据编号", "3-2": "{{ 单据编号 }}", "3-4": "单据日期", "3-5": "{{ 单据日期 }}", "3-7": "项目号", "3-8": "{{ 项目号 }}",
        "4-1": "往来单位", "4-2": "{{ 供应商名称 }}{{ 客户名称 }}", "4-4": "机号", "4-5": "{{ 机号 }}", "4-7": "仓库", "4-8": "{{ 仓库 }}",
        "6-1": "物料编码", "6-2": "物料名称", "6-3": "规格型号", "6-4": "单位", "6-5": "数量", "6-6": "单价", "6-7": "含税金额", "6-8": "备注",
        "7-1": "{{ 物料编码 }}", "7-2": "{{ 物料名称 }}", "7-3": "{{ 规格型号 }}", "7-4": "{{ 单位 }}", "7-5": "{{ 数量 }}", "7-6": "{{ 单价 }}", "7-7": "{{ 含税金额 }}", "7-8": "{{ 备注 }}",
        "14-1": "数量合计", "14-2": "{{ 数量合计 }}", "14-4": "金额合计", "14-5": "{{ 金额合计 }}", "14-7": "大写金额", "14-8": "{{ 大写金额 }}",
        "17-1": "制单人", "17-2": "{{ 制单人 }}", "17-4": "审核人", "17-5": "{{ 审核人 }}", "17-7": "主管签字", "17-8": "{{ 主管签字 }}",
    }
    cell_styles = {"1-1": {"fontWeight": "700", "textAlign": "center", "fontSize": "18", "merged": True, "colSpan": 8}}
    for col in range(2, 9):
        cell_styles[f"1-{col}"] = {"covered": True, "mergeAnchor": "1-1"}
    for col in range(1, 9):
        cell_styles[f"6-{col}"] = {"fontWeight": "700", "textAlign": "center", "border": True}
    for row in range(7, 13):
        for col in range(1, 9):
            cell_styles[f"{row}-{col}"] = {"border": True}
    cell_styles["14-5"] = {"merged": True, "colSpan": 2}
    cell_styles["14-6"] = {"covered": True, "mergeAnchor": "14-5"}
    return {
        **DEFAULT_LAYOUT,
        "grid_cols": 8,
        "cells": cells,
        "cell_styles": cell_styles,
        "col_widths": {"1": 85, "2": 120, "3": 90, "4": 60, "5": 65, "6": 85, "7": 120, "8": 90},
        "version": 7,
    }


def _initial_html(document_label: str) -> str:
    return f'<div class="print-sheet-title">{document_label}</div>'


DOCUMENT_TYPES = [
    ("quotation", "报价单", "销售"),
    ("sales_order", "销售订单", "销售"),
    ("shipment", "销售发货单", "销售"),
    ("sales_return", "销售退货单", "销售"),
    ("sales_invoice", "销售发票登记", "财务"),
    ("purchase_order", "采购订单", "采购"),
    ("purchase_receipt", "采购入库单", "采购"),
    ("purchase_return", "采购退货单", "采购"),
    ("purchase_invoice", "采购发票登记", "财务"),
    ("supplier_quote", "供应商报价单", "采购"),
    ("subcontract_order", "委外加工单", "委外"),
    ("subcontract_issue", "委外发料单", "委外"),
    ("subcontract_receive", "委外收货单", "委外"),
    ("inventory_adjustment", "库存调整单", "库存"),
    ("inventory_transfer", "库存调拨单", "库存"),
    ("inventory_check", "库存盘点单", "库存"),
    ("inventory_assembly", "组装单", "库存"),
    ("inventory_disassembly", "拆卸单", "库存"),
    ("work_order", "生产工单", "生产"),
    ("work_order_issue", "工单领料单", "生产"),
    ("work_order_completion", "工单完工入库单", "生产"),
    ("work_order_requisition", "生产领料申请单", "生产"),
    ("quality_inspection", "质量检验单", "生产"),
    ("service_card", "设备服务档案", "售后"),
    ("service_order", "服务单", "售后"),
    ("service_rma", "RMA单", "售后"),
    ("voucher", "会计凭证", "财务"),
]


def ensure_print_template_table(execute_db):
    # DDL 已迁移至 services/schema_migrations.py（20260619_004_print_templates_schema）
    # 请求期不再执行 CREATE TABLE / ALTER TABLE / CREATE INDEX
    # 以下仅保留种子数据初始化逻辑
    execute_db("DELETE FROM print_templates WHERE template_code LIKE %s", ("PT-AUDIT-%",))
    for document_type, document_label, category in DOCUMENT_TYPES:
        template_code = f"PT-{document_type.upper().replace('_', '-')}-STD"
        execute_db(
            """
            INSERT INTO print_templates
                (template_code, template_name, document_type, category, print_type, status,
                 is_default, layout_json, content_html, remark, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,'enabled',TRUE,%s::jsonb,%s,%s,NOW(),NOW())
            ON CONFLICT (template_code) DO NOTHING
            """,
            (
                template_code,
                f"{document_label}标准模板",
                document_type,
                category,
                "单据打印",
                json.dumps(_default_grid_layout(document_label), ensure_ascii=False),
                _initial_html(document_label),
                "系统预置模板，可复制或编辑后用于套打。",
            ),
        )
        execute_db(
            """
            UPDATE print_templates
            SET layout_json=%s::jsonb, updated_at=NOW()
            WHERE document_type=%s
              AND (
                  layout_json IS NULL
                  OR NOT (layout_json ? 'cells')
                  OR layout_json->'cells' = '{}'::jsonb
              )
            """,
            (
                json.dumps(_default_grid_layout(document_label), ensure_ascii=False),
                document_type,
            ),
        )
        execute_db(
            """
            UPDATE print_templates
            SET layout_json=%s::jsonb, updated_at=NOW()
            WHERE template_code=%s
              AND COALESCE((layout_json->>'version')::int, 1) < 6
            """,
            (
                json.dumps(_default_grid_layout(document_label), ensure_ascii=False),
                template_code,
            ),
        )


def _document_label(document_type: str) -> str:
    for value, label, _category in DOCUMENT_TYPES:
        if value == document_type:
            return label
    return document_type or "-"


def _layout_from_form():
    rows = request.form.get("grid_rows") or DEFAULT_LAYOUT["grid_rows"]
    cols = request.form.get("grid_cols") or DEFAULT_LAYOUT["grid_cols"]
    try:
        rows = max(8, min(60, int(rows)))
    except ValueError:
        rows = DEFAULT_LAYOUT["grid_rows"]
    try:
        cols = max(6, min(24, int(cols)))
    except ValueError:
        cols = DEFAULT_LAYOUT["grid_cols"]
    cells = {}
    cell_styles = {}
    raw_cells = (request.form.get("grid_cells_json") or "").strip()
    if raw_cells:
        try:
            parsed = json.loads(raw_cells)
            if isinstance(parsed, dict):
                cells = {
                    str(key): sanitize_template_html(str(value).strip())
                    for key, value in parsed.items()
                    if str(value).strip()
                }
        except ValueError:
            cells = {}
    raw_styles = (request.form.get("grid_styles_json") or "").strip()
    if raw_styles:
        try:
            parsed_styles = json.loads(raw_styles)
            if isinstance(parsed_styles, dict):
                cell_styles = {
                    str(key): value
                    for key, value in parsed_styles.items()
                    if isinstance(value, dict) and value
                }
        except ValueError:
            cell_styles = {}
    col_widths = {}
    raw_col_widths = (request.form.get("grid_col_widths_json") or "").strip()
    if raw_col_widths:
        try:
            parsed_widths = json.loads(raw_col_widths)
            if isinstance(parsed_widths, dict):
                col_widths = {
                    str(key): max(48, min(260, int(value)))
                    for key, value in parsed_widths.items()
                    if str(key).isdigit()
                }
        except (TypeError, ValueError):
            col_widths = {}
    return {
        "paper": (request.form.get("paper") or "A4").strip(),
        "orientation": (request.form.get("orientation") or "portrait").strip(),
        "grid_rows": rows,
        "grid_cols": cols,
        "cells": cells,
        "cell_styles": cell_styles,
        "col_widths": col_widths,
        "version": 1,
    }


def _template_form_data(template=None):
    template = template or {}
    document_type = (request.form.get("document_type") or template.get("document_type") or DOCUMENT_TYPES[0][0]).strip()
    document_label = _document_label(document_type)
    return {
        "template_code": (request.form.get("template_code") or template.get("template_code") or "").strip(),
        "template_name": (request.form.get("template_name") or template.get("template_name") or f"{document_label}模板").strip(),
        "document_type": document_type,
        "category": (request.form.get("category") or template.get("category") or "").strip(),
        "print_type": (request.form.get("print_type") or template.get("print_type") or "单据打印").strip(),
        "status": (request.form.get("status") or template.get("status") or "enabled").strip(),
        "is_default": bool(request.form.get("is_default")),
        "layout_json": _layout_from_form(),
        "content_html": sanitize_template_html(request.form.get("content_html") or template.get("content_html") or _initial_html(document_label)),
        "remark": (request.form.get("remark") or template.get("remark") or "").strip(),
    }


def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]
    login_required = deps["login_required"]
    role_required = deps.get("role_required")
    log_action = deps.get("log_action") or (lambda *args, **kwargs: None)
    admin_required = role_required("admin", "manager") if role_required else (lambda func: func)

    def query_one(sql, params=None):
        return query_db(sql, params or (), one=True)

    @app.get("/system/print-templates", endpoint="print_template_list")
    @login_required
    @admin_required
    def print_template_list():
        ensure_print_template_table(execute_db)
        keyword = (request.args.get("keyword") or "").strip()
        category = (request.args.get("category") or "").strip()
        status = (request.args.get("status") or "").strip()
        where = []
        params = []
        if keyword:
            where.append("(template_code ILIKE %s OR template_name ILIKE %s OR document_type ILIKE %s OR remark ILIKE %s)")
            params.extend([f"%{keyword}%"] * 4)
        if category:
            where.append("category=%s")
            params.append(category)
        if status:
            where.append("status=%s")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = query_db(
            f"""
            SELECT id, template_code, template_name, document_type, category, print_type,
                   status, is_default, created_at, updated_at, remark
            FROM print_templates
            {where_sql}
            ORDER BY category, document_type, is_default DESC, template_code
            LIMIT 300
            """,
            tuple(params),
        )
        categories = query_db(
            """
            SELECT COALESCE(NULLIF(category,''),'未分类') AS category, COUNT(*) AS count
            FROM print_templates
            GROUP BY COALESCE(NULLIF(category,''),'未分类')
            ORDER BY category
            """
        )
        for row in rows:
            row["document_label"] = _document_label(row.get("document_type"))
        return render_template(
            "print_template_list.html",
            rows=rows,
            categories=categories,
            filters={"keyword": keyword, "category": category, "status": status},
            document_types=DOCUMENT_TYPES,
        )

    @app.route("/system/print-templates/new", methods=["GET", "POST"], endpoint="print_template_new")
    @login_required
    @admin_required
    def print_template_new():
        ensure_print_template_table(execute_db)
        template = _template_form_data()
        if request.method == "POST":
            if not template["template_code"] or not template["template_name"]:
                flash("模板编码和模板名称必须填写。", "warning")
            else:
                if template["is_default"]:
                    execute_db(
                        "UPDATE print_templates SET is_default=FALSE, updated_at=NOW() WHERE document_type=%s",
                        (template["document_type"],),
                    )
                row = execute_and_return(
                    """
                    INSERT INTO print_templates
                        (template_code, template_name, document_type, category, print_type, status,
                         is_default, layout_json, content_html, remark, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,NOW(),NOW())
                    RETURNING id
                    """,
                    (
                        template["template_code"],
                        template["template_name"],
                        template["document_type"],
                        template["category"],
                        template["print_type"],
                        template["status"],
                        template["is_default"],
                        json.dumps(template["layout_json"], ensure_ascii=False),
                        template["content_html"],
                        template["remark"],
                    ),
                )
                log_action("打印模板", "新增", template["template_code"])
                return redirect(url_for("print_template_edit", template_id=row["id"]))
        if request.method == "GET":
            template["layout_json"] = _normalize_layout(template.get("layout_json"), template.get("document_type"))
        return render_template(
            "print_template_editor.html",
            template=template,
            document_types=DOCUMENT_TYPES,
            field_groups=FIELD_GROUPS,
            mode="new",
        )

    @app.route("/system/print-templates/<int:template_id>/edit", methods=["GET", "POST"], endpoint="print_template_edit")
    @login_required
    @admin_required
    def print_template_edit(template_id):
        ensure_print_template_table(execute_db)
        existing = query_one("SELECT * FROM print_templates WHERE id=%s", (template_id,))
        if not existing:
            flash("打印模板不存在。", "warning")
            return redirect(url_for("print_template_list"))
        template = _template_form_data(existing)
        if request.method == "POST":
            if not template["template_code"] or not template["template_name"]:
                flash("模板编码和模板名称必须填写。", "warning")
            else:
                if template["is_default"]:
                    execute_db(
                        "UPDATE print_templates SET is_default=FALSE, updated_at=NOW() WHERE document_type=%s AND id<>%s",
                        (template["document_type"], template_id),
                    )
                execute_db(
                    """
                    UPDATE print_templates
                    SET template_code=%s, template_name=%s, document_type=%s, category=%s,
                        print_type=%s, status=%s, is_default=%s, layout_json=%s::jsonb,
                        content_html=%s, remark=%s, updated_at=NOW()
                    WHERE id=%s
                    """,
                    (
                        template["template_code"],
                        template["template_name"],
                        template["document_type"],
                        template["category"],
                        template["print_type"],
                        template["status"],
                        template["is_default"],
                        json.dumps(template["layout_json"], ensure_ascii=False),
                        template["content_html"],
                        template["remark"],
                        template_id,
                    ),
                )
                log_action("打印模板", "保存", template["template_code"])
                flash("打印模板已保存。", "success")
                return redirect(url_for("print_template_edit", template_id=template_id))
        if request.method == "GET":
            template.update(existing)
            template["layout_json"] = _normalize_layout(existing.get("layout_json"), existing.get("document_type"))
        return render_template(
            "print_template_editor.html",
            template=template,
            document_types=DOCUMENT_TYPES,
            field_groups=FIELD_GROUPS,
            mode="edit",
        )

    @app.get("/system/print-templates/<int:template_id>/preview", endpoint="print_template_preview")
    @login_required
    @admin_required
    def print_template_preview(template_id):
        ensure_print_template_table(execute_db)
        template = query_one("SELECT * FROM print_templates WHERE id=%s", (template_id,))
        if not template:
            flash("打印模板不存在。", "warning")
            return redirect(url_for("print_template_list"))
        template["layout_json"] = _normalize_layout(template.get("layout_json"), template.get("document_type"))
        template["content_html"] = sanitize_template_html(template.get("content_html") or "")
        return render_template(
            "print_template_preview.html",
            template=template,
            preview_time=datetime.now(),
        )

    @app.post("/system/print-templates/<int:template_id>/set-default", endpoint="print_template_set_default")
    @login_required
    @admin_required
    def print_template_set_default(template_id):
        ensure_print_template_table(execute_db)
        template = query_one("SELECT id, document_type, template_code FROM print_templates WHERE id=%s", (template_id,))
        if template:
            execute_db("UPDATE print_templates SET is_default=FALSE, updated_at=NOW() WHERE document_type=%s", (template["document_type"],))
            execute_db("UPDATE print_templates SET is_default=TRUE, status='enabled', updated_at=NOW() WHERE id=%s", (template_id,))
            log_action("打印模板", "设为默认", template["template_code"])
        return redirect(url_for("print_template_list"))

    @app.post("/system/print-templates/<int:template_id>/copy", endpoint="print_template_copy")
    @login_required
    @admin_required
    def print_template_copy(template_id):
        ensure_print_template_table(execute_db)
        template = query_one("SELECT * FROM print_templates WHERE id=%s", (template_id,))
        if not template:
            flash("打印模板不存在。", "warning")
            return redirect(url_for("print_template_list"))
        base_code = f"{template['template_code']}-COPY"
        next_code = base_code
        index = 1
        while query_one("SELECT id FROM print_templates WHERE template_code=%s", (next_code,)):
            index += 1
            next_code = f"{base_code}-{index}"
        row = execute_and_return(
            """
            INSERT INTO print_templates
                (template_code, template_name, document_type, category, print_type, status,
                 is_default, layout_json, content_html, remark, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,'enabled',FALSE,%s::jsonb,%s,%s,NOW(),NOW())
            RETURNING id
            """,
            (
                next_code,
                f"{template['template_name']}副本",
                template["document_type"],
                template["category"],
                template["print_type"],
                json.dumps(_normalize_layout(template.get("layout_json"), template.get("document_type")), ensure_ascii=False),
                template.get("content_html") or "",
                template.get("remark") or "",
            ),
        )
        log_action("打印模板", "复制", f"{template['template_code']} -> {next_code}")
        return redirect(url_for("print_template_edit", template_id=row["id"]))

    @app.post("/system/print-templates/<int:template_id>/delete", endpoint="print_template_delete")
    @login_required
    @admin_required
    def print_template_delete(template_id):
        ensure_print_template_table(execute_db)
        template = query_one("SELECT id, template_code, template_name, is_default FROM print_templates WHERE id=%s", (template_id,))
        if not template:
            flash("打印模板不存在。", "warning")
            return redirect(url_for("print_template_list"))
        if template.get("is_default") or str(template.get("template_code") or "").endswith("-STD"):
            flash("内置模板和默认模板不能删除，请先复制后编辑副本。", "warning")
            return redirect(url_for("print_template_list"))
        execute_db("DELETE FROM print_templates WHERE id=%s", (template_id,))
        log_action("打印模板", "删除", f"{template['template_code']} {template['template_name']}")
        flash("打印模板已删除。", "success")
        return redirect(url_for("print_template_list"))

    @app.post("/system/print-templates/<int:template_id>/toggle", endpoint="print_template_toggle")
    @login_required
    @admin_required
    def print_template_toggle(template_id):
        ensure_print_template_table(execute_db)
        template = query_one("SELECT id, template_code, status, is_default FROM print_templates WHERE id=%s", (template_id,))
        if template:
            next_status = "disabled" if template.get("status") == "enabled" else "enabled"
            is_default = False if next_status == "disabled" else template.get("is_default")
            execute_db(
                "UPDATE print_templates SET status=%s, is_default=%s, updated_at=NOW() WHERE id=%s",
                (next_status, is_default, template_id),
            )
            log_action("打印模板", "启用禁用", f"{template['template_code']} -> {next_status}")
        return redirect(url_for("print_template_list"))
