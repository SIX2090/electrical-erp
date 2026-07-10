from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    from psycopg2.extras import Json as _Psycopg2Json
except Exception:  # pragma: no cover - fallback when psycopg2 unavailable
    _Psycopg2Json = None


def _json_value(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _as_dict(row) -> Dict[str, Any]:
    return dict(row or {})


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_jsonb(value):
    if _Psycopg2Json is not None:
        return _Psycopg2Json(value)
    return json.dumps(value, ensure_ascii=False, default=str)


def _decimal_to_str(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return f"{value:f}"
    return str(value)


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a DB row dict into a JSON-safe dict."""
    result: Dict[str, Any] = {}
    for key, value in (row or {}).items():
        if isinstance(value, Decimal):
            result[key] = _decimal_to_str(value)
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def _load_work_order(query_db, work_order_id: int) -> Dict[str, Any]:
    row = query_db(
        """
        SELECT wo.id, wo.wo_no, wo.product_id, wo.bom_id,
               wo.project_code, wo.cabinet_no, wo.status, wo.quantity,
               p.code AS product_code, p.name AS product_name,
               p.specification AS product_specification, p.unit AS product_unit,
               b.bom_no, b.version AS bom_version
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        WHERE wo.id=%s
        """,
        (int(work_order_id),),
        one=True,
    )
    return _as_dict(row)


def _load_bom_header(query_db, bom_id) -> Dict[str, Any]:
    if not bom_id:
        return {}
    row = query_db(
        """
        SELECT b.id, b.bom_no, b.version, b.status, b.bom_type,
               b.effective_date, b.expiry_date, b.remark,
               b.product_id, p.code AS product_code, p.name AS product_name,
               p.specification AS product_specification, p.unit AS product_unit
        FROM boms b
        LEFT JOIN products p ON p.id=b.product_id
        WHERE b.id=%s
        """,
        (int(bom_id),),
        one=True,
    )
    return _as_dict(row)


def _load_bom_items(query_db, bom_id) -> List[Dict[str, Any]]:
    if not bom_id:
        return []
    rows = query_db(
        """
        SELECT bi.id AS bom_item_id, bi.product_id,
               bi.quantity AS base_qty, bi.loss_rate, bi.unit AS material_unit,
               bi.remark, bi.is_optional,
               p.code AS material_code, p.name AS material_name,
               p.specification AS material_spec, p.standard_price
        FROM bom_items bi
        LEFT JOIN products p ON p.id=bi.product_id
        WHERE bi.bom_id=%s
        ORDER BY bi.id
        """,
        (int(bom_id),),
    )
    return [_as_dict(row) for row in rows or []]


def _load_routing_header(query_db, routing_id) -> Dict[str, Any]:
    if not routing_id:
        return {}
    row = query_db(
        """
        SELECT pr.id, pr.routing_no, pr.product_id, pr.status, pr.remark
        FROM production_routings pr
        WHERE pr.id=%s
        """,
        (int(routing_id),),
        one=True,
    )
    return _as_dict(row)


def _load_routing_operations(query_db, routing_id) -> List[Dict[str, Any]]:
    if not routing_id:
        return []
    rows = query_db(
        """
        SELECT ro.id, ro.routing_id, ro.sequence, ro.work_center_id,
               ro.operation_name, ro.standard_time, ro.setup_time,
               ro.is_active, ro.remark,
               wc.code AS work_center_code, wc.name AS work_center_name
        FROM routing_operations ro
        LEFT JOIN work_centers wc ON wc.id=ro.work_center_id
        WHERE ro.routing_id=%s
          AND COALESCE(ro.is_active, TRUE)=TRUE
        ORDER BY ro.sequence, ro.id
        """,
        (int(routing_id),),
    )
    return [_as_dict(row) for row in rows or []]


def _load_drawings_for_order(query_db, order: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = query_db(
        """
        SELECT d.id AS drawing_id, d.drawing_no, d.version, d.status,
               d.drawing_name, d.drawing_type, d.effective_date, d.obsolete_date,
               d.release_no, d.approved_by, d.approval_date,
               d.file_location, d.checksum,
               dl.product_id, dl.bom_id, dl.project_code, dl.cabinet_no, dl.usage_scope
        FROM engineering_drawings d
        LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
        WHERE d.status='released'
          AND (
                dl.product_id=%s OR dl.bom_id=%s
                OR (COALESCE(%s, '')<>'' AND COALESCE(dl.project_code, '')=COALESCE(%s, ''))
                OR (COALESCE(%s, '')<>'' AND COALESCE(dl.cabinet_no, '')=COALESCE(%s, ''))
          )
        ORDER BY d.id DESC
        LIMIT 50
        """,
        (
            order.get("product_id"),
            order.get("bom_id"),
            order.get("project_code"),
            order.get("project_code"),
            order.get("cabinet_no"),
            order.get("cabinet_no"),
        ),
    )
    return [_as_dict(row) for row in rows or []]


def _resolve_bom_version_id(query_db, work_order: Dict[str, Any], bom_version_id) -> Optional[int]:
    if bom_version_id:
        return _to_int(bom_version_id)
    from services.bom_version_service import get_active_version

    active = get_active_version(query_db, work_order.get("bom_id"))
    if active:
        return active.get("id")
    return None


def create_bom_snapshot(
    query_db,
    execute_db,
    execute_and_return,
    work_order_id: int,
    bom_version_id=None,
) -> Optional[Dict[str, Any]]:
    """Snapshot the BOM (header + items) into work_order_bom_snapshots as JSONB."""
    work_order_id = _to_int(work_order_id)
    if not work_order_id:
        return None
    order = _load_work_order(query_db, work_order_id)
    if not order:
        return None
    bom_id = order.get("bom_id")
    if not bom_id:
        return None
    resolved_version_id = _resolve_bom_version_id(query_db, order, bom_version_id)
    header = _load_bom_header(query_db, bom_id)
    items = _load_bom_items(query_db, bom_id)
    payload = {
        "work_order_id": work_order_id,
        "work_order_no": order.get("wo_no"),
        "bom_id": bom_id,
        "bom_version_id": resolved_version_id,
        "bom_header": _serialize_row(header),
        "bom_items": [_serialize_row(item) for item in items],
        "project_code": order.get("project_code"),
        "cabinet_no": order.get("cabinet_no"),
    }
    row = execute_and_return(
        """
        INSERT INTO work_order_bom_snapshots (work_order_id, bom_version_id, snapshot_json)
        VALUES (%s, %s, %s)
        RETURNING id, work_order_id, bom_version_id, snapshot_json, created_at
        """,
        (work_order_id, resolved_version_id, _to_jsonb(payload)),
    )
    if not row:
        return None
    result = _as_dict(row)
    result["snapshot_json"] = _json_value(result.get("snapshot_json"), {})
    return result


def create_process_snapshot(
    query_db,
    execute_db,
    execute_and_return,
    work_order_id: int,
    routing_id=None,
) -> Optional[Dict[str, Any]]:
    """Snapshot the routing operations into work_order_process_snapshots."""
    work_order_id = _to_int(work_order_id)
    if not work_order_id:
        return None
    order = _load_work_order(query_db, work_order_id)
    if not order:
        return None
    resolved_routing_id = _to_int(routing_id) or _to_int(order.get("routing_id"))
    if not resolved_routing_id:
        return None
    header = _load_routing_header(query_db, resolved_routing_id)
    operations = _load_routing_operations(query_db, resolved_routing_id)
    payload = {
        "work_order_id": work_order_id,
        "work_order_no": order.get("wo_no"),
        "routing_id": resolved_routing_id,
        "routing_header": _serialize_row(header),
        "routing_operations": [_serialize_row(op) for op in operations],
        "project_code": order.get("project_code"),
        "cabinet_no": order.get("cabinet_no"),
    }
    row = execute_and_return(
        """
        INSERT INTO work_order_process_snapshots (work_order_id, route_version_id, snapshot_json)
        VALUES (%s, %s, %s)
        RETURNING id, work_order_id, route_version_id, snapshot_json, created_at
        """,
        (work_order_id, resolved_routing_id, _to_jsonb(payload)),
    )
    if not row:
        return None
    result = _as_dict(row)
    result["snapshot_json"] = _json_value(result.get("snapshot_json"), {})
    return result


def create_drawing_snapshot(
    query_db,
    execute_db,
    execute_and_return,
    work_order_id: int,
    drawings=None,
) -> Optional[Dict[str, Any]]:
    """Snapshot drawings into work_order_drawing_snapshots."""
    work_order_id = _to_int(work_order_id)
    if not work_order_id:
        return None
    order = _load_work_order(query_db, work_order_id)
    if not order:
        return None
    drawing_rows = drawings
    if drawing_rows is None:
        drawing_rows = _load_drawings_for_order(query_db, order)
    drawing_version_id = None
    if drawing_rows:
        first = drawing_rows[0]
        drawing_version_id = _to_int(first.get("drawing_id"))
    payload = {
        "work_order_id": work_order_id,
        "work_order_no": order.get("wo_no"),
        "drawing_version_id": drawing_version_id,
        "drawings": [_serialize_row(d) for d in (drawing_rows or [])],
        "project_code": order.get("project_code"),
        "cabinet_no": order.get("cabinet_no"),
    }
    row = execute_and_return(
        """
        INSERT INTO work_order_drawing_snapshots (work_order_id, drawing_version_id, snapshot_json)
        VALUES (%s, %s, %s)
        RETURNING id, work_order_id, drawing_version_id, snapshot_json, created_at
        """,
        (work_order_id, drawing_version_id, _to_jsonb(payload)),
    )
    if not row:
        return None
    result = _as_dict(row)
    result["snapshot_json"] = _json_value(result.get("snapshot_json"), {})
    return result


def get_work_order_snapshots(query_db, work_order_id: int) -> Dict[str, Any]:
    """Get all snapshots for a work order."""
    work_order_id = _to_int(work_order_id)
    if not work_order_id:
        return {"work_order": None, "bom_snapshots": [], "process_snapshots": [], "drawing_snapshots": []}
    order = _load_work_order(query_db, work_order_id)
    bom_rows = query_db(
        """
        SELECT id, work_order_id, bom_version_id, snapshot_json, created_at
        FROM work_order_bom_snapshots
        WHERE work_order_id=%s
        ORDER BY id DESC
        """,
        (work_order_id,),
    )
    process_rows = query_db(
        """
        SELECT id, work_order_id, route_version_id, snapshot_json, created_at
        FROM work_order_process_snapshots
        WHERE work_order_id=%s
        ORDER BY id DESC
        """,
        (work_order_id,),
    )
    drawing_rows = query_db(
        """
        SELECT id, work_order_id, drawing_version_id, snapshot_json, created_at
        FROM work_order_drawing_snapshots
        WHERE work_order_id=%s
        ORDER BY id DESC
        """,
        (work_order_id,),
    )
    bom_snapshots = []
    for row in bom_rows or []:
        item = _as_dict(row)
        item["snapshot_json"] = _json_value(item.get("snapshot_json"), {})
        bom_snapshots.append(item)
    process_snapshots = []
    for row in process_rows or []:
        item = _as_dict(row)
        item["snapshot_json"] = _json_value(item.get("snapshot_json"), {})
        process_snapshots.append(item)
    drawing_snapshots = []
    for row in drawing_rows or []:
        item = _as_dict(row)
        item["snapshot_json"] = _json_value(item.get("snapshot_json"), {})
        drawing_snapshots.append(item)
    return {
        "work_order": order,
        "bom_snapshots": bom_snapshots,
        "process_snapshots": process_snapshots,
        "drawing_snapshots": drawing_snapshots,
    }


def compare_bom_snapshot_to_current(query_db, work_order_id: int) -> Dict[str, Any]:
    """Compare the latest BOM snapshot to the current BOM and return differences."""
    work_order_id = _to_int(work_order_id)
    if not work_order_id:
        return {"snapshot": None, "current": None, "added": [], "removed": [], "changed": []}
    order = _load_work_order(query_db, work_order_id)
    if not order:
        return {"snapshot": None, "current": None, "added": [], "removed": [], "changed": []}
    snapshot_row = query_db(
        """
        SELECT id, snapshot_json, created_at
        FROM work_order_bom_snapshots
        WHERE work_order_id=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (work_order_id,),
        one=True,
    )
    if not snapshot_row:
        return {"snapshot": None, "current": None, "added": [], "removed": [], "changed": []}
    snapshot_data = _json_value(_as_dict(snapshot_row).get("snapshot_json"), {})
    snapshot_items = snapshot_data.get("bom_items") or []
    snapshot_map: Dict[str, Dict[str, Any]] = {}
    for item in snapshot_items:
        product_id = item.get("product_id")
        if product_id is not None:
            snapshot_map[str(product_id)] = item
    current_items = _load_bom_items(query_db, order.get("bom_id"))
    current_map: Dict[str, Dict[str, Any]] = {}
    for item in current_items:
        product_id = item.get("product_id")
        if product_id is not None:
            current_map[str(product_id)] = item
    added: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    for product_id, current_item in current_map.items():
        if product_id not in snapshot_map:
            added.append(_serialize_row(current_item))
            continue
        snapshot_item = snapshot_map[product_id]
        diffs: Dict[str, Any] = {}
        for field in ("base_qty", "loss_rate", "material_unit", "remark", "is_optional"):
            snap_val = snapshot_item.get(field)
            cur_val = current_item.get(field)
            if _decimal_to_str(snap_val) != _decimal_to_str(cur_val) and snap_val != cur_val:
                diffs[field] = {"snapshot": snap_val, "current": cur_val}
        if diffs:
            changed.append({
                "product_id": product_id,
                "material_code": current_item.get("material_code"),
                "material_name": current_item.get("material_name"),
                "differences": diffs,
            })
    for product_id, snapshot_item in snapshot_map.items():
        if product_id not in current_map:
            removed.append(_serialize_row(snapshot_item))
    return {
        "snapshot": _as_dict(snapshot_row),
        "current_bom_id": order.get("bom_id"),
        "added": added,
        "removed": removed,
        "changed": changed,
    }
