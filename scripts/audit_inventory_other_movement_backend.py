from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    migrations = (ROOT / "services" / "schema_migrations.py").read_text(encoding="utf-8")
    movement_section = registry.rsplit("def _create_inventory_movement(direction):", 1)[1].split("def _create_material_opening", 1)[0]
    checks = [
        ("movement_schema_helper", "_ensure_stock_transaction_movement_columns" in registry),
        ("material_snapshot_fields", all(token in registry for token in ("material_code", "material_name", "material_spec", "material_unit", "spec", "unit"))),
        ("line_location_parse", all(token in registry for token in ("warehouse_id[]", "line_warehouse_id[]", "location_id[]", "line_location_id[]"))),
        ("available_qty_snapshot", "available_qty" in registry and "_inventory_available_qty" in registry),
        ("amount_backend_calculated", "amount = abs(qty) * cost" in registry),
        ("frontend_amount_not_trusted", 'request.form.getlist("amount' not in movement_section and '_form_decimal("amount"' not in movement_section),
        ("source_trace_fields", all(token in registry for token in ("source_doc_type", "source_doc_no", "source_line_no"))),
        ("usage_reason_required", "其他出库每行必须填写用途/原因" in registry),
        ("positive_quantity_required", "entered_qty <= 0" in registry and "qty <= 0" in registry),
        ("line_or_header_location", "line.get(\"location_id\") or header_location_id" in registry),
        ("migration_fields", all(token in migrations for token in ("20260528_001_inventory_other_movement_line_fields", "usage_reason", "source_doc_type", "available_qty", "amount"))),
    ]
    failed = [(name, ok) for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    if failed:
        raise SystemExit(1)
    print("inventory_other_movement_backend=ok")


if __name__ == "__main__":
    main()
