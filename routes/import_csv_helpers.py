"""CSV import helpers: parse CSV files and validate rows for data import."""
import csv
import io
from decimal import Decimal

from routes.display_helpers import _looks_corrupt_text


CSV_COLUMN_ALIASES = {
    "code": ("\u7269\u6599\u7f16\u7801", "\u5206\u7c7b\u7f16\u7801", "\u7f16\u7801"),
    "name": ("\u7269\u6599\u540d\u79f0", "\u5206\u7c7b\u540d\u79f0", "\u540d\u79f0"),
    "specification": ("\u89c4\u683c\u578b\u53f7", "\u89c4\u683c"),
    "unit": ("\u57fa\u672c\u5355\u4f4d", "\u5355\u4f4d"),
    "category": ("\u7269\u6599\u5206\u7c7b\u540d\u79f0", "\u7269\u6599\u5206\u7c7b", "\u5206\u7c7b"),
    "drawing_no": ("\u56fe\u53f7",),
    "material_grade": ("\u6750\u8d28",),
    "brand": ("\u54c1\u724c",),
    "standard_price": ("\u6807\u51c6\u4ef7",),
    "safety_stock": ("\u5b89\u5168\u5e93\u5b58",),
    "default_supplier_name": ("\u9ed8\u8ba4\u4f9b\u5e94\u5546",),
    "default_tax_rate": ("\u9ed8\u8ba4\u7a0e\u7387",),
    "status": ("\u4f7f\u7528\u72b6\u6001", "\u72b6\u6001"),
    "remark": ("\u5907\u6ce8",),
}


def csv_cell(row, *names):
    for name in names:
        if name in row and row.get(name) is not None:
            return str(row.get(name) or "").strip()
        for alias in CSV_COLUMN_ALIASES.get(name, ()):
            if alias in row and row.get(alias) is not None:
                return str(row.get(alias) or "").strip()
    return ""


def decimal_text(value, default="0"):
    text = str(value or "").strip()
    if not text:
        return Decimal(default)
    try:
        return Decimal(text)
    except Exception:
        return Decimal(default)


def decode_import_upload(file):
    raw = file.read()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding), []
        except UnicodeDecodeError:
            continue
    return "", ["\u4e0a\u4f20\u6587\u4ef6\u7f16\u7801\u65e0\u6cd5\u8bc6\u522b\uff0c\u8bf7\u4f7f\u7528 UTF-8 \u6216 GB18030 CSV \u540e\u91cd\u65b0\u5bfc\u5165"]


def read_csv_upload(file):
    text, _errors = decode_import_upload(file)
    return csv.DictReader(io.StringIO(text))


def _dirty_import_cell(value):
    text = str(value or "")
    if not text.strip():
        return False
    if "\ufffd" in text or "\x00" in text:
        return True
    if chr(63) * 3 in text:
        return True
    if chr(63) in text and len(text.replace(chr(63), "")) <= 2:
        return True
    if any(0xE000 <= ord(char) <= 0xF8FF for char in text) and _looks_corrupt_text(text):
        return True
    return _looks_corrupt_text(text) and not any("\u4e00" <= char <= "\u9fff" for char in text)


def validate_import_rows(rows, max_errors=50):
    errors = []
    for line_no, row in enumerate(rows, start=2):
        for column, value in (row or {}).items():
            dirty_column = _dirty_import_cell(column)
            if dirty_column or _dirty_import_cell(value):
                label = "\u5b57\u6bb5\u8868\u5934" if dirty_column else (str(column or "\u672a\u77e5\u5b57\u6bb5").strip() or "\u672a\u77e5\u5b57\u6bb5")
                errors.append(f"\u7b2c {line_no} \u884c {label} \u5305\u542b\u4e71\u7801\u6216\u975e\u6cd5\u7f16\u7801\uff0c\u8bf7\u4fee\u6b63\u540e\u91cd\u65b0\u5bfc\u5165")
                break
        if len(errors) >= max_errors:
            errors.append("\u9519\u8bef\u8fc7\u591a\uff0c\u8bf7\u5148\u4fee\u6b63\u524d\u9762\u7684\u6570\u636e\u540e\u91cd\u65b0\u5bfc\u5165")
            break
    return errors


def read_validated_csv_upload(file):
    text, errors = decode_import_upload(file)
    if errors:
        return [], errors
    rows = list(csv.DictReader(io.StringIO(text)))
    errors = validate_import_rows(rows)
    return rows, errors


def coerce_basic_import_value(column, value):
    text = str(value or "").strip()
    if column in {"credit_limit", "conversion_rate", "standard_labor_rate_per_hour"}:
        return decimal_text(text, "1" if column == "conversion_rate" else "0")
    if column == "lead_time_days":
        try:
            return int(Decimal(text or "0"))
        except Exception:
            return 0
    if column in {"is_sales", "is_active"}:
        return text in {"\u662f", "true", "True", "1", "Y", "y", "yes"}
    return text
