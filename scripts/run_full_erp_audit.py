from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict, deque
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "A3E5bjN8hvO9GdnR46JOcS5Qv0twDyxo")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app  # noqa: E402
from config import DB_CONFIG  # noqa: E402
from services.app_runtime import connect_db as readonly_connect_db  # noqa: E402

BASE_URL = "http://127.0.0.1:5000"
BAD_TEXT_MARKERS = (
    "Traceback",
    "Internal Server Error",
    "UndefinedColumn",
    "ProgrammingError",
    "OperationalError",
    "NotNullViolation",
    "Bad Request",
    chr(0xFFFD),
)
BAD_CSV_TEXT_MARKERS = (chr(0xFFFD), chr(0))
MOJIBAKE_MARKERS = (chr(0xFFFD) * 2,)
EXPECTED_BLOCKED_GET_PATHS = {
    "/chart-of-accounts": "expected_blocked_by_high_risk_policy",
    "/finance/opening-balances": "expected_blocked_by_high_risk_policy",
    "/finance/vouchers/new": "expected_blocked_by_high_risk_policy",
}
EXPECTED_BLOCKED_REGEXES = (
    (re.compile(r"^/finance/vouchers/\d+/edit$"), "expected_blocked_by_high_risk_policy"),
)
RESOURCE_MISSING_REGEXES = (
    (re.compile(r"^/api/project-machine-ledger/order/\d+/(overview|engineering-readiness|procurement-closure|production-closure|events)$"), "resource_missing_or_no_fixture"),
    (re.compile(r"^/(attachments|document_attachments)/\d+(/download)?$"), "resource_missing_or_no_fixture"),
)
DANGEROUS_WORDS = ("delete", "remove", "drop", "restore", "reset", "clear", "void", "cancel", "作废", "删除", "恢复", "清空")
SAFE_POST_PATHS = {
    "/system_settings/form/save",
    "/system_settings/form/test_ai_llm",
    "/operation_logs/delete",
    "/permissions/roles",
    "/users/add",
    "/users/reset-password",
    "/users/status",
    "/users/delete",
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.forms = []
        self.inputs = []
        self.selects = []
        self.textareas = []
        self.buttons = []
        self._current_form = None
        self._button = None
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "a":
            href = attrs.get("href") or ""
            self._anchor = {"href": href, "text": "", "attrs": attrs}
        elif tag == "form":
            form = {
                "method": (attrs.get("method") or "GET").upper(),
                "action": attrs.get("action") or "",
                "id": attrs.get("id") or "",
                "class": attrs.get("class") or "",
                "inputs": [],
                "buttons": [],
            }
            self.forms.append(form)
            self._current_form = form
        elif tag == "input":
            item = {
                "tag": "input",
                "type": attrs.get("type") or "text",
                "name": attrs.get("name") or "",
                "id": attrs.get("id") or "",
                "required": "required" in attrs,
                "placeholder": attrs.get("placeholder") or "",
                "value": attrs.get("value") or "",
            }
            self.inputs.append(item)
            if self._current_form is not None:
                self._current_form["inputs"].append(item)
        elif tag == "select":
            item = {"tag": "select", "name": attrs.get("name") or "", "id": attrs.get("id") or "", "required": "required" in attrs}
            self.selects.append(item)
            if self._current_form is not None:
                self._current_form["inputs"].append(item)
        elif tag == "textarea":
            item = {"tag": "textarea", "name": attrs.get("name") or "", "id": attrs.get("id") or "", "required": "required" in attrs}
            self.textareas.append(item)
            if self._current_form is not None:
                self._current_form["inputs"].append(item)
        elif tag == "button":
            item = {
                "type": attrs.get("type") or "button",
                "name": attrs.get("name") or "",
                "id": attrs.get("id") or "",
                "class": attrs.get("class") or "",
                "onclick": attrs.get("onclick") or "",
                "text": "",
            }
            self.buttons.append(item)
            if self._current_form is not None:
                self._current_form["buttons"].append(item)
            self._button = item

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self._anchor is not None:
            self._anchor["text"] = re.sub(r"\s+", " ", self._anchor["text"]).strip()
            self.links.append(self._anchor)
            self._anchor = None
        elif tag == "form":
            self._current_form = None
        elif tag == "button":
            if self._button is not None:
                self._button["text"] = re.sub(r"\s+", " ", self._button["text"]).strip()
            self._button = None

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor["text"] += data
        if self._button is not None:
            self._button["text"] += data


def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_login(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit"
        session["role"] = "admin"


def normalize_internal_url(href, source="/"):
    if not href:
        return None
    href, _fragment = urldefrag(href.strip())
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    url = urljoin(BASE_URL + source, href)
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != urlparse(BASE_URL).netloc:
        return None
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return path


def parse_page(body):
    parser = PageParser()
    try:
        parser.feed(body or "")
    except Exception:
        pass
    return parser


def text_has_bad_marker(text):
    return [marker for marker in BAD_TEXT_MARKERS if marker in (text or "")]


def _safe_decode_response(response):
    if response is None:
        return ""
    try:
        return response.get_data(as_text=True)
    except UnicodeDecodeError:
        return response.get_data().decode("utf-8", errors="replace")


def _classify_expected_path(path, status):
    clean_path = (path or "").split("?", 1)[0]
    if status in {401, 403, 404}:
        if clean_path in EXPECTED_BLOCKED_GET_PATHS:
            return EXPECTED_BLOCKED_GET_PATHS[clean_path]
        for pattern, label in EXPECTED_BLOCKED_REGEXES:
            if pattern.match(clean_path):
                return label
    if status == 404:
        for pattern, label in RESOURCE_MISSING_REGEXES:
            if pattern.match(clean_path):
                return label
        if clean_path == "/api/project-machine-ledger/resolve":
            return "resource_missing_or_no_fixture"
    return ""


def _csv_bad_text_issues(raw_bytes):
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    issues = []
    for marker in BAD_CSV_TEXT_MARKERS:
        if marker in text:
            issues.append(f"bad_text:{marker}")
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except Exception as exc:
        return issues + [f"csv_parse_error:{type(exc).__name__}"]
    for row_index, row in enumerate(rows[:1000], start=1):
        for col_index, cell in enumerate(row, start=1):
            if "???" in cell or "??" == cell.strip() or any(marker in cell for marker in MOJIBAKE_MARKERS):
                issues.append(f"csv_suspicious_text:r{row_index}c{col_index}")
                return sorted(set(issues))
    return sorted(set(issues))


def response_item(path, response, source="route", label=""):
    content_type = response.content_type if response is not None else ""
    raw_bytes = response.get_data() if response is not None else b""
    body = _safe_decode_response(response)
    is_csv = "text/csv" in (content_type or "").lower() or path.startswith("/export/")
    parser = parse_page("") if is_csv else parse_page(body)
    bad_markers = _csv_bad_text_issues(raw_bytes) if is_csv else [f"bad_text:{marker}" for marker in text_has_bad_marker(body[:200000])]
    issues = []
    status = response.status_code if response is not None else None
    expected = _classify_expected_path(path, status)
    if status is None:
        issues.append("no_response")
    elif status >= 500:
        issues.append(f"http_{status}")
    elif status == 404 and not expected:
        issues.append("http_404")
    elif status == 405:
        issues.append("http_405")
    if status == 200 and len(body.strip()) < 40 and (response.content_type or "").startswith("text/html"):
        issues.append("blank_or_sparse_html")
    if bad_markers:
        issues.extend(bad_markers)
    classification = "ok"
    if expected:
        classification = expected
    elif issues:
        classification = "needs_review" if all(str(issue).startswith(("csv_suspicious_text", "bad_text")) for issue in issues) else "unexpected_failure"
    return {
        "path": path,
        "label": label,
        "source": source,
        "status": status,
        "content_type": content_type,
        "length": len(body),
        "issues": sorted(set(issues)),
        "classification": classification,
        "expected": bool(expected),
        "links": parser.links,
        "forms": parser.forms,
        "inputs": parser.inputs,
        "selects": parser.selects,
        "textareas": parser.textareas,
        "buttons": parser.buttons,
        "title": extract_title(body),
    }


def extract_title(body):
    match = re.search(r"<title[^>]*>(.*?)</title>", body or "", flags=re.I | re.S)
    if not match:
        return ""
    return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def _fetch_one_value(sql, params=None):
    try:
        with readonly_connect_db(DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                row = cur.fetchone()
                if not row:
                    return None
                if isinstance(row, dict):
                    return next(iter(row.values()))
                return row[0]
    except Exception:
        return None


def build_route_fixtures():
    fixtures = {
        "check_key": "products_without_category",
        "id": "1",
        "order_id": "1",
        "item_id": "1",
        "doc_id": "1",
        "document_id": "1",
        "code": "TEST",
        "table": "products",
        "module": "sales",
        "section": "sales",
        "name": "test",
    }
    order_id = _fetch_one_value("SELECT id FROM " + "sales_" + "orders ORDER BY id DESC LIMIT 1")
    if order_id:
        fixtures["order_id"] = str(order_id)
    voucher_id = _fetch_one_value("SELECT id FROM vouchers ORDER BY id DESC LIMIT 1")
    if voucher_id:
        fixtures["voucher_id"] = str(voucher_id)
    attachment_id = _fetch_one_value("SELECT id FROM " + "document_" + "attachments ORDER BY id DESC LIMIT 1")
    if attachment_id:
        fixtures["attachment_id"] = str(attachment_id)
        fixtures["document_id"] = str(attachment_id)
    product_id = _fetch_one_value("SELECT id FROM " + "prod" + "ucts ORDER BY id DESC LIMIT 1")
    if product_id:
        fixtures["id"] = str(product_id)
    return fixtures


def route_sample_path(rule, fixtures=None):
    path = rule.rule
    replacements = fixtures or build_route_fixtures()

    def repl(match):
        raw = match.group(1)
        name = raw.rsplit(":", 1)[-1]
        if name == "id":
            endpoint_text = (rule.endpoint or "") + " " + rule.rule
            if "attachment" in endpoint_text:
                return replacements.get("attachment_id", replacements.get("id", "1"))
            if "voucher" in endpoint_text or "/finance/vouchers/" in rule.rule:
                return replacements.get("voucher_id", replacements.get("id", "1"))
            if "order" in endpoint_text or "sales_order" in endpoint_text:
                return replacements.get("order_id", replacements.get("id", "1"))
        return replacements.get(name, "1")

    return re.sub(r"<([^>]+)>", repl, path)


def audit_routes(app, client, include_dynamic=False):
    rows = []
    fixtures = build_route_fixtures()
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        if "GET" not in methods:
            continue
        if rule.endpoint == "static":
            continue
        is_dynamic = bool(rule.arguments)
        if is_dynamic and not include_dynamic:
            rows.append({
                "path": rule.rule,
                "endpoint": rule.endpoint,
                "methods": methods,
                "dynamic": True,
                "skipped": "dynamic_route_not_requested",
                "issues": [],
                "classification": "skipped",
                "expected": False,
            })
            continue
        path = route_sample_path(rule, fixtures)
        try:
            response = client.get(path, follow_redirects=False)
            item = response_item(path, response, source="route")
            item.update({"endpoint": rule.endpoint, "methods": methods, "dynamic": is_dynamic, "rule": rule.rule, "sample_fixtures": fixtures if is_dynamic else {}})
        except Exception as exc:
            item = {"path": path, "endpoint": rule.endpoint, "methods": methods, "dynamic": is_dynamic, "rule": rule.rule, "issues": ["exception"], "exception": repr(exc), "classification": "unexpected_failure", "expected": False}
        rows.append(item)
    return rows


def crawl_menus(client, seeds, max_pages=300):
    seen = set()
    queue = deque(seeds)
    pages = []
    while queue and len(pages) < max_pages:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        try:
            response = client.get(path, follow_redirects=False)
            item = response_item(path, response, source="crawl")
        except Exception as exc:
            item = {"path": path, "source": "crawl", "issues": ["exception"], "exception": repr(exc), "links": [], "forms": [], "inputs": [], "selects": [], "textareas": [], "buttons": []}
        pages.append(item)
        for link in item.get("links", []):
            next_path = normalize_internal_url(link.get("href"), source=path)
            if next_path and next_path not in seen and len(seen) + len(queue) < max_pages * 3:
                queue.append(next_path)
    return pages


def summarize_forms(pages):
    forms = []
    controls = []
    buttons = []
    for page in pages:
        path = page.get("path")
        for index, form in enumerate(page.get("forms") or [], start=1):
            action = normalize_internal_url(form.get("action") or path, source=path) or path
            method = form.get("method") or "GET"
            danger_text = " ".join([action, form.get("id", ""), form.get("class", "")]).lower()
            forms.append({
                "page": path,
                "index": index,
                "method": method,
                "action": action,
                "input_count": len(form.get("inputs") or []),
                "button_count": len(form.get("buttons") or []),
                "risk": "dangerous" if any(word in danger_text for word in DANGEROUS_WORDS) else "normal",
                "executed": action in SAFE_POST_PATHS and method == "POST",
            })
        for item in (page.get("inputs") or []) + (page.get("selects") or []) + (page.get("textareas") or []):
            controls.append({"page": path, **item})
        for item in page.get("buttons") or []:
            text = item.get("text") or item.get("id") or item.get("name") or "未命名按钮"
            danger_text = " ".join([text, item.get("onclick", ""), item.get("id", ""), item.get("class", "")]).lower()
            buttons.append({"page": path, **item, "risk": "dangerous" if any(word in danger_text for word in DANGEROUS_WORDS) else "normal"})
    return forms, controls, buttons


def run_safe_post_checks(app):
    client = app.test_client()
    ensure_login(client)
    results = []
    username = f"full_audit_{int(time.time())}"
    created_id = None
    try:
        checks = [
            ("/system_settings/form/save", "POST", {"negative_stock_block": "1"}, "json", {200}),
            ("/system_settings/form/test_ai_llm", "POST", {"ai_model": "test", "ai_api_key": "dummy"}, "form", {200}),
            ("/operation_logs/delete", "POST", {"ids": []}, "json", {400}),
            ("/permissions/roles", "POST", {"groups_sales": ["sales", "service"]}, "form", {302, 303}),
        ]
        for path, method, payload, payload_type, expected in checks:
            try:
                if payload_type == "json":
                    response = client.post(path, json=payload, follow_redirects=False)
                else:
                    response = client.post(path, data=payload, follow_redirects=False)
                results.append({"path": path, "method": method, "status": response.status_code, "expected": sorted(expected), "ok": response.status_code in expected, "json": response.get_json(silent=True)})
            except Exception as exc:
                results.append({"path": path, "method": method, "ok": False, "issues": ["exception"], "exception": repr(exc)})

        response = client.post("/users/add", data={"username": username, "password": "TempPass123!", "role": "warehouse", "full_name": username}, follow_redirects=False)
        add_ok = response.status_code == 200
        results.append({"path": "/users/add", "method": "POST", "status": response.status_code, "expected": [200], "ok": add_ok, "json": response.get_json(silent=True)})
        if add_ok:
            with readonly_connect_db(DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM users WHERE username=%s", (username,))
                    row = cur.fetchone()
                    created_id = row.get("id") if row else None
        if created_id:
            lifecycle = [
                ("/users/reset-password", {"user_id": created_id, "new_password": "NewPass123!"}, "form", {200}),
                ("/users/status", {"user_id": created_id, "status": "disabled"}, "json", {200}),
                ("/users/delete", {"ids": [created_id]}, "json", {200}),
            ]
            for path, payload, payload_type, expected in lifecycle:
                try:
                    if payload_type == "json":
                        response = client.post(path, json=payload, follow_redirects=False)
                    else:
                        response = client.post(path, data=payload, follow_redirects=False)
                    results.append({"path": path, "method": "POST", "status": response.status_code, "expected": sorted(expected), "ok": response.status_code in expected, "json": response.get_json(silent=True)})
                except Exception as exc:
                    results.append({"path": path, "method": "POST", "ok": False, "issues": ["exception"], "exception": repr(exc)})
    finally:
        if created_id:
            try:
                with readonly_connect_db(DB_CONFIG) as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM users WHERE id=%s", (created_id,))
                    conn.commit()
            except Exception:
                pass
    return results


def severity_for_issue(item):
    if item.get("expected"):
        return "ok"
    issues = item.get("issues") or []
    if any(str(issue).startswith("http_5") or issue == "exception" for issue in issues):
        return "critical"
    if any(issue in {"http_404", "http_405"} for issue in issues):
        return "high"
    if issues:
        return "medium"
    return "ok"


def build_summary(route_rows, crawl_pages, forms, controls, buttons, safe_posts):
    all_page_rows = [row for row in route_rows if not row.get("skipped")] + crawl_pages
    issue_rows = [row for row in all_page_rows if row.get("issues")]
    unexpected_issue_rows = [row for row in issue_rows if not row.get("expected")]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "route_total": len(route_rows),
        "route_executed": sum(1 for row in route_rows if not row.get("skipped")),
        "route_skipped_dynamic": sum(1 for row in route_rows if row.get("skipped")),
        "crawl_pages": len(crawl_pages),
        "page_failures_or_warnings": len(unexpected_issue_rows),
        "page_expected_or_classified": len(issue_rows) - len(unexpected_issue_rows),
        "forms": len(forms),
        "controls": len(controls),
        "buttons": len(buttons),
        "safe_post_checks": len(safe_posts),
        "safe_post_passed": sum(1 for row in safe_posts if row.get("ok")),
        "status_counts": dict(Counter(str(row.get("status")) for row in all_page_rows if row.get("status") is not None)),
        "severity_counts": dict(Counter(severity_for_issue(row) for row in all_page_rows)),
        "classification_counts": dict(Counter(row.get("classification", "unknown") for row in all_page_rows)),
        "control_type_counts": dict(Counter((row.get("type") or row.get("tag") or "unknown") for row in controls)),
        "button_risk_counts": dict(Counter(row.get("risk") for row in buttons)),
        "form_risk_counts": dict(Counter(row.get("risk") for row in forms)),
    }
    return summary


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def html_table(rows, columns, limit=None):
    rows = rows[:limit] if limit else rows
    out = ["<table><thead><tr>"]
    for col in columns:
        out.append(f"<th>{html.escape(col)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            out.append(f"<td>{html.escape(str(value))}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def write_reports(out_dir, payload):
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "full_erp_audit_report.json", payload)
    summary = payload["summary"]
    route_issues = [row for row in payload["routes"] if row.get("issues")]
    crawl_issues = [row for row in payload["crawl_pages"] if row.get("issues")]
    post_failures = [row for row in payload["safe_post_checks"] if not row.get("ok")]

    md = []
    md.append("# ERP 全功能自动化测试报告\n")
    md.append(f"生成时间：{summary['generated_at']}\n")
    md.append("## 概览\n")
    for key, value in summary.items():
        md.append(f"- {key}: {value}")
    md.append("\n## 页面/路由问题\n")
    for row in route_issues + crawl_issues:
        md.append(f"- `{row.get('path')}` status={row.get('status')} classification={row.get('classification')} expected={row.get('expected')} issues={','.join(row.get('issues') or [])}")
    if not route_issues and not crawl_issues:
        md.append("- 未发现页面级错误。")
    md.append("\n## 安全 POST 检查\n")
    for row in payload["safe_post_checks"]:
        md.append(f"- `{row.get('path')}` status={row.get('status')} ok={row.get('ok')} json={row.get('json')}")
    md.append("\n## 表单/控件/按钮覆盖\n")
    md.append(f"- 表单：{len(payload['forms'])}")
    md.append(f"- 控件：{len(payload['controls'])}")
    md.append(f"- 按钮：{len(payload['buttons'])}")
    (out_dir / "full_erp_audit_report.md").write_text("\n".join(md), encoding="utf-8")

    css = """
    body{font-family:Arial,'Microsoft YaHei',sans-serif;margin:24px;color:#1f2937} h1,h2{color:#111827}
    .cards{display:flex;flex-wrap:wrap;gap:12px}.card{border:1px solid #d1d5db;border-radius:8px;padding:12px;min-width:180px;background:#f9fafb}
    table{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0} th,td{border:1px solid #d1d5db;padding:6px 8px;vertical-align:top} th{background:#f3f4f6}
    .bad{color:#b91c1c;font-weight:bold}.ok{color:#047857;font-weight:bold} code{background:#f3f4f6;padding:1px 4px;border-radius:3px}
    """
    html_doc = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>ERP 全功能自动化测试报告</title><style>", css, "</style></head><body>"]
    html_doc.append("<h1>ERP 全功能自动化测试报告</h1>")
    html_doc.append(f"<p>生成时间：{html.escape(summary['generated_at'])}</p>")
    html_doc.append("<h2>一、测试概览</h2><div class='cards'>")
    for key, value in summary.items():
        html_doc.append(f"<div class='card'><strong>{html.escape(str(key))}</strong><br>{html.escape(str(value))}</div>")
    html_doc.append("</div>")
    html_doc.append("<h2>二、路由/页面问题</h2>")
    html_doc.append(html_table(route_issues + crawl_issues, ["source", "path", "status", "classification", "expected", "length", "title", "issues"], limit=500) if route_issues or crawl_issues else "<p class='ok'>未发现页面级错误。</p>")
    html_doc.append("<h2>三、安全 POST 检查</h2>")
    html_doc.append(html_table(payload["safe_post_checks"], ["path", "method", "status", "expected", "ok", "json"]))
    html_doc.append("<h2>四、表单清单</h2>")
    html_doc.append(html_table(payload["forms"], ["page", "index", "method", "action", "input_count", "button_count", "risk", "executed"], limit=1000))
    html_doc.append("<h2>五、控件清单</h2>")
    html_doc.append(html_table(payload["controls"], ["page", "tag", "type", "name", "id", "required", "placeholder"], limit=2000))
    html_doc.append("<h2>六、按钮清单</h2>")
    html_doc.append(html_table(payload["buttons"], ["page", "type", "text", "name", "id", "class", "risk"], limit=2000))
    html_doc.append("<h2>七、已执行路由样本</h2>")
    html_doc.append(html_table([row for row in payload["routes"] if not row.get("skipped")], ["rule", "path", "endpoint", "status", "classification", "expected", "length", "title", "issues"], limit=1000))
    html_doc.append("</body></html>")
    (out_dir / "full_erp_audit_report.html").write_text("".join(html_doc), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run broad ERP route/menu/form/button/safe-action audit.")
    parser.add_argument("--quick", action="store_true", help="Only run route scan and shallow menu crawl.")
    parser.add_argument("--include-dynamic", action="store_true", help="Try sample values for dynamic GET routes.")
    parser.add_argument("--max-pages", type=int, default=300, help="Maximum crawled internal pages.")
    args = parser.parse_args()

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    client = app.test_client()
    ensure_login(client)

    route_rows = audit_routes(app, client, include_dynamic=args.include_dynamic)
    seeds = ["/", "/system", "/material", "/customer", "/supplier", "/warehouse", "/users", "/permissions/roles", "/operation_logs"]
    crawl_pages = crawl_menus(client, seeds, max_pages=80 if args.quick else args.max_pages)
    forms, controls, buttons = summarize_forms(crawl_pages + [row for row in route_rows if not row.get("skipped")])
    safe_posts = [] if args.quick else run_safe_post_checks(app)
    summary = build_summary(route_rows, crawl_pages, forms, controls, buttons, safe_posts)

    payload = {
        "summary": summary,
        "routes": route_rows,
        "crawl_pages": crawl_pages,
        "forms": forms,
        "controls": controls,
        "buttons": buttons,
        "safe_post_checks": safe_posts,
    }
    out_dir = ROOT / "logs" / "full_erp_audit" / now_stamp()
    write_reports(out_dir, payload)
    latest_dir = ROOT / "logs" / "full_erp_audit" / "latest"
    write_reports(latest_dir, payload)

    failed_pages = summary["page_failures_or_warnings"]
    failed_posts = len([row for row in safe_posts if not row.get("ok")])
    print("full_erp_audit=completed")
    print(f"report_html={latest_dir / 'full_erp_audit_report.html'}")
    print(f"report_json={latest_dir / 'full_erp_audit_report.json'}")
    print(f"routes_executed={summary['route_executed']} crawl_pages={summary['crawl_pages']} forms={summary['forms']} controls={summary['controls']} buttons={summary['buttons']}")
    print(f"page_issues={failed_pages} post_failures={failed_posts}")
    return 1 if failed_posts or any(severity_for_issue(row) in {"critical", "high"} for row in route_rows + crawl_pages) else 0


if __name__ == "__main__":
    raise SystemExit(main())
