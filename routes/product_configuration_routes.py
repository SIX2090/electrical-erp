"""Product configuration routes: product family, model, and configuration management."""
from datetime import date

from flask import flash, redirect, render_template, request, session

from services.transaction_utils import cursor_db_helpers


CONFIG_STATUSES = {
    "draft": "草稿",
    "submitted": "待工程确认",
    "engineering_confirmed": "工程已确认",
    "bom_linked": "已链接项目BOM",
    "voided": "已作废",
}

OPTION_TYPES = {
    "required": "必选",
    "optional": "可选",
    "mutually_exclusive": "互斥",
    "reference": "参考",
}

BOM_ITEM_ACTIONS = {
    "add": "新增BOM项",
    "replace": "替换BOM项",
    "remove": "移除BOM项",
    "reference": "仅作参考",
}


def _text(name, default=""):
    return (request.form.get(name) or default or "").strip()


def _int_or_none(name):
    value = _text(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _decimal_text(value, default="0"):
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        return str(float(raw))
    except ValueError:
        return default


def _option_rows_from_form():
    groups = request.form.getlist("option_group[]")
    rows = []
    selected_lines = set(request.form.getlist("selected_line[]"))
    required_lines = set(request.form.getlist("required_line[]"))
    for idx, group in enumerate(groups, start=1):
        option_name = (request.form.getlist("option_name[]")[idx - 1] if idx <= len(request.form.getlist("option_name[]")) else "").strip()
        option_code = (request.form.getlist("option_code[]")[idx - 1] if idx <= len(request.form.getlist("option_code[]")) else "").strip()
        material_id_raw = request.form.getlist("material_id[]")[idx - 1] if idx <= len(request.form.getlist("material_id[]")) else ""
        if not group.strip() and not option_name and not option_code and not material_id_raw:
            continue
        option_types = request.form.getlist("option_type[]")
        bom_actions = request.form.getlist("bom_item_action[]")
        quantities = request.form.getlist("quantity[]")
        units = request.form.getlist("unit[]")
        costs = request.form.getlist("estimated_cost[]")
        lead_times = request.form.getlist("lead_time_days[]")
        owners = request.form.getlist("item_owner[]")
        blocked = request.form.getlist("item_blocked_reason[]")
        next_actions = request.form.getlist("item_next_action[]")
        impacts = request.form.getlist("item_downstream_impact[]")
        remarks = request.form.getlist("item_remark[]")
        conflict_groups = request.form.getlist("conflict_group[]")
        rows.append(
            {
                "line_no": idx,
                "option_group": group.strip(),
                "option_code": option_code,
                "option_name": option_name,
                "option_type": option_types[idx - 1] if idx <= len(option_types) and option_types[idx - 1] in OPTION_TYPES else "optional",
                "selected": str(idx) in selected_lines,
                "required_flag": str(idx) in required_lines,
                "conflict_group": conflict_groups[idx - 1].strip() if idx <= len(conflict_groups) else "",
                "material_id": int(material_id_raw) if str(material_id_raw).isdigit() else None,
                "bom_item_action": bom_actions[idx - 1] if idx <= len(bom_actions) and bom_actions[idx - 1] in BOM_ITEM_ACTIONS else "reference",
                "quantity": _decimal_text(quantities[idx - 1] if idx <= len(quantities) else "1", "1"),
                "unit": units[idx - 1].strip() if idx <= len(units) else "",
                "estimated_cost": _decimal_text(costs[idx - 1] if idx <= len(costs) else "0", "0"),
                "lead_time_days": int(lead_times[idx - 1]) if idx <= len(lead_times) and str(lead_times[idx - 1]).isdigit() else 0,
                "owner": owners[idx - 1].strip() if idx <= len(owners) else "",
                "blocked_reason": blocked[idx - 1].strip() if idx <= len(blocked) else "",
                "next_action": next_actions[idx - 1].strip() if idx <= len(next_actions) else "",
                "downstream_impact": impacts[idx - 1].strip() if idx <= len(impacts) else "",
                "remark": remarks[idx - 1].strip() if idx <= len(remarks) else "",
            }
        )
    return rows


def _validate_configuration(row, items):
    blockers = []
    if not row.get("product_id") and not row.get("machine_model"):
        blockers.append("缺少产品或机型")
    required_missing = [
        item.get("option_name") or item.get("option_code") or f"第{item.get('line_no')}行"
        for item in items
        if item.get("required_flag") and not item.get("selected")
    ]
    if required_missing:
        blockers.append("必选项未选择：" + "、".join(required_missing[:3]))
    conflict_selected = {}
    for item in items:
        group = (item.get("conflict_group") or "").strip()
        if not group or not item.get("selected"):
            continue
        conflict_selected.setdefault(group, []).append(item.get("option_name") or item.get("option_code") or str(item.get("line_no")))
    conflicts = [f"{group}({len(values)}项)" for group, values in conflict_selected.items() if len(values) > 1]
    if conflicts:
        blockers.append("互斥项冲突：" + "、".join(conflicts[:3]))
    line_blockers = [
        item.get("blocked_reason")
        for item in items
        if item.get("selected") and item.get("blocked_reason")
    ]
    if line_blockers:
        blockers.append("选项未关闭问题：" + "、".join(line_blockers[:2]))
    return "；".join(blockers)


def _next_action_for(row, blocked_reason=""):
    status = row.get("status") or "draft"
    if status == "draft":
        return "补齐选项并提交工程确认"
    if status == "submitted":
        return "工程确认选配结果"
    if status == "engineering_confirmed":
        return "链接项目BOM或技术确认单"
    if status == "bom_linked":
        return "下游按项目BOM进入MRP、齐套和工单准备"
    if status == "voided":
        return "已作废，不再下推"
    return "处理选配单阻塞项" if blocked_reason else "提交工程确认"


def _downstream_impact(row):
    return row.get("downstream_impact") or "影响项目BOM、工艺准备、MRP齐套、采购委外需求、项目柜号成本测算；本页不直接生成采购、生产、库存或财务单据。"


def _form_state(default_status="draft"):
    return {
        "config_date": _text("config_date") or date.today().isoformat(),
        "sales_order_id": _int_or_none("sales_order_id"),
        "quotation_id": _int_or_none("quotation_id"),
        "customer_id": _int_or_none("customer_id"),
        "product_id": _int_or_none("product_id"),
        "base_bom_id": _int_or_none("base_bom_id"),
        "project_bom_id": _int_or_none("project_bom_id"),
        "project_code": _text("project_code"),
        "cabinet_no": _text("cabinet_no"),
        "product_family": _text("product_family"),
        "machine_model": _text("machine_model"),
        "status": _text("status") or default_status,
        "owner": _text("owner"),
        "engineering_owner": _text("engineering_owner"),
        "blocked_reason": _text("blocked_reason"),
        "next_action": _text("next_action"),
        "downstream_impact": _text("downstream_impact"),
        "remark": _text("remark"),
    }


def register_product_configuration_routes(
    app,
    login_required,
    query_rows,
    query_one,
    execute_db,
    execute_and_return,
    next_doc_no,
    log_action=None,
):
    def _options():
        return {
            "customers": query_rows("SELECT id, name FROM customers ORDER BY name LIMIT 500"),
            "products": query_rows("SELECT id, code, name, specification, unit, category, category AS product_family FROM products ORDER BY code LIMIT 800"),
            "sales_orders": query_rows(
                """
                SELECT so.id, so.order_no, so.project_code, so.cabinet_no, so.customer_id,
                       c.name AS customer_name, soi.product_id,
                       p.code AS product_code, p.name AS product_name, p.specification AS product_specification,
                       p.category AS product_family
                FROM sales_orders so
                LEFT JOIN customers c ON c.id=so.customer_id
                LEFT JOIN LATERAL (
                    SELECT product_id
                    FROM sales_order_items
                    WHERE order_id=so.id
                    ORDER BY id
                    LIMIT 1
                ) soi ON TRUE
                LEFT JOIN products p ON p.id=soi.product_id
                ORDER BY so.id DESC
                LIMIT 300
                """
            ),
            "quotations": query_rows(
                """
                SELECT q.id, q.quote_no, q.project_code, q.cabinet_no, q.customer_id, c.name AS customer_name
                FROM quotation_headers q
                LEFT JOIN customers c ON c.id=q.customer_id
                ORDER BY q.id DESC
                LIMIT 300
                """
            ),
            "boms": query_rows(
                """
                SELECT b.id, b.bom_no, b.version, b.status, b.product_id,
                       p.code AS product_code, p.name AS product_name, p.specification AS product_specification
                FROM boms b
                LEFT JOIN products p ON p.id=b.product_id
                ORDER BY b.id DESC
                LIMIT 800
                """
            ),
            "materials": query_rows("SELECT id, code, name, specification, unit FROM products ORDER BY code LIMIT 1000"),
        }

    def _get_configuration(config_id):
        return query_one(
            """
            SELECT pc.*,
                   so.order_no AS sales_order_no,
                   q.quote_no AS quotation_no,
                   c.name AS customer_name,
                   p.code AS product_code, p.name AS product_name, p.specification AS product_specification,
                   bb.bom_no AS base_bom_no, bb.version AS base_bom_version,
                   pb.bom_no AS project_bom_no, pb.version AS project_bom_version,
                   u.username AS engineering_confirmed_by_name
            FROM product_configurations pc
            LEFT JOIN sales_orders so ON so.id=pc.sales_order_id
            LEFT JOIN quotation_headers q ON q.id=pc.quotation_id
            LEFT JOIN customers c ON c.id=pc.customer_id
            LEFT JOIN products p ON p.id=pc.product_id
            LEFT JOIN boms bb ON bb.id=pc.base_bom_id
            LEFT JOIN boms pb ON pb.id=pc.project_bom_id
            LEFT JOIN users u ON u.id=pc.engineering_confirmed_by
            WHERE pc.id=%s
            """,
            (config_id,),
        )

    def _get_items(config_id):
        return query_rows(
            """
            SELECT pci.*, p.code AS material_code, p.name AS material_name, p.specification AS material_specification
            FROM product_configuration_items pci
            LEFT JOIN products p ON p.id=pci.material_id
            WHERE pci.configuration_id=%s
            ORDER BY pci.line_no, pci.id
            """,
            (config_id,),
        )

    def _insert_items(config_id, items, execute_db_fn=None):
        exec_db = execute_db_fn or execute_db
        exec_db("DELETE FROM product_configuration_items WHERE configuration_id=%s", (config_id,))
        for item in items:
            exec_db(
                """
                INSERT INTO product_configuration_items
                    (configuration_id, line_no, option_group, option_code, option_name, option_type,
                     selected, required_flag, conflict_group, material_id, bom_item_action,
                     quantity, unit, estimated_cost, lead_time_days, owner, blocked_reason,
                     next_action, downstream_impact, remark)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    config_id,
                    item["line_no"],
                    item["option_group"],
                    item["option_code"],
                    item["option_name"],
                    item["option_type"],
                    item["selected"],
                    item["required_flag"],
                    item["conflict_group"],
                    item["material_id"],
                    item["bom_item_action"],
                    item["quantity"],
                    item["unit"],
                    item["estimated_cost"],
                    item["lead_time_days"],
                    item["owner"],
                    item["blocked_reason"],
                    item["next_action"],
                    item["downstream_impact"],
                    item["remark"],
                ),
            )

    @app.get("/product-configurations", endpoint="product_configuration_list")
    @login_required
    def product_configuration_list():
        keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
        status = (request.args.get("status") or "").strip()
        where = []
        params = []
        if keyword:
            where.append(
                """
                (
                    pc.config_no ILIKE %s OR so.order_no ILIKE %s OR q.quote_no ILIKE %s
                    OR c.name ILIKE %s OR p.code ILIKE %s OR p.name ILIKE %s
                    OR pc.project_code ILIKE %s OR pc.cabinet_no ILIKE %s OR pc.machine_model ILIKE %s
                    OR pc.owner ILIKE %s OR pc.engineering_owner ILIKE %s
                )
                """
            )
            params.extend([f"%{keyword}%"] * 11)
        if status:
            where.append("pc.status=%s")
            params.append(status)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = query_rows(
            f"""
            SELECT pc.id, pc.config_no, pc.config_date, pc.status, pc.project_code, pc.cabinet_no,
                   pc.machine_model, pc.owner, pc.engineering_owner, pc.blocked_reason,
                   pc.next_action, pc.downstream_impact, pc.project_bom_id,
                   so.order_no AS sales_order_no, q.quote_no AS quotation_no,
                   c.name AS customer_name,
                   p.code AS product_code, p.name AS product_name,
                   bb.bom_no AS base_bom_no, bb.version AS base_bom_version,
                   pb.bom_no AS project_bom_no, pb.version AS project_bom_version,
                   COALESCE(item_summary.item_count, 0) AS item_count,
                   COALESCE(item_summary.selected_count, 0) AS selected_count,
                   COALESCE(item_summary.required_missing_count, 0) AS required_missing_count,
                   COALESCE(item_summary.open_blocker_count, 0) AS open_blocker_count
            FROM product_configurations pc
            LEFT JOIN sales_orders so ON so.id=pc.sales_order_id
            LEFT JOIN quotation_headers q ON q.id=pc.quotation_id
            LEFT JOIN customers c ON c.id=pc.customer_id
            LEFT JOIN products p ON p.id=pc.product_id
            LEFT JOIN boms bb ON bb.id=pc.base_bom_id
            LEFT JOIN boms pb ON pb.id=pc.project_bom_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS item_count,
                       COUNT(*) FILTER (WHERE selected) AS selected_count,
                       COUNT(*) FILTER (WHERE required_flag AND NOT selected) AS required_missing_count,
                       COUNT(*) FILTER (WHERE selected AND COALESCE(blocked_reason, '') <> '') AS open_blocker_count
                FROM product_configuration_items pci
                WHERE pci.configuration_id=pc.id
            ) item_summary ON TRUE
            {where_sql}
            ORDER BY
                CASE pc.status
                    WHEN 'submitted' THEN 0
                    WHEN 'draft' THEN 1
                    WHEN 'engineering_confirmed' THEN 2
                    WHEN 'bom_linked' THEN 3
                    ELSE 4
                END,
                pc.id DESC
            LIMIT 300
            """,
            tuple(params),
        )
        enhanced = []
        for row in rows:
            item = dict(row)
            item["status_label"] = CONFIG_STATUSES.get(item.get("status"), item.get("status") or "-")
            item["next_action"] = item.get("next_action") or _next_action_for(item)
            item["downstream_impact"] = _downstream_impact(item)
            item["base_bom_display"] = " / ".join(part for part in [item.get("base_bom_no"), item.get("base_bom_version")] if part)
            item["project_bom_display"] = " / ".join(part for part in [item.get("project_bom_no"), item.get("project_bom_version")] if part)
            enhanced.append(item)
        return render_template(
            "product_configuration_list.html",
            rows=enhanced,
            statuses=CONFIG_STATUSES,
        )

    @app.route("/product-configurations/new", methods=["GET", "POST"], endpoint="product_configuration_new")
    @login_required
    def product_configuration_new():
        form_errors = []
        config = _form_state()
        items = _option_rows_from_form() if request.method == "POST" else []
        if request.method == "POST":
            blocked = _validate_configuration(config, items)
            config["blocked_reason"] = config["blocked_reason"] or blocked
            config["next_action"] = config["next_action"] or _next_action_for(config, blocked)
            config["downstream_impact"] = _downstream_impact(config)
            if not items:
                form_errors.append("至少维护一组选配明细。")
            if form_errors:
                return (
                    render_template(
                        "product_configuration_form.html",
                        config=config,
                        items=items,
                        options=_options(),
                        statuses=CONFIG_STATUSES,
                        option_types=OPTION_TYPES,
                        bom_item_actions=BOM_ITEM_ACTIONS,
                        today=date.today().isoformat(),
                        form_errors=form_errors,
                    ),
                    400,
                )
            config_no = next_doc_no("PC", "product_configurations", "config_no")
            def operation(cursor=None):
                if cursor is None:
                    exec_db = execute_db
                    exec_return = execute_and_return
                else:
                    _tx_query, exec_db, exec_return = cursor_db_helpers(cursor)
                row = exec_return(
                    """
                    INSERT INTO product_configurations
                        (config_no, config_date, sales_order_id, quotation_id, customer_id, product_id,
                         base_bom_id, project_bom_id, project_code, cabinet_no, product_family, machine_model,
                         status, owner, engineering_owner, blocked_reason, next_action, downstream_impact,
                         remark, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        config_no,
                        config["config_date"],
                        config["sales_order_id"],
                        config["quotation_id"],
                        config["customer_id"],
                        config["product_id"],
                        config["base_bom_id"],
                        config["project_bom_id"],
                        config["project_code"],
                        config["cabinet_no"],
                        config["product_family"],
                        config["machine_model"],
                        "draft",
                        config["owner"],
                        config["engineering_owner"],
                        config["blocked_reason"],
                        config["next_action"],
                        config["downstream_impact"],
                        config["remark"],
                        session.get("user_id"),
                    ),
                )
                _insert_items(row["id"], items, exec_db)
                return row

            runner = app.extensions.get("run_in_transaction")
            row = runner(operation) if runner else operation()
            if log_action:
                log_action("新增产品选配单", config_no, config["project_code"])
            flash("产品选配单已保存。", "success")
            return redirect(f"/product-configurations/{row['id']}")
        return render_template(
            "product_configuration_form.html",
            config=config,
            items=[],
            options=_options(),
            statuses=CONFIG_STATUSES,
            option_types=OPTION_TYPES,
            bom_item_actions=BOM_ITEM_ACTIONS,
            today=date.today().isoformat(),
            form_errors=[],
        )

    @app.get("/product-configurations/<int:config_id>", endpoint="product_configuration_detail")
    @login_required
    def product_configuration_detail(config_id):
        row = _get_configuration(config_id)
        if not row:
            flash("产品选配单不存在。", "warning")
            return redirect("/product-configurations")
        config = dict(row)
        items = [dict(item) for item in _get_items(config_id)]
        blocked = _validate_configuration(config, items)
        config["status_label"] = CONFIG_STATUSES.get(config.get("status"), config.get("status") or "-")
        config["blocked_reason"] = config.get("blocked_reason") or blocked
        config["next_action"] = config.get("next_action") or _next_action_for(config, blocked)
        config["downstream_impact"] = _downstream_impact(config)
        config["base_bom_display"] = " / ".join(part for part in [config.get("base_bom_no"), config.get("base_bom_version")] if part)
        config["project_bom_display"] = " / ".join(part for part in [config.get("project_bom_no"), config.get("project_bom_version")] if part)
        return render_template(
            "product_configuration_detail.html",
            config=config,
            items=items,
            statuses=CONFIG_STATUSES,
            option_types=OPTION_TYPES,
            bom_item_actions=BOM_ITEM_ACTIONS,
            boms=_options()["boms"],
            validation_blocked=blocked,
        )

    @app.post("/product-configurations/<int:config_id>/submit", endpoint="product_configuration_submit")
    @login_required
    def product_configuration_submit(config_id):
        row = _get_configuration(config_id)
        if not row:
            flash("产品选配单不存在。", "warning")
            return redirect("/product-configurations")
        if row.get("status") != "draft":
            flash("只有草稿产品选配单可以提交。", "warning")
            return redirect(f"/product-configurations/{config_id}")
        items = [dict(item) for item in _get_items(config_id)]
        blocked = _validate_configuration(row, items)
        execute_db(
            """
            UPDATE product_configurations
            SET status='submitted', blocked_reason=%s, next_action=%s, downstream_impact=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (blocked, "工程确认选配结果" if not blocked else "处理选配单阻塞项", _downstream_impact(row), config_id),
        )
        flash("产品选配单已提交工程确认。", "success" if not blocked else "warning")
        return redirect(f"/product-configurations/{config_id}")

    @app.post("/product-configurations/<int:config_id>/engineering-confirm", endpoint="product_configuration_engineering_confirm")
    @login_required
    def product_configuration_engineering_confirm(config_id):
        row = _get_configuration(config_id)
        if not row:
            flash("产品选配单不存在。", "warning")
            return redirect("/product-configurations")
        if row.get("status") not in {"submitted", "draft"}:
            flash("当前状态不能执行工程确认。", "warning")
            return redirect(f"/product-configurations/{config_id}")
        items = [dict(item) for item in _get_items(config_id)]
        blocked = _validate_configuration(row, items)
        if blocked:
            execute_db(
                """
                UPDATE product_configurations
                SET blocked_reason=%s, next_action='处理选配单阻塞项', updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
                """,
                (blocked, config_id),
            )
            flash(f"不能工程确认：{blocked}", "warning")
            return redirect(f"/product-configurations/{config_id}")
        execute_db(
            """
            UPDATE product_configurations
            SET status='engineering_confirmed', blocked_reason='', next_action='链接项目BOM或技术确认单',
                downstream_impact=%s, engineering_confirmed_by=%s, engineering_confirmed_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (_downstream_impact(row), session.get("user_id"), config_id),
        )
        if log_action:
            log_action("工程确认产品选配单", row.get("config_no"), row.get("project_code"))
        flash("产品选配单已工程确认。", "success")
        return redirect(f"/product-configurations/{config_id}")

    @app.post("/product-configurations/<int:config_id>/link-bom", endpoint="product_configuration_link_bom")
    @login_required
    def product_configuration_link_bom(config_id):
        row = _get_configuration(config_id)
        if not row:
            flash("产品选配单不存在。", "warning")
            return redirect("/product-configurations")
        if row.get("status") != "engineering_confirmed":
            flash("只有工程已确认的产品选配单可以链接项目BOM。", "warning")
            return redirect(f"/product-configurations/{config_id}")
        project_bom_id = _int_or_none("project_bom_id")
        bom = query_one("SELECT id, product_id FROM boms WHERE id=%s", (project_bom_id,)) if project_bom_id else None
        if not bom:
            flash("请选择有效的项目BOM。", "warning")
            return redirect(f"/product-configurations/{config_id}#linkBom")
        if row.get("product_id") and bom.get("product_id") and int(row.get("product_id")) != int(bom.get("product_id")):
            flash("项目BOM所属产品与选配单产品不一致。", "warning")
            return redirect(f"/product-configurations/{config_id}#linkBom")
        execute_db(
            """
            UPDATE product_configurations
            SET project_bom_id=%s, status='bom_linked', blocked_reason='',
                next_action='下游按项目BOM进入MRP、齐套和工单准备',
                downstream_impact=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (project_bom_id, _downstream_impact(row), config_id),
        )
        flash("产品选配单已链接项目BOM。", "success")
        return redirect(f"/product-configurations/{config_id}")

    @app.post("/product-configurations/<int:config_id>/void", endpoint="product_configuration_void")
    @login_required
    def product_configuration_void(config_id):
        row = _get_configuration(config_id)
        if not row:
            flash("产品选配单不存在。", "warning")
            return redirect("/product-configurations")
        if row.get("status") == "bom_linked":
            flash("已链接项目BOM的选配单不能直接作废，请先评估BOM影响。", "warning")
            return redirect(f"/product-configurations/{config_id}")
        reason = _text("void_reason") or "人工作废"
        execute_db(
            """
            UPDATE product_configurations
            SET status='voided', blocked_reason=%s, next_action='已作废，不再下推', updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (reason, config_id),
        )
        flash("产品选配单已作废。", "success")
        return redirect(f"/product-configurations/{config_id}")
