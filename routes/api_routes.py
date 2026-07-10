"""API routes: JSON API endpoints for frontend data fetching and lookups."""
from datetime import date, datetime
from decimal import Decimal
import re

from flask import Blueprint, jsonify, request, session

from services.data_scope_service import (
    build_scope_filter,
    get_data_scope,
    scope_has_rules,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")


def register_api_routes(app, deps):
    query_db = deps["query_db"]
    login_required = deps.get("login_required")

    @api_bp.before_request
    def require_api_login():
        if request.path in {"/api/health", "/api/version"}:
            return None
        if login_required and not session.get("user_id"):
            return jsonify({"ok": False, "error": "authentication required"}), 401
        return None

    def _current_scope(permission="view"):
        return get_data_scope(
            query_db,
            user_id=session.get("user_id"),
            role=session.get("role", "staff"),
            permission=permission,
        )

    def scalar(sql, params=None):
        row = query_db(sql, params or (), one=True)
        return next(iter(row.values())) if row else None

    def table_columns(table):
        rows = query_db(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            """,
            (table,),
        )
        return {row["column_name"] for row in rows}

    def table_exists(table):
        return bool(
            scalar(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema='public' AND table_name=%s
                """,
                (table,),
            )
        )

    def serialize(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return value

    def serialize_row(row):
        return {key: serialize(value) for key, value in dict(row).items()}

    def paged_response(rows, total, page, page_size):
        return jsonify(
            {
                "ok": True,
                "page": page,
                "page_size": page_size,
                "total": int(total or 0),
                "items": [serialize_row(row) for row in rows],
            }
        )

    def paging():
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            page = 1
        try:
            page_size = int(request.args.get("page_size", "50"))
        except ValueError:
            page_size = 50
        page_size = min(max(page_size, 1), 200)
        return page, page_size, (page - 1) * page_size

    def list_endpoint(table, columns, search_columns=(), order_by="id DESC", joins="", base_where="TRUE", scope_field_map=None):
        if not table_exists(table):
            return jsonify({"ok": False, "error": f"table {table} is not initialized"}), 503
        # Order expressions are fixed route constants and allow identifier lists only.
        _order_re = re.compile(
            r"^[A-Za-z_][A-Za-z0-9_\.]*(\s+(ASC|DESC))?(\s+NULLS\s+(FIRST|LAST))?"
            r"(\s*,\s*[A-Za-z_][A-Za-z0-9_\.]*(\s+(ASC|DESC))?(\s+NULLS\s+(FIRST|LAST))?)*$",
            re.IGNORECASE,
        )
        if not _order_re.match(order_by):
            return jsonify({"ok": False, "error": "invalid order_by"}), 500
        page, page_size, offset = paging()
        keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
        status = (request.args.get("status") or "").strip()
        where = [base_where]
        params = []
        if keyword and search_columns:
            where.append("(" + " OR ".join(f"{column} ILIKE %s" for column in search_columns) + ")")
            params.extend([f"%{keyword}%"] * len(search_columns))
        if status and "status" in table_columns(table):
            where.append(f"{table}.status=%s")
            params.append(status)
        # Apply data-scope filtering so API access cannot bypass the same
        # row-level restrictions enforced on the web UI.
        if scope_field_map:
            scope_clause, scope_params = build_scope_filter(
                _current_scope("view"), scope_field_map, params=tuple(params)
            )
            if scope_clause:
                where.append(scope_clause.lstrip(" AND "))
                params = list(scope_params)
        where_sql = " AND ".join(where)
        select_sql = ", ".join(columns)
        total_row = query_db(f"SELECT COUNT(*) AS total FROM {table} {joins} WHERE {where_sql}", tuple(params), one=True)
        rows = query_db(
            f"""
            SELECT {select_sql}
            FROM {table}
            {joins}
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
            """,
            tuple(params + [page_size, offset]),
        )
        return paged_response(rows, total_row.get("total") if total_row else 0, page, page_size)

    def get_endpoint(table, columns, record_id, joins="", id_column=None, scope_field_map=None):
        if not table_exists(table):
            return jsonify({"ok": False, "error": f"table {table} is not initialized"}), 503
        id_column = id_column or f"{table}.id"
        row = query_db(
            f"SELECT {', '.join(columns)} FROM {table} {joins} WHERE {id_column}=%s",
            (record_id,),
            one=True,
        )
        if not row:
            return jsonify({"ok": False, "error": "not found"}), 404
        # Enforce row-level scope on single-record access too.
        if scope_field_map:
            scope = _current_scope("view")
            if scope_has_rules(scope):
                from services.data_scope_service import row_allowed
                if not row_allowed(scope, row, scope_field_map):
                    return jsonify({"ok": False, "error": "forbidden by data scope"}), 403
        return jsonify({"ok": True, "item": serialize_row(row)})

    @api_bp.get("/health")
    def health():
        row = query_db("SELECT 1 AS ok, now() AS checked_at", one=True)
        return jsonify(
            {
                "ok": True,
                "checked_at": row.get("checked_at").isoformat() if row and row.get("checked_at") else datetime.now().isoformat(),
            }
        )

    @api_bp.get("/version")
    def version():
        return jsonify({"ok": True, "name": "wms-erp", "api": "v1"})

    @api_bp.get("/v1/materials")
    def materials():
        return list_endpoint(
            "products",
            [
                "products.id",
                "products.code",
                "products.name",
                "products.specification",
                "products.unit",
                "products.status",
                "products.standard_price",
                "products.safety_stock",
            ],
            ("products.code", "products.name", "products.specification"),
            "products.id DESC",
        )

    @api_bp.get("/v1/materials/<int:record_id>")
    def material_detail(record_id):
        return get_endpoint(
            "products",
            [
                "products.id",
                "products.code",
                "products.name",
                "products.specification",
                "products.unit",
                "products.status",
                "products.standard_price",
                "products.safety_stock",
                "products.drawing_no",
                "products.material_grade",
                "products.brand",
            ],
            record_id,
        )

    @api_bp.get("/v1/customers")
    def customers():
        return list_endpoint(
            "customers",
            ["customers.id", "customers.name", "customers.contact_person", "customers.phone", "customers.customer_level"],
            ("customers.name", "customers.contact_person", "customers.phone"),
            "customers.id DESC",
        )

    @api_bp.get("/v1/suppliers")
    def suppliers():
        return list_endpoint(
            "suppliers",
            ["suppliers.id", "suppliers.name", "suppliers.contact_person", "suppliers.phone"],
            ("suppliers.name", "suppliers.contact_person", "suppliers.phone"),
            "suppliers.id DESC",
        )

    @api_bp.get("/v1/inventory-balances")
    def inventory_balances():
        return list_endpoint(
            "inventory_balances",
            [
                "inventory_balances.id",
                "inventory_balances.product_id",
                "p.code AS product_code",
                "p.name AS product_name",
                "p.specification",
                "inventory_balances.warehouse_id",
                "w.name AS warehouse_name",
                "inventory_balances.location_id",
                "l.code AS location_code",
                "inventory_balances.quantity",
                "inventory_balances.locked_qty",
                "inventory_balances.unit_cost",
                "inventory_balances.lot_no",
                "inventory_balances.cabinet_no",
                "inventory_balances.updated_at",
            ],
            ("p.code", "p.name", "p.specification", "w.name", "l.code", "inventory_balances.lot_no", "inventory_balances.cabinet_no"),
            "inventory_balances.updated_at DESC NULLS LAST, inventory_balances.id DESC",
            "LEFT JOIN products p ON p.id=inventory_balances.product_id LEFT JOIN warehouses w ON w.id=inventory_balances.warehouse_id LEFT JOIN locations l ON l.id=inventory_balances.location_id",
        )

    @api_bp.get("/v1/sales-orders")
    def sales_orders():
        return list_endpoint(
            "sales_orders",
            [
                "sales_orders.id",
                "sales_orders.order_no",
                "sales_orders.order_date",
                "c.name AS customer_name",
                "sales_orders.project_code",
                "sales_orders.cabinet_no",
                "sales_orders.status",
                "sales_orders.total_amount",
                "sales_orders.amount_with_tax",
                "sales_orders.shipped_amount",
            ],
            ("sales_orders.order_no", "c.name", "sales_orders.project_code", "sales_orders.cabinet_no"),
            "sales_orders.id DESC",
            "LEFT JOIN customers c ON c.id=sales_orders.customer_id",
            scope_field_map={"project": "sales_orders.project_code", "cabinet": "sales_orders.cabinet_no", "customer": "sales_orders.customer_id"},
        )

    @api_bp.get("/v1/sales-orders/<int:record_id>")
    def sales_order_detail(record_id):
        return get_endpoint(
            "sales_orders",
            [
                "sales_orders.id",
                "sales_orders.order_no",
                "sales_orders.order_date",
                "sales_orders.customer_id",
                "sales_orders.project_code",
                "sales_orders.cabinet_no",
                "sales_orders.status",
                "sales_orders.total_amount",
                "sales_orders.amount_with_tax",
                "sales_orders.shipped_amount",
            ],
            record_id,
            scope_field_map={"project": "project_code", "cabinet": "cabinet_no", "customer": "customer_id"},
        )

    @api_bp.get("/v1/purchase-orders")
    def purchase_orders():
        return list_endpoint(
            "purchase_orders",
            [
                "purchase_orders.id",
                "purchase_orders.order_no",
                "purchase_orders.order_date",
                "s.name AS supplier_name",
                "purchase_orders.project_code",
                "purchase_orders.cabinet_no",
                "purchase_orders.status",
                "purchase_orders.total_amount",
                "purchase_orders.amount_with_tax",
                "purchase_orders.received_amount",
                "COALESCE(items.received_qty, 0) AS received_qty",
                "COALESCE(items.pending_receive_qty, 0) AS pending_receive_qty",
                "COALESCE(ap.payable_balance, 0) AS payable_balance",
            ],
            ("purchase_orders.order_no", "s.name", "purchase_orders.project_code", "purchase_orders.cabinet_no"),
            "purchase_orders.id DESC",
            """
            LEFT JOIN suppliers s ON s.id=purchase_orders.supplier_id
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(received_qty), 0) AS received_qty,
                       COALESCE(SUM(GREATEST(COALESCE(quantity,0)-COALESCE(received_qty,0),0)), 0) AS pending_receive_qty
                FROM purchase_order_items poi
                WHERE poi.order_id=purchase_orders.id
            ) items ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(balance), 0) AS payable_balance
                FROM supplier_payables sp
                WHERE sp.doc_id=purchase_orders.id OR sp.doc_no=purchase_orders.order_no
            ) ap ON TRUE
            """,
            scope_field_map={"project": "purchase_orders.project_code", "cabinet": "purchase_orders.cabinet_no", "supplier": "purchase_orders.supplier_id"},
        )

    @api_bp.get("/v1/purchase-orders/<int:record_id>")
    def purchase_order_detail(record_id):
        return get_endpoint(
            "purchase_orders",
            [
                "purchase_orders.id",
                "purchase_orders.order_no",
                "purchase_orders.order_date",
                "purchase_orders.supplier_id",
                "purchase_orders.project_code",
                "purchase_orders.cabinet_no",
                "purchase_orders.status",
                "purchase_orders.total_amount",
                "purchase_orders.amount_with_tax",
                "purchase_orders.received_amount",
            ],
            record_id,
            scope_field_map={"project": "project_code", "cabinet": "cabinet_no", "supplier": "supplier_id"},
        )

    @api_bp.get("/v1/receivables")
    def receivables():
        return list_endpoint(
            "customer_receivables",
            [
                "customer_receivables.id",
                "customer_receivables.source_no",
                "customer_receivables.receivable_date",
                "c.name AS customer_name",
                "customer_receivables.total_amount",
                "customer_receivables.received_amount",
                "customer_receivables.balance",
                "customer_receivables.status",
                "customer_receivables.project_code",
                "customer_receivables.cabinet_no",
            ],
            ("customer_receivables.source_no", "c.name", "customer_receivables.project_code", "customer_receivables.cabinet_no"),
            "customer_receivables.id DESC",
            "LEFT JOIN customers c ON c.id=customer_receivables.customer_id",
            scope_field_map={"project": "customer_receivables.project_code", "cabinet": "customer_receivables.cabinet_no", "customer": "customer_receivables.customer_id"},
        )

    @api_bp.get("/v1/receivables/<int:record_id>")
    def receivable_detail(record_id):
        return get_endpoint(
            "customer_receivables",
            [
                "customer_receivables.id",
                "customer_receivables.source_no",
                "customer_receivables.receivable_date",
                "customer_receivables.customer_id",
                "customer_receivables.total_amount",
                "customer_receivables.received_amount",
                "customer_receivables.balance",
                "customer_receivables.status",
                "customer_receivables.project_code",
                "customer_receivables.cabinet_no",
            ],
            record_id,
            scope_field_map={"project": "project_code", "cabinet": "cabinet_no", "customer": "customer_id"},
        )

    @api_bp.get("/v1/payables")
    def payables():
        return list_endpoint(
            "supplier_payables",
            [
                "supplier_payables.id",
                "supplier_payables.payable_no",
                "supplier_payables.doc_no",
                "supplier_payables.doc_date",
                "s.name AS supplier_name",
                "supplier_payables.amount",
                "supplier_payables.paid_amount",
                "supplier_payables.balance",
                "supplier_payables.status",
                "supplier_payables.next_follow_up_date",
            ],
            ("supplier_payables.payable_no", "supplier_payables.doc_no", "supplier_payables.source_no", "s.name"),
            "supplier_payables.id DESC",
            "LEFT JOIN suppliers s ON s.id=supplier_payables.supplier_id",
            scope_field_map={"supplier": "supplier_payables.supplier_id"},
        )

    @api_bp.get("/v1/payables/<int:record_id>")
    def payable_detail(record_id):
        return get_endpoint(
            "supplier_payables",
            [
                "supplier_payables.id",
                "supplier_payables.payable_no",
                "supplier_payables.doc_no",
                "supplier_payables.doc_date",
                "supplier_payables.supplier_id",
                "supplier_payables.amount",
                "supplier_payables.paid_amount",
                "supplier_payables.balance",
                "supplier_payables.status",
                "supplier_payables.next_follow_up_date",
            ],
            record_id,
            scope_field_map={"supplier": "supplier_id"},
        )

    @api_bp.get("/v1/financial-statements")
    def financial_statements():
        year = request.args.get("year", type=int) or date.today().year
        month = request.args.get("month", type=int) or date.today().month
        period = query_db("SELECT id, status FROM accounting_periods WHERE year=%s AND month=%s", (year, month), one=True)
        if not period:
            return jsonify({"ok": True, "period": f"{year:04d}-{month:02d}", "items": []})
        rows = query_db(
            """
            SELECT report_type, data, status, created_at
            FROM financial_reports
            WHERE period_id=%s
            ORDER BY report_type
            """,
            (period["id"],),
        )
        return jsonify(
            {
                "ok": True,
                "period": f"{year:04d}-{month:02d}",
                "period_status": period.get("status"),
                "items": [serialize_row(row) for row in rows],
            }
        )

    # ── Document navigation API ──
    # Returns first / prev / next / last record IDs for a given table.
    _NAV_TABLE_MAP = {
        "sales_orders": "sales_orders",
        "purchase_orders": "purchase_orders",
        "sales_shipments": "sales_shipments",
        "purchase_receipts": "purchase_receipts",
        "quotations": "quotations",
        "purchase_requisitions": "purchase_requisitions",
        "inventory_movements": "inventory_movements",
        "inventory_transfers": "inventory_transfers",
        "inventory_adjustments": "inventory_adjustments",
        "inventory_checks": "inventory_checks",
        "inventory_assembly_orders": "inventory_assembly_orders",
        "inventory_returns": "inventory_returns",
        "work_orders": "work_orders",
        "production_issues": "production_issues",
        "production_completions": "production_completions",
        "subcontract_orders": "subcontract_orders",
        "subcontract_issues": "subcontract_issues",
        "subcontract_receives": "subcontract_receives",
        "customer_receivables": "customer_receivables",
        "supplier_payables": "supplier_payables",
        "finance_funds": "finance_funds",
        "finance_vouchers": "finance_vouchers",
        "quality_inspections": "quality_inspection_records",
        "quality_inspection_records": "quality_inspection_records",
        "service_orders": "service_orders",
        "service_rmas": "service_rmas",
        "service_acceptances": "service_acceptances",
        "bom_ecn": "bom_engineering_changes",
        "purchase_requests": "purchase_requests",
        "supplier_quotes": "supplier_quotes",
        "sales_invoices": "sales_invoices",
        "purchase_invoices": "purchase_invoices",
        "operation_reports": "operation_reports",
        "production_routings": "production_routings",
        "product_configurations": "product_configurations",
        "bank_statements": "bank_statements",
        "work_centers": "work_centers",
        "engineering_drawings": "engineering_drawings",
        "engineering_technical_confirmations": "engineering_technical_confirmations",
    }

    @api_bp.get("/doc_nav/<table>/<int:doc_id>")
    def document_navigation(table, doc_id):
        import re as _re
        # Validate table name (only alphanumeric + underscore)
        if not _re.match(r"^[a-z_]+$", table):
            return jsonify({"ok": False, "error": "invalid table name"}), 400
        actual_table = _NAV_TABLE_MAP.get(table, table)
        if not table_exists(actual_table):
            return jsonify({"ok": False, "error": "table not found"}), 404

        cols = table_columns(actual_table)
        if "id" not in cols:
            return jsonify({"ok": False, "error": "table has no id column"}), 400

        first_row = query_db(
            f"SELECT id FROM {actual_table} ORDER BY id ASC LIMIT 1"
        )
        last_row = query_db(
            f"SELECT id FROM {actual_table} ORDER BY id DESC LIMIT 1"
        )
        prev_row = query_db(
            f"SELECT id FROM {actual_table} WHERE id < %s ORDER BY id DESC LIMIT 1",
            (doc_id,),
            one=True,
        )
        next_row = query_db(
            f"SELECT id FROM {actual_table} WHERE id > %s ORDER BY id ASC LIMIT 1",
            (doc_id,),
            one=True,
        )
        first_id = first_row[0]["id"] if first_row else None
        last_id = last_row[0]["id"] if last_row else None
        prev_id = prev_row["id"] if prev_row else None
        next_id = next_row["id"] if next_row else None
        return jsonify({
            "ok": True,
            "current": doc_id,
            "first": first_id,
            "prev": prev_id,
            "next": next_id,
            "last": last_id,
        })

    @api_bp.get("/entry_doc_nav/<kind>")
    def entry_document_navigation(kind):
        configs = {
            "inventory_inbound": {
                "table": "inventory_movement_documents",
                "base": "/inventory/inbound/",
                "value_field": "doc_no",
                "order_field": "id",
                "where": "direction=%s AND movement_kind=%s",
                "params": ("in", "other_inbound"),
            },
            "inventory_outbound": {
                "table": "inventory_movement_documents",
                "base": "/inventory/outbound/",
                "value_field": "doc_no",
                "order_field": "id",
                "where": "direction=%s AND movement_kind=%s",
                "params": ("out", "other_outbound"),
            },
            "purchase_request": {"table": "purchase_requisitions", "base": "/purchase_request/"},
            "purchase_order": {"table": "purchase_orders", "base": "/purchase_order/"},
            "purchase_receipt": {"table": "purchase_receipts", "base": "/purchase_receipts/"},
            "inventory_adjustment": {"table": "inventory_adjustments", "base": "/adjustments/"},
            "inventory_transfer": {"table": "transfer_orders", "base": "/transfers/"},
            "inventory_check": {"table": "inventory_check_orders", "base": "/inventory_checks/"},
            "assembly_order": {"table": "inventory_assembly_orders", "base": "/assembly-orders/"},
            "disassembly_order": {"table": "inventory_assembly_orders", "base": "/disassembly-orders/"},
        }
        config = configs.get(kind)
        if not config:
            return jsonify({"ok": False, "error": "unsupported document kind"}), 404
        table = config["table"]
        if not table_exists(table):
            return jsonify({"ok": False, "error": "table not found"}), 404
        if "id" not in table_columns(table):
            return jsonify({"ok": False, "error": "table has no id column"}), 400

        current_id = request.args.get("current_id", type=int)
        params = tuple(config.get("params") or ())
        where = config.get("where")
        group = config.get("group")
        value_field = config.get("value_field", "id")
        order_field = config.get("order_field", "id")
        where_sql = f"WHERE {where}" if where else ""
        if group:
            rows = query_db(
                f"""
                SELECT MIN(id) AS id, MIN({value_field}) AS value
                FROM {table}
                {where_sql}
                GROUP BY {group}
                ORDER BY MIN(id)
                """,
                params,
            )
        else:
            rows = query_db(
                f"SELECT id, {value_field} AS value FROM {table} {where_sql} ORDER BY {order_field}",
                params,
            )
        entries = [
            {"id": row["id"], "value": row.get("value") if row.get("value") is not None else row["id"]}
            for row in rows
            if row.get("id") is not None
        ]

        if not entries:
            return jsonify({"ok": True, "base": config["base"], "first": None, "prev": None, "next": None, "last": None})

        first_entry = entries[0]
        last_entry = entries[-1]
        current_value = (request.args.get("current_value") or "").strip()
        current_entry = None
        if current_value:
            current_entry = next((entry for entry in entries if str(entry["value"]) == current_value), None)
        if not current_entry and current_id:
            current_entry = next((entry for entry in entries if entry["id"] == current_id), None)
        if current_entry:
            current_index = entries.index(current_entry)
            prev_entry = entries[current_index - 1] if current_index > 0 else None
            next_entry = entries[current_index + 1] if current_index < len(entries) - 1 else None
        else:
            prev_entry = last_entry
            next_entry = None

        return jsonify({
            "ok": True,
            "base": config["base"],
            "first": first_entry["value"],
            "prev": prev_entry["value"] if prev_entry else None,
            "next": next_entry["value"] if next_entry else None,
            "last": last_entry["value"],
        })

    app.register_blueprint(api_bp)
