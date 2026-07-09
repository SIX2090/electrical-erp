from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import load_first_machine_values


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def exists(cur, sql, params):
    cur.execute(sql, params)
    row = cur.fetchone()
    return bool(row and row.get("exists"))


def write_gap_tasks(path, missing_checks):
    output_dir = ROOT / "release" / "trial_run"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "first_machine_master_data_tasks.csv"
    lines = ["source_template,gap_type,gap_value,suggested_page,next_action,status"]
    page_map = {
        "sales_order_no": "/sales/new",
        "product_code": "/material",
        "bom_no": "/bom",
        "warehouse_code": "/warehouse",
        "material_code_1": "/material",
        "material_code_2": "/material",
    }
    for label, value in missing_checks:
        lines.append(f"{path},{label},{value},{page_map.get(label, '/projects')},maintain master or source document,pending")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    values = load_first_machine_values(path)
    checks = []
    errors = []
    warnings = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            order_no = values.get("sales_order_no")
            if order_no:
                checks.append(("sales_order_no", order_no, exists(cur, "SELECT EXISTS(SELECT 1 FROM sales_orders WHERE order_no=%s)", (order_no,))))
            product_code = values.get("product_code")
            if product_code:
                checks.append(("product_code", product_code, exists(cur, "SELECT EXISTS(SELECT 1 FROM products WHERE code=%s)", (product_code,))))
            bom_no = values.get("bom_no")
            if bom_no:
                checks.append(("bom_no", bom_no, exists(cur, "SELECT EXISTS(SELECT 1 FROM boms WHERE bom_no=%s)", (bom_no,))))
            warehouse_code = values.get("warehouse_code")
            if warehouse_code:
                checks.append(("warehouse_code", warehouse_code, exists(cur, "SELECT EXISTS(SELECT 1 FROM warehouses WHERE name=%s OR code=%s)", (warehouse_code, warehouse_code))))
            for key in ("material_code_1", "material_code_2"):
                material_code = values.get(key)
                if material_code:
                    checks.append((key, material_code, exists(cur, "SELECT EXISTS(SELECT 1 FROM products WHERE code=%s)", (material_code,))))
    finally:
        conn.close()

    missing_checks = []
    for label, value, ok in checks:
        if not ok:
            missing_checks.append((label, value))
            errors.append(f"{label}: missing `{value}`")

    print(f"template={path}")
    print(f"checks={len(checks)} errors={len(errors)} warnings={len(warnings)}")
    for label, value, ok in checks:
        print(f"check | {label} | {value} | {'ok' if ok else 'missing'}")
    for item in errors:
        print(f"error | {item}")
    for item in warnings:
        print(f"warning | {item}")
    if missing_checks:
        print(f"task_csv={write_gap_tasks(path, missing_checks)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
