"""
P0-BLK-01 库存三重独立校验脚本
==============================================
执行环境  : Windows Server，Python 3.10+，需激活 .venv
执行权限  : 只读，不修改任何数据
执行方式  : .venv\Scripts\python.exe scripts\p0_blk01_inventory_triple_check.py
依赖      : 完全独立于原 audit_inventory_batch_balance.py，不共享任何逻辑

三重校验说明
  CHECK-A : batch_tracking 与 inventory_balances 按6维度全量 FULL OUTER JOIN
  CHECK-B : 负库存检测（quantity_available < 0 或 quantity < 0）
  CHECK-C : 批次追踪总量与库存余额总量的汇总一致性（全局加法校验）

输出格式 : 每行以 ✅ PASS 或 ❌ FAIL 开头，无需人工判断
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# ── 路径设置（独立于原脚本，不复用 audit_inventory_batch_balance.py 任何代码）──
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"p0_blk01_triple_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

_log_lines: list[str] = []


def _w(line: str = "") -> None:
    """同时输出到控制台和日志文件。"""
    print(line)
    _log_lines.append(line)


def _flush_log() -> None:
    LOG_FILE.write_text("\n".join(_log_lines), encoding="utf-8")


# ── 加载环境变量（与原脚本同源，但独立调用）──────────────────────────────────
def _load_cmd_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith(("@", "::")) or line.lower().startswith("rem "):
            continue
        if not line.lower().startswith("set "):
            continue
        payload = line[4:].strip().strip('"')
        if "=" not in payload:
            continue
        k, v = payload.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_cmd_env(ROOT / "runtime_env.cmd")
_load_cmd_env(ROOT / "runtime_local_secrets.cmd")

# ── 数据库连接（直接使用 psycopg2，不依赖 app_runtime.connect_db）──────────────
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    _w("❌ FAIL [环境] psycopg2 未安装，请确认已激活 .venv")
    _flush_log()
    sys.exit(1)

DB_CFG = {
    "host":     os.environ.get("PG_HOST",     "127.0.0.1"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "dbname":   os.environ.get("PG_DATABASE", "wms"),
    "user":     os.environ.get("PG_USER",     "wms_user"),
    "password": os.environ.get("PG_PASSWORD", ""),
}


def _connect():
    return psycopg2.connect(
        **DB_CFG,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=10,
        options="-c client_encoding=UTF8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHECK-A : 6维度 FULL OUTER JOIN 差异检测
# ─────────────────────────────────────────────────────────────────────────────
CHECK_A_SQL = """
WITH
batch AS (
    SELECT
        product_id,
        COALESCE(warehouse_id,  0)  AS warehouse_id,
        COALESCE(location_id,   0)  AS location_id,
        COALESCE(lot_no,       '')  AS lot_no,
        COALESCE(serial_no,    '')  AS serial_no,
        COALESCE(project_code, '')  AS project_code,
        SUM(COALESCE(quantity_available, 0)) AS batch_qty
    FROM batch_tracking
    GROUP BY
        product_id,
        COALESCE(warehouse_id,  0),
        COALESCE(location_id,   0),
        COALESCE(lot_no,       ''),
        COALESCE(serial_no,    ''),
        COALESCE(project_code, '')
),
balance AS (
    SELECT
        product_id,
        COALESCE(warehouse_id,  0)  AS warehouse_id,
        COALESCE(location_id,   0)  AS location_id,
        COALESCE(lot_no,       '')  AS lot_no,
        COALESCE(serial_no,    '')  AS serial_no,
        COALESCE(project_code, '')  AS project_code,
        SUM(COALESCE(quantity, 0)) AS balance_qty
    FROM inventory_balances
    GROUP BY
        product_id,
        COALESCE(warehouse_id,  0),
        COALESCE(location_id,   0),
        COALESCE(lot_no,       ''),
        COALESCE(serial_no,    ''),
        COALESCE(project_code, '')
)
SELECT
    COALESCE(b.product_id,    i.product_id)    AS product_id,
    COALESCE(b.warehouse_id,  i.warehouse_id)  AS warehouse_id,
    COALESCE(b.location_id,   i.location_id)   AS location_id,
    COALESCE(b.lot_no,        i.lot_no)         AS lot_no,
    COALESCE(b.serial_no,     i.serial_no)      AS serial_no,
    COALESCE(b.project_code,  i.project_code)   AS project_code,
    COALESCE(b.batch_qty,   0)                  AS batch_qty,
    COALESCE(i.balance_qty, 0)                  AS balance_qty,
    COALESCE(b.batch_qty, 0) - COALESCE(i.balance_qty, 0) AS diff_qty
FROM batch b
FULL OUTER JOIN balance i
    ON  b.product_id   IS NOT DISTINCT FROM i.product_id
    AND b.warehouse_id = i.warehouse_id
    AND b.location_id  = i.location_id
    AND b.lot_no       = i.lot_no
    AND b.serial_no    = i.serial_no
    AND b.project_code = i.project_code
WHERE
    COALESCE(b.batch_qty, 0) <> COALESCE(i.balance_qty, 0)
ORDER BY ABS(COALESCE(b.batch_qty, 0) - COALESCE(i.balance_qty, 0)) DESC
LIMIT 500
"""

# ─────────────────────────────────────────────────────────────────────────────
# CHECK-B : 负库存检测
# ─────────────────────────────────────────────────────────────────────────────
CHECK_B_BATCH_SQL = """
SELECT product_id, warehouse_id, location_id, lot_no, serial_no, project_code,
       SUM(quantity_available) AS total_qty
FROM batch_tracking
GROUP BY product_id, warehouse_id, location_id, lot_no, serial_no, project_code
HAVING SUM(quantity_available) < 0
ORDER BY SUM(quantity_available)
LIMIT 200
"""

CHECK_B_BALANCE_SQL = """
SELECT product_id, warehouse_id, location_id, lot_no, serial_no, project_code,
       SUM(quantity) AS total_qty
FROM inventory_balances
GROUP BY product_id, warehouse_id, location_id, lot_no, serial_no, project_code
HAVING SUM(quantity) < 0
ORDER BY SUM(quantity)
LIMIT 200
"""

# ─────────────────────────────────────────────────────────────────────────────
# CHECK-C : 全局总量一致性（加法校验）
# ─────────────────────────────────────────────────────────────────────────────
CHECK_C_SQL = """
SELECT
    (SELECT COALESCE(SUM(quantity_available), 0) FROM batch_tracking)      AS total_batch_qty,
    (SELECT COALESCE(SUM(quantity),           0) FROM inventory_balances)  AS total_balance_qty,
    (SELECT COUNT(*)                             FROM batch_tracking)      AS batch_rows,
    (SELECT COUNT(*)                             FROM inventory_balances)  AS balance_rows
"""


def run_checks() -> int:
    """执行三重校验，返回失败项数量（0 = 全部通过）。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _w("=" * 70)
    _w(f"  P0-BLK-01 库存三重独立校验")
    _w(f"  执行时间 : {ts}")
    _w(f"  数据库   : {DB_CFG['dbname']}@{DB_CFG['host']}:{DB_CFG['port']}")
    _w("=" * 70)

    fail_count = 0

    try:
        conn = _connect()
    except Exception as exc:
        _w(f"❌ FAIL [连接] 无法连接数据库: {exc}")
        _flush_log()
        return 99

    try:
        with conn.cursor() as cur:

            # ── 表/列存在性预检 ────────────────────────────────────────────
            _w("\n── 前置检查：表与关键列 ─────────────────────────────────────")
            for tbl, col in [
                ("batch_tracking",    "quantity_available"),
                ("inventory_balances","quantity"),
            ]:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=%s AND column_name=%s",
                    (tbl, col),
                )
                if cur.fetchone():
                    _w(f"✅ PASS [预检] {tbl}.{col} 存在")
                else:
                    _w(f"❌ FAIL [预检] {tbl}.{col} 不存在——后续校验可能失败")
                    fail_count += 1

            # ── CHECK-C 全局总量（最快，先跑）────────────────────────────
            _w("\n── CHECK-C : 全局总量一致性 ─────────────────────────────────")
            cur.execute(CHECK_C_SQL)
            c = cur.fetchone()
            total_batch   = float(c["total_batch_qty"])
            total_balance = float(c["total_balance_qty"])
            diff_total    = round(total_batch - total_balance, 6)
            _w(f"   batch_tracking 总行数     : {c['batch_rows']}")
            _w(f"   inventory_balances 总行数 : {c['balance_rows']}")
            _w(f"   batch_tracking 总quantity_available : {total_batch}")
            _w(f"   inventory_balances 总quantity       : {total_balance}")
            _w(f"   全局差异                            : {diff_total}")
            if diff_total == 0:
                _w("✅ PASS [CHECK-C] 全局总量一致")
            else:
                _w(f"❌ FAIL [CHECK-C] 全局总量差异 = {diff_total}，存在未对账数量")
                fail_count += 1

            # ── CHECK-A 6维度 FULL OUTER JOIN ─────────────────────────────
            _w("\n── CHECK-A : 6维度明细差异 ──────────────────────────────────")
            cur.execute(CHECK_A_SQL)
            diffs = cur.fetchall()
            if not diffs:
                _w("✅ PASS [CHECK-A] 6维度全量比对无差异（0行）")
            else:
                _w(f"❌ FAIL [CHECK-A] 发现 {len(diffs)} 行差异（最多显示500行）：")
                fail_count += 1
                _w(f"   {'product_id':>10} {'warehouse':>9} {'location':>8} "
                   f"{'lot_no':>12} {'serial_no':>12} {'project':>10} "
                   f"{'batch_qty':>12} {'balance_qty':>12} {'diff_qty':>12}")
                _w("   " + "-" * 95)
                for row in diffs:
                    _w(
                        f"   {str(row['product_id']):>10} "
                        f"{str(row['warehouse_id']):>9} "
                        f"{str(row['location_id']):>8} "
                        f"{str(row['lot_no']):>12} "
                        f"{str(row['serial_no']):>12} "
                        f"{str(row['project_code']):>10} "
                        f"{float(row['batch_qty']):>12.3f} "
                        f"{float(row['balance_qty']):>12.3f} "
                        f"{float(row['diff_qty']):>12.3f}"
                    )

            # ── CHECK-B 负库存 ─────────────────────────────────────────────
            _w("\n── CHECK-B : 负库存检测 ─────────────────────────────────────")
            cur.execute(CHECK_B_BATCH_SQL)
            neg_batch = cur.fetchall()
            cur.execute(CHECK_B_BALANCE_SQL)
            neg_balance = cur.fetchall()

            if not neg_batch:
                _w("✅ PASS [CHECK-B-1] batch_tracking 无负库存")
            else:
                _w(f"❌ FAIL [CHECK-B-1] batch_tracking 存在 {len(neg_batch)} 条负库存记录：")
                fail_count += 1
                for row in neg_batch:
                    _w(f"   product_id={row['product_id']} warehouse={row['warehouse_id']} "
                       f"lot_no={row['lot_no']!r} qty={float(row['total_qty']):.3f}")

            if not neg_balance:
                _w("✅ PASS [CHECK-B-2] inventory_balances 无负库存")
            else:
                _w(f"❌ FAIL [CHECK-B-2] inventory_balances 存在 {len(neg_balance)} 条负库存记录：")
                fail_count += 1
                for row in neg_balance:
                    _w(f"   product_id={row['product_id']} warehouse={row['warehouse_id']} "
                       f"lot_no={row['lot_no']!r} qty={float(row['total_qty']):.3f}")

    finally:
        conn.close()

    # ── 汇总 ────────────────────────────────────────────────────────────────
    _w("\n" + "=" * 70)
    if fail_count == 0:
        _w("✅ PASS [汇总] 三重校验全部通过，库存数据一致")
    else:
        _w(f"❌ FAIL [汇总] {fail_count} 项校验失败，需执行修复脚本")
    _w(f"  日志已保存: {LOG_FILE}")
    _w("=" * 70)

    _flush_log()
    return fail_count


if __name__ == "__main__":
    raise SystemExit(0 if run_checks() == 0 else 1)
