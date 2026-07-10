from pathlib import Path
from decimal import Decimal, InvalidOperation
import csv
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "release" / "trial_run" / "first_machine_data_template.csv"

QTY_FIELDS = {"sales_qty", "material_qty_1", "material_qty_2"}
REQUIRED_FIELDS = {
    "project_code",
    "cabinet_no",
    "product_code",
    "bom_no",
    "sales_qty",
    "machine_model",
    "material_code_1",
    "material_qty_1",
    "warehouse_code",
}


def is_blank(value):
    return not (value or "").strip()


def valid_decimal(value, allow_blank=False):
    if allow_blank and is_blank(value):
        return True
    try:
        return Decimal(str(value).strip()) >= 0
    except (InvalidOperation, ValueError):
        return False


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig")))
    errors = []
    warnings = []
    values = {}

    for row in rows:
        field = (row.get("field") or row.get("字段") or "").strip()
        value = (row.get("actual") or row.get("实际填写") or "").strip()
        required_text = (row.get("required") or row.get("必填") or "").strip().lower()
        required = required_text in {"yes", "true", "1", "是"} or field in REQUIRED_FIELDS
        if not field:
            continue
        values[field] = value
        if required and is_blank(value):
            errors.append(f"{field}: required value is blank")
            continue
        if field in QTY_FIELDS and not valid_decimal(value, allow_blank=not required):
            errors.append(f"{field}: quantity must be a non-negative number")

    for field in sorted(REQUIRED_FIELDS - set(values)):
        errors.append(f"{field}: required template row is missing")

    print(f"template={path}")
    print(f"errors={len(errors)} warnings={len(warnings)}")
    for item in errors:
        print(f"error | {item}")
    for item in warnings:
        print(f"warning | {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
