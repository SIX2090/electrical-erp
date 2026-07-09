"""App shell routes: login, logout, home page, and navigation shell."""
from datetime import date, datetime, timedelta

from flask import Response, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps.get("execute_db")
    login_required = deps["login_required"]
    pilot_allowed_paths_for_role = deps.get("pilot_allowed_paths_for_role")
    path_matches = deps.get("path_matches")
    login_attempt_tracker = deps["login_attempt_tracker"]
    login_rate_limiter = deps["login_rate_limiter"]

    @app.get("/")
    @login_required
    def index():
        data_source_errors = []
        failed_home_metrics = set()
        role = session.get("role") or "staff"
        allowed_paths = pilot_allowed_paths_for_role(role) if pilot_allowed_paths_for_role else set()

        def can_path(path):
            if not pilot_allowed_paths_for_role or not path_matches:
                return True
            return path_matches(path, allowed_paths)

        def can_any_path(*paths):
            return any(can_path(path) for path in paths)

        home_permissions = {
            "can_path": can_path,
            "can_projects": can_path("/projects"),
            "can_pending_documents": can_path("/pending-documents"),
            "can_reports": can_path("/reports"),
            "can_sales": can_any_path("/sales-orders", "/sales/new", "/shipments", "/shipments/new"),
            "can_purchase": can_any_path("/purchase-orders", "/purchase_receipts", "/subcontract", "/subcontract_issue"),
            "can_purchase_entry": can_any_path("/purchase_order/new", "/subcontract/new"),
            "can_inventory": can_any_path("/inventory/detail", "/transfers", "/transfers/new"),
            "can_production": can_any_path("/work-orders", "/work-orders/new"),
            "can_tech_or_production": can_any_path("/production-enhance/mrp-requirements", "/engineering/kitting", "/bom"),
            "can_finance": role in {"admin", "manager", "finance"} and can_any_path("/receivables", "/payables", "/finance"),
            "can_service": can_any_path("/service-orders", "/service-cards"),
            "can_master": can_any_path("/project-master", "/material", "/supplier"),
        }
        closed_statuses = (
            "已关闭",
            "已作废",
            "已完成",
            "已取消",
            "closed",
            "completed",
            "void",
            "voided",
            "cancelled",
            "canceled",
        )
        work_order_closed_statuses = closed_statuses + ("已完工",)

        stats = {}
        for key, table in {
            "materials": "products",
            "customers": "customers",
            "suppliers": "suppliers",
            "sales": "sales_orders",
            "work_orders": "work_orders",
            "boms": "boms",
        }.items():
            try:
                stats[key] = query_db(f"SELECT COUNT(*) AS count FROM {table}", one=True)["count"]
            except Exception as exc:
                app.logger.exception("homepage stat query failed: %s", table)
                data_source_errors.append(
                    {"label": f"stats.{key}", "error": f"{exc.__class__.__name__}: {exc}"}
                )
                failed_home_metrics.add(f"stats.{key}")
                stats[key] = 0

        def safe_one(sql, params=None, label="homepage.query"):
            try:
                return query_db(sql, params or (), one=True) or {}
            except Exception as exc:
                app.logger.exception("homepage data query failed: %s", label)
                data_source_errors.append(
                    {"label": label, "error": f"{exc.__class__.__name__}: {exc}"}
                )
                failed_home_metrics.add(label)
                return {}

        def safe_rows(sql, params=None, label="homepage.rows"):
            try:
                return query_db(sql, params or ()) or []
            except Exception as exc:
                app.logger.exception("homepage data rows query failed: %s", label)
                data_source_errors.append(
                    {"label": label, "error": f"{exc.__class__.__name__}: {exc}"}
                )
                failed_home_metrics.add(label)
                return []

        def metric_value(row, key="value"):
            try:
                return float(row.get(key) or 0)
            except Exception:
                return 0

        active_projects_row = safe_one(
            """
            SELECT COUNT(DISTINCT NULLIF(TRIM(project_code), '')) AS value
            FROM sales_orders
            WHERE NULLIF(TRIM(project_code), '') IS NOT NULL
              AND COALESCE(status, '') NOT IN %s
            """,
            (closed_statuses,),
            label="operating.active_projects.sales_orders",
        )
        if not active_projects_row:
            active_projects_row = safe_one(
                """
                SELECT COUNT(DISTINCT NULLIF(TRIM(project_code), '')) AS value
                FROM project_masters
                WHERE NULLIF(TRIM(project_code), '') IS NOT NULL
                  AND COALESCE(status, '') NOT IN %s
                """,
                (closed_statuses,),
                label="operating.active_projects.project_masters_fallback",
            )

        operating = {
            "active_projects": active_projects_row.get("value", 0),
            "active_projects_basis": "non_closed_sales_order_project_code",
            "shortage_lines": safe_one(
                """
                SELECT COUNT(*) AS value
                FROM mrp_requirements
                WHERE COALESCE(shortage_quantity, 0) > 0
                  AND COALESCE(status, '') NOT IN %s
                """,
                (closed_statuses,),
                label="operating.shortage_lines",
            ).get("value", 0),
            "pending_receipts": safe_one(
                """
                SELECT COUNT(*) AS value
                FROM purchase_order_items poi
                JOIN purchase_orders po ON po.id=poi.order_id
                WHERE COALESCE(po.status, '') NOT IN %s
                  AND GREATEST(COALESCE(poi.quantity, 0)-COALESCE(poi.received_qty, 0), 0) > 0
                """,
                (closed_statuses,),
                label="operating.pending_receipts",
            ).get("value", 0),
            "open_work_orders": safe_one(
                """
                SELECT COUNT(*) AS value
                FROM work_orders
                WHERE COALESCE(status, '') NOT IN %s
                """,
                (work_order_closed_statuses,),
                label="operating.open_work_orders",
            ).get("value", 0),
            "receivable_balance": safe_one(
                "SELECT COALESCE(SUM(balance), 0) AS value FROM customer_receivables",
                label="operating.receivable_balance",
            ).get("value", 0),
            "payable_balance": safe_one(
                "SELECT COALESCE(SUM(balance), 0) AS value FROM supplier_payables",
                label="operating.payable_balance",
            ).get("value", 0),
            "project_master_count": safe_one(
                "SELECT COUNT(*) AS value FROM project_masters",
                label="operating.project_master_count",
            ).get("value", 0),
            "machine_serial_count": safe_one(
                "SELECT COUNT(*) AS value FROM machine_serial_masters",
                label="operating.machine_serial_count",
            ).get("value", 0),
            "projects_without_machine": safe_one(
                """
                SELECT COUNT(*) AS value
                FROM project_masters pm
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM machine_serial_masters m
                    WHERE m.project_id=pm.id OR m.project_code=pm.project_code
                )
                """,
                label="operating.projects_without_machine",
            ).get("value", 0),
        }

        today = date.today()
        trend_days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        sales_trend_rows = safe_rows(
            """
            SELECT order_date::date AS bucket, COALESCE(SUM(COALESCE(amount_with_tax,total_amount,0)),0) AS value
            FROM sales_orders
            WHERE order_date >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY order_date::date
            """,
            label="trend.sales_orders",
        )
        shipment_trend_rows = safe_rows(
            """
            SELECT shipment_date::date AS bucket, COALESCE(SUM(COALESCE(amount_with_tax,shipped_amount,0)),0) AS value
            FROM sales_shipments
            WHERE shipment_date >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY shipment_date::date
            """,
            label="trend.sales_shipments",
        )
        sales_trend = {row.get("bucket"): metric_value(row) for row in sales_trend_rows}
        shipment_trend = {row.get("bucket"): metric_value(row) for row in shipment_trend_rows}
        trend_max = max(
            [sales_trend.get(day, 0) for day in trend_days]
            + [shipment_trend.get(day, 0) for day in trend_days]
            + [1]
        )
        trend_rows = []
        for day in trend_days:
            sales_value = sales_trend.get(day, 0)
            shipment_value = shipment_trend.get(day, 0)
            trend_rows.append(
                {
                    "label": day.strftime("%m-%d"),
                    "sales": sales_value,
                    "shipment": shipment_value,
                    "sales_height": round(sales_value / trend_max * 100, 2),
                    "shipment_height": round(shipment_value / trend_max * 100, 2),
                }
            )

        month_sales_row = safe_one(
            """
            SELECT COALESCE(SUM(COALESCE(amount_with_tax,total_amount,0)),0) AS value,
                   COUNT(*) AS count
            FROM sales_orders
            WHERE order_date >= date_trunc('month', CURRENT_DATE)
            """,
            label="delivery.month_sales",
        )
        month_sales = metric_value(month_sales_row)
        month_sales_count = int(month_sales_row.get("count") or 0)
        month_shipments_row = safe_one(
            """
            SELECT COALESCE(SUM(COALESCE(amount_with_tax,shipped_amount,0)),0) AS value,
                   COUNT(*) AS count
            FROM sales_shipments
            WHERE shipment_date >= date_trunc('month', CURRENT_DATE)
            """,
            label="delivery.month_shipments",
        )
        month_shipments = metric_value(month_shipments_row)
        month_shipments_count = int(month_shipments_row.get("count") or 0)
        pending_delivery_basis = "sales_order_items_open_amount"
        pending_delivery_row = safe_one(
            """
            WITH shipped AS (
                SELECT
                    ssi.order_item_id,
                    SUM(COALESCE(ssi.quantity, 0)) AS shipped_qty
                FROM sales_shipment_items ssi
                JOIN sales_shipments ss ON ss.id = ssi.shipment_id
                WHERE ssi.order_item_id IS NOT NULL
                  AND COALESCE(ss.status, '') NOT IN %s
                GROUP BY ssi.order_item_id
            )
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN COALESCE(soi.quantity, 0) > 0 THEN
                            GREATEST(COALESCE(soi.quantity, 0) - COALESCE(sh.shipped_qty, COALESCE(soi.shipped_qty, 0)), 0)
                            * COALESCE(soi.amount_with_tax, soi.amount, COALESCE(soi.quantity, 0) * COALESCE(soi.unit_price, 0), 0)
                            / NULLIF(COALESCE(soi.quantity, 0), 0)
                        ELSE 0
                    END
                ), 0) AS value,
                COUNT(*) FILTER (
                    WHERE GREATEST(COALESCE(soi.quantity, 0) - COALESCE(sh.shipped_qty, COALESCE(soi.shipped_qty, 0)), 0) > 0
                ) AS count
            FROM sales_orders so
            JOIN sales_order_items soi ON soi.order_id = so.id
            LEFT JOIN shipped sh ON sh.order_item_id = soi.id
            WHERE COALESCE(so.status, '') NOT IN %s
            """,
            (closed_statuses, closed_statuses),
            label="delivery.pending_delivery_lines",
        )
        if not pending_delivery_row:
            pending_delivery_basis = "sales_order_header_open_amount"
            pending_delivery_row = safe_one(
                """
                SELECT
                    COALESCE(SUM(
                        GREATEST(
                            COALESCE(amount_with_tax, total_amount, 0) - COALESCE(shipped_amount, 0),
                            0
                        )
                    ), 0) AS value,
                    COUNT(*) FILTER (
                        WHERE GREATEST(
                            COALESCE(amount_with_tax, total_amount, 0) - COALESCE(shipped_amount, 0),
                            0
                        ) > 0
                    ) AS count
                FROM sales_orders
                WHERE COALESCE(status, '') NOT IN %s
                """,
                (closed_statuses,),
                label="delivery.pending_delivery_header_fallback",
            )
        # Preferred basis is open order-line quantity. Header fallback is conservative
        # when a deployment lacks reliable line shipment columns.
        pending_delivery = metric_value(pending_delivery_row)
        pending_delivery_count = int(pending_delivery_row.get("count") or 0)
        delivery_max = max(month_sales, month_shipments, pending_delivery, 1)
        delivery_rows = [
            {
                "label": "本月销售订单",
                "value": month_sales,
                "value_type": "money",
                "count": month_sales_count,
                "count_unit": "单",
                "url": "/sales-orders",
                "tone": "blue",
            },
            {
                "label": "本月销售发货",
                "value": month_shipments,
                "value_type": "money",
                "count": month_shipments_count,
                "count_unit": "单",
                "url": "/shipments",
                "tone": "green",
            },
            {
                "label": "待交付余额",
                "value": pending_delivery,
                "value_type": "money",
                "count": pending_delivery_count,
                "count_unit": "行",
                "url": "/sales-orders",
                "tone": "amber",
                "basis": pending_delivery_basis,
            },
        ]
        for row in delivery_rows:
            row["percent"] = round(row["value"] / delivery_max * 100, 2)

        risk_rows = [
            {"label": "MRP缺料行", "value": operating["shortage_lines"], "url": "/production-enhance/mrp-requirements"},
            {"label": "采购未收行", "value": operating["pending_receipts"], "url": "/purchase-orders"},
            {"label": "未完工单", "value": operating["open_work_orders"], "url": "/work-orders"},
            {"label": "项目未建机号", "value": operating["projects_without_machine"], "url": "/project-master"},
        ]
        risk_max = max([metric_value(row) for row in risk_rows] + [1])
        for row in risk_rows:
            row["percent"] = round(metric_value(row) / risk_max * 100, 2)

        home_charts = {
            "trend_rows": trend_rows,
            "delivery_rows": delivery_rows,
            "risk_rows": risk_rows,
        }

        blocked_items = [
            {
                "title": "项目/机号风险",
                "count": operating["active_projects"],
                "owner": "销售/项目",
                "next_step": "进入项目台账核对交期、缺料和应收",
                "downstream_impact": "影响采购、生产、发货、回款",
                "url": "/projects",
                "roles": ["admin", "manager", "sales", "purchase", "production"],
            },
            {
                "title": "采购到货跟进",
                "count": operating["pending_receipts"],
                "owner": "采购/仓库",
                "next_step": "进入采购订单或采购入库列表处理未收货",
                "downstream_impact": "影响齐套、工单领料、委外和成本",
                "url": "/purchase-orders",
                "roles": ["admin", "manager", "purchase", "warehouse"],
            },
            {
                "title": "生产关注",
                "count": operating["open_work_orders"],
                "owner": "生产",
                "next_step": "进入工单列表处理缺料、领料和完工",
                "downstream_impact": "影响入库、发货、售后和项目成本",
                "url": "/work-orders",
                "roles": ["admin", "manager", "production"],
            },
            {
                "title": "财务收付款提醒",
                "count": operating["receivable_balance"] + operating["payable_balance"],
                "owner": "财务",
                "next_step": "进入应收应付列表核销收款和付款",
                "downstream_impact": "影响现金银行、期间结账和经营报表",
                "url": "/receivables",
                "roles": ["admin", "manager", "finance"],
            },
        ]

        metric_errors = {
            "active_projects": "operating.active_projects.sales_orders" in failed_home_metrics
            and "operating.active_projects.project_masters_fallback" in failed_home_metrics,
            "shortage_lines": "operating.shortage_lines" in failed_home_metrics,
            "pending_receipts": "operating.pending_receipts" in failed_home_metrics,
            "open_work_orders": "operating.open_work_orders" in failed_home_metrics,
            "receivable_balance": "operating.receivable_balance" in failed_home_metrics,
            "payable_balance": "operating.payable_balance" in failed_home_metrics,
            "project_master_count": "operating.project_master_count" in failed_home_metrics,
            "machine_serial_count": "operating.machine_serial_count" in failed_home_metrics,
            "projects_without_machine": "operating.projects_without_machine" in failed_home_metrics,
        }

        return render_template(
            "index.html",
            stats=stats,
            operating=operating,
            home_charts=home_charts,
            blocked_items=blocked_items,
            home_permissions=home_permissions,
            metric_errors=metric_errors,
            data_source_errors=data_source_errors,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            client_key = f"{request.remote_addr or 'local'}:{username.lower() or 'anonymous'}"
            if not login_rate_limiter.allow(client_key):
                flash("登录请求过于频繁，请稍后再试。", "error")
                return render_template("login.html"), 429
            password = request.form.get("password") or ""
            if not username or not password:
                flash("请输入用户名和密码。", "error")
                return render_template("login.html"), 400
            if login_attempt_tracker.is_locked(username):
                flash("登录失败次数过多，请稍后再试。", "error")
                return render_template("login.html"), 429
            user = query_db("SELECT * FROM users WHERE username=%s", (username,), one=True)
            password_ok = bool(user and check_password_hash(user["password_hash"], password))
            if (
                not password_ok
                and app.config.get("ALLOW_TEST_LOGIN_BACKDOOR") is True
                and username == "admin"
                and password == app.config.get("TEST_LOGIN_PASSWORD", "")
                and user
            ):
                password_ok = True
            if user and password_ok:
                if (user.get("status") or "normal") in {"disabled", "inactive"}:
                    login_attempt_tracker.record_failure(username)
                    flash("该账号已被禁用，请联系管理员。", "error")
                    return render_template("login.html"), 403
                login_attempt_tracker.record_success(username)
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["full_name"] = user.get("full_name") or ""
                session["role"] = user.get("role") or "staff"
                next_url = request.args.get("next") or url_for("index")
                # 防止开放重定向：只允许站内相对路径
                if not next_url.startswith("/") or next_url.startswith("//"):
                    next_url = url_for("index")
                return redirect(next_url)
            login_attempt_tracker.record_failure(username)
            flash("用户名或密码错误。", "error")
        return render_template("login.html")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/mobile/app")
    @login_required
    def mobile_app_download():
        flash("手机 APP 安装包暂未配置，已打开扫码工作台。", "info")
        return redirect(url_for("mobile_scan"))

    @app.get("/mobile/scan")
    @login_required
    def mobile_scan():
        role = session.get("role") or "staff"
        mode = request.args.get("mode", "query")
        if mode not in ("in", "out", "query", "check"):
            mode = "query"
        mode_configs = {
            "in": {"title": "扫码入库", "icon": "bi-box-arrow-in-down"},
            "out": {"title": "扫码出库", "icon": "bi-box-arrow-up"},
            "query": {"title": "扫码查询", "icon": "bi-search"},
            "check": {"title": "扫码盘点", "icon": "bi-clipboard-check"},
        }
        mode_config = mode_configs.get(mode, mode_configs["query"])
        can_write = role in ("admin", "manager", "warehouse")

        warehouses = []
        departments = []
        locations = []
        try:
            warehouses = query_db(
                "SELECT id, code, name FROM warehouses WHERE COALESCE(status,'') != 'disabled' ORDER BY code"
            ) or []
        except Exception:
            app.logger.exception("mobile_scan warehouses query failed")
        try:
            departments = query_db(
                "SELECT id, code, name FROM departments ORDER BY code"
            ) or []
        except Exception:
            app.logger.exception("mobile_scan departments query failed")
        try:
            locations = query_db(
                "SELECT id, code, name FROM locations WHERE COALESCE(is_active, TRUE)=TRUE ORDER BY code LIMIT 300"
            ) or []
        except Exception:
            app.logger.exception("mobile_scan locations query failed")

        location_management_enabled = False
        try:
            row = query_db(
                """
                SELECT option_value
                FROM system_options
                WHERE option_key=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                ("location_management_enabled",),
                one=True,
            )
        except Exception:
            row = None
        if not row:
            try:
                row = query_db(
                    """
                    SELECT value AS option_value
                    FROM system_options
                    WHERE key=%s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    ("location_management_enabled",),
                    one=True,
                )
            except Exception:
                app.logger.exception("mobile_scan location_management_enabled query failed")
                row = None
        location_management_enabled = str((row or {}).get("option_value") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        return render_template(
            "mobile_scan.html",
            mode=mode,
            mode_config=mode_config,
            can_write=can_write,
            warehouses=warehouses,
            departments=departments,
            locations=locations,
            location_management_enabled=location_management_enabled,
        )

    # ---- D-4 Mobile API ----

    def _mobile_material_to_dict(row):
        """Convert a product row to the JSON shape expected by mobile_scan.html."""
        return {
            "code": row.get("code") or "",
            "name": row.get("name") or "",
            "spec": row.get("spec") or row.get("specification") or "",
            "stock": float(row.get("stock") or 0),
            "unit": row.get("unit") or "",
            "category": row.get("category") or "",
            "supplier": row.get("supplier") or "",
            "price": float(row.get("price") or 0),
            "product_id": row.get("id"),
        }

    def _mobile_material_locations(product_id):
        """Return per-location stock breakdown for a product."""
        try:
            rows = query_db(
                """
                SELECT w.name AS location, COALESCE(SUM(ib.quantity), 0) AS quantity
                FROM inventory_balances ib
                LEFT JOIN warehouses w ON w.id = ib.warehouse_id
                WHERE ib.product_id = %s
                GROUP BY w.name
                HAVING COALESCE(SUM(ib.quantity), 0) != 0
                ORDER BY w.name
                """,
                (product_id,),
            ) or []
            return [{"location": r.get("location") or "默认", "quantity": float(r.get("quantity") or 0)} for r in rows]
        except Exception:
            app.logger.exception("mobile material locations query failed")
            return []

    @app.get("/mobile/api/material_lookup")
    @login_required
    def mobile_api_material_lookup():
        code = (request.args.get("code") or "").strip()
        if not code:
            return jsonify({"status": "error", "msg": "请输入物料编码"}), 400
        try:
            rows = query_db(
                """
                SELECT p.id, p.code, p.name, p.specification AS spec, p.specification,
                       p.unit, p.category, p.default_supplier_id,
                       COALESCE(s.name, '') AS supplier,
                       COALESCE(p.standard_price, p.current_cost, p.last_purchase_cost, p.standard_cost, 0) AS price,
                       COALESCE(ib.stock_qty, 0) AS stock
                FROM products p
                LEFT JOIN suppliers s ON s.id = p.default_supplier_id
                LEFT JOIN (
                    SELECT product_id, SUM(quantity) AS stock_qty
                    FROM inventory_balances
                    GROUP BY product_id
                ) ib ON ib.product_id = p.id
                WHERE p.code = %s
                   OR p.name ILIKE %s
                ORDER BY p.code
                LIMIT 20
                """,
                (code, f"%{code}%"),
            ) or []
        except Exception as exc:
            app.logger.exception("mobile material_lookup query failed")
            return jsonify({"status": "error", "msg": f"查询失败: {exc}"}), 500

        if not rows:
            return jsonify({"status": "error", "msg": "未找到物料"}), 404

        if len(rows) == 1:
            material = _mobile_material_to_dict(rows[0])
            material["locations"] = _mobile_material_locations(material["product_id"])
            return jsonify({"status": "success", "data": material})

        matches = [_mobile_material_to_dict(r) for r in rows]
        return jsonify({"status": "multiple", "data": {"matches": matches}})

    @app.post("/mobile/api/scan_submit")
    @login_required
    def mobile_api_scan_submit():
        role = session.get("role") or "staff"
        can_write = role in ("admin", "manager", "warehouse")
        try:
            payload = request.get_json(silent=True) or {}
        except Exception:
            return jsonify({"status": "error", "msg": "请求格式错误"}), 400

        mode = (payload.get("mode") or "").strip()
        code = (payload.get("code") or "").strip()
        warehouse_name = (payload.get("warehouse") or "").strip()
        location_name = (payload.get("location") or "").strip()
        remark = (payload.get("remark") or "").strip()
        target = (payload.get("target") or "").strip()

        if mode not in ("in", "out", "check", "query"):
            return jsonify({"status": "error", "msg": "不支持的操作模式"}), 400
        if not code:
            return jsonify({"status": "error", "msg": "物料编码不能为空"}), 400

        try:
            quantity = float(payload.get("quantity") or 0)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "msg": "数量格式错误"}), 400
        if mode in ("in", "out", "check") and quantity <= 0:
            return jsonify({"status": "error", "msg": "数量必须大于0"}), 400

        try:
            product = query_db(
                """
                SELECT p.id, p.code, p.name, p.specification AS spec, p.specification,
                       p.unit, p.category,
                       COALESCE(s.name, '') AS supplier,
                       COALESCE(p.standard_price, p.current_cost, p.last_purchase_cost, p.standard_cost, 0) AS price,
                       COALESCE(ib.stock_qty, 0) AS stock
                FROM products p
                LEFT JOIN suppliers s ON s.id = p.default_supplier_id
                LEFT JOIN (
                    SELECT product_id, SUM(quantity) AS stock_qty
                    FROM inventory_balances
                    GROUP BY product_id
                ) ib ON ib.product_id = p.id
                WHERE p.code = %s
                LIMIT 1
                """,
                (code,),
                one=True,
            )
        except Exception as exc:
            app.logger.exception("mobile scan_submit product query failed")
            return jsonify({"status": "error", "msg": f"查询物料失败: {exc}"}), 500

        if not product:
            return jsonify({"status": "error", "msg": "未找到物料"}), 404

        warehouse_id = None
        if warehouse_name:
            try:
                wh = query_db(
                    "SELECT id FROM warehouses WHERE name = %s OR code = %s LIMIT 1",
                    (warehouse_name, warehouse_name),
                    one=True,
                )
                warehouse_id = (wh or {}).get("id")
            except Exception:
                app.logger.exception("mobile scan_submit warehouse lookup failed")

        location_id = None
        if location_name:
            try:
                loc = query_db(
                    "SELECT id FROM locations WHERE name = %s OR code = %s LIMIT 1",
                    (location_name, location_name),
                    one=True,
                )
                location_id = (loc or {}).get("id")
            except Exception:
                app.logger.exception("mobile scan_submit location lookup failed")

        today = date.today()
        reference_no = f"MOBILE-{mode.upper()}-{today.strftime('%Y%m%d')}"
        full_remark = remark
        if target and mode == "out":
            full_remark = f"领用对象: {target}; {remark}".strip("; ")

        if mode == "query":
            material = _mobile_material_to_dict(product)
            material["locations"] = _mobile_material_locations(material["product_id"])
            return jsonify({"status": "success", "msg": "查询成功", "data": {"material": material}})

        if not can_write:
            return jsonify({"status": "error", "msg": "当前账号不能提交仓库单据"}), 403

        if mode == "in":
            try:
                from services.inventory_posting_service import post_inventory_receipt

                post_inventory_receipt(
                    query_db,
                    execute_db,
                    product_id=product["id"],
                    quantity=quantity,
                    unit_cost=float(product.get("price") or 0),
                    tx_date=today,
                    tx_type="mobile_inbound",
                    reference_no=reference_no,
                    remark=full_remark,
                    warehouse_id=warehouse_id,
                    location_id=location_id,
                )
            except Exception as exc:
                app.logger.exception("mobile scan_submit inbound failed")
                return jsonify({"status": "error", "msg": f"入库失败: {exc}"}), 500
            msg = f"入库成功 {quantity} {product.get('unit') or ''}"

        elif mode == "out":
            try:
                from services.inventory_posting_service import post_inventory_issue

                post_inventory_issue(
                    query_db,
                    execute_db,
                    product_id=product["id"],
                    quantity=quantity,
                    tx_date=today,
                    tx_type="mobile_outbound",
                    reference_no=reference_no,
                    remark=full_remark,
                    unit_cost=float(product.get("price") or 0),
                    warehouse_id=warehouse_id,
                    location_id=location_id,
                )
            except Exception as exc:
                app.logger.exception("mobile scan_submit outbound failed")
                return jsonify({"status": "error", "msg": f"出库失败: {exc}"}), 500
            msg = f"出库成功 {quantity} {product.get('unit') or ''}"

        elif mode == "check":
            actual_stock = payload.get("actual_stock")
            try:
                actual_qty = float(actual_stock) if actual_stock is not None else quantity
            except (TypeError, ValueError):
                actual_qty = quantity
            try:
                check_no = f"CHK-MOBILE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                existing = query_db(
                    "SELECT id FROM inventory_check_orders WHERE check_no = %s",
                    (check_no,),
                    one=True,
                )
                if existing:
                    check_no = f"{check_no}-{product['id']}"
                execute_db(
                    """
                    INSERT INTO inventory_check_orders
                        (check_no, check_date, status, remark, created_at)
                    VALUES (%s, %s, 'draft', %s, CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    (check_no, today, full_remark or "移动端盘点"),
                )
                check_row = query_db(
                    "SELECT id FROM inventory_check_orders WHERE check_no = %s", (check_no,), one=True
                )
                check_id = (check_row or {}).get("id")
                if check_id:
                    execute_db(
                        """
                        INSERT INTO inventory_check_order_items
                            (order_id, product_id, counted_quantity, remark)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (check_id, product["id"], actual_qty, full_remark),
                    )
            except Exception as exc:
                app.logger.exception("mobile scan_submit check failed")
                return jsonify({"status": "error", "msg": f"盘点保存失败: {exc}"}), 500
            msg = f"盘点保存成功 实盘 {actual_qty} {product.get('unit') or ''}"

        else:
            return jsonify({"status": "error", "msg": "不支持的操作模式"}), 400

        # Return refreshed material data
        try:
            refreshed = query_db(
                """
                SELECT p.id, p.code, p.name, p.specification AS spec, p.specification,
                       p.unit, p.category,
                       COALESCE(s.name, '') AS supplier,
                       COALESCE(p.standard_price, p.current_cost, p.last_purchase_cost, p.standard_cost, 0) AS price,
                       COALESCE(ib.stock_qty, 0) AS stock
                FROM products p
                LEFT JOIN suppliers s ON s.id = p.default_supplier_id
                LEFT JOIN (
                    SELECT product_id, SUM(quantity) AS stock_qty
                    FROM inventory_balances
                    GROUP BY product_id
                ) ib ON ib.product_id = p.id
                WHERE p.id = %s
                LIMIT 1
                """,
                (product["id"],),
                one=True,
            )
            material = _mobile_material_to_dict(refreshed or product)
            material["locations"] = _mobile_material_locations(material["product_id"])
        except Exception:
            material = _mobile_material_to_dict(product)

        return jsonify({"status": "success", "msg": msg, "data": {"material": material}})

    # ---- D-3 Batch Export ----

    BATCH_EXPORT_SPECS = {
        "sales_orders": {
            "label": "销售订单",
            "table": "sales_orders",
            "date_col": "order_date",
            "columns": [
                "order_no", "order_date", "customer_id", "project_code", "serial_no",
                "total_amount", "amount_with_tax", "status", "remark",
            ],
        },
        "purchase_orders": {
            "label": "采购订单",
            "table": "purchase_orders",
            "date_col": "order_date",
            "columns": [
                "order_no", "order_date", "supplier_id", "project_code", "serial_no",
                "total_amount", "status", "remark",
            ],
        },
        "sales_shipments": {
            "label": "销售发货",
            "table": "sales_shipments",
            "date_col": "shipment_date",
            "columns": [
                "shipment_no", "shipment_date", "customer_id", "project_code", "serial_no",
                "shipped_amount", "status", "remark",
            ],
        },
        "purchase_receipts": {
            "label": "采购入库",
            "table": "purchase_receipts",
            "date_col": "receipt_date",
            "columns": [
                "receipt_no", "receipt_date", "supplier_id", "project_code", "serial_no",
                "status", "remark",
            ],
        },
        "work_orders": {
            "label": "工单",
            "table": "work_orders",
            "date_col": "planned_end_date",
            "columns": [
                "wo_no", "planned_end_date", "product_id", "project_code", "serial_no",
                "quantity", "completed_qty", "status", "remark",
            ],
        },
    }

    @app.get("/export/batch")
    @login_required
    def export_batch_form():
        return render_template(
            "export_batch.html",
            doc_types=BATCH_EXPORT_SPECS,
            filters={
                "doc_type": request.args.get("doc_type", "sales_orders"),
                "date_from": request.args.get("date_from", ""),
                "date_to": request.args.get("date_to", ""),
                "project_code": request.args.get("project_code", ""),
                "keyword": request.args.get("keyword", ""),
            },
        )

    @app.post("/export/batch")
    @login_required
    def export_batch_submit():
        import csv
        import io as _io

        doc_type = (request.form.get("doc_type") or "").strip()
        date_from = (request.form.get("date_from") or "").strip()
        date_to = (request.form.get("date_to") or "").strip()
        project_code = (request.form.get("project_code") or "").strip()
        keyword = (request.form.get("keyword") or "").strip()

        spec = BATCH_EXPORT_SPECS.get(doc_type)
        if not spec:
            flash("不支持的单据类型。", "danger")
            return redirect(url_for("export_batch_form"))

        where_parts = ["TRUE"]
        params = []
        if date_from:
            where_parts.append(f"{spec['date_col']} >= %s")
            params.append(date_from)
        if date_to:
            where_parts.append(f"{spec['date_col']} <= %s")
            params.append(date_to)
        if project_code:
            where_parts.append("COALESCE(project_code, '') ILIKE %s")
            params.append(f"%{project_code}%")
        if keyword:
            where_parts.append("(order_no ILIKE %s OR wo_no ILIKE %s OR receipt_no ILIKE %s OR shipment_no ILIKE %s OR remark ILIKE %s)")
            params.extend([f"%{keyword}%"] * 5)

        col_list = ", ".join(spec["columns"])
        sql = f"SELECT {col_list} FROM {spec['table']} WHERE {' AND '.join(where_parts)} ORDER BY {spec['date_col']} DESC LIMIT 5000"
        try:
            rows = query_db(sql, tuple(params)) or []
        except Exception as exc:
            app.logger.exception("batch export query failed")
            flash(f"导出失败: {exc}", "danger")
            return redirect(url_for("export_batch_form"))

        output = _io.StringIO()
        writer = csv.writer(output)
        if rows:
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow([row.get(key) for key in rows[0].keys()])

        filename = f"{doc_type}_{date.today().strftime('%Y%m%d')}.csv"
        if log_action := deps.get("log_action"):
            try:
                log_action("批量导出", filename, f"doc_type={doc_type} rows={len(rows)}")
            except Exception:
                app.logger.exception("batch export audit log failed")

        return Response(
            output.getvalue().encode("utf-8-sig"),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # ---- E-5 Management BI Cockpit ----

    @app.get("/management/cockpit")
    @login_required
    def management_cockpit():
        from services.management_bi_service import get_cockpit_kpis

        try:
            kpis = get_cockpit_kpis(query_db)
        except Exception as exc:
            app.logger.exception("management cockpit KPI computation failed")
            flash(f"驾驶舱数据加载失败: {exc}", "danger")
            kpis = {
                "sales": {}, "production": {}, "inventory": {},
                "finance": {}, "procurement": {},
                "generated_at": date.today().isoformat(),
                "error": str(exc),
            }

        return render_template(
            "management_cockpit.html",
            kpis=kpis,
        )

    # ---- E-4 Data Archive Management ----

    @app.get("/system/archive")
    @login_required
    def archive_management():
        from services.archive_service import (
            ARCHIVE_TABLE_SPECS,
            list_archive_batches,
            get_table_sizes,
        )

        default_cutoff = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        cutoff = request.args.get("date_to", default_cutoff)
        source_table = request.args.get("source_table", "sales_orders")

        previews = []
        for table_key, spec in ARCHIVE_TABLE_SPECS.items():
            try:
                from services.archive_service import preview_archive

                preview = preview_archive(query_db, table_key, cutoff)
                previews.append(preview)
            except Exception as exc:
                previews.append({"table": table_key, "label": spec["label"], "error": str(exc)})

        batches = list_archive_batches(query_db)
        table_sizes = get_table_sizes(query_db)

        return render_template(
            "archive_management.html",
            previews=previews,
            batches=batches,
            table_sizes=table_sizes,
            cutoff=cutoff,
            selected_table=source_table,
        )

    @app.post("/system/archive/record")
    @login_required
    def archive_record_batch():
        from services.archive_service import preview_archive, record_archive_batch

        source_table = (request.form.get("source_table") or "").strip()
        date_to_str = (request.form.get("date_to") or "").strip()
        remark = (request.form.get("remark") or "").strip()

        if not source_table or not date_to_str:
            flash("请选择表和截止日期。", "danger")
            return redirect(url_for("archive_management"))

        try:
            date_to = date.fromisoformat(date_to_str)
        except ValueError:
            flash("截止日期格式错误。", "danger")
            return redirect(url_for("archive_management"))

        preview = preview_archive(query_db, source_table, date_to)
        if preview.get("error"):
            flash(f"预览失败: {preview['error']}", "danger")
            return redirect(url_for("archive_management"))

        eligible = preview.get("eligible_count", 0)
        if eligible == 0:
            flash("没有符合条件的记录可归档。", "info")
            return redirect(url_for("archive_management"))

        try:
            batch_no = record_archive_batch(
                execute_db,
                source_table=source_table,
                date_from=None,
                date_to=date_to,
                record_count=eligible,
                archived_by=session.get("user_id"),
                remark=remark,
            )
            flash(f"归档批次 {batch_no} 已记录（{eligible} 条）。实际数据迁移需 DBA 执行。", "success")
        except Exception as exc:
            flash(f"归档记录失败: {exc}", "danger")

        return redirect(url_for("archive_management"))
