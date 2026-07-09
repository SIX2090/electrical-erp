from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def check(name, ok, detail):
    print(f"{name}={'ok' if ok else 'failed'} | {detail}")
    return ok


def main():
    checks = []
    index = read("templates/index.html")
    subcontract_registry = read("routes/registry.py")
    bom_list = read("templates/bom_list.html")
    bom_form = read("templates/bom_form.html")
    master_data = read("routes/master_data_routes.py")
    system_management = read("routes/system_management_routes.py")
    system_health = read("routes/system_health_routes.py")
    inventory_adjustment = read("templates/inventory_adjustment_form.html")

    checks.append(check("home_role_queue_boundary", "试点队列" in index and "项目/机号风险" in index and "业务单据" not in index.split("{% if nav_mode")[1].split("{% else %}")[0], "home pilot area is queue/workbench oriented"))
    checks.append(check("subcontract_list_boundary", "add_url=\"/subcontract/new\"" not in subcontract_registry and "execution_status" in subcontract_registry and "payable_balance" in subcontract_registry, "subcontract list shows execution/payable state without create action in workbench list"))
    checks.append(check("bom_version_and_copy", all(token in bom_list for token in ("失效日期", "复制升版", "列表只负责查询")) and all(token in bom_form for token in ("版本有效期", "替代标识", "复制升版BOM")), "BOM list/form expose version/copy/substitute boundary"))
    checks.append(check("master_data_queue_boundary", all(token in master_data for token in ("安全库存", "默认仓库", "信用信息", "结算资料", "待处理队列")), "master data dashboard keeps gap queues and key fields"))
    checks.append(check("system_switches", all(token in system_management for token in ("allow_negative_stock", "batch_serial_control", "document_approval_flow")) and all(token in system_health for token in ("PG_PASSWORD", "INVENTORY_SECRET_KEY", "角色权限矩阵", "业务控制开关")), "system options and data health expose required switches/security checks"))
    checks.append(check("inventory_adjustment_required_markers", all(token in inventory_adjustment for token in ('name="location_id" required', "请选择库位", "调整原因必填")), "inventory adjustment keeps location and reason required markers"))

    if not all(checks):
        raise SystemExit(1)
    print("screenshot11_main_scope=ok")


if __name__ == "__main__":
    main()
