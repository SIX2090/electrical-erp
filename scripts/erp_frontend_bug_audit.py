from __future__ import annotations

import json
import os
import re
import socket
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
BASE_URL = "http://127.0.0.1:5000"
OUT_DIR = ROOT / "logs" / "erp_frontend_bug_audit"
SCREENSHOT_DIR = OUT_DIR / "screenshots"
OUT_JSON = OUT_DIR / "findings.json"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


ENTRY_PAGES = [
    {"path": "/purchase_request/new", "module": "purchase", "name": "purchase request"},
    {"path": "/sales/new", "module": "sales", "name": "sales order"},
    {"path": "/purchase_order/new", "module": "purchase", "name": "purchase order"},
    {"path": "/work-orders/new", "module": "production", "name": "work order"},
    {"path": "/subcontract/new", "module": "subcontract", "name": "subcontract order"},
    {"path": "/adjustments/new", "module": "inventory", "name": "inventory adjustment"},
    {"path": "/transfers/new", "module": "inventory", "name": "inventory transfer"},
    {"path": "/inventory_checks/new", "module": "inventory", "name": "inventory check"},
    {"path": "/service-orders/new", "module": "service", "name": "service order"},
]

VIEWPORTS = [
    {"name": "desktop", "width": 1440, "height": 950},
    {"name": "mobile", "width": 390, "height": 844},
]

BAD_TEXT = ("\ufffd", "???", "Traceback", "Internal Server Error", "UndefinedColumn", "ProgrammingError")
SAVE_BUTTON_SELECTOR = (
    "button[type='submit'], input[type='submit'], "
    "button[data-menu-event='global-submit-main-form'], "
    "[data-menu-event='global-submit-main-form'], "
    "button[onclick*='submitForm'], #submitAdd"
)


def safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip("/").replace("/", "_") or "home")[:120]


def check_service_available() -> tuple[bool, str]:
    """Check whether the ERP service is listening on BASE_URL host/port.

    Returns (available, detail). Using a short socket probe avoids the previous
    behavior where a missing service caused Playwright to raise a navigation
    exception that was misclassified as a critical ERP business bug.
    """
    try:
        with socket.create_connection(("127.0.0.1", 5000), timeout=2):
            return True, "ERP service is reachable on 127.0.0.1:5000"
    except (OSError, ConnectionError) as exc:
        return False, f"ERP service is not reachable on 127.0.0.1:5000: {exc}"


def finding(severity, module, bug_type, location, title, actual, expected, reproduce, evidence):
    return {
        "severity": severity,
        "module": module,
        "bug_type": bug_type,
        "location": location,
        "title": title,
        "actual": actual,
        "expected": expected,
        "reproduce": reproduce,
        "evidence": evidence,
        "owner": "frontend owner",
    }


def write_findings(findings):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")


def launch_chromium_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True), "playwright chromium"
    except PlaywrightError as first_error:
        for executable in EDGE_CANDIDATES:
            if not executable.exists():
                continue
            try:
                return playwright.chromium.launch(headless=True, executable_path=str(executable)), f"edge executable: {executable}"
            except PlaywrightError:
                continue
        raise first_error


def load_password(username: str) -> str:
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def inject_login(page):
    page.goto(BASE_URL + "/login", wait_until="networkidle")
    if page.locator("input[name='username']").count() == 0:
        return
    username = "pilot_admin"
    password = load_password(username)
    if not password:
        raise RuntimeError("missing pilot_admin password handoff")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    if page.locator("input[name='username']").count():
        raise RuntimeError("browser login failed for pilot_admin")


def visible_text(page):
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def audit_page(page, config, viewport):
    issues = []
    path = config["path"]
    url = BASE_URL + path
    console_errors = []
    page_errors = []
    responses = []

    def on_console(message):
        if message.type in {"error", "warning"} and "Failed to load resource" not in message.text:
            console_errors.append({"type": message.type, "text": message.text[:500]})

    def on_page_error(exc):
        page_errors.append(str(exc)[:500])

    def on_response(response):
        if response.url.startswith(BASE_URL) and response.status >= 400:
            responses.append({"url": response.url, "status": response.status})

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("response", on_response)
    try:
        response = page.goto(url, wait_until="networkidle", timeout=30000)
        status = response.status if response else None
        screenshot = SCREENSHOT_DIR / f"{viewport['name']}_{safe_name(path)}.png"
        page.screenshot(path=screenshot, full_page=True)
        body = visible_text(page)
        if status and status >= 400:
            issues.append(
                finding(
                    "critical",
                    config["module"],
                    "frontend_http_error",
                    path,
                    "Entry page returns HTTP error",
                    f"GET returned HTTP {status}.",
                    "Document entry pages must open without HTTP errors.",
                    [f"Open `{path}` in a browser."],
                    {"status": status, "screenshot": str(screenshot)},
                )
            )
        if any(marker in body for marker in BAD_TEXT):
            issues.append(
                finding(
                    "critical",
                    config["module"],
                    "visible_dirty_text",
                    path,
                    "Entry page contains dirty text",
                    "Page body contains dirty text markers or server error text.",
                    "Operator-facing document pages must show clean Chinese text.",
                    [f"Open `{path}` in a browser.", "Inspect visible text."],
                    {"screenshot": str(screenshot)},
                )
            )
        if len(body.strip()) < 80:
            issues.append(
                finding(
                    "high",
                    config["module"],
                    "blank_or_sparse_page",
                    path,
                    "Entry page appears blank or incomplete",
                    f"Only {len(body.strip())} visible characters were found.",
                    "Document entry pages should render header fields, line grid, and actions.",
                    [f"Open `{path}` in a browser."],
                    {"screenshot": str(screenshot)},
                )
            )
        submit_buttons = page.locator(SAVE_BUTTON_SELECTOR)
        if submit_buttons.count() == 0:
            issues.append(
                finding(
                    "high",
                    config["module"],
                    "missing_save_button",
                    path,
                    "No visible save/submit button found",
                    "Browser audit could not find a save or submit control.",
                    "Document entry pages must expose a clear save action.",
                    [f"Open `{path}` in a browser.", "Look for a save button."],
                    {"screenshot": str(screenshot)},
                )
            )
        else:
            button = submit_buttons.first
            before_text = button.inner_text(timeout=3000) if button.count() else ""
            try:
                button.click(timeout=5000)
                page.wait_for_timeout(1800)
                after_text = button.inner_text(timeout=3000) if button.count() else ""
                disabled = button.is_disabled(timeout=3000) if button.count() else False
                alert_count = page.locator(".alert-danger, .invalid-feedback, [aria-invalid='true'], .is-invalid").count()
                invalid_count = page.locator(":invalid").count()
                if disabled and ("保存中" in after_text or "saving" in after_text.lower()):
                    issues.append(
                        finding(
                            "critical",
                            config["module"],
                            "save_button_stuck",
                            path,
                            "Save button stayed in loading state",
                            f"Button text changed from `{before_text}` to `{after_text}` and remained disabled.",
                            "Invalid save attempts must recover and show validation feedback.",
                            [f"Open `{path}`.", "Click save with required fields empty.", "Wait two seconds."],
                            {"button_before": before_text, "button_after": after_text, "screenshot": str(screenshot)},
                        )
                    )
                if alert_count == 0 and invalid_count == 0 and page.url.rstrip("/") == url.rstrip("/"):
                    issues.append(
                        finding(
                            "medium",
                            config["module"],
                            "missing_required_feedback",
                            path,
                            "Save with empty form produced no visible validation feedback",
                            "No alert, invalid field marker, or aria-invalid field was detected after clicking save.",
                            "Required fields must be visibly marked and explain why save failed.",
                            [f"Open `{path}`.", "Click save with required fields empty."],
                            {"button_before": before_text, "button_after": after_text, "screenshot": str(screenshot)},
                        )
                    )
            except Exception as exc:
                issues.append(
                    finding(
                        "high",
                        config["module"],
                        "save_click_exception",
                        path,
                        "Save button could not be clicked",
                        str(exc)[:500],
                        "Save action should be clickable or explicitly disabled with visible reason.",
                        [f"Open `{path}`.", "Click save."],
                        {"screenshot": str(screenshot)},
                    )
                )

        if console_errors:
            issues.append(
                finding(
                    "high",
                    config["module"],
                    "console_error",
                    path,
                    "Browser console reported errors or warnings",
                    f"{len(console_errors)} console messages were captured.",
                    "Document entry pages should not emit console errors in normal use.",
                    [f"Open `{path}` in browser audit."],
                    {"messages": console_errors[:10], "screenshot": str(screenshot)},
                )
            )
        if page_errors:
            issues.append(
                finding(
                    "critical",
                    config["module"],
                    "javascript_exception",
                    path,
                    "Unhandled JavaScript exception occurred",
                    f"{len(page_errors)} page errors were captured.",
                    "Frontend JavaScript must not throw during page load or save attempts.",
                    [f"Open `{path}` in browser audit."],
                    {"messages": page_errors[:10], "screenshot": str(screenshot)},
                )
            )
        if responses:
            issues.append(
                finding(
                    "high",
                    config["module"],
                    "frontend_network_error",
                    path,
                    "Page triggered failed network responses",
                    f"{len(responses)} HTTP responses were >=400.",
                    "Frontend should not trigger missing or failed assets/actions.",
                    [f"Open `{path}` in browser audit."],
                    {"responses": responses[:10], "screenshot": str(screenshot)},
                )
            )
    except Exception as exc:
        issues.append(
            finding(
                "critical",
                config["module"],
                "browser_navigation_exception",
                path,
                "Browser could not audit page",
                str(exc)[:500],
                "Browser audit should be able to open every core document entry page.",
                [f"Open `{path}` in browser audit."],
                {},
            )
        )
    finally:
        page.remove_listener("console", on_console)
        page.remove_listener("pageerror", on_page_error)
        page.remove_listener("response", on_response)
    return issues


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    findings = []

    # Environment precondition check: if the ERP service is not running, the
    # browser audit cannot proceed. Report this as a structured environment
    # precondition result instead of letting Playwright raise a navigation
    # exception that would be misclassified as a critical ERP business bug.
    available, detail = check_service_available()
    if not available:
        findings.append(
            finding(
                "environment",
                "frontend_audit",
                "environment_precondition",
                "127.0.0.1:5000",
                "ERP service is not running",
                detail,
                "Start the ERP service on 127.0.0.1:5000 before running the frontend audit.",
                [
                    "Start the ERP service (e.g. run app.py or the local run script).",
                    "Confirm http://127.0.0.1:5000/login is reachable in a browser.",
                    "Re-run scripts/erp_frontend_bug_audit.py.",
                ],
                {"base_url": BASE_URL, "json_report": str(OUT_JSON)},
            )
        )
        write_findings(findings)
        print(f"frontend_bug_audit={OUT_JSON}")
        print(f"findings={len(findings)}")
        print(f"environment_precondition=failed | {detail}")
        print("Skipping browser audit because the ERP service is not running.")
        return 0

    try:
        with sync_playwright() as p:
            try:
                browser, browser_runtime = launch_chromium_browser(p)
            except PlaywrightError as exc:
                findings.append(
                    finding(
                        "critical",
                        "frontend_audit",
                        "browser_runtime_missing",
                        "playwright chromium",
                        "Playwright browser runtime is missing",
                        str(exc).splitlines()[0][:500],
                        "Frontend audit must have a browser runtime so it can produce screenshots and interaction evidence.",
                        ["Run `.\\.venv\\Scripts\\python.exe -m playwright install chromium`.", "Then run `scripts/erp_frontend_bug_audit.py` again."],
                        {"json_report": str(OUT_JSON)},
                    )
                )
                write_findings(findings)
                print(f"frontend_bug_audit={OUT_JSON}")
                print(f"findings={len(findings)}")
                for item in findings:
                    text = f"{item['severity']} | {item['module']} | {item['location']} | {item['title']}"
                    print(text.encode("ascii", "backslashreplace").decode("ascii"))
                return 1
            print(f"browser_runtime={browser_runtime}")
            for viewport in VIEWPORTS:
                page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]}, device_scale_factor=1)
                inject_login(page)
                for config in ENTRY_PAGES:
                    findings.extend(audit_page(page, config, viewport))
                page.close()
            browser.close()
    except Exception as exc:
        findings.append(
            finding(
                "critical",
                "frontend_audit",
                "audit_exception",
                "scripts/erp_frontend_bug_audit.py",
                "Frontend audit crashed before completing",
                str(exc)[:500],
                "Frontend audit should always emit JSON findings even when it cannot complete.",
                ["Run `scripts/erp_frontend_bug_audit.py`."],
                {"json_report": str(OUT_JSON)},
            )
        )
    write_findings(findings)
    print(f"frontend_bug_audit={OUT_JSON}")
    print(f"findings={len(findings)}")
    for item in findings[:50]:
        text = f"{item['severity']} | {item['module']} | {item['location']} | {item['title']}"
        print(text.encode("ascii", "backslashreplace").decode("ascii"))
    return 1 if any(item["severity"] in {"critical", "high"} for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
