"""Extract core business table schemas from the codebase to generate CREATE TABLE migrations."""
import re
import os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CORE_TABLES = [
    "products", "customers", "suppliers", "warehouses", "locations", "units",
    "sales_orders", "sales_order_items", "purchase_orders", "purchase_order_items",
    "purchase_requisitions", "purchase_requisition_items", "purchase_receipts", "purchase_receipt_items",
    "stock_transactions", "inventory_balances", "work_orders", "work_order_items",
    "customer_receivables", "supplier_payables",
    "product_categories", "customer_categories", "supplier_categories", "warehouse_categories",
    "inventory_adjustments", "inventory_adjustment_items", "transfer_orders",
    "inventory_check_orders", "boms", "bom_items",
    "departments", "employees",
    "sales_shipments", "shipment_items",
]

# Type inference from column name patterns
def infer_type(col):
    cl = col.lower()
    if cl == "id":
        return "SERIAL PRIMARY KEY"
    if cl.endswith("_id"):
        return "INTEGER"
    if cl.endswith("_date") or cl == "date":
        return "DATE"
    if cl.endswith("_at") or cl.endswith("_time") or "timestamp" in cl:
        return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    if cl in ("amount", "total_amount", "amount_with_tax", "tax_amount", "balance",
              "paid_amount", "expected_amount", "confirmed_amount", "variance_amount",
              "price", "unit_price", "standard_price", "standard_cost", "unit_cost",
              "last_purchase_cost", "current_cost", "credit_limit", "credit_used",
              "quantity", "qty", "available_qty", "safety_stock", "min_stock",
              "max_stock", "stock", "stock_qty", "received_qty", "shipped_qty",
              "conversion_rate", "default_tax_rate", "tax_rate", "discount",
              "total_qty", "wip_qty", "operation_wip_qty", "completed_qty",
              "rate", "cost", "lead_time_days", "purchase_lead_days"):
        return "NUMERIC(16,4) DEFAULT 0"
    if cl in ("is_active", "is_outsourced_processor", "is_sales", "disabled"):
        return "BOOLEAN DEFAULT TRUE"
    if cl in ("remark", "description", "blocked_reason", "downstream_impact",
              "usage_reason", "finance_remark", "address", "specification"):
        return "TEXT"
    if cl in ("status",):
        return "VARCHAR(50) DEFAULT '启用'"
    if cl in ("doc_status", "approval_status"):
        return "VARCHAR(30)"
    if cl == "row_version":
        return "INTEGER DEFAULT 1"
    if cl == "data" or cl == "extra_data":
        return "JSONB DEFAULT '{}'::jsonb"
    return "VARCHAR(200)"


# 1. Extract from ALTER TABLE ADD COLUMN in schema_migrations.py
alter_columns = defaultdict(dict)  # table -> {col: type}
migration_text = (ROOT / "services" / "schema_migrations.py").read_text(encoding="utf-8")

# Match: ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <col> <type>;
for m in re.finditer(
    r'ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+([^\n;]+)',
    migration_text, re.IGNORECASE
):
    table, col, typ = m.group(1), m.group(2), m.group(3).strip()
    if table in CORE_TABLES:
        alter_columns[table][col] = typ

# 2. Extract column names from INSERT and UPDATE in all .py files
insert_columns = defaultdict(set)  # table -> {col, ...}

py_files = list((ROOT / "routes").glob("*.py")) + list((ROOT / "services").glob("*.py"))
py_files.append(ROOT / "app.py")

for pyfile in py_files:
    try:
        text = pyfile.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue

    # INSERT INTO <table> (col1, col2, ...) VALUES
    for m in re.finditer(
        r'INSERT\s+INTO\s+(\w+)\s*\(\s*([^)]+)\)\s*(?:VALUES|SELECT|RETURNING)',
        text, re.IGNORECASE
    ):
        table = m.group(1)
        if table not in CORE_TABLES:
            continue
        cols_str = m.group(2)
        for col in re.split(r'[,\s]+', cols_str.strip()):
            col = col.strip().strip('"').strip("'")
            if col and col.isidentifier():
                insert_columns[table].add(col)

    # UPDATE <table> SET col1=..., col2=...
    for m in re.finditer(
        r'UPDATE\s+(\w+)\s+SET\s+([^WHERE;]+?)(?:\s+WHERE|\s+RETURNING|;|\n)',
        text, re.IGNORECASE
    ):
        table = m.group(1)
        if table not in CORE_TABLES:
            continue
        set_str = m.group(2)
        for col_m in re.finditer(r'(\w+)\s*=', set_str):
            col = col_m.group(1)
            if col.isidentifier():
                insert_columns[table].add(col)

# 3. Combine: for each table, merge ALTER columns and INSERT columns
all_columns = defaultdict(dict)  # table -> {col: type}
for table in CORE_TABLES:
    cols = {}
    # Start with INSERT/UPDATE columns (may not have types)
    for col in insert_columns.get(table, set()):
        cols[col] = None  # type unknown yet
    # Override with ALTER TABLE columns (authoritative types)
    for col, typ in alter_columns.get(table, {}).items():
        cols[col] = typ
    # Fill in missing types with inference
    for col in list(cols.keys()):
        if cols[col] is None:
            cols[col] = infer_type(col)
    all_columns[table] = cols

# 4. Output CREATE TABLE IF NOT EXISTS SQL
lines = []
lines.append("-- Core business tables: CREATE TABLE IF NOT EXISTS migrations")
lines.append("-- Generated from ALTER TABLE definitions and INSERT/UPDATE column extraction")
lines.append("")

for table in CORE_TABLES:
    cols = all_columns.get(table, {})
    if not cols:
        print(f"# WARNING: {table} - no columns found")
        continue
    lines.append(f"-- {table}: {len(cols)} columns")
    col_defs = []
    has_id = "id" in cols
    if has_id:
        col_defs.append(f"    id SERIAL PRIMARY KEY")
    for col, typ in sorted(cols.items()):
        if col == "id":
            continue
        col_defs.append(f'    {col} {typ}')
    lines.append(f"CREATE TABLE IF NOT EXISTS {table} (")
    lines.append(",\n".join(col_defs))
    lines.append(");")
    lines.append("")

    # Report
    untyped = [c for c in cols if cols[c] == infer_type(c) and c not in alter_columns.get(table, {})]
    print(f"{table}: {len(cols)} cols ({len(alter_columns.get(table, {}))} from ALTER, {len(untyped)} inferred)")

print("\n--- SQL OUTPUT ---")
print("\n".join(lines))
