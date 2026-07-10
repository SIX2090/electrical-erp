"""Procurement routes: purchase request list, request form, and request-to-order conversion."""
from datetime import datetime

from flask import render_template, request


INVALID_DOC_STATUSES = ("已作废", "作废", "cancelled", "canceled", "rejected", "已驳回")
FINISHED_DOC_STATUSES = ("已完成", "已关闭", "completed", "closed")


def _invalid_status_sql(alias="status"):
    return f"COALESCE({alias}, '') NOT IN {INVALID_DOC_STATUSES + FINISHED_DOC_STATUSES}"


def _engineering_ready_sql(project_expr, cabinet_expr):
    return f"""
    EXISTS (
        SELECT 1
        FROM engineering_technical_confirmations etc
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS item_count
            FROM bom_items bi
            WHERE bi.bom_id=etc.bom_id
        ) bom_items ON TRUE
        LEFT JOIN LATERAL (
            SELECT d.id
            FROM engineering_drawings d
            WHERE d.drawing_no=etc.drawing_no
              AND d.version=etc.drawing_version
              AND d.status='released'
              AND (d.effective_date IS NULL OR d.effective_date <= COALESCE(etc.confirm_date, CURRENT_DATE))
              AND (d.obsolete_date IS NULL OR d.obsolete_date > COALESCE(etc.confirm_date, CURRENT_DATE))
            LIMIT 1
        ) released_drawing ON TRUE
        WHERE (
                ({project_expr} <> '-' AND etc.project_code={project_expr})
                OR ({cabinet_expr} <> '-' AND etc.cabinet_no={cabinet_expr})
              )
          AND COALESCE(etc.status, '') IN ('已确认','confirmed','released')
          AND etc.bom_id IS NOT NULL
          AND etc.routing_id IS NOT NULL
          AND etc.work_center_id IS NOT NULL
          AND COALESCE(bom_items.item_count,0)>0
          AND released_drawing.id IS NOT NULL
    )
    """


def render_engineering_kitting_dashboard(
    query_one,
    query_rows,
    count_rows,
    sum_value,
    qty_metric,
    columns,
    render_module_dashboard,
):
    material_count = query_one(
        "SELECT COUNT(DISTINCT product_id) AS value FROM mrp_requirements WHERE COALESCE(shortage_quantity, 0) > 0"
    ) or {}
    project_count = query_one(
        """
        SELECT COUNT(*) AS value
        FROM (
            SELECT COALESCE(project_code, ''), COALESCE(cabinet_no, '')
            FROM mrp_requirements
            WHERE COALESCE(shortage_quantity, 0) > 0
            GROUP BY COALESCE(project_code, ''), COALESCE(cabinet_no, '')
        ) t
        """
    ) or {}
    metrics = [
        {"label": "缺料行", "value": count_rows("mrp_requirements", "COALESCE(shortage_quantity, 0) > 0"), "hint": "MRP 缺料明细行数"},
        {"label": "缺料物料", "value": material_count.get("value", 0), "hint": "按物料去重"},
        {
            "label": "采购未到",
            "value": qty_metric(sum_value("purchase_order_items", "GREATEST(COALESCE(quantity,0)-COALESCE(received_qty,0),0)")),
            "hint": "采购订单未收数量",
        },
        {"label": "未齐套项目", "value": project_count.get("value", 0), "hint": "按项目号/柜号归并"},
    ]
    shortcuts = [
        {"label": "MRP缺料", "url": "/production-enhance/mrp-requirements", "icon": "bi-exclamation-triangle"},
        {"label": "缺料转采购", "url": "/procurement/suggestions", "icon": "bi-lightbulb"},
        {"label": "采购申请", "url": "/purchase_request", "icon": "bi-card-checklist"},
        {"label": "工单列表", "url": "/work-orders", "icon": "bi-clipboard-check"},
    ]
    work_order_lateral = """
        LEFT JOIN LATERAL (
            SELECT STRING_AGG(wo.wo_no, ', ' ORDER BY wo.id DESC) AS work_order_no
            FROM (
                SELECT DISTINCT wo.id, wo.wo_no
                FROM work_orders wo
                WHERE (
                    NULLIF(mr.project_code, '') IS NOT NULL AND wo.project_code=mr.project_code
                ) OR (
                    NULLIF(mr.cabinet_no, '') IS NOT NULL AND wo.cabinet_no=mr.cabinet_no
                )
                ORDER BY wo.id DESC
                LIMIT 3
            ) wo
        ) source_wo ON TRUE
    """
    project_rows = query_rows(
        f"""
        SELECT MIN(mr.id) AS id,
               COALESCE(NULLIF(mr.project_code, ''), '-') AS project_code,
               COALESCE(NULLIF(mr.cabinet_no, ''), '-') AS cabinet_no,
               COALESCE(source_wo.work_order_no, '待关联工单') AS source_work_order,
               COUNT(*) AS shortage_lines,
               COUNT(DISTINCT mr.product_id) AS material_count,
               COALESCE(SUM(mr.shortage_quantity), 0) AS shortage_qty,
               MIN(mr.requirement_date) AS earliest_date,
               CASE
                   WHEN MIN(mr.requirement_date) IS NULL THEN '确认需求日期'
                   WHEN MIN(mr.requirement_date) < CURRENT_DATE THEN '处理逾期缺料'
                   WHEN MIN(mr.requirement_date) <= CURRENT_DATE + INTERVAL '7 days' THEN '优先处理本周缺料'
                   ELSE '生成采购申请'
               END AS next_action,
               '生产计划/采购' AS owner_role,
               '缺料影响齐套，需确认库存、在途采购和请购覆盖' AS blocked_reason,
               '影响工单领料、装配和交付' AS downstream_impact
        FROM mrp_requirements mr
        {work_order_lateral}
        WHERE COALESCE(mr.shortage_quantity, 0) > 0
        GROUP BY COALESCE(NULLIF(mr.project_code, ''), '-'), COALESCE(NULLIF(mr.cabinet_no, ''), '-'), source_wo.work_order_no
        ORDER BY shortage_lines DESC, shortage_qty DESC
        LIMIT 30
        """
    )
    material_rows = query_rows(
        """
        SELECT MIN(mr.id) AS id, p.code AS product_code, p.name AS product_name,
               p.specification, COALESCE(p.unit, mr.unit, '') AS unit,
               COUNT(*) AS project_lines,
               COALESCE(SUM(mr.quantity), 0) AS required_qty,
               COALESCE(SUM(mr.available_quantity), 0) AS available_qty,
               COALESCE(SUM(mr.shortage_quantity), 0) AS shortage_qty,
               CASE WHEN COALESCE(p.default_supplier_name, '') <> '' THEN '生成采购申请' ELSE '维护供应商' END AS next_action,
               CASE WHEN COALESCE(p.default_supplier_name, '') <> '' THEN '采购' ELSE '基础资料/采购' END AS owner_role,
               CASE WHEN COALESCE(p.default_supplier_name, '') <> '' THEN '缺料待转请购' ELSE '缺少默认供应商或价格' END AS blocked_reason
        FROM mrp_requirements mr
        LEFT JOIN products p ON p.id=mr.product_id
        WHERE COALESCE(mr.shortage_quantity, 0) > 0
        GROUP BY p.code, p.name, p.specification, COALESCE(p.unit, mr.unit, ''), COALESCE(p.default_supplier_name, '')
        ORDER BY shortage_qty DESC
        LIMIT 40
        """
    )
    detail_rows = query_rows(
        f"""
        SELECT mr.id, mr.requirement_date, mr.project_code, mr.cabinet_no,
               COALESCE(source_wo.work_order_no, '待关联工单') AS source_work_order,
               p.code AS product_code, p.name AS product_name,
               mr.quantity, mr.available_quantity, mr.shortage_quantity, mr.status,
               CASE
                   WHEN mr.requirement_date IS NOT NULL AND mr.requirement_date < CURRENT_DATE THEN '逾期缺料'
                   WHEN mr.requirement_date IS NOT NULL AND mr.requirement_date <= CURRENT_DATE + INTERVAL '7 days' THEN '本周缺料'
                   ELSE '待采购处理'
               END AS next_action,
               '生产计划/采购' AS owner_role,
               '缺料未覆盖' AS blocked_reason
        FROM mrp_requirements mr
        LEFT JOIN products p ON p.id=mr.product_id
        {work_order_lateral}
        WHERE COALESCE(mr.shortage_quantity, 0) > 0
        ORDER BY mr.requirement_date NULLS LAST, mr.id DESC
        LIMIT 60
        """
    )
    return render_module_dashboard(
        "齐套检查",
        "按来源工单、项目号、柜号和物料缺料跟踪齐套状态；查询页只展示缺料、责任、堵点和下一步，缺料转采购进入受控采购建议。",
        metrics,
        shortcuts,
        [
            {
                "title": "按项目/柜号缺料",
                "rows": project_rows,
                "columns": columns(
                    ("source_work_order", "来源工单"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("shortage_lines", "缺料行"),
                    ("material_count", "物料数"),
                    ("shortage_qty", "缺料数量"),
                    ("earliest_date", "最早需求"),
                    ("owner_role", "责任"),
                    ("blocked_reason", "堵点/条件"),
                    ("next_action", "下一步"),
                ),
            },
            {
                "title": "缺料物料汇总",
                "rows": material_rows,
                "columns": columns(
                    ("product_code", "物料编码"),
                    ("product_name", "物料名称"),
                    ("specification", "规格"),
                    ("unit", "单位"),
                    ("project_lines", "项目行"),
                    ("required_qty", "需求"),
                    ("available_qty", "可用"),
                    ("shortage_qty", "缺料"),
                    ("owner_role", "责任"),
                    ("blocked_reason", "堵点/条件"),
                    ("next_action", "下一步"),
                ),
            },
            {
                "title": "缺料明细",
                "rows": detail_rows,
                "columns": columns(
                    ("source_work_order", "来源工单"),
                    ("requirement_date", "需求日期"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("product_code", "物料编码"),
                    ("product_name", "物料名称"),
                    ("specification", "规格"),
                    ("unit", "单位"),
                    ("shortage_quantity", "缺料"),
                    ("owner_role", "责任"),
                    ("blocked_reason", "堵点/条件"),
                    ("next_action", "下一步"),
                ),
                "detail_base": "/production-enhance/mrp-requirements",
            },
        ],
    )


def purchase_suggestion_rows(query_rows, limit=120, keyword=""):
    keyword = (keyword or "").strip()
    keyword_sql = ""
    params = []
    if keyword:
        keyword_sql = """
              AND (
                  mr.project_code ILIKE %s
                  OR mr.cabinet_no ILIKE %s
                  OR mp.code ILIKE %s
                  OR mp.name ILIKE %s
              )
        """
        params.extend([f"%{keyword}%"] * 4)
    params.append(limit)
    return query_rows(
        f"""
        WITH mrp AS (
            SELECT mr.product_id,
                   COALESCE(NULLIF(mr.project_code, ''), '-') AS project_code,
                   COALESCE(NULLIF(mr.cabinet_no, ''), '-') AS cabinet_no,
                   MIN(mr.requirement_date) AS need_date,
                   MAX(NULLIF(mr.supply_mode, '')) AS supply_mode,
                   COALESCE(SUM(mr.shortage_quantity), 0) AS mrp_shortage_qty,
                   COUNT(*) AS mrp_lines
            FROM mrp_requirements mr
            LEFT JOIN products mp ON mp.id=mr.product_id
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
            {keyword_sql}
            GROUP BY mr.product_id, COALESCE(NULLIF(mr.project_code, ''), '-'), COALESCE(NULLIF(mr.cabinet_no, ''), '-')
        ),
        req AS (
            SELECT pri.product_id,
                   COALESCE(NULLIF(pri.project_code, ''), '-') AS project_code,
                   COALESCE(NULLIF(pri.cabinet_no, ''), '-') AS cabinet_no,
                   COALESCE(SUM(GREATEST(COALESCE(pri.quantity, 0), 0)), 0) AS requested_qty,
                   MAX(pr.id) AS purchase_request_id
            FROM purchase_requisition_items pri
            LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
            WHERE {_invalid_status_sql("pr.status")}
            GROUP BY pri.product_id, COALESCE(NULLIF(pri.project_code, ''), '-'), COALESCE(NULLIF(pri.cabinet_no, ''), '-')
        ),
        po AS (
            SELECT poi.product_id,
                   COALESCE(NULLIF(po.project_code, ''), '-') AS project_code,
                   COALESCE(NULLIF(po.cabinet_no, ''), '-') AS cabinet_no,
                   COALESCE(SUM(GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0)), 0) AS pending_po_qty,
                   MIN(po.expected_date) FILTER (
                       WHERE GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0) > 0
                   ) AS expected_arrival_date
            FROM purchase_order_items poi
            LEFT JOIN purchase_orders po ON po.id=poi.order_id
            WHERE {_invalid_status_sql("po.status")}
            GROUP BY poi.product_id, COALESCE(NULLIF(po.project_code, ''), '-'), COALESCE(NULLIF(po.cabinet_no, ''), '-')
        ),
        best_supplier AS (
            SELECT DISTINCT ON (sp.product_id) sp.product_id, sp.supplier_id, s.name AS supplier_name,
                   sp.unit_price, sp.lead_time_days, sp.supplier_item_code
            FROM supplier_prices sp
            LEFT JOIN suppliers s ON s.id=sp.supplier_id
            WHERE COALESCE(sp.is_active, TRUE)=TRUE
            ORDER BY sp.product_id, COALESCE(sp.is_primary, FALSE) DESC, sp.effective_date DESC NULLS LAST, sp.id DESC
        )
        SELECT ROW_NUMBER() OVER (
                   ORDER BY GREATEST(mrp.mrp_shortage_qty-COALESCE(req.requested_qty,0)-COALESCE(po.pending_po_qty,0),0) DESC,
                            mrp.need_date NULLS LAST
               ) AS id,
               mrp.product_id,
               p.code AS product_code,
               p.name AS product_name,
               p.specification,
               COALESCE(p.unit, '') AS unit,
               mrp.project_code,
               mrp.cabinet_no,
               COALESCE(source_wo.work_order_no, '待关联工单') AS source_work_order,
               COALESCE(mrp.supply_mode, '') AS supply_mode,
               mrp.need_date,
               mrp.mrp_lines,
               mrp.mrp_shortage_qty,
               GREATEST(mrp.mrp_shortage_qty-COALESCE(req.requested_qty,0)-COALESCE(po.pending_po_qty,0),0) AS uncovered_shortage_qty,
               COALESCE(req.requested_qty, 0) AS requested_qty,
               COALESCE(req.purchase_request_id, 0) AS purchase_request_id,
               COALESCE(po.pending_po_qty, 0) AS pending_po_qty,
               COALESCE(
                   po.expected_arrival_date,
                   CASE
                       WHEN COALESCE(best_supplier.lead_time_days, p.purchase_lead_days, 0) > 0
                       THEN CURRENT_DATE + COALESCE(best_supplier.lead_time_days, p.purchase_lead_days, 0)::int
                       ELSE NULL
                   END
               ) AS expected_arrival_date,
               CASE
                   WHEN mrp.need_date IS NOT NULL
                    AND COALESCE(
                        po.expected_arrival_date,
                        CASE
                            WHEN COALESCE(best_supplier.lead_time_days, p.purchase_lead_days, 0) > 0
                            THEN CURRENT_DATE + COALESCE(best_supplier.lead_time_days, p.purchase_lead_days, 0)::int
                            ELSE NULL
                        END
                    ) IS NOT NULL
                   THEN GREATEST(
                       COALESCE(
                           po.expected_arrival_date,
                           CASE
                               WHEN COALESCE(best_supplier.lead_time_days, p.purchase_lead_days, 0) > 0
                               THEN CURRENT_DATE + COALESCE(best_supplier.lead_time_days, p.purchase_lead_days, 0)::int
                               ELSE NULL
                           END
                       ) - mrp.need_date,
                       0
                   )
                   ELSE NULL
               END AS delivery_delay_days,
               CASE
                   WHEN LOWER(COALESCE(mrp.supply_mode, '')) IN ('subcontract', 'outsourcing', 'alternative', 'substitute', '委外', '外协', '替代') THEN 0
                   WHEN COALESCE(best_supplier.supplier_id, 0) = 0 AND COALESCE(best_supplier.supplier_name, p.default_supplier_name, '') = '' THEN 0
                   ELSE GREATEST(mrp.mrp_shortage_qty-COALESCE(req.requested_qty,0)-COALESCE(po.pending_po_qty,0),0)
               END AS suggestion_qty,
               COALESCE(best_supplier.supplier_id, 0) AS suggested_supplier_id,
               COALESCE(best_supplier.supplier_name, p.default_supplier_name, '') AS supplier_name,
               COALESCE(best_supplier.unit_price, p.standard_price, 0) AS unit_price,
               COALESCE(best_supplier.lead_time_days, p.purchase_lead_days, 0) AS lead_time_days,
               best_supplier.supplier_item_code,
               CASE WHEN {_engineering_ready_sql("mrp.project_code", "mrp.cabinet_no")} THEN TRUE ELSE FALSE END AS engineering_ready,
               latest_confirmation.id AS technical_confirmation_id,
               latest_confirmation.confirm_no AS technical_confirmation_no
        FROM mrp
        LEFT JOIN req ON req.product_id=mrp.product_id AND req.project_code=mrp.project_code AND req.cabinet_no=mrp.cabinet_no
        LEFT JOIN po ON po.product_id=mrp.product_id AND po.project_code=mrp.project_code AND po.cabinet_no=mrp.cabinet_no
        LEFT JOIN products p ON p.id=mrp.product_id
        LEFT JOIN best_supplier ON best_supplier.product_id=mrp.product_id
        LEFT JOIN LATERAL (
            SELECT etc.id, etc.confirm_no
            FROM engineering_technical_confirmations etc
            WHERE (mrp.project_code <> '-' AND etc.project_code=mrp.project_code)
               OR (mrp.cabinet_no <> '-' AND etc.cabinet_no=mrp.cabinet_no)
            ORDER BY etc.confirmed_at DESC NULLS LAST, etc.id DESC
            LIMIT 1
        ) latest_confirmation ON TRUE
        LEFT JOIN LATERAL (
            SELECT STRING_AGG(wo.wo_no, ', ' ORDER BY wo.id DESC) AS work_order_no
            FROM (
                SELECT DISTINCT wo.id, wo.wo_no
                FROM work_orders wo
                WHERE (
                    mrp.project_code <> '-' AND COALESCE(NULLIF(wo.project_code, ''), '-')=mrp.project_code
                ) OR (
                    mrp.cabinet_no <> '-' AND COALESCE(NULLIF(wo.cabinet_no, ''), '-')=mrp.cabinet_no
                )
                ORDER BY wo.id DESC
                LIMIT 3
            ) wo
        ) source_wo ON TRUE
        ORDER BY uncovered_shortage_qty DESC, mrp.need_date NULLS LAST, p.code
        LIMIT %s
        """,
        tuple(params),
    )


def render_purchase_suggestions(query_rows, as_decimal, qty_metric, money_metric):
    keyword = (request.args.get("keyword") or "").strip()
    rows = purchase_suggestion_rows(query_rows, keyword=keyword)
    today = datetime.now().date()
    for row in rows:
        suggestion_qty = as_decimal(row.get("suggestion_qty"))
        uncovered_qty = as_decimal(row.get("uncovered_shortage_qty"))
        supply_mode = (row.get("supply_mode") or "").strip().lower()
        need_date = row.get("need_date")
        if need_date is None:
            row["date_risk"] = "未定需求日"
        elif need_date < today:
            row["date_risk"] = "已逾期"
        elif (need_date - today).days <= 7:
            row["date_risk"] = "7天内需求"
        else:
            row["date_risk"] = "正常"

        if uncovered_qty <= 0:
            row["suggestion_status"] = "已覆盖"
            row["next_action"] = "回到齐套复核"
            row["owner_role"] = "生产计划"
            row["controlled_entry"] = "齐套复核"
            row["blocked_reason"] = "缺料已被请购或采购未到覆盖"
            row["target_document_type"] = "齐套复核"
            row["status_transition"] = "缺料已覆盖 -> 齐套复核"
        elif supply_mode in {"subcontract", "outsourcing", "委外", "外协"}:
            row["suggestion_status"] = "委外建议"
            row["next_action"] = "确认委外建议"
            row["owner_role"] = "生产计划/委外采购"
            row["controlled_entry"] = "委外订单"
            row["blocked_reason"] = "供给方式为委外，需确认发料和到货节点"
            row["target_document_type"] = "委外订单"
            row["status_transition"] = "MRP缺料 -> 委外确认"
        elif supply_mode in {"alternative", "substitute", "替代"}:
            row["suggestion_status"] = "替代料确认"
            row["next_action"] = "确认替代料"
            row["owner_role"] = "生产计划/技术"
            row["controlled_entry"] = "BOM/替代料"
            row["blocked_reason"] = "需技术确认替代料后再复核齐套"
            row["target_document_type"] = "BOM/替代料确认"
            row["status_transition"] = "MRP缺料 -> 替代料确认"
        elif not row.get("engineering_ready"):
            row["suggestion_status"] = "工程未就绪"
            row["next_action"] = "先补技术确认、BOM或图纸"
            row["owner_role"] = "技术/工艺"
            row["controlled_entry"] = "技术确认单"
            row["blocked_reason"] = "工程准备未就绪，不能生成采购申请"
            row["target_document_type"] = "技术确认单"
            row["status_transition"] = "MRP缺料 -> 工程阻塞"
        elif row.get("suggested_supplier_id") or row.get("supplier_name"):
            row["suggestion_status"] = "建议采购"
            row["next_action"] = "生成采购申请"
            row["owner_role"] = "采购"
            row["controlled_entry"] = "受控生成请购"
            row["blocked_reason"] = "缺料未覆盖，具备供应商或价格基础"
            row["target_document_type"] = "采购申请"
            row["status_transition"] = "MRP缺料 -> 建议请购"
        else:
            row["suggestion_status"] = "缺供应商"
            row["next_action"] = "维护供应商/价格"
            row["owner_role"] = "基础资料/采购"
            row["controlled_entry"] = "供应商档案"
            row["blocked_reason"] = "缺少供应商或价格，不能生成请购"
            row["target_document_type"] = "供应商档案"
            row["status_transition"] = "MRP缺料 -> 供应商阻塞"

        row["material_shortage"] = row.get("uncovered_shortage_qty")
        row["purchase_request_link"] = f"/purchase_request/{row.get('purchase_request_id')}" if row.get("purchase_request_id") else ""
        row["technical_confirmation_link"] = (
            f"/engineering/technical-confirmations/{row.get('technical_confirmation_id')}"
            if row.get("technical_confirmation_id")
            else "/engineering/technical-confirmations"
        )
        row["project_ledger_link"] = (
            f"/projects/project/{row.get('project_code')}"
            if row.get("project_code") and row.get("project_code") != "-"
            else (f"/projects/machine/{row.get('cabinet_no')}" if row.get("cabinet_no") and row.get("cabinet_no") != "-" else "/projects")
        )
        expected_arrival = row.get("expected_arrival_date")
        delay_days = row.get("delivery_delay_days")
        if expected_arrival:
            row["expected_arrival_display"] = str(expected_arrival)
        elif supply_mode in {"subcontract", "outsourcing", "委外", "外协"}:
            row["expected_arrival_display"] = "委外确认后回填"
        elif supply_mode in {"alternative", "substitute", "替代"}:
            row["expected_arrival_display"] = "替代确认后回填"
        else:
            row["expected_arrival_display"] = "待确认"
        if delay_days is None:
            row["delivery_impact"] = "交期影响待确认"
            row["delivery_impact_class"] = "secondary"
        elif delay_days > 0:
            row["delivery_impact"] = f"预计影响项目交期 {delay_days} 天"
            row["delivery_impact_class"] = "danger"
        else:
            row["delivery_impact"] = "预计不影响需求日"
            row["delivery_impact_class"] = "success"
        row["recheck_action"] = "到货/替代/委外确认后再齐套复核"
        row["downstream_impact"] = f"影响工单齐套、领料、装配和交付；{row['delivery_impact']}"
        row["status_class"] = "warning" if row["suggestion_status"] in {"缺供应商", "工程未就绪"} else ("success" if uncovered_qty <= 0 else "primary")
        row["risk_class"] = "danger" if row["date_risk"] == "已逾期" else ("warning" if row["date_risk"] == "7天内需求" else "secondary")
        mrp_qty = as_decimal(row.get("mrp_shortage_qty"))
        covered_qty = as_decimal(row.get("requested_qty")) + as_decimal(row.get("pending_po_qty"))
        row["coverage_rate"] = int(min(100, max(0, (covered_qty / mrp_qty * 100) if mrp_qty > 0 else 100)))

    actionable = [row for row in rows if as_decimal(row.get("suggestion_qty")) > 0 and row.get("suggestion_status") == "建议采购"]
    missing_supplier = [row for row in rows if row.get("suggestion_status") == "缺供应商"]
    covered = [row for row in rows if as_decimal(row.get("uncovered_shortage_qty")) <= 0]
    urgent = [row for row in rows if as_decimal(row.get("uncovered_shortage_qty")) > 0 and row.get("date_risk") in {"已逾期", "7天内需求"}]
    total_qty = sum((as_decimal(row.get("suggestion_qty")) for row in actionable), as_decimal("0"))
    total_amount = sum((as_decimal(row.get("suggestion_qty")) * as_decimal(row.get("unit_price")) for row in actionable), as_decimal("0"))
    return render_template(
        "purchase_suggestions.html",
        rows=rows,
        filters={"keyword": keyword},
        metrics=[
            {"label": "建议采购行", "value": len(actionable), "hint": "仍有建议数量且可转请购的缺料行"},
            {"label": "建议数量", "value": qty_metric(total_qty), "hint": "按物料单位汇总，仅作计划处理量"},
            {"label": "预估金额", "value": money_metric(total_amount), "hint": "按供应商价或标准价估算"},
            {"label": "缺供应商", "value": len(missing_supplier), "hint": "需先维护供应商或价格"},
            {"label": "紧急缺料", "value": len(urgent), "hint": "逾期或7天内需求"},
        ],
        covered_count=len(covered),
    )


def render_purchase_requisition_form(
    inventory_product_options,
    query_rows,
    as_decimal,
    next_daily_doc_no,
    now=None,
):
    products = []
    for row in inventory_product_options():
        products.append(
            {
                "id": row.get("id"),
                "code": row.get("code") or "",
                "name": row.get("name") or "",
                "spec": row.get("specification") or "",
                "unit": {"name": row.get("unit") or ""},
                "price": float(as_decimal(row.get("standard_price"))),
                "stock": 0,
            }
        )
    suppliers = query_rows("SELECT id, name FROM suppliers ORDER BY name LIMIT 500")
    units = query_rows("SELECT id, code, name FROM units ORDER BY name LIMIT 200")
    warehouses = query_rows("SELECT id, name FROM warehouses ORDER BY name LIMIT 500")
    locations = query_rows("SELECT id, warehouse_id, code, name FROM locations WHERE COALESCE(is_active, TRUE)=TRUE ORDER BY code LIMIT 1000")
    request_date = (now or datetime.now()).strftime("%Y-%m-%d")
    return render_template(
        "purchase_request_add.html",
        page_title="新增采购申请单",
        request_no=next_daily_doc_no("PR", "purchase_requisitions", "req_no"),
        request_date=request_date,
        order=None,
        request_id="",
        materials=products,
        suppliers=suppliers,
        units=units,
        warehouses=warehouses,
        locations=locations,
        initial_items=[],
    )


def render_purchase_requisition_dashboard(
    query_rows,
    count_rows,
    sum_value,
    qty_metric,
    money_metric,
    columns,
    render_module_dashboard,
    back_url="/purchase_request",
):
    metrics = [
        {"label": "采购申请", "value": count_rows("purchase_requisitions"), "hint": "全部申请单"},
        {
            "label": "待处理",
            "value": count_rows(
                "purchase_requisitions",
                "COALESCE(status, '') NOT IN ('已完成','已关闭','已作废','completed','closed')",
            ),
            "hint": "仍需审核或下推",
        },
        {"label": "申请数量", "value": qty_metric(sum_value("purchase_requisition_items", "quantity")), "hint": "明细数量合计"},
        {"label": "申请金额", "value": money_metric(sum_value("purchase_requisition_items", "amount")), "hint": "按申请单价估算"},
    ]
    shortcuts = [
        {"label": "新增采购申请", "url": "/purchase_request/new", "icon": "bi-plus-lg"},
        {"label": "采购建议", "url": "/procurement/suggestions", "icon": "bi-lightbulb"},
        {"label": "采购订单列表", "url": "/purchase-orders", "icon": "bi-bag-check"},
        {"label": "MRP缺料", "url": "/production-enhance/mrp-requirements", "icon": "bi-exclamation-triangle"},
    ]
    requests = query_rows(
        """
        SELECT pr.id, pr.req_no, pr.req_date, pr.department, pr.purpose, pr.status,
               pr.project_code, pr.cabinet_no,
               COUNT(pri.id) AS item_count,
               COALESCE(SUM(pri.quantity), 0) AS request_qty,
               COALESCE(SUM(pri.amount), 0) AS total_amount
        FROM purchase_requisitions pr
        LEFT JOIN purchase_requisition_items pri ON pri.req_id=pr.id
        GROUP BY pr.id
        ORDER BY pr.id DESC
        LIMIT 40
        """
    )
    pending_items = query_rows(
        """
        SELECT pri.id, pr.req_no, pr.req_date, p.code AS product_code, p.name AS product_name,
               p.specification, p.unit, pri.project_code, pri.cabinet_no, pri.quantity,
               COALESCE(po_items.ordered_qty, 0) AS ordered_qty,
               GREATEST(COALESCE(pri.quantity,0)-COALESCE(po_items.ordered_qty,0),0) AS remaining_qty,
               s.name AS supplier_name
        FROM purchase_requisition_items pri
        LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
        LEFT JOIN products p ON p.id=pri.product_id
        LEFT JOIN suppliers s ON s.id=pri.suggested_supplier_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(poi.quantity), 0) AS ordered_qty
            FROM purchase_order_items poi
            WHERE poi.source_line_no=CONCAT('PRITEM-', pri.id::text)
        ) po_items ON TRUE
        WHERE GREATEST(COALESCE(pri.quantity,0)-COALESCE(po_items.ordered_qty,0),0) > 0
        ORDER BY pr.id DESC, pri.id DESC
        LIMIT 40
        """
    )
    return render_module_dashboard(
        "采购申请单列表",
        "",
        metrics,
        shortcuts,
        [
            {
                "title": "最近采购申请",
                "rows": requests,
                "columns": columns(
                    ("req_no", "申请单"),
                    ("req_date", "日期"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("item_count", "行数"),
                    ("request_qty", "数量"),
                    ("total_amount", "金额"),
                    ("status", "状态"),
                ),
                "detail_base": back_url,
            },
            {
                "title": "待下推明细",
                "rows": pending_items,
                "columns": columns(
                    ("req_no", "申请单"),
                    ("product_code", "物料编码"),
                    ("product_name", "物料名称"),
                    ("specification", "规格"),
                    ("unit", "单位"),
                    ("project_code", "项目号"),
                    ("cabinet_no", "柜号"),
                    ("quantity", "申请"),
                    ("ordered_qty", "已下推"),
                    ("remaining_qty", "未下推"),
                    ("supplier_name", "建议供应商"),
                ),
            },
        ],
    )


def render_purchase_requisition_detail(
    req_id,
    query_one,
    query_rows,
    as_decimal,
    qty_metric,
    money_metric,
    back_url="/purchase_request",
):
    req = query_one(
        """
        SELECT pr.*, u.username AS requester_name
        FROM purchase_requisitions pr
        LEFT JOIN users u ON u.id=pr.requester_id
        WHERE pr.id=%s
        """,
        (req_id,),
    )
    if not req:
        return render_template("simple_detail.html", title="采购申请单明细", row=None, back_url=back_url, labels={})
    status_aliases = {
        "pending": "待提交",
        "draft": "待提交",
        "submitted": "已提交",
        "approved": "已审核",
        "completed": "已关闭",
        "closed": "已关闭",
        "void": "已作废",
        "cancelled": "已作废",
        "canceled": "已作废",
    }
    req = dict(req)
    req["status"] = status_aliases.get((req.get("status") or "").strip(), req.get("status"))
    req["approval_status"] = status_aliases.get((req.get("approval_status") or "").strip(), req.get("approval_status"))
    items = query_rows(
        """
        SELECT pri.*, p.code AS product_code, p.name AS product_name, p.specification,
               COALESCE(p.unit, '') AS unit, s.name AS supplier_name,
               COALESCE(po_items.ordered_qty, 0) AS ordered_qty,
               GREATEST(COALESCE(pri.quantity,0)-COALESCE(po_items.ordered_qty,0),0) AS remaining_qty
        FROM purchase_requisition_items pri
        LEFT JOIN products p ON p.id=pri.product_id
        LEFT JOIN suppliers s ON s.id=pri.suggested_supplier_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(poi.quantity), 0) AS ordered_qty
            FROM purchase_order_items poi
            WHERE poi.source_line_no=CONCAT('PRITEM-', pri.id::text)
        ) po_items ON TRUE
        WHERE pri.req_id=%s
        ORDER BY pri.id
        """,
        (req_id,),
    )
    purchase_orders = query_rows(
        """
        SELECT po.id, po.order_no, po.order_date, po.status, po.project_code, po.cabinet_no,
               po.total_amount, s.name AS supplier_name
        FROM purchase_orders po
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        WHERE EXISTS (
            SELECT 1
            FROM purchase_requisition_items pri
            JOIN purchase_order_items poi ON poi.source_line_no=CONCAT('PRITEM-', pri.id::text)
            WHERE pri.req_id=%s
              AND poi.order_id=po.id
        )
        ORDER BY po.id DESC
        LIMIT 30
        """,
        (req_id,),
    )
    total_qty = sum((as_decimal(row.get("quantity")) for row in items), as_decimal("0"))
    remaining_qty = sum((as_decimal(row.get("remaining_qty")) for row in items), as_decimal("0"))
    total_amount = sum((as_decimal(row.get("amount")) for row in items), as_decimal("0"))
    status_value = (req.get("status") or "").strip()
    approval_value = (req.get("approval_status") or "").strip()
    is_approved = status_value in {"已审核", "已审批"} or approval_value in {"已审核", "已审批", "approved"}
    can_submit = status_value in {"待提交", "草稿", "pending", "draft", ""}
    can_approve = status_value in {"已提交", "待审批", "待审核", "submitted"} or approval_value in {"submitted", "待审批", "待审核"}
    can_create_po = is_approved and remaining_qty > 0
    missing_supplier_item_ids = {
        row.get("id")
        for row in items
        if as_decimal(row.get("remaining_qty")) > 0 and not row.get("suggested_supplier_id")
    }
    push_blockers = []
    if is_approved and missing_supplier_item_ids:
        push_blockers.append(
            {
                "reason": "\u5b58\u5728\u672a\u6307\u5b9a\u5efa\u8bae\u4f9b\u5e94\u5546\u7684\u672a\u4e0b\u63a8\u660e\u7ec6\uff0c\u5f53\u524d\u91c7\u8d2d\u7533\u8bf7\u4e0d\u80fd\u751f\u6210\u91c7\u8d2d\u8ba2\u5355\u3002",
                "owner": "\u91c7\u8d2d",
                "next_action": "\u7ef4\u62a4\u5efa\u8bae\u4f9b\u5e94\u5546\u6216\u5728\u7269\u6599\u4f9b\u5e94\u5546\u4ef7\u683c\u4e2d\u7ef4\u62a4\u6709\u6548\u4f9b\u5e94\u5546\u540e\u518d\u4e0b\u63a8\u3002",
                "line_count": len(missing_supplier_item_ids),
            }
        )
    if is_approved and remaining_qty <= 0:
        push_blockers.append(
            {
                "reason": "采购申请明细已全部下推，不能重复生成采购订单。",
                "owner": "采购",
                "next_action": "查看下游采购订单或新增采购申请。",
                "line_count": len(items),
            }
        )
    return render_template(
        "purchase_requisition_detail.html",
        back_url=back_url,
        req=req,
        can_submit=can_submit,
        can_approve=can_approve,
        can_create_po=can_create_po,
        items=items,
        purchase_orders=purchase_orders,
        push_blockers=push_blockers,
        missing_supplier_item_ids=missing_supplier_item_ids,
        metrics=[
            {"label": "申请行数", "value": len(items), "hint": "物料明细"},
            {"label": "申请数量", "value": qty_metric(total_qty), "hint": "明细合计"},
            {"label": "未下推", "value": qty_metric(remaining_qty), "hint": "还未形成采购单"},
            {"label": "预估金额", "value": money_metric(total_amount), "hint": "按申请单价"},
        ],
    )
