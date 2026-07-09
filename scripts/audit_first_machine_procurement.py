from pathlib import Path
import csv
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.app_runtime import connect_db
from services.env_config import get_pg_password
from scripts.first_machine_trial_utils import ensure_first_machine_demand_baseline, load_first_machine_values, load_trial_password


TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"


def get_db_config():
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def load_values():
    return load_first_machine_values(TEMPLATE)


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "first-machine-procurement-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")
    values = load_values()
    checks = []

    conn = connect_db(get_db_config())
    try:
        with conn.cursor() as cur:
            ensure_first_machine_demand_baseline(cur, values)
            conn.commit()
            cur.execute(
                """
                SELECT COUNT(*) AS lines, COALESCE(SUM(shortage_quantity), 0) AS shortage_qty
                FROM mrp_requirements
                WHERE project_code=%s AND serial_no=%s AND COALESCE(shortage_quantity, 0) > 0
                """,
                (values["项目号"], values["机号"]),
            )
            shortage = cur.fetchone() or {}
            lines = int(shortage.get("lines") or 0)
            checks.append(("mrp_shortage_lines", lines >= 1, lines))

            cur.execute(
                """
                SELECT COUNT(*) AS lines
                FROM mrp_requirements mr
                JOIN products p ON p.id=mr.product_id
                WHERE mr.project_code=%s
                  AND mr.serial_no=%s
                  AND COALESCE(mr.shortage_quantity, 0) > 0
                  AND p.code IN (%s, %s)
                """,
                (values["项目号"], values["机号"], values["关键物料1编码"], values.get("关键物料2编码") or ""),
            )
            material_lines = int((cur.fetchone() or {}).get("lines") or 0)
            checks.append(("shortage_materials_match_bom", material_lines >= 1, material_lines))
    finally:
        conn.close()

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000})
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_production", "password": load_password("pilot_production")})
    checks.append(("pilot_production_login", login.status_code == 302, login.status_code))
    if login.status_code == 302:
        for path in (
            f"/engineering/kitting?keyword={values['项目号']}",
            f"/production-enhance/mrp-requirements?search={values['项目号']}",
            f"/procurement/suggestions?keyword={values['项目号']}",
        ):
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"{path}:status", response.status_code == 200, response.status_code))
            checks.append((f"{path}:project_visible", values["项目号"] in body and values["机号"] in body, "visible"))
            checks.append((f"{path}:clean", not any(marker in body for marker in ["\ufffd", "???", "\u9435", "\u93bf", "\u93b5"]), "clean"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("first_machine_procurement_audit=ok" if not failures else "first_machine_procurement_audit=failed")
    print(f"checked_items={len(checks)}")
    print(f"project_code={values['项目号']}")
    print(f"serial_no={values['机号']}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
