from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.script_quarantine import audit_quarantine


SCAN_DIRS = ("app.py", "routes", "services", "scripts", "tests", "waitress_server.py")
IGNORED_PARTS = {"__pycache__", ".pytest_cache", "output", "logs", "backups", "restore_zip"}

# Core .md rule files that must also be scanned for mojibake
SCAN_MD_FILES = (
    "AGENTS.md",
    "MENU_ROLLOUT_CLASSIFICATION.md",
    "ERP_BOUNDARY_STABILIZATION.md",
    "ERP_SCOPE_PLAN.md",
)

DIRTY_CODEPOINTS = {
    0xFFFD,  # replacement character
    # Existing mojibake codepoints
    0x95C1, 0x95BF, 0x9359, 0x934F, 0x9351, 0x9352, 0x935B,
    0x9366, 0x9368, 0x937C, 0x6434, 0x9417, 0x9422, 0x93C2,
    0x95B2, 0x7487, 0x5BEF, 0x6FEE, 0x8930, 0x7BDB, 0x7DCB,
    0x7EEF, 0x95AB, 0x9A9E,
    # Expanded: common GBK-decoded-UTF8 mojibake characters (by codepoint)
    # U+951B U+9427 U+7490 U+93B6 U+9225 U+9286
    0x951B, 0x9427, 0x7490, 0x93B6, 0x9225, 0x9286,
    # U+6D93 U+7ECB U+9357 U+93C1 U+95C2 U+59AF U+6924
    0x6D93, 0x7ECB, 0x9357, 0x93C1, 0x95C2, 0x59AF, 0x6924,
    # U+93BC U+590C U+5BB8 U+53C9 U+5F41 U+6D5C
    0x93BC, 0x590C, 0x5BB8, 0x53C9, 0x5F41, 0x6D5C,
    # U+8BF2 U+7D8D U+9422 U+93B4 U+9428 U+9429
    0x8BF2, 0x7D8D, 0x93B4, 0x9428, 0x9429,
    # U+942E U+942D U+942C U+942F U+9430 U+9431
    0x942E, 0x942D, 0x942C, 0x942F, 0x9430, 0x9431,
    # U+93B5 U+93B7 U+93BA U+93BB U+93BC
    0x93B5, 0x93B7, 0x93BA, 0x93BB,
    # U+6D94 U+6D98 U+6D9B U+6DA9 U+6DAA
    0x6D94, 0x6D98, 0x6D9B, 0x6DA9, 0x6DAA,
    # U+7F5B U+701B U+701C U+701D U+701E
    0x7F5B, 0x701B, 0x701C, 0x701D, 0x701E,
}
DIRTY_CHAR_CODEPOINTS = {0x20AC, 0x2122, 0x0153}  # euro, trademark, oe-ligature
DIRTY_TEXT_MARKER_PARTS = (
    (0x5BF0, 0x546E, 0x5F41, 0x6D5C),
    (0x5BB8, 0x53C9, 0x5F41, 0x6D5C),  # "submitted" mojibake marker
    (0x59DD, 0xFF45, 0x7236),
    (0x947D, 0x5926),
    (0x701A, 0xFF05),
    (0x6D63, 0xFF53),
    (0x6FEE, 0x892A),
    # "draft" mojibake marker (U+93BC U+590C)
    (0x93BC, 0x590C),
    # "login" mojibake marker (U+9427 U+8BF2 U+7D8D)
    (0x9427, 0x8BF2, 0x7D8D),
)


def iter_python_files():
    for entry in SCAN_DIRS:
        path = ROOT / entry
        if path.is_file() and path.suffix == ".py":
            yield path
        elif path.is_dir():
            for file_path in path.rglob("*.py"):
                if not (set(file_path.parts) & IGNORED_PARTS):
                    yield file_path


def has_mojibake(text: str) -> bool:
    if any(ord(ch) in DIRTY_CODEPOINTS or ord(ch) in DIRTY_CHAR_CODEPOINTS for ch in text):
        return True
    return any("".join(chr(part) for part in marker) in text for marker in DIRTY_TEXT_MARKER_PARTS)


def audit_sources():
    findings = []
    for file_path in sorted(iter_python_files()):
        rel = file_path.relative_to(ROOT)
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            findings.append(f"{rel}: utf-8 decode failed: {exc}")
            continue
        try:
            ast.parse(text, filename=str(rel))
        except SyntaxError as exc:
            findings.append(f"{rel}:{exc.lineno}: syntax error: {exc.msg}")
    return findings


def audit_cross_file_contamination():
    findings = []
    report_markers = (
        "ERP Document Field Comprehensive Audit Report",
        "Summary: 12 Major Issues Identified Across ERP Document Tables",
        "ISSUE 1: Inconsistent Document Number Field Naming",
    )
    template_markers = (
        '{% extends "base.html" %}',
        "{% block content %}",
        'class="page-heading order-form-heading"',
    )
    for template_path in sorted((ROOT / "templates").rglob("*.html")):
        try:
            text = template_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            findings.append(f"{template_path.relative_to(ROOT)}: read failed: {exc}")
            continue
        for marker in report_markers:
            if marker in text:
                findings.append(f"{template_path.relative_to(ROOT)}: audit report content written into template: {marker}")
                break
    for report_name in ("file1.txt", "file.txt"):
        report_path = ROOT / report_name
        if not report_path.exists():
            continue
        text = report_path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in template_markers) and not any(marker in text for marker in report_markers):
            findings.append(f"{report_name}: template content written into report target")
    return findings


def audit_mojibake_sources():
    findings = []
    question_marker = chr(63) * 3
    scan_bases = [
        ROOT / "templates",
        ROOT / "routes",
        ROOT / "scripts",
        ROOT / "services",
        ROOT / "app.py",
    ]
    for base in scan_bases:
        if base.is_file():
            file_paths = [base]
        else:
            file_paths = sorted(base.rglob("*"))
        for file_path in file_paths:
            if file_path.suffix.lower() not in {".html", ".py"}:
                continue
            if set(file_path.parts) & IGNORED_PARTS:
                continue
            rel = file_path.relative_to(ROOT)
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), 1):
                if has_mojibake(line):
                    findings.append(f"{rel}:{line_no}: possible mojibake: {line.strip()[:160]}")
                if "scripts" not in str(rel) and question_marker in line:
                    findings.append(f"{rel}:{line_no}: replacement question marks: {line.strip()[:160]}")

    # Scan core .md rule files for mojibake
    for md_name in SCAN_MD_FILES:
        md_path = ROOT / md_name
        if not md_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if has_mojibake(line):
                findings.append(f"{md_name}:{line_no}: possible mojibake: {line.strip()[:160]}")
            if question_marker in line:
                findings.append(f"{md_name}:{line_no}: replacement question marks: {line.strip()[:160]}")

    return findings


def audit_warnings():
    return []


def safe_print(text: str) -> None:
    print(text.encode("ascii", "backslashreplace").decode("ascii"))


def main():
    findings = audit_sources()
    findings.extend(audit_cross_file_contamination())
    mojibake_findings = audit_mojibake_sources()
    findings.extend(mojibake_findings)
    findings.extend(audit_quarantine())
    print(f"source_mojibake_findings={len(mojibake_findings)}")
    if findings:
        print("source_integrity=failed")
        for item in findings:
            safe_print(item)
        return 1
    print("source_integrity=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
