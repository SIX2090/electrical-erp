from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


PAGES = {
    "/sales/new": (
        "新增销售订单",
        "客户",
        "单据日期",
        "项目号",
        "柜号",
        "物料明细",
        "规格型号",
        "未税单价",
        "税率",
        "未税金额",
        "税额",
        "含税金额",
        "批号",
    ),
    "/purchase_order/new": (
        "新增采购订单",
        "供应商",
        "单据日期",
        "预计到货",
        "项目号",
        "柜号",
        "物料明细",
        "规格型号",
        "未税单价",
        "税率",
        "未税金额",
        "税额",
        "含税金额",
        "批号",
    ),
    "/inventory/inbound": ("其他入库", "单据信息", "来源单据", "项目号", "物料明细", "库存成本单价", "批号", "柜号"),
    "/inventory/outbound": ("其他出库", "单据信息", "来源单据", "项目号", "物料明细", "库存成本单价", "批号", "柜号"),
    "/transfers/new": ("库存调拨单", "调出仓库", "调入仓库", "项目号", "调拨明细", "库存成本单价", "批号", "柜号"),
    "/adjustments/new": ("库存调整单", "调整类型", "项目号", "调整明细", "库存成本单价", "批号", "柜号"),
    "/inventory_checks/new": ("库存盘点单", "盘点日期", "项目号", "盘点明细", "实盘数量", "库存成本单价", "批号", "柜号"),
}

DIRTY_CODEPOINTS = {0xFFFD, 0x95C1, 0x9359, 0x6434}


def has_dirty_text(text):
    return "???" in text or any(ord(ch) in DIRTY_CODEPOINTS for ch in text)


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def safe_print_value(value):
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-core-document-fields")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    client = app.test_client()
    checks = []
    login = client.post("/login", data={"username": "pilot_admin", "password": load_password("pilot_admin")}, follow_redirects=False)
    checks.append(("pilot_admin_login", login.status_code == 302, login.status_code))
    if login.status_code == 302:
        for path, required_labels in PAGES.items():
            response = client.get(path)
            body = response.get_data(as_text=True)
            checks.append((f"page_status:{path}", response.status_code == 200, response.status_code))
            for label in required_labels:
                checks.append((f"required:{path}:{label}", label in body, "present" if label in body else "missing"))
            checks.append((f"dirty:{path}", not has_dirty_text(body), "clean" if not has_dirty_text(body) else "dirty"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("trial_core_document_fields_audit=ok" if not failures else "trial_core_document_fields_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {safe_print_value(name)} | {safe_print_value(detail)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
