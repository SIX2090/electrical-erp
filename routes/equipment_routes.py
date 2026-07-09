"""Equipment routes: work center equipment list and OEE calculation."""
from flask import render_template


def equipment_oee_expr():
    availability = (
        "CASE WHEN COALESCE(SUM(o.planned_minutes),0) > 0 "
        "THEN COALESCE(SUM(o.run_minutes),0) / NULLIF(SUM(o.planned_minutes),0) ELSE 0 END"
    )
    performance = (
        "CASE WHEN COALESCE(SUM(o.target_quantity),0) > 0 "
        "THEN COALESCE(SUM(o.total_quantity),0) / NULLIF(SUM(o.target_quantity),0) ELSE 0 END"
    )
    quality = (
        "CASE WHEN COALESCE(SUM(o.total_quantity),0) > 0 "
        "THEN COALESCE(SUM(o.good_quantity),0) / NULLIF(SUM(o.total_quantity),0) ELSE 0 END"
    )
    return availability, performance, quality, f"({availability}) * ({performance}) * ({quality})"


def render_equipment_dashboard(query_rows, query_one, qty_metric, request_args, back_url="/equipment"):
    availability, performance, quality, oee = equipment_oee_expr()
    keyword = (request_args.get("keyword") or request_args.get("q") or "").strip()
    status = (request_args.get("status") or "").strip()
    where = []
    params = []
    if keyword:
        where.append("(e.code ILIKE %s OR e.name ILIKE %s OR e.model ILIKE %s OR e.work_center ILIKE %s)")
        params.extend([f"%{keyword}%"] * 4)
    if status:
        where.append("COALESCE(e.status,'')=%s")
        params.append(status)
    clause = "WHERE " + " AND ".join(where) if where else ""
    rows = query_rows(
        f"""
        SELECT e.id, e.code, e.name, e.model, e.work_center, e.status, e.maintenance_status,
               COALESCE(SUM(o.planned_minutes),0) AS planned_minutes,
               COALESCE(SUM(o.run_minutes),0) AS run_minutes,
               COALESCE(SUM(o.downtime_minutes),0) AS downtime_minutes,
               COALESCE(SUM(o.total_quantity),0) AS total_quantity,
               COALESCE(SUM(o.good_quantity),0) AS good_quantity,
               ROUND(({availability}) * 100, 1) AS availability_rate,
               ROUND(({performance}) * 100, 1) AS performance_rate,
               ROUND(({quality}) * 100, 1) AS quality_rate,
               ROUND(({oee}) * 100, 1) AS oee_rate,
               CASE
                 WHEN COALESCE(e.status,'') NOT IN ('启用','正常','active','operational') THEN '停用设备，确认处置或复机'
                 WHEN COALESCE(e.maintenance_status,'') NOT IN ('正常','完好','') THEN '安排保养/维修'
                 WHEN ({oee}) > 0 AND ({oee}) < 0.6 THEN '复盘停机和良品损失'
                 ELSE '维护台账并记录OEE'
               END AS next_step
        FROM equipment e
        LEFT JOIN equipment_oee_records o ON o.equipment_id=e.id
        {clause}
        GROUP BY e.id, e.code, e.name, e.model, e.work_center, e.status, e.maintenance_status
        ORDER BY e.id DESC
        LIMIT 100
        """,
        tuple(params),
    )
    summary = query_one(
        f"""
        SELECT COUNT(*) AS equipment_count,
               COUNT(*) FILTER (WHERE COALESCE(e.status,'') IN ('启用','正常','active','operational')) AS active_count,
               COUNT(*) FILTER (WHERE COALESCE(e.maintenance_status,'') NOT IN ('正常','完好','')) AS maintenance_count,
               ROUND(AVG(NULLIF(oee_rows.oee_rate, 0)), 1) AS avg_oee
        FROM equipment e
        LEFT JOIN (
            SELECT equipment_id, ({oee}) * 100 AS oee_rate
            FROM equipment_oee_records o
            GROUP BY equipment_id
        ) oee_rows ON oee_rows.equipment_id=e.id
        """
    ) or {}
    recent_records = query_rows(
        """
        SELECT o.id, o.record_date, e.code AS equipment_code, e.name AS equipment_name,
               o.planned_minutes, o.run_minutes, o.downtime_minutes,
               o.total_quantity, o.good_quantity, o.target_quantity, o.status, o.remark
        FROM equipment_oee_records o
        LEFT JOIN equipment e ON e.id=o.equipment_id
        ORDER BY o.record_date DESC, o.id DESC
        LIMIT 50
        """
    )
    process_rows = query_rows(
        """
        SELECT wp.id, wo.wo_no AS order_no, p.code AS product_code, p.name AS product_name,
               wp.planned_start_date, wp.planned_end_date, wp.actual_start_date, wp.actual_end_date,
               wp.planned_quantity, wp.actual_quantity, wp.status
        FROM work_order_processes wp
        LEFT JOIN work_orders wo ON wo.id=wp.work_order_id
        LEFT JOIN products p ON p.id=wo.product_id
        WHERE wp.process_operation_id IN (
            SELECT id FROM process_operations WHERE equipment_id IS NOT NULL
        )
        ORDER BY wp.id DESC
        LIMIT 50
        """
    )
    return render_template(
        "equipment_dashboard.html",
        title="设备台账",
        subtitle="维护生产设备档案、保养状态、OEE记录和工序占用，不再把设备菜单当普通占位表。",
        back_url=back_url,
        filters={"keyword": keyword, "status": status},
        metrics=[
            {"label": "设备总数", "value": summary.get("equipment_count", 0), "hint": "台账记录"},
            {"label": "启用设备", "value": summary.get("active_count", 0), "hint": "可排产设备"},
            {"label": "需维护", "value": summary.get("maintenance_count", 0), "hint": "保养/维修状态"},
            {"label": "平均OEE", "value": qty_metric(summary.get("avg_oee")) + "%", "hint": "有记录设备"},
        ],
        equipment_rows=rows,
        recent_records=recent_records,
        process_rows=process_rows,
    )
