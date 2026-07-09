"""Production execution helpers: decimal conversion and operation status derivation."""
from __future__ import annotations

from decimal import Decimal


def as_decimal(value) -> Decimal:
    """Convert a value to Decimal, returning Decimal('0') on failure."""
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def operation_status_from_quantities(planned_qty, good_qty, rework_qty, scrap_qty, pause_count=0, start_count=0):
    """Derive the production operation status from planned and actual quantities."""
    planned = as_decimal(planned_qty)
    good = as_decimal(good_qty)
    rework = as_decimal(rework_qty)
    scrap = as_decimal(scrap_qty)
    if rework > 0:
        return "rework_pending"
    if scrap > 0:
        return "scrap_pending"
    if planned > 0 and good >= planned:
        return "completed"
    if pause_count:
        return "paused"
    if good > 0 or start_count:
        return "in_progress"
    return "not_started"


def operation_wip_qty(planned_qty, good_qty, scrap_qty=0):
    planned = as_decimal(planned_qty)
    good = as_decimal(good_qty)
    scrap = as_decimal(scrap_qty)
    remaining = planned - good - scrap
    return remaining if remaining > 0 else Decimal("0")


def execution_blocked_reason(status, blocked_reason="", rework_qty=0, scrap_qty=0, wip_qty=0):
    if blocked_reason:
        return blocked_reason
    if status == "rework_pending" or as_decimal(rework_qty) > 0:
        return "Rework is not dispositioned."
    if status == "scrap_pending" or as_decimal(scrap_qty) > 0:
        return "Scrap is not dispositioned."
    if status == "paused":
        return "Operation is paused and waiting for restart conditions."
    if as_decimal(wip_qty) > 0:
        return "Operation still has open WIP."
    return ""


def execution_next_action(status, wip_qty=0):
    if status == "completed":
        return "Prepare quality release and completion/inbound readiness check."
    if status == "rework_pending":
        return "Complete rework disposition and submit qualified operation report."
    if status == "scrap_pending":
        return "Confirm scrap responsibility, make-up plan, or work-order change."
    if status == "paused":
        return "Remove pause reason and restart operation reporting."
    if status == "in_progress":
        return "Continue reporting remaining operation quantity."
    if as_decimal(wip_qty) > 0:
        return "Dispatch operation and start operation reporting."
    return "Dispatch operation or confirm routing operation readiness."


def execution_downstream_impact(status, wip_qty=0, rework_qty=0, scrap_qty=0):
    if status == "completed":
        return "Supports quality release, completion inbound, shipment readiness, and work-order cost collection."
    if status == "rework_pending" or as_decimal(rework_qty) > 0:
        return "Blocks operation closure and may delay completion inbound and project delivery."
    if status == "scrap_pending" or as_decimal(scrap_qty) > 0:
        return "Affects make-up quantity, material consumption, delivery risk, and work-order cost collection."
    if status == "paused":
        return "Blocks work center load release and downstream operation start."
    if as_decimal(wip_qty) > 0:
        return "Leaves WIP open and may affect downstream operation, completion, and delivery."
    return "Waiting for production execution confirmation."


def status_label(status):
    return {
        "not_started": "待开工",
        "ready": "待开工",
        "in_progress": "执行中",
        "paused": "已暂停",
        "rework_pending": "返工待处理",
        "scrap_pending": "报废待处理",
        "completed": "已完工",
        "cancelled": "已取消",
    }.get(status or "", status or "-")
