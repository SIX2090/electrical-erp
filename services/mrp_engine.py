"""MRP engine service: BOM explosion, net requirement calculation, and MRP run persistence."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.bom_snapshot_service import create_bom_snapshot
from services.bom_substitute_service import list_substitutes_for_product
from services.bom_version_service import get_active_version as _get_active_bom_version

logger = logging.getLogger(__name__)


def _as_decimal(value, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _positive(value) -> Decimal:
    qty = _as_decimal(value)
    return qty if qty > 0 else Decimal("0")


def _sum_quantity(query_one, sql: str, params) -> Decimal:
    row = query_one(sql, params) or {}
    return _as_decimal(row.get("qty"))


def _inventory_quantities(query_one, product_id, project_code=None, serial_no=None) -> Dict[str, Decimal]:
    row = query_one(
        """
        SELECT COALESCE(SUM(quantity), 0) AS stock_qty,
               COALESCE(SUM(locked_qty), 0) AS locked_qty
        FROM inventory_balances
        WHERE product_id=%s
          AND (COALESCE(%s, '')='' OR COALESCE(project_code, '')='' OR COALESCE(project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(serial_no, '')='' OR COALESCE(serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    ) or {}
    stock_qty = _as_decimal(row.get("stock_qty"))
    locked_qty = _as_decimal(row.get("locked_qty"))
    available_qty = stock_qty - locked_qty
    return {
        "stock_qty": _positive(stock_qty),
        "locked_qty": _positive(locked_qty),
        "available_qty": _positive(available_qty),
    }


def _inventory_available_other_projects(query_one, product_id, project_code=None, serial_no=None) -> Decimal:
    """Available stock in other project/serial buckets (for transfer suggestions)."""
    row = query_one(
        """
        SELECT COALESCE(SUM(GREATEST(COALESCE(quantity, 0) - COALESCE(locked_qty, 0), 0)), 0) AS qty
        FROM inventory_balances
        WHERE product_id=%s
          AND (COALESCE(%s, '')='' OR COALESCE(project_code, '')<>COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(serial_no, '')<>COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    ) or {}
    return _positive(row.get("qty"))


def _purchase_requisition_qty(query_one, product_id, project_code=None, serial_no=None) -> Decimal:
    return _sum_quantity(
        query_one,
        """
        SELECT COALESCE(SUM(COALESCE(pri.quantity, 0)), 0) AS qty
        FROM purchase_requisition_items pri
        LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
        WHERE pri.product_id=%s
          AND COALESCE(pr.status, '') NOT IN ('已关闭','已作废','已取消','closed','void','voided','cancelled','canceled')
          AND (COALESCE(%s, '')='' OR COALESCE(pri.project_code, pr.project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(pri.serial_no, pr.serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    )


def _purchase_on_order_qty(query_one, product_id, project_code=None, serial_no=None) -> Decimal:
    return _sum_quantity(
        query_one,
        """
        SELECT COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0) AS qty
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.id=poi.order_id
        WHERE poi.product_id=%s
          AND COALESCE(po.status, '') NOT IN ('已关闭','已作废','已取消','closed','completed','void','voided','cancelled','canceled')
          AND (COALESCE(%s, '')='' OR COALESCE(poi.line_project_code, po.project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(poi.line_serial_no, po.serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    )


def _outsource_on_order_qty(query_one, product_id, project_code=None, serial_no=None) -> Decimal:
    """Open subcontract orders for this product (not yet received)."""
    return _sum_quantity(
        query_one,
        """
        SELECT COALESCE(SUM(GREATEST(COALESCE(so.quantity, 0)-COALESCE(so.received_qty, 0), 0)), 0) AS qty
        FROM subcontract_orders so
        WHERE so.product_id=%s
          AND COALESCE(so.status, '') NOT IN ('已关闭','已作废','已取消','closed','completed','void','voided','cancelled','canceled')
          AND (COALESCE(%s, '')='' OR COALESCE(so.project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(so.serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    )


def _production_on_order_qty(query_one, product_id, project_code=None, serial_no=None) -> Decimal:
    """Open work orders producing this product (not yet completed)."""
    return _sum_quantity(
        query_one,
        """
        SELECT COALESCE(SUM(COALESCE(wo.quantity, 0)), 0) AS qty
        FROM work_orders wo
        WHERE wo.product_id=%s
          AND COALESCE(wo.status, '') NOT IN ('已完工','已关闭','已完成','closed','completed','cancelled','canceled')
          AND (COALESCE(%s, '')='' OR COALESCE(wo.project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(wo.serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    )


def _supply_commitment_dates(query_one, product_id, project_code=None, serial_no=None) -> Dict[str, Any]:
    """Read existing supply commitment dates for kitting readiness calculation."""
    purchase_request = query_one(
        """
        SELECT MAX(pri.need_date) AS ready_date
        FROM purchase_requisition_items pri
        LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
        WHERE pri.product_id=%s
          AND COALESCE(pr.status, '') NOT IN ('closed','void','voided','cancelled','canceled')
          AND COALESCE(pri.quantity, 0) > 0
          AND (COALESCE(%s, '')='' OR COALESCE(pri.project_code, pr.project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(pri.serial_no, pr.serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    ) or {}
    purchase_order = query_one(
        """
        SELECT MAX(COALESCE(poi.expected_date, po.expected_date)) AS ready_date
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.id=poi.order_id
        WHERE poi.product_id=%s
          AND COALESCE(po.status, '') NOT IN ('closed','completed','void','voided','cancelled','canceled')
          AND GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0) > 0
          AND (COALESCE(%s, '')='' OR COALESCE(poi.line_project_code, po.project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(poi.line_serial_no, po.serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    ) or {}
    outsource_order = query_one(
        """
        SELECT MAX(so.required_date) AS ready_date
        FROM subcontract_orders so
        WHERE so.product_id=%s
          AND COALESCE(so.status, '') NOT IN ('closed','completed','void','voided','cancelled','canceled')
          AND GREATEST(COALESCE(so.quantity, 0)-COALESCE(so.received_qty, 0), 0) > 0
          AND (COALESCE(%s, '')='' OR COALESCE(so.project_code, so.line_project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(so.serial_no, so.line_serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    ) or {}
    production_order = query_one(
        """
        SELECT MAX(wo.planned_end_date) AS ready_date
        FROM work_orders wo
        WHERE wo.product_id=%s
          AND COALESCE(wo.status, '') NOT IN ('closed','completed','cancelled','canceled')
          AND COALESCE(wo.quantity, 0) > 0
          AND (COALESCE(%s, '')='' OR COALESCE(wo.project_code, wo.line_project_code, '')=COALESCE(%s, ''))
          AND (COALESCE(%s, '')='' OR COALESCE(wo.serial_no, wo.line_serial_no, '')=COALESCE(%s, ''))
        """,
        (product_id, project_code, project_code, serial_no, serial_no),
    ) or {}
    return {
        "purchase_request_date": purchase_request.get("ready_date"),
        "purchase_order_date": purchase_order.get("ready_date"),
        "outsource_order_date": outsource_order.get("ready_date"),
        "production_order_date": production_order.get("ready_date"),
    }


def _product_procurement_type(query_one, product_id) -> str:
    """Determine whether a product is buyable, manufactured, or outsourced.

    Heuristic:
      - If a BOM exists for the product -> 'manufactured'
      - Otherwise -> 'purchase' (default buyable)
    Outsourced is determined by context (subcontract route), not by master data here.
    """
    if not product_id:
        return "purchase"
    row = query_one(
        """
        SELECT COUNT(*) AS bom_count
        FROM boms
        WHERE product_id=%s
          AND COALESCE(status, '') NOT IN ('停用','inactive','disabled')
        """,
        (product_id,),
    ) or {}
    return "manufactured" if int(row.get("bom_count") or 0) > 0 else "purchase"


def _estimated_ready_date(
    required_date,
    lead_time_days: int,
    suggestion_type: str,
    net_qty: Decimal,
    gross_qty: Decimal,
    effective_available_qty: Decimal,
    supply_dates: Dict[str, Any] | None = None,
):
    """Estimate readiness from existing commitments before falling back to lead time."""
    supply_dates = supply_dates or {}
    commitment_dates = [value for value in supply_dates.values() if value]
    if suggestion_type == "covered":
        if gross_qty <= effective_available_qty:
            return date.today()
        return max(commitment_dates) if commitment_dates else date.today()
    if net_qty <= 0 and commitment_dates:
        return max(commitment_dates)
    if suggestion_type == "transfer":
        return date.today()
    lead_days = max(int(lead_time_days or 0), 0)
    candidate = date.today() + timedelta(days=lead_days)
    if commitment_dates:
        candidate = max([candidate, *commitment_dates])
    if required_date and suggestion_type in {"purchase", "outsource", "production"}:
        return max(candidate, required_date)
    return candidate


def _kitting_action_fields(row: Dict[str, Any], net_qty: Decimal, suggestion_type: str) -> Dict[str, Any]:
    """Return operator-facing kitting action fields for a net requirement line."""
    material = row.get("material_name") or row.get("material_code") or "物料"
    required_date = row.get("required_date")
    lead_time_days = int(row.get("lead_time_days") or 0)
    estimated_ready_date = _estimated_ready_date(
        required_date,
        lead_time_days,
        suggestion_type,
        net_qty,
        _as_decimal(row.get("gross_qty")),
        _as_decimal(row.get("effective_available_qty")),
        row.get("supply_dates") or {},
    )
    if net_qty <= 0:
        return {
            "kitting_state": "covered",
            "kitting_state_label": "已齐套",
            "blocked_reason": "库存、在途、在制或替代料可覆盖需求。",
            "owner_role": "生产计划",
            "next_action": "按工单领料节奏复核批次、库位和项目机号后投产。",
            "downstream_impact": "支持工单领料、投产、完工入库和项目交付。",
            "action_url": "/requisition",
            "estimated_ready_date": estimated_ready_date,
        }
    if suggestion_type == "transfer":
        return {
            "kitting_state": "shortage",
            "kitting_state_label": "需调拨",
            "blocked_reason": f"{material} 当前项目/机号缺 {net_qty}，其他项目或公共库存可覆盖。",
            "owner_role": "仓库/计划",
            "next_action": "发起库存调拨或释放可用库存，确认项目机号归属后再领料。",
            "downstream_impact": "未调拨会阻塞工单领料和投产。",
            "action_url": "/transfers/new",
            "estimated_ready_date": estimated_ready_date,
        }
    if suggestion_type == "production":
        return {
            "kitting_state": "shortage",
            "kitting_state_label": "需生产",
            "blocked_reason": f"{material} 为自制件，净缺口 {net_qty}。",
            "owner_role": "生产计划",
            "next_action": "生成或跟进下阶工单，确认下阶齐套、报工和完工入库日期。",
            "downstream_impact": "下阶工单未完成会影响本工单装配、调试和交付。",
            "action_url": "/work-orders/new",
            "estimated_ready_date": estimated_ready_date,
        }
    if suggestion_type == "outsource":
        return {
            "kitting_state": "shortage",
            "kitting_state_label": "需委外",
            "blocked_reason": f"{material} 需要委外补齐，净缺口 {net_qty}。",
            "owner_role": "委外采购/计划",
            "next_action": "生成或跟进委外订单，确认发料、到货、短收/报废和应付影响。",
            "downstream_impact": "委外未回厂会影响工单齐套、成本归集和项目交付。",
            "action_url": "/subcontract/new",
            "estimated_ready_date": estimated_ready_date,
        }
    return {
        "kitting_state": "shortage",
        "kitting_state_label": "需采购",
        "blocked_reason": f"{material} 净缺口 {net_qty}，库存和已有在途无法覆盖。",
        "owner_role": "采购/计划",
        "next_action": "将 MRP 建议转采购申请，确认供应商、需求日期和采购订单到货承诺。",
        "downstream_impact": "未形成采购闭环会阻塞工单领料、投产和项目交付。",
        "action_url": "/mrp/suggestions?suggestion_type=purchase&status=open",
        "estimated_ready_date": estimated_ready_date,
    }


def _resolve_bom_id(query_one, product_id, bom_id=None) -> Optional[int]:
    """Resolve the BOM id to use: explicit, or default production BOM for the product."""
    if bom_id:
        return int(bom_id)
    if not product_id:
        return None
    row = query_one(
        """
        SELECT id FROM boms
        WHERE product_id=%s
          AND COALESCE(status, '') NOT IN ('停用','inactive','disabled')
        ORDER BY
            CASE WHEN bom_type='production' THEN 0 ELSE 1 END,
            id DESC
        LIMIT 1
        """,
        (product_id,),
    ) or {}
    return int(row.get("id")) if row.get("id") else None


def expand_bom_multi_level(
    query_one,
    query_rows,
    product_id,
    bom_id=None,
    bom_version_id: Optional[int] = None,
    level: int = 0,
    parent_material_id: Optional[int] = None,
    project_code: Optional[str] = None,
    serial_no: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Recursively expand BOM. Returns flat list of BOM rows across all levels."""
    rows: List[Dict[str, Any]] = []
    if not product_id:
        return rows
    resolved_bom_id = _resolve_bom_id(query_one, product_id, bom_id)
    if not resolved_bom_id:
        return rows
    bom_items = query_rows(
        """
        SELECT bi.id AS bom_item_id, bi.product_id,
               COALESCE(bi.quantity, 0) AS base_qty,
               COALESCE(bi.loss_rate, 0) AS loss_rate,
               COALESCE(bi.unit, p.unit, '') AS material_unit,
               bi.is_optional,
               p.code AS material_code, p.name AS material_name,
               p.specification AS material_spec,
               COALESCE(p.purchase_lead_days, 0) AS lead_time_days,
               COALESCE(p.safety_stock, 0) AS safety_stock
        FROM bom_items bi
        LEFT JOIN products p ON p.id=bi.product_id
        WHERE bi.bom_id=%s
        ORDER BY bi.id
        """,
        (resolved_bom_id,),
    ) or []
    for raw in bom_items:
        item = dict(raw)
        child_product_id = item.get("product_id")
        procurement_type = _product_procurement_type(query_one, child_product_id)
        is_manufactured = procurement_type == "manufactured"
        row = {
            "product_id": child_product_id,
            "material_code": item.get("material_code") or "",
            "material_name": item.get("material_name") or "",
            "material_spec": item.get("material_spec") or "",
            "material_unit": item.get("material_unit") or "",
            "bom_level": level,
            "base_qty": _as_decimal(item.get("base_qty")),
            "loss_rate": _as_decimal(item.get("loss_rate")),
            "lead_time_days": int(item.get("lead_time_days") or 0),
            "safety_stock": _as_decimal(item.get("safety_stock")),
            "source_bom_item_id": item.get("bom_item_id"),
            "parent_material_id": parent_material_id,
            "is_manufactured": is_manufactured,
            "procurement_type": procurement_type,
            "is_optional": bool(item.get("is_optional")),
        }
        rows.append(row)
        if is_manufactured and child_product_id and level < 10:
            child_rows = expand_bom_multi_level(
                query_one,
                query_rows,
                child_product_id,
                bom_id=None,
                bom_version_id=bom_version_id,
                level=level + 1,
                parent_material_id=child_product_id,
                project_code=project_code,
                serial_no=serial_no,
            )
            rows.extend(child_rows)
    return rows


def calculate_net_requirements(
    query_one,
    query_rows,
    bom_rows: List[Dict[str, Any]],
    quantity,
    project_code: Optional[str] = None,
    serial_no: Optional[str] = None,
    required_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """For each BOM row, compute gross / available / net qty and suggestion type.

    Time-phased MRP (B-1 enhancement):
      - Each BOM row carries a lead_time_days (from products.purchase_lead_days).
      - The required_date for a child material is the parent due date minus the
        child's lead time, offset further by the BOM level (deeper levels need
        to be ready earlier so their parent can be produced).
      - Safety stock (products.safety_stock) is subtracted from available
        inventory when computing net requirements, so MRP will suggest
        replenishment to restore the safety buffer.

    When the main material has a shortage (net_qty > 0), the engine checks
    approved auto-substitute materials in priority order. If a substitute's
    available inventory can cover the remaining shortage, the main material's
    net_qty is reduced and the substitute usage is recorded in the result row.
    """
    parent_qty = _as_decimal(quantity)
    parent_due_date = required_date or date.today()
    result: List[Dict[str, Any]] = []
    for row in bom_rows:
        product_id = row.get("product_id")
        base_qty = _as_decimal(row.get("base_qty"))
        loss_rate = _as_decimal(row.get("loss_rate"))
        gross_qty = base_qty * parent_qty * (Decimal("1") + loss_rate / Decimal("100"))
        if not product_id or gross_qty <= 0:
            continue
        inventory = _inventory_quantities(query_one, product_id, project_code, serial_no)
        available_qty = inventory["available_qty"]
        locked_qty = inventory["locked_qty"]
        purchase_on_order_qty = _purchase_on_order_qty(query_one, product_id, project_code, serial_no)
        purchase_requisition_qty = _purchase_requisition_qty(query_one, product_id, project_code, serial_no)
        outsource_on_order_qty = _outsource_on_order_qty(query_one, product_id, project_code, serial_no)
        production_on_order_qty = _production_on_order_qty(query_one, product_id, project_code, serial_no)
        other_project_available = _inventory_available_other_projects(query_one, product_id, project_code, serial_no)
        supply_dates = _supply_commitment_dates(query_one, product_id, project_code, serial_no)

        # Safety stock: subtract from available inventory so MRP suggests
        # replenishment to preserve the safety buffer.
        safety_stock = _as_decimal(row.get("safety_stock"))
        effective_available = available_qty - safety_stock
        effective_available = effective_available if effective_available > 0 else Decimal("0")

        deducted = (
            effective_available
            + purchase_on_order_qty
            + purchase_requisition_qty
            + outsource_on_order_qty
            + production_on_order_qty
        )
        net_qty = gross_qty - deducted
        net_qty = net_qty if net_qty > 0 else Decimal("0")

        # Time-phased required date: parent due date minus lead time, offset
        # by BOM level so deeper-level components are ready earlier.
        lead_time_days = int(row.get("lead_time_days") or 0)
        bom_level = int(row.get("bom_level") or 0)
        # Total offset = own lead time * (bom_level + 1) so multi-level
        # assemblies schedule raw materials earlier.
        total_offset_days = lead_time_days * (bom_level + 1)
        item_required_date = parent_due_date - timedelta(days=total_offset_days)

        # 替代料逻辑：主料缺料时按优先级尝试已审批的自动替代料
        substitute_used = None
        if net_qty > 0 and row.get("source_bom_item_id"):
            try:
                substitutes = list_substitutes_for_product(
                    query_rows, row["source_bom_item_id"], only_approved=True
                )
            except Exception:
                logger.warning("list_substitutes_for_product failed for bom_item_id=%s", row.get("source_bom_item_id"), exc_info=True)
                substitutes = []
            for sub in substitutes:
                if not sub.get("allow_auto_substitute"):
                    continue
                sub_product_id = sub.get("substitute_product_id")
                if not sub_product_id:
                    continue
                sub_ratio = _as_decimal(sub.get("ratio")) or Decimal("1")
                sub_needed_qty = net_qty * sub_ratio
                sub_inventory = _inventory_quantities(
                    query_one, sub_product_id, project_code, serial_no
                )
                sub_available = sub_inventory["available_qty"]
                if sub_available >= sub_needed_qty:
                    substitute_used = {
                        "product_id": sub_product_id,
                        "code": sub.get("substitute_code") or "",
                        "name": sub.get("substitute_name") or "",
                        "spec": sub.get("substitute_spec") or "",
                        "unit": sub.get("substitute_unit") or "",
                        "priority": sub.get("priority") or 1,
                        "ratio": sub_ratio,
                        "qty": sub_needed_qty,
                    }
                    net_qty = Decimal("0")
                    break

        procurement_type = row.get("procurement_type") or _product_procurement_type(query_one, product_id)
        if net_qty <= 0:
            suggestion_type = "covered"
        elif other_project_available > 0 and other_project_available >= net_qty:
            suggestion_type = "transfer"
        elif procurement_type == "manufactured":
            suggestion_type = "production"
        else:
            suggestion_type = "purchase"
        result_row = {
            "product_id": product_id,
            "material_code": row.get("material_code") or "",
            "material_name": row.get("material_name") or "",
            "material_spec": row.get("material_spec") or "",
            "material_unit": row.get("material_unit") or "",
            "bom_level": bom_level,
            "base_qty": base_qty,
            "loss_rate": loss_rate,
            "lead_time_days": lead_time_days,
            "safety_stock": safety_stock,
            "gross_qty": gross_qty,
            "available_qty": available_qty,
            "effective_available_qty": effective_available,
            "locked_qty": locked_qty,
            "purchase_on_order_qty": purchase_on_order_qty,
            "purchase_requisition_qty": purchase_requisition_qty,
            "outsource_on_order_qty": outsource_on_order_qty,
            "production_on_order_qty": production_on_order_qty,
            "other_project_available": other_project_available,
            "net_qty": net_qty,
            "suggestion_type": suggestion_type,
            "required_date": item_required_date,
            "source_bom_item_id": row.get("source_bom_item_id"),
            "parent_material_id": row.get("parent_material_id"),
            "is_manufactured": bool(row.get("is_manufactured")),
            "project_code": project_code,
            "serial_no": serial_no,
            "substitute_used": substitute_used,
            "supply_dates": supply_dates,
        }
        result_row.update(_kitting_action_fields(result_row, net_qty, suggestion_type))
        result.append(result_row)
    return result


SUGGESTION_LABELS = {
    "covered": "已覆盖",
    "purchase": "建议采购",
    "production": "建议生产",
    "transfer": "建议调拨",
    "outsource": "建议委外",
}


def suggestion_label(suggestion_type: str) -> str:
    """Return the Chinese display label for a given MRP suggestion type."""
    return SUGGESTION_LABELS.get(suggestion_type or "", "未定义")


def _generate_run_no(query_one) -> str:
    """Generate run number in format MRP-YYYYMMDD-NNN."""
    today = datetime.now()
    prefix = f"MRP-{today:%Y%m%d}-"
    row = query_one(
        "SELECT run_no FROM mrp_runs WHERE run_no LIKE %s ORDER BY run_no DESC LIMIT 1",
        (f"{prefix}%",),
    ) or {}
    last_no = (row.get("run_no") or "").replace(prefix, "")
    try:
        next_seq = int(last_no or "0") + 1
    except ValueError:
        next_seq = 1
    return f"{prefix}{next_seq:03d}"


def run_mrp(
    query_one,
    query_rows,
    execute_db,
    execute_and_return,
    *,
    source_type: str,
    source_id: Optional[int] = None,
    source_no: Optional[str] = None,
    project_code: Optional[str] = None,
    serial_no: Optional[str] = None,
    bom_id: Optional[int] = None,
    bom_version_id: Optional[int] = None,
    quantity=1,
    required_date: Optional[date] = None,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Main MRP entry point. Executes a run and persists results.

    The required_date (demand due date) drives time-phased MRP: child
    components' required dates are back-scheduled from this date using
    each material's purchase_lead_days and BOM level. When not supplied,
    the engine derives it from the source document (work order planned
    completion date, sales order delivery date) or defaults to today.
    """
    parent_qty = _as_decimal(quantity)
    if parent_qty <= 0:
        return {"status": "error", "message": "数量必须大于 0"}
    if source_type == "work_order" and source_id:
        wo = query_one(
            "SELECT id, wo_no, product_id, bom_id, quantity, project_code, serial_no, status, planned_completion_date FROM work_orders WHERE id=%s",
            (source_id,),
        ) or {}
        if not wo:
            return {"status": "error", "message": "工单不存在"}
        product_id = wo.get("product_id")
        if not bom_id:
            bom_id = wo.get("bom_id")
        if not project_code:
            project_code = wo.get("project_code")
        if not serial_no:
            serial_no = wo.get("serial_no")
        if not source_no:
            source_no = wo.get("wo_no")
        if parent_qty <= 0:
            parent_qty = _as_decimal(wo.get("quantity"))
        # Derive required date from work order planned completion date.
        if not required_date and wo.get("planned_completion_date"):
            required_date = wo.get("planned_completion_date")
    elif source_type == "product":
        product_id = source_id
    elif source_type == "sales_order" and source_id:
        so = query_one(
            "SELECT id, order_no, project_code, serial_no, delivery_date FROM sales_orders WHERE id=%s",
            (source_id,),
        ) or {}
        if not so:
            return {"status": "error", "message": "销售订单不存在"}
        # sales_orders 表无 product_id/quantity 字段，需从 sales_order_items 取首行
        so_item = query_one(
            "SELECT product_id, quantity FROM sales_order_items WHERE order_id=%s ORDER BY id LIMIT 1",
            (source_id,),
        ) or {}
        if not so_item:
            return {"status": "error", "message": "销售订单无明细行，无法展开 BOM"}
        product_id = so_item.get("product_id")
        if not source_no:
            source_no = so.get("order_no")
        if not project_code:
            project_code = so.get("project_code")
        if not serial_no:
            serial_no = so.get("serial_no")
        if parent_qty <= 0:
            parent_qty = _as_decimal(so_item.get("quantity"))
        # Derive required date from sales order delivery date.
        if not required_date and so.get("delivery_date"):
            required_date = so.get("delivery_date")
    else:
        product_id = source_id
    if not product_id:
        return {"status": "error", "message": "未指定物料或来源"}

    # Resolve BOM id if not yet set (for sales_order / product sources).
    if not bom_id:
        bom_id = _resolve_bom_id(query_one, product_id)

    # Auto-resolve the released BOM version when not explicitly supplied.
    # This ties MRP results to a specific released BOM version per P0-4 acceptance.
    if not bom_version_id and bom_id:
        active_version = _get_active_bom_version(query_one, bom_id)
        if active_version:
            bom_version_id = active_version.get("id")

    # P5-B1: 当来源为工单时，自动创建 BOM 快照，绑定 MRP 运行与 BOM 版本快照
    bom_snapshot_id: Optional[int] = None
    if source_type == "work_order" and source_id:
        try:
            snapshot = create_bom_snapshot(
                query_one,
                execute_db,
                execute_and_return,
                source_id,
                bom_version_id=bom_version_id,
            )
            if snapshot:
                bom_snapshot_id = snapshot.get("id")
        except Exception:
            # 快照创建失败不阻断 MRP 运行
            logger.warning("BOM snapshot creation failed during MRP run for source_id=%s", source_id, exc_info=True)
            bom_snapshot_id = None

    run_no = _generate_run_no(query_one)
    run_row = execute_and_return(
        """
        INSERT INTO mrp_runs
            (run_no, source_type, source_id, source_no, project_code, serial_no,
             bom_version_id, bom_snapshot_id, status, kitting_rate, total_gross_qty, total_net_qty,
             shortage_line_count, created_by, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            run_no,
            source_type,
            source_id,
            source_no,
            project_code,
            serial_no,
            bom_version_id,
            bom_snapshot_id,
            "running",
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            0,
            created_by,
        ),
    ) or {}
    run_id = int(run_row.get("id"))

    bom_rows = expand_bom_multi_level(
        query_one,
        query_rows,
        product_id,
        bom_id=bom_id,
        bom_version_id=bom_version_id,
        level=0,
        parent_material_id=None,
        project_code=project_code,
        serial_no=serial_no,
    )
    net_rows = calculate_net_requirements(
        query_one,
        query_rows,
        bom_rows,
        parent_qty,
        project_code=project_code,
        serial_no=serial_no,
        required_date=required_date,
    )

    total_gross = Decimal("0")
    total_net = Decimal("0")
    shortage_count = 0
    substitute_count = 0
    for row in net_rows:
        substitute_used = row.get("substitute_used")
        substitute_for_id = substitute_used.get("product_id") if substitute_used else None
        execute_db(
            """
            INSERT INTO mrp_run_items
                (run_id, material_id, material_code, material_name, material_spec, material_unit,
                 bom_level, gross_qty, available_qty, locked_qty, reserved_qty,
                 purchase_on_order_qty, production_on_order_qty, outsource_on_order_qty,
                 net_qty, suggestion_type, required_date, project_code, serial_no,
                 source_bom_item_id, parent_material_id, loss_rate, substitute_for, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            """,
            (
                run_id,
                row.get("product_id"),
                row.get("material_code"),
                row.get("material_name"),
                row.get("material_spec"),
                row.get("material_unit"),
                row.get("bom_level"),
                row.get("gross_qty"),
                row.get("available_qty"),
                row.get("locked_qty"),
                Decimal("0"),
                row.get("purchase_on_order_qty"),
                row.get("production_on_order_qty"),
                row.get("outsource_on_order_qty"),
                row.get("net_qty"),
                row.get("suggestion_type"),
                row.get("required_date"),
                row.get("project_code"),
                row.get("serial_no"),
                row.get("source_bom_item_id"),
                row.get("parent_material_id"),
                row.get("loss_rate"),
                substitute_for_id,
            ),
        )
        total_gross += _as_decimal(row.get("gross_qty"))
        net_qty = _as_decimal(row.get("net_qty"))
        total_net += net_qty
        if substitute_used:
            substitute_count += 1
        if net_qty > 0:
            shortage_count += 1
            execute_db(
                """
                INSERT INTO mrp_suggestions
                    (run_id, suggestion_type, material_id, material_code, material_name,
                     qty, required_date, project_code, serial_no, status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                """,
                (
                    run_id,
                    row.get("suggestion_type"),
                    row.get("product_id"),
                    row.get("material_code"),
                    row.get("material_name"),
                    net_qty,
                    row.get("required_date"),
                    row.get("project_code"),
                    row.get("serial_no"),
                    "open",
                ),
            )

    line_count = len(net_rows)
    covered_count = line_count - shortage_count
    kitting_rate = Decimal("0")
    if line_count > 0:
        kitting_rate = (Decimal(str(covered_count)) / Decimal(str(line_count)) * Decimal("100")).quantize(Decimal("0.01"))

    execute_db(
        """
        UPDATE mrp_runs
        SET status=%s, kitting_rate=%s, total_gross_qty=%s, total_net_qty=%s, shortage_line_count=%s
        WHERE id=%s
        """,
        ("completed", kitting_rate, total_gross, total_net, shortage_count, run_id),
    )

    return {
        "status": "ok",
        "run_id": run_id,
        "run_no": run_no,
        "required_date": required_date,
        "line_count": line_count,
        "shortage_line_count": shortage_count,
        "covered_line_count": covered_count,
        "substitute_count": substitute_count,
        "total_gross_qty": total_gross,
        "total_net_qty": total_net,
        "kitting_rate": kitting_rate,
        "bom_snapshot_id": bom_snapshot_id,
    }


def get_mrp_run(query_one, run_id: int) -> Dict[str, Any]:
    """Get run header (use get_mrp_run_detail for items + suggestions)."""
    header = query_one(
        """
        SELECT mr.*,
               u.username AS created_by_name
        FROM mrp_runs mr
        LEFT JOIN users u ON u.id=mr.created_by
        WHERE mr.id=%s
        """,
        (run_id,),
    ) or {}
    if not header:
        return {"status": "not_found", "header": None}
    return {"status": "ok", "header": dict(header)}


def get_mrp_run_detail(query_one, query_rows, run_id: int) -> Dict[str, Any]:
    """Get full run detail: header, items, suggestions."""
    header = query_one(
        """
        SELECT mr.*,
               u.username AS created_by_name
        FROM mrp_runs mr
        LEFT JOIN users u ON u.id=mr.created_by
        WHERE mr.id=%s
        """,
        (run_id,),
    ) or {}
    if not header:
        return {"status": "not_found", "header": None, "items": [], "suggestions": []}
    items = [
        dict(row)
        for row in (query_rows(
            """
            SELECT mri.*,
                   CASE mri.suggestion_type
                       WHEN 'covered' THEN '已覆盖'
                       WHEN 'purchase' THEN '建议采购'
                       WHEN 'production' THEN '建议生产'
                       WHEN 'transfer' THEN '建议调拨'
                       WHEN 'outsource' THEN '建议委外'
                       ELSE '未定义'
                   END AS suggestion_label
            FROM mrp_run_items mri
            WHERE mri.run_id=%s
            ORDER BY mri.bom_level, mri.id
            """,
            (run_id,),
        ) or [])
    ]
    suggestions = [
        dict(row)
        for row in (query_rows(
            """
            SELECT ms.*,
                   CASE ms.suggestion_type
                       WHEN 'purchase' THEN '建议采购'
                       WHEN 'production' THEN '建议生产'
                       WHEN 'transfer' THEN '建议调拨'
                       WHEN 'outsource' THEN '建议委外'
                       ELSE '未定义'
                   END AS suggestion_label
            FROM mrp_suggestions ms
            WHERE ms.run_id=%s
            ORDER BY ms.id
            """,
            (run_id,),
        ) or [])
    ]
    return {
        "status": "ok",
        "header": dict(header),
        "items": items,
        "suggestions": suggestions,
    }


def list_mrp_runs(query_rows, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """List MRP runs with optional filters (status, source_type, project_code, serial_no, keyword)."""
    filters = filters or {}
    where = []
    params: List[Any] = []
    if filters.get("status"):
        where.append("mr.status=%s")
        params.append(filters["status"])
    if filters.get("source_type"):
        where.append("mr.source_type=%s")
        params.append(filters["source_type"])
    if filters.get("project_code"):
        where.append("mr.project_code=%s")
        params.append(filters["project_code"])
    if filters.get("serial_no"):
        where.append("mr.serial_no=%s")
        params.append(filters["serial_no"])
    if filters.get("keyword"):
        where.append("(mr.run_no ILIKE %s OR mr.source_no ILIKE %s OR mr.project_code ILIKE %s OR mr.serial_no ILIKE %s)")
        kw = f"%{filters['keyword']}%"
        params.extend([kw, kw, kw, kw])
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = query_rows(
        f"""
        SELECT mr.id, mr.run_no, mr.source_type, mr.source_id, mr.source_no,
               mr.project_code, mr.serial_no, mr.status, mr.kitting_rate,
               mr.total_gross_qty, mr.total_net_qty, mr.shortage_line_count,
               mr.created_by, mr.created_at,
               u.username AS created_by_name
        FROM mrp_runs mr
        LEFT JOIN users u ON u.id=mr.created_by
        {where_sql}
        ORDER BY mr.created_at DESC, mr.id DESC
        LIMIT 300
        """,
        tuple(params),
    ) or []
    return [dict(row) for row in rows]


def get_mrp_suggestions(query_rows, run_id: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get suggestions, optionally filtered by run_id and/or status."""
    where = []
    params: List[Any] = []
    if run_id is not None:
        where.append("ms.run_id=%s")
        params.append(run_id)
    if status:
        where.append("ms.status=%s")
        params.append(status)
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = query_rows(
        f"""
        SELECT ms.id, ms.run_id, ms.suggestion_type, ms.material_id, ms.material_code,
               ms.material_name, ms.qty, ms.required_date, ms.project_code, ms.serial_no,
               ms.status, ms.converted_doc_type, ms.converted_doc_id, ms.converted_doc_no,
               ms.converted_at, ms.created_at,
               mr.run_no, mr.source_type, mr.source_no,
               CASE ms.suggestion_type
                   WHEN 'purchase' THEN '建议采购'
                   WHEN 'production' THEN '建议生产'
                   WHEN 'transfer' THEN '建议调拨'
                   WHEN 'outsource' THEN '建议委外'
                   ELSE '未定义'
               END AS suggestion_label
        FROM mrp_suggestions ms
        LEFT JOIN mrp_runs mr ON mr.id=ms.run_id
        {where_sql}
        ORDER BY ms.created_at DESC, ms.id DESC
        LIMIT 500
        """,
        tuple(params),
    ) or []
    return [dict(row) for row in rows]


def convert_suggestion(execute_db, execute_and_return, suggestion_id: int, doc_type: str, doc_id: int, doc_no: str) -> Dict[str, Any]:
    """Mark a suggestion as converted to a downstream document."""
    row = execute_and_return(
        """
        UPDATE mrp_suggestions
        SET status='converted',
            converted_doc_type=%s,
            converted_doc_id=%s,
            converted_doc_no=%s,
            converted_at=CURRENT_TIMESTAMP
        WHERE id=%s AND status='open'
        RETURNING id, run_id
        """,
        (doc_type, doc_id, doc_no, suggestion_id),
    ) or {}
    if not row:
        return {"status": "not_found_or_converted"}
    return {"status": "ok", "suggestion_id": suggestion_id, "run_id": row.get("run_id")}


def build_kitting_analysis(query_one, query_rows, work_order_id: int) -> Dict[str, Any]:
    """Build a kitting analysis for a work order: BOM coverage, shortage lines, kitting rate."""
    wo = query_one(
        """
        SELECT wo.id, wo.wo_no, wo.product_id, wo.bom_id, wo.quantity, wo.project_code, wo.serial_no,
               wo.status, p.code AS product_code, p.name AS product_name
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        WHERE wo.id=%s
        """,
        (work_order_id,),
    ) or {}
    if not wo:
        return {"status": "not_found", "header": None, "items": [], "summary": {}}
    bom_rows = expand_bom_multi_level(
        query_one,
        query_rows,
        wo.get("product_id"),
        bom_id=wo.get("bom_id"),
        project_code=wo.get("project_code"),
        serial_no=wo.get("serial_no"),
    )
    net_rows = calculate_net_requirements(
        query_one,
        query_rows,
        bom_rows,
        wo.get("quantity"),
        project_code=wo.get("project_code"),
        serial_no=wo.get("serial_no"),
    )
    line_count = len(net_rows)
    shortage_count = sum(1 for r in net_rows if _as_decimal(r.get("net_qty")) > 0)
    covered_count = line_count - shortage_count
    kitting_rate = Decimal("0")
    if line_count > 0:
        kitting_rate = (Decimal(str(covered_count)) / Decimal(str(line_count)) * Decimal("100")).quantize(Decimal("0.01"))
    total_gross = sum((_as_decimal(r.get("gross_qty")) for r in net_rows), Decimal("0"))
    total_net = sum((_as_decimal(r.get("net_qty")) for r in net_rows), Decimal("0"))
    shortage_rows = [r for r in net_rows if _as_decimal(r.get("net_qty")) > 0]
    ready_dates = [r.get("estimated_ready_date") for r in net_rows if r.get("estimated_ready_date")]
    shortage_ready_dates = [r.get("estimated_ready_date") for r in shortage_rows if r.get("estimated_ready_date")]
    earliest_ready_date = max(ready_dates) if ready_dates else None
    shortage_ready_date = max(shortage_ready_dates) if shortage_ready_dates else None
    if line_count <= 0:
        gate_status = "no_bom"
        gate_label = "未找到BOM"
        gate_reason = "该工单未找到可展开的生产BOM，不能执行齐套判断。"
        gate_next_action = "先维护生产BOM或选择正确BOM版本，再重新做齐套分析。"
    elif shortage_count:
        gate_status = "cannot_start"
        gate_label = "缺料不可投产"
        gate_reason = f"存在 {shortage_count} 行缺料，净缺口合计 {total_net}。"
        gate_next_action = "按缺料行责任分工处理采购、生产、委外或调拨，补齐后再领料投产。"
    else:
        gate_status = "can_start"
        gate_label = "齐套可投产"
        gate_reason = "BOM物料已被库存、在途、在制或替代料覆盖。"
        gate_next_action = "进入工单领料，核对项目号、机号、批次、库位后投产。"
    for r in net_rows:
        r["suggestion_label"] = suggestion_label(r.get("suggestion_type"))
    return {
        "status": "ok",
        "header": dict(wo),
        "items": net_rows,
        "summary": {
            "line_count": line_count,
            "shortage_line_count": shortage_count,
            "covered_line_count": covered_count,
            "kitting_rate": kitting_rate,
            "total_gross_qty": total_gross,
            "total_net_qty": total_net,
            "gate_status": gate_status,
            "gate_label": gate_label,
            "gate_reason": gate_reason,
            "gate_next_action": gate_next_action,
            "earliest_ready_date": earliest_ready_date,
            "shortage_ready_date": shortage_ready_date,
        },
    }
