"""After-sale service domain: warranty policy, service card, service order, and RMA helpers."""
from datetime import date, datetime
from decimal import Decimal


SERVICE_CLOSED_STATUSES = {"已关闭", "已完成", "已作废", "closed", "completed", "cancelled"}
RMA_CLOSED_STATUSES = {"已关闭", "已完成", "closed", "completed", "cancelled"}


def parse_date(value):
    """Parse a value into a date object, returning None on failure."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def money(value):
    """Convert a value to Decimal, returning Decimal('0') on failure."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def warranty_policy_for_card(card, today=None):
    today = today or date.today()
    start = parse_date(card.get("warranty_start_date"))
    end = parse_date(card.get("warranty_end_date"))
    if start and end:
        scope = "保内" if start <= today <= end else "保外"
        basis = f"质保期 {start.isoformat()} 至 {end.isoformat()}"
    elif start:
        scope = "待判定"
        basis = f"已记录质保开始 {start.isoformat()}，缺少质保结束日期"
    elif end:
        scope = "保内" if today <= end else "保外"
        basis = f"缺少质保开始日期，按质保结束 {end.isoformat()} 临时判断"
    else:
        scope = "待判定"
        basis = "服务档案缺少质保开始和结束日期"
    return {"scope": scope, "basis": basis}


def service_order_flow_fields(service, card=None):
    status = (service.get("status") or "").strip()
    warranty = warranty_policy_for_card(card or service)
    project_missing = not (service.get("project_code") or "").strip()
    cabinet_missing = not (service.get("cabinet_no") or "").strip()
    if status in SERVICE_CLOSED_STATUSES:
        return {
            "owner": "售后主管",
            "blocked_reason": "",
            "next_action": "服务单已关闭，按柜号成本报表复核成本",
            "downstream_impact": "进入售后成本和项目/柜号成本分析",
            "warranty_policy": warranty["scope"],
            "warranty_decision_basis": warranty["basis"],
        }
    if project_missing or cabinet_missing:
        blocked = "缺少项目号或柜号"
        next_action = "补齐项目号和柜号后继续派工、备件消耗和RMA"
    elif status in {"", "新建", "待派工", "open", "pending", "draft"}:
        blocked = ""
        next_action = "登记外勤派工计划"
    elif status in {"已派工"}:
        blocked = ""
        next_action = "登记现场处理、备件消耗和成本"
    elif status in {"处理中", "RMA处理中"}:
        blocked = ""
        next_action = "完成客户验收、回访或RMA索赔"
    elif status in {"已验收"}:
        blocked = ""
        next_action = "登记客户回访并准备关闭"
    elif status in {"已回访"}:
        blocked = ""
        next_action = "确认费用和RMA后关闭服务单"
    else:
        blocked = ""
        next_action = "按服务状态补齐处理记录"
    return {
        "owner": "售后内勤",
        "blocked_reason": blocked,
        "next_action": next_action,
        "downstream_impact": "影响客户验收、备件库存、RMA索赔和柜号售后成本",
        "warranty_policy": warranty["scope"],
        "warranty_decision_basis": warranty["basis"],
    }


def rma_flow_fields(rma):
    status = (rma.get("status") or "").strip()
    claim = (rma.get("claim_status") or "").strip()
    diagnosis_missing = not (rma.get("diagnosis") or "").strip()
    responsibility_missing = (rma.get("responsibility_type") or "").strip() in {"", "待判定"}
    recovered = money(rma.get("supplier_recovered_amount"))
    claim_amount = money(rma.get("supplier_claim_amount"))
    if status in RMA_CLOSED_STATUSES:
        next_action = "RMA已关闭，复核索赔追回和售后成本"
        blocked = ""
    elif diagnosis_missing or responsibility_missing:
        next_action = "完成故障诊断和责任判定"
        blocked = "缺少诊断或责任判定"
    elif claim_amount > recovered and claim not in {"不索赔", "已追回"}:
        next_action = "跟进供应商索赔和追回金额"
        blocked = "供应商索赔未追回"
    else:
        next_action = "确认关闭RMA"
        blocked = ""
    return {
        "owner": "售后/质量/采购",
        "blocked_reason": blocked,
        "next_action": next_action,
        "downstream_impact": "影响供应商索赔、售后损失抵减和柜号成本分析",
    }


def machine_service_cost_summary(service_orders, rmas):
    parts_cost = sum(money(row.get("parts_cost")) for row in service_orders or [])
    labor_cost = sum(money(row.get("labor_cost")) for row in service_orders or [])
    travel_cost = sum(money(row.get("travel_cost")) for row in service_orders or [])
    service_total = sum(money(row.get("total_cost")) for row in service_orders or [])
    supplier_claim = sum(money(row.get("supplier_claim_amount")) for row in rmas or [])
    supplier_recovered = sum(money(row.get("supplier_recovered_amount")) for row in rmas or [])
    net_cost = service_total - supplier_recovered
    return {
        "parts_cost": parts_cost,
        "labor_cost": labor_cost,
        "travel_cost": travel_cost,
        "service_total": service_total,
        "supplier_claim": supplier_claim,
        "supplier_recovered": supplier_recovered,
        "net_service_cost": net_cost,
    }
