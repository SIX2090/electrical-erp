from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.trace_engine import create_trace_snapshot


WORK_ORDER_EXECUTION_SNAPSHOT_EVENT = "work_order_execution"


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _as_dict(row) -> Dict[str, Any]:
    return dict(row or {})


def _json_value(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _load_work_order(query_one, work_order_id):
    return _as_dict(
        query_one(
            """
            SELECT wo.*, p.code AS product_code, p.name AS product_name,
                   p.specification AS product_specification, p.unit AS product_unit,
                   b.bom_no, b.version AS bom_version, b.status AS bom_status
            FROM work_orders wo
            LEFT JOIN products p ON p.id=wo.product_id
            LEFT JOIN boms b ON b.id=wo.bom_id
            WHERE wo.id=%s
            """,
            (work_order_id,),
        )
    )


def _load_bom_header(query_one, bom_id):
    if not bom_id:
        return {}
    return _as_dict(
        query_one(
            """
            SELECT b.*, p.code AS product_code, p.name AS product_name,
                   p.specification AS product_specification, p.unit AS product_unit
            FROM boms b
            LEFT JOIN products p ON p.id=b.product_id
            WHERE b.id=%s
            """,
            (bom_id,),
        )
    )


def _load_bom_lines(query_rows, bom_id):
    if not bom_id:
        return []
    rows = query_rows(
        """
        SELECT bi.id AS bom_item_id, bi.product_id,
               COALESCE(bi.quantity, 0) AS base_qty,
               COALESCE(bi.loss_rate, 0) AS loss_rate,
               COALESCE(bi.unit, p.unit, '') AS material_unit,
               bi.remark,
               p.code AS material_code, p.name AS material_name,
               p.specification AS material_spec, p.standard_price,
               bi.is_optional
        FROM bom_items bi
        LEFT JOIN products p ON p.id=bi.product_id
        WHERE bi.bom_id=%s
        ORDER BY bi.id
        """,
        (bom_id,),
    )
    return [dict(row) for row in rows or []]


def _load_routing_header(query_one, order):
    routing = query_one(
        """
        SELECT pr.*
        FROM engineering_technical_confirmations etc
        JOIN production_routings pr ON pr.id=etc.routing_id
        WHERE etc.routing_id IS NOT NULL
          AND (%s IS NULL OR etc.product_id=%s)
          AND (%s IS NULL OR etc.bom_id=%s)
          AND (COALESCE(%s, '')='' OR COALESCE(etc.project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(etc.serial_no, '')=COALESCE(%s, ''))
        ORDER BY etc.confirm_date DESC NULLS LAST, etc.id DESC
        LIMIT 1
        """,
        (
            order.get("product_id"),
            order.get("product_id"),
            order.get("bom_id"),
            order.get("bom_id"),
            order.get("project_code"),
            order.get("project_code"),
            order.get("serial_no"),
            order.get("serial_no"),
        ),
    )
    if routing:
        return dict(routing)
    return _as_dict(
        query_one(
            """
            SELECT *
            FROM production_routings
            WHERE product_id=%s
              AND COALESCE(is_active, TRUE)=TRUE
            ORDER BY id DESC
            LIMIT 1
            """,
            (order.get("product_id"),),
        )
    )


def _load_routing_operations(query_rows, routing_id):
    if not routing_id:
        return []
    rows = query_rows(
        """
        SELECT ro.*, wc.code AS work_center_code, wc.name AS work_center_name
        FROM routing_operations ro
        LEFT JOIN work_centers wc ON wc.id=ro.work_center_id
        WHERE ro.routing_id=%s
          AND COALESCE(ro.is_active, TRUE)=TRUE
        ORDER BY ro.sequence, ro.id
        """,
        (routing_id,),
    )
    return [dict(row) for row in rows or []]


def _load_drawings(query_rows, order):
    rows = query_rows(
        """
        SELECT d.id AS drawing_id, d.drawing_no, d.version, d.status,
               d.effective_date, d.obsolete_date, d.release_no, d.approved_by,
               d.approval_date, d.file_location, d.checksum,
               dl.product_id, dl.bom_id, dl.project_code, dl.serial_no, dl.usage_scope
        FROM engineering_drawings d
        LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
        WHERE d.status='released'
          AND (
                dl.product_id=%s OR dl.bom_id=%s
                OR (COALESCE(%s, '')<>'' AND COALESCE(dl.project_code, '')=COALESCE(%s, ''))
                OR (COALESCE(%s, '')<>'' AND COALESCE(dl.serial_no, '')=COALESCE(%s, ''))
          )
        ORDER BY
          CASE
            WHEN COALESCE(dl.serial_no, '')=COALESCE(%s, '') AND COALESCE(dl.project_code, '')=COALESCE(%s, '') THEN 100
            WHEN dl.bom_id=%s THEN 80
            WHEN dl.product_id=%s THEN 60
            ELSE 10
          END DESC,
          d.id DESC
        LIMIT 20
        """,
        (
            order.get("product_id"),
            order.get("bom_id"),
            order.get("project_code"),
            order.get("project_code"),
            order.get("serial_no"),
            order.get("serial_no"),
            order.get("serial_no"),
            order.get("project_code"),
            order.get("bom_id"),
            order.get("product_id"),
        ),
    )
    return [dict(row) for row in rows or []]


def build_work_order_execution_snapshot(query_one, query_rows, work_order_id):
    order = _load_work_order(query_one, work_order_id)
    if not order:
        return None
    bom_header = _load_bom_header(query_one, order.get("bom_id"))
    bom_lines = _load_bom_lines(query_rows, order.get("bom_id"))
    routing_header = _load_routing_header(query_one, order)
    routing_operations = _load_routing_operations(query_rows, routing_header.get("id"))
    drawings = _load_drawings(query_rows, order)
    header_payload = {
        "work_order": order,
        "bom": bom_header,
        "routing": routing_header,
    }
    trace_context_payload = {
        "routing_operations": routing_operations,
        "drawings": drawings,
        "source_policy": "work_order_execution_snapshot",
    }
    return {
        "order": order,
        "header_payload": header_payload,
        "lines_payload": bom_lines,
        "trace_context_payload": trace_context_payload,
    }


def create_work_order_execution_snapshot(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    work_order_id,
    *,
    snapshot_by=None,
):
    snapshot = build_work_order_execution_snapshot(query_one, query_rows, work_order_id)
    if not snapshot:
        return None
    order = snapshot["order"]
    return create_trace_snapshot(
        query_one,
        execute_db,
        doc_type="work_order",
        doc_id=work_order_id,
        doc_no=order.get("wo_no"),
        snapshot_event=WORK_ORDER_EXECUTION_SNAPSHOT_EVENT,
        snapshot_by=snapshot_by,
        project_code=order.get("project_code"),
        serial_no=order.get("serial_no"),
        header_payload=snapshot["header_payload"],
        lines_payload=snapshot["lines_payload"],
        trace_context_payload=snapshot["trace_context_payload"],
        execute_and_return=execute_and_return,
    )


def latest_work_order_execution_snapshot(query_one, work_order_id) -> Optional[Dict[str, Any]]:
    row = query_one(
        """
        SELECT *
        FROM trace_snapshots
        WHERE doc_type='work_order'
          AND doc_id=%s
          AND snapshot_event=%s
        ORDER BY snapshot_at DESC, id DESC
        LIMIT 1
        """,
        (work_order_id, WORK_ORDER_EXECUTION_SNAPSHOT_EVENT),
    )
    if not row:
        return None
    result = dict(row)
    result["header_payload"] = _json_value(result.get("header_payload"), {})
    result["lines_payload"] = _json_value(result.get("lines_payload"), [])
    result["trace_context_payload"] = _json_value(result.get("trace_context_payload"), {})
    return result


def bom_requirement_rows_from_snapshot(snapshot) -> List[Dict[str, Any]]:
    if not snapshot:
        return []
    rows = _json_value(snapshot.get("lines_payload"), [])
    result = []
    for row in rows or []:
        item = dict(row)
        item["bom_item_id"] = item.get("bom_item_id")
        item["product_id"] = item.get("product_id")
        item["base_qty"] = item.get("base_qty")
        item["loss_rate"] = item.get("loss_rate")
        item["material_unit"] = item.get("material_unit") or ""
        item["remark"] = item.get("remark")
        item["material_code"] = item.get("material_code") or ""
        item["material_name"] = item.get("material_name") or ""
        item["material_spec"] = item.get("material_spec") or ""
        item["standard_price"] = item.get("standard_price")
        result.append(item)
    return result

