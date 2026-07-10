"""Deep investigation of inventory batch tracking vs balance inconsistency.
Read-only: only queries, no modifications.
"""
import os
import psycopg2
from decimal import Decimal

PG_PASSWORD = os.environ.get("PG_PASSWORD", "admin")
conn = psycopg2.connect(
    host="127.0.0.1", port=5432, dbname="wms",
    user="wms_user", password=PG_PASSWORD,
)
cur = conn.cursor()

PRODUCT_ID = 173
WAREHOUSE_ID = 58
LOCATION_ID = 11

print("=" * 80)
print("DEEP INVESTIGATION: batch_tracking vs inventory_balances mismatch")
print(f"product_id={PRODUCT_ID}, warehouse_id={WAREHOUSE_ID}, location_id={LOCATION_ID}")
print("=" * 80)

# 1. Product info
cur.execute("SELECT id, code, name, specification, unit FROM products WHERE id=%s", (PRODUCT_ID,))
prod = cur.fetchone()
print(f"\n[1] Product: {prod}")

# 2. Warehouse info
cur.execute("SELECT id, code, name FROM warehouses WHERE id=%s", (WAREHOUSE_ID,))
wh = cur.fetchone()
print(f"[2] Warehouse: {wh}")

# 3. Location info
cur.execute("SELECT id, code, name FROM locations WHERE id=%s", (LOCATION_ID,))
loc = cur.fetchone()
print(f"[3] Location: {loc}")

# 4. inventory_balances for this dimension
print(f"\n[4] inventory_balances rows for this dimension:")
cur.execute("""
    SELECT id, product_id, warehouse_id, location_id, lot_no, cabinet_no, project_code,
           quantity, unit_cost, updated_at
    FROM inventory_balances
    WHERE product_id=%s AND warehouse_id=%s AND location_id=%s
    ORDER BY id
""", (PRODUCT_ID, WAREHOUSE_ID, LOCATION_ID))
for row in cur.fetchall():
    print(f"  {row}")

# 5. batch_tracking for this dimension
print(f"\n[5] batch_tracking rows for this dimension:")
cur.execute("""
    SELECT *
    FROM batch_tracking
    WHERE product_id=%s AND warehouse_id=%s AND location_id=%s
    ORDER BY id
""", (PRODUCT_ID, WAREHOUSE_ID, LOCATION_ID))
cols = [desc[0] for desc in cur.description]
print(f"  Columns: {cols}")
for row in cur.fetchall():
    print(f"  {dict(zip(cols, row))}")

# 6. All stock_transactions for this product/warehouse/location
print(f"\n[6] stock_transactions for this dimension (all):")
cur.execute("""
    SELECT *
    FROM stock_transactions
    WHERE product_id=%s AND warehouse_id=%s AND location_id=%s
    ORDER BY id
""", (PRODUCT_ID, WAREHOUSE_ID, LOCATION_ID))
cols6 = [desc[0] for desc in cur.description]
print(f"  Columns: {cols6}")
for row in cur.fetchall():
    print(f"  {dict(zip(cols6, row))}")

# 7. Summary: sum of stock_transactions by lot_no/cabinet_no/project_code
print(f"\n[7] stock_transactions grouped by lot_no/cabinet_no/project_code:")
cur.execute("""
    SELECT lot_no, cabinet_no, project_code,
           SUM(quantity) as total_qty,
           COUNT(*) as txn_count,
           MIN(id) as min_id, MAX(id) as max_id
    FROM stock_transactions
    WHERE product_id=%s AND warehouse_id=%s AND location_id=%s
    GROUP BY lot_no, cabinet_no, project_code
    ORDER BY lot_no, cabinet_no, project_code
""", (PRODUCT_ID, WAREHOUSE_ID, LOCATION_ID))
for row in cur.fetchall():
    print(f"  lot='{row[0]}', cabinet='{row[1]}', project='{row[2]}', sum_qty={row[3]}, count={row[4]}, ids={row[5]}-{row[6]}")

# 8. Check if there are batch_tracking rows with same dimension but different lot_no
print(f"\n[8] ALL batch_tracking for this product (all warehouses/locations):")
cur.execute("""
    SELECT id, product_id, warehouse_id, location_id, lot_no, cabinet_no, project_code,
           quantity_in, quantity_out, quantity_available, unit_cost, updated_at
    FROM batch_tracking
    WHERE product_id=%s
    ORDER BY id
""", (PRODUCT_ID,))
for row in cur.fetchall():
    print(f"  {row}")

# 9. Check ALL inventory_balances for this product
print(f"\n[9] ALL inventory_balances for this product (all warehouses/locations):")
cur.execute("""
    SELECT id, product_id, warehouse_id, location_id, lot_no, cabinet_no, project_code,
           quantity, unit_cost, updated_at
    FROM inventory_balances
    WHERE product_id=%s
    ORDER BY id
""", (PRODUCT_ID,))
for row in cur.fetchall():
    print(f"  {row}")

# 10. Check if any stock_transaction has NULL lot_no vs empty string
print(f"\n[10] Check NULL vs empty lot_no in stock_transactions:")
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE lot_no IS NULL) as null_lot,
        COUNT(*) FILTER (WHERE lot_no = '') as empty_lot,
        COUNT(*) FILTER (WHERE lot_no IS NOT NULL AND lot_no != '') as has_lot
    FROM stock_transactions
    WHERE product_id=%s AND warehouse_id=%s AND location_id=%s
""", (PRODUCT_ID, WAREHOUSE_ID, LOCATION_ID))
row = cur.fetchone()
print(f"  NULL lot_no: {row[0]}, empty lot_no: {row[1]}, has lot_no: {row[2]}")

# 11. Check if batch_tracking uses NULL vs empty string for lot_no
print(f"\n[11] Check NULL vs empty lot_no in batch_tracking:")
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE lot_no IS NULL) as null_lot,
        COUNT(*) FILTER (WHERE lot_no = '') as empty_lot,
        COUNT(*) FILTER (WHERE lot_no IS NOT NULL AND lot_no != '') as has_lot
    FROM batch_tracking
    WHERE product_id=%s AND warehouse_id=%s AND location_id=%s
""", (PRODUCT_ID, WAREHOUSE_ID, LOCATION_ID))
row = cur.fetchone()
print(f"  NULL lot_no: {row[0]}, empty lot_no: {row[1]}, has lot_no: {row[2]}")

# 12. Check inventory_balances NULL vs empty
print(f"\n[12] Check NULL vs empty lot_no in inventory_balances:")
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE lot_no IS NULL) as null_lot,
        COUNT(*) FILTER (WHERE lot_no = '') as empty_lot,
        COUNT(*) FILTER (WHERE lot_no IS NOT NULL AND lot_no != '') as has_lot
    FROM inventory_balances
    WHERE product_id=%s AND warehouse_id=%s AND location_id=%s
""", (PRODUCT_ID, WAREHOUSE_ID, LOCATION_ID))
row = cur.fetchone()
print(f"  NULL lot_no: {row[0]}, empty lot_no: {row[1]}, has lot_no: {row[2]}")

# 13. Check the posting service logic - how batch_tracking is updated
print(f"\n[13] Check table schemas:")
for table in ["inventory_balances", "batch_tracking", "stock_transactions"]:
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name=%s
        ORDER BY ordinal_position
    """, (table,))
    print(f"\n  {table} columns:")
    for col in cur.fetchall():
        print(f"    {col[0]}: {col[1]}, nullable={col[2]}, default={col[3]}")

# 14. Check if the repair script's logic
print(f"\n[14] What repair_inventory_balance_consistency.py does:")
print("  (Check the repair script source for exact logic)")

cur.close()
conn.close()
print("\n" + "=" * 80)
print("Investigation complete.")
