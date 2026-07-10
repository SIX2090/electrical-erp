from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


FIELD_ALIASES = {
    "project_code": ("\u9879\u76ee\u53f7",),
    "cabinet_no": ("\u67dc\u53f7", "\u673a\u53f7", "serial_no"),
    "product_code": ("\u4ea7\u54c1\u7f16\u7801",),
    "bom_no": ("BOM\u7f16\u53f7",),
    "sales_qty": ("\u9500\u552e\u6570\u91cf",),
    "machine_model": ("\u89c4\u683c\u578b\u53f7", "\u673a\u578b"),
    "material_code_1": ("\u5173\u952e\u7269\u65991\u7f16\u7801",),
    "material_qty_1": ("\u5173\u952e\u7269\u65991\u6570\u91cf",),
    "material_code_2": ("\u5173\u952e\u7269\u65992\u7f16\u7801",),
    "material_qty_2": ("\u5173\u952e\u7269\u65992\u6570\u91cf",),
    "warehouse_code": ("\u9ed8\u8ba4\u4ed3\u5e93",),
}


DEFAULT_VALUES = {
    "customer_name": "\u6d59\u6c5f\u8bd5\u8fd0\u884c\u673a\u5e8a\u6709\u9650\u516c\u53f8",
    "sales_order_no": "SO-GT-TRIAL-20260526-001",
    "bom_version": "A",
    "delivery_date": "2026-06-30",
}


DEFAULT_ALIASES = {
    "customer_name": ("\u5ba2\u6237\u540d\u79f0",),
    "sales_order_no": ("销售订单号", "销售单号"),
    "bom_version": ("BOM\u7248\u672c",),
    "delivery_date": ("\u4ea4\u671f",),
}


def _set_aliases(values: dict[str, str], key: str, aliases: tuple[str, ...]) -> None:
    value = values.get(key, "")
    if not value:
        for alias in aliases:
            alias_value = values.get(alias, "")
            if alias_value:
                value = alias_value
                break
        if value:
            values[key] = value
    for alias in aliases:
        values.setdefault(alias, value)


def load_first_machine_values(path: Path | None = None) -> dict[str, str]:
    template = path or DEFAULT_TEMPLATE
    rows = list(csv.DictReader(template.open("r", encoding="utf-8-sig", newline="")))
    values: dict[str, str] = {}
    for row in rows:
        field = (row.get("field") or row.get("\u5b57\u6bb5") or "").strip()
        actual = (row.get("actual") or row.get("\u5b9e\u9645\u586b\u5199") or "").strip()
        if field:
            values[field] = actual

    for key, value in DEFAULT_VALUES.items():
        values.setdefault(key, value)
    for key, aliases in FIELD_ALIASES.items():
        _set_aliases(values, key, aliases)
    for key, aliases in DEFAULT_ALIASES.items():
        _set_aliases(values, key, aliases)
    return values


def load_trial_password(username: str) -> str:
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")


def load_trial_passwords() -> dict[str, str]:
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()


def _decimal(value: str | int | float | Decimal | None, default: str = "0") -> Decimal:
    if value in (None, ""):
        value = default
    return Decimal(str(value))


def _has_table(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table,))
    return bool((cur.fetchone() or {}).get("exists"))


def _columns(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {row["column_name"] for row in cur.fetchall()}


def _insert_dynamic(cur, table: str, values: dict) -> int | None:
    if not _has_table(cur, table):
        return None
    cols = _columns(cur, table)
    filtered = {key: value for key, value in values.items() if key in cols}
    if not filtered:
        return None
    names = list(filtered)
    placeholders = ",".join(["%s"] * len(names))
    cur.execute(
        f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders}) RETURNING id",
        [filtered[name] for name in names],
    )
    return cur.fetchone()["id"]


def _fetch_one(cur, sql: str, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_first_machine_demand_baseline(cur, values: dict[str, str]) -> None:
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    sales_qty = values.get("sales_qty") or "1"

    cur.execute("SELECT * FROM sales_orders WHERE order_no=%s", (values["sales_order_no"],))
    sales_order = cur.fetchone()
    cur.execute("SELECT * FROM products WHERE code=%s", (values["product_code"],))
    finished = cur.fetchone()
    cur.execute("SELECT * FROM boms WHERE bom_no=%s", (values["bom_no"],))
    bom = cur.fetchone()
    if not sales_order or not finished or not bom:
        return

    cur.execute("SELECT COUNT(*) AS value FROM sales_order_items WHERE order_id=%s", (sales_order["id"],))
    if int((cur.fetchone() or {}).get("value") or 0) == 0:
        unit_price = finished.get("standard_price") or sales_order.get("total_amount") or 0
        cur.execute(
            """
            INSERT INTO sales_order_items
                (order_id, product_id, quantity, shipped_qty, unit_price, amount, tax_rate,
                 tax_amount, amount_with_tax, material_code, material_name, material_spec,
                 material_unit, source_line_no, line_project_code, line_cabinet_no)
            VALUES (%s, %s, %s, 0, %s, %s, 13, 0, %s, %s, %s, %s, %s, '1', %s, %s)
            """,
            (
                sales_order["id"],
                finished["id"],
                sales_qty,
                unit_price,
                sales_order.get("total_amount") or unit_price,
                sales_order.get("amount_with_tax") or sales_order.get("total_amount") or unit_price,
                finished.get("code"),
                finished.get("name"),
                finished.get("specification") or "",
                finished.get("unit") or "",
                project_code,
                cabinet_no,
            ),
        )

    cur.execute(
        """
        INSERT INTO mrp_plans
            (plan_no, name, start_date, end_date, plan_type, status, target_product_id,
             target_quantity, warehouse_id, cost_object_id, project_code, cabinet_no, remark)
        SELECT %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '30 days', 'demand', 'planned',
               %s, %s, %s, %s, %s, %s, 'first machine demand baseline'
        WHERE NOT EXISTS (SELECT 1 FROM mrp_plans WHERE plan_no=%s)
        """,
        (
            f"MRP-{project_code}",
            "First machine MRP demand",
            finished["id"],
            sales_qty,
            sales_order.get("warehouse_id"),
            sales_order.get("cost_object_id"),
            project_code,
            cabinet_no,
            f"MRP-{project_code}",
        ),
    )
    cur.execute("SELECT id FROM mrp_plans WHERE plan_no=%s", (f"MRP-{project_code}",))
    plan = cur.fetchone()
    if not plan:
        return

    cur.execute(
        """
        INSERT INTO mrp_requirements
            (plan_id, product_id, requirement_type, requirement_date, quantity,
             source_document_type, source_document_id, planned_quantity, released_quantity,
             fulfilled_quantity, status, available_quantity, shortage_quantity, bom_level,
             parent_product_id, unit, supply_mode, manufacturing_role, cost_object_id,
             project_code, cabinet_no)
        SELECT %s, bi.product_id, 'production_order', CURRENT_DATE,
               bi.quantity * %s, 'sales_order', %s, 0, 0, 0, 'open',
               0, bi.quantity * %s, 1, %s, bi.unit, 'purchase', 'material',
               %s, %s, %s
        FROM bom_items bi
        WHERE bi.bom_id=%s
          AND NOT EXISTS (
              SELECT 1
              FROM mrp_requirements mr
              WHERE mr.plan_id=%s AND mr.product_id=bi.product_id
          )
        """,
        (
            plan["id"],
            sales_qty,
            sales_order["id"],
            sales_qty,
            finished["id"],
            sales_order.get("cost_object_id"),
            project_code,
            cabinet_no,
            bom["id"],
            plan["id"],
        ),
    )


def ensure_first_machine_production_inventory_baseline(cur, values: dict[str, str]) -> dict[str, int | str | None]:
    """Ensure the first-machine production and inventory trace baseline exists for audits."""
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    product_code = values["product_code"]
    material_code_1 = values["material_code_1"]
    material_code_2 = values.get("material_code_2") or ""
    warehouse_code = values.get("warehouse_code") or "GT-PILOT-WH"

    warehouse = _fetch_one(cur, "SELECT * FROM warehouses WHERE code=%s ORDER BY id LIMIT 1", (warehouse_code,))
    if not warehouse:
        cur.execute(
            """
            INSERT INTO warehouses (code, name, remark)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE
            SET name=EXCLUDED.name
            RETURNING id
            """,
            (warehouse_code, "\u9996\u53f0\u673a\u8bd5\u8fd0\u884c\u4ed3", "first machine pilot warehouse"),
        )
        warehouse_id = cur.fetchone()["id"]
        warehouse = _fetch_one(cur, "SELECT * FROM warehouses WHERE id=%s", (warehouse_id,))
    warehouse_id = warehouse["id"]

    location = _fetch_one(cur, "SELECT * FROM locations WHERE warehouse_id=%s ORDER BY id LIMIT 1", (warehouse_id,))
    if not location and _has_table(cur, "locations"):
        location_id = _insert_dynamic(
            cur,
            "locations",
            {"warehouse_id": warehouse_id, "code": "GT-PILOT-LOC", "name": "\u9996\u53f0\u673a\u5e93\u4f4d", "is_active": True},
        )
        location = _fetch_one(cur, "SELECT * FROM locations WHERE id=%s", (location_id,))
    location_id = location["id"] if location else None

    def ensure_product(code: str, name: str, category: str, unit_cost: Decimal) -> int:
        product = _fetch_one(cur, "SELECT id FROM products WHERE code=%s ORDER BY id LIMIT 1", (code,))
        if product:
            return product["id"]
        return _insert_dynamic(
            cur,
            "products",
            {
                "code": code,
                "name": name,
                "category": category,
                "specification": values.get("machine_model") if category == "finished_good" else "GT-PILOT",
                "unit": "\u53f0" if category == "finished_good" else "\u4ef6",
                "standard_price": unit_cost,
                "unit_cost": unit_cost,
                "status": "enabled",
                "serial_control": category == "finished_good",
            },
        )

    finished_id = ensure_product(product_code, "\u9996\u53f0\u673a\u8bd5\u8fd0\u884c\u6574\u673a", "finished_good", Decimal("120000"))
    material1_id = ensure_product(material_code_1, "\u9996\u53f0\u673a\u5173\u952e\u7269\u65991", "raw_material", Decimal("100"))
    material2_id = ensure_product(material_code_2, "\u9996\u53f0\u673a\u5173\u952e\u7269\u65992", "raw_material", Decimal("50")) if material_code_2 else None

    material_rows = [(material1_id, material_code_1, _decimal(values.get("material_qty_1"), "2"), Decimal("100"))]
    if material2_id:
        material_rows.append((material2_id, material_code_2, _decimal(values.get("material_qty_2"), "1"), Decimal("50")))

    work_order = _fetch_one(
        cur,
        "SELECT * FROM work_orders WHERE project_code=%s AND cabinet_no=%s ORDER BY id DESC LIMIT 1",
        (project_code, cabinet_no),
    )
    if not work_order:
        work_order_id = _insert_dynamic(
            cur,
            "work_orders",
            {
                "wo_no": f"WO-{project_code}",
                "wo_date": date.today(),
                "product_id": finished_id,
                "quantity": _decimal(values.get("sales_qty"), "1"),
                "status": "in_progress",
                "warehouse_id": warehouse_id,
                "location_id": location_id,
                "project_code": project_code,
                "cabinet_no": cabinet_no,
                "planned_start_date": date.today(),
                "planned_end_date": date.today(),
                "remark": "first machine production baseline",
                "production_stage": "assembly",
                "owner_role": "production",
            },
        )
        work_order = _fetch_one(cur, "SELECT * FROM work_orders WHERE id=%s", (work_order_id,))
    work_order_id = work_order["id"]

    for product_id, material_code, required_qty, unit_cost in material_rows:
        cur.execute("SELECT id FROM wo_material_items WHERE wo_id=%s AND product_id=%s LIMIT 1", (work_order_id, product_id))
        if not cur.fetchone():
            _insert_dynamic(
                cur,
                "wo_material_items",
                {
                    "wo_id": work_order_id,
                    "product_id": product_id,
                    "required_qty": required_qty,
                    "issued_qty": Decimal("0"),
                    "returned_qty": Decimal("0"),
                    "unit_cost": unit_cost,
                    "amount": required_qty * unit_cost,
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "material_code": material_code,
                    "material_name": "\u9996\u53f0\u673a\u5173\u952e\u7269\u6599",
                    "material_unit": "\u4ef6",
                    "source_line_no": material_code,
                    "line_project_code": project_code,
                    "line_cabinet_no": cabinet_no,
                },
            )
        stock_qty = max(required_qty * Decimal("3"), Decimal("3"))
        cur.execute(
            """
            SELECT id FROM inventory_balances
            WHERE product_id=%s AND COALESCE(warehouse_id,0)=COALESCE(%s,0)
              AND COALESCE(location_id,0)=COALESCE(%s,0)
              AND COALESCE(project_code,'')=%s AND COALESCE(cabinet_no,'')=%s
            LIMIT 1
            """,
            (product_id, warehouse_id, location_id, project_code, cabinet_no),
        )
        if cur.fetchone():
            cur.execute(
                """
                UPDATE inventory_balances
                SET quantity=GREATEST(COALESCE(quantity,0), %s), unit_cost=%s, updated_at=NOW()
                WHERE product_id=%s AND COALESCE(warehouse_id,0)=COALESCE(%s,0)
                  AND COALESCE(location_id,0)=COALESCE(%s,0)
                  AND COALESCE(project_code,'')=%s AND COALESCE(cabinet_no,'')=%s
                """,
                (stock_qty, unit_cost, product_id, warehouse_id, location_id, project_code, cabinet_no),
            )
        else:
            _insert_dynamic(
                cur,
                "inventory_balances",
                {
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "lot_no": "",
                    "cabinet_no": cabinet_no,
                    "project_code": project_code,
                    "quantity": stock_qty,
                    "locked_qty": Decimal("0"),
                    "unit_cost": unit_cost,
                    "updated_at": date.today(),
                },
            )
        reference_no = f"PR-{project_code}"
        cur.execute(
            """
            SELECT id FROM stock_transactions
            WHERE reference_no=%s AND product_id=%s AND project_code=%s AND cabinet_no=%s
            LIMIT 1
            """,
            (reference_no, product_id, project_code, cabinet_no),
        )
        if not cur.fetchone():
            _insert_dynamic(
                cur,
                "stock_transactions",
                {
                    "transaction_date": date.today(),
                    "transaction_type": "\u91c7\u8d2d\u5165\u5e93",
                    "product_id": product_id,
                    "quantity": stock_qty,
                    "unit_cost": unit_cost,
                    "amount": stock_qty * unit_cost,
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "lot_no": "",
                    "cabinet_no": cabinet_no,
                    "project_code": project_code,
                    "reference_no": reference_no,
                    "source_doc_type": "purchase_receipt",
                    "source_doc_no": reference_no,
                    "source_type": "first_machine_baseline",
                    "material_code": material_code,
                    "material_name": "\u9996\u53f0\u673a\u5173\u952e\u7269\u6599",
                    "material_unit": "\u4ef6",
                    "remark": "first machine project/cabinet opening receipt",
                },
            )

    receipt = _fetch_one(cur, "SELECT id FROM purchase_receipts WHERE receipt_no=%s", (f"PR-{project_code}",))
    if not receipt:
        receipt_id = _insert_dynamic(
            cur,
            "purchase_receipts",
            {
                "receipt_no": f"PR-{project_code}",
                "receipt_date": date.today(),
                "warehouse_id": warehouse_id,
                "status": "\u5df2\u8fc7\u8d26",
                "remark": "first machine trace receipt",
                "project_code": project_code,
                "cabinet_no": cabinet_no,
            },
        )
    else:
        receipt_id = receipt["id"]
    for product_id, _material_code, required_qty, unit_cost in material_rows:
        cur.execute("SELECT id FROM purchase_receipt_items WHERE receipt_id=%s AND product_id=%s LIMIT 1", (receipt_id, product_id))
        if not cur.fetchone():
            _insert_dynamic(
                cur,
                "purchase_receipt_items",
                {
                    "receipt_id": receipt_id,
                    "product_id": product_id,
                    "quantity": max(required_qty * Decimal("3"), Decimal("3")),
                    "unit_cost": unit_cost,
                    "lot_no": "",
                    "location_id": location_id,
                    "amount_with_tax": max(required_qty * Decimal("3"), Decimal("3")) * unit_cost,
                },
            )

    inspection = _fetch_one(
        cur,
        """
        SELECT id FROM quality_inspection_records
        WHERE (
                source_document_type='work_order'
                AND source_document_id=%s
                AND project_code=%s
                AND cabinet_no=%s
              )
           OR inspection_no=%s
        LIMIT 1
        """,
        (work_order_id, project_code, cabinet_no, f"QI-{project_code}"),
    )
    if not inspection:
        _insert_dynamic(
            cur,
            "quality_inspection_records",
            {
                "inspection_no": f"QI-{project_code}",
                "product_id": finished_id,
                "inspection_type": "final",
                "inspection_date": date.today(),
                "sample_size": Decimal("1"),
                "passed_quantity": Decimal("1"),
                "failed_quantity": Decimal("0"),
                "inspection_result": "pass",
                "status": "completed",
                "source_document_type": "work_order",
                "source_document_id": work_order_id,
                "project_code": project_code,
                "cabinet_no": cabinet_no,
                "conclusion": "first machine quality passed",
            },
        )

    return {
        "warehouse_id": warehouse_id,
        "location_id": location_id,
        "finished_id": finished_id,
        "material1_id": material1_id,
        "material2_id": material2_id,
        "work_order_id": work_order_id,
        "project_code": project_code,
        "cabinet_no": cabinet_no,
    }


def _upsert_partner(cur, table: str, name: str, values: dict) -> int:
    row = _fetch_one(cur, f"SELECT id FROM {table} WHERE name=%s ORDER BY id LIMIT 1", (name,))
    if row:
        cols = _columns(cur, table)
        assignments = []
        params = []
        for key, value in values.items():
            if key in cols and key != "name":
                assignments.append(f"{key}=%s")
                params.append(value)
        if assignments:
            params.append(row["id"])
            cur.execute(f"UPDATE {table} SET {', '.join(assignments)} WHERE id=%s", params)
        return row["id"]
    payload = {"name": name, **values}
    inserted = _insert_dynamic(cur, table, payload)
    if inserted is None:
        raise RuntimeError(f"Unable to create {table} row for first-machine sample")
    return inserted


def _ensure_product(cur, code: str, name: str, category: str, unit: str, price: Decimal, specification: str = "") -> int:
    row = _fetch_one(cur, "SELECT id FROM products WHERE code=%s ORDER BY id LIMIT 1", (code,))
    payload = {
        "name": name,
        "category": category,
        "item_type": category,
        "specification": specification,
        "unit": unit,
        "standard_price": price,
        "unit_cost": price,
        "status": "enabled",
    }
    if row:
        cols = _columns(cur, "products")
        assignments = [f"{key}=%s" for key in payload if key in cols]
        cur.execute(
            f"UPDATE products SET {', '.join(assignments)} WHERE id=%s",
            [payload[key] for key in payload if key in cols] + [row["id"]],
        )
        return row["id"]
    inserted = _insert_dynamic(cur, "products", {"code": code, **payload})
    if inserted is None:
        raise RuntimeError(f"Unable to create product {code}")
    return inserted


def _ensure_warehouse(cur, code: str) -> tuple[int, int | None]:
    warehouse = _fetch_one(cur, "SELECT id FROM warehouses WHERE code=%s ORDER BY id LIMIT 1", (code,))
    if warehouse:
        warehouse_id = warehouse["id"]
    else:
        warehouse_id = _insert_dynamic(
            cur,
            "warehouses",
            {"code": code, "name": "First Machine Trial Warehouse", "remark": "first machine lifecycle sample"},
        )
    location_id = None
    if _has_table(cur, "locations"):
        location = _fetch_one(cur, "SELECT id FROM locations WHERE warehouse_id=%s ORDER BY id LIMIT 1", (warehouse_id,))
        if location:
            location_id = location["id"]
        else:
            location_id = _insert_dynamic(
                cur,
                "locations",
                {"warehouse_id": warehouse_id, "code": "GT-TRIAL-LOC", "name": "First Machine Trial Location", "is_active": True},
            )
    return warehouse_id, location_id


def _ensure_bom(cur, finished_id: int, material_rows: list[tuple[int, Decimal, str]], values: dict[str, str]) -> int:
    bom_no = values["bom_no"]
    row = _fetch_one(cur, "SELECT id FROM boms WHERE bom_no=%s ORDER BY id LIMIT 1", (bom_no,))
    if row:
        bom_id = row["id"]
        cur.execute(
            "UPDATE boms SET product_id=%s, version=%s, status=%s, remark=%s WHERE id=%s",
            (finished_id, values.get("bom_version") or "A", "enabled", "first machine lifecycle sample", bom_id),
        )
    else:
        bom_id = _insert_dynamic(
            cur,
            "boms",
            {
                "product_id": finished_id,
                "bom_no": bom_no,
                "version": values.get("bom_version") or "A",
                "status": "enabled",
                "remark": "first machine lifecycle sample",
                "bom_type": "production",
                "effective_date": date.today(),
            },
        )
    for product_id, quantity, unit in material_rows:
        row = _fetch_one(cur, "SELECT id FROM bom_items WHERE bom_id=%s AND product_id=%s LIMIT 1", (bom_id, product_id))
        if row:
            cur.execute("UPDATE bom_items SET quantity=%s, unit=%s, remark=%s WHERE id=%s", (quantity, unit, "first machine lifecycle sample", row["id"]))
        else:
            _insert_dynamic(
                cur,
                "bom_items",
                {"bom_id": bom_id, "product_id": product_id, "quantity": quantity, "unit": unit, "remark": "first machine lifecycle sample"},
            )
    return bom_id


def _ensure_sales_order(cur, values: dict[str, str], customer_id: int, finished_id: int, warehouse_id: int, cost_object_id: int | None) -> int:
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    order_no = values.get("sales_order_no") or "SO-GT-TRIAL-20260526-001"
    quantity = _decimal(values.get("sales_qty"), "1")
    total_amount = Decimal("168000")
    tax_amount = (total_amount * Decimal("0.13")).quantize(Decimal("0.01"))
    amount_with_tax = total_amount + tax_amount
    row = _fetch_one(cur, "SELECT id FROM sales_orders WHERE order_no=%s ORDER BY id LIMIT 1", (order_no,))
    payload = {
        "order_date": date.today(),
        "customer_id": customer_id,
        "status": "completed",
        "remark": "first machine lifecycle sample",
        "total_amount": total_amount,
        "shipped_amount": total_amount,
        "warehouse_id": warehouse_id,
        "delivery_date": values.get("delivery_date") or "2026-06-30",
        "tax_amount": tax_amount,
        "amount_with_tax": amount_with_tax,
        "cost_object_id": cost_object_id,
        "project_code": project_code,
        "cabinet_no": cabinet_no,
    }
    if row:
        order_id = row["id"]
        cols = _columns(cur, "sales_orders")
        assignments = [f"{key}=%s" for key in payload if key in cols]
        cur.execute(f"UPDATE sales_orders SET {', '.join(assignments)} WHERE id=%s", [payload[key] for key in payload if key in cols] + [order_id])
    else:
        order_id = _insert_dynamic(cur, "sales_orders", {"order_no": order_no, **payload})
    item = _fetch_one(cur, "SELECT id FROM sales_order_items WHERE order_id=%s AND product_id=%s LIMIT 1", (order_id, finished_id))
    item_payload = {
        "quantity": quantity,
        "shipped_qty": quantity,
        "unit_price": total_amount,
        "amount": total_amount,
        "tax_rate": Decimal("13"),
        "tax_amount": tax_amount,
        "amount_with_tax": amount_with_tax,
        "material_code": values["product_code"],
        "material_name": "First Machine Trial Finished Product",
        "material_spec": values.get("machine_model") or "GT-RD-800",
        "material_unit": "set",
        "source_line_no": "1",
        "line_project_code": project_code,
        "line_cabinet_no": cabinet_no,
    }
    if item:
        cols = _columns(cur, "sales_order_items")
        assignments = [f"{key}=%s" for key in item_payload if key in cols]
        cur.execute(f"UPDATE sales_order_items SET {', '.join(assignments)} WHERE id=%s", [item_payload[key] for key in item_payload if key in cols] + [item["id"]])
    else:
        _insert_dynamic(cur, "sales_order_items", {"order_id": order_id, "product_id": finished_id, **item_payload})
    return order_id


def _ensure_mrp(cur, values: dict[str, str], finished_id: int, bom_id: int, sales_order_id: int, cost_object_id: int | None, warehouse_id: int | None) -> int | None:
    ensure_first_machine_demand_baseline(cur, values)
    row = _fetch_one(cur, "SELECT id FROM mrp_plans WHERE plan_no=%s ORDER BY id LIMIT 1", (f"MRP-{values['project_code']}",))
    if row:
        return row["id"]
    plan_id = _insert_dynamic(
        cur,
        "mrp_plans",
        {
            "plan_no": f"MRP-{values['project_code']}",
            "name": "First machine lifecycle MRP",
            "start_date": date.today(),
            "end_date": date.today(),
            "plan_type": "demand",
            "status": "planned",
            "target_product_id": finished_id,
            "target_quantity": _decimal(values.get("sales_qty"), "1"),
            "warehouse_id": warehouse_id,
            "cost_object_id": cost_object_id,
            "project_code": values["project_code"],
            "cabinet_no": values["cabinet_no"],
            "remark": "first machine lifecycle sample",
        },
    )
    if plan_id is None:
        return None
    cur.execute("SELECT product_id, quantity, unit FROM bom_items WHERE bom_id=%s", (bom_id,))
    for item in cur.fetchall():
        _insert_dynamic(
            cur,
            "mrp_requirements",
            {
                "plan_id": plan_id,
                "product_id": item["product_id"],
                "requirement_type": "purchase",
                "requirement_date": date.today(),
                "quantity": item["quantity"],
                "source_document_type": "sales_order",
                "source_document_id": sales_order_id,
                "planned_quantity": Decimal("0"),
                "released_quantity": Decimal("0"),
                "fulfilled_quantity": Decimal("0"),
                "status": "open",
                "available_quantity": Decimal("0"),
                "shortage_quantity": item["quantity"],
                "bom_level": 1,
                "parent_product_id": finished_id,
                "unit": item.get("unit") or "pcs",
                "supply_mode": "purchase",
                "manufacturing_role": "material",
                "cost_object_id": cost_object_id,
                "project_code": values["project_code"],
                "cabinet_no": values["cabinet_no"],
            },
        )
    return plan_id


def _ensure_purchase_order(cur, values: dict[str, str], supplier_id: int, material_rows: list[tuple[int, str, Decimal, Decimal]], warehouse_id: int, cost_object_id: int | None) -> int:
    order_no = "PO-GT-TRIAL-20260526-001"
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    total_amount = sum((qty * unit_cost for _pid, _code, qty, unit_cost in material_rows), Decimal("0"))
    row = _fetch_one(cur, "SELECT id FROM purchase_orders WHERE order_no=%s ORDER BY id LIMIT 1", (order_no,))
    payload = {
        "order_date": date.today(),
        "supplier_id": supplier_id,
        "status": "completed",
        "remark": "first machine lifecycle sample",
        "total_amount": total_amount,
        "received_amount": total_amount,
        "warehouse_id": warehouse_id,
        "expected_date": date.today(),
        "tax_amount": Decimal("0"),
        "amount_with_tax": total_amount,
        "cost_object_id": cost_object_id,
        "project_code": project_code,
        "cabinet_no": cabinet_no,
    }
    if row:
        order_id = row["id"]
        cols = _columns(cur, "purchase_orders")
        assignments = [f"{key}=%s" for key in payload if key in cols]
        cur.execute(f"UPDATE purchase_orders SET {', '.join(assignments)} WHERE id=%s", [payload[key] for key in payload if key in cols] + [order_id])
    else:
        order_id = _insert_dynamic(cur, "purchase_orders", {"order_no": order_no, **payload})
    for index, (product_id, material_code, quantity, unit_cost) in enumerate(material_rows, start=1):
        row = _fetch_one(cur, "SELECT id FROM purchase_order_items WHERE order_id=%s AND product_id=%s LIMIT 1", (order_id, product_id))
        line_payload = {
            "quantity": quantity,
            "received_qty": quantity,
            "unit_price": unit_cost,
            "amount": quantity * unit_cost,
            "tax_rate": Decimal("13"),
            "tax_amount": Decimal("0"),
            "amount_with_tax": quantity * unit_cost,
            "material_code": material_code,
            "material_name": "First Machine Trial Material",
            "material_unit": "pcs",
            "source_line_no": str(index),
            "line_project_code": project_code,
            "line_cabinet_no": cabinet_no,
        }
        if row:
            cols = _columns(cur, "purchase_order_items")
            assignments = [f"{key}=%s" for key in line_payload if key in cols]
            cur.execute(f"UPDATE purchase_order_items SET {', '.join(assignments)} WHERE id=%s", [line_payload[key] for key in line_payload if key in cols] + [row["id"]])
        else:
            _insert_dynamic(cur, "purchase_order_items", {"order_id": order_id, "product_id": product_id, **line_payload})
    return order_id


def _ensure_purchase_requisition(cur, values: dict[str, str], supplier_id: int, material_rows: list[tuple[int, str, Decimal, Decimal]], warehouse_id: int, cost_object_id: int | None) -> int:
    req_no = "PR-GT-TRIAL-20260526-001"
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    row = _fetch_one(cur, "SELECT id FROM purchase_requisitions WHERE req_no=%s ORDER BY id LIMIT 1", (req_no,))
    payload = {
        "req_date": date.today(),
        "department": "production",
        "purpose": "first machine MRP shortage",
        "status": "已审核",
        "approval_status": "approved",
        "remark": "first machine lifecycle sample",
        "cost_object_id": cost_object_id,
        "project_code": project_code,
        "cabinet_no": cabinet_no,
    }
    if row:
        req_id = row["id"]
        cols = _columns(cur, "purchase_requisitions")
        assignments = [f"{key}=%s" for key in payload if key in cols]
        cur.execute(f"UPDATE purchase_requisitions SET {', '.join(assignments)} WHERE id=%s", [payload[key] for key in payload if key in cols] + [req_id])
    else:
        req_id = _insert_dynamic(cur, "purchase_requisitions", {"req_no": req_no, **payload})
    for index, (product_id, material_code, quantity, unit_cost) in enumerate(material_rows, start=1):
        item_row = _fetch_one(cur, "SELECT id FROM purchase_requisition_items WHERE req_id=%s AND product_id=%s LIMIT 1", (req_id, product_id))
        line_payload = {
            "quantity": quantity,
            "unit_price": unit_cost,
            "amount": quantity * unit_cost,
            "need_date": date.today(),
            "suggested_supplier_id": supplier_id,
            "remark": "first machine lifecycle sample",
            "cost_object_id": cost_object_id,
            "project_code": project_code,
            "cabinet_no": cabinet_no,
            "warehouse_id": warehouse_id,
            "source_line_no": str(index),
            "material_code": material_code,
            "material_name": "First Machine Trial Material",
            "material_unit": "pcs",
        }
        if item_row:
            cols = _columns(cur, "purchase_requisition_items")
            assignments = [f"{key}=%s" for key in line_payload if key in cols]
            cur.execute(f"UPDATE purchase_requisition_items SET {', '.join(assignments)} WHERE id=%s", [line_payload[key] for key in line_payload if key in cols] + [item_row["id"]])
        else:
            _insert_dynamic(cur, "purchase_requisition_items", {"req_id": req_id, "product_id": product_id, **line_payload})
    return req_id


def _ensure_subcontract_order(cur, values: dict[str, str], supplier_id: int, finished_id: int, work_order_id: int, warehouse_id: int, location_id: int | None, cost_object_id: int | None) -> int:
    order_no = "OS-GT-TRIAL-20260526-001"
    amount = Decimal("2400")
    row = _fetch_one(cur, "SELECT id FROM subcontract_orders WHERE order_no=%s ORDER BY id LIMIT 1", (order_no,))
    payload = {
        "supplier_id": supplier_id,
        "order_date": date.today(),
        "required_date": date.today(),
        "status": "completed",
        "total_amount": amount,
        "tax_amount": Decimal("0"),
        "total_tax_amount": amount,
        "remark": "first machine lifecycle sample",
        "parent_work_order_id": work_order_id,
        "warehouse_id": warehouse_id,
        "cost_object_id": cost_object_id,
        "project_code": values["project_code"],
        "cabinet_no": values["cabinet_no"],
        "product_id": finished_id,
        "quantity": Decimal("1"),
        "unit_price": amount,
        "material_code": values["product_code"],
        "material_name": "First Machine Trial Finished Product",
        "material_spec": values.get("machine_model") or "GT-RD-800",
        "material_unit": "set",
        "process_name": "trial outsourced process",
        "location": str(location_id or ""),
        "source_line_no": "1",
        "line_project_code": values["project_code"],
        "line_cabinet_no": values["cabinet_no"],
        "received_qty": Decimal("1"),
    }
    if row:
        order_id = row["id"]
        cols = _columns(cur, "subcontract_orders")
        assignments = [f"{key}=%s" for key in payload if key in cols]
        cur.execute(f"UPDATE subcontract_orders SET {', '.join(assignments)} WHERE id=%s", [payload[key] for key in payload if key in cols] + [order_id])
    else:
        order_id = _insert_dynamic(cur, "subcontract_orders", {"order_no": order_no, **payload})
    return order_id


def _ensure_work_order_cost(cur, work_order_id: int, cost_object_id: int | None, subcontract_order_id: int) -> None:
    total = Decimal("98000")
    row = _fetch_one(cur, "SELECT id FROM work_order_costs WHERE work_order_id=%s ORDER BY id LIMIT 1", (work_order_id,))
    payload = {
        "cost_object_id": cost_object_id,
        "material_cost": Decimal("95600"),
        "subcontract_cost": Decimal("2400"),
        "labor_cost": Decimal("0"),
        "overhead_cost": Decimal("0"),
        "total_cost": total,
        "last_calculated_at": date.today(),
    }
    if row:
        cols = _columns(cur, "work_order_costs")
        assignments = [f"{key}=%s" for key in payload if key in cols]
        cur.execute(f"UPDATE work_order_costs SET {', '.join(assignments)} WHERE id=%s", [payload[key] for key in payload if key in cols] + [row["id"]])
    else:
        _insert_dynamic(cur, "work_order_costs", {"work_order_id": work_order_id, **payload})
    cur.execute("DELETE FROM work_order_cost_lines WHERE work_order_id=%s AND source_no IN (%s,%s)", (work_order_id, "PO-GT-TRIAL-20260526-001", "OS-GT-TRIAL-20260526-001"))
    for cost_type, source_no, amount, source_type, source_id in [
        ("material", "PO-GT-TRIAL-20260526-001", Decimal("95600"), "purchase_order", None),
        ("subcontract", "OS-GT-TRIAL-20260526-001", Decimal("2400"), "subcontract_order", subcontract_order_id),
    ]:
        _insert_dynamic(
            cur,
            "work_order_cost_lines",
            {
                "work_order_id": work_order_id,
                "cost_object_id": cost_object_id,
                "cost_type": cost_type,
                "source_type": source_type,
                "source_id": source_id,
                "source_no": source_no,
                "quantity": Decimal("1"),
                "unit_cost": amount,
                "amount": amount,
                "remark": "first machine lifecycle sample",
            },
        )


def _ensure_shipment(cur, values: dict[str, str], sales_order_id: int, finished_id: int, customer_id: int, warehouse_id: int, location_id: int | None, cost_object_id: int | None) -> int:
    shipment_no = "SH-GT-TRIAL-20260526-001"
    row = _fetch_one(cur, "SELECT id FROM sales_shipments WHERE shipment_no=%s ORDER BY id LIMIT 1", (shipment_no,))
    payload = {
        "order_id": sales_order_id,
        "shipment_date": date.today(),
        "warehouse_id": warehouse_id,
        "status": "shipped",
        "remark": "first machine lifecycle sample",
        "cost_object_id": cost_object_id,
        "project_code": values["project_code"],
        "cabinet_no": values["cabinet_no"],
        "customer_id": customer_id,
        "source_type": "sales_order",
        "source_no": values.get("sales_order_no") or "SO-GT-TRIAL-20260526-001",
        "shipped_amount": Decimal("168000"),
        "tax_amount": Decimal("21840"),
        "amount_with_tax": Decimal("189840"),
        "inventory_posted": True,
    }
    if row:
        shipment_id = row["id"]
        cols = _columns(cur, "sales_shipments")
        assignments = [f"{key}=%s" for key in payload if key in cols]
        cur.execute(f"UPDATE sales_shipments SET {', '.join(assignments)} WHERE id=%s", [payload[key] for key in payload if key in cols] + [shipment_id])
    else:
        shipment_id = _insert_dynamic(cur, "sales_shipments", {"shipment_no": shipment_no, **payload})
    item = _fetch_one(cur, "SELECT id FROM sales_shipment_items WHERE shipment_id=%s AND product_id=%s LIMIT 1", (shipment_id, finished_id))
    line_payload = {"quantity": Decimal("1"), "unit_cost": Decimal("98000"), "location_id": location_id, "unit_price": Decimal("168000"), "amount": Decimal("168000"), "cost_amount": Decimal("98000")}
    if item:
        cols = _columns(cur, "sales_shipment_items")
        assignments = [f"{key}=%s" for key in line_payload if key in cols]
        cur.execute(f"UPDATE sales_shipment_items SET {', '.join(assignments)} WHERE id=%s", [line_payload[key] for key in line_payload if key in cols] + [item["id"]])
    else:
        _insert_dynamic(cur, "sales_shipment_items", {"shipment_id": shipment_id, "product_id": finished_id, **line_payload})
    return shipment_id


def _ensure_service_chain(cur, values: dict[str, str], sales_order_id: int, finished_id: int, customer_id: int, work_order_id: int, warehouse_id: int, location_id: int | None, cost_object_id: int | None) -> tuple[int, int, int]:
    card = _fetch_one(cur, "SELECT id FROM machine_service_cards WHERE project_code=%s AND cabinet_no=%s ORDER BY id LIMIT 1", (values["project_code"], values["cabinet_no"]))
    card_payload = {
        "wo_id": work_order_id,
        "product_id": finished_id,
        "cabinet_no": values["cabinet_no"],
        "customer_id": customer_id,
        "install_date": date.today(),
        "installation_date": date.today(),
        "acceptance_date": date.today(),
        "warranty_start_date": date.today(),
        "warranty_end_date": date.today(),
        "status": "active",
        "remark": "first machine lifecycle sample",
        "sales_order_id": sales_order_id,
        "cost_object_id": cost_object_id,
        "project_code": values["project_code"],
        "machine_model": values.get("machine_model") or "GT-RD-800",
    }
    if card:
        card_id = card["id"]
        cols = _columns(cur, "machine_service_cards")
        assignments = [f"{key}=%s" for key in card_payload if key in cols]
        cur.execute(f"UPDATE machine_service_cards SET {', '.join(assignments)} WHERE id=%s", [card_payload[key] for key in card_payload if key in cols] + [card_id])
    else:
        card_id = _insert_dynamic(cur, "machine_service_cards", card_payload)
    order = _fetch_one(cur, "SELECT id FROM machine_service_orders WHERE order_no=%s ORDER BY id LIMIT 1", ("SV-GT-TRIAL-20260526-001",))
    order_payload = {
        "service_card_id": card_id,
        "wo_id": work_order_id,
        "service_date": date.today(),
        "service_type": "inspection",
        "performed_by": None,
        "warehouse_id": warehouse_id,
        "location_id": location_id,
        "labor_cost": Decimal("300"),
        "travel_cost": Decimal("200"),
        "parts_cost": Decimal("0"),
        "total_cost": Decimal("500"),
        "billing_type": "warranty",
        "billable_amount": Decimal("0"),
        "settlement_status": "closed",
        "status": "closed",
        "issue_summary": "first machine lifecycle inspection",
        "solution": "sample closed",
        "remark": "first machine lifecycle sample",
        "sales_order_id": sales_order_id,
        "cost_object_id": cost_object_id,
        "project_code": values["project_code"],
        "cabinet_no": values["cabinet_no"],
    }
    if order:
        order_id = order["id"]
        cols = _columns(cur, "machine_service_orders")
        assignments = [f"{key}=%s" for key in order_payload if key in cols]
        cur.execute(f"UPDATE machine_service_orders SET {', '.join(assignments)} WHERE id=%s", [order_payload[key] for key in order_payload if key in cols] + [order_id])
    else:
        order_id = _insert_dynamic(cur, "machine_service_orders", {"order_no": "SV-GT-TRIAL-20260526-001", **order_payload})
    rma = _fetch_one(cur, "SELECT id FROM machine_service_rmas WHERE rma_no=%s ORDER BY id LIMIT 1", ("RMA-GT-TRIAL-20260526-001",))
    rma_payload = {
        "order_id": order_id,
        "service_card_id": card_id,
        "wo_id": work_order_id,
        "rma_date": date.today(),
        "warranty_scope": "in_warranty",
        "responsibility_type": "internal",
        "return_factory_required": False,
        "status": "closed",
        "internal_claim_amount": Decimal("0"),
        "supplier_claim_amount": Decimal("0"),
        "supplier_recovered_amount": Decimal("0"),
        "claim_status": "closed",
        "fault_summary": "first machine lifecycle RMA sample",
        "diagnosis": "sample closed",
        "remark": "first machine lifecycle sample",
        "sales_order_id": sales_order_id,
        "cost_object_id": cost_object_id,
        "project_code": values["project_code"],
        "cabinet_no": values["cabinet_no"],
        "product_id": finished_id,
        "quantity": Decimal("1"),
        "unit_cost": Decimal("0"),
        "amount": Decimal("0"),
        "warehouse_id": warehouse_id,
        "location_id": location_id,
        "material_code": values["product_code"],
        "material_name": "First Machine Trial Finished Product",
        "material_unit": "set",
        "source_line_no": "1",
        "line_project_code": values["project_code"],
        "line_cabinet_no": values["cabinet_no"],
    }
    if rma:
        rma_id = rma["id"]
        cols = _columns(cur, "machine_service_rmas")
        assignments = [f"{key}=%s" for key in rma_payload if key in cols]
        cur.execute(f"UPDATE machine_service_rmas SET {', '.join(assignments)} WHERE id=%s", [rma_payload[key] for key in rma_payload if key in cols] + [rma_id])
    else:
        rma_id = _insert_dynamic(cur, "machine_service_rmas", {"rma_no": "RMA-GT-TRIAL-20260526-001", **rma_payload})
    return card_id, order_id, rma_id


def _ensure_finance_evidence(cur, values: dict[str, str], customer_id: int, supplier_id: int, sales_order_id: int, purchase_order_id: int, subcontract_order_id: int, cost_object_id: int | None) -> None:
    ar = _fetch_one(cur, "SELECT id FROM customer_receivables WHERE source_type=%s AND source_id=%s ORDER BY id LIMIT 1", ("sales_order", sales_order_id))
    ar_payload = {
        "customer_id": customer_id,
        "source_no": values.get("sales_order_no") or "SO-GT-TRIAL-20260526-001",
        "receivable_date": date.today(),
        "total_amount": Decimal("189840"),
        "received_amount": Decimal("0"),
        "balance": Decimal("189840"),
        "status": "open",
        "due_date": date.today(),
        "remark": "first machine lifecycle sample",
        "cost_object_id": cost_object_id,
        "project_code": values["project_code"],
        "cabinet_no": values["cabinet_no"],
        "expected_amount": Decimal("189840"),
        "confirmed_amount": Decimal("189840"),
    }
    if ar:
        cols = _columns(cur, "customer_receivables")
        assignments = [f"{key}=%s" for key in ar_payload if key in cols]
        cur.execute(f"UPDATE customer_receivables SET {', '.join(assignments)} WHERE id=%s", [ar_payload[key] for key in ar_payload if key in cols] + [ar["id"]])
    else:
        _insert_dynamic(cur, "customer_receivables", {"source_type": "sales_order", "source_id": sales_order_id, **ar_payload})
    for doc_type, doc_id, doc_no, amount in [
        ("purchase_order", purchase_order_id, "PO-GT-TRIAL-20260526-001", Decimal("95600")),
        ("subcontract_order", subcontract_order_id, "OS-GT-TRIAL-20260526-001", Decimal("2400")),
    ]:
        ap = _fetch_one(cur, "SELECT id FROM supplier_payables WHERE doc_type=%s AND doc_id=%s ORDER BY id LIMIT 1", (doc_type, doc_id))
        ap_payload = {
            "supplier_id": supplier_id,
            "doc_no": doc_no,
            "doc_date": date.today(),
            "amount": amount,
            "paid_amount": Decimal("0"),
            "balance": amount,
            "status": "open",
            "finance_remark": "first machine lifecycle sample",
            "project_code": values["project_code"],
            "cabinet_no": values["cabinet_no"],
            "cost_object_id": cost_object_id,
            "source_type": doc_type,
            "source_id": doc_id,
            "source_no": doc_no,
            "expected_amount": amount,
            "confirmed_amount": amount,
            "variance_amount": Decimal("0"),
            "due_date": date.today(),
        }
        if ap:
            cols = _columns(cur, "supplier_payables")
            assignments = [f"{key}=%s" for key in ap_payload if key in cols]
            cur.execute(f"UPDATE supplier_payables SET {', '.join(assignments)} WHERE id=%s", [ap_payload[key] for key in ap_payload if key in cols] + [ap["id"]])
        else:
            _insert_dynamic(cur, "supplier_payables", {"doc_type": doc_type, "doc_id": doc_id, **ap_payload})


def _clear_first_machine_audit_login_blockers(cur) -> None:
    if _has_table(cur, "login_attempts"):
        cur.execute("DELETE FROM login_attempts WHERE username=%s", ("pilot_admin",))
    if _has_table(cur, "rate_limit_windows"):
        cur.execute("DELETE FROM rate_limit_windows WHERE limiter_key IN (%s,%s)", ("127.0.0.1", "local"))


def ensure_first_machine_lifecycle_sample(cur, values: dict[str, str]) -> dict[str, int | str | None]:
    """Ensure the controlled first-machine lifecycle sample spans every audit checkpoint."""
    project_code = values["project_code"]
    cabinet_no = values["cabinet_no"]
    values.setdefault("sales_order_no", "SO-GT-TRIAL-20260526-001")
    values.setdefault("bom_no", "BOM-GT-TRIAL-001")
    values.setdefault("bom_version", "A")
    values.setdefault("delivery_date", "2026-06-30")

    warehouse_id, location_id = _ensure_warehouse(cur, values.get("warehouse_code") or "GT-PILOT-WH")
    customer_id = _upsert_partner(
        cur,
        "customers",
        values.get("customer_name") or "First Machine Trial Customer",
        {"contact_person": "trial owner", "phone": "13800000000", "customer_level": "trial", "remark": "first machine lifecycle sample"},
    )
    supplier_id = _upsert_partner(
        cur,
        "suppliers",
        "First Machine Trial Supplier",
        {"contact_person": "trial owner", "phone": "13900000000", "lead_time_days": 7, "remark": "first machine lifecycle sample"},
    )
    finished_id = _ensure_product(
        cur,
        values["product_code"],
        "First Machine Trial Finished Product",
        "finished_good",
        "set",
        Decimal("168000"),
        values.get("machine_model") or "GT-RD-800",
    )
    material1_id = _ensure_product(cur, values["material_code_1"], "First Machine Trial Material 1", "raw_material", "pcs", Decimal("58000"), "GT-MAT")
    material_rows = [(material1_id, values["material_code_1"], _decimal(values.get("material_qty_1"), "2"), Decimal("58000"))]
    if values.get("material_code_2"):
        material2_id = _ensure_product(cur, values["material_code_2"], "First Machine Trial Material 2", "raw_material", "pcs", Decimal("38000"), "GT-MAT")
        material_rows.append((material2_id, values["material_code_2"], _decimal(values.get("material_qty_2"), "1"), Decimal("38000")))
    else:
        material2_id = None

    bom_id = _ensure_bom(cur, finished_id, [(row[0], row[2], "pcs") for row in material_rows], values)
    sales_order_id = _ensure_sales_order(cur, values, customer_id, finished_id, warehouse_id, None)
    _ensure_mrp(cur, values, finished_id, bom_id, sales_order_id, None, warehouse_id)
    production = ensure_first_machine_production_inventory_baseline(cur, values)
    work_order_id = int(production["work_order_id"])
    cur.execute(
        "UPDATE work_orders SET wo_no=%s, bom_id=%s, product_id=%s, quantity=%s, status=%s, cost_object_id=%s, project_code=%s, cabinet_no=%s WHERE id=%s",
        ("WO-GT-TRIAL-20260526-001", bom_id, finished_id, _decimal(values.get("sales_qty"), "1"), "completed", None, project_code, cabinet_no, work_order_id),
    )
    purchase_order_id = _ensure_purchase_order(cur, values, supplier_id, material_rows, warehouse_id, None)
    _ensure_purchase_requisition(cur, values, supplier_id, material_rows, warehouse_id, None)
    subcontract_order_id = _ensure_subcontract_order(cur, values, supplier_id, finished_id, work_order_id, warehouse_id, location_id, None)
    _ensure_work_order_cost(cur, work_order_id, None, subcontract_order_id)
    shipment_id = _ensure_shipment(cur, values, sales_order_id, finished_id, customer_id, warehouse_id, location_id, None)
    _ensure_service_chain(cur, values, sales_order_id, finished_id, customer_id, work_order_id, warehouse_id, location_id, None)
    _ensure_finance_evidence(cur, values, customer_id, supplier_id, sales_order_id, purchase_order_id, subcontract_order_id, None)
    _clear_first_machine_audit_login_blockers(cur)

    return {
        "project_code": project_code,
        "cabinet_no": cabinet_no,
        "sales_order_id": sales_order_id,
        "bom_id": bom_id,
        "work_order_id": work_order_id,
        "purchase_order_id": purchase_order_id,
        "subcontract_order_id": subcontract_order_id,
        "shipment_id": shipment_id,
        "warehouse_id": warehouse_id,
        "location_id": location_id,
        "finished_id": finished_id,
        "material1_id": material1_id,
        "material2_id": material2_id,
    }
