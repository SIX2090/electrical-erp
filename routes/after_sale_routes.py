"""After-sale module routes: service card, service order, RMA, and installation acceptance."""


def _bom_display_text(row):
    parts = [row.get("bom_no") or row.get("default_bom_no"), row.get("bom_version") or row.get("default_bom_version")]
    return " / ".join(str(part) for part in parts if part) or "-"


def _manufacturing_control_text(row):
    labels = []
    if row.get("batch_control"):
        labels.append("批次")
    if row.get("serial_control"):
        labels.append("序列")
    if row.get("inspection_required"):
        labels.append("需检")
    return " / ".join(labels) if labels else "-"


def _decorate_trace(row):
    if row:
        row["bom_display"] = _bom_display_text(row)
        row["control_display"] = _manufacturing_control_text(row)
    return row


def _decorate_rows(rows):
    for row in rows or []:
        _decorate_trace(row)
    return rows


def render_after_sale_dashboard(query_rows, count_rows, columns, render_module_dashboard):
    metrics = [
        {"label": "服务档案", "value": count_rows("machine_service_cards"), "hint": "已建柜号档案"},
        {
            "label": "未关闭服务单",
            "value": count_rows("machine_service_orders", "COALESCE(status, '') NOT IN ('已关闭','已完成','closed','completed')"),
            "hint": "安装/维修/保养待处理",
        },
        {
            "label": "待验收项",
            "value": count_rows(
                "machine_service_acceptance_checks",
                "COALESCE(result, '') NOT IN ('合格','通过','已完成','passed')",
            ),
            "hint": "安装验收检查项",
        },
        {"label": "RMA", "value": count_rows("machine_service_rmas"), "hint": "返修/索赔闭环"},
    ]
    shortcuts = [
        {"label": "设备服务档案", "url": "/service-cards", "icon": "bi-card-checklist"},
        {"label": "安装验收", "url": "/service-acceptance", "icon": "bi-clipboard-check"},
        {"label": "服务单", "url": "/service-orders", "icon": "bi-wrench-adjustable"},
        {"label": "RMA", "url": "/service-rmas", "icon": "bi-arrow-repeat"},
    ]
    pending_queues = query_rows(
        """
        WITH rows AS (
            SELECT '待派工服务单' AS queue_name, COUNT(*) AS doc_count, MIN(service_date) AS oldest_date
            FROM machine_service_orders
            WHERE COALESCE(status, '') IN ('新建','待派工','open','')
            UNION ALL
            SELECT '待处理/待验收服务单', COUNT(*), MIN(service_date)
            FROM machine_service_orders
            WHERE COALESCE(status, '') IN ('已派工','待处理','处理中','RMA处理中')
            UNION ALL
            SELECT '待回访服务单', COUNT(*), MIN(service_date)
            FROM machine_service_orders so
            WHERE COALESCE(so.status, '') IN ('已验收','处理中')
              AND NOT EXISTS (
                  SELECT 1 FROM machine_service_return_visits rv WHERE rv.order_id=so.id
              )
            UNION ALL
            SELECT '待诊断/待索赔RMA', COUNT(*), MIN(rma_date)
            FROM machine_service_rmas
            WHERE COALESCE(status, '') NOT IN ('已关闭','已完成','closed','completed','cancelled')
        )
        SELECT queue_name, doc_count, oldest_date
        FROM rows
        WHERE doc_count > 0
        ORDER BY oldest_date NULLS LAST, queue_name
        """
    )
    queue_meta = {
        "待派工服务单": ("售后内勤", "补派工计划和现场任务", "服务单未进入执行，影响客户响应时效", "/service-orders"),
        "待处理/待验收服务单": ("售后工程师", "处理故障、登记验收和备件成本", "影响客户验收、服务成本和RMA判断", "/service-orders"),
        "待回访服务单": ("客服/售后内勤", "登记回访结果和满意度评分", "影响售后闭环和满意度追踪", "/service-return-visits"),
        "待诊断/待索赔RMA": ("售后/质量/采购", "诊断责任、确认索赔并关闭RMA", "影响供应商索赔和售后成本归集", "/service-rmas"),
    }
    for row in pending_queues:
        owner, next_action, impact, url = queue_meta.get(row.get("queue_name"), ("售后", "跟进闭环", "影响售后闭环", "/service-orders"))
        row["owner_role"] = owner
        row["next_action"] = next_action
        row["downstream_impact"] = impact
        row["list_url"] = url
        row["entry_link"] = "进入列表"
        row["id"] = None

    exception_rows = query_rows(
        """
        WITH rows AS (
            SELECT '缺项目号/柜号服务单' AS issue_type, COUNT(*) AS issue_count
            FROM machine_service_orders
            WHERE (COALESCE(project_code, '')='' OR COALESCE(cabinet_no, '')='')
              AND COALESCE(status, '') NOT IN ('已关闭','已完成','closed','completed','cancelled','已作废')
            UNION ALL
            SELECT '未结算可收费服务单', COUNT(*)
            FROM machine_service_orders
            WHERE COALESCE(billable_amount,0) > 0
              AND COALESCE(settlement_status,'') NOT IN ('已结算','已生成应收','已收款','closed','completed')
            UNION ALL
            SELECT '未通过安装验收项', COUNT(*)
            FROM machine_service_acceptance_checks
            WHERE COALESCE(result, '') NOT IN ('合格','通过','已完成','passed')
            UNION ALL
            SELECT '供应商索赔未追回', COUNT(*)
            FROM machine_service_rmas
            WHERE COALESCE(supplier_claim_amount,0) > COALESCE(supplier_recovered_amount,0)
        )
        SELECT issue_type, issue_count
        FROM rows
        WHERE issue_count > 0
        ORDER BY issue_count DESC, issue_type
        """
    )
    exception_meta = {
        "缺项目号/柜号服务单": ("售后内勤", "补齐推荐追溯字段", "影响项目/柜号成本和服务追溯", "/service-orders"),
        "未结算可收费服务单": ("售后/财务", "确认收费状态或生成应收", "影响应收和服务收入对账", "/service-orders"),
        "未通过安装验收项": ("售后现场", "补齐验收结论和整改记录", "影响质保起算和客户验收", "/service-acceptance"),
        "供应商索赔未追回": ("质量/采购", "跟进供应商索赔追回", "影响售后成本抵减口径", "/service-rmas"),
    }
    for row in exception_rows:
        owner, next_action, impact, url = exception_meta.get(row.get("issue_type"), ("售后", "处理异常", "影响售后闭环", "/service-orders"))
        row["owner_role"] = owner
        row["next_action"] = next_action
        row["downstream_impact"] = impact
        row["list_url"] = url
        row["entry_link"] = "进入列表"
        row["id"] = None

    cost_links = [
        {
            "report_name": "售后成本专题",
            "basis": "服务单 total_cost = parts_cost + labor_cost + travel_cost",
            "finance_link": "/service/reports/cost",
            "owner_role": "售后/财务",
            "downstream_impact": "用于售后服务明细和售后成本专题核对",
        },
        {
            "report_name": "项目/柜号成本明细",
            "basis": "按项目号、柜号读取服务单总成本，展示配件、人工、差旅构成",
            "finance_link": "/finance/reports/project-cost",
            "owner_role": "财务",
            "downstream_impact": "用于项目毛利、柜号成本和售后成本归集",
        },
        {
            "report_name": "应收关联",
            "basis": "服务单 billable_amount 与 receivable_id/settlement_status 关联",
            "finance_link": "/receivables",
            "owner_role": "财务",
            "downstream_impact": "用于收费服务的应收核对，不在工作台写单",
        },
    ]
    return render_module_dashboard(
        "售后工作台",
        "按待办队列、异常原因和财务/成本口径推进售后闭环；完整服务单、RMA、回访记录请进入对应列表。",
        metrics,
        shortcuts,
        [
            {
                "title": "售后待办队列",
                "rows": pending_queues,
                "columns": columns(
                    ("queue_name", "队列"),
                    ("doc_count", "数量"),
                    ("oldest_date", "最早日期"),
                    ("next_action", "下一步"),
                    ("owner_role", "责任"),
                    ("downstream_impact", "下游影响"),
                    ("entry_link", "列表入口"),
                ),
            },
            {
                "title": "售后异常",
                "rows": exception_rows,
                "columns": columns(
                    ("issue_type", "异常"),
                    ("issue_count", "数量"),
                    ("next_action", "下一步"),
                    ("owner_role", "责任"),
                    ("downstream_impact", "下游影响"),
                    ("entry_link", "列表入口"),
                ),
            },
            {
                "title": "成本与财务关联口径",
                "rows": cost_links,
                "columns": columns(
                    ("report_name", "关联报表/账"),
                    ("basis", "取数口径"),
                    ("finance_link", "入口"),
                    ("owner_role", "责任"),
                    ("downstream_impact", "下游影响"),
                ),
            },
        ],
    )


def render_service_rma_detail(
    rma_id,
    query_one,
    as_decimal,
    document_attachments,
    document_activity_logs,
    back_url="/service-rmas",
):
    from flask import render_template
    from routes.registry import _safe_rows

    rma = query_one(
        """
        SELECT r.*, so.order_no AS service_order_no, so.issue_summary AS service_issue,
               sc.cabinet_no AS card_cabinet_no, sc.machine_model, c.name AS customer_name,
               p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               wo.wo_no, sales.order_no AS sales_order_no,
               COALESCE(b.bom_no, default_bom.bom_no) AS bom_no,
               COALESCE(b.version, default_bom.version) AS bom_version
        FROM machine_service_rmas r
        LEFT JOIN machine_service_orders so ON so.id=r.order_id
        LEFT JOIN machine_service_cards sc ON sc.id=r.service_card_id
        LEFT JOIN customers c ON c.id=sc.customer_id
        LEFT JOIN products p ON p.id=sc.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN work_orders wo ON wo.id=sc.wo_id
        LEFT JOIN sales_orders sales ON sales.id=sc.sales_order_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        LEFT JOIN LATERAL (
            SELECT db.bom_no, db.version
            FROM boms db
            WHERE db.product_id=p.id AND COALESCE(db.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN db.bom_type='production' THEN 0 ELSE 1 END,
                db.id DESC
            LIMIT 1
        ) default_bom ON TRUE
        WHERE r.id=%s
        """,
        (rma_id,),
    )
    if not rma:
        return render_template("simple_detail.html", title="RMA详情", row=None, back_url=back_url, labels={})
    _decorate_trace(rma)
    rma_items = _safe_rows(
        """
        SELECT r.id, r.source_line_no, r.material_code, r.material_name,
               r.material_spec, r.material_unit, r.quantity, r.unit_cost,
               r.amount, r.warehouse_id, r.location_id,
               w.name AS warehouse_name, l.name AS location_name,
               r.lot_no, r.line_project_code, r.line_cabinet_no,
               r.project_code, r.cabinet_no,
               p.code AS product_code, p.name AS product_name,
               p.specification, p.unit
        FROM machine_service_rmas r
        LEFT JOIN products p ON p.id=r.product_id
        LEFT JOIN warehouses w ON w.id=r.warehouse_id
        LEFT JOIN locations l ON l.id=r.location_id
        WHERE r.id=%s
        """,
        (rma_id,),
    )
    final_statuses = {"已关闭", "已完成", "closed", "completed", "已作废", "cancelled"}
    can_operate = str(rma.get("status") or "") not in final_statuses
    if not can_operate:
        next_step = "RMA已关闭，只保留查看、附件和备注。"
    elif not rma.get("diagnosis"):
        next_step = "下一步：登记故障诊断和责任判断。"
    elif as_decimal(rma.get("supplier_claim_amount")) > as_decimal(rma.get("supplier_recovered_amount")):
        next_step = "下一步：跟进供应商索赔和追回金额。"
    else:
        next_step = "下一步：确认索赔和整改完成后关闭RMA。"
    return render_template(
        "service_rma_trace_detail.html",
        rma=rma,
        rma_items=rma_items,
        back_url=back_url,
        can_operate=can_operate,
        next_step=next_step,
        attachments=document_attachments("service_rma", rma_id),
        activity_logs=document_activity_logs("service_rma", rma),
    )


def render_service_order_detail(
    order_id,
    query_one,
    query_rows,
    as_decimal,
    inventory_document_product_options,
    document_attachments,
    document_activity_logs,
    load_document_custom_payload,
    back_url="/service-orders",
):
    from flask import render_template

    service = query_one(
        """
        SELECT so.*, sc.cabinet_no AS card_cabinet_no, sc.machine_model, c.name AS customer_name,
               c.contact_person, c.phone AS customer_phone, cr.source_no AS receivable_no,
               cr.balance AS receivable_balance,
               p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               wo.wo_no, sales.order_no AS sales_order_no,
               COALESCE(b.bom_no, default_bom.bom_no) AS bom_no,
               COALESCE(b.version, default_bom.version) AS bom_version
        FROM machine_service_orders so
        LEFT JOIN machine_service_cards sc ON sc.id=so.service_card_id
        LEFT JOIN customers c ON c.id=sc.customer_id
        LEFT JOIN customer_receivables cr ON cr.id=so.receivable_id
        LEFT JOIN products p ON p.id=sc.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN work_orders wo ON wo.id=sc.wo_id
        LEFT JOIN sales_orders sales ON sales.id=sc.sales_order_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        LEFT JOIN LATERAL (
            SELECT db.bom_no, db.version
            FROM boms db
            WHERE db.product_id=p.id AND COALESCE(db.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN db.bom_type='production' THEN 0 ELSE 1 END,
                db.id DESC
            LIMIT 1
        ) default_bom ON TRUE
        WHERE so.id=%s
        """,
        (order_id,),
    )
    if not service:
        return render_template("simple_detail.html", title="服务单详情", row=None, back_url=back_url, labels={})
    _decorate_trace(service)

    dispatches = query_rows(
        """
        SELECT id, dispatch_no, dispatch_date, planned_service_date, assigned_employee_id,
               support_employee_id, work_hours, travel_hours, status, task_summary, remark
        FROM machine_service_dispatches
        WHERE order_id=%s
        ORDER BY id DESC LIMIT 30
        """,
        (order_id,),
    )
    checklists = query_rows(
        """
        SELECT id, check_item, result, remark, created_at
        FROM machine_service_order_checklists
        WHERE order_id=%s
        ORDER BY id DESC
        LIMIT 50
        """,
        (order_id,),
    )
    return_visits = query_rows(
        """
            SELECT id, visit_no, visit_date, satisfaction, satisfaction_score, result, next_action, remark
        FROM machine_service_return_visits
        WHERE order_id=%s
        ORDER BY id DESC LIMIT 30
        """,
        (order_id,),
    )

    status = str(service.get("status") or "").strip()
    final_statuses = {"已关闭", "已完成", "closed", "completed", "作废", "已作废", "cancelled"}
    can_operate = status not in final_statuses
    if not can_operate:
        next_step = "服务单已结束，只保留查看、打印、附件和备注。"
    elif not dispatches:
        next_step = "下一步：先派工，明确计划服务日期和现场任务。"
    elif not checklists:
        next_step = "下一步：登记处理结果和服务检查。"
    elif not return_visits:
        next_step = "下一步：做客户验收/回访，确认问题是否闭环。"
    elif as_decimal(service.get("billable_amount")) > 0 and str(service.get("settlement_status") or "") not in {
        "已结算",
        "已生成应收",
        "已收款",
    }:
        next_step = "下一步：登记收费/结算状态。"
    else:
        next_step = "下一步：确认无遗留事项后关闭服务单。"

    context = {
        "back_url": back_url,
        "service": service,
        "can_operate": can_operate,
        "next_step": next_step,
        "dispatches": dispatches,
        "material_options": query_rows("SELECT id, code, name, standard_price FROM products ORDER BY code LIMIT 300"),
        "product_options": inventory_document_product_options(),
        "warehouse_options": query_rows("SELECT id, code, name FROM warehouses ORDER BY name LIMIT 200"),
        "location_options": query_rows(
            "SELECT id, warehouse_id, code, name FROM locations WHERE is_active=TRUE ORDER BY code LIMIT 300"
        ),
        "items": query_rows(
            """
            SELECT soi.id,
                   soi.product_id,
                   COALESCE(soi.material_code, p.code) AS product_code,
                   COALESCE(soi.material_name, p.name) AS product_name,
                   COALESCE(soi.material_spec, p.specification) AS specification,
                   COALESCE(soi.material_unit, p.unit) AS unit_name,
                   COALESCE(pc.name, p.category, '') AS product_family,
                   bom.bom_no AS default_bom_no,
                   bom.version AS default_bom_version,
                   COALESCE(p.batch_control, FALSE) AS batch_control,
                   COALESCE(p.serial_control, FALSE) AS serial_control,
                   COALESCE(p.inspection_required, FALSE) AS inspection_required,
                   wh.name AS warehouse_name,
                   loc.name AS location_name,
                   soi.quantity, soi.unit_cost, soi.amount, soi.lot_no,
                   soi.cabinet_no, soi.project_code, soi.source_line_no, soi.remark,
                   COALESCE(stock.stock_qty, 0) AS stock_qty,
                   COALESCE(stock.locked_qty, 0) AS locked_qty,
                   GREATEST(COALESCE(stock.stock_qty, 0) - COALESCE(stock.locked_qty, 0), 0) AS available_qty
            FROM machine_service_order_items soi
            LEFT JOIN products p ON p.id=soi.product_id
            LEFT JOIN product_categories pc ON pc.id=p.category_id
            LEFT JOIN warehouses wh ON wh.id=soi.warehouse_id
            LEFT JOIN locations loc ON loc.id=soi.location_id
            LEFT JOIN LATERAL (
                SELECT SUM(COALESCE(ib.quantity,0)) AS stock_qty,
                       SUM(COALESCE(ib.locked_qty,0)) AS locked_qty
                FROM inventory_balances ib
                WHERE ib.product_id=soi.product_id
                  AND (soi.warehouse_id IS NULL OR ib.warehouse_id=soi.warehouse_id)
                  AND (soi.location_id IS NULL OR ib.location_id=soi.location_id)
            ) stock ON TRUE
            LEFT JOIN LATERAL (
                SELECT b.bom_no, b.version
                FROM boms b
                WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
                ORDER BY
                    CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                    b.id DESC
                LIMIT 1
            ) bom ON TRUE
            WHERE soi.order_id=%s
            ORDER BY soi.id
            """,
            (order_id,),
        ),
        "checklists": checklists,
        "return_visits": return_visits,
        "rmas": query_rows(
            """
            SELECT id, rma_no, rma_date, warranty_scope, responsibility_type, status, claim_status, fault_summary
            FROM machine_service_rmas
            WHERE order_id=%s
            ORDER BY id DESC LIMIT 30
            """,
            (order_id,),
        ),
        "logs": query_rows(
            """
            SELECT id, service_date, service_type, performed_by, status, issue_summary, solution
            FROM machine_service_logs
            WHERE service_card_id=%s
            ORDER BY id DESC LIMIT 30
            """,
            (service.get("service_card_id"),),
        ),
        "attachments": document_attachments("service_order", order_id),
        "activity_logs": document_activity_logs("service_order", service),
        "custom_fields_payload": load_document_custom_payload("service_order_part", order_id),
    }
    context["cost_summary"] = {
        "parts_cost": as_decimal(service.get("parts_cost")),
        "labor_cost": as_decimal(service.get("labor_cost")),
        "travel_cost": as_decimal(service.get("travel_cost")),
        "total_cost": as_decimal(service.get("total_cost")),
        "billable_amount": as_decimal(service.get("billable_amount")),
        "receivable_no": service.get("receivable_no"),
        "settlement_status": service.get("settlement_status"),
        "basis": "服务单 total_cost = parts_cost + labor_cost + travel_cost；项目/柜号成本报表读取服务单总成本，库存流水按售后备件出库核对配件消耗。",
    }
    _decorate_rows(context["items"])
    return render_template("service_order_trace_detail.html", **context)


def render_service_card_detail(
    card_id,
    query_one,
    query_rows,
    document_attachments,
    document_activity_logs,
    back_url="/service-cards",
):
    from flask import render_template

    card = query_one(
        """
        SELECT sc.*, c.name AS customer_name, c.contact_person, c.phone AS customer_phone,
               p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               so.order_no AS sales_order_no,
               wo.wo_no,
               COALESCE(b.bom_no, default_bom.bom_no) AS bom_no,
               COALESCE(b.version, default_bom.version) AS bom_version
        FROM machine_service_cards sc
        LEFT JOIN customers c ON c.id=sc.customer_id
        LEFT JOIN products p ON p.id=sc.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN sales_orders so ON so.id=sc.sales_order_id
        LEFT JOIN work_orders wo ON wo.id=sc.wo_id
        LEFT JOIN boms b ON b.id=wo.bom_id
        LEFT JOIN LATERAL (
            SELECT db.bom_no, db.version
            FROM boms db
            WHERE db.product_id=p.id AND COALESCE(db.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN db.bom_type='production' THEN 0 ELSE 1 END,
                db.id DESC
            LIMIT 1
        ) default_bom ON TRUE
        WHERE sc.id=%s
        """,
        (card_id,),
    )
    if not card:
        return render_template("simple_detail.html", title="设备服务档案详情", row=None, back_url=back_url, labels={})
    _decorate_trace(card)

    context = {
        "back_url": back_url,
        "card": card,
        "orders": query_rows(
            """
            SELECT id, order_no, service_date, service_type, total_cost, billable_amount, settlement_status, status
            FROM machine_service_orders
            WHERE service_card_id=%s
            ORDER BY id DESC LIMIT 50
            """,
            (card_id,),
        ),
        "acceptances": query_rows(
            """
            SELECT id, acceptance_no, check_date, checklist_type, item_name, result, remark
            FROM machine_service_acceptance_checks
            WHERE service_card_id=%s
            ORDER BY id DESC LIMIT 50
            """,
            (card_id,),
        ),
        "dispatches": query_rows(
            """
            SELECT id, dispatch_no, dispatch_date, planned_service_date, status, work_hours, travel_hours, task_summary
            FROM machine_service_dispatches
            WHERE service_card_id=%s
            ORDER BY id DESC LIMIT 30
            """,
            (card_id,),
        ),
        "return_visits": query_rows(
            """
            SELECT id, visit_no, visit_date, satisfaction, satisfaction_score, result, next_action, remark
            FROM machine_service_return_visits
            WHERE service_card_id=%s
            ORDER BY id DESC LIMIT 30
            """,
            (card_id,),
        ),
        "rmas": query_rows(
            """
            SELECT id, rma_no, rma_date, warranty_scope, responsibility_type, status, claim_status
            FROM machine_service_rmas
            WHERE service_card_id=%s
            ORDER BY id DESC LIMIT 30
            """,
            (card_id,),
        ),
        "commissioning": query_rows(
            """
            SELECT id, record_date, parameter_category, parameter_name, parameter_value, unit, remark
            FROM machine_commissioning_parameters
            WHERE service_card_id=%s
            ORDER BY id DESC LIMIT 50
            """,
            (card_id,),
        ),
        "attachments": document_attachments("service_card", card_id),
        "activity_logs": document_activity_logs("service_card", card),
    }
    return render_template("service_card_trace_detail.html", **context)
