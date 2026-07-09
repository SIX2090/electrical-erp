"""Value conversion helpers: decimal, int, and numeric formatting utilities."""
from decimal import Decimal


def as_decimal(value, default="0"):
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def as_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def returned_id(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get("id")
    try:
        return row["id"]
    except Exception:
        return row


def short_text(value, max_length):
    text = str(value or "").strip()
    return text[:max_length]
