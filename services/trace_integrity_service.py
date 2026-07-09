from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.trace_engine import create_trace_link, find_downstream, find_upstream

logger = logging.getLogger(__name__)


DOC_TYPE_LABELS: Dict[str, str] = {
    "sales_order": "销售订单",
    "sales_shipment": "销售发货单",
    "sales_return": "销售退货单",
    "purchase_order": "采购订单",
    "purchase_receipt": "采购入库单",
    "purchase_return": "采购退货单",
    "work_order": "生产工单",
    "production_completion": "完工入库单",
    "pick_list": "生产领料单",
    "voucher": "凭证",
    "subcontract_order": "委外订单",
    "subcontract_issue": "委外发料单",
    "subcontract_receive": "委外收货单",
    "service_card": "服务档案",
    "service_order": "服务单",
    "service_rma": "RMA",
}


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _rows(query_db, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    return query_db(sql, params) or []


def _row(query_db, sql: str, params: tuple = ()) -> Dict[str, Any]:
    return query_db(sql, params, one=True) or {}


def _label(doc_type: Optional[str]) -> str:
    if not doc_type:
        return "-"
    return DOC_TYPE_LABELS.get(doc_type, doc_type)


def check_trace_integrity(query_db) -> List[Dict[str, Any]]:
    """Scan business documents for missing trace links and traceability fields.

    Returns a list of finding dicts. Each finding has:
    finding_type, doc_type, doc_id, doc_no, project_code, serial_no, description, severity.
    """
    findings: List[Dict[str, Any]] = []

    # 1. Sales shipments missing links to sales orders
    for row in _rows(
        query_db,
        """
        SELECT ss.id, ss.shipment_no, ss.order_id,
               COALESCE(ss.project_code, so.project_code) AS project_code,
               COALESCE(ss.serial_no, so.serial_no) AS serial_no
        FROM sales_shipments ss
        JOIN sales_orders so ON so.id=ss.order_id
        WHERE ss.order_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM trace_links tl
              WHERE tl.source_doc_type='sales_order'
                AND tl.source_doc_id=ss.order_id
                AND tl.target_doc_type='sales_shipment'
                AND tl.target_doc_id=ss.id
          )
        ORDER BY ss.id DESC
        LIMIT 200
        """,
    ):
        findings.append({
            "finding_type": "missing_shipment_order_link",
            "doc_type": "sales_shipment",
            "doc_id": row.get("id"),
            "doc_no": row.get("shipment_no"),
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "description": f"销售发货单 {row.get('shipment_no') or ''} 缺少到销售订单的追溯链接",
            "severity": "warning",
        })

    # 2. Purchase receipts missing links to purchase orders
    for row in _rows(
        query_db,
        """
        SELECT pr.id, pr.receipt_no, pr.order_id,
               COALESCE(pr.project_code, po.project_code) AS project_code,
               COALESCE(pr.serial_no, po.serial_no) AS serial_no
        FROM purchase_receipts pr
        JOIN purchase_orders po ON po.id=pr.order_id
        WHERE pr.order_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM trace_links tl
              WHERE tl.source_doc_type='purchase_order'
                AND tl.source_doc_id=pr.order_id
                AND tl.target_doc_type='purchase_receipt'
                AND tl.target_doc_id=pr.id
          )
        ORDER BY pr.id DESC
        LIMIT 200
        """,
    ):
        findings.append({
            "finding_type": "missing_receipt_order_link",
            "doc_type": "purchase_receipt",
            "doc_id": row.get("id"),
            "doc_no": row.get("receipt_no"),
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "description": f"采购入库单 {row.get('receipt_no') or ''} 缺少到采购订单的追溯链接",
            "severity": "warning",
        })

    # 3. Production completions missing links to work orders
    for row in _rows(
        query_db,
        """
        SELECT pc.id, pc.completion_no, pc.work_order_id,
               COALESCE(pc.project_code, wo.project_code) AS project_code,
               COALESCE(pc.serial_no, wo.serial_no) AS serial_no
        FROM production_completion_orders pc
        JOIN work_orders wo ON wo.id=pc.work_order_id
        WHERE pc.work_order_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM trace_links tl
              WHERE tl.source_doc_type='work_order'
                AND tl.source_doc_id=pc.work_order_id
                AND tl.target_doc_type='production_completion'
                AND tl.target_doc_id=pc.id
          )
        ORDER BY pc.id DESC
        LIMIT 200
        """,
    ):
        findings.append({
            "finding_type": "missing_completion_wo_link",
            "doc_type": "production_completion",
            "doc_id": row.get("id"),
            "doc_no": row.get("completion_no"),
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "description": f"完工入库单 {row.get('completion_no') or ''} 缺少到生产工单的追溯链接",
            "severity": "warning",
        })

    # 4. Pick lists missing links to work orders
    for row in _rows(
        query_db,
        """
        SELECT pl.id, COALESCE(pl.doc_no, pl.pick_no) AS doc_no, pl.work_order_id,
               COALESCE(pl.project_code, wo.project_code) AS project_code,
               COALESCE(pl.serial_no, wo.serial_no) AS serial_no
        FROM pick_lists pl
        JOIN work_orders wo ON wo.id=pl.work_order_id
        WHERE pl.work_order_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM trace_links tl
              WHERE tl.source_doc_type='work_order'
                AND tl.source_doc_id=pl.work_order_id
                AND tl.target_doc_type='pick_list'
                AND tl.target_doc_id=pl.id
          )
        ORDER BY pl.id DESC
        LIMIT 200
        """,
    ):
        findings.append({
            "finding_type": "missing_pick_wo_link",
            "doc_type": "pick_list",
            "doc_id": row.get("id"),
            "doc_no": row.get("doc_no"),
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "description": f"生产领料单 {row.get('doc_no') or ''} 缺少到生产工单的追溯链接",
            "severity": "warning",
        })

    # 5. Vouchers missing links to source documents
    for row in _rows(
        query_db,
        """
        SELECT v.id, v.voucher_no, v.source_type, v.source_id, v.source_no
        FROM vouchers v
        WHERE v.source_type IS NOT NULL
          AND v.source_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM trace_links tl
              WHERE tl.source_doc_type=v.source_type
                AND tl.source_doc_id=v.source_id
                AND tl.target_doc_type='voucher'
                AND tl.target_doc_id=v.id
                AND tl.link_type='posts_to'
          )
        ORDER BY v.id DESC
        LIMIT 200
        """,
    ):
        findings.append({
            "finding_type": "missing_voucher_source_link",
            "doc_type": "voucher",
            "doc_id": row.get("id"),
            "doc_no": row.get("voucher_no"),
            "project_code": None,
            "serial_no": None,
            "description": f"凭证 {row.get('voucher_no') or ''} 缺少到来源单据的追溯链接",
            "severity": "warning",
        })

    # 6. Documents missing project_code when source has one
    findings.extend(_find_missing_traceability_field(query_db, field="project_code"))
    # 7. Documents missing serial_no when source has one
    findings.extend(_find_missing_traceability_field(query_db, field="serial_no"))

    return findings


def _find_missing_traceability_field(query_db, *, field: str) -> List[Dict[str, Any]]:
    """Find downstream documents whose source has a project_code/serial_no but the
    downstream document itself does not."""
    results: List[Dict[str, Any]] = []
    field_label = "项目号" if field == "project_code" else "机号"
    specs = [
        (
            "sales_shipments",
            "sales_shipment",
            "shipment_no",
            "order_id",
            "sales_orders",
            "sales_order",
        ),
        (
            "purchase_receipts",
            "purchase_receipt",
            "receipt_no",
            "order_id",
            "purchase_orders",
            "purchase_order",
        ),
        (
            "production_completion_orders",
            "production_completion",
            "completion_no",
            "work_order_id",
            "work_orders",
            "work_order",
        ),
        (
            "pick_lists",
            "pick_list",
            "doc_no",
            "work_order_id",
            "work_orders",
            "work_order",
        ),
    ]
    for target_table, target_type, no_field, fk_field, source_table, source_type in specs:
        rows = _rows(
            query_db,
            f"""
            SELECT t.id, t.{no_field} AS doc_no, t.{fk_field} AS source_id,
                   s.{field} AS source_value
            FROM {target_table} t
            JOIN {source_table} s ON s.id=t.{fk_field}
            WHERE t.{fk_field} IS NOT NULL
              AND s.{field} IS NOT NULL AND s.{field} <> ''
              AND (t.{field} IS NULL OR t.{field} = '')
            ORDER BY t.id DESC
            LIMIT 100
            """,
        )
        for row in rows:
            results.append({
                "finding_type": f"missing_{field}",
                "doc_type": target_type,
                "doc_id": row.get("id"),
                "doc_no": row.get("doc_no"),
                "project_code": row.get("source_value") if field == "project_code" else None,
                "serial_no": row.get("source_value") if field == "serial_no" else None,
                "description": (
                    f"{_label(target_type)} {row.get('doc_no') or ''} 缺少{field_label}，"
                    f"来源{_label(source_type)}的{field_label}为 {row.get('source_value') or ''}"
                ),
                "severity": "info",
            })
    return results


def save_findings(query_db, execute_db, findings: List[Dict[str, Any]]) -> int:
    """Persist findings into trace_integrity_findings. Returns the number inserted.

    All rows are inserted in a single batch statement so they commit atomically.
    Existing open findings are cleared first to avoid duplicates on re-scan.
    """
    if not findings:
        return 0
    # Clear previous open findings so re-scans produce a clean result set
    execute_db("DELETE FROM trace_integrity_findings WHERE status='open'")
    values_rows = []
    for item in findings:
        values_rows.append(
            (
                item.get("finding_type"),
                item.get("doc_type"),
                item.get("doc_id"),
                item.get("doc_no"),
                item.get("project_code"),
                item.get("serial_no"),
                item.get("description"),
                item.get("severity", "warning"),
            )
        )
    placeholders = ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s)"] * len(values_rows))
    flat_params = tuple(v for row in values_rows for v in row)
    execute_db(
        f"""
        INSERT INTO trace_integrity_findings
            (finding_type, doc_type, doc_id, doc_no, project_code, serial_no,
             description, severity)
        VALUES {placeholders}
        """,
        flat_params,
    )
    return len(values_rows)


def get_findings(
    query_db, status: Optional[str] = None, severity: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve trace integrity findings with optional status/severity filters."""
    clauses: List[str] = []
    params: List[Any] = []
    if status:
        clauses.append("status=%s")
        params.append(status)
    if severity:
        clauses.append("severity=%s")
        params.append(severity)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT id, finding_type, doc_type, doc_id, doc_no, project_code, serial_no,
               description, severity, status, created_at
        FROM trace_integrity_findings
        {where}
        ORDER BY
            CASE status WHEN 'open' THEN 0 ELSE 1 END,
            CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
            created_at DESC
        LIMIT 500
    """
    return _rows(query_db, sql, tuple(params))


def resolve_finding(query_db, execute_db, finding_id: int) -> bool:
    """Mark a finding as resolved. Returns True if a row was updated."""
    if not finding_id:
        return False
    row = query_db(
        "SELECT id FROM trace_integrity_findings WHERE id=%s AND status='open'",
        (finding_id,),
        one=True,
    )
    if not row:
        return False
    execute_db(
        """
        UPDATE trace_integrity_findings
        SET status='resolved'
        WHERE id=%s AND status='open'
        """,
        (finding_id,),
    )
    return True


def trace_completeness_score(
    query_db, project_code: Optional[str] = None, serial_no: Optional[str] = None
) -> Dict[str, Any]:
    """Calculate trace completeness percentage.

    Completeness = (documents with trace links / total traceable documents) * 100.

    When project_code or serial_no is provided, the score is scoped to that
    project/serial. Otherwise it is computed across all traceable documents.
    """
    project_code = _clean_text(project_code)
    serial_no = _clean_text(serial_no)

    scope_clauses: List[str] = []
    scope_params: List[Any] = []
    if project_code:
        scope_clauses.append("project_code=%s")
        scope_params.append(project_code)
    if serial_no:
        scope_clauses.append("serial_no=%s")
        scope_params.append(serial_no)
    scope_sql = (" AND " + " AND ".join(scope_clauses)) if scope_clauses else ""

    # Total traceable documents: count rows from each business table that have
    # a source reference (order_id / work_order_id / source_id) and match scope.
    total_specs = [
        ("sales_shipments", "order_id", "shipment_no"),
        ("purchase_receipts", "order_id", "receipt_no"),
        ("production_completion_orders", "work_order_id", "completion_no"),
        ("pick_lists", "work_order_id", "doc_no"),
    ]
    total_count = 0
    for table, fk_field, no_field in total_specs:
        row = _row(
            query_db,
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE {fk_field} IS NOT NULL{scope_sql}
            """,
            tuple(scope_params),
        )
        total_count += int(row.get("count", 0) or 0)

    # Vouchers with source
    voucher_row = _row(
        query_db,
        f"""
        SELECT COUNT(*) AS count
        FROM vouchers
        WHERE source_type IS NOT NULL AND source_id IS NOT NULL{scope_sql}
        """,
        tuple(scope_params),
    )
    total_count += int(voucher_row.get("count", 0) or 0)

    # Linked documents: distinct (doc_type, doc_id) pairs in trace_links matching scope
    linked_row = _row(
        query_db,
        f"""
        SELECT COUNT(DISTINCT (target_doc_type, target_doc_id)) AS count
        FROM trace_links
        WHERE target_doc_type IN
              ('sales_shipment','purchase_receipt','production_completion','pick_list','voucher')
        {scope_sql}
        """,
        tuple(scope_params),
    )
    linked_count = int(linked_row.get("count", 0) or 0)

    if total_count <= 0:
        score = Decimal("100")
    else:
        score = (Decimal(linked_count) / Decimal(total_count) * Decimal("100")).quantize(Decimal("0.01"))

    return {
        "total_documents": total_count,
        "linked_documents": linked_count,
        "score": score,
        "project_code": project_code,
        "serial_no": serial_no,
    }


def build_trace_graph(
    query_db, doc_type: str, doc_id: int, depth: int = 3
) -> Dict[str, Any]:
    """Build a trace graph (upstream + downstream) via BFS for visualization.

    Returns a dict with:
    - seed: the starting document
    - nodes: list of node dicts (doc_type, doc_id, doc_no, depth)
    - edges: list of edge dicts (source/target doc_type/id/no, link_type)
    """
    doc_type = _clean_text(doc_type) or ""
    max_depth = max(int(depth), 1)

    nodes: Dict[tuple, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    edge_keys: set = set()
    visited: set = set()

    seed_key = (doc_type, doc_id)
    nodes[seed_key] = {
        "doc_type": doc_type,
        "doc_id": doc_id,
        "doc_no": None,
        "depth": 0,
        "label": _label(doc_type),
    }
    visited.add(seed_key)

    queue: List[tuple] = [(doc_type, doc_id, 0)]
    while queue:
        current_type, current_id, current_depth = queue.pop(0)
        if current_depth >= max_depth:
            continue

        # Downstream: current document is the source
        for link in find_downstream(query_db, current_type, current_id, depth=1):
            edge_key = (
                link.get("source_doc_type"),
                link.get("source_doc_id"),
                link.get("target_doc_type"),
                link.get("target_doc_id"),
                link.get("link_type"),
            )
            if edge_key not in edge_keys:
                edge_keys.add(edge_key)
                edges.append({
                    "source_doc_type": link.get("source_doc_type"),
                    "source_doc_id": link.get("source_doc_id"),
                    "source_doc_no": link.get("source_doc_no"),
                    "target_doc_type": link.get("target_doc_type"),
                    "target_doc_id": link.get("target_doc_id"),
                    "target_doc_no": link.get("target_doc_no"),
                    "link_type": link.get("link_type"),
                    "link_strength": link.get("link_strength"),
                })
            target_key = (link.get("target_doc_type"), link.get("target_doc_id"))
            if target_key not in visited:
                visited.add(target_key)
                nodes[target_key] = {
                    "doc_type": link.get("target_doc_type"),
                    "doc_id": link.get("target_doc_id"),
                    "doc_no": link.get("target_doc_no"),
                    "depth": current_depth + 1,
                    "label": _label(link.get("target_doc_type")),
                }
                queue.append((link.get("target_doc_type"), link.get("target_doc_id"), current_depth + 1))

        # Upstream: current document is the target
        for link in find_upstream(query_db, current_type, current_id, depth=1):
            edge_key = (
                link.get("source_doc_type"),
                link.get("source_doc_id"),
                link.get("target_doc_type"),
                link.get("target_doc_id"),
                link.get("link_type"),
            )
            if edge_key not in edge_keys:
                edge_keys.add(edge_key)
                edges.append({
                    "source_doc_type": link.get("source_doc_type"),
                    "source_doc_id": link.get("source_doc_id"),
                    "source_doc_no": link.get("source_doc_no"),
                    "target_doc_type": link.get("target_doc_type"),
                    "target_doc_id": link.get("target_doc_id"),
                    "target_doc_no": link.get("target_doc_no"),
                    "link_type": link.get("link_type"),
                    "link_strength": link.get("link_strength"),
                })
            source_key = (link.get("source_doc_type"), link.get("source_doc_id"))
            if source_key not in visited:
                visited.add(source_key)
                nodes[source_key] = {
                    "doc_type": link.get("source_doc_type"),
                    "doc_id": link.get("source_doc_id"),
                    "doc_no": link.get("source_doc_no"),
                    "depth": current_depth + 1,
                    "label": _label(link.get("source_doc_type")),
                }
                queue.append((link.get("source_doc_type"), link.get("source_doc_id"), current_depth + 1))

    return {
        "seed": {"doc_type": doc_type, "doc_id": doc_id, "label": _label(doc_type)},
        "nodes": list(nodes.values()),
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# P4-B2: 追溯回填执行
# ---------------------------------------------------------------------------

_LINK_BACKFILL_SPECS = [
    # (finding_type, source_table, source_type, source_no_field, target_table,
    #  target_type, target_no_field, fk_field, link_type)
    (
        "missing_shipment_order_link",
        "sales_orders",
        "sales_order",
        "order_no",
        "sales_shipments",
        "sales_shipment",
        "shipment_no",
        "order_id",
        "source_of",
    ),
    (
        "missing_receipt_order_link",
        "purchase_orders",
        "purchase_order",
        "order_no",
        "purchase_receipts",
        "purchase_receipt",
        "receipt_no",
        "order_id",
        "source_of",
    ),
    (
        "missing_completion_wo_link",
        "work_orders",
        "work_order",
        "wo_no",
        "production_completion_orders",
        "production_completion",
        "completion_no",
        "work_order_id",
        "source_of",
    ),
    (
        "missing_pick_wo_link",
        "work_orders",
        "work_order",
        "wo_no",
        "pick_lists",
        "pick_list",
        "doc_no",
        "work_order_id",
        "source_of",
    ),
]

_FIELD_BACKFILL_SPECS = [
    # (target_table, target_type, no_field, fk_field, source_table, source_type)
    ("sales_shipments", "sales_shipment", "shipment_no", "order_id",
     "sales_orders", "sales_order"),
    ("purchase_receipts", "purchase_receipt", "receipt_no", "order_id",
     "purchase_orders", "purchase_order"),
    ("production_completion_orders", "production_completion", "completion_no",
     "work_order_id", "work_orders", "work_order"),
    ("pick_lists", "pick_list", "doc_no", "work_order_id",
     "work_orders", "work_order"),
]


def backfill_trace_links(query_db, execute_db, *, execute_and_return=None,
                         created_by=None) -> Dict[str, Any]:
    """P4-B2: 扫描并回填缺失的 trace_links 与追溯字段。

    Returns a summary dict with:
    - links_inserted: 新建的 trace_links 行数
    - fields_backfilled: 回填 project_code/serial_no 的行数
    - findings_resolved: 标记为 resolved 的 finding 数量
    - details: 按类别分组的明细
    """
    links_inserted = 0
    fields_backfilled = 0
    details: List[Dict[str, Any]] = []

    # 1. 回填缺失的 trace_links
    for (finding_type, source_table, source_type, source_no_field,
         target_table, target_type, target_no_field, fk_field,
         link_type) in _LINK_BACKFILL_SPECS:
        rows = _rows(
            query_db,
            f"""
            SELECT t.id AS target_id, t.{target_no_field} AS target_no,
                   t.{fk_field} AS source_id,
                   s.{source_no_field} AS source_no,
                   COALESCE(t.project_code, s.project_code) AS project_code,
                   COALESCE(t.serial_no, s.serial_no) AS serial_no
            FROM {target_table} t
            JOIN {source_table} s ON s.id=t.{fk_field}
            WHERE t.{fk_field} IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM trace_links tl
                  WHERE tl.source_doc_type=%s
                    AND tl.source_doc_id=t.{fk_field}
                    AND tl.target_doc_type=%s
                    AND tl.target_doc_id=t.id
              )
            ORDER BY t.id DESC
            LIMIT 500
            """,
            (source_type, target_type),
        )
        count = 0
        for row in rows:
            try:
                create_trace_link(
                    query_db,
                    execute_db,
                    source_doc_type=source_type,
                    source_doc_id=row.get("source_id"),
                    source_doc_no=row.get("source_no"),
                    target_doc_type=target_type,
                    target_doc_id=row.get("target_id"),
                    target_doc_no=row.get("target_no"),
                    link_type=link_type,
                    link_strength="hard",
                    project_code=row.get("project_code"),
                    serial_no=row.get("serial_no"),
                    created_by=created_by,
                    created_event="trace_backfill",
                    execute_and_return=execute_and_return,
                )
                count += 1
            except Exception:
                # 单条失败不阻断整体回填
                logger.warning("trace backfill single-row failed", exc_info=True)
                pass
        if count:
            links_inserted += count
            details.append({
                "category": finding_type,
                "action": "insert_links",
                "count": count,
                "target_type": target_type,
            })

    # 凭证 → 来源单据 的 trace_link 回填
    voucher_rows = _rows(
        query_db,
        """
        SELECT v.id, v.voucher_no, v.source_type, v.source_id, v.source_no
        FROM vouchers v
        WHERE v.source_type IS NOT NULL
          AND v.source_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM trace_links tl
              WHERE tl.source_doc_type=v.source_type
                AND tl.source_doc_id=v.source_id
                AND tl.target_doc_type='voucher'
                AND tl.target_doc_id=v.id
                AND tl.link_type='posts_to'
          )
        ORDER BY v.id DESC
        LIMIT 500
        """,
    )
    voucher_count = 0
    for row in voucher_rows:
        try:
            create_trace_link(
                query_db,
                execute_db,
                source_doc_type=row.get("source_type"),
                source_doc_id=row.get("source_id"),
                source_doc_no=row.get("source_no"),
                target_doc_type="voucher",
                target_doc_id=row.get("id"),
                target_doc_no=row.get("voucher_no"),
                link_type="posts_to",
                link_strength="hard",
                created_by=created_by,
                created_event="trace_backfill",
                execute_and_return=execute_and_return,
            )
            voucher_count += 1
        except Exception:
            logger.warning("trace voucher link backfill failed", exc_info=True)
            pass
    if voucher_count:
        links_inserted += voucher_count
        details.append({
            "category": "missing_voucher_source_link",
            "action": "insert_links",
            "count": voucher_count,
            "target_type": "voucher",
        })

    # 2. 回填缺失的 project_code / serial_no 字段
    for field in ("project_code", "serial_no"):
        field_label = "项目号" if field == "project_code" else "机号"
        for (target_table, target_type, no_field, fk_field,
             source_table, source_type) in _FIELD_BACKFILL_SPECS:
            rows = _rows(
                query_db,
                f"""
                SELECT t.id, t.{no_field} AS doc_no, s.{field} AS source_value
                FROM {target_table} t
                JOIN {source_table} s ON s.id=t.{fk_field}
                WHERE t.{fk_field} IS NOT NULL
                  AND s.{field} IS NOT NULL AND s.{field} <> ''
                  AND (t.{field} IS NULL OR t.{field} = '')
                ORDER BY t.id DESC
                LIMIT 200
                """,
            )
            if not rows:
                continue
            ids = [r.get("id") for r in rows if r.get("id")]
            if not ids:
                continue
            # 批量更新该表缺失字段
            execute_db(
                f"""
                UPDATE {target_table} t
                SET {field} = s.{field}
                FROM {source_table} s
                WHERE t.{fk_field}=s.id
                  AND s.{field} IS NOT NULL AND s.{field} <> ''
                  AND (t.{field} IS NULL OR t.{field} = '')
                  AND t.id = ANY(%s)
                """,
                (ids,),
            )
            fields_backfilled += len(ids)
            details.append({
                "category": f"missing_{field}",
                "action": "backfill_field",
                "field": field,
                "field_label": field_label,
                "count": len(ids),
                "target_type": target_type,
            })

    # 3. 将已回填对应的 open findings 标记为 resolved
    findings_resolved = 0
    if links_inserted > 0 or fields_backfilled > 0:
        execute_db(
            """
            UPDATE trace_integrity_findings
            SET status='resolved'
            WHERE status='open'
              AND finding_type IN (
                  'missing_shipment_order_link',
                  'missing_receipt_order_link',
                  'missing_completion_wo_link',
                  'missing_pick_wo_link',
                  'missing_voucher_source_link',
                  'missing_project_code',
                  'missing_serial_no'
              )
            """,
        )
        # 重新查询已 resolved 的数量差异较难精确，这里用简单计数
        findings_resolved = links_inserted + fields_backfilled  # 近似值

    return {
        "links_inserted": links_inserted,
        "fields_backfilled": fields_backfilled,
        "findings_resolved": findings_resolved,
        "details": details,
    }
