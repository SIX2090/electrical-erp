from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRTY_CODEPOINTS = {0xFFFD, 0x93C2, 0x6434, 0x9417, 0x95BF, 0x95B2, 0x7487}


@dataclass(frozen=True)
class DocumentSpec:
    module: str
    document: str
    entry_path: str | None
    list_path: str | None
    detail_path: str | None
    save_function: str | None
    required_line_fields: tuple[str, ...]
    required_header_fields: tuple[str, ...]
    required_status_ops: tuple[str, ...]


LINE_FIELDS = {
    "material_code": ("data-column-key=\"product_code\"", "物料编码", "product_code", "material_code"),
    "material_name": ("data-column-key=\"product_name\"", "物料名称", "product_name", "material_name", "data-column-key=\"product\""),
    "specification": ("data-column-key=\"specification\"", "data-column-key=\"spec\"", "规格", "规格型号", "specification", "spec"),
    "unit": ("data-column-key=\"unit\"", "单位", "unit_name", "material_unit", "name=\"unit[]\"", "data-unit="),
    "quantity": ("data-column-key=\"quantity\"", "data-column-key=\"diff_quantity\"", "data-column-key=\"actual_qty\"", "data-column-key=\"line_quantity\"", "name=\"quantity[]\"", "name=\"diff_quantity[]\"", "name=\"actual_qty[]\"", "name=\"line_quantity[]\"", "\"quantity\""),
    "price_or_cost": ("data-column-key=\"unit_price\"", "data-column-key=\"unit_cost\"", "data-column-key=\"estimated_price\"", "未税单价", "库存成本单价", "成本", "unit_price", "unit_cost"),
    "amount": ("data-column-key=\"amount\"", "data-column-key=\"cost_amount\"", "data-column-key=\"tax_amount\"", "data-column-key=\"amount_with_tax\"", "金额", "未税金额", "含税金额", "estimated-amount", "amount", "cost_amount"),
    "warehouse": ("data-column-key=\"warehouse\"", "data-column-key=\"line_warehouse\"", "name=\"warehouse_id[]\"", "name=\"line_warehouse_id[]\"", "仓库", "warehouse", "from_warehouse_id", "to_warehouse_id", "warehouse_id", "line_warehouse_id"),
    "location": ("data-column-key=\"location\"", "data-column-key=\"line_location\"", "name=\"location_id[]\"", "name=\"line_location_id[]\"", "库位", "location", "from_location_id", "to_location_id", "location_id", "line_location_id"),
    "lot_no": ("data-column-key=\"lot_no\"", "批号", "lot_no"),
    "serial_no": ("data-column-key=\"serial_no\"", "机号", "serial_no"),
    "project_code": ("data-column-key=\"project_code\"", "项目号", "project_code"),
    "source_line": ("source_line", "source_line_no", "source_item", "source_row", "source_detail", "来源行", "源单行"),
}

HEADER_FIELDS = {
    "partner": ("customer_id", "supplier_id", "客户", "供应商", "委外商"),
    "document_no": ("order_no", "request_no", "doc_no", "reference_no", "本单号", "单据编号"),
    "date": ("order_date", "request_date", "doc_date", "tx_date", "wo_date", "日期"),
    "project_code": ("project_code", "项目号"),
    "serial_no": ("serial_no", "机号"),
    "warehouse": ("warehouse_id", "from_warehouse_id", "to_warehouse_id", "仓库"),
    "location": ("location_id", "from_location_id", "to_location_id", "库位"),
    "status": ("status", "状态", "待提交", "已过账", "已关闭"),
    "remark": ("remark", "备注"),
    "source_doc": ("source_no", "reference_no", "source_id", "来源单", "来源"),
}

STATUS_OPS = {
    "submit": ("/submit", "提交", "submit"),
    "approve": ("/approve", "审核", "approve", "确认"),
    "post": ("/post", "过账", "post"),
    "close": ("/close", "关闭", "close"),
    "cancel_or_void": ("/cancel", "/void", "取消", "作废", "void"),
    "print": ("/print", "打印", "print"),
    "attachments": ("attachments", "附件"),
    "notes": ("notes", "操作记录", "备注"),
}

DOCUMENTS = (
    DocumentSpec("Sales", "Sales order / shipment base", "templates/order_form.html", "templates/sales_order_list.html", "templates/document_trace_detail.html", "_save_sales_order", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "lot_no", "serial_no", "project_code", "source_line"), ("partner", "document_no", "date", "project_code", "serial_no", "warehouse", "status", "remark"), ("submit", "approve", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Purchase", "Purchase order", "templates/order_form.html", "templates/purchase_order_list.html", "templates/document_trace_detail.html", "_save_purchase_order", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "lot_no", "serial_no", "project_code", "source_line"), ("partner", "document_no", "date", "project_code", "serial_no", "warehouse", "status", "remark"), ("submit", "approve", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Purchase", "Purchase request", "templates/purchase_request_add.html", "templates/purchase_request.html", "templates/purchase_request_detail.html", None, ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("document_no", "date", "project_code", "serial_no", "status", "remark"), ("submit", "approve", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Inventory", "Other inbound / other outbound", "templates/inventory_movement_form.html", "templates/simple_list.html", "templates/inventory_document_detail.html", "_create_inventory_movement", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("document_no", "date", "project_code", "serial_no", "warehouse", "location", "source_doc", "status", "remark"), ("post", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Inventory", "Inventory adjustment", "templates/inventory_adjustment_form.html", "templates/simple_list.html", "templates/inventory_document_detail.html", "_create_inventory_adjustment", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("document_no", "date", "project_code", "warehouse", "location", "status", "remark"), ("post", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Inventory", "Inventory transfer", "templates/inventory_transfer_form.html", "templates/simple_list.html", "templates/inventory_document_detail.html", "_create_inventory_transfer", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("document_no", "date", "project_code", "warehouse", "location", "status", "remark"), ("post", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Inventory", "Inventory check", "templates/inventory_check_form.html", "templates/simple_list.html", "templates/inventory_document_detail.html", "_create_inventory_check", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("document_no", "date", "project_code", "warehouse", "location", "status", "remark"), ("post", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Inventory", "Assembly / disassembly", "templates/inventory_assembly_form.html", "templates/simple_list.html", "templates/inventory_assembly_detail.html", "_create_inventory_assembly_document", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("document_no", "date", "project_code", "serial_no", "warehouse", "location", "status", "remark"), ("post", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Outsourcing", "Subcontract order", "templates/subcontract_order_form.html", "templates/subcontract.html", "templates/subcontract_detail.html", "_save_subcontract_order", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("partner", "document_no", "date", "project_code", "serial_no", "status", "remark"), ("submit", "approve", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Production", "Work order", "templates/work_order_form.html", "templates/work_order_requisition.html", "templates/work_order_trace_detail.html", "_save_work_order", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("document_no", "date", "project_code", "serial_no", "warehouse", "status", "remark"), ("submit", "approve", "close", "cancel_or_void", "print", "attachments", "notes")),
    DocumentSpec("Service", "Service order part issue", "templates/service_order_trace_detail.html", None, "templates/service_order_trace_detail.html", "_issue_service_order_part", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("partner", "document_no", "date", "project_code", "serial_no", "status", "remark"), ("close", "print", "attachments", "notes")),
    DocumentSpec("Service", "RMA", None, None, "templates/service_rma_trace_detail.html", "_create_rma_from_service_order", ("material_code", "material_name", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "lot_no", "serial_no", "project_code", "source_line"), ("partner", "document_no", "date", "project_code", "serial_no", "status", "remark", "source_doc"), ("close", "attachments", "notes")),
    DocumentSpec("Finance", "Receivable / payable", None, None, "templates/finance_trace_detail.html", None, ("amount", "project_code", "source_line"), ("partner", "document_no", "date", "project_code", "serial_no", "status", "remark", "source_doc"), ("close", "attachments", "notes")),
)


def read_text(path: str | None) -> str:
    if not path:
        return ""
    file_path = ROOT / path
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8", errors="replace")


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def find_missing(text: str, required: tuple[str, ...], catalog: dict[str, tuple[str, ...]]) -> list[str]:
    return [key for key in required if not contains_any(text, catalog[key])]


def dirty_count(text: str) -> int:
    return int("???" in text) + sum(1 for char in text if ord(char) in DIRTY_CODEPOINTS)


def route_context() -> str:
    chunks = []
    for rel in ("routes/registry.py", "routes/data_route_registration.py", "routes/special_list_routes.py", "routes/finance_routes.py", "routes/after_sale_routes.py"):
        chunks.append(read_text(rel))
    return "\n".join(chunks)


def function_body(source: str, function_name: str | None) -> str:
    if not function_name:
        return ""
    pattern = re.compile(rf"^def {re.escape(function_name)}\b.*?(?=^def |\Z)", re.M | re.S)
    matches = list(pattern.finditer(source))
    return matches[-1].group(0) if matches else ""


def audit_documents() -> list[dict[str, object]]:
    routes = route_context()
    results: list[dict[str, object]] = []
    for spec in DOCUMENTS:
        entry = read_text(spec.entry_path)
        detail = read_text(spec.detail_path)
        listing = read_text(spec.list_path)
        combined_ui = "\n".join([entry, detail, listing])
        save_body = function_body(routes, spec.save_function)
        if spec.save_function == "_create_inventory_movement":
            save_body += "\n" + function_body(routes, "_apply_inventory_movement")
            save_body += "\n" + function_body(routes, "_movement_form_lines")
            save_body += "\n" + function_body(routes, "_inventory_product_snapshot")
        if spec.save_function in {"_create_inventory_adjustment", "_create_inventory_transfer", "_create_inventory_check", "_create_inventory_assembly_document"}:
            save_body += "\n" + function_body(routes, "_inventory_form_lines")
            save_body += "\n" + function_body(routes, "_transfer_form_items")
            save_body += "\n" + function_body(routes, "_inventory_check_form_items")
            save_body += "\n" + function_body(routes, "_apply_inventory_movement")
            save_body += "\n" + function_body(routes, "_inventory_product_snapshot")
        if spec.save_function in {"_save_sales_order", "_save_purchase_order"}:
            save_body += "\n" + function_body(routes, "_order_form_items")
            save_body += "\n" + function_body(routes, "_insert_order_line")
            save_body += "\n" + function_body(routes, "_inventory_product_snapshot")
        if spec.save_function == "_save_subcontract_order":
            save_body += "\n" + function_body(routes, "_ensure_subcontract_trace_columns")
            save_body += "\n" + function_body(routes, "_inventory_product_snapshot")
        if spec.save_function == "_save_work_order":
            save_body += "\n" + function_body(routes, "_ensure_work_order_trace_columns")
            save_body += "\n" + function_body(routes, "_inventory_product_snapshot")
        if spec.save_function == "_create_rma_from_service_order":
            save_body += "\n" + function_body(routes, "_rma_line_from_request_or_service")
            save_body += "\n" + function_body(routes, "_inventory_product_snapshot")
        combined_save = save_body or routes

        line_missing_ui = find_missing(combined_ui, spec.required_line_fields, LINE_FIELDS)
        line_missing_save = find_missing(combined_save, spec.required_line_fields, LINE_FIELDS)
        header_missing_ui = find_missing(combined_ui, spec.required_header_fields, HEADER_FIELDS)
        status_missing = find_missing("\n".join([combined_ui, routes]), spec.required_status_ops, STATUS_OPS)
        dirty = dirty_count(combined_ui)
        results.append(
            {
                "module": spec.module,
                "document": spec.document,
                "entry_path": spec.entry_path,
                "list_path": spec.list_path,
                "detail_path": spec.detail_path,
                "save_function": spec.save_function,
                "missing_line_fields_ui": line_missing_ui,
                "missing_line_fields_save": line_missing_save,
                "missing_header_fields_ui": header_missing_ui,
                "missing_status_operations": status_missing,
                "dirty_marker_count": dirty,
                "risk": risk_level(line_missing_ui, line_missing_save, header_missing_ui, status_missing, dirty),
            }
        )
    return results


def risk_level(line_ui: list[str], line_save: list[str], header_ui: list[str], ops: list[str], dirty: int) -> str:
    if not line_ui and not line_save and not header_ui and not ops and not dirty:
        return "ok"
    critical_fields = {"material_code", "specification", "unit", "quantity", "price_or_cost", "amount", "warehouse", "location", "serial_no", "project_code", "source_line"}
    critical_missing = len(critical_fields.intersection(line_ui)) + len(critical_fields.intersection(line_save))
    if dirty or critical_missing >= 6 or len(header_ui) >= 4:
        return "high"
    if critical_missing >= 3 or ops:
        return "medium"
    return "low"


def main() -> int:
    findings = audit_documents()
    output_path = ROOT / "logs" / "system_document_audit_findings.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")

    high = sum(1 for item in findings if item["risk"] == "high")
    medium = sum(1 for item in findings if item["risk"] == "medium")
    low = sum(1 for item in findings if item["risk"] == "low")
    ok = sum(1 for item in findings if item["risk"] == "ok")
    print("system_document_gap_audit=completed")
    print(f"documents_checked={len(findings)}")
    print(f"risk_high={high} risk_medium={medium} risk_low={low} ok={ok}")
    print(f"findings_json={output_path}")
    for item in findings:
        print(
            " | ".join(
                [
                    str(item["risk"]),
                    str(item["module"]),
                    str(item["document"]),
                    f"line_ui_missing={','.join(item['missing_line_fields_ui']) or '-'}",
                    f"line_save_missing={','.join(item['missing_line_fields_save']) or '-'}",
                    f"dirty={item['dirty_marker_count']}",
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
