"""Decimal utilities: safe decimal conversion and money formatting helpers."""
from decimal import Decimal


def as_decimal(value, default="0"):
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(str(default))


def money_fmt(value):
    """将数值格式化为带千位分隔符的金额字符串，保留2位小数。"""
    try:
        return f"{Decimal(str(value or 0)):,.2f}"
    except Exception:
        return "0.00"
