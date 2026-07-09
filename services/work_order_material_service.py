from decimal import Decimal


def as_decimal(value, default="0"):
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def pending_material_quantity(row):
    return as_decimal(row.get("required_qty")) - as_decimal(row.get("issued_qty")) + as_decimal(row.get("returned_qty"))


def issue_quantity_for_row(row, requested_item_id=None, requested_qty=None):
    row_id = int(row.get("id") or 0)
    if requested_item_id and row_id != int(requested_item_id):
        return None, None
    pending_qty = pending_material_quantity(row)
    if pending_qty <= 0:
        return None, None
    if requested_item_id:
        qty = as_decimal(requested_qty)
        if qty <= 0:
            return None, "quantity_required"
        if qty > pending_qty:
            return None, "quantity_over_pending"
        return qty, None
    return pending_qty, None


def returnable_material_quantity(row):
    return as_decimal(row.get("issued_qty")) - as_decimal(row.get("returned_qty"))


def validate_return_quantity(row, requested_qty):
    qty = as_decimal(requested_qty)
    if qty <= 0:
        return None, "quantity_required"
    if qty > returnable_material_quantity(row):
        return None, "quantity_over_returnable"
    return qty, None


def summarize_material_rows(rows):
    required_qty = Decimal("0")
    issued_qty = Decimal("0")
    returned_qty = Decimal("0")
    pending_qty = Decimal("0")
    returnable_qty = Decimal("0")
    for row in rows:
        required_qty += as_decimal(row.get("required_qty"))
        issued_qty += as_decimal(row.get("issued_qty"))
        returned_qty += as_decimal(row.get("returned_qty"))
        pending = pending_material_quantity(row)
        if pending > 0:
            pending_qty += pending
        returnable = returnable_material_quantity(row)
        if returnable > 0:
            returnable_qty += returnable
    return {
        "required_qty": required_qty,
        "issued_qty": issued_qty,
        "returned_qty": returned_qty,
        "pending_qty": pending_qty,
        "returnable_qty": returnable_qty,
    }


def available_inventory_quantity(product_id, warehouse_id, query_one):
    balance = query_one(
        """
        SELECT COALESCE(SUM(quantity),0) AS stock_qty,
               COALESCE(SUM(locked_qty),0) AS locked_qty
        FROM inventory_balances
        WHERE product_id=%s AND COALESCE(warehouse_id,0)=COALESCE(%s,0)
        """,
        (product_id, warehouse_id),
    ) or {}
    available_qty = as_decimal(balance.get("stock_qty")) - as_decimal(balance.get("locked_qty"))
    return available_qty if available_qty > 0 else Decimal("0")


def validate_issue_stock(row, issue_qty, warehouse_id, query_one):
    qty = as_decimal(issue_qty)
    available_qty = available_inventory_quantity(row.get("product_id"), warehouse_id, query_one)
    if qty > available_qty:
        return "stock_shortage", available_qty
    return None, available_qty


def resolve_unit_cost(row_unit_cost, product_id, warehouse_id, query_one):
    unit_cost = as_decimal(row_unit_cost)
    if unit_cost != 0:
        return unit_cost
    balance = query_one(
        "SELECT COALESCE(MAX(unit_cost),0) AS unit_cost FROM inventory_balances WHERE product_id=%s AND COALESCE(warehouse_id,0)=COALESCE(%s,0)",
        (product_id, warehouse_id),
    ) or {}
    return as_decimal(balance.get("unit_cost"))


def _list_value(values, idx, default=""):
    return values[idx] if idx < len(values) else default


def build_requirement_lines(product_ids, quantities, unit_costs, remarks, order, query_one, extra_fields=None):
    lines = []
    warehouse_id = order.get("warehouse_id")
    extra_fields = extra_fields or {}
    for idx, product_id_value in enumerate(product_ids):
        product_id = _as_int(product_id_value)
        qty = as_decimal(quantities[idx] if idx < len(quantities) else "0")
        if not product_id or qty <= 0:
            continue
        unit_cost = resolve_unit_cost(
            unit_costs[idx] if idx < len(unit_costs) else "0",
            product_id,
            warehouse_id,
            query_one,
        )
        remark = (remarks[idx] if idx < len(remarks) else "") or f"手工新增领料需求 {order.get('wo_no')}"
        lines.append({
            "product_id": product_id,
            "qty": qty,
            "unit_cost": unit_cost,
            "remark": remark,
            "source_line_no": _list_value(extra_fields.get("source_line_no", []), idx),
            "warehouse_id": _as_int(_list_value(extra_fields.get("warehouse_id", []), idx, warehouse_id)),
            "location_id": _as_int(_list_value(extra_fields.get("location_id", []), idx)),
            "lot_no": _list_value(extra_fields.get("lot_no", []), idx),
            "line_project_code": _list_value(extra_fields.get("line_project_code", []), idx, order.get("project_code") or ""),
            "line_serial_no": _list_value(extra_fields.get("line_serial_no", []), idx, order.get("serial_no") or ""),
        })
    return lines


def build_extra_material_lines(product_ids, quantities, unit_costs, lot_nos, remarks, warehouse_id, default_remark, query_one, extra_fields=None):
    lines = []
    extra_fields = extra_fields or {}
    for idx, product_id_value in enumerate(product_ids):
        product_id = _as_int(product_id_value)
        qty = as_decimal(quantities[idx] if idx < len(quantities) else "0")
        if not product_id or qty <= 0:
            continue
        unit_cost = resolve_unit_cost(
            unit_costs[idx] if idx < len(unit_costs) else "0",
            product_id,
            warehouse_id,
            query_one,
        )
        lines.append(
            {
                "product_id": product_id,
                "qty": qty,
                "unit_cost": unit_cost,
                "lot_no": lot_nos[idx] if idx < len(lot_nos) else "",
                "remark": remarks[idx] if idx < len(remarks) else default_remark,
                "source_line_no": _list_value(extra_fields.get("source_line_no", []), idx),
                "location_id": _as_int(_list_value(extra_fields.get("location_id", []), idx)),
                "line_project_code": _list_value(extra_fields.get("line_project_code", []), idx),
                "line_serial_no": _list_value(extra_fields.get("line_serial_no", []), idx),
            }
        )
    return lines


def bom_requirement_source_line(row):
    return f"BOM-{row.get('bom_item_id')}"


def build_bom_requirement_line(row, order, query_one):
    base_qty = as_decimal(row.get("base_qty"))
    loss_rate = as_decimal(row.get("loss_rate"))
    work_order_qty = as_decimal(order.get("quantity"), "1")
    if work_order_qty <= 0:
        work_order_qty = Decimal("1")
    required_qty = base_qty * work_order_qty * (Decimal("1") + (loss_rate / Decimal("100")))
    if not row.get("product_id") or required_qty <= 0:
        return None
    unit_cost = resolve_unit_cost(row.get("standard_price"), row.get("product_id"), order.get("warehouse_id"), query_one)
    return {
        "product_id": row.get("product_id"),
        "required_qty": required_qty,
        "unit_cost": unit_cost,
        "amount": required_qty * unit_cost,
        "remark": row.get("remark") or f"BOM生成领料需求 {order.get('wo_no')}",
        "warehouse_id": order.get("warehouse_id"),
        "location_id": order.get("location_id"),
        "source_line_no": bom_requirement_source_line(row),
        "line_project_code": order.get("project_code"),
        "line_serial_no": order.get("serial_no"),
        "material_code": row.get("material_code") or "",
        "material_name": row.get("material_name") or "",
        "material_spec": row.get("material_spec") or "",
        "material_unit": row.get("material_unit") or "",
    }


def summarize_bom_requirement_generation(order, bom_rows, existing_source_lines):
    if not order.get("bom_id"):
        return {
            "can_generate": False,
            "reason_code": "no_bom",
            "reason": "工单未选择BOM，无法按BOM生成领料需求。",
            "available_count": 0,
            "skipped_count": 0,
            "invalid_count": 0,
            "total_bom_count": 0,
        }
    existing_source_lines = set(existing_source_lines or [])
    available_count = 0
    skipped_count = 0
    invalid_count = 0
    for row in bom_rows or []:
        if bom_requirement_source_line(row) in existing_source_lines:
            skipped_count += 1
            continue
        if not row.get("product_id") or as_decimal(row.get("base_qty")) <= 0:
            invalid_count += 1
            continue
        available_count += 1
    if available_count:
        reason_code = "ready"
        reason = f"有 {available_count} 行BOM可生成领料需求。"
    elif skipped_count:
        reason_code = "all_existing"
        reason = "可生成的BOM来源行均已存在领料需求，重复生成会跳过。"
    elif invalid_count:
        reason_code = "no_valid_lines"
        reason = "BOM没有物料和用量均有效的明细行，无法生成领料需求。"
    else:
        reason_code = "empty_bom"
        reason = "当前BOM没有明细行，无法生成领料需求。"
    return {
        "can_generate": available_count > 0,
        "reason_code": reason_code,
        "reason": reason,
        "available_count": available_count,
        "skipped_count": skipped_count,
        "invalid_count": invalid_count,
        "total_bom_count": len(bom_rows or []),
    }


def _as_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
