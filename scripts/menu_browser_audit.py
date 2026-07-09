from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "logs" / "menu_audit"
SCREENSHOT_DIR = OUT_DIR / "screenshots"
BASE_URL = "http://127.0.0.1:5000"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


BAD_TEXT_PATTERNS = (
    "\ufffd",
    "???",
    "Traceback",
    "Internal Server Error",
    "Not Found",
    "Method Not Allowed",
    "UndefinedColumn",
    "ProgrammingError",
    "OperationalError",
)


def load_password(username: str) -> str:
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def safe_name(index: int, href: str, label: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", f"{index:03d}_{label}_{href.strip('/') or 'home'}")
    return cleaned.strip("_")[:120] + ".png"


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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    findings = []

    with sync_playwright() as p:
        try:
            browser, browser_runtime = launch_chromium_browser(p)
        except PlaywrightError as exc:
            print("menu_browser_audit=blocked")
            print("reason=playwright chromium browser is not installed or cannot be launched")
            print(r"hint=.venv\Scripts\python.exe -m playwright install chromium")
            print(f"detail={str(exc).splitlines()[0]}")
            return 2
        print(f"browser_runtime={browser_runtime}")
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        responses = {}

        def record_response(response):
            url = response.url.split("#", 1)[0]
            if url.startswith(BASE_URL):
                responses[url] = response.status

        page.on("response", record_response)
        page.goto(BASE_URL + "/", wait_until="networkidle")
        if page.locator("input[name='username']").count():
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

        page.screenshot(path=SCREENSHOT_DIR / "000_home.png", full_page=True)
        links = page.eval_on_selector_all(
            "a[data-nav-link]",
            """
            els => els.map(a => ({
                href: a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ')
            })).filter(x => x.href && !x.href.startsWith('#'))
            """,
        )

        seen = set()
        unique_links = []
        for link in links:
            key = (link["href"], link["text"])
            if key in seen:
                continue
            seen.add(key)
            unique_links.append(link)

        for index, link in enumerate(unique_links, start=1):
            href = link["href"]
            label = link["text"] or href
            url = urljoin(BASE_URL + "/", href)
            item = {"index": index, "label": label, "href": href, "url": url, "issues": []}
            try:
                response = page.goto(url, wait_until="networkidle", timeout=30000)
                status = response.status if response else responses.get(url)
                item["status"] = status
                if status and status >= 400:
                    item["issues"].append(f"http_{status}")
                title = page.title()
                body_text = page.locator("body").inner_text(timeout=5000)
                item["title"] = title
                if len(body_text.strip()) < 40:
                    item["issues"].append("blank_or_too_little_text")
                for pattern in BAD_TEXT_PATTERNS:
                    if pattern in body_text or pattern in title:
                        item["issues"].append(f"bad_text:{pattern}")
                if page.locator(".alert-danger").count():
                    danger_text = page.locator(".alert-danger").first.inner_text(timeout=2000)
                    if danger_text.strip():
                        item["danger_text"] = danger_text.strip()[:300]
                        item["issues"].append("danger_text")
                item["screenshot"] = str(SCREENSHOT_DIR / safe_name(index, href, label))
                page.screenshot(path=item["screenshot"], full_page=True)
            except Exception as exc:
                item["issues"].append("exception")
                item["exception"] = str(exc)
            findings.append(item)

        browser.close()

    (OUT_DIR / "menu_audit_findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    issue_count = sum(1 for item in findings if item["issues"])
    print(f"menu_browser_audit=completed links={len(findings)} issues={issue_count}")
    for item in findings:
        if item["issues"]:
            print(f"{item['index']:03d} | {item['label']} | {item['href']} | {','.join(item['issues'])}")
    return 1 if issue_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
