from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY_TEMPLATES = [
    "templates/order_form.html",
    "templates/purchase_request_add.html",
    "templates/subcontract_order_form.html",
    "templates/work_order_form.html",
    "templates/inventory_movement_form.html",
    "templates/inventory_adjustment_form.html",
    "templates/inventory_transfer_form.html",
    "templates/inventory_check_form.html",
    "templates/inventory_assembly_form.html",
]


PRODUCT_COLUMN_KEY = re.compile(r"data-column-key=[\"']product[\"']", re.I)
VISIBLE_PRODUCT_SELECT = re.compile(r"<select\b(?=[^>]*name=[\"']product_id(?:\[\])?[\"'])(?![^>]*\bd-none\b)[^>]*>", re.I)


def main() -> int:
    findings = []
    for rel in ENTRY_TEMPLATES:
        path = ROOT / rel
        if not path.exists():
            findings.append(f"{rel}: missing")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if PRODUCT_COLUMN_KEY.search(text):
            findings.append(f"{rel}: product column key remains; product_id must live inside the material-name cell")
        if VISIBLE_PRODUCT_SELECT.search(text):
            findings.append(f"{rel}: visible product selector remains; keep product_id hidden")
        if "product_name" not in text and "material_name" not in text:
            findings.append(f"{rel}: no material name entry/display field")
    print(f"checked_templates={len(ENTRY_TEMPLATES)}")
    print(f"findings={len(findings)}")
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
