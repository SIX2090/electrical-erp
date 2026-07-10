"""Project delivery workbench routes: render delivery dashboard widgets and summary metrics."""
from flask import render_template


def _scalar(row, key, default=0):
    if not row:
        return default
    value = row.get(key)
    return default if value is None else value


def _money(value):
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _build_project_focus_rows(query_db):
    rows = query_db(
        """
        WITH base_orders AS (
            SELECT so.id, so.order_no, so.project_code, so.cabinet_no, so.status,
                   so.delivery_date, c.name AS customer_name
            FROM sales_orders so
            LEFT JOIN customers c ON c.id=so.customer_id
            WHERE NULLIF(TRIM(COALESCE(so.project_code, '')), '') IS NOT NULL
               OR NULLIF(TRIM(COALESCE(so.cabinet_no, '')), '') IS NOT NULL
        ),
        mrp AS (
            SELECT COALESCE(NULLIF(project_code, ''), '') AS project_code,
                   COALESCE(NULLIF(cabinet_no, ''), '') AS cabinet_no,
                   COUNT(*) AS shortage_lines
            FROM mrp_requirements
            WHERE COALESCE(shortage_quantity, 0) > 0
            GROUP BY COALESCE(NULLIF(project_code, ''), ''), COALESCE(NULLIF(cabinet_no, ''), '')
        ),
        po AS (
            SELECT COALESCE(NULLIF(po.project_code, ''), '') AS project_code,
                   COALESCE(NULLIF(po.cabinet_no, ''), '') AS cabinet_no,
                   COUNT(*) FILTER (
                       WHERE GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) > 0
                   ) AS pending_purchase_lines
            FROM purchase_orders po
            LEFT JOIN purchase_order_items poi ON poi.order_id=po.id
            GROUP BY COALESCE(NULLIF(po.project_code, ''), ''), COALESCE(NULLIF(po.cabinet_no, ''), '')
        ),
        wo AS (
            SELECT COALESCE(NULLIF(project_code, ''), '') AS project_code,
                   COALESCE(NULLIF(cabinet_no, ''), '') AS cabinet_no,
                   COUNT(*) FILTER (
                       WHERE COALESCE(status, '') NOT IN ('已完工','已关闭','已完成','closed','completed')
                   ) AS unfinished_work_orders
            FROM work_orders
            GROUP BY COALESCE(NULLIF(project_code, ''), ''), COALESCE(NULLIF(cabinet_no, ''), '')
        ),
        ar AS (
            SELECT COALESCE(NULLIF(project_code, ''), '') AS project_code,
                   COALESCE(NULLIF(cabinet_no, ''), '') AS cabinet_no,
                   COALESCE(SUM(balance), 0) AS receivable_balance
            FROM customer_receivables
            GROUP BY COALESCE(NULLIF(project_code, ''), ''), COALESCE(NULLIF(cabinet_no, ''), '')
        )
        SELECT bo.*,
               CASE
                   WHEN pm.id IS NULL THEN '项目未建档'
                   WHEN bo.cabinet_no IS NOT NULL AND msm.id IS NULL THEN '柜号未建档'
                   WHEN msm.project_code IS NOT NULL AND bo.project_code IS NOT NULL AND msm.project_code<>bo.project_code THEN '柜号项目不一致'
                   WHEN COALESCE(mrp.shortage_lines,0) > 0 THEN 'MRP缺料'
                   WHEN COALESCE(po.pending_purchase_lines,0) > 0 THEN '采购未收'
                   WHEN COALESCE(wo.unfinished_work_orders,0) > 0 THEN '生产未完工'
                   WHEN COALESCE(ar.receivable_balance,0) > 0 THEN '应收未清'
                   ELSE ''
               END AS blocked_reason,
               COALESCE(mrp.shortage_lines,0) AS shortage_lines,
               COALESCE(po.pending_purchase_lines,0) AS pending_purchase_lines,
               COALESCE(wo.unfinished_work_orders,0) AS unfinished_work_orders,
               COALESCE(ar.receivable_balance,0) AS receivable_balance
        FROM base_orders bo
        LEFT JOIN project_masters pm ON pm.project_code=bo.project_code
        LEFT JOIN cabinet_masters msm ON msm.cabinet_no=bo.cabinet_no
        LEFT JOIN mrp ON mrp.project_code=COALESCE(NULLIF(bo.project_code,''), '') OR mrp.cabinet_no=COALESCE(NULLIF(bo.cabinet_no,''), '')
        LEFT JOIN po ON po.project_code=COALESCE(NULLIF(bo.project_code,''), '') OR po.cabinet_no=COALESCE(NULLIF(bo.cabinet_no,''), '')
        LEFT JOIN wo ON wo.project_code=COALESCE(NULLIF(bo.project_code,''), '') OR wo.cabinet_no=COALESCE(NULLIF(bo.cabinet_no,''), '')
        LEFT JOIN ar ON ar.project_code=COALESCE(NULLIF(bo.project_code,''), '') OR ar.cabinet_no=COALESCE(NULLIF(bo.cabinet_no,''), '')
        WHERE pm.id IS NULL
           OR (bo.cabinet_no IS NOT NULL AND msm.id IS NULL)
           OR (msm.project_code IS NOT NULL AND bo.project_code IS NOT NULL AND msm.project_code<>bo.project_code)
           OR COALESCE(mrp.shortage_lines,0) > 0
           OR COALESCE(po.pending_purchase_lines,0) > 0
           OR COALESCE(wo.unfinished_work_orders,0) > 0
           OR COALESCE(ar.receivable_balance,0) > 0
        ORDER BY
            CASE
                WHEN pm.id IS NULL THEN 0
                WHEN bo.cabinet_no IS NOT NULL AND msm.id IS NULL THEN 1
                WHEN COALESCE(mrp.shortage_lines,0) > 0 THEN 2
                WHEN COALESCE(wo.unfinished_work_orders,0) > 0 THEN 3
                ELSE 4
            END,
            bo.id DESC
        LIMIT 8
        """
    )
    focus_rows = []
    for row in rows:
        reason = row.get("blocked_reason") or "待跟进"
        owner = "销售/项目"
        next_step = "进入项目台账核对"
        if reason == "MRP缺料":
            owner = "计划/采购"
            next_step = "查看齐套和采购建议"
        elif reason == "采购未收":
            owner = "采购/仓库"
            next_step = "跟进采购到货"
        elif reason == "生产未完工":
            owner = "生产"
            next_step = "进入工单列表处理领料、报工和完工"
        elif reason == "应收未清":
            owner = "财务/销售"
            next_step = "进入待收款清单"
        elif reason in {"项目未建档", "柜号未建档", "柜号项目不一致"}:
            owner = "销售/项目"
            next_step = "维护项目档案和柜号档案"
        focus_rows.append(
            {
                "order_no": row.get("order_no"),
                "project_code": row.get("project_code"),
                "cabinet_no": row.get("cabinet_no"),
                "customer_name": row.get("customer_name"),
                "blocked_reason": reason,
                "owner": owner,
                "next_step": next_step,
                "detail_url": f"/projects/{row.get('id')}",
            }
        )
    return focus_rows


def build_project_delivery_workbench(query_db):
    active_projects = query_db(
        """
        SELECT COUNT(*) AS value
        FROM sales_orders
        WHERE COALESCE(status, '') NOT IN ('已关闭','已作废','已完成','closed','voided','completed')
        """,
        one=True,
    )
    project_missing = query_db(
        """
        SELECT COUNT(*) AS value
        FROM sales_orders so
        LEFT JOIN project_masters pm ON pm.project_code=so.project_code
        WHERE NULLIF(TRIM(COALESCE(so.project_code,'')), '') IS NOT NULL
          AND pm.id IS NULL
        """,
        one=True,
    )
    cabinet_missing = query_db(
        """
        SELECT COUNT(*) AS value
        FROM sales_orders so
        LEFT JOIN cabinet_masters msm ON msm.cabinet_no=so.cabinet_no
        WHERE NULLIF(TRIM(COALESCE(so.cabinet_no,'')), '') IS NOT NULL
          AND msm.id IS NULL
        """,
        one=True,
    )
    shortage = query_db(
        """
        SELECT COUNT(*) AS lines,
               COUNT(DISTINCT COALESCE(project_code, '') || '|' || COALESCE(cabinet_no, '')) AS projects
        FROM mrp_requirements
        WHERE COALESCE(shortage_quantity, 0) > 0
        """,
        one=True,
    )
    pending_purchase = query_db(
        """
        SELECT COUNT(*) AS value
        FROM purchase_orders po
        JOIN purchase_order_items poi ON poi.order_id=po.id
        WHERE GREATEST(COALESCE(poi.quantity,0)-COALESCE(poi.received_qty,0),0) > 0
        """,
        one=True,
    )
    unfinished_work = query_db(
        """
        SELECT COUNT(*) AS value
        FROM work_orders
        WHERE COALESCE(status, '') NOT IN ('已完工','已关闭','已完成','closed','completed')
        """,
        one=True,
    )
    shipments = query_db("SELECT COUNT(*) AS value FROM sales_shipments", one=True)
    receivables = query_db(
        """
        SELECT COALESCE(SUM(balance),0) AS balance,
               COUNT(*) FILTER (WHERE COALESCE(balance,0) > 0) AS count
        FROM customer_receivables
        """,
        one=True,
    )

    project_risk_count = _scalar(project_missing, "value") + _scalar(cabinet_missing, "value")
    process_nodes = [
        {"label": "销售项目", "count": _scalar(active_projects, "value"), "hint": "未关闭销售项目", "url": "/sales-orders"},
        {"label": "项目/柜号建档", "count": project_risk_count, "hint": "缺档或追溯风险", "url": "/project-master"},
        {"label": "BOM/MRP齐套", "count": _scalar(shortage, "lines"), "hint": "缺料行", "url": "/engineering/kitting"},
        {"label": "采购到货", "count": _scalar(pending_purchase, "value"), "hint": "采购未收行", "url": "/purchase-orders?risk=pending_receive"},
        {"label": "生产完工", "count": _scalar(unfinished_work, "value"), "hint": "未完工单", "url": "/work-orders"},
        {"label": "发货交付", "count": _scalar(shipments, "value"), "hint": "发货单", "url": "/shipments"},
        {"label": "应收回款", "count": _money(_scalar(receivables, "balance")), "hint": "应收余额", "url": "/finance/receivables/pending-collections"},
        {"label": "服务追溯", "count": "台账", "hint": "按柜号追溯", "url": "/projects"},
    ]
    queue_cards = [
        {
            "title": "项目/柜号风险",
            "count": project_risk_count,
            "owner": "销售/项目",
            "next_step": "补齐项目档案、柜号档案或修正归属",
            "impact": "影响销售、生产、发货、服务和成本追溯",
            "url": "/project-master",
        },
        {
            "title": "MRP缺料",
            "count": _scalar(shortage, "lines"),
            "owner": "计划/采购",
            "next_step": "查看齐套缺口并转采购/委外跟进",
            "impact": "影响生产开工、领料和项目交付",
            "url": "/engineering/kitting",
        },
        {
            "title": "采购未收",
            "count": _scalar(pending_purchase, "value"),
            "owner": "采购/仓库",
            "next_step": "进入待收货订单，处理到货和入库",
            "impact": "影响齐套、库存和应付确认",
            "url": "/purchase-orders?risk=pending_receive",
        },
        {
            "title": "生产未完工",
            "count": _scalar(unfinished_work, "value"),
            "owner": "生产",
            "next_step": "处理领料、报工、完工入库",
            "impact": "影响发货、售后和项目成本",
            "url": "/work-orders",
        },
        {
            "title": "应收未清",
            "count": _money(_scalar(receivables, "balance")),
            "owner": "财务/销售",
            "next_step": "进入待收款清单，跟进核销",
            "impact": "影响现金流、期间结账和经营报表",
            "url": "/finance/receivables/pending-collections",
        },
    ]
    metrics = [
        {"label": "在制项目", "value": _scalar(active_projects, "value"), "hint": "销售项目未关闭"},
        {"label": "缺料行", "value": _scalar(shortage, "lines"), "hint": f"{_scalar(shortage, 'projects')} 个项目受影响"},
        {"label": "未完工单", "value": _scalar(unfinished_work, "value"), "hint": "生产待闭环"},
        {"label": "应收余额", "value": _money(_scalar(receivables, "balance")), "hint": f"{_scalar(receivables, 'count')} 条未清"},
    ]
    return {
        "metrics": metrics,
        "process_nodes": process_nodes,
        "queue_cards": queue_cards,
        "focus_rows": _build_project_focus_rows(query_db),
    }


def render_project_delivery_workbench(query_db):
    context = build_project_delivery_workbench(query_db)
    return render_template("project_delivery_workbench.html", **context)


def register_routes(app, deps):
    query_db = deps["query_db"]
    login_required = deps["login_required"]

    @app.get("/project-delivery-workbench", endpoint="project_delivery_workbench")
    @login_required
    def project_delivery_workbench():
        return render_project_delivery_workbench(query_db)
