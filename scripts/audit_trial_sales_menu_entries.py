from pathlib import Path
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


REQUIRED_ENTRIES = (
    ("销售", None),
    ("销售单据", None),
    ("新增销售订单", "/sales/new"),
    ("销售列表", None),
    ("销售订单列表", "/sales-orders"),
    ("销售发货列表", "/shipments"),
    ("设备报价列表", "/quotations"),
    ("销售退货列表", "/sales-returns"),
    ("销售报表", None),
    ("销售未交报表", "/sales/reports/pending"),
    ("客户未交排行", "/sales/reports/customer-ranking"),
    ("销售执行明细", "/sales/reports/execution"),
)

DOCUMENT_ENTRY_HREFS = {"/sales/new"}
LIST_HREFS = {"/sales-orders", "/shipments", "/quotations", "/sales-returns"}
FINANCE_OWNED_HREFS = {"/sales-invoices", "/receivables", "/customer-receipts"}
REPORT_HREFS = {"/sales/reports/pending", "/sales/reports/customer-ranking", "/sales/reports/execution"}
DIRTY_CODEPOINTS = {0xFFFD, 0x95C1, 0x95BF, 0x6434}


def has_dirty_text(text):
    return "???" in text or any(ord(ch) in DIRTY_CODEPOINTS for ch in text)


def load_password(username):
    from scripts.trial_audit_auth import prepare_trial_audit_passwords

    return prepare_trial_audit_passwords([username]).get(username, "")

def safe_print_value(value):
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def menu_segment(body, heading):
    marker = f'<div class="submenu-label">{heading}</div>'
    start = body.find(marker)
    if start < 0:
        return ""
    next_match = re.search(r'<div class="submenu-label">|<div class="menu-parent">', body[start + len(marker):])
    if next_match:
        end = start + len(marker) + next_match.start()
        return body[start:end]
    end = body.find("</div>", start)
    return body[start:end if end > start else len(body)]


def has_href(segment, href):
    return f'href="{href}"' in segment


def main():
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "trial-sales-menu-entries")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    from app import create_app

    app = create_app({"TESTING": True, "LOGIN_RATE_LIMIT": 1000, "WTF_CSRF_ENABLED": False})
    checks = []
    client = app.test_client()
    login = client.post("/login", data={"username": "pilot_sales", "password": load_password("pilot_sales")}, follow_redirects=False)
    checks.append(("pilot_sales_login", login.status_code == 302, login.status_code))
    if login.status_code == 302:
        response = client.get("/")
        body = response.get_data(as_text=True)
        checks.append(("home_status", response.status_code == 200, response.status_code))
        for label, href in REQUIRED_ENTRIES:
            checks.append((f"menu_label:{label}", label in body, "present" if label in body else "missing"))
            if href:
                checks.append((f"menu_href:{href}", f'href="{href}"' in body, "present" if f'href="{href}"' in body else "missing"))
                page = client.get(href, follow_redirects=False)
                checks.append((f"menu_target:{href}", page.status_code < 400, page.status_code))

        document_segment = menu_segment(body, "销售单据")
        list_segment = menu_segment(body, "销售列表")
        report_segment = menu_segment(body, "销售报表")
        for href in DOCUMENT_ENTRY_HREFS:
            checks.append((f"document_group_contains:{href}", has_href(document_segment, href), "present" if has_href(document_segment, href) else "missing"))
            checks.append((f"list_group_excludes_document:{href}", not has_href(list_segment, href), "clean" if not has_href(list_segment, href) else "mixed"))
            checks.append((f"report_group_excludes_document:{href}", not has_href(report_segment, href), "clean" if not has_href(report_segment, href) else "mixed"))
        for href in LIST_HREFS:
            checks.append((f"document_group_excludes_list:{href}", not has_href(document_segment, href), "clean" if not has_href(document_segment, href) else "mixed"))
            checks.append((f"list_group_contains:{href}", has_href(list_segment, href), "present" if has_href(list_segment, href) else "missing"))
            checks.append((f"report_group_excludes_list:{href}", not has_href(report_segment, href), "clean" if not has_href(report_segment, href) else "mixed"))
        for href in FINANCE_OWNED_HREFS:
            checks.append((f"sales_menu_excludes_finance_owned:{href}", f'href="{href}"' not in body, "clean" if f'href="{href}"' not in body else "duplicated"))
        for href in REPORT_HREFS:
            checks.append((f"report_group_contains:{href}", has_href(report_segment, href), "present" if has_href(report_segment, href) else "missing"))
            checks.append((f"document_group_excludes_report:{href}", not has_href(document_segment, href), "clean" if not has_href(document_segment, href) else "mixed"))
            checks.append((f"list_group_excludes_report:{href}", not has_href(list_segment, href), "clean" if not has_href(list_segment, href) else "mixed"))

        checks.append(("dirty_markers", not has_dirty_text(body), "clean" if not has_dirty_text(body) else "dirty"))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("trial_sales_menu_entries_audit=ok" if not failures else "trial_sales_menu_entries_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {safe_print_value(name)} | {safe_print_value(detail)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
