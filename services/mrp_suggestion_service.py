from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from services.mrp_engine import convert_suggestion
from services.trace_engine import create_trace_link as _create_trace_link

logger = logging.getLogger(__name__)


def _as_decimal(value, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _next_doc_no(query_one, prefix: str, table: str, field: str) -> str:
    """Generate next document number using prefix + YYYYMMDD + 3-digit sequence.

    Uses document_sequences UPSERT for atomic increment to avoid race conditions
    on concurrent calls. Falls back to legacy MAX+1 if the sequence table is
    unavailable (e.g. during offline tests without DB).
    """
    daily_prefix = f"{prefix}{datetime.now():%Y%m%d}"
    try:
        row = query_one(
            """
            INSERT INTO document_sequences (prefix, scope, last_value)
            VALUES (%s, %s, 1)
            ON CONFLICT (prefix, scope)
            DO UPDATE SET last_value = document_sequences.last_value + 1,
                          updated_at = CURRENT_TIMESTAMP
            RETURNING last_value
            """,
            (prefix, daily_prefix),
        ) or {}
        next_seq = int(row.get("last_value") or 1)
    except Exception:
        # Fallback: legacy MAX+1 (non-atomic, kept for environments without document_sequences).
        row = query_one(
            f"SELECT {field} AS doc_no FROM {table} WHERE {field} LIKE %s ORDER BY {field} DESC LIMIT 1",
            (f"{daily_prefix}%",),
        ) or {}
        last_no = (row.get("doc_no") or "").replace(daily_prefix, "")
        try:
            next_seq = int(last_no or "0") + 1
        except ValueError:
            next_seq = 1
    return f"{daily_prefix}{next_seq:03d}"


def _get_suggestion(query_one, suggestion_id: int) -> Optional[Dict[str, Any]]:
    row = query_one(
        """
        SELECT ms.*, mr.source_type, mr.source_id, mr.source_no
        FROM mrp_suggestions ms
        LEFT JOIN mrp_runs mr ON mr.id=ms.run_id
        WHERE ms.id=%s
        """,
        (suggestion_id,),
    )
    return dict(row) if row else None


def _product_snapshot(query_one, product_id) -> Dict[str, Any]:
    row = query_one(
        """
        SELECT id, code, name, specification, unit, standard_price
        FROM products WHERE id=%s
        """,
        (product_id,),
    ) or {}
    return dict(row)


def convert_to_purchase_requisition(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    suggestion_id: int,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a purchase requisition from a purchase suggestion."""
    suggestion = _get_suggestion(query_one, suggestion_id)
    if not suggestion:
        return {"status": "error", "message": "建议不存在"}
    if suggestion.get("status") != "open":
        return {"status": "error", "message": "建议已处理或已关闭"}
    if suggestion.get("suggestion_type") not in ("purchase", "transfer"):
        return {"status": "error", "message": "仅采购或调拨建议可转为采购申请"}
    qty = _as_decimal(suggestion.get("qty"))
    if qty <= 0:
        return {"status": "error", "message": "建议数量必须大于 0"}
    product = _product_snapshot(query_one, suggestion.get("material_id"))
    req_no = _next_doc_no(query_one, "PR", "purchase_requisitions", "req_no")
    project_code = suggestion.get("project_code") or None
    serial_no = suggestion.get("serial_no") or None
    req_row = execute_and_return(
        """
        INSERT INTO purchase_requisitions
            (req_no, req_date, department, purpose, status, remark, project_code, serial_no)
        VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s)
        RETURNING id, req_no
        """,
        (
            req_no,
            "采购部",
            "MRP 建议生成采购申请",
            "待提交",
            f"由 MRP 建议 {suggestion.get('run_id')}-{suggestion_id} 自动生成",
            project_code,
            serial_no,
        ),
    ) or {}
    req_id = req_row.get("id")
    unit_price = _as_decimal(product.get("standard_price"))
    amount = qty * unit_price
    execute_db(
        """
        INSERT INTO purchase_requisition_items
            (req_id, product_id, quantity, unit_price, amount, need_date,
             suggested_supplier_id, remark, project_code, serial_no,
             material_code, material_name, material_spec, material_unit)
        VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            req_id,
            suggestion.get("material_id"),
            qty,
            unit_price,
            amount,
            suggestion.get("required_date"),
            f"MRP 建议自动生成，来源 MRP 运行 {suggestion.get('run_id')}",
            project_code,
            serial_no,
            product.get("code"),
            product.get("name"),
            product.get("specification"),
            product.get("unit"),
        ),
    )
    convert_suggestion(execute_db, execute_and_return, suggestion_id, "purchase_requisition", req_id, req_no)
    try:
        _create_trace_link(
            query_one,
            execute_db,
            source_doc_type="mrp_run",
            source_doc_id=suggestion.get("run_id"),
            source_doc_no=suggestion.get("source_no"),
            target_doc_type="purchase_requisition",
            target_doc_id=req_id,
            target_doc_no=req_no,
            link_type="source_of",
            project_code=project_code,
            serial_no=serial_no,
            created_by=created_by,
            created_event="mrp_convert",
        )
    except Exception:
        logger.exception("create_trace_link failed for MRP suggestion conversion")
    return {
        "status": "ok",
        "doc_type": "purchase_requisition",
        "doc_id": req_id,
        "doc_no": req_no,
        "suggestion_id": suggestion_id,
    }


def convert_to_work_order(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    suggestion_id: int,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a work order from a production suggestion."""
    suggestion = _get_suggestion(query_one, suggestion_id)
    if not suggestion:
        return {"status": "error", "message": "建议不存在"}
    if suggestion.get("status") != "open":
        return {"status": "error", "message": "建议已处理或已关闭"}
    if suggestion.get("suggestion_type") != "production":
        return {"status": "error", "message": "仅生产建议可转为工单"}
    qty = _as_decimal(suggestion.get("qty"))
    if qty <= 0:
        return {"status": "error", "message": "建议数量必须大于 0"}
    product = _product_snapshot(query_one, suggestion.get("material_id"))
    wo_no = _next_doc_no(query_one, "WO", "work_orders", "wo_no")
    project_code = suggestion.get("project_code") or None
    serial_no = suggestion.get("serial_no") or None
    wo_row = execute_and_return(
        """
        INSERT INTO work_orders
            (wo_no, wo_date, product_id, quantity, status,
             material_code, material_name, material_spec, material_unit,
             production_stage, status_changed_at, project_code, serial_no, remark)
        VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
        RETURNING id, wo_no
        """,
        (
            wo_no,
            suggestion.get("material_id"),
            qty,
            "创建",
            product.get("code"),
            product.get("name"),
            product.get("specification"),
            product.get("unit"),
            "创建",
            project_code,
            serial_no,
            f"由 MRP 建议 {suggestion.get('run_id')}-{suggestion_id} 自动生成",
        ),
    ) or {}
    wo_id = wo_row.get("id")
    convert_suggestion(execute_db, execute_and_return, suggestion_id, "work_order", wo_id, wo_no)
    try:
        _create_trace_link(
            query_one,
            execute_db,
            source_doc_type="mrp_run",
            source_doc_id=suggestion.get("run_id"),
            source_doc_no=suggestion.get("source_no"),
            target_doc_type="work_order",
            target_doc_id=wo_id,
            target_doc_no=wo_no,
            link_type="source_of",
            project_code=project_code,
            serial_no=serial_no,
            created_by=created_by,
            created_event="mrp_convert",
        )
    except Exception:
        logger.warning("Failed to create MRP conversion trace link", exc_info=True)
    return {
        "status": "ok",
        "doc_type": "work_order",
        "doc_id": wo_id,
        "doc_no": wo_no,
        "suggestion_id": suggestion_id,
    }


def convert_to_subcontract_order(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    suggestion_id: int,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a subcontract order from an outsource suggestion."""
    suggestion = _get_suggestion(query_one, suggestion_id)
    if not suggestion:
        return {"status": "error", "message": "建议不存在"}
    if suggestion.get("status") != "open":
        return {"status": "error", "message": "建议已处理或已关闭"}
    if suggestion.get("suggestion_type") != "outsource":
        return {"status": "error", "message": "仅委外建议可转为委外订单"}
    qty = _as_decimal(suggestion.get("qty"))
    if qty <= 0:
        return {"status": "error", "message": "建议数量必须大于 0"}
    product = _product_snapshot(query_one, suggestion.get("material_id"))
    order_no = _next_doc_no(query_one, "SCO", "subcontract_orders", "order_no")
    project_code = suggestion.get("project_code") or None
    serial_no = suggestion.get("serial_no") or None
    order_row = execute_and_return(
        """
        INSERT INTO subcontract_orders
            (order_no, order_date, product_id, quantity, unit_price, total_amount,
             project_code, serial_no, status, remark, updated_at, arrival_status,
             shortage_qty, received_qty,
             material_code, material_name, material_spec, material_unit)
        VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, 0, %s, %s, %s, %s)
        RETURNING id, order_no
        """,
        (
            order_no,
            suggestion.get("material_id"),
            qty,
            _as_decimal(product.get("standard_price")),
            qty * _as_decimal(product.get("standard_price")),
            project_code,
            serial_no,
            "draft",
            f"由 MRP 建议 {suggestion.get('run_id')}-{suggestion_id} 自动生成",
            "未发料",
            qty,
            product.get("code"),
            product.get("name"),
            product.get("specification"),
            product.get("unit"),
        ),
    ) or {}
    order_id = order_row.get("id")
    convert_suggestion(execute_db, execute_and_return, suggestion_id, "subcontract_order", order_id, order_no)
    try:
        _create_trace_link(
            query_one,
            execute_db,
            source_doc_type="mrp_run",
            source_doc_id=suggestion.get("run_id"),
            source_doc_no=suggestion.get("source_no"),
            target_doc_type="subcontract_order",
            target_doc_id=order_id,
            target_doc_no=order_no,
            link_type="source_of",
            project_code=project_code,
            serial_no=serial_no,
            created_by=created_by,
            created_event="mrp_convert",
        )
    except Exception:
        logger.warning("mrp convert trace link failed for order_id=%s", order_id, exc_info=True)
        pass
    return {
        "status": "ok",
        "doc_type": "subcontract_order",
        "doc_id": order_id,
        "doc_no": order_no,
        "suggestion_id": suggestion_id,
    }


_CONVERSION_DISPATCH = {
    "purchase": convert_to_purchase_requisition,
    "transfer": convert_to_purchase_requisition,
    "production": convert_to_work_order,
    "outsource": convert_to_subcontract_order,
}


def convert_single(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    suggestion_id: int,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Dispatch a single suggestion to the right converter based on its type."""
    suggestion = _get_suggestion(query_one, suggestion_id)
    if not suggestion:
        return {"status": "error", "message": "建议不存在"}
    suggestion_type = suggestion.get("suggestion_type")
    converter = _CONVERSION_DISPATCH.get(suggestion_type)
    if not converter:
        return {"status": "error", "message": f"不支持的建议类型：{suggestion_type}"}
    return converter(query_one, query_rows, execute_db, execute_and_return, suggestion_id, created_by)


def batch_convert(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    suggestion_ids: List[int],
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Convert multiple suggestions. Returns aggregate result with per-item outcomes."""
    results: List[Dict[str, Any]] = []
    success_count = 0
    failure_count = 0
    for sid in suggestion_ids:
        try:
            outcome = convert_single(query_one, query_rows, execute_db, execute_and_return, sid, created_by)
        except Exception as exc:  # pragma: no cover - defensive
            outcome = {"status": "error", "message": str(exc), "suggestion_id": sid}
        outcome["suggestion_id"] = sid
        results.append(outcome)
        if outcome.get("status") == "ok":
            success_count += 1
        else:
            failure_count += 1
    return {
        "status": "ok" if failure_count == 0 else ("partial" if success_count > 0 else "error"),
        "total": len(suggestion_ids),
        "success_count": success_count,
        "failure_count": failure_count,
        "results": results,
    }
