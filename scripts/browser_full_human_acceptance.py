from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "logs" / "browser_full_human_acceptance"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("ERP_BROWSER_TEST_URL", "http://127.0.0.1:5000").rstrip("/")
FULL_NAV = os.environ.get("ERP_BROWSER_FULL_NAV", "0").strip().lower() in {"1", "true", "yes", "on"}
MAX_NAV_LINKS = int(os.environ.get("ERP_BROWSER_MAX_NAV_LINKS", "10"))
EDGE_PATHS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

DEFAULT_ROLE_USERS = [
    "pilot_admin",
    "pilot_sales",
    "pilot_purchase",
    "pilot_warehouse",
    "pilot_production",
    "pilot_service",
    "pilot_finance",
]
ROLE_USERS = [item.strip() for item in os.environ.get("ERP_BROWSER_USERS", ",".join(DEFAULT_ROLE_USERS)).split(",") if item.strip()]

KEY_INTERACTION_PATHS = {
    "pilot_admin": ["/system_settings/form", "/system/database-backups", "/system/data-health"],
    "pilot_sales": ["/sales/new", "/sales-orders", "/shipments"],
    "pilot_purchase": ["/purchase_request/new", "/purchase-orders", "/purchase_receipts"],
    "pilot_warehouse": ["/inventory/detail", "/transactions", "/transfers/new"],
    "pilot_production": ["/work-orders/new", "/work-orders", "/production-schedules"],
    "pilot_service": ["/service-orders/new", "/service-orders", "/service-rmas"],
    "pilot_finance": ["/receivables", "/payables", "/finance/reports/aging"],
}


def load_passwords() -> dict[str, str]:
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords()

def edge_executable() -> str | None:
    for path in EDGE_PATHS:
        if path.exists():
            return str(path)
    return None


def visible_links(page) -> list[str]:
    parents = page.locator("aside.sidebar .menu-parent")
    for i in range(parents.count()):
        parent = parents.nth(i)
        try:
            if parent.is_visible(timeout=500):
                box = parent.bounding_box()
                if box:
                    page.mouse.move(box["x"] + 12, box["y"] + 12)
                    page.mouse.click(box["x"] + 12, box["y"] + 12)
                    page.wait_for_timeout(80)
        except Exception:
            continue
    links = page.locator("aside.sidebar a[href^='/']")
    hrefs: list[str] = []
    for i in range(links.count()):
        try:
            if not links.nth(i).is_visible(timeout=500):
                continue
        except Exception:
            continue
        href = links.nth(i).get_attribute("href") or ""
        href = href.split("?", 1)[0].rstrip("/") or "/"
        if href.startswith("/") and href not in hrefs:
            hrefs.append(href)
    return hrefs


def has_dirty_text(text: str) -> bool:
    dirty_chars = "".join(chr(codepoint) for codepoint in (0xFFFD, 0x951F))
    return bool(re.search("[" + re.escape(dirty_chars) + r"]|\?{4,}", text or ""))


def human_login(page, username: str, password: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.wait_for_selector("input[name='username']", timeout=10_000)
    user = page.locator("input[name='username']")
    pw = page.locator("input[name='password']")
    box = user.bounding_box()
    if box:
        page.mouse.move(box["x"] + 8, box["y"] + 8)
        page.mouse.click(box["x"] + 8, box["y"] + 8)
    user.fill("")
    page.keyboard.type(username, delay=12)
    box = pw.bounding_box()
    if box:
        page.mouse.move(box["x"] + 8, box["y"] + 8)
        page.mouse.click(box["x"] + 8, box["y"] + 8)
    pw.fill("")
    page.keyboard.type(password, delay=12)
    page.keyboard.press("Enter")
    try:
        page.wait_for_url(lambda url: "/login" not in url, timeout=5_000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)
    if "/login" in page.url and page.locator("input[name='username']").count() > 0:
        raise RuntimeError(f"login failed for {username}")


def click_nav_link(page, href: str) -> dict[str, object]:
    result = {"path": href, "ok": True, "issues": []}
    selector = f"aside.sidebar a[href='{href}'], aside.sidebar a[href='{href}/']"
    try:
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_timeout(120)
        visible_links(page)
        link = page.locator(selector).first
        if link.count():
            try:
                link.scroll_into_view_if_needed(timeout=2_000)
                box = link.bounding_box()
                if box:
                    page.mouse.move(box["x"] + 12, box["y"] + 10)
                    page.mouse.click(box["x"] + 12, box["y"] + 10)
                else:
                    link.click(timeout=2_000)
            except Exception:
                result["fallback"] = "goto_after_click_timeout"
                page.goto(f"{BASE_URL}{href}", wait_until="domcontentloaded")
        else:
            page.goto(f"{BASE_URL}{href}", wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(250)
        body = page.locator("body").inner_text(timeout=5_000)
        if has_dirty_text(body):
            result["issues"].append("dirty_text_marker")
        if any(token in body for token in ["Internal Server Error", "Traceback", "BuildError", "OperationalError"]):
            result["issues"].append("server_error_text")
        if page.locator(".alert-danger").count() > 0:
            result["issues"].append("visible_error_alert")
    except Exception as exc:
        result["ok"] = False
        result["issues"].append(str(exc)[:240])
    result["ok"] = result["ok"] and not result["issues"]
    return result


def interact_current_page(page, username: str, path: str) -> list[str]:
    issues: list[str] = []
    try:
        page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded")
        page.wait_for_timeout(350)
        if path == "/system_settings/form":
            search = page.locator("#settingsSearch")
            if search.count():
                box = search.bounding_box()
                if box:
                    page.mouse.click(box["x"] + 8, box["y"] + 8)
                page.keyboard.type("精度", delay=20)
                page.wait_for_timeout(300)
                if page.locator("[data-settings-card]:visible").count() < 1:
                    issues.append("settings_search_no_result")
                search.fill("")
        elif path == "/system/database-backups":
            select = page.locator("select[name='backup_type']")
            if select.count():
                select.select_option("manual")
            if not page.locator("#runBackupBtn").count():
                issues.append("backup_button_missing")
        else:
            text_inputs = page.locator("input:not([type='hidden']):not([type='password']):not([readonly]), textarea:not([readonly])")
            fill_count = min(text_inputs.count(), 3)
            for i in range(fill_count):
                field = text_inputs.nth(i)
                try:
                    input_type = (field.get_attribute("type") or "text").lower()
                    name = field.get_attribute("name") or ""
                    value = f"BT-{username}-{int(time.time())}"
                    if input_type in {"date", "datetime-local"}:
                        value = datetime.now().strftime("%Y-%m-%d")
                    elif input_type == "number" or "qty" in name or "quantity" in name:
                        value = "1"
                    box = field.bounding_box()
                    if box:
                        page.mouse.click(box["x"] + 8, box["y"] + 8)
                    field.fill("")
                    page.keyboard.type(value, delay=10)
                except Exception:
                    continue
            page.keyboard.press("Tab")
        body = page.locator("body").inner_text(timeout=5_000)
        if has_dirty_text(body):
            issues.append("dirty_text_after_interaction")
    except Exception as exc:
        issues.append(str(exc)[:240])
    return issues


def main() -> int:
    passwords = load_passwords()
    executable = edge_executable()
    results: list[dict[str, object]] = []
    console_errors: list[dict[str, str]] = []

    with sync_playwright() as p:
        launch_args = {"headless": True}
        if executable:
            launch_args["executable_path"] = executable
        try:
            browser = p.chromium.launch(**launch_args)
        except PlaywrightError as exc:
            print("browser_full_human_acceptance=blocked")
            print(f"reason={str(exc).splitlines()[0]}")
            return 2

        for username in ROLE_USERS:
            context = browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
            context.set_default_timeout(8_000)
            context.set_default_navigation_timeout(30_000)
            page = context.new_page()
            page.on(
                "console",
                lambda msg, user=username: console_errors.append({"user": user, "type": msg.type, "text": msg.text[:240]})
                if msg.type in {"error", "warning"} and "favicon" not in msg.text.lower()
                else None,
            )
            role_result = {"user": username, "login_ok": False, "nav": [], "interactions": []}
            try:
                human_login(page, username, passwords[username])
                role_result["login_ok"] = True
                links = visible_links(page)
                if not FULL_NAV:
                    important = KEY_INTERACTION_PATHS.get(username, [])
                    selected = []
                    for href in [*important, *links]:
                        if href in links and href not in selected:
                            selected.append(href)
                        if len(selected) >= MAX_NAV_LINKS:
                            break
                    links = selected
                role_result["visible_links"] = len(links)
                for href in links:
                    role_result["nav"].append(click_nav_link(page, href))
                for path in KEY_INTERACTION_PATHS.get(username, []):
                    role_result["interactions"].append({"path": path, "issues": interact_current_page(page, username, path)})
            except Exception as exc:
                role_result["login_error"] = str(exc)[:240]
            finally:
                try:
                    page.screenshot(path=str(REPORT_DIR / f"{username}.png"), full_page=False, timeout=5_000)
                except Exception:
                    pass
                context.close()
            results.append(role_result)
        browser.close()

    failures = []
    for role in results:
        if not role.get("login_ok"):
            failures.append(f"{role['user']}: login failed")
        for item in role.get("nav", []):
            if not item.get("ok"):
                failures.append(f"{role['user']} nav {item['path']}: {', '.join(item['issues'])}")
        for item in role.get("interactions", []):
            if item.get("issues"):
                failures.append(f"{role['user']} interact {item['path']}: {', '.join(item['issues'])}")

    report = {
        "base_url": BASE_URL,
        "browser": executable or "playwright-default-chromium",
        "results": results,
        "console_errors": console_errors,
        "failures": failures,
    }
    report_path = REPORT_DIR / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"browser_full_human_acceptance={'failed' if failures else 'ok'}")
    print(f"report={report_path}")
    print(f"users={len(results)}")
    print(f"nav_checks={sum(len(r.get('nav', [])) for r in results)}")
    print(f"interaction_checks={sum(len(r.get('interactions', [])) for r in results)}")
    print(f"console_warnings_errors={len(console_errors)}")
    if failures:
        print("failures:")
        for failure in failures[:60]:
            print(f"- {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
