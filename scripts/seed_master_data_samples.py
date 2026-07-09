from pathlib import Path
import argparse
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password


SAMPLE_MARK = "sample-only: machine-tool master data"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def table_columns(cur, table):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        """,
        ("public", table),
    )
    return {row["column_name"] for row in cur.fetchall()}


def table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s) AS name", (table,))
    row = cur.fetchone()
    return bool(row and row.get("name"))


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def first_id(cur, table, where_sql, params):
    cur.execute(f"SELECT id FROM {table} WHERE {where_sql} ORDER BY id LIMIT 1", params)
    row = cur.fetchone()
    return row.get("id") if row else None


def upsert_by_key(cur, table, key_field, values):
    cols = table_columns(cur, table)
    usable = {key: value for key, value in values.items() if key in cols}
    if key_field not in usable:
        raise RuntimeError(f"{table}.{key_field} is required for sample upsert")
    row_id = first_id(cur, table, f"{key_field}=%s", (usable[key_field],))
    if row_id:
        update_items = [(key, value) for key, value in usable.items() if key != key_field]
        if update_items:
            assignments = ", ".join(f"{key}=%s" for key, _value in update_items)
            params = [value for _key, value in update_items] + [row_id]
            cur.execute(f"UPDATE {table} SET {assignments} WHERE id=%s", params)
        return row_id, "updated"
    names = list(usable)
    placeholders = ", ".join(["%s"] * len(names))
    cur.execute(
        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders}) RETURNING id",
        [usable[name] for name in names],
    )
    return cur.fetchone()["id"], "inserted"


def ensure_category(cur, table, code, name, remark):
    if not table_exists(cur, table):
        return None, "missing_table"
    return upsert_by_key(
        cur,
        table,
        "code",
        {
            "code": code,
            "name": name,
            "parent_id": None,
            "remark": f"{SAMPLE_MARK}; {remark}",
        },
    )


def ensure_unit(cur, code, name, category, conversion_rate="1"):
    return upsert_by_key(
        cur,
        "units",
        "code",
        {
            "code": code,
            "name": name,
            "category": category,
            "conversion_rate": conversion_rate,
            "status": "启用",
            "remark": SAMPLE_MARK,
        },
    )


def ensure_department(cur):
    return upsert_by_key(
        cur,
        "departments",
        "code",
        {
            "code": "SAMPLE-DEPT-PROD",
            "name": "样例装配调试部",
            "manager": "样例车间主管",
            "phone": "0571-00000000",
            "status": "启用",
            "remark": SAMPLE_MARK,
        },
    )


def ensure_employee(cur, dept_id):
    return upsert_by_key(
        cur,
        "employees",
        "code",
        {
            "code": "SAMPLE-EMP-001",
            "name": "样例装配员",
            "dept_id": dept_id,
            "position": "装配调试",
            "phone": "13800000000",
            "email": "sample.operator@example.local",
            "is_sales": False,
            "status": "在职",
            "employment_type": "正式",
            "hire_date": "2026-06-01",
            "standard_labor_rate_per_hour": "80",
            "remark": SAMPLE_MARK,
        },
    )


def ensure_customer(cur, category_id):
    return upsert_by_key(
        cur,
        "customers",
        "name",
        {
            "name": "样例客户-机床装备厂",
            "contact_person": "样例客户联系人",
            "phone": "0571-10000000",
            "address": "浙江省杭州市样例工业园",
            "customer_level": "重点客户",
            "credit_limit": "500000",
            "credit_used": "0",
            "category_id": category_id,
            "tax_no": "91330000SAMPLE001",
            "invoice_title": "样例客户-机床装备厂",
            "default_tax_rate": "13",
            "status": "启用",
            "remark": SAMPLE_MARK,
        },
    )


def ensure_supplier(cur, category_id, *, outsourced=False):
    name = "样例委外加工商-龙门加工" if outsourced else "样例供应商-主轴电机"
    return upsert_by_key(
        cur,
        "suppliers",
        "name",
        {
            "name": name,
            "contact_person": "样例供应商联系人",
            "phone": "0571-20000000",
            "address": "浙江省湖州市样例制造区",
            "lead_time_days": 7,
            "category_id": category_id,
            "tax_no": "91330000SAMPLE002" if not outsourced else "91330000SAMPLE003",
            "invoice_title": name,
            "default_tax_rate": "13",
            "is_outsourced_processor": outsourced,
            "status": "启用",
            "remark": SAMPLE_MARK,
        },
    )


def ensure_warehouse_and_location(cur, category_id):
    warehouse_id, warehouse_status = upsert_by_key(
        cur,
        "warehouses",
        "code",
        {
            "code": "SAMPLE-WH-MAIN",
            "name": "样例总装仓",
            "category_id": category_id,
            "warehouse_type": "装配仓",
            "status": "启用",
            "remark": SAMPLE_MARK,
        },
    )
    location_id, location_status = upsert_by_key(
        cur,
        "locations",
        "code",
        {
            "warehouse_id": warehouse_id,
            "code": "SAMPLE-LOC-A01",
            "name": "样例A01库位",
            "is_active": True,
            "location_type": "普通库位",
            "status": "启用",
            "remark": SAMPLE_MARK,
        },
    )
    if "default_location_id" in table_columns(cur, "warehouses"):
        cur.execute(
            "UPDATE warehouses SET default_location_id=%s WHERE id=%s",
            (location_id, warehouse_id),
        )
    return warehouse_id, location_id, warehouse_status, location_status


def ensure_product(cur, category_id, supplier_id, warehouse_id, location_id):
    return upsert_by_key(
        cur,
        "products",
        "code",
        {
            "code": "SAMPLE-GTYM-001",
            "name": "样例滚筒研磨机",
            "category": "滚筒研磨机",
            "category_id": category_id,
            "specification": "GTYM-1200",
            "unit": "台",
            "standard_price": "180000",
            "safety_stock": "0",
            "default_tax_rate": "13",
            "item_type": "成品",
            "drawing_no": "SAMPLE-DWG-GTYM-001",
            "material_grade": "装配件",
            "brand": "样例品牌",
            "default_supplier_id": supplier_id,
            "default_warehouse_id": warehouse_id,
            "default_location_id": location_id,
            "default_supplier_name": "样例供应商-主轴电机",
            "default_warehouse": "样例总装仓",
            "default_location": "样例A01库位",
            "purchase_lead_days": 7,
            "min_order_qty": "1",
            "batch_control": False,
            "serial_control": True,
            "inspection_required": True,
            "abc_class": "A",
            "status": "启用",
            "remark": SAMPLE_MARK,
        },
    )


def expected_checks():
    return [
        ("product_categories", "code", "SAMPLE-PF-GTYM", "产品系列"),
        ("customer_categories", "code", "SAMPLE-CUST-KEY", "客户分类"),
        ("supplier_categories", "code", "SAMPLE-SUP-CORE", "供应商分类"),
        ("supplier_categories", "code", "SAMPLE-SUP-OUT", "委外商分类"),
        ("warehouse_categories", "code", "SAMPLE-WH-ASSEMBLY", "仓库分类"),
        ("units", "code", "TAI", "计量单位-台"),
        ("units", "code", "SET", "计量单位-套"),
        ("departments", "code", "SAMPLE-DEPT-PROD", "部门"),
        ("employees", "code", "SAMPLE-EMP-001", "员工"),
        ("customers", "name", "样例客户-机床装备厂", "客户"),
        ("suppliers", "name", "样例供应商-主轴电机", "供应商"),
        ("suppliers", "name", "样例委外加工商-龙门加工", "委外加工商"),
        ("warehouses", "code", "SAMPLE-WH-MAIN", "仓库"),
        ("locations", "code", "SAMPLE-LOC-A01", "库位"),
        ("products", "code", "SAMPLE-GTYM-001", "产品/机型"),
    ]


def check_samples(cur):
    rows = []
    missing = []
    for table, field, value, label in expected_checks():
        if not table_exists(cur, table):
            rows.append((label, table, value, "missing_table"))
            missing.append(label)
            continue
        found = scalar(cur, f"SELECT COUNT(*) FROM {table} WHERE {field}=%s", (value,)) or 0
        status = "ok" if found else "missing"
        rows.append((label, table, value, status))
        if not found:
            missing.append(label)
    return rows, missing


def seed_samples(cur):
    changes = []
    product_category_id, status = ensure_category(cur, "product_categories", "SAMPLE-PF-GTYM", "滚筒研磨机", "product family")
    changes.append(("产品系列", "product_categories", status))
    customer_category_id, status = ensure_category(cur, "customer_categories", "SAMPLE-CUST-KEY", "重点装备客户", "customer category")
    changes.append(("客户分类", "customer_categories", status))
    supplier_category_id, status = ensure_category(cur, "supplier_categories", "SAMPLE-SUP-CORE", "核心供应商", "supplier category")
    changes.append(("供应商分类", "supplier_categories", status))
    outsource_category_id, status = ensure_category(cur, "supplier_categories", "SAMPLE-SUP-OUT", "委外加工商", "outsourced processor category")
    changes.append(("委外商分类", "supplier_categories", status))
    warehouse_category_id, status = ensure_category(cur, "warehouse_categories", "SAMPLE-WH-ASSEMBLY", "装配仓", "warehouse category")
    changes.append(("仓库分类", "warehouse_categories", status))

    for code, name, category in (("TAI", "台", "数量"), ("SET", "套", "数量")):
        _row_id, status = ensure_unit(cur, code, name, category)
        changes.append((f"计量单位-{name}", "units", status))

    dept_id, status = ensure_department(cur)
    changes.append(("部门", "departments", status))
    _employee_id, status = ensure_employee(cur, dept_id)
    changes.append(("员工", "employees", status))
    _customer_id, status = ensure_customer(cur, customer_category_id)
    changes.append(("客户", "customers", status))
    supplier_id, status = ensure_supplier(cur, supplier_category_id, outsourced=False)
    changes.append(("供应商", "suppliers", status))
    _outsource_id, status = ensure_supplier(cur, outsource_category_id, outsourced=True)
    changes.append(("委外加工商", "suppliers", status))
    warehouse_id, location_id, warehouse_status, location_status = ensure_warehouse_and_location(cur, warehouse_category_id)
    changes.append(("仓库", "warehouses", warehouse_status))
    changes.append(("库位", "locations", location_status))
    _product_id, status = ensure_product(cur, product_category_id, supplier_id, warehouse_id, location_id)
    changes.append(("产品/机型", "products", status))
    return changes


def main():
    parser = argparse.ArgumentParser(description="Seed or check sample-only machine-tool master data.")
    parser.add_argument("--apply", action="store_true", help="Write idempotent sample-only master data.")
    args = parser.parse_args()

    conn = connect_db(get_db_config())
    try:
        with conn:
            with conn.cursor() as cur:
                if args.apply:
                    changes = seed_samples(cur)
                    print("seed_master_data_samples=applied")
                    for label, table, status in changes:
                        print(f"change | {label} | {table} | {status}")
                rows, missing = check_samples(cur)
                print(f"master_data_sample_checks={len(rows)} missing={len(missing)}")
                for label, table, value, status in rows:
                    print(f"check | {label} | {table} | {value} | {status}")
                if missing and not args.apply:
                    print("hint | rerun with --apply to create sample-only master data")
                return 1 if missing else 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
