"""Lookup routes: JSON API endpoints for unit, warehouse, and material lookups."""
from flask import jsonify, request, url_for


def lookup_units(query_rows):
    rows = query_rows("SELECT id, code, name, category FROM units ORDER BY code LIMIT 200")
    return jsonify(rows)


def lookup_boms(query_rows):
    keyword = f"%{request.args.get('q', '').strip()}%"
    rows = query_rows(
        """
        SELECT b.id AS numeric_id, b.bom_no, b.version, b.status, p.code AS product_code, p.name AS product_name
        FROM boms b
        LEFT JOIN products p ON p.id=b.product_id
        WHERE %s='%%' OR b.bom_no ILIKE %s OR p.code ILIKE %s OR p.name ILIKE %s
        ORDER BY b.id DESC
        LIMIT 50
        """,
        (keyword, keyword, keyword, keyword),
    )
    for row in rows:
        key = row.get("bom_no") or row.get("numeric_id")
        row["detail_url"] = url_for("bom_detail", bom_key=key)
    return jsonify(rows)


def lookup_suppliers(query_rows):
    return jsonify(query_rows("SELECT id, name FROM suppliers ORDER BY name LIMIT 200"))


def lookup_customers(query_rows):
    return jsonify(query_rows("SELECT id, name FROM customers ORDER BY name LIMIT 200"))


def lookup_products(query_rows):
    return jsonify(query_rows("SELECT id, code, name, unit FROM products ORDER BY code LIMIT 200"))


def api_categories(query_rows):
    return jsonify(query_rows("SELECT id, code, name FROM product_categories ORDER BY name LIMIT 200"))


def lookup_warehouse_locations(query_rows):
    """返回某仓库是否启用库位及其库位列表。

    启用库位与否由该仓库在 locations 表是否存在启用记录判定（不加标志位字段）。
    前端据此联动：未启用库位→库位字段灰显且非必填；启用库位→库位必填。
    """
    raw = (request.args.get("warehouse_id") or "").strip()
    try:
        warehouse_id = int(raw)
    except (TypeError, ValueError):
        warehouse_id = 0
    if warehouse_id <= 0:
        return jsonify({"has_locations": False, "locations": []})
    locations = query_rows(
        """
        SELECT id, code || ' / ' || name AS name
        FROM locations
        WHERE warehouse_id=%s AND COALESCE(is_active, TRUE)=TRUE
        ORDER BY code
        LIMIT 500
        """,
        (warehouse_id,),
    )
    return jsonify({"has_locations": bool(locations), "locations": locations})


def register_lookup_routes(app, deps):
    login_required = deps["login_required"]
    safe_rows = deps.get("safe_rows")
    query_db = deps.get("query_db")

    def query_rows(sql, params=None):
        if safe_rows is not None:
            return safe_rows(sql, params or ())
        return query_db(sql, params or ())

    app.add_url_rule(
        "/api/lookup/units",
        endpoint="lookup_units",
        view_func=login_required(lambda: lookup_units(query_rows)),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/lookup/boms",
        endpoint="lookup_boms",
        view_func=login_required(lambda: lookup_boms(query_rows)),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/lookup/suppliers",
        endpoint="lookup_suppliers",
        view_func=login_required(lambda: lookup_suppliers(query_rows)),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/lookup/customers",
        endpoint="lookup_customers",
        view_func=login_required(lambda: lookup_customers(query_rows)),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/lookup/products",
        endpoint="lookup_products",
        view_func=login_required(lambda: lookup_products(query_rows)),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/categories",
        endpoint="api_categories",
        view_func=login_required(lambda: api_categories(query_rows)),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/lookup/warehouse_locations",
        endpoint="lookup_warehouse_locations",
        view_func=login_required(lambda: lookup_warehouse_locations(query_rows)),
        methods=["GET"],
    )
