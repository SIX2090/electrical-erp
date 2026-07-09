from __future__ import annotations

from typing import Any, Dict, List

from services.trace_engine import create_trace_link


def _rows(query_db, sql, params=()):
    return query_db(sql, params) or []


def _build_rows(query_db) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rows.extend(
        {
            "source_doc_type": "sales_order",
            "source_doc_id": row["order_id"],
            "source_doc_no": row.get("order_no"),
            "target_doc_type": "sales_shipment",
            "target_doc_id": row["id"],
            "target_doc_no": row.get("shipment_no"),
            "link_type": "source_of",
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "created_event": "trace_gap_backfill",
        }
        for row in _rows(
            query_db,
            """
            SELECT ss.id, ss.shipment_no, ss.order_id, so.order_no,
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
            """,
        )
    )
    rows.extend(
        {
            "source_doc_type": "purchase_order",
            "source_doc_id": row["order_id"],
            "source_doc_no": row.get("order_no"),
            "target_doc_type": "purchase_receipt",
            "target_doc_id": row["id"],
            "target_doc_no": row.get("receipt_no"),
            "link_type": "source_of",
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "created_event": "trace_gap_backfill",
        }
        for row in _rows(
            query_db,
            """
            SELECT pr.id, pr.receipt_no, pr.order_id, po.order_no,
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
            """,
        )
    )
    rows.extend(
        {
            "source_doc_type": "work_order",
            "source_doc_id": row["work_order_id"],
            "source_doc_no": row.get("wo_no"),
            "target_doc_type": "production_completion",
            "target_doc_id": row["id"],
            "target_doc_no": row.get("completion_no"),
            "link_type": "source_of",
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "created_event": "trace_gap_backfill",
        }
        for row in _rows(
            query_db,
            """
            SELECT pc.id, pc.completion_no, pc.work_order_id, wo.wo_no,
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
            """,
        )
    )
    rows.extend(
        {
            "source_doc_type": "work_order",
            "source_doc_id": row["work_order_id"],
            "source_doc_no": row.get("wo_no"),
            "target_doc_type": "pick_list",
            "target_doc_id": row["id"],
            "target_doc_no": row.get("doc_no") or row.get("pick_no"),
            "link_type": "source_of",
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "created_event": "trace_gap_backfill",
        }
        for row in _rows(
            query_db,
            """
            SELECT pl.id, pl.pick_no, pl.doc_no, pl.work_order_id, wo.wo_no,
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
            """,
        )
    )
    rows.extend(
        {
            "source_doc_type": row["source_type"],
            "source_doc_id": row["source_id"],
            "source_doc_no": row.get("source_no"),
            "target_doc_type": "voucher",
            "target_doc_id": row["id"],
            "target_doc_no": row.get("voucher_no"),
            "link_type": "posts_to",
            "project_code": row.get("project_code"),
            "serial_no": row.get("serial_no"),
            "created_event": "trace_gap_backfill",
        }
        for row in _rows(
            query_db,
            """
            SELECT v.id, v.voucher_no, v.source_type, v.source_id, v.source_no,
                   COALESCE(vl.project_code, '') AS project_code,
                   COALESCE(vl.serial_no, '') AS serial_no
            FROM vouchers v
            LEFT JOIN LATERAL (
                SELECT project_code, serial_no
                FROM voucher_lines vl
                WHERE vl.voucher_id=v.id
                  AND (NULLIF(vl.project_code, '') IS NOT NULL OR NULLIF(vl.serial_no, '') IS NOT NULL)
                ORDER BY vl.id
                LIMIT 1
            ) vl ON TRUE
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
            """,
        )
    )
    return rows


def trace_gap_dry_run(query_db) -> Dict[str, Any]:
    rows = _build_rows(query_db)
    counts: Dict[str, int] = {}
    for row in rows:
        key = f"{row['source_doc_type']}->{row['target_doc_type']}"
        counts[key] = counts.get(key, 0) + 1
    return {"candidate_count": len(rows), "counts": counts}


def apply_trace_gap_links(query_db, execute_db, execute_and_return=None) -> Dict[str, Any]:
    rows = _build_rows(query_db)
    created = []
    for row in rows:
        created.append(
            create_trace_link(
                query_db,
                execute_db,
                execute_and_return=execute_and_return,
                **row,
            )
        )
    return {"created_count": len(created), "trace_link_ids": created}

