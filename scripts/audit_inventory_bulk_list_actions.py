from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def contains(path, text):
    return text in (ROOT / path).read_text(encoding="utf-8")


def main():
    checks = []
    template = (ROOT / "templates" / "simple_list.html").read_text(encoding="utf-8")
    special = (ROOT / "routes" / "special_list_routes.py").read_text(encoding="utf-8")
    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    def check(name, ok, detail):
        checks.append((name, ok, detail))

    for doc_type in ["adjustment", "transfer", "check", "sales_return", "purchase_return"]:
        check(f"document config {doc_type}", f'"bulk_doc_type": "{doc_type}"' in special, doc_type)
    for doc_type in ["assembly", "disassembly"]:
        check(f"assembly config {doc_type}", f'_inventory_bulk_actions(meta["doc_type"])' in registry, doc_type)
    for label in ["批量确认过账", "批量关闭", "批量取消", "批量打印/导出提示"]:
        check(f"visible action {label}", label in template or label in special or label in registry, label)
    for token in ["bulk-row-check", "bulkSelectAll", "name=\"ids\"", "bulk_actions.endpoint"]:
        check(f"template contract {token}", token in template, token)
    for token in [
        "def _inventory_bulk_action_config",
        "def _inventory_bulk_action",
        '"post": _post_inventory_adjustment',
        '"close": _close_inventory_transfer',
        '"cancel": _cancel_inventory_check',
        '_post_inventory_assembly_document(record_id, "assembly")',
        '_post_inventory_assembly_document(record_id, "disassembly")',
        '_post_inventory_return("sales_returns", record_id, "sales")',
        '_post_inventory_return("purchase_returns", record_id, "purchase")',
        'status in {"已取消", "cancelled", "canceled"}',
        "allowed_return_urls",
    ]:
        check(f"bulk route contract {token}", token in registry, token)
    check("bulk route registered", '@app.post("/inventory/bulk-action"' in registry, "/inventory/bulk-action")
    check("bulk permission guarded", 'path == "/inventory/bulk-action"' in app, "app.py")

    failures = [item for item in checks if not item[1]]
    print("inventory_bulk_list_actions_audit=ok" if not failures else "inventory_bulk_list_actions_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
