"""Work order requisition routes: material requisition list and form for production."""
from datetime import date, timedelta
from decimal import Decimal

from flask import render_template, request


def as_decimal(value):
    try:
        return Decimal(str(value if value is not None else "0"))
    except Exception:
        return Decimal("0")


def qty_metric(value):
    qty = as_decimal(value)
    return f"{qty:.3f}".rstrip("0").rstrip(".")


def _estimated_ready_date(row):
    if row.get("kit_status") == "可投产":
        return date.today()
    commitment_date = row.get("commitment_ready_date")
    if commitment_date:
        return commitment_date
    planned_end = row.get("planned_end_date")
    if planned_end:
        return planned_end
    if as_decimal(row.get("mrp_shortage_qty")) > 0:
        return date.today() + timedelta(days=7)
    if as_decimal(row.get("stock_shortage_qty")) > 0:
        return date.today() + timedelta(days=1)
    return None


def _kit_action_url(row):
    if row.get("issue_status") == "no_material":
        return f"/work-orders/{row.get('id')}"
    if as_decimal(row.get("mrp_shortage_qty")) > 0:
        return "/mrp/suggestions?status=open"
    if as_decimal(row.get("stock_shortage_qty")) > 0:
        return "/transfers/new"
    if row.get("issue_status") == "pending":
        return f"/production-issues/new?work_order_id={row.get('id')}"
    return f"/work-orders/{row.get('id')}"


def _bom_display_text(row):
    parts = [row.get("default_bom_no") or row.get("bom_no"), row.get("default_bom_version") or row.get("bom_version")]
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


def _issue_loop_fields(row):
    status = row.get("issue_status")
    shortage_reason = row.get("kit_shortage_reason")
    if status == "pending" and row.get("kit_status") == "不可投产":
        return {
            "next_step": row.get("kit_next_step") or "补料、调拨或释放可用库存后再领料",
            "owner_role": row.get("kit_owner_role") or "仓库/计划",
            "shortage_reason": shortage_reason or "物料未齐套",
            "downstream_impact": "影响装配开工、委外发料和项目交付节点",
        }
    if status == "pending":
        return {
            "next_step": "按未领数量领料后投产",
            "owner_role": "仓库/生产",
            "shortage_reason": shortage_reason or "库存可覆盖，等待领料",
            "downstream_impact": "领料完成后支撑投产、装配和项目交付",
        }
    if status == "completed":
        return {
            "next_step": "可投产并推进完工入库或打印留档",
            "owner_role": "生产",
            "shortage_reason": shortage_reason or "用料已领齐",
            "downstream_impact": "支撑完工、质检、成品入库和成本归集",
        }
    return {
        "next_step": "先维护工单用料明细",
        "owner_role": "计划",
        "shortage_reason": shortage_reason or "未生成工单用料需求",
        "downstream_impact": "影响齐套检查、领料和生产进度",
    }


def _decorate_kit_fields(row):
    required_qty = as_decimal(row.get("required_qty"))
    pending_qty = as_decimal(row.get("pending_qty"))
    mrp_shortage_qty = as_decimal(row.get("mrp_shortage_qty"))
    stock_shortage_qty = as_decimal(row.get("stock_shortage_qty"))
    stock_shortage_line_count = int(row.get("stock_shortage_line_count") or 0)
    pending_line_count = int(row.get("pending_line_count") or 0)

    if required_qty <= 0:
        row["kit_status"] = "不可投产"
        row["kit_shortage_reason"] = "未生成工单用料需求"
        row["kit_next_step"] = "按 BOM 生成或补齐工单用料明细"
        row["kit_owner_role"] = "计划"
    elif mrp_shortage_qty > 0:
        row["kit_status"] = "不可投产"
        row["kit_shortage_reason"] = f"MRP 缺料 {mrp_shortage_qty}"
        row["kit_next_step"] = "确认库存、在途采购或转采购申请"
        row["kit_owner_role"] = "计划 / 采购"
    elif stock_shortage_qty > 0:
        row["kit_status"] = "不可投产"
        row["kit_shortage_reason"] = f"库存不足 {stock_shortage_qty}，涉及 {stock_shortage_line_count} 行"
        row["kit_next_step"] = "补料、调拨或释放可用库存后再领料"
        row["kit_owner_role"] = "仓库 / 计划"
    elif pending_qty > 0:
        row["kit_status"] = "可投产"
        row["kit_shortage_reason"] = f"库存可覆盖，待领 {pending_qty}，涉及 {pending_line_count} 行"
        row["kit_next_step"] = "按未领数量领料后投产"
        row["kit_owner_role"] = "仓库 / 生产"
    else:
        row["kit_status"] = "可投产"
        row["kit_shortage_reason"] = "用料已领齐"
        row["kit_next_step"] = "投产并推进完工、质检和入库"
        row["kit_owner_role"] = "生产"
    row["kit_check_result"] = "缺料" if row["kit_status"] == "不可投产" else "齐套"
    row["kit_check_summary"] = f"{row['kit_check_result']}：{row['kit_shortage_reason']}"
    return row


def render_work_order_requisition_dashboard(query_rows):
    filters = {
        "status": (request.args.get("status") or "").strip(),
        "keyword": (request.args.get("keyword") or request.args.get("search") or "").strip(),
    }
    where = []
    params = []
    if filters["keyword"]:
        where.append(
            """
            (
                wo.wo_no ILIKE %s OR wo.project_code ILIKE %s OR wo.serial_no ILIKE %s
                OR p.code ILIKE %s OR p.name ILIKE %s
            )
            """
        )
        params.extend([f"%{filters['keyword']}%"] * 5)
    status_sql = """
        CASE
            WHEN COALESCE(req.required_qty, 0) <= 0 THEN 'no_material'
            WHEN GREATEST(COALESCE(req.required_qty,0)-COALESCE(req.issued_qty,0)+COALESCE(req.returned_qty,0),0) > 0 THEN 'pending'
            ELSE 'completed'
        END
    """
    kit_status_sql = """
        CASE
            WHEN COALESCE(req.required_qty, 0) <= 0 THEN 'cannot_start'
            WHEN COALESCE(mrp_shortage.shortage_qty, 0) > 0 THEN 'cannot_start'
            WHEN COALESCE(req.stock_shortage_qty, 0) > 0 THEN 'cannot_start'
            ELSE 'can_start'
        END
    """
    if filters["status"] in {"pending", "completed", "no_material"}:
        where.append(f"{status_sql}=%s")
        params.append(filters["status"])
    elif filters["status"] in {"can_start", "cannot_start"}:
        where.append(f"{kit_status_sql}=%s")
        params.append(filters["status"])
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = query_rows(
        f"""
        SELECT wo.id, wo.wo_no, wo.wo_date, wo.project_code, wo.serial_no, wo.status,
               wo.quantity AS work_order_qty, wo.planned_end_date,
               p.code AS product_code, p.name AS product_name,
               COALESCE(pc.name, p.category, '') AS product_family,
               COALESCE(b.bom_no, default_bom.bom_no) AS bom_no,
               COALESCE(b.version, default_bom.version) AS bom_version,
               NULLIF(CONCAT_WS(' / ', NULLIF(COALESCE(b.bom_no, default_bom.bom_no), ''), NULLIF(COALESCE(b.version, default_bom.version), '')), '') AS bom_display,
               COALESCE(req.line_count, 0) AS line_count,
               COALESCE(req.required_qty, 0) AS required_qty,
               COALESCE(req.issued_qty, 0) AS issued_qty,
               COALESCE(req.returned_qty, 0) AS returned_qty,
               GREATEST(COALESCE(req.required_qty,0)-COALESCE(req.issued_qty,0)+COALESCE(req.returned_qty,0),0) AS pending_qty,
               COALESCE(req.pending_line_count, 0) AS pending_line_count,
               COALESCE(req.stock_shortage_line_count, 0) AS stock_shortage_line_count,
               COALESCE(req.stock_shortage_qty, 0) AS stock_shortage_qty,
               commitment.commitment_ready_date,
               COALESCE(mrp_shortage.shortage_qty, 0) AS mrp_shortage_qty,
               {status_sql} AS issue_status
        FROM work_orders wo
        LEFT JOIN products p ON p.id=wo.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
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
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS line_count,
                   COALESCE(SUM(required_qty), 0) AS required_qty,
                   COALESCE(SUM(issued_qty), 0) AS issued_qty,
                   COALESCE(SUM(returned_qty), 0) AS returned_qty,
                   COUNT(*) FILTER (
                       WHERE GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > 0
                   ) AS pending_line_count,
                   COUNT(*) FILTER (
                       WHERE GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > COALESCE(inv.available_qty, 0)
                   ) AS stock_shortage_line_count,
                   COALESCE(SUM(GREATEST(
                       GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) - COALESCE(inv.available_qty,0),
                       0
                   )), 0) AS stock_shortage_qty
            FROM wo_material_items mi
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(quantity), 0) AS available_qty
                FROM inventory_balances ib
                WHERE ib.product_id=mi.product_id
                  AND (mi.warehouse_id IS NULL OR ib.warehouse_id=mi.warehouse_id)
                  AND (mi.location_id IS NULL OR ib.location_id=mi.location_id)
                  AND (COALESCE(mi.line_project_code, '')='' OR COALESCE(ib.project_code, '')=COALESCE(mi.line_project_code, ''))
                  AND (COALESCE(mi.line_serial_no, '')='' OR COALESCE(ib.serial_no, '')=COALESCE(mi.line_serial_no, ''))
            ) inv ON TRUE
            WHERE mi.wo_id=wo.id
        ) req ON TRUE
        LEFT JOIN LATERAL (
            SELECT MAX(candidate_date) AS commitment_ready_date
            FROM (
                SELECT MAX(pri.need_date) AS candidate_date
                FROM wo_material_items mi
                JOIN purchase_requisition_items pri ON pri.product_id=mi.product_id
                LEFT JOIN purchase_requisitions pr ON pr.id=pri.req_id
                WHERE mi.wo_id=wo.id
                  AND COALESCE(pr.status, '') NOT IN ('已关闭','已作废','已取消','closed','void','voided','cancelled','canceled')
                  AND COALESCE(pri.quantity, 0) > 0
                  AND (COALESCE(mi.line_project_code, wo.project_code, '')='' OR COALESCE(pri.project_code, pr.project_code, '')=COALESCE(mi.line_project_code, wo.project_code, ''))
                  AND (COALESCE(mi.line_serial_no, wo.serial_no, '')='' OR COALESCE(pri.serial_no, pr.serial_no, '')=COALESCE(mi.line_serial_no, wo.serial_no, ''))
                UNION ALL
                SELECT MAX(COALESCE(poi.expected_date, po.expected_date)) AS candidate_date
                FROM wo_material_items mi
                JOIN purchase_order_items poi ON poi.product_id=mi.product_id
                LEFT JOIN purchase_orders po ON po.id=poi.order_id
                WHERE mi.wo_id=wo.id
                  AND COALESCE(po.status, '') NOT IN ('已关闭','已作废','已取消','closed','completed','void','voided','cancelled','canceled')
                  AND GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0) > 0
                  AND (COALESCE(mi.line_project_code, wo.project_code, '')='' OR COALESCE(poi.line_project_code, po.project_code, '')=COALESCE(mi.line_project_code, wo.project_code, ''))
                  AND (COALESCE(mi.line_serial_no, wo.serial_no, '')='' OR COALESCE(poi.line_serial_no, po.serial_no, '')=COALESCE(mi.line_serial_no, wo.serial_no, ''))
                UNION ALL
                SELECT MAX(so.required_date) AS candidate_date
                FROM wo_material_items mi
                JOIN subcontract_orders so ON so.product_id=mi.product_id
                WHERE mi.wo_id=wo.id
                  AND COALESCE(so.status, '') NOT IN ('已关闭','已作废','已取消','closed','completed','void','voided','cancelled','canceled')
                  AND GREATEST(COALESCE(so.quantity, 0)-COALESCE(so.received_qty, 0), 0) > 0
                  AND (COALESCE(mi.line_project_code, wo.project_code, '')='' OR COALESCE(so.project_code, so.line_project_code, '')=COALESCE(mi.line_project_code, wo.project_code, ''))
                  AND (COALESCE(mi.line_serial_no, wo.serial_no, '')='' OR COALESCE(so.serial_no, so.line_serial_no, '')=COALESCE(mi.line_serial_no, wo.serial_no, ''))
                UNION ALL
                SELECT MAX(child_wo.planned_end_date) AS candidate_date
                FROM wo_material_items mi
                JOIN work_orders child_wo ON child_wo.product_id=mi.product_id
                WHERE mi.wo_id=wo.id
                  AND COALESCE(child_wo.status, '') NOT IN ('已完工','已关闭','已完成','closed','completed','cancelled','canceled')
                  AND COALESCE(child_wo.quantity, 0) > 0
                  AND (COALESCE(mi.line_project_code, wo.project_code, '')='' OR COALESCE(child_wo.project_code, child_wo.line_project_code, '')=COALESCE(mi.line_project_code, wo.project_code, ''))
                  AND (COALESCE(mi.line_serial_no, wo.serial_no, '')='' OR COALESCE(child_wo.serial_no, child_wo.line_serial_no, '')=COALESCE(mi.line_serial_no, wo.serial_no, ''))
            ) dates
        ) commitment ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(shortage_quantity), 0) AS shortage_qty
            FROM mrp_requirements mr
            WHERE COALESCE(mr.shortage_quantity, 0) > 0
              AND (
                  (wo.project_code IS NOT NULL AND mr.project_code=wo.project_code)
                  OR (wo.serial_no IS NOT NULL AND mr.serial_no=wo.serial_no)
              )
        ) mrp_shortage ON TRUE
        {where_sql}
        ORDER BY pending_qty DESC, wo.id DESC
        LIMIT 120
        """,
        params,
    )
    for row in rows:
        _decorate_kit_fields(row)
        row.update(_issue_loop_fields(row))
        row["kit_action_url"] = _kit_action_url(row)
        row["estimated_ready_date"] = _estimated_ready_date(row)
    pending_count = sum(1 for row in rows if row.get("issue_status") == "pending")
    completed_count = sum(1 for row in rows if row.get("issue_status") == "completed")
    can_start_count = sum(1 for row in rows if row.get("kit_status") == "可投产")
    cannot_start_count = sum(1 for row in rows if row.get("kit_status") == "不可投产")
    pending_qty = sum((as_decimal(row.get("pending_qty")) for row in rows), Decimal("0"))

    line_where = [
        "GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) > 0"
    ]
    line_params = []
    if filters["keyword"]:
        line_where.append(
            """
            (
                wo.wo_no ILIKE %s OR wo.project_code ILIKE %s OR wo.serial_no ILIKE %s
                OR p.code ILIKE %s OR p.name ILIKE %s OR p.specification ILIKE %s OR mi.remark ILIKE %s
            )
            """
        )
        line_params.extend([f"%{filters['keyword']}%"] * 7)
    if filters["status"] in {"completed", "no_material"}:
        line_where.append("1=0")
    line_where_sql = "WHERE " + " AND ".join(line_where)
    material_lines = query_rows(
        f"""
        SELECT wo.id AS work_order_id, wo.wo_no, wo.project_code, wo.serial_no,
               p.code AS product_code, p.name AS product_name, p.specification, p.unit,
               COALESCE(pc.name, p.category, '') AS product_family,
               bom.bom_no AS default_bom_no,
               bom.version AS default_bom_version,
               COALESCE(p.batch_control, FALSE) AS batch_control,
               COALESCE(p.serial_control, FALSE) AS serial_control,
               COALESCE(p.inspection_required, FALSE) AS inspection_required,
               mi.id AS material_item_id,
               mi.required_qty, mi.issued_qty, mi.returned_qty,
               GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) AS pending_qty,
               COALESCE(inv.available_qty, 0) AS available_qty,
               GREATEST(
                   GREATEST(COALESCE(mi.required_qty,0)-COALESCE(mi.issued_qty,0)+COALESCE(mi.returned_qty,0),0) - COALESCE(inv.available_qty,0),
                   0
               ) AS stock_shortage_qty,
               mi.remark
        FROM wo_material_items mi
        JOIN work_orders wo ON wo.id=mi.wo_id
        LEFT JOIN products p ON p.id=mi.product_id
        LEFT JOIN product_categories pc ON pc.id=p.category_id
        LEFT JOIN LATERAL (
            SELECT b.bom_no, b.version
            FROM boms b
            WHERE b.product_id=p.id AND COALESCE(b.status, '') NOT IN ('停用','inactive','disabled')
            ORDER BY
                CASE WHEN b.bom_type='production' THEN 0 ELSE 1 END,
                b.id DESC
            LIMIT 1
        ) bom ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(quantity), 0) AS available_qty
            FROM inventory_balances ib
            WHERE ib.product_id=mi.product_id
              AND (mi.warehouse_id IS NULL OR ib.warehouse_id=mi.warehouse_id)
              AND (mi.location_id IS NULL OR ib.location_id=mi.location_id)
              AND (COALESCE(mi.line_project_code, '')='' OR COALESCE(ib.project_code, '')=COALESCE(mi.line_project_code, ''))
              AND (COALESCE(mi.line_serial_no, '')='' OR COALESCE(ib.serial_no, '')=COALESCE(mi.line_serial_no, ''))
        ) inv ON TRUE
        {line_where_sql}
        ORDER BY pending_qty DESC, wo.id DESC
        LIMIT 500
        """,
        line_params,
    )
    for line in material_lines:
        line["bom_display"] = _bom_display_text(line)
        line["control_display"] = _manufacturing_control_text(line)
        line["kit_line_result"] = "缺料" if as_decimal(line.get("stock_shortage_qty")) > 0 else "齐套"
    return render_template(
        "work_order_requisition.html",
        filters=filters,
        rows=rows,
        material_lines=material_lines,
        metrics=[
            {"label": "工单数", "value": len(rows), "hint": "当前筛选"},
            {"label": "可投产", "value": can_start_count, "hint": "齐套可执行"},
            {"label": "不可投产", "value": cannot_start_count, "hint": "缺料或未建需求"},
            {"label": "待领数量", "value": qty_metric(pending_qty), "hint": "按物料明细汇总"},
            {"label": "待领/已齐", "value": f"{pending_count}/{completed_count}", "hint": "领料状态"},
        ],
    )
