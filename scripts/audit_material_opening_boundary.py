from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def section(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


def main():
    registry = (ROOT / "routes" / "registry.py").read_text(encoding="utf-8")
    template = (ROOT / "templates" / "inventory_movement_form.html").read_text(encoding="utf-8")

    material_create = section(
        registry,
        "def _create_material_opening():",
        "def _render_material_opening_list():",
    )
    movement_create = section(
        registry,
        "def _create_inventory_movement(direction):",
        "def _create_material_opening():",
    )

    checks = [
        (
            "material_opening_ui_boundary",
            all(
                marker in template
                for marker in (
                    "is_material_opening",
                    "\u671f\u521d\u4fe1\u606f",
                    "\u5f53\u524d\u5e93\u5b58\u53c2\u8003",
                    "\u671f\u521d\u4f9d\u636e",
                    "\u76d8\u70b9/\u65e7\u7cfb\u7edf\u5355\u53f7",
                    "\u4fdd\u5b58\u671f\u521d",
                )
            ),
        ),
        (
            "material_opening_backend_source_type",
            "source_type=%s" in material_create
            and "source_doc_type=%s" in material_create
            and "(document_type, document_type, source_doc_no" in material_create,
        ),
        (
            "material_opening_uses_own_document_type",
            'document_type = "material_opening"' in material_create
            and '"MO"' in material_create
            and "other_inbound" not in material_create
            and "_create_inventory_movement(" not in material_create,
        ),
        (
            "other_inbound_still_separate",
            'document_type = "other_inbound" if direction == "in" else "other_outbound"' in movement_create
            and '"OI" if direction == "in" else "OO"' in movement_create,
        ),
        (
            "opening_list_filters_material_only",
            'params.extend(["material_opening", "\u7269\u6599\u671f\u521d"])' in registry
            and 'where = "(st.source_doc_type=%s OR st.transaction_type=%s)"' in registry,
        ),
    ]

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    if failed:
        raise SystemExit(1)
    print("material_opening_boundary=ok")


if __name__ == "__main__":
    main()
