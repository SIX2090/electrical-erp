"""Inventory posting helpers: balance locking, weighted-average cost, and stock transactions."""
from decimal import Decimal
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)


TRUTHY_ENV_VALUES = {"1", "true", "yes", "on", "启用", "允许", "开启"}
SAFE_IDENTIFIER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _safe_identifier(value) -> str:
    text = str(value or "")
    if not text or any(ch not in SAFE_IDENTIFIER_CHARS for ch in text):
        raise ValueError(f"unsafe SQL identifier: {text!r}")
    return text


def _to_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _first_row(rows):
    if isinstance(rows, dict):
        return rows
    return rows[0] if rows else None


def _row_value(row, key=None):
    if not row:
        return None
    if isinstance(row, dict):
        return row.get(key) if key is not None else next(iter(row.values()), None)
    if isinstance(row, (list, tuple)):
        return row[0] if row else None
    return None


def _fetch_one(query_db, sql, params=()) -> Optional[dict]:
    rows = query_db(sql, params)
    return _first_row(rows)


def _env_flag(name, default=False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY_ENV_VALUES


def _allow_negative_inventory_balance(query_db=None) -> bool:
    """Read negative-stock policy from system_options first, env only as fallback."""
    env_default = _env_flag("INVENTORY_ALLOW_NEGATIVE_BALANCE", False)
    if not query_db:
        return env_default
    try:
        row = _fetch_one(
            query_db,
            """
            SELECT COALESCE(option_value, value) AS option_value
            FROM system_options
            WHERE option_key=%s OR key=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            ("allow_negative_stock", "allow_negative_stock"),
        )
    except Exception:
        return env_default
    value = (row or {}).get("option_value")
    if value is None:
        return env_default
    return str(value).strip().lower() in TRUTHY_ENV_VALUES


def ensure_inventory(query_db, execute_db, product_id, quantity=0, unit_cost=0, location="", reorder_level=0):
    rows = query_db("SELECT id FROM inventory WHERE product_id=%s LIMIT 1", (product_id,))
    row = _first_row(rows)
    if row:
        return _row_value(row, "id")
    try:
        row = query_db(
            "INSERT INTO inventory (product_id, quantity, unit_cost, location, reorder_level) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (product_id, quantity or 0, unit_cost or 0, location or "", reorder_level or 0),
            one=True,
        )
        if row:
            return _row_value(row, "id")
    except Exception as exc:
        # Concurrent insert may raise IntegrityError; fall back to SELECT.
        logger.warning("ensure_inventory concurrent insert for product_id=%s: %s", product_id, exc)
    rows = query_db("SELECT id FROM inventory WHERE product_id=%s LIMIT 1", (product_id,))
    row = _first_row(rows)
    return _row_value(row, "id") if row else None


def _sync_legacy_inventory_from_balances(query_db, execute_db, product_id, location="") -> None:
    """Keep legacy inventory table as a product-level compatibility summary."""
    ensure_inventory(query_db, execute_db, product_id, 0, 0, location, 0)
    row = _fetch_one(
        query_db,
        """
        SELECT
            COALESCE(SUM(quantity),0) AS quantity,
            CASE WHEN COALESCE(SUM(quantity),0) <> 0
                THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                ELSE COALESCE(MAX(unit_cost),0)
            END AS unit_cost
        FROM inventory_balances
        WHERE product_id=%s
        """,
        (product_id,),
    ) or {}
    execute_db(
        """
        UPDATE inventory
        SET quantity=%s, unit_cost=%s
        WHERE id = (SELECT id FROM inventory WHERE product_id=%s ORDER BY id LIMIT 1)
        """,
        (_to_decimal(row.get("quantity")), _to_decimal(row.get("unit_cost")), product_id),
    )


def _sync_batch_tracking_from_balance(query_db, execute_db, product_id, warehouse_id=None, location_id=None, lot_no="", serial_no="", project_code="", reference_no="", movement_qty=None) -> None:
    row = _fetch_one(
        query_db,
        """
        SELECT
            COALESCE(SUM(quantity),0) AS quantity,
            CASE WHEN COALESCE(SUM(quantity),0) <> 0
                THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                ELSE COALESCE(MAX(unit_cost),0)
            END AS unit_cost
        FROM inventory_balances
        WHERE product_id=%s
          AND warehouse_id IS NOT DISTINCT FROM %s
          AND location_id IS NOT DISTINCT FROM %s
          AND COALESCE(project_code,'')=%s
          AND COALESCE(lot_no,'')=%s
          AND COALESCE(serial_no,'')=%s
        """,
        (product_id, warehouse_id, location_id, project_code or "", lot_no or "", serial_no or ""),
    ) or {}
    quantity = _to_decimal(row.get("quantity"))
    unit_cost = _to_decimal(row.get("unit_cost"))
    mv_qty = _to_decimal(movement_qty) if movement_qty is not None else quantity
    batch = _fetch_one(
        query_db,
        """
        SELECT id
        FROM batch_tracking
        WHERE product_id=%s
          AND warehouse_id IS NOT DISTINCT FROM %s
          AND location_id IS NOT DISTINCT FROM %s
          AND COALESCE(project_code,'')=%s
          AND COALESCE(lot_no,'')=%s
          AND COALESCE(serial_no,'')=%s
        ORDER BY id
        LIMIT 1
        FOR UPDATE
        """,
        (product_id, warehouse_id, location_id, project_code or "", lot_no or "", serial_no or ""),
    )
    if batch:
        execute_db(
            """
            UPDATE batch_tracking
            SET quantity_available=%s,
                unit_cost=%s,
                quantity_in=CASE WHEN %s > 0 THEN COALESCE(quantity_in,0) + %s ELSE COALESCE(quantity_in,0) END,
                quantity_out=CASE WHEN %s < 0 THEN COALESCE(quantity_out,0) + (-%s) ELSE COALESCE(quantity_out,0) END,
                updated_at=NOW()
            WHERE id=%s
            """,
            (quantity, unit_cost, mv_qty, mv_qty, mv_qty, mv_qty, batch["id"]),
        )
        return
    execute_db(
        """
        INSERT INTO batch_tracking
            (lot_no, product_id, warehouse_id, location_id, serial_no, project_code,
             quantity_in, quantity_out, quantity_available, unit_cost, source_order_no,
             status, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'derived',NOW(),NOW())
        """,
        (
            lot_no or "",
            product_id,
            warehouse_id,
            location_id,
            serial_no or None,
            project_code or None,
            mv_qty if mv_qty > 0 else Decimal("0"),
            -mv_qty if mv_qty < 0 else Decimal("0"),
            quantity,
            unit_cost,
            reference_no or "inventory_balance_sync",
        ),
    )


def _ensure_inventory_balance(query_db, execute_db, product_id, lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code="") -> Optional[int]:
    balance = _fetch_one(
        query_db,
        """
        SELECT id
        FROM inventory_balances
        WHERE product_id=%s
          AND warehouse_id IS NOT DISTINCT FROM %s
          AND location_id IS NOT DISTINCT FROM %s
          AND COALESCE(project_code,'')=%s
          AND COALESCE(lot_no,'')=%s
          AND COALESCE(serial_no,'')=%s
        ORDER BY id
        LIMIT 1
        """,
        (product_id, warehouse_id, location_id, project_code or "", lot_no or "", serial_no or ""),
    )
    if balance:
        return balance["id"]
    row = _fetch_one(
        query_db,
        """
        INSERT INTO inventory_balances
            (product_id, warehouse_id, location_id, project_code, quantity, locked_qty, unit_cost, lot_no, serial_no, updated_at)
        VALUES (%s,%s,%s,%s,0,0,0,%s,%s,NOW())
        RETURNING id
        """,
        (product_id, warehouse_id, location_id, project_code or "", lot_no or "", serial_no or ""),
    )
    return _row_value(row, "id")


def lock_inventory_balance(query_db, execute_db, product_id, lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code=""):
    balance_id = _ensure_inventory_balance(query_db, execute_db, product_id, lot_no, serial_no, warehouse_id, location_id, project_code)
    return _fetch_one(
        query_db,
        """
        SELECT *
        FROM inventory_balances
        WHERE id=%s
        FOR UPDATE
        """,
        (balance_id,),
    )


def lock_inventory_balances(query_db, execute_db, balance_keys) -> list:
    """Lock a deduplicated list of inventory balances in a stable order to avoid deadlocks."""
    locked = []
    seen = set()
    normalized_keys = []
    for key in balance_keys or ():
        if isinstance(key, dict):
            product_id = key.get("product_id")
            lot_no = key.get("lot_no") or ""
            serial_no = key.get("serial_no") or ""
            warehouse_id = key.get("warehouse_id")
            location_id = key.get("location_id")
            project_code = key.get("project_code") or key.get("line_project_code") or ""
        else:
            product_id, *rest = key
            lot_no = rest[0] if len(rest) > 0 else ""
            serial_no = rest[1] if len(rest) > 1 else ""
            warehouse_id = rest[2] if len(rest) > 2 else None
            location_id = rest[3] if len(rest) > 3 else None
            project_code = rest[4] if len(rest) > 4 else ""
        normalized = (product_id, warehouse_id, location_id, project_code or "", lot_no or "", serial_no or "")
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_keys.append(normalized)
    for product_id, warehouse_id, location_id, project_code, lot_no, serial_no in sorted(normalized_keys, key=lambda row: tuple(str(v or "") for v in row)):
        locked.append(lock_inventory_balance(query_db, execute_db, product_id, lot_no, serial_no, warehouse_id, location_id, project_code))
    return locked


def _sync_inventory_balance_inbound(query_db, execute_db, product_id, quantity, unit_cost, lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code="") -> None:
    qty = _to_decimal(quantity)
    cost = _to_decimal(unit_cost)
    balance = lock_inventory_balance(query_db, execute_db, product_id, lot_no, serial_no, warehouse_id, location_id, project_code)
    balance_id = balance["id"]
    old_qty = _to_decimal(balance.get("quantity"))
    old_cost = _to_decimal(balance.get("unit_cost"))
    new_qty = old_qty + qty
    if old_qty <= 0 or new_qty <= 0:
        new_cost = cost
    else:
        new_cost = ((old_qty * old_cost) + (qty * cost)) / new_qty
    execute_db(
        """
        UPDATE inventory_balances
        SET quantity = COALESCE(quantity,0) + %s,
            unit_cost = %s,
            updated_at = NOW()
        WHERE id=%s
        """,
        (qty, new_cost, balance_id),
    )


def _sync_inventory_balance_outbound(query_db, execute_db, product_id, quantity, unit_cost, lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code="") -> None:
    qty = _to_decimal(quantity)
    cost = _to_decimal(unit_cost)
    balance = lock_inventory_balance(query_db, execute_db, product_id, lot_no, serial_no, warehouse_id, location_id, project_code)
    balance_id = balance["id"]
    if qty < 0:
        raise ValueError(f"outbound quantity must be non-negative, got {qty}")
    if _allow_negative_inventory_balance(query_db):
        logger.warning(
            "negative inventory allowed: product_id=%s, qty=%s, warehouse_id=%s, "
            "location_id=%s, project_code=%s",
            product_id, qty, warehouse_id or '', location_id or '', project_code or ''
        )
        execute_db(
            """
            UPDATE inventory_balances
            SET quantity = COALESCE(quantity,0) - %s,
                unit_cost = CASE WHEN %s <> 0 THEN %s ELSE COALESCE(unit_cost,0) END,
                updated_at = NOW()
            WHERE id=%s
            """,
            (qty, cost, cost, balance_id),
        )
        return
    row = _fetch_one(
        query_db,
        """
        UPDATE inventory_balances
        SET quantity = COALESCE(quantity,0) - %s,
            unit_cost = CASE WHEN %s <> 0 THEN %s ELSE COALESCE(unit_cost,0) END,
            updated_at = NOW()
        WHERE id=%s
          AND COALESCE(quantity,0) >= %s
        RETURNING quantity
        """,
        (qty, cost, cost, balance_id, qty),
    )
    if row:
        return
    current = _fetch_one(query_db, "SELECT COALESCE(quantity,0) AS quantity FROM inventory_balances WHERE id=%s", (balance_id,))
    available = _to_decimal((current or {}).get("quantity"))
    raise RuntimeError(
        "insufficient inventory balance: "
        f"product_id={product_id}, requested={qty}, available={available}, "
        f"warehouse_id={warehouse_id or ''}, location_id={location_id or ''}, "
        f"project_code={project_code or ''}, lot_no={lot_no or ''}, serial_no={serial_no or ''}. "
        "Set system option allow_negative_stock=1 only for approved legacy correction work."
    )


def _assert_inventory_balance_consistent(query_db, product_id) -> None:
    if os.environ.get("INVENTORY_STRICT_BALANCE_CHECK", "").strip() != "1":
        return
    row = _fetch_one(
        query_db,
        """
        SELECT
            COALESCE((SELECT quantity FROM inventory WHERE product_id=%s ORDER BY id LIMIT 1),0) AS legacy_qty,
            COALESCE((SELECT SUM(quantity) FROM inventory_balances WHERE product_id=%s),0) AS balance_qty
        """,
        (product_id, product_id),
    )
    legacy_qty = _to_decimal(row.get("legacy_qty") if row else 0)
    balance_qty = _to_decimal(row.get("balance_qty") if row else 0)
    if legacy_qty != balance_qty:
        raise RuntimeError(f"inventory balance mismatch for product_id={product_id}: legacy inventory={legacy_qty}, inventory_balances={balance_qty}")


def _ensure_product_balance_ready(query_db, execute_db, product_id, location="", lot_no="", serial_no="", project_code=""):
    legacy = _fetch_one(
        query_db,
        """
        SELECT
            COALESCE(SUM(quantity),0) AS quantity,
            CASE WHEN COALESCE(SUM(quantity),0) <> 0
                THEN COALESCE(SUM(quantity * COALESCE(unit_cost,0)) / NULLIF(SUM(quantity),0),0)
                ELSE COALESCE(MAX(unit_cost),0)
            END AS unit_cost
        FROM inventory
        WHERE product_id=%s
        """,
        (product_id,),
    )
    balance = _fetch_one(query_db, "SELECT COUNT(*) AS row_count, COALESCE(SUM(quantity),0) AS quantity FROM inventory_balances WHERE product_id=%s", (product_id,))
    if int((balance or {}).get("row_count") or 0) == 0:
        _ensure_inventory_balance(query_db, execute_db, product_id, lot_no, serial_no, project_code=project_code)
        execute_db(
            """
            UPDATE inventory_balances
            SET quantity=%s, unit_cost=%s, updated_at=NOW()
            WHERE product_id=%s
              AND warehouse_id IS NULL
              AND location_id IS NULL
              AND COALESCE(project_code,'')=%s
              AND COALESCE(lot_no,'')=%s
              AND COALESCE(serial_no,'')=%s
            """,
            (_to_decimal((legacy or {}).get("quantity")), _to_decimal((legacy or {}).get("unit_cost")), product_id, project_code or "", lot_no or "", serial_no or ""),
        )
        return
    _assert_inventory_balance_consistent(query_db, product_id)


def lock_product_inventory_rows(query_db, product_id) -> None:
    query_db("SELECT id FROM inventory WHERE product_id=%s ORDER BY id FOR UPDATE", (product_id,))


def post_inventory_change(query_db, execute_db, *, product_id, quantity, unit_cost=0, direction, location="", reference_no="", remark="", tx_date=None, tx_type="", lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code="", source_type="", source_doc_no="", source_line_no="", amount=None) -> bool:
    """Dispatch an inbound or outbound inventory posting based on direction."""
    direction = (direction or "").strip().lower()
    if direction in {"in", "inbound", "receipt", "receive"}:
        return inventory_inbound_weighted_avg(query_db, execute_db, product_id, quantity, unit_cost, location, reference_no, remark, tx_date, tx_type or "inbound", lot_no, serial_no, warehouse_id, location_id, project_code, source_type, source_doc_no, source_line_no, amount)
    if direction in {"out", "outbound", "issue", "shipment"}:
        return inventory_outbound(query_db, execute_db, product_id, quantity, location, reference_no, remark, tx_date, tx_type or "outbound", lot_no, serial_no, unit_cost, warehouse_id, location_id, project_code, source_type, source_doc_no, source_line_no, amount)
    raise ValueError(f"unsupported inventory posting direction: {direction!r}")


def post_inventory_change_with_cursor(cur, *, product_id, quantity, unit_cost=0, direction, location="", reference_no="", remark="", tx_date=None, tx_type="", lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code="", source_type="", source_doc_no="", source_line_no="", amount=None) -> bool:
    from services.transaction_utils import cursor_db_helpers

    query_db, execute_db, _execute_and_return = cursor_db_helpers(cur)
    return post_inventory_change(
        query_db,
        execute_db,
        product_id=product_id,
        quantity=quantity,
        unit_cost=unit_cost,
        direction=direction,
        location=location,
        reference_no=reference_no,
        remark=remark,
        tx_date=tx_date,
        tx_type=tx_type,
        lot_no=lot_no,
        serial_no=serial_no,
        warehouse_id=warehouse_id,
        location_id=location_id,
        project_code=project_code,
        source_type=source_type,
        source_doc_no=source_doc_no,
        source_line_no=source_line_no,
        amount=amount,
    )


def record_stock_transaction(query_db, execute_db, product_id, tx_type, quantity, location="", reference_no="", remark="", tx_date=None, unit_cost=0, lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code="", source_type="", source_doc_no="", source_line_no="", amount=None):
    qty = _to_decimal(quantity)
    cost = _to_decimal(unit_cost)
    amount_value = _to_decimal(amount) if amount is not None else qty * cost
    rows = query_db(
        """
        INSERT INTO stock_transactions
            (product_id, transaction_type, quantity, location, reference_no, remark, transaction_date,
             unit_cost, lot_no, serial_no, warehouse_id, location_id, project_code,
             source_type, source_doc_no, source_line_no, amount)
        VALUES (%s,%s,%s,%s,%s,%s,COALESCE(%s, CURRENT_DATE),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (product_id, tx_type, qty, location, reference_no, remark, tx_date, cost, lot_no or "", serial_no or "", warehouse_id, location_id, project_code or "", source_type or "", source_doc_no or reference_no or "", source_line_no or "", amount_value),
    )
    return _row_value(_first_row(rows), "id")


def resolve_outbound_unit_cost(query_db, product_id, explicit_unit_cost=0) -> Decimal:
    cost = _to_decimal(explicit_unit_cost)
    if cost != 0:
        return cost
    rows = query_db("SELECT COALESCE(unit_cost,0) AS unit_cost FROM inventory WHERE product_id=%s LIMIT 1", (product_id,))
    row = _first_row(rows)
    if not row:
        return Decimal("0")
    return _to_decimal(_row_value(row, "unit_cost"))


def inventory_inbound_weighted_avg(query_db, execute_db, product_id, quantity, unit_cost, location="", reference_no="", remark="", tx_date=None, tx_type="inbound", lot_no="", serial_no="", warehouse_id=None, location_id=None, project_code="", source_type="", source_doc_no="", source_line_no="", amount=None):
    """Post an inbound receipt using weighted-average cost across the balance."""
    ensure_inventory(query_db, execute_db, product_id, 0, 0, location, 0)
    _ensure_product_balance_ready(query_db, execute_db, product_id, location, lot_no, serial_no, project_code)
    lock_product_inventory_rows(query_db, product_id)
    qty = _to_decimal(quantity)
    cost = _to_decimal(unit_cost)
    _sync_inventory_balance_inbound(query_db, execute_db, product_id, qty, cost, lot_no, serial_no, warehouse_id, location_id, project_code)
    _sync_legacy_inventory_from_balances(query_db, execute_db, product_id, location)
    _sync_batch_tracking_from_balance(query_db, execute_db, product_id, warehouse_id, location_id, lot_no, serial_no, project_code, reference_no, movement_qty=qty)
    tx_id = record_stock_transaction(query_db, execute_db, product_id, tx_type, qty, location, reference_no, remark, tx_date, cost, lot_no, serial_no, warehouse_id, location_id, project_code, source_type, source_doc_no, source_line_no, amount)
    _assert_inventory_balance_consistent(query_db, product_id)
    return {"tx_id": tx_id}


def inventory_outbound(query_db, execute_db, product_id, quantity, location="", reference_no="", remark="", tx_date=None, tx_type="outbound", lot_no="", serial_no="", unit_cost=0, warehouse_id=None, location_id=None, project_code="", source_type="", source_doc_no="", source_line_no="", amount=None):
    """Post an outbound issue, decreasing balance with negative-stock protection."""
    ensure_inventory(query_db, execute_db, product_id, 0, 0, location, 0)
    _ensure_product_balance_ready(query_db, execute_db, product_id, location, lot_no, serial_no, project_code)
    lock_product_inventory_rows(query_db, product_id)
    qty = _to_decimal(quantity)
    cost = resolve_outbound_unit_cost(query_db, product_id, unit_cost)
    _sync_inventory_balance_outbound(query_db, execute_db, product_id, qty, cost, lot_no, serial_no, warehouse_id, location_id, project_code)
    _sync_legacy_inventory_from_balances(query_db, execute_db, product_id, location)
    _sync_batch_tracking_from_balance(query_db, execute_db, product_id, warehouse_id, location_id, lot_no, serial_no, project_code, reference_no, movement_qty=-qty)
    tx_id = record_stock_transaction(query_db, execute_db, product_id, tx_type, -qty, location, reference_no, remark, tx_date, cost, lot_no, serial_no, warehouse_id, location_id, project_code, source_type, source_doc_no, source_line_no, amount)
    _assert_inventory_balance_consistent(query_db, product_id)
    return {"tx_id": tx_id}


def ensure_document_sequence_schema(execute_db) -> None:
    """Create the document_sequences table if it does not yet exist."""
    execute_db(
        """
        CREATE TABLE IF NOT EXISTS document_sequences (
            prefix VARCHAR(40) NOT NULL,
            scope VARCHAR(80) NOT NULL DEFAULT '',
            last_value INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (prefix, scope)
        )
        """
    )


def _extract_plain_sequence_value(doc_no, prefix) -> int:
    text = str(doc_no or "").strip()
    if not text.startswith(prefix):
        return 0
    suffix = text[len(prefix):]
    if not suffix.isdigit():
        return 0
    return int(suffix or "0")


def _code_rule_date_part(date_format) -> str:
    from datetime import datetime

    fmt = str(date_format or "").strip().upper()
    if fmt in {"", "NONE", "NO_DATE"}:
        return ""
    if fmt == "YYYYMM":
        return f"{datetime.now():%Y%m}"
    if fmt == "YYMMDD":
        return f"{datetime.now():%y%m%d}"
    return f"{datetime.now():%Y%m%d}"


def _active_document_number_rule(query_db, prefix, table, field):
    try:
        rows = query_db(
            """
            SELECT *
            FROM erp_code_rules
            WHERE target_type='document'
              AND is_active=TRUE
              AND rule_key IN (%s, %s)
            ORDER BY CASE WHEN rule_key=%s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (f"document:{table}.{field}", f"document:{prefix}", f"document:{table}.{field}"),
        )
    except Exception:
        return None
    return _first_row(rows)


def _document_rule_base(rule) -> str:
    prefix = str((rule or {}).get("prefix") or "").strip().upper()
    separator = str((rule or {}).get("separator") or "").strip()[:4]
    date_part = _code_rule_date_part((rule or {}).get("date_format"))
    if separator:
        parts = [part for part in (prefix, date_part) if part]
        return separator.join(parts) + separator
    return f"{prefix}{date_part}"


def _next_sequence_value(query_db, execute_and_return, table, field, base, sequence_scope):
    rows = query_db(
        f"SELECT {field} FROM {table} WHERE {field} LIKE %s ORDER BY {field} DESC LIMIT 1",
        (f"{base}%",),
    )
    existing_value = 0
    existing = _first_row(rows)
    if existing:
        current = _row_value(existing, field) or ""
        existing_value = _extract_plain_sequence_value(current, base)
    row = execute_and_return(
        """
        INSERT INTO document_sequences (prefix, scope, last_value, updated_at)
        VALUES (%s,%s,%s,NOW())
        ON CONFLICT (prefix, scope) DO UPDATE
        SET last_value=GREATEST(document_sequences.last_value, EXCLUDED.last_value) + 1,
            updated_at=NOW()
        RETURNING last_value
        """,
        (base, sequence_scope or "", existing_value + 1),
    )
    if not row:
        return 1
    last_value = _row_value(row, "last_value")
    return int(last_value or 1)


def get_next_doc_no(query_db, prefix, table, field="order_no", execute_and_return=None, scope="") -> str:
    """Return the next document number for a prefix, using a sequence table when available."""
    table = _safe_identifier(table)
    field = _safe_identifier(field)
    rule = _active_document_number_rule(query_db, prefix, table, field)
    if rule:
        base = _document_rule_base(rule)
        if not base:
            base = str(prefix or "").strip().upper()
        try:
            sequence_length = int(_row_value(rule, "sequence_length") or 4) if not isinstance(rule, dict) else int(rule.get("sequence_length") or 4)
        except (TypeError, ValueError):
            sequence_length = 4
        sequence_length = max(2, min(sequence_length, 8))
        reset_scope = (_row_value(rule, "reset_scope") if not isinstance(rule, dict) else rule.get("reset_scope")) or "daily"
        sequence_scope = scope or f"{table}.{field}"
        if str(reset_scope).lower() == "continuous":
            sequence_scope = f"{sequence_scope}:continuous"
        if execute_and_return:
            last_value = _next_sequence_value(query_db, execute_and_return, table, field, base, sequence_scope)
            return f"{base}{last_value:0{sequence_length}d}"
        rows = query_db(f"SELECT {field} FROM {table} WHERE {field} LIKE %s ORDER BY {field} DESC LIMIT 1", (f"{base}%",))
        row = _first_row(rows)
        if not row:
            return f"{base}{1:0{sequence_length}d}"
        current = _row_value(row, field) or ""
        next_no = _extract_plain_sequence_value(current, base) + 1
        return f"{base}{next_no:0{sequence_length}d}"
    if execute_and_return:
        rows = query_db(f"SELECT {field} FROM {table} WHERE {field} LIKE %s ORDER BY {field} DESC LIMIT 1", (f"{prefix}%",))
        existing_value = 0
        existing = _first_row(rows)
        if existing:
            current = _row_value(existing, field) or ""
            existing_value = _extract_plain_sequence_value(current, prefix)
        row = execute_and_return(
            """
            INSERT INTO document_sequences (prefix, scope, last_value, updated_at)
            VALUES (%s,%s,%s,NOW())
            ON CONFLICT (prefix, scope) DO UPDATE
            SET last_value=GREATEST(document_sequences.last_value, EXCLUDED.last_value) + 1,
                updated_at=NOW()
            RETURNING last_value
            """,
            (prefix, scope or "", existing_value + 1),
        )
        if not row:
            return f"{prefix}0001"
        last_value = _row_value(row, "last_value")
        if last_value is None:
            return f"{prefix}0001"
        return f"{prefix}{int(last_value):04d}"
    rows = query_db(f"SELECT {field} FROM {table} WHERE {field} LIKE %s ORDER BY {field} DESC LIMIT 1", (f"{prefix}%",))
    row = _first_row(rows)
    if not row:
        return f"{prefix}0001"
    current = _row_value(row, field) or ""
    next_no = _extract_plain_sequence_value(current, prefix) + 1
    return f"{prefix}{next_no:04d}"
