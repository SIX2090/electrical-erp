from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List

from services.mrp_engine import (
    _as_decimal,
    _inventory_quantities,
    _purchase_on_order_qty,
    _purchase_requisition_qty,
)
from services.work_order_material_service import as_decimal
from services.work_order_snapshot_service import (
    bom_requirement_rows_from_snapshot,
    latest_work_order_execution_snapshot,
)


def _positive(value):
    qty = as_decimal(value)
    return qty if qty > 0 else Decimal("0")


def _sum_quantity(query_one, sql, params):
    row = query_one(sql, params) or {}
    return as_decimal(row.get("qty"))


def _issued_returned_quantities(query_one, work_order_id, source_line_no):
    row = query_one(
        """
        SELECT COALESCE(SUM(issued_qty), 0) AS issued_qty,
               COALESCE(SUM(returned_qty), 0) AS returned_qty
        FROM wo_material_items
        WHERE wo_id=%s
          AND source_line_no=%s
        """,
        (work_order_id, source_line_no),
    ) or {}
    return as_decimal(row.get("issued_qty")), as_decimal(row.get("returned_qty"))


def _product_safety_stock(query_one, product_id) -> Decimal:
    """Fetch safety_stock for a product (0 if missing)."""
    if not product_id:
        return Decimal("0")
    row = query_one(
        "SELECT COALESCE(safety_stock, 0) AS safety_stock FROM products WHERE id=%s",
        (product_id,),
    ) or {}
    return _as_decimal(row.get("safety_stock"))


def build_work_order_mrp_preview(query_one, work_order_id) -> Dict[str, Any]:
    order = query_one("SELECT * FROM work_orders WHERE id=%s", (work_order_id,)) or {}
    if not order:
        return {"rows": [], "summary": {"status": "no_work_order"}}
    snapshot = latest_work_order_execution_snapshot(query_one, work_order_id)
    bom_rows = bom_requirement_rows_from_snapshot(snapshot)
    rows: List[Dict[str, Any]] = []
    totals = defaultdict(Decimal)
    for item in bom_rows:
        product_id = item.get("product_id")
        source_line_no = f"BOM-{item.get('bom_item_id')}"
        gross_qty = as_decimal(item.get("base_qty")) * as_decimal(order.get("quantity"), "1")
        gross_qty = gross_qty * (Decimal("1") + (as_decimal(item.get("loss_rate")) / Decimal("100")))
        if not product_id or gross_qty <= 0:
            continue
        # Reuse mrp_engine helpers so net-requirement logic stays in one place.
        inventory = _inventory_quantities(query_one, product_id, order.get("project_code"), order.get("serial_no"))
        requisition_qty = _purchase_requisition_qty(query_one, product_id, order.get("project_code"), order.get("serial_no"))
        purchase_on_order_qty = _purchase_on_order_qty(query_one, product_id, order.get("project_code"), order.get("serial_no"))
        issued_qty, returned_qty = _issued_returned_quantities(query_one, work_order_id, source_line_no)
        # Safety stock: subtract from available inventory (B-1 enhancement).
        safety_stock = _product_safety_stock(query_one, product_id)
        effective_available = inventory["available_qty"] - safety_stock
        effective_available = effective_available if effective_available > 0 else Decimal("0")
        deducted_qty = effective_available + requisition_qty + purchase_on_order_qty + issued_qty - returned_qty
        net_shortage_qty = gross_qty - deducted_qty
        net_shortage_qty = net_shortage_qty if net_shortage_qty > 0 else Decimal("0")
        if net_shortage_qty <= 0:
            suggestion_type = "covered"
            suggestion_label = "已覆盖"
        elif purchase_on_order_qty > 0 or requisition_qty > 0:
            suggestion_type = "follow_purchase"
            suggestion_label = "跟进采购"
        else:
            suggestion_type = "purchase"
            suggestion_label = "建议采购"
        row = {
            "source_line_no": source_line_no,
            "material_code": item.get("material_code") or "",
            "material_name": item.get("material_name") or "",
            "material_spec": item.get("material_spec") or "",
            "material_unit": item.get("material_unit") or "",
            "gross_qty": gross_qty,
            "available_qty": inventory["available_qty"],
            "safety_stock": safety_stock,
            "effective_available_qty": effective_available,
            "locked_qty": inventory["locked_qty"],
            "requisition_qty": requisition_qty,
            "purchase_on_order_qty": purchase_on_order_qty,
            "issued_qty": issued_qty,
            "returned_qty": returned_qty,
            "net_shortage_qty": net_shortage_qty,
            "suggestion_type": suggestion_type,
            "suggestion_label": suggestion_label,
        }
        rows.append(row)
        for key in (
            "gross_qty",
            "available_qty",
            "effective_available_qty",
            "locked_qty",
            "requisition_qty",
            "purchase_on_order_qty",
            "issued_qty",
            "returned_qty",
            "net_shortage_qty",
        ):
            totals[key] += as_decimal(row.get(key))
    shortage_lines = [row for row in rows if as_decimal(row.get("net_shortage_qty")) > 0]
    return {
        "rows": rows,
        "summary": {
            "status": "ok" if rows else "empty",
            "source": "work_order_execution_snapshot" if snapshot else "none",
            "line_count": len(rows),
            "shortage_line_count": len(shortage_lines),
            "gross_qty": totals["gross_qty"],
            "available_qty": totals["available_qty"],
            "effective_available_qty": totals["effective_available_qty"],
            "purchase_cover_qty": totals["requisition_qty"] + totals["purchase_on_order_qty"],
            "net_shortage_qty": totals["net_shortage_qty"],
        },
    }

