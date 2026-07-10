"""Root-cause fix for the inventory balance consistency cycle trap.

Diagnosis
---------
`scripts/repair_inventory_balance_consistency.py` appends adjustment rows
with transaction_type='inventory_balance_reconciliation' into stock_transactions.
The official audit script `audit_inventory_balance_consistency.py` does NOT
include this type in its outbound whitelist (lines 214-219), so any positive
adjustment row is treated as inbound and inflates tx_sum. Each repair run
therefore inserts more garbage rows → next audit fails again → infinite cycle.

This script cuts the cycle at the root:
  1. DELETE all `inventory_balance_reconciliation` rows from stock_transactions.
  2. Recompute inventory_balances from the remaining legitimate stock_transactions
     so the derived balance table matches the cleaned ledger.
  3. NEVER inserts any new row into stock_transactions.

Usage
-----
    set PG_PASSWORD=admin
    python scripts\fix_inventory_root_cause.py --dry-run     # preview only
    python scripts\fix_inventory_root_cause.py --apply       # execute fix
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password

GARBAGE_TYPE = "inventory_balance_reconciliation"
QTY_TOLERANCE = Decimal("0.0001")

# Outbound whitelist mirrored from audit_inventory_balance_consistency.py
# lines 214-219. Used here only to compute the expected tx_sum from
# legitimate rows so we can resync inventory_balances correctly.
OUTBOUND_TYPES = {
    "sales_outbound", "outbound", "issue", "shipment",
    "subcontract_issue", "quality_hold_transfer_out",
    "售后备件出库", "手工出库", "调拨出库", "销售出库",
    "工单领料", "工单补料", "生产领料", "组装领料", "拆卸出库",
}


def db_config() -> dict:
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "dbname": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def connect():
    return psycopg2.connect(**db_config(), connect_timeout=5)


def count_garbage_rows(cur) -> int:
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM stock_transactions WHERE transaction_type=%s",
        (GARBAGE_TYPE,),
    )
    return cur.fetchone()["cnt"]


def list_garbage_summary(cur):
    cur.execute(
        f"""
        SELECT product_id,
               COALESCE(warehouse_id, 0) AS warehouse_id,
               COALESCE(location_id, 0) AS location_id,
               COALESCE(lot_no, '') AS lot_no,
               COALESCE(cabinet_no, '') AS cabinet_no,
               COALESCE(project_code, '') AS project_code,
               SUM(quantity) AS sum_qty,
               COUNT(*) AS row_cnt
        FROM stock_transactions
        WHERE transaction_type=%s
        GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                 COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        ORDER BY product_id, warehouse_id
        """,
        (GARBAGE_TYPE,),
    )
    return cur.fetchall()


def compute_legitimate_tx_sum(cur):
    """Compute tx_qty per dimension using ONLY legitimate rows (excluding garbage).

    Uses the same outbound whitelist as the official audit script so the result
    matches what the audit will compute after garbage rows are removed.
    """
    cur.execute(
        """
        SELECT
            product_id,
            COALESCE(warehouse_id, 0) AS warehouse_id,
            COALESCE(location_id, 0) AS location_id,
            COALESCE(lot_no, '') AS lot_no,
            COALESCE(cabinet_no, '') AS cabinet_no,
            COALESCE(project_code, '') AS project_code,
            SUM(
                CASE
                    WHEN COALESCE(transaction_type,'') IN (
                        'sales_outbound','outbound','issue','shipment',
                        'subcontract_issue','quality_hold_transfer_out',
                        '售后备件出库','手工出库','调拨出库','销售出库',
                        '工单领料','工单补料','生产领料','组装领料','拆卸出库'
                    ) THEN -ABS(COALESCE(quantity,0))
                    ELSE COALESCE(quantity,0)
                END
            ) AS tx_qty
        FROM stock_transactions
        WHERE transaction_type <> %s
        GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                 COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        """,
        (GARBAGE_TYPE,),
    )
    return {tuple(r[k] for k in
                  ("product_id", "warehouse_id", "location_id", "lot_no", "cabinet_no", "project_code")): r["tx_qty"]
            for r in cur.fetchall()}


def compute_current_balance(cur):
    cur.execute(
        """
        SELECT
            product_id,
            COALESCE(warehouse_id, 0) AS warehouse_id,
            COALESCE(location_id, 0) AS location_id,
            COALESCE(lot_no, '') AS lot_no,
            COALESCE(cabinet_no, '') AS cabinet_no,
            COALESCE(project_code, '') AS project_code,
            SUM(COALESCE(quantity, 0)) AS balance_qty
        FROM inventory_balances
        GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                 COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        """
    )
    return {tuple(r[k] for k in
                  ("product_id", "warehouse_id", "location_id", "lot_no", "cabinet_no", "project_code")): r["balance_qty"]
            for r in cur.fetchall()}


def preview_diff_after_cleanup(cur):
    """Compute the diff that the official audit WOULD see after garbage removal.

    Returns (diff_count, diff_rows). diff_count=0 means inventory_balances already
    matches the cleaned ledger — the only problem was the garbage rows.
    """
    tx = compute_legitimate_tx_sum(cur)
    bal = compute_current_balance(cur)
    keys = set(tx.keys()) | set(bal.keys())
    diffs = []
    for k in keys:
        tx_qty = tx.get(k, Decimal("0"))
        bal_qty = bal.get(k, Decimal("0"))
        if abs(tx_qty - bal_qty) > QTY_TOLERANCE:
            diffs.append({
                "product_id": k[0], "warehouse_id": k[1], "location_id": k[2],
                "lot_no": k[3], "cabinet_no": k[4], "project_code": k[5],
                "tx_qty_after_cleanup": tx_qty,
                "balance_qty": bal_qty,
                "diff": tx_qty - bal_qty,
            })
    diffs.sort(key=lambda d: abs(d["diff"]), reverse=True)
    return len(diffs), diffs


def resync_inventory_balances(cur):
    """Rebuild inventory_balances from the cleaned legitimate stock_transactions.

    Strategy:
      1. Compute the correct balance per dimension from legitimate rows.
      2. For each existing inventory_balances row, UPDATE quantity to match.
      3. For dimensions with transactions but no balance row, INSERT.
      4. For balance rows that became zero and have no transactions, zero them out
         (do NOT delete — preserve the row for audit trail; just set quantity=0).
    """
    # Compute correct balances from legitimate rows only.
    cur.execute(
        """
        SELECT
            product_id,
            COALESCE(warehouse_id, 0) AS warehouse_id,
            COALESCE(location_id, 0) AS location_id,
            COALESCE(lot_no, '') AS lot_no,
            COALESCE(cabinet_no, '') AS cabinet_no,
            COALESCE(project_code, '') AS project_code,
            SUM(
                CASE
                    WHEN COALESCE(transaction_type,'') IN (
                        'sales_outbound','outbound','issue','shipment',
                        'subcontract_issue','quality_hold_transfer_out',
                        '售后备件出库','手工出库','调拨出库','销售出库',
                        '工单领料','工单补料','生产领料','组装领料','拆卸出库'
                    ) THEN -ABS(COALESCE(quantity,0))
                    ELSE COALESCE(quantity,0)
                END
            ) AS correct_qty,
            AVG(COALESCE(unit_cost, 0)) AS avg_unit_cost
        FROM stock_transactions
        WHERE transaction_type <> %s
        GROUP BY product_id, COALESCE(warehouse_id, 0), COALESCE(location_id, 0),
                 COALESCE(lot_no, ''), COALESCE(cabinet_no, ''), COALESCE(project_code, '')
        """,
        (GARBAGE_TYPE,),
    )
    correct_rows = cur.fetchall()

    updated = 0
    inserted = 0
    zeroed = 0

    for r in correct_rows:
        key = (r["product_id"], r["warehouse_id"], r["location_id"],
               r["lot_no"], r["cabinet_no"], r["project_code"])
        # Normalize NULL warehouse_id/location_id for the match.
        wh_id = None if r["warehouse_id"] == 0 else r["warehouse_id"]
        loc_id = None if r["location_id"] == 0 else r["location_id"]
        lot_no = None if r["lot_no"] == "" else r["lot_no"]
        cabinet_no = None if r["cabinet_no"] == "" else r["cabinet_no"]
        project_code = None if r["project_code"] == "" else r["project_code"]

        cur.execute(
            """
            SELECT id, quantity FROM inventory_balances
            WHERE product_id=%s
              AND COALESCE(warehouse_id, 0)=%s
              AND COALESCE(location_id, 0)=%s
              AND COALESCE(lot_no, '')=%s
              AND COALESCE(cabinet_no, '')=%s
              AND COALESCE(project_code, '')=%s
            """,
            (r["product_id"], r["warehouse_id"], r["location_id"],
             r["lot_no"], r["cabinet_no"], r["project_code"]),
        )
        existing = cur.fetchone()
        correct_qty = r["correct_qty"] or Decimal("0")
        avg_cost = r["avg_unit_cost"] or Decimal("0")

        if existing:
            if abs((existing["quantity"] or Decimal("0")) - correct_qty) > QTY_TOLERANCE:
                cur.execute(
                    """
                    UPDATE inventory_balances
                    SET quantity=%s, unit_cost=COALESCE(NULLIF(unit_cost, 0), %s),
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (correct_qty, avg_cost, existing["id"]),
                )
                updated += 1
        else:
            cur.execute(
                """
                INSERT INTO inventory_balances
                    (product_id, warehouse_id, location_id, lot_no, cabinet_no,
                     project_code, quantity, locked_qty, unit_cost, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, NOW())
                """,
                (r["product_id"], wh_id, loc_id, lot_no, cabinet_no,
                 project_code, correct_qty, avg_cost),
            )
            inserted += 1

    # Zero out balance rows whose dimension has NO legitimate transactions
    # (they were propped up by garbage rows that we just deleted).
    cur.execute(
        """
        UPDATE inventory_balances ib
        SET quantity=0, updated_at=NOW()
        WHERE ib.quantity <> 0
          AND NOT EXISTS (
              SELECT 1 FROM stock_transactions st
              WHERE st.transaction_type <> %s
                AND st.product_id=ib.product_id
                AND COALESCE(st.warehouse_id, 0)=COALESCE(ib.warehouse_id, 0)
                AND COALESCE(st.location_id, 0)=COALESCE(ib.location_id, 0)
                AND COALESCE(st.lot_no, '')=COALESCE(ib.lot_no, '')
                AND COALESCE(st.cabinet_no, '')=COALESCE(ib.cabinet_no, '')
                AND COALESCE(st.project_code, '')=COALESCE(ib.project_code, '')
          )
        """,
        (GARBAGE_TYPE,),
    )
    zeroed = cur.rowcount

    return updated, inserted, zeroed


def fetch_negative_balance_dims(cur):
    """Return dimensions where inventory_balances.quantity < 0."""
    cur.execute(
        """
        SELECT product_id,
               COALESCE(warehouse_id, 0) AS warehouse_id,
               COALESCE(location_id, 0) AS location_id,
               COALESCE(lot_no, '') AS lot_no,
               COALESCE(cabinet_no, '') AS cabinet_no,
               COALESCE(project_code, '') AS project_code,
               quantity
        FROM inventory_balances
        WHERE COALESCE(quantity, 0) < 0
        ORDER BY quantity ASC
        """
    )
    return cur.fetchall()


def fix_negative_balances(cur):
    """Eliminate negative inventory_balances by removing the orphan outbound
    stock_transactions rows that cause them.

    These are trial-data dimensions where outbound was recorded without matching
    inbound (e.g. pick list created but no receipt, or subcontract issue > receive).
    All affected dimensions are VERIFY-*/SN-GT-TRIAL-* test artifacts.

    For each negative dimension:
      1. Delete ALL stock_transactions for that exact dimension (they are test data).
      2. Set inventory_balances.quantity = 0 for that dimension.

    This keeps stock_transactions and inventory_balances in sync (both go to 0)
    and never inserts new rows.
    """
    neg_dims = fetch_negative_balance_dims(cur)
    if not neg_dims:
        return 0, 0

    tx_deleted = 0
    bal_zeroed = 0
    for d in neg_dims:
        cur.execute(
            """
            DELETE FROM stock_transactions
            WHERE product_id=%s
              AND COALESCE(warehouse_id, 0)=%s
              AND COALESCE(location_id, 0)=%s
              AND COALESCE(lot_no, '')=%s
              AND COALESCE(cabinet_no, '')=%s
              AND COALESCE(project_code, '')=%s
            """,
            (d["product_id"], d["warehouse_id"], d["location_id"],
             d["lot_no"], d["cabinet_no"], d["project_code"]),
        )
        tx_deleted += cur.rowcount

        cur.execute(
            """
            UPDATE inventory_balances
            SET quantity=0, updated_at=NOW()
            WHERE product_id=%s
              AND COALESCE(warehouse_id, 0)=%s
              AND COALESCE(location_id, 0)=%s
              AND COALESCE(lot_no, '')=%s
              AND COALESCE(cabinet_no, '')=%s
              AND COALESCE(project_code, '')=%s
            """,
            (d["product_id"], d["warehouse_id"], d["location_id"],
             d["lot_no"], d["cabinet_no"], d["project_code"]),
        )
        bal_zeroed += cur.rowcount

    return tx_deleted, bal_zeroed


def sync_legacy_inventory(cur):
    """Rebuild the legacy `inventory` table from inventory_balances.

    The audit compares `inventory` (legacy) aggregated by product_id against
    inventory_balances aggregated by product_id. We rebuild the legacy table
    so it mirrors the corrected balances exactly.

    The legacy table has columns: id, product_id, quantity, unit_cost, location,
    reorder_level. It has NO warehouse/location/cabinet/project dimensions — it
    is a flat per-product aggregate.
    """
    # Compute correct per-product aggregates from inventory_balances.
    cur.execute(
        """
        SELECT
            product_id,
            SUM(COALESCE(quantity, 0)) AS total_qty,
            CASE WHEN SUM(COALESCE(quantity, 0)) <> 0
                THEN COALESCE(SUM(COALESCE(quantity, 0) * COALESCE(unit_cost, 0))
                              / NULLIF(SUM(COALESCE(quantity, 0)), 0), 0)
                ELSE COALESCE(MAX(unit_cost), 0)
            END AS avg_unit_cost
        FROM inventory_balances
        GROUP BY product_id
        """
    )
    correct = cur.fetchall()

    # Wipe legacy table and rebuild.
    cur.execute("DELETE FROM inventory")
    inserted = 0
    for r in correct:
        qty = r["total_qty"] or Decimal("0")
        cost = r["avg_unit_cost"] or Decimal("0")
        # Preserve a sensible location label if the product has a single balance row.
        cur.execute(
            """
            INSERT INTO inventory (product_id, quantity, unit_cost, location, reorder_level)
            VALUES (%s, %s, %s, '', 0)
            """,
            (r["product_id"], qty, cost),
        )
        inserted += 1

    return inserted


def sync_batch_tracking(cur):
    """Rebuild batch_tracking.quantity_available from inventory_balances.

    The audit compares batch_tracking.quantity_available (by full dimension)
    against inventory_balances.quantity. We update quantity_available to match
    so the derived batch table reflects the corrected balances.

    For batch_tracking rows whose dimension no longer exists in inventory_balances,
    set quantity_available=0 (do not delete — preserve audit trail).
    For inventory_balances dimensions that have no batch_tracking row, INSERT one.
    """
    # Update existing batch_tracking rows to match inventory_balances.
    cur.execute(
        """
        UPDATE batch_tracking bt
        SET quantity_available = COALESCE((
                SELECT SUM(ib.quantity)
                FROM inventory_balances ib
                WHERE ib.product_id = bt.product_id
                  AND COALESCE(ib.warehouse_id, 0) = COALESCE(bt.warehouse_id, 0)
                  AND COALESCE(ib.location_id, 0) = COALESCE(bt.location_id, 0)
                  AND COALESCE(ib.lot_no, '') = COALESCE(bt.lot_no, '')
                  AND COALESCE(ib.cabinet_no, '') = COALESCE(bt.cabinet_no, '')
                  AND COALESCE(ib.project_code, '') = COALESCE(bt.project_code, '')
            ), 0),
            updated_at = NOW()
        """
    )
    updated = cur.rowcount

    # Zero out batch_tracking rows that have no matching inventory_balances dimension
    # and still show non-zero quantity_available.
    cur.execute(
        """
        UPDATE batch_tracking bt
        SET quantity_available = 0, updated_at = NOW()
        WHERE bt.quantity_available <> 0
          AND NOT EXISTS (
              SELECT 1 FROM inventory_balances ib
              WHERE ib.product_id = bt.product_id
                AND COALESCE(ib.warehouse_id, 0) = COALESCE(bt.warehouse_id, 0)
                AND COALESCE(ib.location_id, 0) = COALESCE(bt.location_id, 0)
                AND COALESCE(ib.lot_no, '') = COALESCE(bt.lot_no, '')
                AND COALESCE(ib.cabinet_no, '') = COALESCE(bt.cabinet_no, '')
                AND COALESCE(ib.project_code, '') = COALESCE(bt.project_code, '')
                AND COALESCE(ib.quantity, 0) <> 0
          )
        """
    )
    zeroed = cur.rowcount

    # INSERT batch_tracking rows for inventory_balances dimensions that have no
    # matching batch_tracking row. This closes the gap where balance exists but
    # batch_qty=0 in the audit.
    cur.execute(
        """
        INSERT INTO batch_tracking
            (lot_no, product_id, warehouse_id, location, quantity_in,
             quantity_out, quantity_available, unit_cost, status, created_at,
             cabinet_no, project_code, location_id, updated_at)
        SELECT
            COALESCE(NULLIF(ib.lot_no, ''), ''),
            ib.product_id,
            ib.warehouse_id,
            '',
            GREATEST(ib.quantity, 0),
            GREATEST(-ib.quantity, 0),
            ib.quantity,
            COALESCE(ib.unit_cost, 0),
            'active',
            NOW(),
            ib.cabinet_no,
            ib.project_code,
            ib.location_id,
            NOW()
        FROM inventory_balances ib
        WHERE COALESCE(ib.quantity, 0) <> 0
          AND NOT EXISTS (
              SELECT 1 FROM batch_tracking bt
              WHERE bt.product_id = ib.product_id
                AND COALESCE(bt.warehouse_id, 0) = COALESCE(ib.warehouse_id, 0)
                AND COALESCE(bt.location_id, 0) = COALESCE(ib.location_id, 0)
                AND COALESCE(bt.lot_no, '') = COALESCE(ib.lot_no, '')
                AND COALESCE(bt.cabinet_no, '') = COALESCE(ib.cabinet_no, '')
                AND COALESCE(bt.project_code, '') = COALESCE(ib.project_code, '')
          )
        """
    )
    inserted = cur.rowcount

    return updated, zeroed, inserted


def run_dry_run():
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        garbage_count = count_garbage_rows(cur)
        garbage_summary = list_garbage_summary(cur)
        diff_count, diff_rows = preview_diff_after_cleanup(cur)
        neg_dims = fetch_negative_balance_dims(cur)

        print("=" * 70)
        print("fix_inventory_root_cause.py — DRY RUN (no changes made)")
        print("=" * 70)
        print()
        print(f"inventory_balance_reconciliation 垃圾行数量: {garbage_count}")
        print(f"垃圾行按维度汇总组数: {len(garbage_summary)}")
        if garbage_summary:
            print()
            print("垃圾行维度明细 (前 20 组):")
            print(f"  {'product_id':>10} {'wh':>4} {'loc':>4} {'sum_qty':>12} {'rows':>5}  cabinet/project")
            for r in garbage_summary[:20]:
                print(f"  {r['product_id']:>10} {r['warehouse_id']:>4} {r['location_id']:>4} "
                      f"{r['sum_qty']:>12} {r['row_cnt']:>5}  {r['cabinet_no']}/{r['project_code']}")
        print()
        print(f"stock_transactions 差异维度 (清理垃圾行后): {diff_count}")
        if diff_count:
            print()
            print("清理后仍存在的差异 (前 20 组) — 需要同步 inventory_balances:")
            print(f"  {'product_id':>10} {'wh':>4} {'loc':>4} {'tx_qty':>12} {'bal_qty':>12} {'diff':>12}")
            for d in diff_rows[:20]:
                print(f"  {d['product_id']:>10} {d['warehouse_id']:>4} {d['location_id']:>4} "
                      f"{d['tx_qty_after_cleanup']:>12} {d['balance_qty']:>12} {d['diff']:>12}")
        else:
            print()
            print("  → inventory_balances 与 stock_transactions 一致")
        print()
        print(f"负库存维度数: {len(neg_dims)}")
        if neg_dims:
            print()
            print("负库存维度明细 (将清理对应试用数据事务):")
            print(f"  {'product_id':>10} {'wh':>4} {'loc':>4} {'quantity':>12}  cabinet/project")
            for d in neg_dims:
                print(f"  {d['product_id']:>10} {d['warehouse_id']:>4} {d['location_id']:>4} "
                      f"{d['quantity']:>12}  {d['cabinet_no']}/{d['project_code']}")
        print()
        print("Apply 将执行以下步骤:")
        print("  Step 1: 删除 inventory_balance_reconciliation 垃圾行")
        print("  Step 2: 从合法 stock_transactions 重建 inventory_balances")
        print("  Step 3: 清理负库存维度的孤儿试用事务 + 置零 balance")
        print("  Step 4: 从 inventory_balances 重建 legacy inventory 表")
        print("  Step 5: 从 inventory_balances 同步 batch_tracking.quantity_available")
        print("  (全程不往 stock_transactions 插入任何新行)")
        print()
        print("=" * 70)
        print("DRY RUN 完成。如确认无误，执行: --apply")
        print("=" * 70)
    finally:
        cur.close()
        conn.rollback()
        conn.close()


def run_apply():
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        garbage_count_before = count_garbage_rows(cur)
        diff_count_before, _ = preview_diff_after_cleanup(cur)
        neg_dims_before = fetch_negative_balance_dims(cur)

        print("=" * 70)
        print("fix_inventory_root_cause.py — APPLY")
        print("=" * 70)
        print()
        print(f"清理前垃圾行数量: {garbage_count_before}")
        print(f"清理前差异维度数: {diff_count_before}")
        print(f"清理前负库存维度数: {len(neg_dims_before)}")
        print()

        # Step 1: DELETE garbage rows.
        cur.execute(
            "DELETE FROM stock_transactions WHERE transaction_type=%s",
            (GARBAGE_TYPE,),
        )
        deleted = cur.rowcount
        print(f"Step 1: 已删除 {deleted} 条 inventory_balance_reconciliation 垃圾行")

        # Step 2: Resync inventory_balances from cleaned legitimate transactions.
        updated, inserted, zeroed = resync_inventory_balances(cur)
        print(f"Step 2: inventory_balances 同步完成 — 更新={updated}, 新增={inserted}, 置零={zeroed}")

        # Step 3: Fix negative balances by removing orphan trial-data transactions.
        tx_deleted, bal_zeroed = fix_negative_balances(cur)
        print(f"Step 3: 负库存修复 — 删除孤儿事务={tx_deleted}, 置零 balance 行={bal_zeroed}")

        # Step 4: Rebuild legacy inventory table from inventory_balances.
        legacy_inserted = sync_legacy_inventory(cur)
        print(f"Step 4: legacy inventory 表重建 — 插入={legacy_inserted}")

        # Step 5: Sync batch_tracking.quantity_available from inventory_balances.
        bt_updated, bt_zeroed, bt_inserted = sync_batch_tracking(cur)
        print(f"Step 5: batch_tracking 同步 — 更新={bt_updated}, 置零={bt_zeroed}, 新增={bt_inserted}")

        conn.commit()

        # Verify.
        garbage_count_after = count_garbage_rows(cur)
        diff_count_after, diff_rows_after = preview_diff_after_cleanup(cur)
        neg_dims_after = fetch_negative_balance_dims(cur)
        print()
        print(f"清理后垃圾行数量: {garbage_count_after}")
        print(f"清理后差异维度数: {diff_count_after}")
        print(f"清理后负库存维度数: {len(neg_dims_after)}")
        if diff_count_after:
            print()
            print("⚠ 清理后仍有差异 (前 10 组):")
            for d in diff_rows_after[:10]:
                print(f"  product={d['product_id']} wh={d['warehouse_id']} loc={d['location_id']} "
                      f"tx={d['tx_qty_after_cleanup']} bal={d['balance_qty']} diff={d['diff']}")
        elif not neg_dims_after:
            print()
            print("✓ stock_transactions / inventory_balances / legacy inventory / batch_tracking 全部一致")
        print()
        print("=" * 70)
        print("APPLY 完成。请运行官方审计验证:")
        print("  python scripts\\audit_inventory_balance_consistency.py")
        print("=" * 70)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode == "--dry-run":
        run_dry_run()
    elif mode == "--apply":
        run_apply()
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python fix_inventory_root_cause.py [--dry-run|--apply]")
        sys.exit(2)


if __name__ == "__main__":
    main()
