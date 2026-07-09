import csv
import io
import os
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Response, g, has_app_context, redirect, request, session, url_for
from services.schema_migrations import apply_schema_migrations
from services.transaction_utils import db_transaction, execute_in_transaction
from services.update_service import get_update_status


FULL_NAV_MODES = {"full", "all"}

ROLE_LABELS = {
    "admin": "管理员",
    "manager": "经理",
    "sales": "销售",
    "purchase": "采购",
    "warehouse": "仓库",
    "production": "生产",
    "service": "售后",
    "finance": "财务",
    "staff": "员工",
}

ERP_FIELD_LABELS = {
    "id": "ID",
    "code": "编码",
    "name": "名称",
    "no": "编号",
    "doc_no": "单据编号",
    "document_no": "单据编号",
    "order_no": "订单编号",
    "request_no": "申请编号",
    "receipt_no": "收款单号",
    "payment_no": "付款单号",
    "invoice_no": "发票编号",
    "shipment_no": "发货单号",
    "return_no": "退货单号",
    "issue_no": "发料单号",
    "receive_no": "收货单号",
    "wo_no": "工单编号",
    "bom_no": "BOM编号",
    "ecn_no": "ECN编号",
    "project_code": "项目号",
    "serial_no": "机号",
    "status": "状态",
    "status_label": "状态",
    "doc_status": "单据状态",
    "source_type": "来源类型",
    "source_no": "来源单号",
    "source_doc_no": "来源单据",
    "partner": "往来单位",
    "partner_name": "往来单位",
    "customer": "客户",
    "customer_id": "客户",
    "customer_name": "客户",
    "supplier": "供应商",
    "supplier_id": "供应商",
    "supplier_name": "供应商",
    "processor_name": "加工商",
    "product": "物料",
    "product_id": "物料",
    "product_code": "物料编码",
    "product_name": "物料名称",
    "material_code": "物料编码",
    "material_name": "物料名称",
    "spec": "规格",
    "specification": "规格",
    "unit": "单位",
    "unit_name": "单位",
    "warehouse": "仓库",
    "warehouse_id": "仓库",
    "warehouse_name": "仓库",
    "location": "库位",
    "location_id": "库位",
    "location_name": "库位",
    "quantity": "数量",
    "qty": "数量",
    "price": "单价",
    "unit_price": "单价",
    "amount": "金额",
    "total_amount": "合计金额",
    "amount_with_tax": "含税金额",
    "tax_amount": "税额",
    "balance": "余额",
    "remark": "备注",
    "description": "说明",
    "owner": "责任人",
    "owner_role": "责任角色",
    "next_step": "下一步",
    "next_action": "下一步",
    "blocked_reason": "阻断原因",
    "downstream_impact": "下游影响",
    "created_by": "创建人",
    "created_at": "创建时间",
    "updated_by": "更新人",
    "updated_at": "更新时间",
    "date": "日期",
    "doc_date": "单据日期",
    "order_date": "订单日期",
    "delivery_date": "交期",
    "due_date": "到期日",
}

ERP_VALUE_LABELS = {
    "active": "启用",
    "inactive": "停用",
    "enabled": "启用",
    "disabled": "停用",
    "normal": "正常",
    "draft": "草稿",
    "pending": "待处理",
    "submitted": "已提交",
    "approved": "已审核",
    "audited": "已审核",
    "rejected": "已驳回",
    "completed": "已完成",
    "closed": "已关闭",
    "cancelled": "已取消",
    "canceled": "已取消",
    "void": "已作废",
    "voided": "已作废",
    "posted": "已过账",
    "unposted": "未过账",
    "processing": "处理中",
    "open": "未关闭",
    "partial": "部分完成",
    "pass": "合格",
    "conditional_pass": "让步放行",
    "fail": "不合格",
    "manual": "手工",
    "yes": "是",
    "no": "否",
    "true": "是",
    "false": "否",
    "customer": "客户",
    "supplier": "供应商",
    "material": "物料",
    "document": "单据",
    "receivable": "应收",
    "payable": "应付",
    "customer_receipt": "\u5ba2\u6237\u6536\u6b3e\u5355",
    "supplier_payment": "\u4f9b\u5e94\u5546\u4ed8\u6b3e\u5355",
    "sales_order": "\u9500\u552e\u8ba2\u5355",
    "purchase_order": "\u91c7\u8d2d\u8ba2\u5355",
    "purchase_receipt": "\u91c7\u8d2d\u6536\u8d27\u5355",
    "sales_shipment": "\u9500\u552e\u53d1\u8d27\u5355",
    "work_order": "\u751f\u4ea7\u5de5\u5355",
    "subcontract_order": "\u59d4\u5916\u8ba2\u5355",
    "subcontract_issue": "\u59d4\u5916\u53d1\u6599\u5355",
    "subcontract_receive": "\u59d4\u5916\u6536\u8d27\u5355",
}


def erp_label(value):
    text = str(value or "").strip()
    if not text:
        return ""
    return ERP_FIELD_LABELS.get(text, text.replace("_", " "))


def erp_value(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return ERP_VALUE_LABELS.get(text.lower(), text)


def _read_package_info():
    package_info = {
        "build": os.environ.get("ERP_BUILD", "local"),
        "name": os.environ.get("ERP_PACKAGE_NAME", "local runtime"),
    }
    info_path = os.environ.get("ERP_PACKAGE_INFO")
    paths = []
    if info_path:
        paths.append(info_path)
    paths.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "PACKAGE_INFO.txt"))
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                lines = [line.strip() for line in handle if line.strip()]
        except OSError:
            continue
        if lines:
            package_info["name"] = lines[0]
        for line in lines:
            if line.startswith("built_at="):
                package_info["build"] = line.split("=", 1)[1].strip() or package_info["build"]
        break
    return package_info


def connect_db(db_config, cursor_factory=RealDictCursor):
    return psycopg2.connect(
        host=db_config["host"],
        port=db_config["port"],
        dbname=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
        cursor_factory=cursor_factory,
        connect_timeout=int(os.environ.get("PG_CONNECT_TIMEOUT", "5")),
        client_encoding="UTF8",
        options="-c client_encoding=utf8",
    )


def create_db_helpers(app, db_config):
    def get_db(cursor_factory=RealDictCursor):
        if not has_app_context():
            return connect_db(db_config, cursor_factory=cursor_factory)
        cache_key = "_db_conn_real_dict" if cursor_factory is RealDictCursor else "_db_conn_plain"
        conn = getattr(g, cache_key, None)
        if conn is None or conn.closed:
            conn = connect_db(db_config, cursor_factory=cursor_factory)
            setattr(g, cache_key, conn)
        return conn

    @app.teardown_appcontext
    def close_db_connections(exc=None):
        for cache_key in ("_db_conn_real_dict", "_db_conn_plain"):
            conn = getattr(g, cache_key, None)
            if conn is not None and not conn.closed:
                conn.close()

    def query_db(sql, params=None, one=False):
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            if one:
                return rows[0] if rows else None
            return rows

    def execute_db(sql, params=None):
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()

    def execute_and_return(sql, params=None):
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
        conn.commit()
        return row

    def transaction(cursor_factory=RealDictCursor):
        return db_transaction(get_db, cursor_factory=cursor_factory)

    def run_in_transaction(operations, cursor_factory=RealDictCursor):
        return execute_in_transaction(get_db, operations, cursor_factory=cursor_factory)

    app.extensions["db_transaction"] = transaction
    app.extensions["run_in_transaction"] = run_in_transaction

    return get_db, query_db, execute_db, execute_and_return


def create_login_required(is_logged_in):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_logged_in():
                return redirect(url_for("login", next=request.path))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def create_role_required(has_any_role):
    def decorator(*roles):
        def outer(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not has_any_role(*roles):
                    return ("Forbidden", 403)
                return func(*args, **kwargs)

            return wrapper

        return outer

    return decorator


def create_visibility_checker(has_any_role):
    def is_visible_for_roles(*roles):
        return has_any_role(*roles) if roles else True

    return is_visible_for_roles


class CurrentUser:
    @property
    def id(self):
        return session.get("user_id")

    @property
    def username(self):
        return session.get("username", "")

    @property
    def role(self):
        return session.get("role", "staff")

    @property
    def display_name(self):
        return session.get("full_name") or session.get("username") or ""

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    def has_role(self, *roles):
        return self.role in roles

    @property
    def is_authenticated(self):
        return bool(session.get("user_id"))


def register_context_processors(app):
    @app.context_processor
    def inject_runtime_context():
        nav_mode = os.environ.get("INVENTORY_NAV_MODE", "small_factory").strip().lower()
        return {
            "current_user": CurrentUser(),
            "nav_mode": nav_mode,
            "small_factory_nav": nav_mode not in FULL_NAV_MODES,
            "location_management_enabled": True,
            "topbar_release_info": _read_package_info(),
            "topbar_update_status": get_update_status(),
        }


def _decimal_for_display(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").strip() or "0")
    except Exception:
        return Decimal("0")


def _format_money(value):
    number = _decimal_for_display(value)
    if number is None:
        number = Decimal("0")
    return f"{number:,.2f}"


def _format_decimal(value):
    number = _decimal_for_display(value)
    if number is None:
        return ""
    return f"{number:.2f}".rstrip("0").rstrip(".")


def register_template_helpers(app):
    app.jinja_env.filters["money"] = _format_money
    app.jinja_env.filters["money_fmt"] = app.jinja_env.filters["money"]
    app.jinja_env.filters["currency_cn"] = app.jinja_env.filters["money"]
    app.jinja_env.filters["qty"] = _format_decimal
    app.jinja_env.filters["erp_label"] = erp_label
    app.jinja_env.filters["erp_value"] = erp_value
    app.jinja_env.globals["today"] = date.today


def require_date(value, field_name="date"):
    if not value:
        raise ValueError(f"{field_name} is required")
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def to_positive_float(value, field_name="quantity"):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if number <= 0:
        raise ValueError(f"{field_name} must be positive")
    return number


def to_non_negative_float(value, field_name="amount"):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def rows_to_csv_response(rows, filename):
    output = io.StringIO()
    writer = csv.writer(output)
    rows = list(rows or [])
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow([row.get(key) for key in row.keys()])
    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def initialize_database(base_dir, db_config, generate_password_hash, force=False):
    conn = connect_db(db_config=db_config, cursor_factory=None)
    try:
        with conn.cursor() as cur:
            apply_schema_migrations(cur)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(120),
                    role VARCHAR(50) DEFAULT 'admin',
                    status VARCHAR(50) DEFAULT 'normal',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'normal'")
            cur.execute("UPDATE users SET status='normal' WHERE status IS NULL OR status=''")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS login_attempts (
                    username VARCHAR(80) PRIMARY KEY,
                    failures INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS document_sequences (
                    prefix VARCHAR(40) NOT NULL,
                    scope VARCHAR(80) NOT NULL DEFAULT '',
                    last_value INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (prefix, scope)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_windows (
                    limiter_key VARCHAR(160) NOT NULL,
                    window_start BIGINT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (limiter_key, window_start)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subcontract_orders (
                    id SERIAL PRIMARY KEY,
                    order_no VARCHAR(80) UNIQUE,
                    order_date DATE DEFAULT CURRENT_DATE,
                    supplier_id INTEGER,
                    product_id INTEGER,
                    quantity NUMERIC(14, 3) DEFAULT 0,
                    unit_price NUMERIC(14, 4) DEFAULT 0,
                    total_amount NUMERIC(14, 2) DEFAULT 0,
                    project_code VARCHAR(120),
                    serial_no VARCHAR(120),
                    status VARCHAR(50) DEFAULT '新建',
                    remark TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subcontract_issue_orders (
                    id SERIAL PRIMARY KEY,
                    issue_no VARCHAR(80) UNIQUE,
                    date DATE DEFAULT CURRENT_DATE,
                    subcontract_order_id INTEGER,
                    supplier_id INTEGER,
                    status VARCHAR(50) DEFAULT 'pending',
                    total_quantity NUMERIC(14, 3) DEFAULT 0,
                    remark TEXT,
                    operator_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subcontract_receive_orders (
                    id SERIAL PRIMARY KEY,
                    receive_no VARCHAR(80) UNIQUE,
                    date DATE DEFAULT CURRENT_DATE,
                    subcontract_order_id INTEGER,
                    supplier_id INTEGER,
                    status VARCHAR(50) DEFAULT 'pending',
                    total_quantity NUMERIC(14, 3) DEFAULT 0,
                    total_scrap NUMERIC(14, 3) DEFAULT 0,
                    remark TEXT,
                    operator_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "INSERT INTO users (username, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
                    ("admin", generate_password_hash("admin"), "Administrator", "admin"),
                )
        conn.commit()
    finally:
        conn.close()
