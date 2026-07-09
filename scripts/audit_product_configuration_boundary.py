from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def require(name, condition, detail):
    return {"name": name, "ok": bool(condition), "detail": detail}


def main():
    route_text = read("routes/product_configuration_routes.py")
    registry_text = read("routes/registry.py")
    base_text = read("templates/base.html")
    boundary_text = read("ERP_BOUNDARY_STABILIZATION.md")
    classification_text = read("MENU_ROLLOUT_CLASSIFICATION.md")
    permissions_text = read("services/pilot_permissions.py")
    migration_text = read("services/schema_migrations.py")

    checks = [
        require("route_list", '"/product-configurations"' in route_text and "product_configuration_list" in route_text, "list route exists"),
        require("route_entry", '"/product-configurations/new"' in route_text and "product_configuration_new" in route_text, "entry route exists"),
        require("route_detail", '"/product-configurations/<int:config_id>"' in route_text and "product_configuration_detail" in route_text, "detail route exists"),
        require("status_submit", "product_configuration_submit" in route_text and "engineering_confirmed" in route_text, "bounded status actions exist"),
        require("bom_link_only", "product_configuration_link_bom" in route_text and "project_bom_id" in route_text, "project BOM linking exists"),
        require("no_execution_creation", "purchase_order" not in route_text and "work_orders" not in route_text and "stock_transactions" not in route_text, "route does not create execution documents"),
        require("required_option_validation", "required_flag" in route_text and "互斥项冲突" in route_text, "required and mutual exclusion validation exists"),
        require("schema_tables", "product_configurations" in migration_text and "product_configuration_items" in migration_text, "schema migration contains tables"),
        require("registered", "register_product_configuration_routes" in registry_text, "route module registered"),
        require("menu_entry", 'href="/product-configurations/new"' in base_text and 'href="/product-configurations"' in base_text, "menu exposes entry and list separately"),
        require("pilot_permission", '"/product-configurations"' in permissions_text and '"product_configuration"' in permissions_text, "pilot permissions include configuration routes"),
        require("boundary_doc", "Product Configuration Boundary" in boundary_text and "must not directly create purchase" in boundary_text, "business boundary documented"),
        require("classification", "/product-configurations/new" in classification_text and "/product-configurations/<id>" in classification_text, "menu classification documented"),
    ]

    failed = [check for check in checks if not check["ok"]]
    for check in checks:
        status = "OK" if check["ok"] else "FAIL"
        print(f"{status} {check['name']}: {check['detail']}")
    if failed:
        raise SystemExit(1)
    print("Product configuration boundary audit passed.")


if __name__ == "__main__":
    main()
