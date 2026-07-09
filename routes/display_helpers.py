"""Display helpers: mojibake detection, text cleaning, and row filtering for ERP pages."""
from __future__ import annotations

from datetime import datetime


# Code points commonly produced by UTF-8 Chinese text being decoded as GBK/ANSI.
# Keep this ASCII-only so the detector cannot become another dirty source file.
MOJIBAKE_CODEPOINTS = {
    0xFFFD,
    0x95C1,
    0x95BF,
    0x95B8,
    0x95BB,
    0x93BC,
    0x95BA,
    0x5A11,
    0x7F01,
    0x6D34,
    0x6FE1,
    0x93CB,
    0x93C8,
    0x7025,
    0x7016,
    0x9427,
    0x8BE7,
    0x7D8D,
    0x54C4,
    0x7C25,
    0x6401,
    0x64B3,
    0x74E8,
    0x508C,
    0x6F98,
    0x9840,
    0x5186,
    0x6FB6,
    0x7164,
    0x782D,
    0x6D57,
    0x6A3C,
    0x8680,
    0x7F02,
    0x6D23,
    0x95C2,
    0x95C3,
    0x95C4,
    0x95C5,
    0x95C6,
    0x95C7,
    0x95C8,
    0x95C9,
    0x95CA,
    0x95CB,
    0x95CC,
    0x95CD,
    0x95CE,
    0x95CF,
    0x95D0,
    0x95D1,
    0x95D2,
    0x95D3,
    0x95FA,
    0x50A8,
    0x9864,
    0x5192,
    0x61CE,
    0x62F9,
    0x504C,
    0x7C92,
    0x4E02,
    0x4F9D,
    0x4E0A,
    0x95F0,
    0x7992,
    0x9422,
    0x8FA9,
    0x9F0E,
    0x9366,
    0x569C,
    0x9364,
    0x93C1,
    0x7F8A,
    0x95E8,
    0x93C2,
    0xE583,
    0x947D,
    0xE7C8,
    0x5BF0,
    0x5466,
    0x5F42,
    0x7490,
    0x20AC,
    0x935E,
    0x935F,
    0x941C,
    0x9411,
    0x71B8,
    0x7487,
    0xFE3D,
    0x510F,
    0x6E1A,
    0x7C32,
    0x30E5,
    0x7C31,
    0x6944,
}
QUESTION_MARK = chr(63)
MOJIBAKE_MARKERS = tuple(chr(codepoint) for codepoint in sorted(MOJIBAKE_CODEPOINTS))

NON_BUSINESS_TEXT_MARKERS = (
    "pytest",
    "test supplier",
    "test customer",
    "accuracy supplier",
    "accuracy customer",
    "lifecycle supplier",
    "cf supplier",
    "multi line supplier",
    "multi line customer",
    "main warehouse",
    "default location",
    "sample",
    "demo",
    "e2e",
)


def _looks_corrupt_text(value):
    text = str(value or "").strip()
    if not text:
        return False
    if QUESTION_MARK * 3 in text:
        return True
    if "?" in text and len(text.replace("?", "")) <= 2:
        return True
    dirty_count = sum(1 for char in text if ord(char) in MOJIBAKE_CODEPOINTS)
    private_count = sum(1 for char in text if 0xE000 <= ord(char) <= 0xF8FF)
    if private_count and ("?" in text or dirty_count):
        return True
    if dirty_count and ("?" in text or dirty_count >= 2):
        return True
    return dirty_count >= 2 and dirty_count / max(len(text), 1) > 0.18


def _looks_non_business_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in NON_BUSINESS_TEXT_MARKERS)


def _clean_display_text(value, fallback="-"):
    if value is None or value == "":
        return fallback
    if _looks_corrupt_text(value):
        return fallback
    return _status_label(value) if isinstance(value, str) else value


def _filter_clean_rows(rows, *fields):
    clean = []
    for row in rows or []:
        if any(_looks_corrupt_text(row.get(field)) for field in fields):
            continue
        clean.append(row)
    return clean


def _filter_operator_rows(rows, *fields):
    clean = []
    for row in rows or []:
        if any(_looks_corrupt_text(row.get(field)) or _looks_non_business_text(row.get(field)) for field in fields):
            continue
        clean.append(row)
    return clean


def _status_label(value):
    text = str(value or "").strip()
    if not text:
        return "未定"
    if _looks_corrupt_text(text):
        return "未知状态"
    status_map = {
        "active": "启用",
        "inactive": "停用",
        "enabled": "启用",
        "disabled": "停用",
        "normal": "正常",
        "open": "未完成",
        "planned": "已计划",
        "released": "已下达",
        "fulfilled": "已满足",
        "generated": "已生成",
        "posted": "已过账",
        "unpaid": "未付款",
        "paid": "已付款",
        "partial": "部分完成",
        "pending": "待处理",
        "draft": "草稿",
        "closed": "已关闭",
        "completed": "已完成",
        "approved": "已审核",
        "confirmed": "已确认",
        "cancelled": "已取消",
        "canceled": "已取消",
        "void": "已作废",
        "issued": "已开票",
        "running": "执行中",
        "in_progress": "执行中",
        "processing": "加工中",
        "failed": "不合格",
        "pass": "合格",
        "passed": "合格",
    }
    return status_map.get(text.lower(), text)


def _money_metric(value):
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _qty_metric(value):
    try:
        return f"{float(value or 0):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "0"


def _format_timestamp(timestamp):
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, TypeError, ValueError):
        return "-"
