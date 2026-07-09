"""Verify unified toolbar architecture."""
import os, json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"

PAGES = [
    ("/work-orders/new", "entry"),
    ("/purchase-orders/new", "entry"),
    ("/shipments/new", "entry"),
    ("/work-orders", "list"),
    ("/receivables", "list"),
    ("/bom", "list"),
    ("/purchase/reports/pending", "report"),
    ("/inventory/reports/balance", "report"),
    ("/", "workbench"),
    ("/pending-documents", "workbench"),
]


def main():
    with sync_playwright() as p:
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        edge_path = next((p for p in edge_paths if os.path.exists(p)), None)
        browser = p.chromium.launch(headless=True, executable_path=edge_path)
        page = browser.new_page()

        # Capture console errors
        errors = []
        page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("pageerror", lambda err: errors.append(f"[pageerror] {err}"))

        page.goto(f"{BASE}/login")
        page.fill('input[name="username"]', "pilot_admin")
        page.fill('input[name="password"]', "admin")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        for path, ptype in PAGES:
            errors.clear()
            page.goto(f"{BASE}{path}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)

            result = page.evaluate("""() => {
                const bars = document.querySelectorAll('.document-menu-bar');
                const globalToolbar = document.getElementById('globalOperationToolbar');
                const globalHidden = globalToolbar ? globalToolbar.hidden : 'N/A';

                // Get primary items (not in dropdown)
                const primaryItems = Array.from(document.querySelectorAll('#globalOperationToolbar .document-menu-bar__item:not(.dropdown-item)')).map(el => el.innerText.trim()).filter(Boolean);
                // Get dropdown items
                const dropdownItems = Array.from(document.querySelectorAll('#globalOperationToolbar .dropdown-item')).map(el => el.innerText.trim()).filter(Boolean);

                return {
                    totalBars: bars.length,
                    globalHidden,
                    primaryItems,
                    dropdownItems
                };
            }""")

            status = "OK" if result['totalBars'] == 1 and not result['globalHidden'] else "ISSUE"
            print(f"[{status:5s}] [{ptype:9s}] {path}")
            print(f"  bars={result['totalBars']} hidden={result['globalHidden']}")
            print(f"  primary: {result['primaryItems']}")
            print(f"  dropdown: {result['dropdownItems']}")
            if errors:
                print(f"  JS ERRORS: {errors}")
            print()

        browser.close()


if __name__ == "__main__":
    main()
