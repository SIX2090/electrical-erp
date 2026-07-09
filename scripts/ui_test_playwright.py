"""Playwright UI 自动化测试 - 方案 C。

用 7 个 pilot 角色登录 ERP，遍历可见菜单，检查页面错误、表单元素状态、
按钮可用性，并截图保存。专注于发现工具栏、菜单栏、文本框、选择框、
命令按钮等 UI 层 BUG。

前置条件:
1. PostgreSQL 已启动且 ERP 数据库可连接
2. pilot 用户已创建并激活（密码统一为 admin）
3. ERP 应用已在 http://127.0.0.1:5000 运行
   或通过 --start-app 参数自动启动

使用方式:
    python scripts/ui_test_playwright.py                    # 跑全部 7 个角色
    python scripts/ui_test_playwright.py --role pilot_admin # 只跑指定角色
    python scripts/ui_test_playwright.py --headed            # 有头模式（调试用）
    python scripts/ui_test_playwright.py --report md         # 生成 Markdown 报告
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
PYTHON = sys.executable
BASE_URL = os.environ.get("ERP_TEST_BASE_URL", "http://127.0.0.1:5000")
OUT_DIR = ROOT / "logs" / "ui_test"
SCREENSHOT_DIR = OUT_DIR / "screenshots"

EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

# pilot 角色 → ERP 角色映射
PILOT_ROLES = [
    "pilot_admin",
    "pilot_sales",
    "pilot_purchase",
    "pilot_warehouse",
    "pilot_production",
    "pilot_service",
    "pilot_finance",
]

# 页面错误标记
BAD_TEXT_PATTERNS = (
    "\ufffd",          # 替换字符
    "Traceback",
    "Internal Server Error",
    "Not Found",
    "Method Not Allowed",
    "UndefinedColumn",
    "ProgrammingError",
    "OperationalError",
    "NotNullViolation",
    "psycopg2.Error",
)

# 不应该出现在正常页面中的文本
MOJIBAKE_MARKERS = (
    "\ufffd\ufffd",    # 连续替换字符
    "???",
    "æ\x9c\x8d",       # 常见 UTF-8 被当 Latin1 解释的乱码
)


@dataclass
class PageFinding:
    """单个页面检查结果。"""

    role: str
    url: str
    label: str
    status: int = 0
    title: str = ""
    issues: list[str] = field(default_factory=list)
    forms: int = 0
    inputs: int = 0
    selects: int = 0
    buttons: int = 0
    disabled_buttons: int = 0
    required_inputs: int = 0
    screenshot: str = ""
    error_detail: str = ""


@dataclass
class RoleResult:
    """单个角色的测试结果。"""

    role: str
    login_success: bool = False
    menu_links: int = 0
    pages_checked: int = 0
    pages_with_issues: int = 0
    findings: list[PageFinding] = field(default_factory=list)
    duration: float = 0.0
    error: str = ""


def load_password(username: str) -> str:
    """获取 pilot 用户密码（默认 admin）。"""
    try:
        sys.path.insert(0, str(ROOT))
        from scripts.trial_audit_auth import prepare_trial_audit_passwords

        return prepare_trial_audit_passwords([username]).get(username, "admin")
    except Exception:
        return "admin"


def safe_name(role: str, index: int, href: str, label: str) -> str:
    """生成安全的截图文件名。"""
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", f"{role}_{index:03d}_{label}_{href.strip('/') or 'home'}")
    return cleaned.strip("_")[:120] + ".png"


def launch_browser(playwright, headless: bool = True):
    """启动浏览器，优先用 Playwright Chromium，备选 Edge。"""
    from playwright.sync_api import Error as PlaywrightError

    try:
        return playwright.chromium.launch(headless=headless), "playwright chromium"
    except PlaywrightError as first_error:
        for executable in EDGE_CANDIDATES:
            if not executable.exists():
                continue
            try:
                return playwright.chromium.launch(
                    headless=headless, executable_path=str(executable)
                ), f"edge: {executable.name}"
            except PlaywrightError:
                continue
        raise first_error


def login(page, username: str, password: str) -> bool:
    """登录 ERP，返回是否成功。"""
    page.goto(BASE_URL + "/", wait_until="networkidle", timeout=30000)
    if not page.locator("input[name='username']").count():
        return True  # 已经登录

    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle", timeout=15000)

    # 登录成功后应该不再有用户名输入框
    return page.locator("input[name='username']").count() == 0


def collect_menu_links(page) -> list[dict]:
    """收集页面上的导航菜单链接。"""
    links = page.eval_on_selector_all(
        "a[data-nav-link], .sidebar a[href], nav a[href]",
        """
        els => els.map(a => ({
            href: a.getAttribute('href') || '',
            text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ')
        })).filter(x => x.href && !x.href.startsWith('#') && !x.href.startsWith('javascript'))
        """,
    )
    seen = set()
    unique = []
    for link in links:
        key = (link["href"], link["text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(link)
    return unique


def check_page(page, role: str, href: str, label: str, index: int) -> PageFinding:
    """检查单个页面，返回检查结果。"""
    url = urljoin(BASE_URL + "/", href)
    finding = PageFinding(role=role, url=url, label=label)

    try:
        response = page.goto(url, wait_until="networkidle", timeout=30000)
        finding.status = response.status if response else 0

        if finding.status and finding.status >= 400:
            finding.issues.append(f"http_{finding.status}")

        finding.title = page.title()

        # 检查页面正文
        body_text = page.locator("body").inner_text(timeout=5000)
        if len(body_text.strip()) < 40:
            finding.issues.append("blank_or_too_little_text")

        for pattern in BAD_TEXT_PATTERNS:
            if pattern in body_text or pattern in finding.title:
                finding.issues.append(f"bad_text:{pattern[:30]}")

        for pattern in MOJIBAKE_MARKERS:
            if pattern in body_text:
                finding.issues.append("mojibake")
                break

        # 检查 alert-danger
        if page.locator(".alert-danger").count():
            try:
                danger_text = page.locator(".alert-danger").first.inner_text(timeout=2000)
                if danger_text.strip():
                    finding.issues.append("alert_danger")
                    finding.error_detail = danger_text.strip()[:200]
            except Exception:
                pass

        # 统计表单元素
        finding.forms = page.locator("form").count()
        finding.inputs = page.locator("input").count()
        finding.selects = page.locator("select").count()
        finding.buttons = page.locator("button").count()
        finding.disabled_buttons = page.locator("button[disabled]").count()
        finding.required_inputs = page.locator("input[required]").count()

        # 截图
        screenshot_path = SCREENSHOT_DIR / safe_name(role, index, href, label)
        page.screenshot(path=str(screenshot_path), full_page=True)
        finding.screenshot = str(screenshot_path)

    except Exception as exc:
        finding.issues.append("exception")
        finding.error_detail = str(exc)[:200]

    return finding


def test_role(browser, role: str, headless: bool) -> RoleResult:
    """测试单个角色的所有可见页面。"""
    result = RoleResult(role=role)
    start = time.time()
    password = load_password(role)

    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()

    try:
        # 登录
        if not login(page, role, password):
            result.login_success = False
            result.error = "登录失败"
            return result
        result.login_success = True

        # 收集菜单链接
        links = collect_menu_links(page)
        result.menu_links = len(links)

        # 截图首页
        home_finding = check_page(page, role, "/", "首页", 0)
        result.findings.append(home_finding)

        # 遍历每个菜单链接
        for index, link in enumerate(links, start=1):
            href = link["href"]
            label = link["text"] or href
            finding = check_page(page, role, href, label, index)
            result.findings.append(finding)

        result.pages_checked = len(result.findings)
        result.pages_with_issues = sum(1 for f in result.findings if f.issues)

    except Exception as exc:
        result.error = str(exc)[:200]
    finally:
        context.close()

    result.duration = time.time() - start
    return result


def run_ui_tests(roles: list[str], headless: bool = True) -> list[RoleResult]:
    """运行 UI 测试。"""
    from playwright.sync_api import Error as PlaywrightError, sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[RoleResult] = []

    print(f"\n{'=' * 70}")
    print(f"Playwright UI 自动化测试 - {len(roles)} 个角色")
    print(f"{'=' * 70}\n")

    with sync_playwright() as p:
        try:
            browser, browser_runtime = launch_browser(p, headless=headless)
        except PlaywrightError as exc:
            print(f"错误: 无法启动浏览器 - {exc}")
            print(f"提示: 运行 {PYTHON} -m playwright install chromium")
            return results
        print(f"浏览器: {browser_runtime}\n")

        for role in roles:
            print(f"[{role}] 测试中...")
            result = test_role(browser, role, headless)
            results.append(result)

            if result.error and not result.login_success:
                print(f"  ✗ 登录失败: {result.error}")
            else:
                status = "✓" if result.pages_with_issues == 0 else "⚠"
                print(
                    f"  {status} 菜单 {result.menu_links} 项，"
                    f"检查 {result.pages_checked} 页，"
                    f"问题 {result.pages_with_issues} 项，"
                    f"耗时 {result.duration:.1f}s"
                )
            print()

        browser.close()

    return results


def print_summary(results: list[RoleResult]) -> int:
    """打印汇总报告，返回问题总数。"""
    total_roles = len(results)
    successful_logins = sum(1 for r in results if r.login_success)
    total_pages = sum(r.pages_checked for r in results)
    total_issues = sum(r.pages_with_issues for r in results)

    print(f"\n{'=' * 70}")
    print(f"UI 测试汇总")
    print(f"{'=' * 70}")
    print(f"  角色: {total_roles}    登录成功: {successful_logins}    登录失败: {total_roles - successful_logins}")
    print(f"  检查页面: {total_pages}    有问题的页面: {total_issues}")
    print()

    print(f"{'角色':<20} {'登录':>6} {'菜单':>6} {'检查':>6} {'问题':>6} {'耗时':>8}")
    print(f"{'─' * 55}")
    for r in results:
        login_status = "✓" if r.login_success else "✗"
        print(f"{r.role:<20} {login_status:>6} {r.menu_links:>6} {r.pages_checked:>6} {r.pages_with_issues:>6} {r.duration:>7.1f}s")

    # 问题明细
    all_issues = []
    for r in results:
        for f in r.findings:
            if f.issues:
                all_issues.append(f)
    if all_issues:
        print(f"\n{'─' * 70}")
        print(f"问题明细（{len(all_issues)} 项）")
        print(f"{'─' * 70}")
        for f in all_issues[:30]:  # 只显示前 30 个
            print(f"\n  [{f.role}] {f.label} ({f.url})")
            print(f"    状态: {f.status}, 问题: {', '.join(f.issues)}")
            if f.error_detail:
                print(f"    详情: {f.error_detail[:100]}")
        if len(all_issues) > 30:
            print(f"\n  ... 还有 {len(all_issues) - 30} 项问题，详见 JSON 报告")

    print(f"\n{'=' * 70}")
    if total_issues == 0:
        print(f"结果: 全部通过 ✓")
    else:
        print(f"结果: {total_issues} 项问题 ✗")
    print(f"{'=' * 70}\n")

    return total_issues


def save_json_report(results: list[RoleResult]) -> Path:
    """保存 JSON 报告。"""
    report_path = OUT_DIR / "ui_test_findings.json"
    data = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "roles": [asdict(r) for r in results],
    }
    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def save_markdown_report(results: list[RoleResult]) -> Path:
    """保存 Markdown 报告。"""
    report_path = OUT_DIR / "ui_test_report.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_roles = len(results)
    successful_logins = sum(1 for r in results if r.login_success)
    total_pages = sum(r.pages_checked for r in results)
    total_issues = sum(r.pages_with_issues for r in results)

    lines = [
        "# Playwright UI 测试报告",
        "",
        f"- 生成时间: {now}",
        f"- 基础 URL: {BASE_URL}",
        f"- 角色数: {total_roles}",
        f"- 登录成功: {successful_logins}",
        f"- 检查页面: {total_pages}",
        f"- 问题页面: {total_issues}",
        "",
        "## 角色汇总",
        "",
        "| 角色 | 登录 | 菜单数 | 检查页数 | 问题页数 | 耗时 |",
        "|------|------|--------|----------|----------|------|",
    ]
    for r in results:
        login_status = "✓" if r.login_success else "✗"
        lines.append(f"| {r.role} | {login_status} | {r.menu_links} | {r.pages_checked} | {r.pages_with_issues} | {r.duration:.1f}s |")

    all_issues = [f for r in results for f in r.findings if f.issues]
    if all_issues:
        lines.extend(["", "## 问题明细", "", "| 角色 | 页面 | URL | 状态 | 问题 |", "|------|------|-----|------|------|"])
        for f in all_issues:
            issues_str = ", ".join(f.issues)
            lines.append(f"| {f.role} | {f.label} | {f.url} | {f.status} | {issues_str} |")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright UI 自动化测试")
    parser.add_argument("--role", help="只测试指定角色（如 pilot_admin），默认全部 7 个角色")
    parser.add_argument("--headed", action="store_true", help="有头模式（显示浏览器窗口，调试用）")
    parser.add_argument("--report", choices=["text", "md", "json"], default="text", help="报告格式")
    args = parser.parse_args()

    roles = [args.role] if args.role else PILOT_ROLES.copy()

    results = run_ui_tests(roles, headless=not args.headed)
    if not results:
        return 2

    total_issues = print_summary(results)

    if args.report in ("md", "json"):
        json_path = save_json_report(results)
        print(f"JSON 报告: {json_path}")
    if args.report == "md":
        md_path = save_markdown_report(results)
        print(f"Markdown 报告: {md_path}")

    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
