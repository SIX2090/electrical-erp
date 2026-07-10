"""BOM version routes: BOM version list, version creation, and version comparison."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from services.bom_snapshot_service import (
    compare_bom_snapshot_to_current,
    create_bom_snapshot,
    create_drawing_snapshot,
    create_process_snapshot,
    get_work_order_snapshots,
)
from services.bom_version_service import (
    approve_version,
    create_version,
    get_active_version,
    get_version,
    list_versions,
    obsolete_version,
    release_version,
    VERSION_STATUS_LABELS,
)
from services.ecn_impact_service import (
    analyze_ecn_impact,
    assign_action_task,
    generate_action_tasks,
    get_action_task,
    get_impact_results,
    get_pending_impact_tasks,
    list_action_tasks,
    resolve_impact_task,
    save_impact_results,
    update_action_task_status,
    ACTION_STATUS_LABELS,
    ACTION_TASK_LABELS,
    IMPACT_STATUS_LABELS,
    IMPACT_TYPE_LABELS,
)
from services.bom_substitute_service import (
    approve_substitute,
    create_substitute,
    delete_substitute,
    get_substitute,
    list_substitutes,
    update_substitute,
)


def _text(name: str) -> str:
    return (request.form.get(name) or "").strip()


def _arg(name: str) -> str:
    return (request.args.get(name) or "").strip()


def _int_or_none(name: str):
    value = _text(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _arg_int_or_none(name: str):
    value = _arg(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    execute_and_return = deps["execute_and_return"]
    login_required = deps["login_required"]
    log_action = deps.get("log_action")

    @app.get("/bom/versions", endpoint="bom_version_list")
    @login_required
    def bom_version_list():
        bom_id = _arg_int_or_none("bom_id")
        keyword = _arg("keyword")
        where_parts = []
        params = []
        if bom_id:
            where_parts.append("bv.bom_id=%s")
            params.append(bom_id)
        if keyword:
            where_parts.append(
                "(bv.version_no ILIKE %s OR b.bom_no ILIKE %s OR p.code ILIKE %s OR p.name ILIKE %s)"
            )
            params.extend([f"%{keyword}%"] * 4)
        where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        rows = query_db(
            f"""
            SELECT bv.*, b.bom_no, b.product_id,
                   p.code AS product_code, p.name AS product_name,
                   p.specification AS product_specification,
                   approver.username AS approver_name,
                   creator.username AS creator_name
            FROM bom_versions bv
            LEFT JOIN boms b ON b.id=bv.bom_id
            LEFT JOIN products p ON p.id=b.product_id
            LEFT JOIN users approver ON approver.id=bv.approved_by
            LEFT JOIN users creator ON creator.id=bv.created_by
            {where_sql}
            ORDER BY
                CASE bv.status
                    WHEN 'released' THEN 0
                    WHEN 'approved' THEN 1
                    WHEN 'draft' THEN 2
                    ELSE 3
                END,
                bv.effective_date DESC NULLS LAST,
                bv.id DESC
            LIMIT 200
            """,
            tuple(params),
        )
        versions = []
        for row in rows or []:
            item = dict(row)
            item["status_label"] = VERSION_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
            versions.append(item)
        return render_template(
            "bom/versions.html",
            versions=versions,
            filters={"bom_id": bom_id or "", "keyword": keyword},
        )

    @app.get("/bom/<int:bom_id>/versions", endpoint="bom_versions_by_bom")
    @login_required
    def bom_versions_by_bom(bom_id):
        versions = list_versions(query_db, bom_id)
        bom = query_db(
            """
            SELECT b.id, b.bom_no, b.version, b.status,
                   p.code AS product_code, p.name AS product_name,
                   p.specification AS product_specification
            FROM boms b
            LEFT JOIN products p ON p.id=b.product_id
            WHERE b.id=%s
            """,
            (bom_id,),
            one=True,
        )
        return render_template(
            "bom/versions.html",
            versions=versions,
            filters={"bom_id": str(bom_id), "keyword": ""},
            bom=dict(bom) if bom else None,
        )

    @app.get("/bom/versions/<int:version_id>", endpoint="bom_version_detail")
    @login_required
    def bom_version_detail(version_id):
        version = get_version(query_db, version_id)
        if not version:
            flash("未找到BOM版本。", "warning")
            return redirect(url_for("bom_version_list"))
        items = []
        bom_id = version.get("bom_id")
        if bom_id:
            rows = query_db(
                """
                SELECT bi.id AS bom_item_id, bi.product_id,
                       bi.quantity AS base_qty, bi.loss_rate, bi.unit AS material_unit,
                       bi.remark, bi.is_optional,
                       p.code AS material_code, p.name AS material_name,
                       p.specification AS material_spec, p.standard_price
                FROM bom_items bi
                LEFT JOIN products p ON p.id=bi.product_id
                WHERE bi.bom_id=%s
                ORDER BY bi.id
                """,
                (bom_id,),
            )
            items = [dict(row) for row in rows or []]
        active = get_active_version(query_db, bom_id) if bom_id else None
        version["is_active"] = bool(active and active.get("id") == version.get("id"))
        return render_template(
            "bom/version_detail.html",
            version=version,
            items=items,
        )

    @app.route("/bom/versions/new", methods=["GET", "POST"], endpoint="bom_version_new")
    @login_required
    def bom_version_new():
        if request.method == "POST":
            bom_id = _int_or_none("bom_id")
            version_no = _text("version_no")
            change_note = _text("change_note")
            if not bom_id or not version_no:
                flash("请填写BOM和版本号。", "warning")
                return redirect(url_for("bom_version_new", bom_id=bom_id or ""))
            version = create_version(
                query_db, execute_db, execute_and_return,
                bom_id=bom_id, version_no=version_no,
                change_note=change_note,
                created_by=_current_user_id(),
            )
            if not version:
                flash("版本号已存在或BOM不存在，未能创建版本。", "warning")
                return redirect(url_for("bom_version_new", bom_id=bom_id))
            if log_action:
                log_action("新增BOM版本", f"bom_id={bom_id}; version={version_no}", change_note or "")
            flash("BOM版本已创建，状态为草稿。", "success")
            return redirect(url_for("bom_version_detail", version_id=version.get("id")))
        bom_id = _arg_int_or_none("bom_id")
        bom = None
        if bom_id:
            row = query_db(
                """
                SELECT b.id, b.bom_no, b.version, b.status,
                       p.code AS product_code, p.name AS product_name,
                       p.specification AS product_specification
                FROM boms b
                LEFT JOIN products p ON p.id=b.product_id
                WHERE b.id=%s
                """,
                (bom_id,),
                one=True,
            )
            bom = dict(row) if row else None
        bom_options = query_db(
            """
            SELECT b.id, b.bom_no, b.version, b.status,
                   p.code AS product_code, p.name AS product_name
            FROM boms b
            LEFT JOIN products p ON p.id=b.product_id
            ORDER BY b.id DESC
            LIMIT 300
            """
        )
        return render_template(
            "bom/version_form.html",
            bom=bom,
            bom_options=[dict(r) for r in bom_options or []],
            form_state={"bom_id": bom_id or "", "version_no": "", "change_note": ""},
            mode="new",
        )

    @app.post("/bom/versions/<int:version_id>/approve", endpoint="bom_version_approve")
    @login_required
    def bom_version_approve(version_id):
        ok = approve_version(query_db, execute_db, version_id, _current_user_id())
        if ok:
            if log_action:
                log_action("审核BOM版本", f"version_id={version_id}", "approved")
            flash("BOM版本已审核。", "success")
        else:
            flash("只有草稿状态的版本可以审核。", "warning")
        return redirect(url_for("bom_version_detail", version_id=version_id))

    @app.post("/bom/versions/<int:version_id>/release", endpoint="bom_version_release")
    @login_required
    def bom_version_release(version_id):
        ok = release_version(query_db, execute_db, version_id)
        if ok:
            if log_action:
                log_action("发布BOM版本", f"version_id={version_id}", "released")
            flash("BOM版本已发布，原已发布版本已作废。", "success")
        else:
            flash("只有草稿或已审核的版本可以发布。", "warning")
        return redirect(url_for("bom_version_detail", version_id=version_id))

    @app.post("/bom/versions/<int:version_id>/obsolete", endpoint="bom_version_obsolete")
    @login_required
    def bom_version_obsolete(version_id):
        ok = obsolete_version(query_db, execute_db, version_id)
        if ok:
            if log_action:
                log_action("作废BOM版本", f"version_id={version_id}", "obsoleted")
            flash("BOM版本已作废。", "success")
        else:
            flash("未找到BOM版本。", "warning")
        return redirect(url_for("bom_version_detail", version_id=version_id))

    @app.get("/work-orders/<int:work_order_id>/snapshots", endpoint="work_order_snapshots")
    @login_required
    def work_order_snapshots(work_order_id):
        data = get_work_order_snapshots(query_db, work_order_id)
        comparison = compare_bom_snapshot_to_current(query_db, work_order_id)
        return render_template(
            "bom/work_order_snapshots.html",
            work_order=data.get("work_order"),
            bom_snapshots=data.get("bom_snapshots") or [],
            process_snapshots=data.get("process_snapshots") or [],
            drawing_snapshots=data.get("drawing_snapshots") or [],
            comparison=comparison,
        )

    @app.get("/ecn/<int:ecn_id>/impact", endpoint="ecn_impact_view")
    @login_required
    def ecn_impact_view(ecn_id):
        ecn = query_db(
            """
            SELECT ec.*, src.bom_no AS source_bom_no, src.version AS source_bom_version,
                   tgt.bom_no AS target_bom_no, tgt.version AS target_bom_version
            FROM bom_engineering_changes ec
            LEFT JOIN boms src ON src.id=ec.source_bom_id
            LEFT JOIN boms tgt ON tgt.id=ec.target_bom_id
            WHERE ec.id=%s
            """,
            (ecn_id,),
            one=True,
        )
        results = get_impact_results(query_db, ecn_id)
        return render_template(
            "engineering/ecn_impact.html",
            ecn=dict(ecn) if ecn else None,
            results=results,
            type_labels=IMPACT_TYPE_LABELS,
            status_labels=IMPACT_STATUS_LABELS,
        )

    @app.post("/ecn/<int:ecn_id>/impact/analyze", endpoint="ecn_impact_analyze")
    @login_required
    def ecn_impact_analyze(ecn_id):
        product_id = _arg_int_or_none("product_id")
        bom_id = _arg_int_or_none("bom_id")
        project_code = _arg("project_code")
        cabinet_no = _arg("cabinet_no")
        results = analyze_ecn_impact(
            query_db, ecn_id,
            product_id=product_id, bom_id=bom_id,
            project_code=project_code, cabinet_no=cabinet_no,
        )
        saved = save_impact_results(query_db, execute_db, ecn_id, results)
        if log_action:
            log_action("执行ECN影响分析", f"ecn_id={ecn_id}", f"saved={saved}")
        flash(f"ECN影响分析完成，共保存 {saved} 条影响结果。", "success")
        return redirect(url_for("ecn_impact_view", ecn_id=ecn_id))

    @app.post("/ecn/impact-tasks/<int:task_id>/resolve", endpoint="ecn_impact_task_resolve")
    @login_required
    def ecn_impact_task_resolve(task_id):
        action_taken = _text("action_taken")
        ok = resolve_impact_task(execute_db, task_id, action_taken)
        if ok:
            if log_action:
                log_action("处理ECN影响任务", f"task_id={task_id}", action_taken or "")
            flash("ECN影响任务已标记为已处理。", "success")
        else:
            flash("未找到待处理的ECN影响任务。", "warning")
        next_url = request.form.get("next") or url_for("ecn_impact_tasks")
        return redirect(next_url)

    @app.get("/ecn/impact-tasks", endpoint="ecn_impact_tasks")
    @login_required
    def ecn_impact_tasks():
        tasks = get_pending_impact_tasks(query_db)
        return render_template(
            "engineering/ecn_impact_tasks.html",
            tasks=tasks,
            type_labels=IMPACT_TYPE_LABELS,
            status_labels=IMPACT_STATUS_LABELS,
        )

    def _current_user_id():
        try:
            from flask import session
            return session.get("user_id")
        except Exception:
            return None

    # ===== BOM 替代料管理 =====

    @app.get("/bom/items/<int:bom_item_id>/substitutes", endpoint="bom_substitute_list")
    @login_required
    def bom_substitute_list(bom_item_id):
        bom_item = query_db(
            """
            SELECT bi.id, bi.bom_id, bi.product_id, bi.quantity, bi.loss_rate,
                   p.code AS product_code, p.name AS product_name,
                   p.specification AS product_spec, p.unit AS product_unit,
                   b.bom_no, b.version AS bom_version
            FROM bom_items bi
            LEFT JOIN products p ON p.id=bi.product_id
            LEFT JOIN boms b ON b.id=bi.bom_id
            WHERE bi.id=%s
            """,
            (bom_item_id,),
            one=True,
        ) or {}
        substitutes = list_substitutes(query_db, bom_item_id)
        products = query_db(
            """
            SELECT id, code, name, specification, unit
            FROM products
            WHERE COALESCE(status, '') NOT IN ('disabled','inactive','停用','禁用')
            ORDER BY code
            LIMIT 500
            """,
        ) or []
        return render_template(
            "bom/substitute_list.html",
            bom_item=bom_item,
            substitutes=substitutes,
            products=products,
        )

    @app.post("/bom/items/<int:bom_item_id>/substitutes/new", endpoint="bom_substitute_new")
    @login_required
    def bom_substitute_new(bom_item_id):
        substitute_product_id = _int_or_none("substitute_product_id")
        if not substitute_product_id:
            flash("请选择替代物料。", "warning")
            return redirect(url_for("bom_substitute_list", bom_item_id=bom_item_id))
        priority = int(_text("priority") or "1")
        ratio = float(_text("ratio") or "1")
        allow_auto = _text("allow_auto_substitute") in ("1", "true", "on", "yes")
        approval_status = _text("approval_status") or "approved"
        remark = _text("remark")
        create_substitute(
            execute_db,
            bom_item_id=bom_item_id,
            substitute_product_id=substitute_product_id,
            priority=priority,
            ratio=ratio,
            allow_auto_substitute=allow_auto,
            approval_status=approval_status,
            remark=remark,
            created_by=_current_user_id(),
        )
        if log_action:
            log_action("新增BOM替代料", f"bom_item={bom_item_id} substitute={substitute_product_id}")
        flash("替代料已新增。", "success")
        return redirect(url_for("bom_substitute_list", bom_item_id=bom_item_id))

    @app.post("/bom/substitutes/<int:substitute_id>/edit", endpoint="bom_substitute_edit")
    @login_required
    def bom_substitute_edit(substitute_id):
        sub = get_substitute(query_db, substitute_id)
        if not sub:
            flash("替代料不存在。", "warning")
            return redirect(url_for("bom_version_list"))
        fields = {}
        priority = _text("priority")
        if priority:
            fields["priority"] = int(priority)
        ratio = _text("ratio")
        if ratio:
            fields["ratio"] = float(ratio)
        fields["allow_auto_substitute"] = _text("allow_auto_substitute") in ("1", "true", "on", "yes")
        remark = _text("remark")
        if remark is not None:
            fields["remark"] = remark
        update_substitute(execute_db, substitute_id, **fields)
        if log_action:
            log_action("更新BOM替代料", f"substitute={substitute_id}")
        flash("替代料已更新。", "success")
        return redirect(url_for("bom_substitute_list", bom_item_id=sub.get("bom_item_id")))

    @app.post("/bom/substitutes/<int:substitute_id>/approve", endpoint="bom_substitute_approve")
    @login_required
    def bom_substitute_approve(substitute_id):
        sub = get_substitute(query_db, substitute_id)
        if not sub:
            flash("替代料不存在。", "warning")
            return redirect(url_for("bom_version_list"))
        approve_substitute(execute_db, substitute_id, _current_user_id() or 0)
        if log_action:
            log_action("审批BOM替代料", f"substitute={substitute_id}")
        flash("替代料已审批。", "success")
        return redirect(url_for("bom_substitute_list", bom_item_id=sub.get("bom_item_id")))

    @app.post("/bom/substitutes/<int:substitute_id>/delete", endpoint="bom_substitute_delete")
    @login_required
    def bom_substitute_delete(substitute_id):
        sub = get_substitute(query_db, substitute_id)
        if not sub:
            flash("替代料不存在。", "warning")
            return redirect(url_for("bom_version_list"))
        bom_item_id = sub.get("bom_item_id")
        delete_substitute(execute_db, substitute_id)
        if log_action:
            log_action("删除BOM替代料", f"substitute={substitute_id}")
        flash("替代料已删除。", "success")
        return redirect(url_for("bom_substitute_list", bom_item_id=bom_item_id))

    # ===== ECN 变更执行控制 =====

    @app.get("/ecn/action-tasks", endpoint="ecn_action_tasks")
    @login_required
    def ecn_action_tasks():
        status = _arg("status")
        tasks = list_action_tasks(query_db, status=status or None)
        return render_template(
            "engineering/ecn_action_tasks.html",
            tasks=tasks,
            status_labels=ACTION_STATUS_LABELS,
            type_labels=ACTION_TASK_LABELS,
            current_status=status,
        )

    @app.get("/ecn/<int:ecn_id>/action-tasks", endpoint="ecn_action_tasks_by_ecn")
    @login_required
    def ecn_action_tasks_by_ecn(ecn_id):
        tasks = list_action_tasks(query_db, ecn_id=ecn_id)
        return render_template(
            "engineering/ecn_action_tasks.html",
            tasks=tasks,
            status_labels=ACTION_STATUS_LABELS,
            type_labels=ACTION_TASK_LABELS,
            ecn_id=ecn_id,
        )

    @app.post("/ecn/<int:ecn_id>/action-tasks/generate", endpoint="ecn_action_tasks_generate")
    @login_required
    def ecn_action_tasks_generate(ecn_id):
        count = generate_action_tasks(query_db, execute_db, ecn_id)
        if log_action:
            log_action("生成ECN执行任务", f"ecn={ecn_id} count={count}")
        flash(f"已生成 {count} 条变更执行任务。", "success")
        return redirect(url_for("ecn_action_tasks_by_ecn", ecn_id=ecn_id))

    @app.post("/ecn/action-tasks/<int:task_id>/status", endpoint="ecn_action_task_status")
    @login_required
    def ecn_action_task_status(task_id):
        task = get_action_task(query_db, task_id)
        if not task:
            flash("执行任务不存在。", "warning")
            return redirect(url_for("ecn_action_tasks"))
        status = _text("status") or "pending"
        remark = _text("remark")
        update_action_task_status(
            execute_db, task_id, status,
            resolved_by=_current_user_id(),
            remark=remark,
        )
        if log_action:
            log_action("更新ECN执行任务状态", f"task={task_id} status={status}")
        flash("执行任务状态已更新。", "success")
        return redirect(url_for("ecn_action_tasks"))
