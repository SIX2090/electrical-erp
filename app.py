from flask import Flask, abort, g, redirect, request, session, url_for
from pathlib import Path
import os
import uuid

from werkzeug.security import generate_password_hash
from flask_wtf.csrf import CSRFProtect
from urllib.parse import urlencode

from services.inventory_service import (
    inventory_outbound,
    inventory_inbound_weighted_avg,
    record_stock_transaction,
    ensure_inventory as svc_ensure_inventory,
    ensure_document_sequence_schema,
    get_next_doc_no as svc_get_next_doc_no,
)
from services.system_config import (
    build_database_info,
    create_visibility_checker,
    get_export_config,
    get_export_groups,
    get_export_items_by_format,
    get_import_config,
    get_import_groups,
    get_import_items,
    get_system_admin_actions,
    get_system_shortcuts,
    get_system_top_cards,
)
from services.app_runtime import (
    create_db_helpers,
    create_login_required,
    create_role_required,
    initialize_database as runtime_initialize_database,
    register_context_processors,
    register_template_helpers,
    require_date,
    to_non_negative_float,
    to_positive_float,
)
from services.env_config import get_inventory_secret_key, get_login_lockout_seconds, get_login_max_failures, get_login_rate_limit, get_login_rate_limit_window_seconds, get_pg_password, is_production_env
from services.login_protection import LoginAttemptTracker
from services.rate_limit import FixedWindowRateLimiter
from services.inventory_posting_service import post_inventory_issue, post_inventory_receipt
from services.schema_migrations import apply_schema_migrations
from services.audit_log_service import log_action as record_audit_action
from services.pilot_permissions import (
    PILOT_COMMON_PATHS,
    PILOT_DEFAULT_ROLE_GROUPS,
    PILOT_PERMISSION_GROUPS,
    default_groups_for_role,
    pilot_paths_for_groups,
)
from routes.system_management_routes import register_routes as register_system_management_routes
from routes.print_template_routes import register_routes as register_print_template_routes
from routes.core_operations_routes import register_routes as register_core_operations_routes
from routes.help_routes import register_routes as register_help_routes
from routes.app_shell_routes import register_routes as register_app_shell_routes
from routes.api_routes import register_api_routes
from routes.finance_routes import register_routes as register_finance_routes
from routes.project_cost_routes import register_routes as register_project_cost_routes
from routes.project_delivery_workbench_routes import register_routes as register_project_delivery_workbench_routes
from routes.attachment_routes import register_routes as register_attachment_routes
from routes.sales_report_routes import register_sales_report_routes
from routes.invoice_matching_routes import register_invoice_matching_routes
from routes.invoice_red_flush_routes import register_invoice_red_flush_routes
from routes.invoice_reconciliation_routes import register_invoice_reconciliation_routes
# FIXED 20260617: Comment out duplicate route registrations to avoid conflicts
# from routes.voucher_routes import register_voucher_routes
from routes.general_ledger_routes import register_general_ledger_routes
from routes.inventory_costing_routes import register_inventory_costing_routes
from routes.project_cost_reports_routes import register_project_cost_routes as register_project_cost_reports_routes
from routes.cabinet_cost_reports_routes import register_cabinet_cost_routes
from routes.period_closing_routes import register_period_closing_routes
from routes.financial_report_routes import register_financial_report_routes
from routes.trace_routes import register_routes as register_trace_routes
from routes.bom_version_routes import register_routes as register_bom_version_routes
from routes.mrp_routes import register_routes as register_mrp_routes
from routes.cost_engine_routes import register_routes as register_cost_engine_routes
from routes.data_permission_routes import register_routes as register_data_permission_routes
from routes.registry import bind_route_dependencies, register_blueprints
from routes.notification_routes import bp as notification_bp
from routes.security_routes import bp as security_bp
from routes.monitoring_routes import bp as monitoring_bp


BASE_DIR = Path(__file__).resolve().parent

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DATABASE = os.environ.get("PG_DATABASE", "wms")
PG_USER = os.environ.get("PG_USER", "wms_user")
PG_PASSWORD = get_pg_password()

SECRET_KEY = get_inventory_secret_key()
ROLE_ALIASES = {
    "admin": "admin",
    "\u7ba1\u7406\u5458": "admin",
    "\u7cfb\u7edf\u7ba1\u7406\u5458": "admin",
    "manager": "manager",
    "\u7ecf\u7406": "manager",
    "\u4e3b\u7ba1": "manager",
    "sales": "sales",
    "\u9500\u552e": "sales",
    "purchase": "purchase",
    "\u91c7\u8d2d": "purchase",
    "warehouse": "warehouse",
    "\u4ed3\u5e93": "warehouse",
    "production": "production",
    "\u751f\u4ea7": "production",
    "service": "service",
    "\u552e\u540e": "service",
    "finance": "finance",
    "\u8d22\u52a1": "finance",
    "staff": "staff",
    "clerk": "staff",
    "\u5458\u5de5": "staff",
    "\u64cd\u4f5c\u5458": "staff",
    "user": "staff",
    "\u666e\u901a\u7528\u6237": "staff",
}


def normalize_role(role):
    value = (role or "").strip()
    if not value:
        return "staff"
    return ROLE_ALIASES.get(value, value)


PILOT_NAV_MODES = {"gt_pilot", "pilot_gtym", "gtym_pilot"}
PILOT_GROUP_PATHS = {group["key"]: set(group["paths"]) for group in PILOT_PERMISSION_GROUPS}


def _path_matches(path, allowed_paths):
    for allowed in allowed_paths:
        allowed = (allowed or "").split("?", 1)[0]
        if allowed == "/":
            if path == "/":
                return True
            continue
        if path == allowed or path.startswith(allowed.rstrip("/") + "/"):
            return True
    return False


def get_db_config():
    return {
        "host": PG_HOST,
        "port": PG_PORT,
        "database": PG_DATABASE,
        "user": PG_USER,
        "password": PG_PASSWORD,
    }


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(config=None):
    app = Flask(__name__)
    # Keep Flask JSON responses encoded as UTF-8.
    app.config["JSON_AS_ASCII"] = False
    app.config["JSONIFY_MIMETYPE"] = "application/json; charset=utf-8"
    
    if config:
        app.config.update(config)
    if is_production_env() and not app.testing:
        get_pg_password()
        if not app.config.get("SECRET_KEY"):
            get_inventory_secret_key()
    _secret = app.config.get("SECRET_KEY") or get_inventory_secret_key() or os.urandom(32).hex()
    if not app.config.get("SECRET_KEY") and not SECRET_KEY and not app.testing:
        import warnings
        warnings.warn(
            "INVENTORY_SECRET_KEY is not configured; using a random key for this process. Set it explicitly for production.",
            stacklevel=2,
        )
    app.config["SECRET_KEY"] = _secret
    app.config.setdefault("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get("INVENTORY_COOKIE_SAMESITE", "Lax")
    secure_default = "1" if is_production_env() else "0"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("INVENTORY_COOKIE_SECURE", secure_default) == "1"
    if "WTF_CSRF_ENABLED" not in app.config:
        csrf_default = "0" if app.testing or os.environ.get("PYTEST_CURRENT_TEST") else "1"
        app.config["WTF_CSRF_ENABLED"] = os.environ.get(
            "WTF_CSRF_ENABLED", os.environ.get("INVENTORY_CSRF_ENABLED", csrf_default)
        ) == "1"
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600
    if "INIT_DATABASE_ON_CREATE" not in app.config:
        app.config["INIT_DATABASE_ON_CREATE"] = _env_flag(
            "INVENTORY_INIT_DB_ON_CREATE",
            default=False,
        )
    app.config.setdefault("LOGIN_MAX_FAILURES", get_login_max_failures())
    app.config.setdefault("LOGIN_LOCKOUT_SECONDS", get_login_lockout_seconds())
    app.config.setdefault("LOGIN_RATE_LIMIT", get_login_rate_limit())
    app.config.setdefault("LOGIN_RATE_LIMIT_WINDOW_SECONDS", get_login_rate_limit_window_seconds())
    if app.testing:
        # 测试登录后门必须同时满足 app.testing 和显式环境变量 ALLOW_TEST_LOGIN_BACKDOOR=1
        # 防止误用 testing 配置启动生产服务时后门自动开启
        if os.environ.get("ALLOW_TEST_LOGIN_BACKDOOR", "") == "1":
            app.config.setdefault("ALLOW_TEST_LOGIN_BACKDOOR", True)
            app.config.setdefault("TEST_LOGIN_PASSWORD", "admin")
    csrf = CSRFProtect(app)
    register_context_processors(app)

    def _route_rule_exists(path, method="GET"):
        method = (method or "GET").upper()
        for rule in app.url_map.iter_rules():
            if rule.rule == path and method in rule.methods:
                return True
        return False

    def _global_operation_actions():
        """Generate standardized toolbar actions by page type.

        Page types: entry, list, report, workbench, other.
        Page-specific buttons can be injected via g.toolbar_extras.
        """
        path = request.path.rstrip("/") or "/"
        if path.startswith(("/api", "/static", "/attachments", "/document_attachments")):
            return []
        if path in {"/login", "/logout"}:
            return []

        endpoint = request.endpoint or ""
        is_entry_page = path.endswith("/new") or path.endswith("/edit") or "/edit" in path
        is_report_page = (
            "/reports/" in path
            or path.startswith("/reports")
            or path.startswith("/finance/inventory-costing")
            or "report" in endpoint
        )
        is_workbench_page = "workbench" in endpoint or path == "/" or path in {
            "/pending-documents", "/approval/pending", "/trace", "/trace/integrity",
            "/project-delivery-workbench", "/projects",
        }
        is_detail_page = bool(endpoint) and "_detail" in endpoint or path.rstrip("/").split("/")[-1].isdigit()
        # Trace/report/cost/ledger detail pages are read-only views, not document detail pages
        is_trace_detail = is_detail_page and any(kw in endpoint for kw in (
            "run_detail", "cost_detail",
            "account_detail_ledger", "balance_detail",
            "shipped_unsettled_detail", "sales_order_execution_detail",
            "snapshot_detail", "finance_detail_ledger",
            "fx_adjustment_detail", "approval_record_detail",
            "project_trace_detail",
        ))
        is_list_page = not (is_entry_page or is_report_page or is_workbench_page or is_detail_page)

        def export_href(export_format):
            args = request.args.to_dict(flat=True)
            args["export"] = export_format
            return f"{path}?{urlencode(args)}"

        # Page-specific extras (set by route handlers via g.toolbar_extras)
        extras = getattr(g, "toolbar_extras", None) or []

        # --- Standard button groups by page type ---
        actions = []

        if is_entry_page:
            # Entry page: 新增 | 保存 | 保存并新增 | 刷新 | 返回列表 | 打印 | [extras] | 更多
            actions.append({"label": "新增", "type": "link", "href": path})
            actions.extend([
                {"label": "保存", "type": "button", "event": "global-submit-main-form"},
                {"label": "保存并新增", "type": "button", "event": "global-submit-main-form-new"},
            ])
            if extras:
                actions.extend(extras)
            actions.append({"label": "刷新", "type": "link", "href": request.full_path if request.query_string else path})
            list_path = path.rsplit("/new", 1)[0].rsplit("/edit", 1)[0]
            if "/edit" in path:
                parts = list_path.rsplit("/", 1)
                if parts and parts[-1].isdigit():
                    list_path = parts[0]
            if list_path and list_path != path and _route_rule_exists(list_path, "GET"):
                actions.append({"label": "返回列表", "type": "link", "href": list_path})
            actions.append({"label": "打印", "type": "button", "event": "global-print-page"})
            # 更多 dropdown
            is_new_page = path.endswith("/new")
            more_items = [
                {"label": "复制", "type": "button", "event": "global-copy-document", "disabled": is_new_page},
                {"label": "删除", "type": "button", "event": "global-delete-document", "disabled": is_new_page},
                {"label": "作废", "type": "button", "event": "global-void-document", "disabled": is_new_page},
                {"type": "divider"},
                {"label": "导出页面 CSV", "type": "button", "event": "global-export-table", "title": "导出当前页面可见表格，不生成正式单据导出文件。"},
                {"label": "导出 Excel", "type": "disabled", "title": "新增/编辑页未保存为正式单据前不提供后端 Excel 导出。"},
                {"type": "divider"},
                {"type": "divider"},
                {"label": "返回首页", "type": "link", "href": "/"},
            ]
            if path in {"/inventory/inbound/new", "/inventory/outbound/new"}:
                more_items = [
                    item for item in more_items
                    if item.get("event") not in {"global-copy-document", "global-delete-document", "global-void-document"}
                ]
            elif is_new_page:
                more_items = [
                    item for item in more_items
                    if item.get("event") not in {"global-copy-document", "global-delete-document", "global-void-document"}
                ]
            actions.append({"label": "更多", "type": "dropdown", "items": more_items})

        elif is_report_page:
            # Report page: 刷新报表 | 打印 | 更多
            actions.append({"label": "查询", "type": "button", "event": "global-focus-filter"})
            actions.append({"label": "重置", "type": "link", "href": path})
            actions.append({"label": "刷新报表", "type": "link", "href": request.full_path if request.query_string else path})
            actions.append({"label": "打印", "type": "button", "event": "global-print-page"})
            if extras:
                actions.append({"type": "divider"})
                actions.extend(extras)
            more_items = [
                {"label": "导出 CSV", "type": "link", "href": export_href("csv")},
                {"label": "导出 Excel", "type": "link", "href": export_href("xlsx")},
                {"type": "divider"},
                {"type": "divider"},
                {"label": "返回报表中心", "type": "link", "href": "/reports"},
                {"label": "返回首页", "type": "link", "href": "/"},
            ]
            actions.append({"label": "更多", "type": "dropdown", "items": more_items})

        elif is_workbench_page:
            # Workbench page: 刷新 | 更多
            actions.append({"label": "刷新", "type": "link", "href": request.full_path if request.query_string else path})
            if extras:
                actions.append({"type": "divider"})
                actions.extend(extras)
            more_items = [
                {"type": "divider"},
                {"label": "返回首页", "type": "link", "href": "/"},
            ]
            actions.append({"label": "更多", "type": "dropdown", "items": more_items})

        elif is_detail_page:
            # Detail page (T+ style): 查找 | 首张 上一张 下一张 末张 | 刷新 | 打印 | [extras] | 更多
            if not is_trace_detail:
                actions.append({"label": "查找", "type": "button", "event": "doc-nav-search"})
                actions.append({"type": "nav", "items": [
                    {"label": "首张", "event": "doc-nav-first"},
                    {"label": "上一张", "event": "doc-nav-prev"},
                    {"label": "下一张", "event": "doc-nav-next"},
                    {"label": "末张", "event": "doc-nav-last"},
                ]})
            actions.append({"label": "刷新", "type": "link", "href": request.full_path if request.query_string else path})
            actions.append({"label": "打印", "type": "button", "event": "global-print-page"})
            if extras:
                actions.append({"type": "divider"})
                actions.extend(extras)
            # Derive list path by stripping trailing /<id>
            list_path = path.rsplit("/", 1)[0] if "/" in path else path
            more_items = [
                {"label": "导出 CSV", "type": "link", "href": export_href("csv")},
                {"label": "导出 Excel", "type": "link", "href": export_href("xlsx")},
                {"type": "divider"},
            ]
            if list_path and list_path != path and _route_rule_exists(list_path, "GET"):
                more_items.append({"type": "divider"})
                more_items.append({"label": "返回列表", "type": "link", "href": list_path})
            more_items.append({"type": "divider"})
            more_items.append({"label": "返回首页", "type": "link", "href": "/"})
            actions.append({"label": "更多", "type": "dropdown", "items": more_items})

        else:
            # List/other page: standard query/list actions only. Page-specific
            # actions are merged in from local document_menu_bar instances.
            actions.append({"label": "筛选", "type": "button", "event": "global-focus-filter"})
            actions.append({"label": "刷新", "type": "link", "href": request.full_path if request.query_string else path})
            actions.append({"label": "打印", "type": "button", "event": "global-print-page"})
            actions.append({"label": "复制", "type": "button", "event": "global-copy-table"})
            if extras:
                actions.append({"type": "divider"})
                actions.extend(extras)
            more_items = [
                {"label": "导出 Excel", "type": "link", "href": export_href("xlsx")},
                {"label": "导出 CSV", "type": "link", "href": export_href("csv")},
                {"type": "divider"},
                {"label": "返回首页", "type": "link", "href": "/"},
            ]
            actions.append({"label": "更多", "type": "dropdown", "items": more_items})

        return actions

    @app.context_processor
    def inject_global_operation_toolbar():
        return {"global_operation_actions": _global_operation_actions}

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # Prevent browser from caching HTML pages so users always see the latest version
        if response.content_type and "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        # Keep template context values encoded as UTF-8.
        if response.content_type and "text" in response.content_type:
            if "charset=" not in response.content_type:
                response.headers["Content-Type"] = f"{response.content_type}; charset=utf-8"
        return response

    @app.after_request
    def record_audit_log(response):
        if request.method in {"POST", "PUT", "DELETE"} and response.status_code < 400:
            failed_categories = {"danger", "error", "warning"}
            flashed_failure = any(
                category in failed_categories
                for category, _message in session.get("_flashes", [])
            )
            if flashed_failure:
                return response
            record_audit_action(
                session.get("user_id"),
                session.get("username") or session.get("user_name") or session.get("role") or "",
                request.method,
                request.path,
                request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",", 1)[0].strip(),
            )
        return response

    _get_db, query_db, execute_db, execute_and_return = create_db_helpers(app, get_db_config())
    app.config["_query_db"] = query_db
    with _get_db(cursor_factory=None) as conn:
        with conn.cursor() as cur:
            apply_schema_migrations(cur)
        conn.commit()

    @app.context_processor
    def inject_topbar_alerts():
        alerts = []
        if not session.get("user_id"):
            return {"topbar_alerts": alerts, "topbar_alert_total": 0}
        try:
            row = query_db(
                """
                SELECT COUNT(*) AS engineering_not_ready
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
                    LIMIT 1
                ) released_drawing ON TRUE
                WHERE COALESCE(etc.status, '') NOT IN ('confirmed', 'closed', 'voided')
                   OR COALESCE(etc.blocked_reason, '') <> ''
                   OR etc.bom_id IS NULL
                   OR etc.routing_id IS NULL
                   OR COALESCE(etc.drawing_no, '') = ''
                   OR COALESCE(etc.drawing_version, '') = ''
                   OR COALESCE(bom_items.item_count, 0) = 0
                   OR released_drawing.id IS NULL
                """,
                one=True,
            )
            engineering_not_ready = int((row or {}).get("engineering_not_ready") or 0)
        except Exception:
            engineering_not_ready = 0
        if engineering_not_ready:
            alerts.append(
                {
                    "label": "工程准备未就绪",
                    "hint": "技术确认、BOM、图纸或齐套仍有缺口",
                    "href": "/engineering/technical-confirmations",
                    "count": engineering_not_ready,
                    "level": "warning",
                }
            )
        return {
            "topbar_alerts": alerts,
            "topbar_alert_total": sum(int(item.get("count") or 0) for item in alerts),
        }
    app.extensions["login_rate_limiter"] = FixedWindowRateLimiter(
        limit=app.config["LOGIN_RATE_LIMIT"],
        window_seconds=app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"],
        query_db=query_db,
        execute_db=execute_db,
    )
    app.extensions["login_rate_limiter"].ensure_schema()
    app.extensions["login_attempt_tracker"] = LoginAttemptTracker(
        max_failures=app.config["LOGIN_MAX_FAILURES"],
        lockout_seconds=app.config["LOGIN_LOCKOUT_SECONDS"],
        query_db=query_db,
        execute_db=execute_db,
    )
    app.extensions["login_attempt_tracker"].ensure_schema()

    def is_logged_in():
        return "user_id" in session

    def has_any_role(*allowed_roles):
        return normalize_role(session.get("role")) in {normalize_role(role) for role in allowed_roles}

    def _forbidden():
        return "Forbidden", 403

    def _current_role_allowed(*roles):
        return has_any_role(*roles)

    def _ensure_pilot_role_permission_table():
        execute_db(
            """
            CREATE TABLE IF NOT EXISTS pilot_role_permissions (
                role VARCHAR(80) PRIMARY KEY,
                permission_groups TEXT NOT NULL DEFAULT '',
                action_permissions TEXT NOT NULL DEFAULT '',
                updated_by INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        execute_db("ALTER TABLE pilot_role_permissions ADD COLUMN IF NOT EXISTS action_permissions TEXT NOT NULL DEFAULT ''")

    def _configured_pilot_groups_for_role(role):
        normalized = normalize_role(role)
        try:
            _ensure_pilot_role_permission_table()
            row = query_db(
                "SELECT permission_groups FROM pilot_role_permissions WHERE role=%s",
                (normalized,),
                one=True,
            )
        except Exception:
            row = None
        if not row:
            return default_groups_for_role(normalized)
        raw = row.get("permission_groups") or ""
        parsed = {item.strip() for item in raw.split(",") if item.strip()}
        if not parsed:
            # 数据库行存在但 permission_groups 为空时，回退到默认权限组，
            # 避免角色保存权限后失去对所有详情页的访问权限。
            return default_groups_for_role(normalized)
        return parsed

    def _pilot_allowed_paths_for_role(role):
        normalized = normalize_role(role)
        return pilot_paths_for_groups(_configured_pilot_groups_for_role(normalized))

    def _is_pilot_scope_path(path):
        scoped = set(PILOT_COMMON_PATHS)
        for paths in PILOT_GROUP_PATHS.values():
            scoped |= set(paths)
        return _path_matches(path, scoped)

    @app.before_request
    def enforce_high_risk_access_controls():
        path = request.path.rstrip("/") or "/"
        method = request.method.upper()
        nav_mode = (os.environ.get("INVENTORY_NAV_MODE") or "").strip()

        protected_system_prefixes = ("/security", "/monitoring")
        if path.startswith(protected_system_prefixes) and not session.get("user_id"):
            return redirect(url_for("login", next=request.path))

        if not session.get("user_id"):
            return None

        # FIXED 20260617: Removed finance route guards to allow normal access
        # finance_blocked_get_paths = {
        #     "/finance/vouchers/new",
        #     "/finance/opening-balances",
        #     "/chart-of-accounts",
        # }
        # if method == "GET" and path in finance_blocked_get_paths:
        #     return "Not Found", 404

        # finance_blocked_post_paths = {
        #     "/finance/vouchers/save",
        #     "/finance/opening-balances",
        #     "/chart-of-accounts/add",
        # }
        # if method == "POST" and path in finance_blocked_post_paths:
        #     return _forbidden()

        # 发票和凭证的编辑/保存/审核路由均已实现，不再硬编码拦截。
        # 权限控制由 pilot 权限组和路由自身的 @login_required 负责。
        if path.startswith("/chart-of-accounts/") and method == "POST" and path.endswith(("/edit", "/delete")):
            return _forbidden()

        if nav_mode in PILOT_NAV_MODES and path in {"/system_settings"}:
            return "Not Found", 404

        if nav_mode in PILOT_NAV_MODES and method == "GET":
            opening_setup_paths = {
                "/subcontract/opening",
                "/subcontract/opening/new",
                "/finance/opening/receivables",
                "/finance/opening/receivables/new",
                "/finance/opening/payables",
                "/finance/opening/payables/new",
            }
            if path in opening_setup_paths and not _current_role_allowed("admin", "manager", "purchase", "finance"):
                return _forbidden()
            if path in {"/inventory/inbound", "/inventory/outbound"} and not _current_role_allowed("admin", "manager", "purchase", "warehouse", "production", "finance"):
                return _forbidden()
            if path in {"/purchase-returns", "/purchase-returns/new"} and not _current_role_allowed("admin", "manager", "purchase", "finance"):
                return _forbidden()
            if path == "/purchase_receipts/new" and not _current_role_allowed("admin", "manager", "purchase", "warehouse", "finance"):
                return _forbidden()
            if path == "/shipments/new" and not _current_role_allowed("admin", "manager", "sales", "warehouse", "finance"):
                return _forbidden()
            subcontract_inventory_report_paths = {
                "/inventory/reports/subcontract-wip",
                "/inventory/reports/subcontract-execution",
                "/inventory/reports/subcontract-inout-detail",
                "/inventory/reports/subcontract-variance",
                "/inventory/reports/subcontract-payable-reconcile",
            }
            if path in subcontract_inventory_report_paths and not _current_role_allowed("admin", "manager", "purchase", "finance"):
                return _forbidden()

        if method == "POST":
            finance_action_prefixes = (
                "/sales/",
                "/purchase_order/",
            )
            finance_action_suffixes = (
                "/receive-payment",
                "/pay",
            )
            if path.startswith(finance_action_prefixes) and path.endswith(finance_action_suffixes):
                if _current_role_allowed("admin", "manager", "finance"):
                    return None
                return _forbidden()

        if nav_mode in PILOT_NAV_MODES and method == "POST" and path.startswith("/sales/"):
            sales_action_suffixes = ("/submit", "/ship", "/notes")
            if path.endswith(sales_action_suffixes):
                if _current_role_allowed("admin", "manager", "sales"):
                    return None
                return _forbidden()

        if method == "POST" and path in {"/shipments/new", "/sales-returns/new"}:
            if _current_role_allowed("admin", "manager", "sales"):
                return None
            return _forbidden()

        if method == "POST" and path in {"/purchase_receipts/new", "/purchase-returns/new"}:
            if _current_role_allowed("admin", "manager", "purchase", "warehouse"):
                return None
            return _forbidden()

        if nav_mode in PILOT_NAV_MODES and _is_pilot_scope_path(path):
            allowed_paths = _pilot_allowed_paths_for_role(session.get("role"))
            if not _path_matches(path, allowed_paths):
                return _forbidden()

        if path.startswith(("/users", "/permissions", "/operation_logs", "/system_settings", "/security", "/monitoring")):
            if not _current_role_allowed("admin", "manager"):
                return _forbidden()

        if path.startswith("/system/"):
            if not _current_role_allowed("admin", "manager"):
                return _forbidden()

        if path.startswith("/finance/cash-bank/"):
            if not _current_role_allowed("admin", "manager", "finance"):
                return _forbidden()

        # Guard production completion posting and reversal with explicit route handling.
        if method == "POST" and path.startswith("/production-completions/") and path.endswith(("/post", "/reverse")):
            if not _current_role_allowed("admin", "manager", "production"):
                return _forbidden()

        # Register purchase and production document routes after shared services are available.
        if method == "POST" and path.startswith("/subcontract_receive/") and path.endswith("/post"):
            if not _current_role_allowed("admin", "manager", "purchase", "production"):
                return _forbidden()

        if path in {"/finance/period-close", "/finance/exchange-adjustment", "/finance/exchange-adjustments"} or path.startswith("/finance/exchange-adjustments/"):
            if not _current_role_allowed("admin", "manager", "finance"):
                return _forbidden()

        if method == "POST" and path in {"/adjustments/new", "/transfers/new", "/assembly-orders/new", "/disassembly-orders/new"}:
            if not _current_role_allowed("admin", "manager", "warehouse"):
                return _forbidden()

        if method == "POST" and path == "/inventory/bulk-action":
            if not _current_role_allowed("admin", "manager", "warehouse"):
                return _forbidden()

        if method == "GET" and path == "/adjustments/new":
            if not _current_role_allowed("admin", "manager", "warehouse", "finance"):
                return _forbidden()

        if method == "GET" and path in {"/assembly-orders/new", "/disassembly-orders/new"}:
            if not _current_role_allowed("admin", "manager", "purchase", "warehouse", "production", "finance"):
                return _forbidden()

        inventory_post_prefixes = (
            "/adjustments/",
            "/transfers/",
            "/inventory_checks/",
            "/assembly-orders/",
            "/disassembly-orders/",
            "/sales-returns/",
            "/purchase-returns/",
        )
        if method == "POST" and path.startswith(inventory_post_prefixes) and path.endswith("/post"):
            if not _current_role_allowed("admin", "manager", "warehouse"):
                return _forbidden()

        inventory_close_prefixes = (
            "/adjustments/",
            "/transfers/",
            "/inventory_checks/",
            "/assembly-orders/",
            "/disassembly-orders/",
            "/sales-returns/",
            "/purchase-returns/",
        )
        if method == "POST" and path.startswith(inventory_close_prefixes) and path.endswith("/close"):
            if not _current_role_allowed("admin", "manager", "warehouse"):
                return _forbidden()

        inventory_cancel_prefixes = (
            "/adjustments/",
            "/transfers/",
            "/inventory_checks/",
            "/assembly-orders/",
            "/disassembly-orders/",
            "/sales-returns/",
            "/purchase-returns/",
        )
        if method == "POST" and path.startswith(inventory_cancel_prefixes) and path.endswith("/cancel"):
            if not _current_role_allowed("admin", "manager", "warehouse"):
                return _forbidden()

        if method == "POST" and (path.endswith("/void") or "/delete" in path or path.endswith("/delete")):
            if not _current_role_allowed("admin", "manager"):
                return _forbidden()
        return None

    login_required = create_login_required(is_logged_in)
    role_required = create_role_required(has_any_role)
    register_template_helpers(app)
    is_visible_for_roles = create_visibility_checker(has_any_role)

    def ensure_inventory(product_id, quantity, unit_cost, location, reorder_level):
        svc_ensure_inventory(query_db, execute_db, product_id, quantity, unit_cost, location, reorder_level)

    ensure_document_sequence_schema(execute_db)

    def next_doc_no(prefix, table, field="order_no"):
        return svc_get_next_doc_no(query_db, prefix, table, field, execute_and_return=execute_and_return, scope=f"{table}.{field}")

    def log_action(action, target="", remark=""):
        trace_id = getattr(g, "trace_id", None) or uuid.uuid4().hex
        g.trace_id = trace_id
        execute_db(
            """
            INSERT INTO operation_logs
                (user_id, username, action, target, remark, request_path, request_method, remote_addr, user_agent, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session.get("user_id"),
                session.get("username", ""),
                action,
                target,
                remark,
                request.path,
                request.method,
                request.headers.get("X-Forwarded-For", request.remote_addr or ""),
                request.headers.get("User-Agent", ""),
                trace_id,
            ),
        )

    def _inventory_outbound(product_id, quantity, location="", reference_no="", remark="", tx_date=None, tx_type="\u51fa\u5e93", lot_no="", cabinet_no=""):
        inventory_outbound(query_db, execute_db, product_id, quantity, location, reference_no, remark, tx_date, tx_type, lot_no, cabinet_no)

    def _inventory_inbound_weighted_avg(product_id, quantity, unit_cost, location="", reference_no="", remark="", tx_date=None, tx_type="\u5165\u5e93", lot_no="", cabinet_no=""):
        inventory_inbound_weighted_avg(query_db, execute_db, product_id, quantity, unit_cost, location, reference_no, remark, tx_date, tx_type, lot_no, cabinet_no)

    def _post_inventory_receipt(product_id, quantity, unit_cost, tx_date, tx_type, reference_no="", remark=""):
        post_inventory_receipt(query_db, execute_db, product_id, quantity, unit_cost, tx_date, tx_type, reference_no, remark)

    def _post_inventory_issue(product_id, quantity, tx_date, tx_type, reference_no="", remark=""):
        post_inventory_issue(query_db, execute_db, product_id, quantity, tx_date, tx_type, reference_no, remark)

    def initialize_database(force=False):
        return runtime_initialize_database(BASE_DIR, get_db_config(), generate_password_hash, force)


    if app.config["INIT_DATABASE_ON_CREATE"]:
        with app.app_context():
            initialize_database(False)


    register_help_routes(
        app,
        {
            "login_required": login_required,
        },
    )

    register_app_shell_routes(
        app,
        {
            "query_db": query_db,
            "execute_db": execute_db,
            "login_required": login_required,
            "is_logged_in": is_logged_in,
            "normalize_role": normalize_role,
            "pilot_allowed_paths_for_role": _pilot_allowed_paths_for_role,
            "path_matches": _path_matches,
            "csrf": csrf,
            "login_attempt_tracker": app.extensions["login_attempt_tracker"],
            "login_rate_limiter": app.extensions["login_rate_limiter"],
        },
    )

    register_core_operations_routes(
        app,
        {
            "query_db": query_db,
            "execute_db": execute_db,
            "execute_and_return": execute_and_return,
            "log_action": log_action,
            "login_required": login_required,
            "require_date": require_date,
            "to_positive_float": to_positive_float,
            "to_non_negative_float": to_non_negative_float,
            "ensure_inventory": ensure_inventory,
            "next_doc_no": next_doc_no,
            "inventory_outbound": _inventory_outbound,
            "inventory_inbound_weighted_avg": _inventory_inbound_weighted_avg,
            "record_stock_transaction": record_stock_transaction,
        },
    )

    register_system_management_routes(
        app,
        {
            "query_db": query_db,
            "execute_db": execute_db,
            "execute_and_return": execute_and_return,
            "log_action": log_action,
            "login_required": login_required,
            "role_required": role_required,
            "csrf": csrf,
            "has_any_role": has_any_role,
            "get_import_config": lambda import_type: get_import_config(import_type) or abort(404),
            "get_import_items": get_import_items,
            "get_import_groups": get_import_groups,
            "get_export_config": get_export_config,
            "get_export_groups": get_export_groups,
            "get_export_items_by_format": get_export_items_by_format,
            "get_system_top_cards": lambda: get_system_top_cards(is_visible_for_roles),
            "get_system_shortcuts": get_system_shortcuts,
            "get_system_admin_actions": lambda: get_system_admin_actions(is_visible_for_roles),
            "build_database_info": build_database_info,
            "ensure_inventory": ensure_inventory,
            "next_doc_no": next_doc_no,
            "initialize_database": initialize_database,
            "post_inventory_receipt": _post_inventory_receipt,
            "post_inventory_issue": _post_inventory_issue,
            "generate_password_hash": generate_password_hash,
            "pg_host": PG_HOST,
            "pg_port": PG_PORT,
            "pg_database": PG_DATABASE,
        },
    )
    register_print_template_routes(
        app,
        {
            "query_db": query_db,
            "execute_db": execute_db,
            "execute_and_return": execute_and_return,
            "log_action": log_action,
            "login_required": login_required,
            "role_required": role_required,
        },
    )

    bind_route_dependencies(
        {
            "query_db": query_db,
            "get_db": _get_db,
            "execute_db": execute_db,
            "execute_and_return": execute_and_return,
            "log_action": log_action,
            "login_required": login_required,
            "role_required": role_required,
            "has_any_role": has_any_role,
            "init_database_on_create": app.config["INIT_DATABASE_ON_CREATE"],
            "next_doc_no": next_doc_no,
            "inventory_outbound": inventory_outbound,
            "inventory_inbound_weighted_avg": inventory_inbound_weighted_avg,
            "record_stock_transaction": record_stock_transaction,
        }
    )

    register_api_routes(
        app,
        {
            "query_db": query_db,
            "login_required": login_required,
        },
    )

    register_finance_routes(
        app,
        {
            "query_db": query_db,
            "execute_db": execute_db,
            "execute_and_return": execute_and_return,
            "next_doc_no": next_doc_no,
            "log_action": log_action,
            "login_required": login_required,
        },
    )
    register_project_cost_routes(
        app,
        {
            "query_db": query_db,
            "login_required": login_required,
        },
    )
    register_project_delivery_workbench_routes(
        app,
        {
            "query_db": query_db,
            "login_required": login_required,
        },
    )
    register_attachment_routes(
        app,
        {
            "query_db": query_db,
            "login_required": login_required,
        },
    )
    register_sales_report_routes(
        app,
        {
            "query_db": query_db,
            "login_required": login_required,
            "role_required": role_required,
        },
    )
    register_invoice_matching_routes(
        app,
        query_db,
        login_required,
    )
    register_invoice_red_flush_routes(
        app,
        query_db,
        execute_db,
        login_required,
        get_db=_get_db,
        role_required=role_required,
    )
    register_invoice_reconciliation_routes(
        app,
        query_db,
        login_required,
    )
    # FIXED 20260617: Commented out to avoid route conflicts with finance_routes.py
    # register_voucher_routes(
    #     app,
    #     query_db,
    #     execute_db,
    #     login_required,
    # )
    # B-001: re-enabled; the duplicate /finance/reports/account-balance route
    # inside general_ledger_routes.py is commented out to avoid overriding
    # finance_routes.py:7572 which already serves that path.
    register_general_ledger_routes(
        app,
        query_db,
        login_required,
    )
    register_inventory_costing_routes(
        app,
        query_db,
        execute_db,
        login_required,
    )
    # B-001: re-enabled; the duplicate /finance/project-cost/detail route
    # inside project_cost_reports_routes.py is commented out to avoid
    # overriding project_cost_routes.py:535 which already serves that path.
    register_project_cost_reports_routes(
        app,
        query_db,
        execute_db,
        login_required,
    )
    register_cabinet_cost_routes(
        app,
        query_db,
        execute_db,
        login_required,
    )
    # Integration contract marker: register_period_closing_routes(app)
    register_period_closing_routes(
        app,
        query_db,
        execute_db,
        login_required,
        get_db=_get_db,
    )
    # Integration contract marker: register_financial_report_routes(app)
    register_financial_report_routes(
        app,
        query_db,
        execute_db,
        login_required,
    )

    # P0 首期核心引擎路由注册
    _p0_deps = {
        "query_db": query_db,
        "execute_db": execute_db,
        "execute_and_return": execute_and_return,
        "login_required": login_required,
        "log_action": log_action,
    }
    register_trace_routes(app, _p0_deps)
    register_bom_version_routes(app, _p0_deps)
    register_mrp_routes(app, _p0_deps)
    register_cost_engine_routes(app, _p0_deps)
    register_data_permission_routes(app, _p0_deps)

    register_blueprints(app)

    # 注册新增的 Blueprint
    app.register_blueprint(notification_bp)

    # 注册安全管理 Blueprint
    app.register_blueprint(security_bp)

    # 注册系统监控 Blueprint
    app.register_blueprint(monitoring_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    default_host = os.environ.get("ERP_HOST", "127.0.0.1")
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host=os.environ.get("FLASK_RUN_HOST", default_host), port=5000)
