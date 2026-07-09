from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "templates" / "base.html"
PYTHON_SOURCES = [ROOT / "app.py", *sorted((ROOT / "routes").glob("*.py"))]
FORBIDDEN_ROOT_LINKS = {"/inventory", "/sales", "/purchase_order", "/production", "/service", "/finance"}
MASTER_DATA_ENTRY_PATHS = {"/engineering/drawings/new"}
ROUTE_LITERAL_RE = re.compile(r"""["'](/[^"'?#\s]*)["']""")
NAV_LINK_RE = re.compile(r"""<a\s+[^>]*href=["'](?P<href>/[^"'?#]*)["'][^>]*data-nav-link""")
SUBMENU_LABEL_RE = re.compile(r"""<div\s+class=["']submenu-label["']>(?P<label>.*?)</div>""")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def collect_declared_paths() -> set[str]:
    paths = set()
    for source in PYTHON_SOURCES:
        if not source.exists():
            continue
        text = read_text(source)
        for match in ROUTE_LITERAL_RE.finditer(text):
            value = match.group(1).rstrip("/") or "/"
            if value.startswith(("/static/", "/api/")):
                continue
            paths.add(value)
    return paths


def route_matches(href: str, declared_paths: set[str]) -> bool:
    href = href.rstrip("/") or "/"
    if href in declared_paths:
        return True
    for pattern in declared_paths:
        regex = re.escape(pattern)
        regex = re.sub(r"\\<int:[^>]+\\>", r"\\d+", regex)
        regex = re.sub(r"\\<string:[^>]+\\>", r"[^/]+", regex)
        regex = re.sub(r"\\<path:[^>]+\\>", r".+", regex)
        if re.fullmatch(regex, href):
            return True
    return False


def collect_nav_links() -> list[dict[str, object]]:
    links = []
    current_group = ""
    for line_no, line in enumerate(read_text(BASE_TEMPLATE).splitlines(), start=1):
        label_match = SUBMENU_LABEL_RE.search(line)
        if label_match:
            current_group = re.sub(r"<[^>]+>", "", label_match.group("label")).strip()
            continue
        link_match = NAV_LINK_RE.search(line)
        if link_match:
            href = link_match.group("href").rstrip("/") or "/"
            text = re.sub(r"<[^>]+>", "", line).strip()
            links.append({"line": line_no, "href": href, "text": text, "group": current_group})
    return links


def check_group_separation(links: list[dict[str, object]]) -> list[str]:
    failures = []
    for link in links:
        href = str(link["href"])
        if href in MASTER_DATA_ENTRY_PATHS:
            continue
        group = str(link["group"])
        line = int(link["line"])
        if not group:
            continue
        if href.endswith("/new") and ("列表" in group or "查询" in group or "报表" in group):
            failures.append(f"line {line}: create link {href} is under non-entry group {group}")
        if not href.endswith("/new") and "单据" in group and "列表" not in group:
            failures.append(f"line {line}: non-create link {href} is under entry group {group}")
        if href.endswith("/new") and "单据" not in group:
            failures.append(f"line {line}: create link {href} is not under a document-entry group")
    return failures


def main() -> int:
    declared_paths = collect_declared_paths()
    links = collect_nav_links()
    failures = []
    warnings = []

    for link in links:
        href = str(link["href"])
        line = int(link["line"])
        if href in FORBIDDEN_ROOT_LINKS:
            failures.append(f"line {line}: forbidden root/workbench link {href}")
        if not route_matches(href, declared_paths):
            failures.append(f"line {line}: nav link has no matching route literal {href}")

    failures.extend(check_group_separation(links))

    counts = Counter(str(link["href"]) for link in links)
    duplicate_map = defaultdict(list)
    for link in links:
        href = str(link["href"])
        if counts[href] > 1:
            duplicate_map[href].append(int(link["line"]))
    for href, lines in sorted(duplicate_map.items()):
        warnings.append(f"duplicate nav link {href} at lines {lines}")

    print(f"navigation_integrity={'failed' if failures else 'ok'}")
    print(f"checked_links={len(links)}")
    print(f"declared_paths={len(declared_paths)}")
    if failures:
        print("failures:")
        for item in failures:
            print(f"- {item}")
    if warnings:
        print("warnings:")
        for item in warnings:
            print(f"- {item}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
