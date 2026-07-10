from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


REQUIRED_TEMPLATE_MARKERS = (
    "物料编码",
    "物料名称",
    "规格型号",
    "单位",
    "行仓库",
    "行库位",
    "可用库存",
    "数量",
    "库存成本单价",
    "成本金额",
    "批号",
    "柜号",
    "项目号",
    "出库原因",
    "来源单据",
    "来源行",
    'name="line_warehouse_id[]"',
    'name="line_location_id[]"',
    'name="usage_reason[]"',
    'name="source_doc_no[]"',
    'name="source_line_no[]"',
    'name="unit_cost[]" value="0" readonly',
)

REQUIRED_SCRIPT_MARKERS = (
    "recalcMovementRow",
    "js-product-code",
    "js-product-name",
    "js-product-spec",
    "js-product-unit",
    "js-available-qty",
    "js-cost-amount",
    "data-available-qty",
    "data-price",
    "quantity * unitCost",
    "name=\"usage_reason[]\"",
    "name=\"source_doc_no[]\"",
)

DIRTY_CODEPOINTS = {0xFFFD, 0x93C2, 0x9357, 0x9417, 0x6434, 0x93B5, 0x93C1}


def has_dirty_text(text):
    return "???" in text or any(ord(ch) in DIRTY_CODEPOINTS for ch in text)


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "inventory-movement-line-fields")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    template = (ROOT / "templates" / "inventory_movement_form.html").read_text(encoding="utf-8")
    script = (ROOT / "templates" / "partials" / "inventory_grid_scripts.html").read_text(encoding="utf-8")
    checks = []
    for marker in REQUIRED_TEMPLATE_MARKERS:
        checks.append((f"template_marker:{marker}", marker in template, "present" if marker in template else "missing"))
    for marker in REQUIRED_SCRIPT_MARKERS:
        checks.append((f"script_marker:{marker}", marker in script, "present" if marker in script else "missing"))
    checks.append(("dirty_markers", not has_dirty_text(template + script), "clean" if not has_dirty_text(template + script) else "dirty"))

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    password = load_password("pilot_warehouse") or load_password("pilot_admin")
    checks.append(("password_loaded", bool(password), "loaded" if password else "missing"))
    if password:
        username = "pilot_warehouse" if load_password("pilot_warehouse") else "pilot_admin"
        login = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        checks.append(("login", login.status_code == 302, login.status_code))
        page_markers = {
            "/inventory/inbound": ("物料名称", "规格型号", "行仓库", "可用库存", "成本金额", "入库原因", "来源单据", "readonly"),
            "/inventory/outbound": ("物料名称", "规格型号", "行仓库", "可用库存", "成本金额", "出库原因", "来源单据", "readonly"),
        }
        for path, markers in page_markers.items():
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"GET {path}", response.status_code == 200, response.status_code))
            for marker in markers:
                checks.append((f"{path}:{marker}", marker in body, "present" if marker in body else "missing"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("inventory_movement_line_fields_audit=ok" if not failures else "inventory_movement_line_fields_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        line = f"{'ok' if ok else 'failed'} | {name} | {detail}"
        print(line.encode("ascii", "backslashreplace").decode("ascii"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
