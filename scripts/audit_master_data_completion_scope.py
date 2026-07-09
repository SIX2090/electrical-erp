from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def check(name, ok, detail):
    print(f"{name}={'ok' if ok else 'failed'} | {detail}")
    return ok


def main():
    master_data = read("routes/master_data_routes.py")
    customer_supplier_forms = read("routes/master_data_form_routes.py")
    registry = read("routes/registry.py")

    checks = []
    checks.append(
        check(
            "quality_workbench_boundary",
            all(token in master_data for token in ("基础资料质量工作台", "待补齐字段", "不会自动填值", "不自动乱填业务主数据")),
            "master-data root is a data-quality workbench with human maintenance boundary",
        )
    )
    checks.append(
        check(
            "material_completion_fields",
            all(token in master_data for token in ("默认供应商", "默认仓库", "安全库存", "/material", "/material/import")),
            "material queue exposes supplier, warehouse, safety stock and batch maintenance entry",
        )
    )
    checks.append(
        check(
            "partner_completion_fields",
            all(token in master_data for token in ("信用额度", "客户信用资料队列", "供应商结算资料队列", "默认交期", "付款条件")),
            "customer credit and supplier settlement completion cues are visible",
        )
    )
    checks.append(
        check(
            "human_maintenance_forms",
            all(token in customer_supplier_forms for token in ("付款条件/备注", "收票/结算地址", "付款条件/结算资料备注", "不自动生成")),
            "customer and supplier forms show low-risk maintenance hints without creating business data",
        )
    )
    forbidden = ("UPDATE products SET default_supplier_name", "UPDATE products SET default_warehouse", "UPDATE products SET safety_stock", "DELETE FROM products", "DELETE FROM customers", "DELETE FROM suppliers")
    checks.append(
        check(
            "no_auto_fill_or_delete",
            not any(token in master_data for token in forbidden),
            "workbench does not auto-fill or delete master records",
        )
    )
    checks.append(
        check(
            "no_forbidden_scope_change",
            all(token not in master_data for token in ("bom_items", "financial_reports", "pilot_role_permissions", "@app.route('/')")),
            "master-data completion audit does not touch BOM, finance, security, or root route scope",
        )
    )
    checks.append(
        check(
            "route_registration_stable",
            "_render_master_data_dashboard" in registry and "render_master_data_dashboard_adapter" in registry,
            "existing master-data dashboard registration remains in place",
        )
    )

    if not all(checks):
        raise SystemExit(1)
    print("master_data_completion_scope=ok")


if __name__ == "__main__":
    main()
