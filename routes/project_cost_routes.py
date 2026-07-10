"""Project cost routes: project cost summary and cost detail analysis."""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

from flask import render_template, request


SALES_INCOME = "销售收入参考"
PURCHASE_COST = "采购材料成本"
SUBCONTRACT_COST = "委外加工成本"
WORK_ORDER_COST = "工单实际成本"
INVENTORY_ISSUE_COST = "库存出库成本"
SERVICE_COST = "售后服务成本"

SOURCE_TYPES = (
    SALES_INCOME,
    PURCHASE_COST,
    SUBCONTRACT_COST,
    WORK_ORDER_COST,
    INVENTORY_ISSUE_COST,
    SERVICE_COST,
)

CLOSED_STATUS = (
    "已关闭",
    "已完成",
    "已作废",
    "closed",
    "completed",
    "void",
    "voided",
    "cancelled",
    "canceled",
)

MOJIBAKE_MARKERS = (
    chr(0xFFFD),
    chr(63) * 3,
    chr(0x95C1),
    chr(0x95BF),
    chr(0x9359),
    chr(0x934F),
    chr(0x6434),
    chr(0x9417),
    chr(0x9422),
    chr(0x93C2),
    chr(0x95B2),
    chr(0x7487),
)


def _as_decimal(value):
    try:
        return Decimal(str(value if value is not None else "0"))
    except Exception:
        return Decimal("0")


def _money(value):
    try:
        return f"{float(value or 0):,.2f}"
    except Exception:
        return "0.00"


def _sql_string_list(values):
    return "(" + ", ".join("'" + value.replace("'", "''") + "'" for value in values) + ")"


def _clean_text(value):
    text = "" if value is None else str(value).strip()
    if not text:
        return "-"
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return "-"
    return text


def _clean_rows(rows):
    cleaned = []
    for row in rows or []:
        item = dict(row)
        for key, value in list(item.items()):
            if isinstance(value, str):
                item[key] = _clean_text(value)
        cleaned.append(item)
    return cleaned


def _has_column(table, column, query_rows):
    rows = query_rows(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table, column),
    )
    return bool(rows)


def _optional_expr(table_alias, table_name, column, query_rows, fallback="NULL"):
    return f"{table_alias}.{column}" if _has_column(table_name, column, query_rows) else fallback


def _filters():
    source_type = (request.args.get("source_type") or "").strip()
    if source_type not in SOURCE_TYPES:
        source_type = ""
    return {
        "keyword": (request.args.get("keyword") or "").strip(),
        "project_code": (request.args.get("project_code") or "").strip(),
        "cabinet_no": (request.args.get("cabinet_no") or "").strip(),
        "source_type": source_type,
        "date_start": (request.args.get("date_start") or "").strip(),
        "date_end": (request.args.get("date_end") or "").strip(),
        "period": (request.args.get("period") or "").strip(),
    }


def _where_from_filters(filters, *, detail_kind):
    clauses = []
    params = []
    if filters["project_code"]:
        clauses.append("COALESCE(project_code, '') ILIKE %s")
        params.append(f"%{filters['project_code']}%")
    if filters["cabinet_no"]:
        clauses.append("COALESCE(cabinet_no, '') ILIKE %s")
        params.append(f"%{filters['cabinet_no']}%")
    if filters["source_type"]:
        clauses.append("source_type=%s")
        params.append(filters["source_type"])
    if filters["date_start"]:
        clauses.append("cost_date >= %s")
        params.append(filters["date_start"])
    if filters["date_end"]:
        clauses.append("cost_date <= %s")
        params.append(filters["date_end"])
    if filters["keyword"]:
        if detail_kind == "machine":
            clauses.append(
                "(COALESCE(cabinet_no, '') ILIKE %s OR COALESCE(project_code, '') ILIKE %s "
                "OR COALESCE(source_no, '') ILIKE %s OR COALESCE(source_name, '') ILIKE %s)"
            )
        else:
            clauses.append(
                "(COALESCE(project_code, '') ILIKE %s OR COALESCE(cabinet_no, '') ILIKE %s "
                "OR COALESCE(source_no, '') ILIKE %s OR COALESCE(source_name, '') ILIKE %s)"
            )
        params.extend([f"%{filters['keyword']}%"] * 4)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, tuple(params)


def _cost_union_sql(query_rows):
    closed_status = _sql_string_list(CLOSED_STATUS)
    purchase_amount = (
        "COALESCE(po.amount_with_tax, po.total_amount, 0)"
        if _has_column("purchase_orders", "amount_with_tax", query_rows)
        else "COALESCE(po.total_amount, 0)"
    )
    sales_amount = (
        "COALESCE(so.amount_with_tax, so.total_amount, 0)"
        if _has_column("sales_orders", "amount_with_tax", query_rows)
        else "COALESCE(so.total_amount, 0)"
    )
    service_parts = _optional_expr("mso", "machine_service_orders", "parts_cost", query_rows, "0")
    service_labor = _optional_expr("mso", "machine_service_orders", "labor_cost", query_rows, "0")
    service_travel = _optional_expr("mso", "machine_service_orders", "travel_cost", query_rows, "0")
    source_doc_no = (
        "COALESCE(st.source_doc_no, st.reference_no)"
        if _has_column("stock_transactions", "source_doc_no", query_rows)
        else "st.reference_no"
    )
    source_doc_type = (
        "COALESCE(st.source_doc_type, st.source_type, st.transaction_type)"
        if _has_column("stock_transactions", "source_doc_type", query_rows)
        else "COALESCE(st.source_type, st.transaction_type)"
    )
    material_name = (
        "COALESCE(st.material_name, p.name)"
        if _has_column("stock_transactions", "material_name", query_rows)
        else "p.name"
    )
    amount_expr = (
        "COALESCE(st.amount, ABS(COALESCE(st.quantity,0)) * COALESCE(st.unit_cost,0))"
        if _has_column("stock_transactions", "amount", query_rows)
        else "ABS(COALESCE(st.quantity,0)) * COALESCE(st.unit_cost,0)"
    )
    stock_date = (
        "COALESCE(st.transaction_date::date, st.created_at::date)"
        if _has_column("stock_transactions", "created_at", query_rows)
        else "st.transaction_date::date"
    )
    standard_price = _optional_expr("pwo", "products", "standard_price", query_rows, "0")

    return f"""
    WITH cost_sources AS (
        SELECT '{PURCHASE_COST}' AS source_type, po.id AS source_id, po.order_no AS source_no,
               po.order_date AS cost_date, po.project_code, po.cabinet_no, s.name AS partner_name,
               {purchase_amount} AS cost_amount, 0::numeric AS standard_amount,
               0::numeric AS quantity, po.status,
               '采购入库或发票应付金额，用于项目/柜号材料成本归集；本页不执行应付核销。' AS basis_note,
               '采购应付来源' AS source_name
        FROM (
            SELECT id, doc_no AS order_no, doc_date AS order_date, project_code, cabinet_no,
                   supplier_id, COALESCE(NULLIF(confirmed_amount, 0), amount, 0) AS amount_with_tax,
                   amount AS total_amount, status
            FROM supplier_payables
            WHERE COALESCE(doc_type, source_type, '') IN ('purchase_receipt','purchase_invoice')
              AND COALESCE(NULLIF(confirmed_amount, 0), amount, 0) > 0
        ) po
        LEFT JOIN suppliers s ON s.id=po.supplier_id
        WHERE COALESCE(po.status, '') NOT IN {closed_status}

        UNION ALL
        SELECT '{SUBCONTRACT_COST}' AS source_type, sc.id AS source_id, sc.order_no AS source_no,
               sc.order_date AS cost_date, sc.project_code, sc.cabinet_no, s.name AS partner_name,
               COALESCE(sc.total_amount, 0) AS cost_amount, 0::numeric AS standard_amount,
               COALESCE(sc.quantity, 0) AS quantity, sc.status,
               '委外收货应付金额，用于单台设备委外加工费归集；本页不生成应付或凭证。' AS basis_note,
               '委外收货来源' AS source_name
        FROM (
            SELECT id, doc_no AS order_no, doc_date AS order_date, project_code, cabinet_no,
                   supplier_id, COALESCE(NULLIF(confirmed_amount, 0), amount, 0) AS total_amount,
                   0::numeric AS quantity, status
            FROM supplier_payables
            WHERE COALESCE(doc_type, source_type, '') IN ('subcontract_receive','subcontract_receive_order')
              AND COALESCE(NULLIF(confirmed_amount, 0), amount, 0) > 0
        ) sc
        LEFT JOIN suppliers s ON s.id=sc.supplier_id
        WHERE COALESCE(sc.status, '') NOT IN {closed_status}

        UNION ALL
        SELECT '{WORK_ORDER_COST}' AS source_type, wo.id AS source_id, wo.wo_no AS source_no,
               COALESCE(woc.last_calculated_at::date, wo.wo_date) AS cost_date,
               wo.project_code, wo.cabinet_no, wo.wo_no AS partner_name,
               COALESCE(woc.total_cost, 0) AS cost_amount,
               COALESCE(wo.quantity, 0) * COALESCE({standard_price}, 0) AS standard_amount,
               COALESCE(wo.quantity, 0) AS quantity, wo.status,
               CONCAT('工单成本汇总：材料 ', COALESCE(woc.material_cost,0),
                      '，委外 ', COALESCE(woc.subcontract_cost,0),
                      '，人工 ', COALESCE(woc.labor_cost,0),
                      '，制造费用 ', COALESCE(woc.overhead_cost,0),
                      '；标准成本按产品标准价乘工单数量参考。') AS basis_note,
               '生产工单' AS source_name
        FROM work_orders wo
        LEFT JOIN work_order_costs woc ON woc.work_order_id=wo.id
        LEFT JOIN products pwo ON pwo.id=wo.product_id
        WHERE COALESCE(wo.status, '') NOT IN {closed_status}

        UNION ALL
        SELECT '{SERVICE_COST}' AS source_type, mso.id AS source_id, mso.order_no AS source_no,
               mso.service_date AS cost_date, mso.project_code, mso.cabinet_no,
               mso.service_type AS partner_name, COALESCE(mso.total_cost, 0) AS cost_amount,
               0::numeric AS standard_amount, 0::numeric AS quantity, mso.status,
               CONCAT('服务单成本：备件 ', {service_parts}, '，人工 ', {service_labor}, '，差旅 ', {service_travel}, '。') AS basis_note,
               '服务单' AS source_name
        FROM machine_service_orders mso
        WHERE COALESCE(mso.status, '') NOT IN {closed_status}

        UNION ALL
        SELECT '{INVENTORY_ISSUE_COST}' AS source_type, st.id AS source_id, {source_doc_no} AS source_no,
               {stock_date} AS cost_date, st.project_code, st.cabinet_no, {material_name} AS partner_name,
               {amount_expr} AS cost_amount, 0::numeric AS standard_amount,
               ABS(COALESCE(st.quantity, 0)) AS quantity, st.transaction_type AS status,
               '库存出库流水金额，仅用于核对非工单领料类耗用来源；本页不调整库存成本。' AS basis_note,
               {source_doc_type} AS source_name
        FROM stock_transactions st
        LEFT JOIN products p ON p.id=st.product_id
        WHERE COALESCE(st.quantity, 0) < 0
          AND COALESCE(st.transaction_type, '') NOT IN ('工单领料', '工单退料')

        UNION ALL
        SELECT '{SALES_INCOME}' AS source_type, so.id AS source_id, so.order_no AS source_no,
               so.order_date AS cost_date, so.project_code, so.cabinet_no, c.name AS partner_name,
               -1 * {sales_amount} AS cost_amount, 0::numeric AS standard_amount,
               0::numeric AS quantity, so.status,
               '销售订单金额以负数显示为收入参考，便于同页查看毛利口径；本页不生成应收。' AS basis_note,
               '销售订单' AS source_name
        FROM sales_orders so
        LEFT JOIN customers c ON c.id=so.customer_id
        WHERE COALESCE(so.status, '') NOT IN {closed_status}
    )
    """


def _source_url(row):
    source_id = row.get("source_id")
    source_no = row.get("source_no")
    source_type = row.get("source_type")
    if source_type == SALES_INCOME and source_id:
        return f"/sales/{source_id}"
    if source_type == PURCHASE_COST and source_id:
        return f"/payables/{source_id}"
    if source_type == SUBCONTRACT_COST and source_id:
        return f"/payables/{source_id}"
    if source_type == WORK_ORDER_COST and source_id:
        return f"/work-orders/{source_id}"
    if source_type == SERVICE_COST and source_id:
        return f"/service-orders/{source_id}"
    if source_type == INVENTORY_ISSUE_COST and source_no and source_no != "-":
        return f"/transactions?keyword={quote(str(source_no))}"
    return ""


def _attach_source_urls(rows):
    for row in rows:
        row["source_url"] = _source_url(row)
    return rows


def _period_status(query_rows, filters, totals):
    period = filters.get("period") or ""
    snapshot = None
    if period:
        rows = query_rows(
            """
            SELECT period_label, status, closed_at, generated_at
            FROM finance_period_closes
            WHERE period_label=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (period,),
        )
        snapshot = rows[0] if rows else None
    if not period:
        return {
            "label": "未选择期间",
            "blocked_reason": "未选择期间，不能判断结转准备。",
            "next_action": "输入期间后复核成本来源和期间快照。",
            "downstream_impact": "影响项目/柜号成本结转准备判断，不影响当前只读查询。",
            "snapshot": None,
        }
    if not snapshot:
        return {
            "label": "缺期间快照",
            "blocked_reason": "当前期间没有保存的经营结账快照。",
            "next_action": "由财务在期间结账页生成经营快照后再复核。",
            "downstream_impact": "期间结转准备证据不完整，但本页不会生成凭证。",
            "snapshot": None,
        }
    if _as_decimal(totals.get("total_cost")) <= 0:
        return {
            "label": "待核成本",
            "blocked_reason": "当前筛选范围没有可结转的实际成本。",
            "next_action": "检查工单成本、委外应付、库存出库和服务成本是否已归集。",
            "downstream_impact": "可能导致单台设备成本低估。",
            "snapshot": snapshot,
        }
    return {
        "label": "可复核",
        "blocked_reason": "未发现报表层阻塞项。",
        "next_action": "按来源明细核对后，进入正式期间结账流程。",
        "downstream_impact": "可作为项目/柜号成本结转准备参考，不替代总账结账。",
        "snapshot": snapshot,
    }


def _decorate_groups(groups):
    for row in groups:
        actual = _as_decimal(row.get("total_cost"))
        standard = _as_decimal(row.get("standard_cost"))
        variance = actual - standard
        row["actual_cost"] = actual
        row["standard_cost"] = standard
        row["variance_amount"] = variance
        if not row.get("project_code") or row.get("project_code") == "-":
            row["blocked_reason"] = "缺项目号，不能完整归集项目成本。"
            row["next_action"] = "补齐源单项目号或维护项目档案。"
        elif not row.get("cabinet_no") or row.get("cabinet_no") == "-":
            row["blocked_reason"] = "缺柜号，不能形成单台设备成本。"
            row["next_action"] = "补齐销售、工单、委外、库存或服务源单柜号。"
        elif actual <= 0:
            row["blocked_reason"] = "实际成本为零。"
            row["next_action"] = "复核工单成本、委外应付、库存出库和服务成本。"
        elif standard <= 0:
            row["blocked_reason"] = "缺标准成本基础。"
            row["next_action"] = "维护产品标准价或工单标准成本口径。"
        elif abs(variance) > max(standard * Decimal("0.2"), Decimal("1000")):
            row["blocked_reason"] = "实际与标准差异偏大。"
            row["next_action"] = "检查委外、人工、制造费用和材料耗用异常。"
        else:
            row["blocked_reason"] = "无报表层阻塞。"
            row["next_action"] = "按来源明细抽查后进入期间复核。"
        row["owner"] = "成本会计"
        row["downstream_impact"] = "影响单台设备毛利、项目复盘和期间结转准备。"
    return groups


def _load_report(query_rows, *, detail_kind):
    filters = _filters()
    where_sql, params = _where_from_filters(filters, detail_kind=detail_kind)
    group_field = "cabinet_no" if detail_kind == "machine" else "project_code"
    empty_group_label = "未填写柜号" if detail_kind == "machine" else "未填写项目号"
    cost_union = _cost_union_sql(query_rows)
    groups = query_rows(
        cost_union
        + f"""
        SELECT COALESCE(NULLIF({group_field}, ''), %s) AS group_key,
               MAX(COALESCE(NULLIF(project_code, ''), '-')) AS project_code,
               MAX(COALESCE(NULLIF(cabinet_no, ''), '-')) AS cabinet_no,
               COUNT(*) AS source_count,
               SUM(CASE WHEN source_type=%s THEN -cost_amount ELSE 0 END) AS sales_amount,
               SUM(CASE WHEN source_type=%s THEN cost_amount ELSE 0 END) AS purchase_cost,
               SUM(CASE WHEN source_type=%s THEN cost_amount ELSE 0 END) AS subcontract_cost,
               SUM(CASE WHEN source_type=%s THEN cost_amount ELSE 0 END) AS work_order_cost,
               SUM(CASE WHEN source_type=%s THEN cost_amount ELSE 0 END) AS inventory_issue_cost,
               SUM(CASE WHEN source_type=%s THEN cost_amount ELSE 0 END) AS service_cost,
               SUM(CASE WHEN source_type=%s THEN standard_amount ELSE 0 END) AS standard_cost,
               SUM(CASE WHEN source_type NOT IN (%s, %s) THEN cost_amount ELSE 0 END) AS total_cost,
               SUM(CASE WHEN source_type=%s THEN -cost_amount ELSE 0 END)
                 - SUM(CASE WHEN source_type NOT IN (%s, %s) THEN cost_amount ELSE 0 END) AS gross_profit
        FROM cost_sources
        {where_sql}
        GROUP BY COALESCE(NULLIF({group_field}, ''), %s)
        ORDER BY total_cost DESC, group_key
        LIMIT 200
        """,
        (
            empty_group_label,
            SALES_INCOME,
            PURCHASE_COST,
            SUBCONTRACT_COST,
            WORK_ORDER_COST,
            INVENTORY_ISSUE_COST,
            SERVICE_COST,
            WORK_ORDER_COST,
            SALES_INCOME,
            INVENTORY_ISSUE_COST,
            SALES_INCOME,
            SALES_INCOME,
            INVENTORY_ISSUE_COST,
            *params,
            empty_group_label,
        ),
    )
    rows = query_rows(
        cost_union
        + f"""
        SELECT source_type, source_id, source_no, cost_date, project_code, cabinet_no, source_name,
               partner_name, quantity, cost_amount, standard_amount,
               cost_amount - standard_amount AS variance_amount,
               status, basis_note
        FROM cost_sources
        {where_sql}
        ORDER BY cost_date DESC NULLS LAST, source_no DESC NULLS LAST
        LIMIT 500
        """,
        params,
    )
    groups = _decorate_groups(_clean_rows(groups))
    rows = _attach_source_urls(_clean_rows(rows))
    totals = {
        "source_count": sum(int(row.get("source_count") or 0) for row in groups),
        "sales_amount": sum(_as_decimal(row.get("sales_amount")) for row in groups),
        "purchase_cost": sum(_as_decimal(row.get("purchase_cost")) for row in groups),
        "subcontract_cost": sum(_as_decimal(row.get("subcontract_cost")) for row in groups),
        "work_order_cost": sum(_as_decimal(row.get("work_order_cost")) for row in groups),
        "inventory_issue_cost": sum(_as_decimal(row.get("inventory_issue_cost")) for row in groups),
        "service_cost": sum(_as_decimal(row.get("service_cost")) for row in groups),
        "standard_cost": sum(_as_decimal(row.get("standard_cost")) for row in groups),
        "total_cost": sum(_as_decimal(row.get("total_cost")) for row in groups),
        "gross_profit": sum(_as_decimal(row.get("gross_profit")) for row in groups),
    }
    period_status = _period_status(query_rows, filters, totals)
    group_hint = "按项目号汇总" if detail_kind == "project" else "按柜号汇总"
    metrics = [
        {"label": "归集对象", "value": len(groups), "hint": group_hint},
        {"label": "实际成本", "value": _money(totals["total_cost"]), "hint": "材料/委外/工单/出库/售后"},
        {"label": "标准成本", "value": _money(totals["standard_cost"]), "hint": "产品标准价 * 工单数量"},
        {"label": "成本差异", "value": _money(totals["total_cost"] - totals["standard_cost"]), "hint": "实际成本 - 标准成本"},
        {"label": "委外成本", "value": _money(totals["subcontract_cost"]), "hint": "委外收货应付来源"},
        {"label": "售后成本", "value": _money(totals["service_cost"]), "hint": "备件/人工/差旅"},
        {"label": "毛利参考", "value": _money(totals["gross_profit"]), "hint": "销售收入 - 已归集成本"},
        {"label": "期间准备", "value": period_status["label"], "hint": period_status["blocked_reason"]},
    ]
    return filters, groups, rows, totals, metrics, period_status


def render_project_cost_report(query_rows):
    filters, groups, rows, totals, metrics, period_status = _load_report(query_rows, detail_kind="project")
    return render_template(
        "project_cost_report.html",
        title="项目成本明细",
        subtitle="按项目号汇总销售收入参考、采购材料、委外、工单、库存出库和售后成本来源；只读查询，不生成凭证、分摊或调整。",
        detail_kind="project",
        group_label="项目号",
        source_types=SOURCE_TYPES,
        filters=filters,
        groups=groups,
        rows=rows,
        totals=totals,
        metrics=metrics,
        period_status=period_status,
    )


def render_machine_cost_report(query_rows):
    filters, groups, rows, totals, metrics, period_status = _load_report(query_rows, detail_kind="machine")
    return render_template(
        "project_cost_report.html",
        title="柜号成本明细",
        subtitle="按柜号汇总单台设备实际成本、标准成本、成本差异、委外成本、售后成本和期间结转准备；只读查询，不改总账。",
        detail_kind="machine",
        group_label="柜号",
        source_types=SOURCE_TYPES,
        filters=filters,
        groups=groups,
        rows=rows,
        totals=totals,
        metrics=metrics,
        period_status=period_status,
    )


def register_routes(app, deps):
    login_required = deps["login_required"]
    query_rows = lambda sql, params=None: deps["query_db"](sql, params or ())

    @app.get("/finance/reports/project-cost", endpoint="finance_project_cost_report")
    @login_required
    def finance_project_cost_report():
        return render_project_cost_report(query_rows)

    @app.get("/finance/reports/machine-cost", endpoint="finance_machine_cost_report")
    @login_required
    def finance_machine_cost_report():
        return render_machine_cost_report(query_rows)

    @app.get("/finance/project-cost/detail", endpoint="finance_project_cost_detail")
    @login_required
    def finance_project_cost_detail():
        return render_project_cost_report(query_rows)

    @app.get("/finance/project-cost/machine-detail", endpoint="finance_machine_cost_detail")
    @login_required
    def finance_machine_cost_detail():
        return render_machine_cost_report(query_rows)
