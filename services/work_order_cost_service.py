from decimal import Decimal


SYSTEM_COST_SOURCE_TYPES = (
    "工单领料",
    "工单退料",
    "委外成本",
    "工序人工",
    "工序设备",
    "完工入库",
)


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _optional_columns(query_rows, table_name):
    rows = query_rows(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,),
    )
    return {row.get("column_name") for row in rows or []}


def ensure_work_order_cost_schema(execute_db):
    # DDL 已迁移至 services/schema_migrations.py（20260619_003_work_order_cost_schema）
    # 请求期不再执行 CREATE TABLE / ALTER TABLE
    pass


def _latest_cost_id(query_one, execute_db, work_order_id, cost_object_id):
    existing = query_one(
        "SELECT id FROM work_order_costs WHERE work_order_id=%s ORDER BY id DESC LIMIT 1",
        (work_order_id,),
    )
    if existing:
        return existing.get("id")
    execute_db(
        """
        INSERT INTO work_order_costs
            (work_order_id, cost_object_id, material_cost, subcontract_cost, labor_cost,
             overhead_cost, total_cost, last_calculated_at)
        VALUES (%s,%s,0,0,0,0,0,NOW())
        """,
        (work_order_id, cost_object_id),
    )
    created = query_one(
        "SELECT id FROM work_order_costs WHERE work_order_id=%s ORDER BY id DESC LIMIT 1",
        (work_order_id,),
    ) or {}
    return created.get("id")


def _material_lines(query_rows, work_order_id, cost_object_id):
    rows = query_rows(
        """
        SELECT mi.id, mi.product_id,
               COALESCE(mi.issued_qty, 0) AS issued_qty,
               COALESCE(mi.returned_qty, 0) AS returned_qty,
               COALESCE(NULLIF(mi.unit_cost, 0), p.standard_price, 0) AS unit_cost,
               COALESCE(mi.material_name, p.name, mi.material_code, p.code) AS material_name
        FROM wo_material_items mi
        LEFT JOIN products p ON p.id=mi.product_id
        WHERE mi.wo_id=%s
        ORDER BY mi.id
        """,
        (work_order_id,),
    )
    lines = []
    material_cost = Decimal("0")
    for row in rows or []:
        issued_qty = _decimal(row.get("issued_qty"))
        returned_qty = _decimal(row.get("returned_qty"))
        unit_cost = _decimal(row.get("unit_cost"))
        if issued_qty > 0:
            amount = issued_qty * unit_cost
            material_cost += amount
            lines.append(
                {
                    "work_order_id": work_order_id,
                    "cost_object_id": cost_object_id,
                    "cost_type": "材料成本",
                    "source_type": "工单领料",
                    "source_id": row.get("id"),
                    "source_no": f"WO-MAT-{row.get('id')}",
                    "product_id": row.get("product_id"),
                    "quantity": issued_qty,
                    "unit_cost": unit_cost,
                    "amount": amount,
                    "remark": row.get("material_name") or "",
                }
            )
        if returned_qty > 0:
            amount = returned_qty * unit_cost * Decimal("-1")
            material_cost += amount
            lines.append(
                {
                    "work_order_id": work_order_id,
                    "cost_object_id": cost_object_id,
                    "cost_type": "材料冲减",
                    "source_type": "工单退料",
                    "source_id": row.get("id"),
                    "source_no": f"WO-MAT-{row.get('id')}",
                    "product_id": row.get("product_id"),
                    "quantity": returned_qty,
                    "unit_cost": unit_cost,
                    "amount": amount,
                    "remark": row.get("material_name") or "",
                }
            )
    return material_cost, lines


def _subcontract_lines(query_rows, order, work_order_id, cost_object_id):
    receive_rows = query_rows(
        """
        SELECT sp.doc_id AS id,
               COALESCE(sp.doc_no, sro.receive_no) AS source_no,
               COALESCE(NULLIF(sp.confirmed_amount, 0), sp.amount, 0) AS amount,
               COALESCE(sro.total_quantity, 0) AS quantity,
               sro.receive_no
        FROM supplier_payables sp
        LEFT JOIN subcontract_receive_orders sro ON sro.id=sp.doc_id
        LEFT JOIN subcontract_orders sc ON sc.id=sro.subcontract_order_id
        WHERE COALESCE(sp.doc_type, sp.source_type, '')='subcontract_receive'
          AND COALESCE(sp.status, '') NOT IN ('void','voided','cancelled','canceled','closed')
          AND (
               sc.parent_work_order_id=%s
               OR (%s IS NOT NULL AND COALESCE(sp.cost_object_id, sc.cost_object_id)=%s)
               OR (%s IS NOT NULL AND COALESCE(sp.project_code, sc.project_code)=%s)
               OR (%s IS NOT NULL AND COALESCE(sp.serial_no, sc.serial_no)=%s)
          )
        ORDER BY sp.id
        """,
        (
            work_order_id,
            cost_object_id,
            cost_object_id,
            order.get("project_code"),
            order.get("project_code"),
            order.get("serial_no"),
            order.get("serial_no"),
        ),
    )
    if receive_rows:
        lines = []
        subcontract_cost = Decimal("0")
        seen = set()
        for row in receive_rows or []:
            if row.get("id") in seen:
                continue
            seen.add(row.get("id"))
            amount = _decimal(row.get("amount"))
            subcontract_cost += amount
            if amount == 0:
                continue
            lines.append(
                {
                    "work_order_id": work_order_id,
                    "cost_object_id": cost_object_id,
                    "cost_type": "subcontract_receive_cost",
                    "source_type": SYSTEM_COST_SOURCE_TYPES[2],
                    "source_id": row.get("id"),
                    "source_no": row.get("source_no"),
                    "product_id": None,
                    "quantity": _decimal(row.get("quantity")),
                    "unit_cost": Decimal("0"),
                    "amount": amount,
                    "remark": "subcontract receive payable cost",
                }
            )
        return subcontract_cost, lines

    rows = query_rows(
        """
        SELECT id, order_no, total_amount, quantity, project_code, serial_no
        FROM subcontract_orders
        WHERE parent_work_order_id=%s
           OR (%s IS NOT NULL AND cost_object_id=%s)
           OR (%s IS NOT NULL AND project_code=%s)
           OR (%s IS NOT NULL AND serial_no=%s)
        ORDER BY id
        """,
        (
            work_order_id,
            cost_object_id,
            cost_object_id,
            order.get("project_code"),
            order.get("project_code"),
            order.get("serial_no"),
            order.get("serial_no"),
        ),
    )
    lines = []
    subcontract_cost = Decimal("0")
    seen = set()
    for row in rows or []:
        if row.get("id") in seen:
            continue
        seen.add(row.get("id"))
        amount = _decimal(row.get("total_amount"))
        subcontract_cost += amount
        if amount == 0:
            continue
        lines.append(
            {
                "work_order_id": work_order_id,
                "cost_object_id": cost_object_id,
                "cost_type": "委外加工费",
                "source_type": "委外成本",
                "source_id": row.get("id"),
                "source_no": row.get("order_no"),
                "product_id": None,
                "quantity": _decimal(row.get("quantity")),
                "unit_cost": Decimal("0"),
                "amount": amount,
                "remark": "委外订单成本归集",
            }
        )
    return subcontract_cost, lines


def _operation_lines(query_rows, order, work_order_id, cost_object_id):
    columns = _optional_columns(query_rows, "operation_reports")
    if "work_order_id" not in columns:
        return Decimal("0"), Decimal("0"), []
    labor_column = "labor_cost" if "labor_cost" in columns else None
    overhead_column = "overhead_cost" if "overhead_cost" in columns else ("equipment_cost" if "equipment_cost" in columns else None)
    if not labor_column and not overhead_column:
        return Decimal("0"), Decimal("0"), []
    sql = f"""
        SELECT id,
               {labor_column if labor_column else '0'} AS labor_cost,
               {overhead_column if overhead_column else '0'} AS overhead_cost,
               {('report_no' if 'report_no' in columns else "'OPR-' || id::text")} AS report_no
        FROM operation_reports
        WHERE work_order_id=%s
        ORDER BY id
    """
    rows = query_rows(sql, (work_order_id,))
    labor_cost = Decimal("0")
    overhead_cost = Decimal("0")
    lines = []
    for row in rows or []:
        labor = _decimal(row.get("labor_cost"))
        overhead = _decimal(row.get("overhead_cost"))
        if labor:
            labor_cost += labor
            lines.append(
                {
                    "work_order_id": work_order_id,
                    "cost_object_id": cost_object_id,
                    "cost_type": "人工成本",
                    "source_type": "工序人工",
                    "source_id": row.get("id"),
                    "source_no": row.get("report_no"),
                    "product_id": order.get("product_id"),
                    "quantity": Decimal("0"),
                    "unit_cost": Decimal("0"),
                    "amount": labor,
                    "remark": "工序报工人工归集",
                }
            )
        if overhead:
            overhead_cost += overhead
            lines.append(
                {
                    "work_order_id": work_order_id,
                    "cost_object_id": cost_object_id,
                    "cost_type": "制造费用",
                    "source_type": "工序设备",
                    "source_id": row.get("id"),
                    "source_no": row.get("report_no"),
                    "product_id": order.get("product_id"),
                    "quantity": Decimal("0"),
                    "unit_cost": Decimal("0"),
                    "amount": overhead,
                    "remark": "工序报工设备归集",
                }
            )
    return labor_cost, overhead_cost, lines


def _completion_lines(query_rows, order, work_order_id, cost_object_id):
    rows = query_rows(
        """
        SELECT wc.id, COALESCE(wc.source_doc_no, 'WC-' || wc.id::text) AS source_no,
               wc.product_id, COALESCE(wc.qty, 0) AS qty, COALESCE(wc.unit_cost, 0) AS unit_cost
        FROM wo_complete_items wc
        WHERE wc.wo_id=%s AND COALESCE(wc.qty, 0) <> 0
        ORDER BY wc.id
        """,
        (work_order_id,),
    )
    lines = []
    for row in rows or []:
        qty = _decimal(row.get("qty"))
        unit_cost = _decimal(row.get("unit_cost"))
        lines.append(
            {
                "work_order_id": work_order_id,
                "cost_object_id": cost_object_id,
                "cost_type": "完工入库",
                "source_type": "完工入库",
                "source_id": row.get("id"),
                "source_no": row.get("source_no"),
                "product_id": row.get("product_id") or order.get("product_id"),
                "quantity": qty,
                "unit_cost": unit_cost,
                "amount": qty * unit_cost,
                "remark": "完工入库成本对照",
            }
        )
    return lines


def _insert_cost_lines(execute_db, lines):
    for line in lines:
        execute_db(
            """
            INSERT INTO work_order_cost_lines
                (work_order_id, cost_object_id, cost_type, source_type, source_id, source_no,
                 product_id, quantity, unit_cost, amount, remark, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """,
            (
                line.get("work_order_id"),
                line.get("cost_object_id"),
                line.get("cost_type"),
                line.get("source_type"),
                line.get("source_id"),
                line.get("source_no"),
                line.get("product_id"),
                line.get("quantity"),
                line.get("unit_cost"),
                line.get("amount"),
                line.get("remark"),
            ),
        )


def sync_work_order_costs(query_one, query_rows, execute_db, work_order_id, source_type=None, source_no=None, remark=None):
    if not work_order_id:
        return {"synced": False, "reason": "missing_work_order"}
    ensure_work_order_cost_schema(execute_db)
    order = query_one(
        """
        SELECT id, wo_no, product_id, project_code, serial_no, cost_object_id, quantity
        FROM work_orders
        WHERE id=%s
        """,
        (work_order_id,),
    )
    if not order:
        return {"synced": False, "reason": "work_order_not_found"}
    cost_object_id = order.get("cost_object_id")
    cost_id = _latest_cost_id(query_one, execute_db, work_order_id, cost_object_id)
    material_cost, material_lines = _material_lines(query_rows, work_order_id, cost_object_id)
    subcontract_cost, subcontract_lines = _subcontract_lines(query_rows, order, work_order_id, cost_object_id)
    labor_cost, overhead_cost, operation_lines = _operation_lines(query_rows, order, work_order_id, cost_object_id)
    completion_lines = _completion_lines(query_rows, order, work_order_id, cost_object_id)
    total_cost = material_cost + subcontract_cost + labor_cost + overhead_cost
    execute_db(
        """
        UPDATE work_order_costs
        SET cost_object_id=%s,
            material_cost=%s,
            subcontract_cost=%s,
            labor_cost=%s,
            overhead_cost=%s,
            total_cost=%s,
            last_calculated_at=NOW()
        WHERE id=%s
        """,
        (cost_object_id, material_cost, subcontract_cost, labor_cost, overhead_cost, total_cost, cost_id),
    )
    execute_db(
        """
        DELETE FROM work_order_cost_lines
        WHERE work_order_id=%s AND source_type = ANY(%s)
        """,
        (work_order_id, list(SYSTEM_COST_SOURCE_TYPES)),
    )
    lines = material_lines + subcontract_lines + operation_lines + completion_lines
    _insert_cost_lines(execute_db, lines)
    return {
        "synced": True,
        "work_order_id": work_order_id,
        "source_type": source_type,
        "source_no": source_no,
        "remark": remark,
        "material_cost": material_cost,
        "subcontract_cost": subcontract_cost,
        "labor_cost": labor_cost,
        "overhead_cost": overhead_cost,
        "total_cost": total_cost,
        "line_count": len(lines),
    }
