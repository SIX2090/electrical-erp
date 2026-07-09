"""Reference-check helpers for safe deletion of master data records."""
BASIC_DELETE_REFERENCE_CHECKS = {
    "material": [
        ("sales_order_items", "product_id", "销售明细"),
        ("purchase_order_items", "product_id", "采购明细"),
        ("inventory_balances", "product_id", "库存余额"),
        ("stock_transactions", "product_id", "库存流水"),
        ("bom_items", "product_id", "BOM子件"),
        ("boms", "product_id", "BOM主件"),
        ("work_orders", "product_id", "生产工单"),
        ("wo_material_items", "product_id", "工单领料"),
        ("transfer_order_items", "product_id", "调拨明细"),
        ("inventory_check_order_items", "product_id", "盘点明细"),
    ],
    "customer": [
        ("sales_orders", "customer_id", "销售订单"),
        ("customer_receivables", "customer_id", "应收账目"),
        ("customer_receipts", "customer_id", "客户回款"),
        ("machine_service_cards", "customer_id", "设备服务档案"),
    ],
    "supplier": [
        ("purchase_orders", "supplier_id", "采购单"),
        ("purchase_requisitions", "suggested_supplier_id", "采购申请"),
        ("supplier_prices", "supplier_id", "供应价格"),
        ("supplier_payables", "supplier_id", "应付账目"),
        ("supplier_payments", "supplier_id", "供应商付款"),
        ("subcontract_orders", "supplier_id", "委外单"),
    ],
    "warehouse": [
        ("locations", "warehouse_id", "库位"),
        ("inventory_balances", "warehouse_id", "库存余额"),
        ("stock_transactions", "warehouse_id", "库存流水"),
        ("sales_orders", "warehouse_id", "销售订单"),
        ("purchase_orders", "warehouse_id", "采购单"),
        ("work_orders", "warehouse_id", "生产工单"),
        ("transfer_orders", "from_warehouse_id", "调出单"),
        ("transfer_orders", "to_warehouse_id", "调入单"),
        ("inventory_check_orders", "warehouse_id", "盘点单"),
    ],
    "location": [
        ("inventory_balances", "location_id", "库存余额"),
        ("stock_transactions", "location_id", "库存流水"),
        ("wo_complete_items", "location_id", "完工入库"),
    ],
    "department": [
        ("employees", "dept_id", "员工"),
        ("departments", "parent_id", "下级部门"),
    ],
    "employee": [
        ("wage_calculations", "employee_id", "工资核算"),
        ("payroll_records", "employee_id", "薪资记录"),
    ],
}


def reference_count(table, column, value, *, has_table, has_column, count_rows, extra_where=""):
    if not has_table(table) or not has_column(table, column):
        return 0
    where = f"{column}=%s"
    if extra_where:
        where = f"{where} AND ({extra_where})"
    return count_rows(table, where, (value,))


def basic_delete_blockers(kind, record, *, has_table, has_column, count_rows):
    record_id = record.get("id") if record else None
    if not record_id:
        return []

    checks = BASIC_DELETE_REFERENCE_CHECKS
    blockers = []
    for table, column, label in checks.get(kind, []):
        count = reference_count(table, column, record_id, has_table=has_table, has_column=has_column, count_rows=count_rows)
        if count:
            blockers.append(f"{label}{count}条")

    if kind == "unit":
        code = record.get("code") or ""
        name = record.get("name") or ""
        product_count = 0
        if code or name:
            product_count = count_rows("products", "(unit=%s OR unit=%s)", (code, name))
        base_count = reference_count("units", "base_unit_id", record_id, has_table=has_table, has_column=has_column, count_rows=count_rows)
        if product_count:
            blockers.append(f"物料引用{product_count}条")
        if base_count:
            blockers.append(f"下级单位{base_count}条")
    return blockers
