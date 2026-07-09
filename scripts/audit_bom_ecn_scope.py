from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(name, condition, detail):
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}: {detail}")
    return condition


def main():
    route_text = read("routes/bom_routes.py")
    list_text = read("templates/bom_ecn_list.html")
    form_text = read("templates/bom_ecn_form.html")
    detail_text = read("templates/bom_ecn_detail.html")
    bom_form_text = read("templates/bom_form.html")
    combined = "\n".join([route_text, list_text, form_text, detail_text, bom_form_text])

    checks = [
        require("ecn_list_route", '"/bom/ecn"' in route_text and "bom_ecn_list" in route_text, "engineering change list route exists"),
        require("ecn_entry_route", '"/bom/ecn/new"' in route_text and "bom_ecn_new" in route_text, "engineering change entry route exists"),
        require("ecn_detail_route", '"/bom/ecn/<path:ecn_key>"' in route_text and "bom_ecn_detail" in route_text, "engineering change detail route exists"),
        require("ecn_status_flow", all(token in route_text for token in ["draft", "submitted", "approved", "closed", "voided", "submit", "approve", "close", "void"]), "draft/submit/approve/close/void flow is present"),
        require("change_reason_required", "change_reason TEXT NOT NULL" in route_text and "请填写变更原因" in route_text, "change reason is required"),
        require("bom_impact_link", "source_bom_id" in route_text and "target_bom_id" in route_text, "source and target BOM links are stored"),
        require("copy_upgrade_link", "ecn_no" in bom_form_text and "_update_ecn_target" in route_text, "BOM copy upgrade can link back to ECN"),
        require("readonly_impact", all(token in detail_text for token in ["只读影响摘要", "相关工单", "MRP需求", "采购未到"]), "work order/MRP/purchase impact is read-only UI"),
        require("alternative_boundary", "替代料一期保留为BOM子项替代标识或说明" in form_text and "规则引擎" not in combined, "alternative material stays at BOM item flag/remark boundary"),
        require("no_forbidden_modules", not any(token in combined for token in ["/finance", "/system", "/customers", "/suppliers"]), "no finance/system/master-data/root route expansion"),
    ]
    if not all(checks):
        raise SystemExit(1)
    print("BOM ECN scope audit passed.")


if __name__ == "__main__":
    main()
