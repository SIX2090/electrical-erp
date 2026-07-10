"""Trace engine: document link graph and snapshot history for project/cabinet traceability."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

try:
    from psycopg2.extras import Json
except Exception:  # pragma: no cover - psycopg2 is present in production runtime
    Json = None


VALID_LINK_TYPES = {
    "source_of",
    "settles",
    "reverses",
    "replaces",
    "posts_to",
    "dispatches_to",
    "returns_to",
}

VALID_LINK_STRENGTHS = {"hard", "soft"}


def _clean_text(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _json_default(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _json_param(value) -> Any:
    if Json is not None:
        return Json(value, dumps=lambda obj: json.dumps(obj, ensure_ascii=False, default=_json_default))
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _stable_hash(header_payload, lines_payload):
    payload = {
        "header": header_payload or {},
        "lines": lines_payload or [],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _execute_and_return(query_db, execute_and_return, sql, params) -> Any:
    if execute_and_return is not None:
        return execute_and_return(sql, params)
    try:
        return query_db(sql, params, one=True)
    except TypeError as exc:
        if "one" not in str(exc):
            raise
        return query_db(sql, params)


def create_trace_link(
    query_db,
    execute_db,
    *,
    source_doc_type,
    source_doc_id,
    target_doc_type,
    target_doc_id,
    link_type="source_of",
    source_doc_no=None,
    source_line_id=None,
    source_line_no=None,
    target_doc_no=None,
    target_line_id=None,
    target_line_no=None,
    link_strength="hard",
    project_code=None,
    cabinet_no=None,
    created_by=None,
    created_event=None,
    execute_and_return=None,
) -> Any:
    """Insert or upsert a trace_links edge between a source and target document."""
    source_doc_type = _clean_text(source_doc_type)
    target_doc_type = _clean_text(target_doc_type)
    link_type = _clean_text(link_type)
    link_strength = _clean_text(link_strength) or "hard"
    if not source_doc_type or not target_doc_type:
        raise ValueError("source_doc_type and target_doc_type are required")
    if source_doc_id is None or target_doc_id is None:
        raise ValueError("source_doc_id and target_doc_id are required")
    if link_type not in VALID_LINK_TYPES:
        raise ValueError(f"unsupported trace link_type: {link_type}")
    if link_strength not in VALID_LINK_STRENGTHS:
        raise ValueError(f"unsupported trace link_strength: {link_strength}")

    row = _execute_and_return(
        query_db,
        execute_and_return,
        """
        INSERT INTO trace_links (
            source_doc_type, source_doc_id, source_doc_no, source_line_id, source_line_no,
            target_doc_type, target_doc_id, target_doc_no, target_line_id, target_line_no,
            link_type, link_strength, project_code, cabinet_no, created_by, created_event
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (
            source_doc_type,
            source_doc_id,
            (COALESCE(source_line_id, 0)),
            target_doc_type,
            target_doc_id,
            (COALESCE(target_line_id, 0)),
            link_type
        )
        DO UPDATE SET
            source_doc_no=COALESCE(EXCLUDED.source_doc_no, trace_links.source_doc_no),
            source_line_no=COALESCE(EXCLUDED.source_line_no, trace_links.source_line_no),
            target_doc_no=COALESCE(EXCLUDED.target_doc_no, trace_links.target_doc_no),
            target_line_no=COALESCE(EXCLUDED.target_line_no, trace_links.target_line_no),
            link_strength=EXCLUDED.link_strength,
            project_code=COALESCE(EXCLUDED.project_code, trace_links.project_code),
            cabinet_no=COALESCE(EXCLUDED.cabinet_no, trace_links.cabinet_no),
            created_by=COALESCE(EXCLUDED.created_by, trace_links.created_by),
            created_event=COALESCE(EXCLUDED.created_event, trace_links.created_event)
        RETURNING id
        """,
        (
            source_doc_type,
            source_doc_id,
            _clean_text(source_doc_no),
            source_line_id,
            _clean_text(source_line_no),
            target_doc_type,
            target_doc_id,
            _clean_text(target_doc_no),
            target_line_id,
            _clean_text(target_line_no),
            link_type,
            link_strength,
            _clean_text(project_code),
            _clean_text(cabinet_no),
            created_by,
            _clean_text(created_event),
        ),
    )
    if execute_and_return is None:
        execute_db("SELECT 1")
    return row.get("id") if hasattr(row, "get") else row[0]


def create_trace_snapshot(
    query_db,
    execute_db,
    *,
    doc_type,
    doc_id,
    snapshot_event,
    header_payload,
    lines_payload=None,
    trace_context_payload=None,
    doc_no=None,
    snapshot_by=None,
    project_code=None,
    cabinet_no=None,
    execute_and_return=None,
) -> Any:
    doc_type = _clean_text(doc_type)
    snapshot_event = _clean_text(snapshot_event)
    if not doc_type or doc_id is None or not snapshot_event:
        raise ValueError("doc_type, doc_id, and snapshot_event are required")
    header_payload = dict(header_payload or {})
    lines_payload = list(lines_payload or [])
    trace_context_payload = dict(trace_context_payload or {})
    source_hash = _stable_hash(header_payload, lines_payload)
    row = _execute_and_return(
        query_db,
        execute_and_return,
        """
        INSERT INTO trace_snapshots (
            doc_type, doc_id, doc_no, snapshot_event, snapshot_by, project_code, cabinet_no,
            header_payload, lines_payload, trace_context_payload, source_hash
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (doc_type, doc_id, snapshot_event, source_hash)
        WHERE source_hash IS NOT NULL
        DO UPDATE SET created_at=trace_snapshots.created_at
        RETURNING id
        """,
        (
            doc_type,
            doc_id,
            _clean_text(doc_no),
            snapshot_event,
            snapshot_by,
            _clean_text(project_code),
            _clean_text(cabinet_no),
            _json_param(header_payload),
            _json_param(lines_payload),
            _json_param(trace_context_payload),
            source_hash,
        ),
    )
    if execute_and_return is None:
        execute_db("SELECT 1")
    return row.get("id") if hasattr(row, "get") else row[0]


def find_upstream(query_db, doc_type, doc_id, depth=1) -> List[Dict[str, Any]]:
    rows = query_db(
        """
        SELECT *
        FROM trace_links
        WHERE target_doc_type=%s AND target_doc_id=%s
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (_clean_text(doc_type), doc_id, max(int(depth), 1) * 200),
    )
    return rows or []


def find_downstream(query_db, doc_type, doc_id, depth=1) -> List[Dict[str, Any]]:
    """Return direct downstream trace_links whose source is this document."""
    rows = query_db(
        """
        SELECT *
        FROM trace_links
        WHERE source_doc_type=%s AND source_doc_id=%s
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (_clean_text(doc_type), doc_id, max(int(depth), 1) * 200),
    )
    return rows or []


def _trace_label(doc_type: str) -> str:
    """Human-readable label for a document type."""
    mapping = {
        "sales_order": "销售订单",
        "sales_shipment": "销售发货",
        "sales_invoice": "销售发票",
        "purchase_order": "采购订单",
        "purchase_receipt": "采购入库",
        "purchase_invoice": "采购发票",
        "purchase_requisition": "采购申请",
        "work_order": "工单",
        "production_completion": "完工入库",
        "pick_list": "领料单",
        "subcontract_order": "委外订单",
        "subcontract_issue": "委外发料",
        "subcontract_receive": "委外收货",
        "voucher": "凭证",
        "inventory_transaction": "库存交易",
        "machine_service_order": "售后工单",
        "rma": "RMA",
    }
    return mapping.get(doc_type or "", doc_type or "")


def find_upstream_recursive(query_db, doc_type, doc_id, max_depth=5) -> List[Dict[str, Any]]:
    """Recursively walk upstream (sources of this document) level by level.

    Returns a list of dicts, each with:
      - depth: 1-based level (1 = direct parent)
      - link: the trace_links row connecting parent -> current
      - path: list of (doc_type, doc_id) from seed to this node
    Uses BFS with a visited set to avoid cycles.
    """
    doc_type = _clean_text(doc_type) or ""
    max_depth = max(int(max_depth), 1)
    results: List[Dict[str, Any]] = []
    visited: set = {(doc_type, doc_id)}
    queue: List[tuple] = [(doc_type, doc_id, 0, [])]
    while queue:
        cur_type, cur_id, cur_depth, cur_path = queue.pop(0)
        if cur_depth >= max_depth:
            continue
        links = query_db(
            """
            SELECT *
            FROM trace_links
            WHERE target_doc_type=%s AND target_doc_id=%s
            ORDER BY created_at DESC, id DESC
            """,
            (cur_type, cur_id),
        ) or []
        for link in links:
            src_type = link.get("source_doc_type")
            src_id = link.get("source_doc_id")
            src_key = (src_type, src_id)
            new_path = cur_path + [{"doc_type": src_type, "doc_id": src_id, "label": _trace_label(src_type)}]
            results.append({
                "depth": cur_depth + 1,
                "link": dict(link),
                "source_doc_type": src_type,
                "source_doc_id": src_id,
                "source_doc_no": link.get("source_doc_no"),
                "link_type": link.get("link_type"),
                "label": _trace_label(src_type),
                "path": new_path,
            })
            if src_key not in visited:
                visited.add(src_key)
                queue.append((src_type, src_id, cur_depth + 1, new_path))
    return results


def find_downstream_recursive(query_db, doc_type, doc_id, max_depth=5) -> List[Dict[str, Any]]:
    """Recursively walk downstream (targets of this document) level by level.

    Returns a list of dicts, each with:
      - depth: 1-based level (1 = direct child)
      - link: the trace_links row connecting current -> child
      - path: list of (doc_type, doc_id) from seed to this node
    Uses BFS with a visited set to avoid cycles.
    """
    doc_type = _clean_text(doc_type) or ""
    max_depth = max(int(max_depth), 1)
    results: List[Dict[str, Any]] = []
    visited: set = {(doc_type, doc_id)}
    queue: List[tuple] = [(doc_type, doc_id, 0, [])]
    while queue:
        cur_type, cur_id, cur_depth, cur_path = queue.pop(0)
        if cur_depth >= max_depth:
            continue
        links = query_db(
            """
            SELECT *
            FROM trace_links
            WHERE source_doc_type=%s AND source_doc_id=%s
            ORDER BY created_at DESC, id DESC
            """,
            (cur_type, cur_id),
        ) or []
        for link in links:
            tgt_type = link.get("target_doc_type")
            tgt_id = link.get("target_doc_id")
            tgt_key = (tgt_type, tgt_id)
            new_path = cur_path + [{"doc_type": tgt_type, "doc_id": tgt_id, "label": _trace_label(tgt_type)}]
            results.append({
                "depth": cur_depth + 1,
                "link": dict(link),
                "target_doc_type": tgt_type,
                "target_doc_id": tgt_id,
                "target_doc_no": link.get("target_doc_no"),
                "link_type": link.get("link_type"),
                "label": _trace_label(tgt_type),
                "path": new_path,
            })
            if tgt_key not in visited:
                visited.add(tgt_key)
                queue.append((tgt_type, tgt_id, cur_depth + 1, new_path))
    return results


def list_trace_snapshots(query_db, doc_type=None, doc_id=None, limit=100) -> List[Dict[str, Any]]:
    """List trace snapshots, optionally filtered by doc_type/doc_id."""
    params: list = []
    where_clauses: list = []
    if doc_type:
        where_clauses.append("doc_type=%s")
        params.append(_clean_text(doc_type))
    if doc_id:
        where_clauses.append("doc_id=%s")
        params.append(int(doc_id))
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(int(limit))
    return query_db(
        f"""
        SELECT id, doc_type, doc_id, doc_no, snapshot_event, snapshot_by,
               project_code, cabinet_no, source_hash, created_at
        FROM trace_snapshots
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        tuple(params),
    ) or []


def get_trace_snapshot(query_db, snapshot_id: int) -> Optional[Dict[str, Any]]:
    """Get a single trace snapshot by id, including payload details."""
    return query_db(
        """
        SELECT id, doc_type, doc_id, doc_no, snapshot_event, snapshot_by,
               project_code, cabinet_no, header_payload, lines_payload,
               trace_context_payload, source_hash, created_at
        FROM trace_snapshots
        WHERE id=%s
        """,
        (int(snapshot_id),),
        one=True,
    )


def find_by_project(query_db, project_code, limit=500) -> List[Dict[str, Any]]:
    """Return trace_links filtered by project_code."""
    return query_db(
        """
        SELECT *
        FROM trace_links
        WHERE project_code=%s
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (_clean_text(project_code), int(limit)),
    ) or []


def find_by_cabinet(query_db, cabinet_no, limit=500) -> List[Dict[str, Any]]:
    """Return trace_links filtered by cabinet_no."""
    return query_db(
        """
        SELECT *
        FROM trace_links
        WHERE cabinet_no=%s
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (_clean_text(cabinet_no), int(limit)),
    ) or []


def backfill_trace_links_dry_run(query_db) -> List[Dict[str, Any]]:
    """Count missing trace links per known document pair without writing any data."""
    candidates = []
    specs = [
        ("sales_shipments", "sales_shipment", "sales_orders", "sales_order", "order_id", "shipment_no"),
        ("purchase_receipts", "purchase_receipt", "purchase_orders", "purchase_order", "order_id", "receipt_no"),
        ("production_completion_orders", "production_completion", "work_orders", "work_order", "work_order_id", "completion_no"),
        ("pick_lists", "pick_list", "work_orders", "work_order", "work_order_id", "doc_no"),
        ("vouchers", "voucher", None, None, "source_type", "voucher_no"),
    ]
    for target_table, target_type, source_table, source_type, source_field, no_field in specs:
        if source_table:
            sql = f"""
                SELECT COUNT(*) AS count
                FROM {target_table} t
                WHERE t.{source_field} IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trace_links tl
                      WHERE tl.source_doc_type=%s
                        AND tl.source_doc_id=t.{source_field}
                        AND tl.target_doc_type=%s
                        AND tl.target_doc_id=t.id
                  )
            """
            row = query_db(sql, (source_type, target_type), one=True) or {}
        else:
            sql = """
                SELECT COUNT(*) AS count
                FROM vouchers v
                WHERE v.source_type IS NOT NULL
                  AND v.source_no IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trace_links tl
                      WHERE tl.target_doc_type='voucher'
                        AND tl.target_doc_id=v.id
                        AND tl.link_type='posts_to'
                  )
            """
            row = query_db(sql, one=True) or {}
        candidates.append({"target_table": target_table, "target_doc_type": target_type, "missing_links": row.get("count", 0)})
    return candidates


def validate_trace_link_integrity(query_db) -> List[Dict[str, Any]]:
    """Report duplicate trace edges and missing links as integrity findings."""
    findings = []
    duplicate_rows = query_db(
        """
        SELECT source_doc_type, source_doc_id, COALESCE(source_line_id,0) AS source_line_key,
               target_doc_type, target_doc_id, COALESCE(target_line_id,0) AS target_line_key,
               link_type, COUNT(*) AS count
        FROM trace_links
        GROUP BY source_doc_type, source_doc_id, COALESCE(source_line_id,0),
                 target_doc_type, target_doc_id, COALESCE(target_line_id,0), link_type
        HAVING COUNT(*) > 1
        LIMIT 50
        """
    )
    for row in duplicate_rows or []:
        findings.append({"type": "duplicate_trace_edge", **dict(row)})
    for item in backfill_trace_links_dry_run(query_db):
        if item.get("missing_links"):
            findings.append({"type": "missing_trace_links", **item})
    return findings


def create_links_for_rows(query_db, execute_db, rows: Iterable[Dict[str, Any]], execute_and_return=None) -> List[int]:
    ids = []
    for row in rows:
        ids.append(create_trace_link(query_db, execute_db, execute_and_return=execute_and_return, **row))
    return ids
