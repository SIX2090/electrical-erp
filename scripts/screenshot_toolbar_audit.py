"""Playwright toolbar / export / print consistency screenshot audit.

Logs in as pilot_admin (sees all menus), visits every visible navigation link,
captures a full-page screenshot, and records toolbar consistency findings:

1. duplicate document-menu-bar instances on a single page
2. duplicate filter / query / reset buttons (toolbar vs in-page filter form)
3. export button placement (inside menu-bar "more" vs loose in section-title vs other)
4. print button placement
5. create / new-document actions leaking into list / report / workbench pages
6. "more" dropdown contents

Output:
    logs/toolbar_audit/screenshots/*.png
    logs/toolbar_audit/findings.json
    logs/toolbar_audit/report.md

Prerequisites:
    - PostgreSQL running
    - ERP running on http://127.0.0.1:5000
    - pilot_admin user ready (password admin)
    - PG_PASSWORD set for trial_audit_auth
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("ERP_TEST_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
OUT_DIR = ROOT / "logs" / "toolbar_audit"
SCREENSHOT_DIR = OUT_DIR / "screenshots"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

# button labels that are considered "filter / query" actions
FILTER_LABELS = {"筛选", "筛选条件", "查询", "重置", "搜索"}
# export labels (must match document_menu_bar macro grouping)
EXPORT_LABELS = {"导出", "导出 CSV", "导出 Excel", "导出 PDF", "XLSX", "CSV", "Excel", "PDF"}
PRINT_LABELS = {"打印", "打印预览", "直接打印"}
# create / new-document labels that must NOT appear on list / report / workbench pages
CREATE_LABELS = {"新增", "新建", "创建", "制单", "新增单据", "新增报价单", "新增销售订单", "新增销售发货单", "新增销售退货单", "新增销售发票"}
# page type classification keywords in URL
LIST_KEYWORDS = ("list", "列表", "-orders", "-receipts", "-returns", "-invoices", "/shipments", "/payables", "/receivables", "/transactions", "/work-orders", "/production-", "/subcontract", "/bom", "/service-", "/quotations", "/purchase", "/sales-")
REPORT_KEYWORDS = ("/reports", "报表", "汇总", "明细", "分析", "对账", "排行", "跟踪", "账龄", "执行")
ENTRY_KEYWORDS = ("/new", "/edit", "录入", "新增", "form")
WORKBENCH_KEYWORDS = ("workbench", "工作台", "/pending", "/approval", "/mrp", "/trace", "/cost", "/projects")


@dataclass
class PageFinding:
    url: str
    label: str
    page_type: str = "unknown"
    status: int = 0
    screenshot: str = ""
    menu_bar_count: int = 0
    duplicate_filter_buttons: list[str] = field(default_factory=list)
    export_locations: list[str] = field(default_factory=list)
    print_locations: list[str] = field(default_factory=list)
    create_actions_on_nonentry: list[str] = field(default_factory=list)
    more_dropdown_items: list[str] = field(default_factory=list)
    section_title_button_count: int = 0
    issues: list[str] = field(default_factory=list)
    error: str = ""


def load_password(username: str) -> str:
    try:
        sys.path.insert(0, str(ROOT))
        from scripts.trial_audit_auth import prepare_trial_audit_passwords

        return prepare_trial_audit_passwords([username]).get(username, "admin")
    except Exception:
        return "admin"


def launch_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True), "playwright chromium"
    except PlaywrightError as first_error:
        for executable in EDGE_CANDIDATES:
            if not executable.exists():
                continue
            try:
                return playwright.chromium.launch(headless=True, executable_path=str(executable)), f"edge: {executable}"
            except PlaywrightError:
                continue
        raise first_error


def classify_page(url: str, label: str) -> str:
    path = url.split(BASE_URL, 1)[-1].split("?", 1)[0].rstrip("/") or "/"
    combined = path + " " + label
    if any(kw in combined for kw in ENTRY_KEYWORDS):
        return "entry"
    if any(kw in combined for kw in WORKBENCH_KEYWORDS):
        return "workbench"
    if any(kw in combined for kw in REPORT_KEYWORDS):
        return "report"
    if any(kw in combined for kw in LIST_KEYWORDS):
        return "list"
    return "other"


def safe_filename(index: int, href: str, label: str) -> str:
    raw = f"{index:03d}_{label}_{href.strip('/') or 'home'}"
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", raw)
    return cleaned.strip("_")[:140] + ".png"


def collect_nav_links(page) -> list[dict]:
    """Collect all navigation links from sidebar DOM (regardless of CSS visibility).

    Submenus are toggled by .flyout-open class and may be hidden by CSS.
    We extract all anchor hrefs directly from the DOM to avoid flaky click-to-expand.
    """
    raw_links = page.eval_on_selector_all(
        "aside.sidebar a[href^='/']",
        """
        els => els.map(a => ({
            href: a.getAttribute('href') || '',
            text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ')
        })).filter(x => x.href && !x.href.startsWith('#'))
        """,
    )
    seen: set[str] = set()
    result: list[dict] = []
    for link in raw_links:
        href = (link.get("href") or "").split("?", 1)[0].rstrip("/")
        if not href or href in seen:
            continue
        seen.add(href)
        text = (link.get("text") or "").strip().replace("\n", " ")
        result.append({"href": href, "label": text or href})
    return result


def analyze_page(page, url: str, label: str, page_type: str) -> PageFinding:
    finding = PageFinding(url=url, label=label, page_type=page_type)

    # 1. count document-menu-bar instances
    menu_bars = page.locator(".document-menu-bar")
    finding.menu_bar_count = menu_bars.count()
    if finding.menu_bar_count > 1:
        finding.issues.append(f"duplicate_document_menu_bar: count={finding.menu_bar_count}")

    # 2. collect all visible button/link texts and their container context
    # We scan for buttons and links whose text matches filter/export/print/create labels
    filter_hits: list[str] = []
    export_hits: list[str] = []
    print_hits: list[str] = []
    create_hits: list[str] = []

    def scan_elements(selector: str, container_label: str):
        loc = page.locator(selector)
        for i in range(min(loc.count(), 200)):
            try:
                el = loc.nth(i)
                if not el.is_visible(timeout=300):
                    continue
                text = (el.inner_text(timeout=300) or "").strip()
                if not text:
                    continue
                # normalize
                norm = text.replace("\n", " ").strip()
                # check first token for label match (buttons often have icon + text)
                first_token = norm.split(" ")[-1] if norm else ""
                matched_label = None
                for lbl in FILTER_LABELS:
                    if norm == lbl or first_token == lbl:
                        matched_label = lbl
                        break
                if matched_label:
                    filter_hits.append(f"{container_label}:{matched_label}")
                    continue
                for lbl in EXPORT_LABELS:
                    if norm == lbl or first_token == lbl:
                        export_hits.append(f"{container_label}:{lbl}")
                        matched_label = lbl
                        break
                if matched_label:
                    continue
                for lbl in PRINT_LABELS:
                    if norm == lbl or first_token == lbl:
                        print_hits.append(f"{container_label}:{lbl}")
                        matched_label = lbl
                        break
                if matched_label:
                    continue
                for lbl in CREATE_LABELS:
                    if norm == lbl or first_token == lbl or norm.startswith(lbl):
                        create_hits.append(f"{container_label}:{norm[:20]}")
                        break
            except Exception:
                continue

    # scan inside document-menu-bar
    scan_elements(".document-menu-bar .document-menu-bar__item", "menu_bar")
    # scan inside dropdown menus (may be hidden until opened, but DOM exists)
    scan_elements(".document-menu-bar .dropdown-item", "more_dropdown")
    # scan inside section-title
    scan_elements(".section-title button, .section-title a", "section_title")
    # scan inside filter-card / page-card forms
    scan_elements(".filter-card button, .filter-card a, .page-card form button", "filter_form")
    # scan inside page-heading
    scan_elements(".page-heading button, .page-heading a", "page_heading")

    # 3. duplicate filter buttons: same filter label appearing in multiple containers
    filter_by_label: dict[str, list[str]] = {}
    for hit in filter_hits:
        container, lbl = hit.split(":", 1)
        filter_by_label.setdefault(lbl, []).append(container)
    for lbl, containers in filter_by_label.items():
        unique_containers = list(dict.fromkeys(containers))
        if len(unique_containers) > 1:
            finding.duplicate_filter_buttons.append(f"{lbl} in {unique_containers}")
            finding.issues.append(f"duplicate_filter_button: {lbl} appears in {unique_containers}")

    # 4. export locations
    finding.export_locations = list(dict.fromkeys(export_hits))
    if not finding.export_locations and page_type in ("list", "report"):
        finding.issues.append("missing_export_on_list_or_report")
    # export should be in more_dropdown (grouped by macro), not loose in section_title
    export_in_section = [h for h in export_hits if h.startswith("section_title:")]
    if export_in_section:
        finding.issues.append(f"export_loose_in_section_title: {export_in_section}")

    # 5. print locations
    finding.print_locations = list(dict.fromkeys(print_hits))
    if not finding.print_locations and page_type in ("entry", "report"):
        finding.issues.append("missing_print_on_entry_or_report")

    # 6. create actions on non-entry pages
    if page_type in ("list", "report", "workbench"):
        finding.create_actions_on_nonentry = list(dict.fromkeys(create_hits))
        if create_hits:
            finding.issues.append(f"create_action_on_{page_type}: {create_hits[:5]}")

    # 7. more dropdown items
    more_items = page.locator(".document-menu-bar .document-menu-bar__dropdown .dropdown-item")
    for i in range(min(more_items.count(), 50)):
        try:
            text = (more_items.nth(i).inner_text(timeout=300) or "").strip()
            if text:
                finding.more_dropdown_items.append(text)
        except Exception:
            continue

    # 8. section-title button count (loose buttons in section titles)
    section_btns = page.locator(".section-title button, .section-title a")
    finding.section_title_button_count = section_btns.count()
    if finding.section_title_button_count > 2 and page_type == "list":
        finding.issues.append(f"many_buttons_in_section_title: count={finding.section_title_button_count}")

    return finding


def login(page, username: str, password: str):
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.wait_for_selector("input[name='username']", timeout=10_000)
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    try:
        page.wait_for_url(lambda url: "/login" not in url, timeout=8_000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(500)
    if "/login" in page.url and page.locator("input[name='username']").count() > 0:
        raise RuntimeError(f"login failed for {username}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    username = "pilot_admin"
    password = load_password(username)

    findings: list[dict] = []
    started = datetime.now()

    with sync_playwright() as p:
        try:
            browser, browser_runtime = launch_browser(p)
        except PlaywrightError as exc:
            print("toolbar_audit=blocked")
            print(f"reason={str(exc).splitlines()[0]}")
            return 2
        print(f"browser_runtime={browser_runtime}")

        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        responses: dict[str, int] = {}

        def record_response(response):
            u = response.url.split("#", 1)[0]
            if u.startswith(BASE_URL):
                responses[u.split("?")[0]] = response.status

        page.on("response", record_response)

        # login
        login(page, username, password)
        print(f"login_ok user={username}")

        # collect nav links
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        nav_links = collect_nav_links(page)
        print(f"nav_links_found count={len(nav_links)}")

        # screenshot home
        home_shot = SCREENSHOT_DIR / "000_home.png"
        page.screenshot(path=str(home_shot), full_page=True)
        home_finding = analyze_page(page, f"{BASE_URL}/", "首页", "workbench")
        home_finding.status = 200
        home_finding.screenshot = str(home_shot.relative_to(ROOT))
        findings.append(asdict(home_finding))

        # visit each nav link
        for index, link in enumerate(nav_links, start=1):
            href = link["href"]
            label = link["label"]
            url = urljoin(BASE_URL + "/", href)
            page_type = classify_page(url, label)
            shot_name = safe_filename(index, href, label)
            shot_path = SCREENSHOT_DIR / shot_name

            finding = PageFinding(url=url, label=label, page_type=page_type, screenshot=str(shot_path.relative_to(ROOT)))
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(600)
                status = responses.get(url.rstrip("/"), responses.get(url, 0))
                finding.status = status or 200
                page.screenshot(path=str(shot_path), full_page=True)
                finding = analyze_page(page, url, label, page_type)
                finding.status = status or 200
                finding.screenshot = str(shot_path.relative_to(ROOT))
            except PlaywrightTimeoutError:
                finding.error = "timeout"
                finding.issues.append("page_load_timeout")
                try:
                    page.screenshot(path=str(shot_path), full_page=True)
                    finding.screenshot = str(shot_path.relative_to(ROOT))
                except Exception:
                    pass
            except Exception as exc:
                finding.error = str(exc)[:200]
                finding.issues.append(f"error: {finding.error[:80]}")

            findings.append(asdict(finding))
            issue_str = f" issues={finding.issues}" if finding.issues else ""
            print(f"[{index:03d}] {label} ({page_type}) status={finding.status}{issue_str}")

        browser.close()

    # write JSON
    json_path = OUT_DIR / "findings.json"
    json_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")

    # write Markdown report
    report_lines = [
        "# ERP Toolbar / Export / Print Consistency Audit Report",
        "",
        f"- Generated: {started.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Base URL: {BASE_URL}",
        f"- Role: {username}",
        f"- Pages checked: {len(findings)}",
        "",
    ]

    pages_with_issues = [f for f in findings if f.get("issues")]
    pages_ok = [f for f in findings if not f.get("issues")]
    report_lines.extend([
        "## Summary",
        "",
        f"- Pages with issues: **{len(pages_with_issues)}**",
        f"- Pages clean: {len(pages_ok)}",
        "",
    ])

    # issue type counts
    issue_types: dict[str, int] = {}
    for f in pages_with_issues:
        for issue in f.get("issues", []):
            key = issue.split(":")[0]
            issue_types[key] = issue_types.get(key, 0) + 1
    if issue_types:
        report_lines.append("### Issue Type Counts")
        report_lines.append("")
        report_lines.append("| Issue Type | Count |")
        report_lines.append("|------------|-------|")
        for key, count in sorted(issue_types.items(), key=lambda x: -x[1]):
            report_lines.append(f"| {key} | {count} |")
        report_lines.append("")

    # detailed findings by page type
    for ptype in ("entry", "list", "report", "workbench", "other"):
        type_findings = [f for f in findings if f.get("page_type") == ptype]
        if not type_findings:
            continue
        report_lines.append(f"## {ptype.capitalize()} Pages ({len(type_findings)})")
        report_lines.append("")
        report_lines.append("| # | Label | URL | Status | Menu Bars | Issues | Screenshot |")
        report_lines.append("|---|-------|-----|--------|-----------|--------|------------|")
        for i, f in enumerate(type_findings, 1):
            issues = "; ".join(f.get("issues", [])) or "OK"
            url_short = f.get("url", "").replace(BASE_URL, "")
            report_lines.append(f"| {i} | {f.get('label','')} | {url_short} | {f.get('status','')} | {f.get('menu_bar_count',0)} | {issues} | {f.get('screenshot','')} |")
        report_lines.append("")

    # duplicate filter buttons detail
    dup_filter = [f for f in findings if any("duplicate_filter_button" in i for i in f.get("issues", []))]
    if dup_filter:
        report_lines.append(f"## Duplicate Filter / Query Buttons ({len(dup_filter)})")
        report_lines.append("")
        for f in dup_filter:
            report_lines.append(f"### {f.get('label')} - {f.get('url','')}")
            report_lines.append("")
            for dup in f.get("duplicate_filter_buttons", []):
                report_lines.append(f"- {dup}")
            report_lines.append(f"- Screenshot: {f.get('screenshot','')}")
            report_lines.append("")

    # export placement detail
    export_issues = [f for f in findings if any("export_loose" in i or "missing_export" in i for i in f.get("issues", []))]
    if export_issues:
        report_lines.append(f"## Export Placement Issues ({len(export_issues)})")
        report_lines.append("")
        report_lines.append("| Label | URL | Export Locations | Issue | Screenshot |")
        report_lines.append("|-------|-----|-------------------|-------|------------|")
        for f in export_issues:
            issue = "; ".join(i for i in f.get("issues", []) if "export" in i)
            report_lines.append(f"| {f.get('label','')} | {f.get('url','').replace(BASE_URL,'')} | {', '.join(f.get('export_locations',[]))} | {issue} | {f.get('screenshot','')} |")
        report_lines.append("")

    # create actions on non-entry pages
    create_issues = [f for f in findings if any("create_action" in i for i in f.get("issues", []))]
    if create_issues:
        report_lines.append(f"## Create Actions on Non-Entry Pages ({len(create_issues)})")
        report_lines.append("")
        for f in create_issues:
            report_lines.append(f"### {f.get('label')} ({f.get('page_type','')}) - {f.get('url','')}")
            report_lines.append("")
            for ca in f.get("create_actions_on_nonentry", []):
                report_lines.append(f"- {ca}")
            report_lines.append(f"- Screenshot: {f.get('screenshot','')}")
            report_lines.append("")

    # print placement detail
    print_issues = [f for f in findings if any("missing_print" in i for i in f.get("issues", []))]
    if print_issues:
        report_lines.append(f"## Missing Print on Entry/Report Pages ({len(print_issues)})")
        report_lines.append("")
        report_lines.append("| Label | URL | Page Type | Screenshot |")
        report_lines.append("|-------|-----|-----------|------------|")
        for f in print_issues:
            report_lines.append(f"| {f.get('label','')} | {f.get('url','').replace(BASE_URL,'')} | {f.get('page_type','')} | {f.get('screenshot','')} |")
        report_lines.append("")

    report_path = OUT_DIR / "report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"\ntoolbar_audit=done")
    print(f"pages_checked={len(findings)}")
    print(f"pages_with_issues={len(pages_with_issues)}")
    print(f"screenshots_dir={SCREENSHOT_DIR}")
    print(f"report={report_path}")
    print(f"json={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
