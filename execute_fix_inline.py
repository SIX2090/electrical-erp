#!/usr/bin/env python3
"""
内联执行库存余额一致性修复（绕过 subprocess）
"""
import os
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 设置环境变量
os.environ.setdefault('PG_PASSWORD', 'admin')
os.environ.setdefault('PG_HOST', '127.0.0.1')
os.environ.setdefault('PG_PORT', '5432')
os.environ.setdefault('PG_DATABASE', 'wms')
os.environ.setdefault('PG_USER', 'wms_user')

from services.app_runtime import connect_db
from services.env_config import get_pg_password

def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }

QTY_TOLERANCE = "0.0001"
COST_TOLERANCE = "0.0001"
AUDIT_TABLE = "inventory_balance_repair_audit"

print("=" * 80)
print("库存余额一致性自动修复工具（AI 无人值守模式）")
print("=" * 80)
print()

# 步骤 1: 审计
print("步骤 1/5: 审计当前状态...")
print("-" * 80)

conn = connect_db(get_db_config())
cur = conn.cursor()

# 检查表是否存在
cur.execute("SELECT to_regclass('inventory_balances') AS tb")
if not cur.fetchone()['tb']:
    print("❌ inventory_balances 表不存在！")
    sys.exit(1)

# 审计 legacy inventory 不匹配
cur.execute(f"""
    WITH legacy AS (
        SELECT product_id, COALESCE(SUM(quantity),0) AS legacy_qty, COUNT(*) AS cnt
        FROM inventory GROUP BY product_id
    ),
    balances AS (
        SELECT product_id, COALESCE(SUM(quantity),0) AS balance_qty
        FROM inventory_balances GROUP BY product_id
    )
    SELECT COUNT(*) AS mismatch_count
    FROM legacy l FULL OUTER JOIN balances b ON b.product_id=l.product_id
    WHERE ABS(COALESCE(l.legacy_qty,0) - COALESCE(b.balance_qty,0)) > {QTY_TOLERANCE}
       OR COALESCE(l.cnt,0) > 1
""")
legacy_mismatch = cur.fetchone()['mismatch_count']

# 审计 batch_tracking 不匹配
cur.execute(f"""
    WITH batch AS (
        SELECT product_id, COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj,
               SUM(COALESCE(quantity_available,0)) AS qty, COUNT(*) AS cnt
        FROM batch_tracking
        GROUP BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                 COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
    ),
    balance AS (
        SELECT product_id, COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj,
               SUM(COALESCE(quantity,0)) AS qty
        FROM inventory_balances
        GROUP BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                 COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
    )
    SELECT COUNT(*) AS mismatch_count
    FROM batch b FULL OUTER JOIN balance bal
      ON b.product_id IS NOT DISTINCT FROM bal.product_id
     AND b.wh=bal.wh AND b.loc=bal.loc AND b.lot=bal.lot AND b.sn=bal.sn AND b.proj=bal.proj
    WHERE ABS(COALESCE(b.qty,0) - COALESCE(bal.qty,0)) > {QTY_TOLERANCE} OR COALESCE(b.cnt,0) > 1
""")
batch_mismatch = cur.fetchone()['mismatch_count']

total_findings = legacy_mismatch + batch_mismatch

print(f"legacy_inventory_mismatch={legacy_mismatch}")
print(f"batch_tracking_mismatch={batch_mismatch}")
print(f"total_findings={total_findings}")
print()

if total_findings == 0:
    print("✅ 审计通过！无需修复。")
    conn.close()
    sys.exit(0)

print(f"⚠️  发现 {total_findings} 个不一致问题，开始修复...")
print()

# 步骤 2: 创建审计表
print("步骤 2/5: 创建审计备份表...")
print("-" * 80)
cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
        id BIGSERIAL PRIMARY KEY,
        run_id TEXT NOT NULL,
        table_name TEXT NOT NULL,
        row_id INTEGER,
        action TEXT NOT NULL,
        before_data JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
""")
conn.commit()
print(f"✅ 审计表 {AUDIT_TABLE} 已准备就绪")
print()

# 步骤 3: 备份受影响行
print("步骤 3/5: 备份受影响行...")
print("-" * 80)
run_id = f"auto_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 备份 inventory
cur.execute(f"""
    INSERT INTO {AUDIT_TABLE} (run_id, table_name, row_id, action, before_data)
    SELECT %s, 'inventory', i.id, 'before_repair', to_jsonb(i)
    FROM inventory i
""", (run_id,))
inventory_backup_count = cur.rowcount

# 备份 batch_tracking
cur.execute(f"""
    INSERT INTO {AUDIT_TABLE} (run_id, table_name, row_id, action, before_data)
    SELECT %s, 'batch_tracking', bt.id, 'before_repair', to_jsonb(bt)
    FROM batch_tracking bt
""", (run_id,))
batch_backup_count = cur.rowcount

conn.commit()
print(f"✅ inventory 备份: {inventory_backup_count} 行")
print(f"✅ batch_tracking 备份: {batch_backup_count} 行")
print(f"✅ run_id: {run_id}")
print()

# 步骤 4: 修复 legacy inventory
print("步骤 4/5: 修复 legacy inventory...")
print("-" * 80)
cur.execute("""
    WITH desired AS (
        SELECT product_id,
               COALESCE(SUM(quantity),0) AS qty,
               CASE WHEN COALESCE(SUM(quantity),0) <> 0
                   THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                   ELSE COALESCE(MAX(unit_cost),0)
               END AS cost
        FROM inventory_balances GROUP BY product_id
    ),
    ranked AS (
        SELECT id, product_id, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY id) AS rn
        FROM inventory
    )
    UPDATE inventory i
    SET quantity=COALESCE(d.qty,0), unit_cost=COALESCE(d.cost,0)
    FROM ranked r LEFT JOIN desired d ON d.product_id=r.product_id
    WHERE i.id=r.id AND r.rn=1
""")
updated_legacy = cur.rowcount

# 清零重复行
cur.execute("""
    WITH ranked AS (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY id) AS rn
        FROM inventory
    )
    UPDATE inventory i SET quantity=0
    FROM ranked r WHERE i.id=r.id AND r.rn > 1
""")
zeroed_legacy = cur.rowcount

# 插入缺失行
cur.execute("""
    WITH desired AS (
        SELECT product_id,
               COALESCE(SUM(quantity),0) AS qty,
               CASE WHEN COALESCE(SUM(quantity),0) <> 0
                   THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                   ELSE COALESCE(MAX(unit_cost),0)
               END AS cost
        FROM inventory_balances GROUP BY product_id
    ),
    existing AS (SELECT DISTINCT product_id FROM inventory)
    INSERT INTO inventory (product_id, quantity, unit_cost, location, reorder_level)
    SELECT d.product_id, d.qty, d.cost, '', 0
    FROM desired d LEFT JOIN existing e ON e.product_id=d.product_id
    WHERE e.product_id IS NULL
""")
inserted_legacy = cur.rowcount

conn.commit()
print(f"✅ 更新: {updated_legacy} 行")
print(f"✅ 清零重复: {zeroed_legacy} 行")
print(f"✅ 插入缺失: {inserted_legacy} 行")
print()

# 步骤 5: 修复 batch_tracking
print("步骤 5/5: 修复 batch_tracking...")
print("-" * 80)

cur.execute("""
    WITH desired AS (
        SELECT product_id,
               COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj,
               SUM(COALESCE(quantity,0)) AS qty,
               CASE WHEN COALESCE(SUM(quantity),0) <> 0
                   THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                   ELSE COALESCE(MAX(unit_cost),0)
               END AS cost
        FROM inventory_balances
        GROUP BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                 COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
    ),
    ranked AS (
        SELECT id, product_id,
               COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj,
               ROW_NUMBER() OVER (
                   PARTITION BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                                COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
                   ORDER BY id
               ) AS rn
        FROM batch_tracking
    )
    UPDATE batch_tracking bt
    SET quantity_available=COALESCE(d.qty,0),
        unit_cost=COALESCE(d.cost, bt.unit_cost, 0),
        updated_at=NOW()
    FROM ranked r LEFT JOIN desired d
      ON d.product_id IS NOT DISTINCT FROM r.product_id
     AND d.wh=r.wh AND d.loc=r.loc AND d.lot=r.lot AND d.sn=r.sn AND d.proj=r.proj
    WHERE bt.id=r.id AND r.rn=1
""")
updated_batch = cur.rowcount

# 清零重复行
cur.execute("""
    WITH ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                                COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
                   ORDER BY id
               ) AS rn
        FROM batch_tracking
    )
    UPDATE batch_tracking bt SET quantity_available=0, updated_at=NOW()
    FROM ranked r WHERE bt.id=r.id AND r.rn > 1
""")
zeroed_batch = cur.rowcount

# 插入缺失维度
cur.execute("""
    WITH desired AS (
        SELECT product_id,
               COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj,
               SUM(COALESCE(quantity,0)) AS qty,
               CASE WHEN COALESCE(SUM(quantity),0) <> 0
                   THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                   ELSE COALESCE(MAX(unit_cost),0)
               END AS cost
        FROM inventory_balances
        GROUP BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                 COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
    ),
    existing AS (
        SELECT DISTINCT product_id,
               COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj
        FROM batch_tracking
    )
    INSERT INTO batch_tracking
        (lot_no, product_id, warehouse_id, location_id, cabinet_no, project_code,
         quantity_in, quantity_out, quantity_available, unit_cost, source_order_no,
         status, created_at, updated_at)
    SELECT COALESCE(d.lot,''), d.product_id, NULLIF(d.wh,0), NULLIF(d.loc,0),
           NULLIF(d.sn,''), NULLIF(d.proj,''),
           CASE WHEN d.qty>0 THEN d.qty ELSE 0 END,
           CASE WHEN d.qty<0 THEN -d.qty ELSE 0 END,
           d.qty, d.cost, 'auto_repair',
           'derived', NOW(), NOW()
    FROM desired d LEFT JOIN existing e
      ON e.product_id IS NOT DISTINCT FROM d.product_id
     AND e.wh=d.wh AND e.loc=d.loc AND e.lot=d.lot AND e.sn=d.sn AND e.proj=d.proj
    WHERE e.product_id IS NULL
""")
inserted_batch = cur.rowcount

conn.commit()
print(f"✅ 更新: {updated_batch} 行")
print(f"✅ 清零重复: {zeroed_batch} 行")
print(f"✅ 插入缺失: {inserted_batch} 行")
print()

# 最终验证
print("=" * 80)
print("最终验证...")
print("-" * 80)

# 重新审计
cur.execute(f"""
    WITH legacy AS (
        SELECT product_id, COALESCE(SUM(quantity),0) AS legacy_qty, COUNT(*) AS cnt
        FROM inventory GROUP BY product_id
    ),
    balances AS (
        SELECT product_id, COALESCE(SUM(quantity),0) AS balance_qty
        FROM inventory_balances GROUP BY product_id
    )
    SELECT COUNT(*) AS mismatch_count
    FROM legacy l FULL OUTER JOIN balances b ON b.product_id=l.product_id
    WHERE ABS(COALESCE(l.legacy_qty,0) - COALESCE(b.balance_qty,0)) > {QTY_TOLERANCE}
       OR COALESCE(l.cnt,0) > 1
""")
final_legacy = cur.fetchone()['mismatch_count']

cur.execute(f"""
    WITH batch AS (
        SELECT product_id, COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj,
               SUM(COALESCE(quantity_available,0)) AS qty, COUNT(*) AS cnt
        FROM batch_tracking
        GROUP BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                 COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
    ),
    balance AS (
        SELECT product_id, COALESCE(warehouse_id,0) AS wh, COALESCE(location_id,0) AS loc,
               COALESCE(lot_no,'') AS lot, COALESCE(cabinet_no,'') AS sn, COALESCE(project_code,'') AS proj,
               SUM(COALESCE(quantity,0)) AS qty
        FROM inventory_balances
        GROUP BY product_id, COALESCE(warehouse_id,0), COALESCE(location_id,0),
                 COALESCE(lot_no,''), COALESCE(cabinet_no,''), COALESCE(project_code,'')
    )
    SELECT COUNT(*) AS mismatch_count
    FROM batch b FULL OUTER JOIN balance bal
      ON b.product_id IS NOT DISTINCT FROM bal.product_id
     AND b.wh=bal.wh AND b.loc=bal.loc AND b.lot=bal.lot AND b.sn=bal.sn AND b.proj=bal.proj
    WHERE ABS(COALESCE(b.qty,0) - COALESCE(bal.qty,0)) > {QTY_TOLERANCE} OR COALESCE(b.cnt,0) > 1
""")
final_batch = cur.fetchone()['mismatch_count']

final_total = final_legacy + final_batch

cur.close()
conn.close()

print(f"legacy_inventory_mismatch={final_legacy}")
print(f"batch_tracking_mismatch={final_batch}")
print(f"total_findings={final_total}")
print()

if final_total == 0:
    print("=" * 80)
    print("🎉 修复成功！库存余额一致性审计通过！")
    print("=" * 80)
    print()
    print(f"审计备份表: {AUDIT_TABLE}")
    print(f"run_id: {run_id}")
    sys.exit(0)
else:
    print("=" * 80)
    print(f"⚠️  修复后仍有 {final_total} 个问题，需要进一步检查。")
    print("=" * 80)
    sys.exit(1)
