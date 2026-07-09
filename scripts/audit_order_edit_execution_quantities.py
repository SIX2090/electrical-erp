from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def section_between(text: str, start: str, end: str) -> str:
    if start not in text:
        return ""
    chunk = text.split(start, 1)[1]
    return chunk.split(end, 1)[0] if end in chunk else chunk


def main() -> int:
    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    helper = section_between(registry, "def _prepare_order_edit_lines", "def _ensure_document_custom_field_table")
    sales_edit = section_between(registry, "def _save_sales_order", "order_no = _next_doc_no(\"SO\"")
    purchase_edit = section_between(registry, "def _save_purchase_order", "order_no = _next_doc_no(\"PO\"")

    checks = [
        ("shared_edit_guard_exists", "def _prepare_order_edit_lines" in registry),
        ("non_editable_status_guard", "ORDER_NON_EDITABLE_STATUS_KEYWORDS" in registry and "不能普通编辑保存" in helper),
        ("executed_deleted_guard", "deleted_executed" in helper and "已执行明细不能删除" in helper),
        ("executed_quantity_floor_guard", "executed > item[\"quantity\"]" in helper and "不能低于" in helper),
        ("sales_edit_uses_guard", "_prepare_order_edit_lines(kind=\"sales\"" in sales_edit),
        ("purchase_edit_uses_guard", "_prepare_order_edit_lines(kind=\"purchase\"" in purchase_edit),
        ("sales_insert_preserves_shipped_qty", "item[\"shipped_qty\"]" in sales_edit and "VALUES (%s,%s,%s,%s" in sales_edit),
        ("purchase_insert_preserves_received_qty", "item[\"received_qty\"]" in purchase_edit and "VALUES (%s,%s,%s,%s" in purchase_edit),
        ("sales_insert_keeps_source_line", "source_line_no" in sales_edit and "item.get(\"source_line_no\")" in sales_edit),
        ("purchase_insert_keeps_source_line", "source_line_no" in purchase_edit and "item.get(\"source_line_no\")" in purchase_edit),
        ("no_sales_edit_hardcoded_zero", "VALUES (%s,%s,%s,0,%s" not in sales_edit),
        ("no_purchase_edit_hardcoded_zero", "VALUES (%s,%s,%s,0,%s" not in purchase_edit),
    ]

    failed = []
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
        if not ok:
            failed.append(name)
    print(f"checked={len(checks)} failed={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
