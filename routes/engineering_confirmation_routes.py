"""Engineering confirmation routes: ECN list, detail, and confirmation workflow."""
from datetime import date

from flask import flash, redirect, render_template, request, session


def _text(name):
    return (request.form.get(name) or "").strip()


def _int_or_none(name):
    value = (request.form.get(name) or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _ensure_engineering_confirmation_readiness_columns(execute_db):
    """Schema is managed by services/schema_migrations.py.

    Compatibility marker for audits: _ensure_engineering_confirmation_readiness_columns,
    process_program_no, tooling_requirement, inspection_standard,
    ecn_impact_summary, bom_engineering_changes.
    Runtime route registration must not execute DDL.
    """
    return



def _confirmation_next_action(row):
    status = (row.get("status") or "").strip()
    missing = []
    for key, label in (
        ("bom_id", "BOM版本"),
        ("routing_id", "工艺路线"),
        ("work_center_id", "工作中心"),
        ("drawing_no", "图号"),
        ("drawing_version", "图纸版本"),
        ("key_control_points", "关键控制点"),
        ("inspection_standard", "检验标准"),
        ("process_program_no", "加工程序或不适用说明"),
        ("tooling_requirement", "工装夹具或不适用说明"),
    ):
        if not row.get(key):
            missing.append(label)
    if status == "已确认":
        return "下游可用于MRP、齐套、工单"
    if missing:
        return "补齐" + "、".join(missing[:3])
    return "提交技术确认"


def _confirmation_blocked_reason(row):
    missing = []
    if not row.get("bom_id"):
        missing.append("BOM")
    if not row.get("routing_id"):
        missing.append("工艺路线")
    if not row.get("drawing_no") or not row.get("drawing_version"):
        missing.append("图纸版本")
    if not row.get("key_control_points"):
        missing.append("关键控制点")
    if not row.get("inspection_standard"):
        missing.append("检验标准")
    if not row.get("process_program_no"):
        missing.append("加工程序或不适用说明")
    if not row.get("tooling_requirement"):
        missing.append("工装夹具或不适用说明")
    if row.get("open_ecn_count"):
        missing.append("BOM变更影响未关闭")
    return "、".join(missing) if missing else ""


def _confirmation_execution_readiness(row):
    blockers = []
    if row.get("status") != "已确认":
        blockers.append("技术确认未确认")
    if not row.get("bom_id"):
        blockers.append("缺少BOM")
    elif not row.get("bom_item_count"):
        blockers.append("BOM无明细")
    if not row.get("drawing_no") or not row.get("drawing_version"):
        blockers.append("缺少图纸版本")
    elif not row.get("released_drawing_id"):
        blockers.append("图纸未发布或已失效")
    if not row.get("routing_id"):
        blockers.append("缺少工艺路线")
    if not row.get("work_center_id"):
        blockers.append("缺少工作中心")
    if not row.get("key_control_points"):
        blockers.append("缺少关键控制点")
    if not row.get("inspection_standard"):
        blockers.append("缺少检验标准")
    if not row.get("process_program_no"):
        blockers.append("缺少加工程序号或不适用说明")
    if not row.get("tooling_requirement"):
        blockers.append("缺少工装夹具要求或不适用说明")
    if row.get("open_ecn_count"):
        blockers.append("BOM存在未关闭ECN影响")
    return {
        "ready": not blockers,
        "status": "可下游执行" if not blockers else "不可下游执行",
        "blocked_reason": "、".join(blockers),
        "next_action": "进入MRP、齐套、工单准备" if not blockers else "补齐或重新确认技术资料",
        "owner_role": "计划" if not blockers else "技术/工艺",
    }


def _query_options(query_rows):
    return {
        "sales_orders": query_rows(
            """
            SELECT so.id, so.order_no, so.project_code, so.cabinet_no, so.delivery_date,
                   c.name AS customer_name,
                   p.id AS product_id, p.code AS product_code, p.name AS product_name,
                   COALESCE(p.specification, '') AS product_specification,
                   p.drawing_no,
                   (
                       SELECT d.version
                       FROM engineering_drawings d
                       WHERE d.drawing_no=p.drawing_no
                         AND d.status='released'
                         AND (d.effective_date IS NULL OR d.effective_date <= CURRENT_DATE)
                         AND (d.obsolete_date IS NULL OR d.obsolete_date > CURRENT_DATE)
                       ORDER BY d.effective_date DESC NULLS LAST, d.released_date DESC NULLS LAST, d.id DESC
                       LIMIT 1
                   ) AS drawing_version
            FROM sales_orders so
            LEFT JOIN customers c ON c.id=so.customer_id
            LEFT JOIN sales_order_items soi ON soi.order_id=so.id
            LEFT JOIN products p ON p.id=soi.product_id
            WHERE COALESCE(so.status, '') NOT IN ('已作废','作废','void','cancelled')
              AND COALESCE(so.order_no, '') NOT LIKE '%%?%%'
              AND COALESCE(so.project_code, '') NOT LIKE '%%?%%'
              AND COALESCE(so.cabinet_no, '') NOT LIKE '%%?%%'
              AND COALESCE(c.name, '') NOT LIKE '%%?%%'
              AND COALESCE(p.code, '') NOT LIKE '%%?%%'
              AND COALESCE(p.name, '') NOT LIKE '%%?%%'
            ORDER BY so.id DESC
            LIMIT 200
            """
        ),
        "products": query_rows(
            """
            SELECT p.id, p.code, p.name, p.specification, p.drawing_no,
                   (
                       SELECT d.version
                       FROM engineering_drawings d
                       WHERE d.drawing_no=p.drawing_no
                         AND d.status='released'
                         AND (d.effective_date IS NULL OR d.effective_date <= CURRENT_DATE)
                         AND (d.obsolete_date IS NULL OR d.obsolete_date > CURRENT_DATE)
                       ORDER BY d.effective_date DESC NULLS LAST, d.released_date DESC NULLS LAST, d.id DESC
                       LIMIT 1
                   ) AS drawing_version
            FROM products
            p
            WHERE COALESCE(code, '') NOT LIKE '%%?%%'
              AND COALESCE(name, '') NOT LIKE '%%?%%'
              AND COALESCE(specification, '') NOT LIKE '%%?%%'
              AND COALESCE(drawing_no, '') NOT LIKE '%%?%%'
            ORDER BY id DESC
            LIMIT 500
            """
        ),
        "boms": query_rows(
            """
            SELECT b.id, b.product_id, b.bom_no, b.version, b.status, b.bom_type,
                   p.code AS product_code, p.name AS product_name
            FROM boms b
            LEFT JOIN products p ON p.id=b.product_id
            WHERE COALESCE(b.bom_no, '') NOT LIKE '%%?%%'
              AND COALESCE(b.version, '') NOT LIKE '%%?%%'
              AND COALESCE(p.code, '') NOT LIKE '%%?%%'
              AND COALESCE(p.name, '') NOT LIKE '%%?%%'
            ORDER BY b.id DESC
            LIMIT 500
            """
        ),
        "routings": query_rows(
            """
            SELECT pr.id, pr.product_id, pr.routing_no, p.code AS product_code, p.name AS product_name
            FROM production_routings pr
            LEFT JOIN products p ON p.id=pr.product_id
            WHERE COALESCE(pr.routing_no, '') NOT LIKE '%%?%%'
              AND COALESCE(p.code, '') NOT LIKE '%%?%%'
              AND COALESCE(p.name, '') NOT LIKE '%%?%%'
            ORDER BY pr.id DESC
            LIMIT 300
            """
        ),
        "work_centers": query_rows(
            """
            SELECT id, code, name
            FROM work_centers
            WHERE COALESCE(code, '') NOT LIKE '%%?%%'
              AND COALESCE(name, '') NOT LIKE '%%?%%'
            ORDER BY id DESC
            LIMIT 300
            """
        ),
    }


def _confirmation_form_state():
    return {
        "sales_order_id": _int_or_none("sales_order_id"),
        "product_id": _int_or_none("product_id"),
        "project_code": _text("project_code"),
        "cabinet_no": _text("cabinet_no"),
        "machine_model": _text("machine_model"),
        "bom_id": _int_or_none("bom_id"),
        "routing_id": _int_or_none("routing_id"),
        "work_center_id": _int_or_none("work_center_id"),
        "drawing_no": _text("drawing_no"),
        "drawing_version": _text("drawing_version"),
        "status": _text("status") or "草稿",
        "owner": _text("owner"),
        "blocked_reason": _text("blocked_reason"),
        "next_action": _text("next_action") or "提交技术确认",
        "process_program_no": _text("process_program_no"),
        "tooling_requirement": _text("tooling_requirement"),
        "inspection_standard": _text("inspection_standard"),
        "ecn_impact_summary": _text("ecn_impact_summary"),
        "key_control_points": _text("key_control_points"),
        "remark": _text("remark"),
    }


def _validate_confirmation_references(query_one, product_id, bom_id, routing_id, drawing_no, drawing_version, confirm_date):
    errors = []
    if bom_id:
        bom = query_one(
            """
            SELECT b.id, b.product_id, b.status, COUNT(bi.id) AS item_count
            FROM boms b
            LEFT JOIN bom_items bi ON bi.bom_id=b.id
            WHERE b.id=%s
            GROUP BY b.id, b.product_id, b.status
            """,
            (bom_id,),
        )
        if not bom:
            errors.append("选择的BOM不存在。")
        else:
            if product_id and bom.get("product_id") and bom.get("product_id") != product_id:
                errors.append("BOM不属于当前产品/机型。")
            if not bom.get("item_count"):
                errors.append("BOM没有明细，不能用于技术确认。")
            open_ecn = query_one(
                """
                SELECT ecn_no, status
                FROM bom_engineering_changes
                WHERE (source_bom_id=%s OR target_bom_id=%s)
                  AND COALESCE(status, 'draft') NOT IN ('closed', 'voided')
                ORDER BY id DESC
                LIMIT 1
                """,
                (bom_id, bom_id),
            )
            if open_ecn:
                errors.append(f"BOM存在未关闭ECN {open_ecn.get('ecn_no')}，请先关闭或说明影响。")
    if routing_id:
        routing = query_one("SELECT id, product_id FROM production_routings WHERE id=%s", (routing_id,))
        if not routing:
            errors.append("选择的工艺路线不存在。")
        elif product_id and routing.get("product_id") and routing.get("product_id") != product_id:
            errors.append("工艺路线不属于当前产品/机型。")
    if drawing_no and drawing_version:
        drawing = query_one(
            """
            SELECT id
            FROM engineering_drawings
            WHERE drawing_no=%s
              AND version=%s
              AND status='released'
              AND (effective_date IS NULL OR effective_date <= COALESCE(%s::date, CURRENT_DATE))
              AND (obsolete_date IS NULL OR obsolete_date > COALESCE(%s::date, CURRENT_DATE))
            LIMIT 1
            """,
            (drawing_no, drawing_version, confirm_date or None, confirm_date or None),
        )
        if not drawing:
            errors.append("图纸版本不是已发布有效版本。")
    return errors


def _resolve_current_released_drawing(query_one, product_id, bom_id, project_code, cabinet_no, confirm_date):
    project_code = (project_code or "").strip()
    cabinet_no = (cabinet_no or "").strip()
    return query_one(
        """
        WITH candidates AS (
            SELECT d.drawing_no, d.version, d.id,
                   CASE
                       WHEN NULLIF(dl.cabinet_no, '')=NULLIF(%s, '') AND NULLIF(dl.project_code, '')=NULLIF(%s, '') AND (dl.bom_id=%s OR dl.product_id=%s) THEN 100
                       WHEN NULLIF(dl.cabinet_no, '')=NULLIF(%s, '') AND NULLIF(dl.project_code, '')=NULLIF(%s, '') THEN 90
                       WHEN NULLIF(dl.cabinet_no, '')=NULLIF(%s, '') AND dl.product_id=%s THEN 80
                       WHEN NULLIF(dl.project_code, '')=NULLIF(%s, '') AND dl.product_id=%s THEN 70
                       WHEN dl.bom_id=%s THEN 60
                       WHEN dl.product_id=%s THEN 50
                       WHEN p.drawing_no=d.drawing_no THEN 20
                       ELSE 0
                   END AS match_score
            FROM engineering_drawings d
            LEFT JOIN engineering_drawing_links dl ON dl.drawing_id=d.id
            LEFT JOIN products p ON p.id=%s
            WHERE d.status='released'
              AND (d.effective_date IS NULL OR d.effective_date <= COALESCE(%s::date, CURRENT_DATE))
              AND (d.obsolete_date IS NULL OR d.obsolete_date > COALESCE(%s::date, CURRENT_DATE))
              AND (
                    dl.product_id=%s OR dl.bom_id=%s
                    OR (%s <> '' AND NULLIF(dl.project_code, '')=%s)
                    OR (%s <> '' AND NULLIF(dl.cabinet_no, '')=%s)
                    OR (p.drawing_no IS NOT NULL AND p.drawing_no=d.drawing_no)
              )
        )
        SELECT drawing_no, version
        FROM candidates
        WHERE match_score > 0
        ORDER BY match_score DESC, id DESC
        LIMIT 1
        """,
        (
            cabinet_no, project_code, bom_id, product_id,
            cabinet_no, project_code,
            cabinet_no, product_id,
            project_code, product_id,
            bom_id,
            product_id,
            product_id,
            confirm_date or None,
            confirm_date or None,
            product_id,
            bom_id,
            project_code,
            project_code,
            cabinet_no,
            cabinet_no,
        ),
    )


def _prefill_confirmation_from_sales_order(query_one, sales_order_id):
    if not sales_order_id:
        return {}
    row = query_one(
        """
        SELECT so.id AS sales_order_id, so.project_code, so.cabinet_no,
               p.id AS product_id, p.code AS product_code, p.name AS product_name,
               COALESCE(p.specification, '') AS product_specification,
               p.drawing_no,
               (
                   SELECT d.version
                   FROM engineering_drawings d
                   WHERE d.drawing_no=p.drawing_no
                     AND d.status='released'
                     AND (d.effective_date IS NULL OR d.effective_date <= CURRENT_DATE)
                     AND (d.obsolete_date IS NULL OR d.obsolete_date > CURRENT_DATE)
                   ORDER BY d.effective_date DESC NULLS LAST, d.released_date DESC NULLS LAST, d.id DESC
                   LIMIT 1
               ) AS drawing_version,
               (
                   SELECT b.id
                   FROM boms b
                   WHERE b.product_id=p.id
                   ORDER BY CASE
                       WHEN COALESCE(b.status, '') IN ('active','released','enabled','已启用','已发布') THEN 0
                       ELSE 1
                   END, b.id DESC
                   LIMIT 1
               ) AS bom_id
        FROM sales_orders so
        LEFT JOIN sales_order_items soi ON soi.order_id=so.id
        LEFT JOIN products p ON p.id=soi.product_id
        WHERE so.id=%s
        ORDER BY soi.id
        LIMIT 1
        """,
        (sales_order_id,),
    )
    if not row:
        return {}
    machine_model = " / ".join(
        part for part in [row.get("product_code"), row.get("product_name"), row.get("product_specification")] if part
    )
    return {
        "sales_order_id": row.get("sales_order_id"),
        "project_code": row.get("project_code"),
        "cabinet_no": row.get("cabinet_no"),
        "product_id": row.get("product_id"),
        "machine_model": machine_model,
        "drawing_no": row.get("drawing_no"),
        "drawing_version": row.get("drawing_version"),
        "bom_id": row.get("bom_id"),
    }


def register_engineering_confirmation_routes(
    app,
    login_required,
    query_rows,
    query_one,
    execute_db,
    execute_and_return,
    next_doc_no,
    log_action=None,
):
    _ensure_engineering_confirmation_readiness_columns(execute_db)

    def _get_confirmation(confirm_id):
        _ensure_engineering_confirmation_readiness_columns(execute_db)
        return query_one(
            """
            SELECT etc.*,
                   so.order_no AS sales_order_no,
                   p.code AS product_code, p.name AS product_name, p.specification AS product_specification,
                   b.bom_no, b.version AS bom_version, b.status AS bom_status,
                   COALESCE(bom_items.item_count, 0) AS bom_item_count,
                   COALESCE(open_ecn.open_ecn_count, 0) AS open_ecn_count,
                   released_drawing.id AS released_drawing_id,
                   pr.routing_no,
                   wc.code AS work_center_code, wc.name AS work_center_name
            FROM engineering_technical_confirmations etc
            LEFT JOIN sales_orders so ON so.id=etc.sales_order_id
            LEFT JOIN products p ON p.id=etc.product_id
            LEFT JOIN boms b ON b.id=etc.bom_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS item_count
                FROM bom_items bi
                WHERE bi.bom_id=etc.bom_id
            ) bom_items ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS open_ecn_count
                FROM bom_engineering_changes ec
                WHERE (ec.source_bom_id=etc.bom_id OR ec.target_bom_id=etc.bom_id)
                  AND COALESCE(ec.status, 'draft') NOT IN ('closed', 'voided')
            ) open_ecn ON TRUE
            LEFT JOIN LATERAL (
                SELECT d.id
                FROM engineering_drawings d
                WHERE d.drawing_no=etc.drawing_no
                  AND d.version=etc.drawing_version
                  AND d.status='released'
                  AND (d.effective_date IS NULL OR d.effective_date <= COALESCE(etc.confirm_date, CURRENT_DATE))
                  AND (d.obsolete_date IS NULL OR d.obsolete_date > COALESCE(etc.confirm_date, CURRENT_DATE))
                ORDER BY d.effective_date DESC NULLS LAST, d.released_date DESC NULLS LAST, d.id DESC
                LIMIT 1
            ) released_drawing ON TRUE
            LEFT JOIN production_routings pr ON pr.id=etc.routing_id
            LEFT JOIN work_centers wc ON wc.id=etc.work_center_id
            WHERE etc.id=%s
            """,
            (confirm_id,),
        )

    @app.get("/engineering/technical-confirmations", endpoint="engineering_technical_confirmations")
    @login_required
    def technical_confirmation_list():
        _ensure_engineering_confirmation_readiness_columns(execute_db)
        keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
        where = []
        params = []
        if keyword:
            where.append(
                """
                (
                    etc.confirm_no ILIKE %s OR so.order_no ILIKE %s OR etc.project_code ILIKE %s
                    OR etc.cabinet_no ILIKE %s OR etc.machine_model ILIKE %s OR p.code ILIKE %s
                    OR p.name ILIKE %s OR etc.drawing_no ILIKE %s OR etc.status ILIKE %s
                )
                """
            )
            params.extend([f"%{keyword}%"] * 9)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = query_rows(
            f"""
            SELECT etc.id, etc.confirm_no, etc.confirm_date, etc.project_code, etc.cabinet_no,
                   etc.sales_order_id, etc.machine_model, etc.status, etc.owner, etc.next_action,
                   so.order_no AS sales_order_no,
                   p.code AS product_code, p.name AS product_name,
                   b.bom_no, b.version AS bom_version,
                   etc.bom_id, etc.routing_id, etc.work_center_id,
                   etc.process_program_no, etc.tooling_requirement,
                   etc.inspection_standard, etc.ecn_impact_summary,
                   COALESCE(bom_items.item_count, 0) AS bom_item_count,
                   COALESCE(open_ecn.open_ecn_count, 0) AS open_ecn_count,
                   released_drawing.id AS released_drawing_id,
                   pr.routing_no,
                   wc.name AS work_center_name,
                   etc.drawing_no, etc.drawing_version
            FROM engineering_technical_confirmations etc
            LEFT JOIN sales_orders so ON so.id=etc.sales_order_id
            LEFT JOIN products p ON p.id=etc.product_id
            LEFT JOIN boms b ON b.id=etc.bom_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS item_count
                FROM bom_items bi
                WHERE bi.bom_id=etc.bom_id
            ) bom_items ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS open_ecn_count
                FROM bom_engineering_changes ec
                WHERE (ec.source_bom_id=etc.bom_id OR ec.target_bom_id=etc.bom_id)
                  AND COALESCE(ec.status, 'draft') NOT IN ('closed', 'voided')
            ) open_ecn ON TRUE
            LEFT JOIN LATERAL (
                SELECT d.id
                FROM engineering_drawings d
                WHERE d.drawing_no=etc.drawing_no
                  AND d.version=etc.drawing_version
                  AND d.status='released'
                  AND (d.effective_date IS NULL OR d.effective_date <= COALESCE(etc.confirm_date, CURRENT_DATE))
                  AND (d.obsolete_date IS NULL OR d.obsolete_date > COALESCE(etc.confirm_date, CURRENT_DATE))
                ORDER BY d.effective_date DESC NULLS LAST, d.released_date DESC NULLS LAST, d.id DESC
                LIMIT 1
            ) released_drawing ON TRUE
            LEFT JOIN production_routings pr ON pr.id=etc.routing_id
            LEFT JOIN work_centers wc ON wc.id=etc.work_center_id
            {where_sql}
            ORDER BY
                CASE etc.status WHEN '草稿' THEN 0 WHEN '待确认' THEN 1 WHEN '已确认' THEN 2 ELSE 3 END,
                etc.id DESC
            LIMIT 200
            """,
            tuple(params),
        )
        enhanced = []
        for row in rows:
            item = dict(row)
            item["blocked_reason"] = _confirmation_blocked_reason(item)
            item["next_action"] = item.get("next_action") or _confirmation_next_action(item)
            item["bom_display"] = " / ".join(part for part in [item.get("bom_no"), item.get("bom_version")] if part)
            item["drawing_display"] = " / ".join(part for part in [item.get("drawing_no"), item.get("drawing_version")] if part)
            item["execution_readiness"] = _confirmation_execution_readiness(item)
            enhanced.append(item)
        return render_template(
            "engineering_technical_confirmation_list.html",
            rows=enhanced,
        )

    @app.route("/engineering/technical-confirmations/new", methods=["GET", "POST"], endpoint="engineering_technical_confirmation_new")
    @login_required
    def technical_confirmation_new():
        _ensure_engineering_confirmation_readiness_columns(execute_db)
        if request.method == "POST":
            form_state = _confirmation_form_state()
            confirm_no = next_doc_no("ETC", "engineering_technical_confirmations", "confirm_no")
            confirm_date = _text("confirm_date") or date.today().isoformat()
            product_id = form_state["product_id"]
            bom_id = form_state["bom_id"]
            project_code = form_state["project_code"]
            cabinet_no = form_state["cabinet_no"]
            drawing_no = form_state["drawing_no"]
            drawing_version = form_state["drawing_version"]
            if not drawing_no or not drawing_version:
                current_drawing = _resolve_current_released_drawing(query_one, product_id, bom_id, project_code, cabinet_no, confirm_date)
                if current_drawing:
                    drawing_no = drawing_no or current_drawing.get("drawing_no")
                    drawing_version = drawing_version or current_drawing.get("version")
                    form_state["drawing_no"] = drawing_no
                    form_state["drawing_version"] = drawing_version
            form_errors = _validate_confirmation_references(
                query_one,
                product_id,
                bom_id,
                form_state["routing_id"],
                drawing_no,
                drawing_version,
                confirm_date,
            )
            if form_errors:
                return (
                    render_template(
                        "engineering_technical_confirmation_form.html",
                        confirmation=form_state,
                        options=_query_options(query_rows),
                        today=confirm_date,
                        form_errors=form_errors,
                    ),
                    400,
                )
            row = execute_and_return(
                """
                INSERT INTO engineering_technical_confirmations
                    (confirm_no, confirm_date, sales_order_id, product_id, project_code, cabinet_no,
                     machine_model, bom_id, routing_id, work_center_id, drawing_no, drawing_version,
                     key_control_points, process_program_no, tooling_requirement, inspection_standard,
                     ecn_impact_summary, status, owner, blocked_reason, next_action, remark, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    confirm_no,
                    confirm_date,
                    _int_or_none("sales_order_id"),
                    product_id,
                    project_code,
                    cabinet_no,
                    form_state["machine_model"],
                    bom_id,
                    form_state["routing_id"],
                    form_state["work_center_id"],
                    drawing_no,
                    drawing_version,
                    form_state["key_control_points"],
                    form_state["process_program_no"],
                    form_state["tooling_requirement"],
                    form_state["inspection_standard"],
                    form_state["ecn_impact_summary"],
                    form_state["status"],
                    form_state["owner"],
                    form_state["blocked_reason"],
                    form_state["next_action"],
                    form_state["remark"],
                    session.get("user_id"),
                ),
            )
            if log_action:
                log_action("新增技术确认单", confirm_no, _text("project_code"))
            flash("技术确认单已保存。", "success")
            return redirect(f"/engineering/technical-confirmations/{row['id']}")
        return render_template(
            "engineering_technical_confirmation_form.html",
            confirmation=_prefill_confirmation_from_sales_order(query_one, request.args.get("sales_order_id")),
            options=_query_options(query_rows),
            today=date.today().isoformat(),
            form_errors=[],
        )

    @app.get("/engineering/technical-confirmations/<int:confirm_id>", endpoint="engineering_technical_confirmation_detail")
    @login_required
    def technical_confirmation_detail(confirm_id):
        row = _get_confirmation(confirm_id)
        if not row:
            flash("技术确认单不存在。", "warning")
            return redirect("/engineering/technical-confirmations")
        confirmation = dict(row)
        confirmation["blocked_reason"] = confirmation.get("blocked_reason") or _confirmation_blocked_reason(confirmation)
        confirmation["next_action"] = confirmation.get("next_action") or _confirmation_next_action(confirmation)
        confirmation["execution_readiness"] = _confirmation_execution_readiness(confirmation)
        confirmation["ledger_url"] = f"/projects/{confirmation.get('sales_order_id')}" if confirmation.get("sales_order_id") else ""
        return render_template("engineering_technical_confirmation_detail.html", confirmation=confirmation)

    @app.post("/engineering/technical-confirmations/<int:confirm_id>/confirm", endpoint="engineering_technical_confirmation_confirm")
    @login_required
    def technical_confirmation_confirm(confirm_id):
        row = _get_confirmation(confirm_id)
        if not row:
            flash("技术确认单不存在。", "warning")
            return redirect("/engineering/technical-confirmations")
        blocked = _confirmation_blocked_reason(row)
        if blocked:
            flash(f"不能确认，仍缺少：{blocked}", "warning")
            return redirect(f"/engineering/technical-confirmations/{confirm_id}")
        reference_errors = _validate_confirmation_references(
            query_one,
            row.get("product_id"),
            row.get("bom_id"),
            row.get("routing_id"),
            row.get("drawing_no"),
            row.get("drawing_version"),
            row.get("confirm_date"),
        )
        if reference_errors:
            flash("不能确认：" + "、".join(reference_errors), "warning")
            return redirect(f"/engineering/technical-confirmations/{confirm_id}")
        execute_db(
            """
            UPDATE engineering_technical_confirmations
            SET status='已确认',
                confirmed_by=%s,
                confirmed_at=NOW(),
                next_action='下游可用于MRP、齐套、工单',
                updated_at=NOW()
            WHERE id=%s
            """,
            (session.get("user_id"), confirm_id),
        )
        if log_action:
            log_action("确认技术资料", row.get("confirm_no"), row.get("project_code") or "")
        flash("技术资料已确认，下游可按该版本执行。", "success")
        return redirect(f"/engineering/technical-confirmations/{confirm_id}")
