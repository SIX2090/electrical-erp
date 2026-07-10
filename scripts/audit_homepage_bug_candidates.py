from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "homepage-audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app  # noqa: E402

REPORT_MD = ROOT / "logs" / "homepage_bug_audit_latest.md"
REPORT_JSON = ROOT / "logs" / "homepage_bug_audit_latest.json"

ROLES = ["admin", "manager", "sales", "purchase", "warehouse", "production", "service", "finance", "staff"]


@dataclass
class Finding:
    severity: str
    bug_type: str
    role: str
    location: str
    title: str
    actual: str
    expected: str
    evidence: dict


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict] = []
        self._current: dict | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attr = dict(attrs)
        href = attr.get("href") or ""
        self._current = {"href": href, "class": attr.get("class", ""), "text": ""}
        self._text_parts = []

    def handle_data(self, data):
        if self._current is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._current is not None:
            text = re.sub(r"\s+", " ", "".join(self._text_parts)).strip()
            self._current["text"] = text
            self.links.append(self._current)
            self._current = None
            self._text_parts = []


def normalize_internal_href(href: str) -> str | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path or "/"
    if not path.startswith("/"):
        return None
    if path.startswith(("/static/", "/attachments/", "/document_attachments/")):
        return None
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{path}{query}"


def get_links(html: str) -> list[dict]:
    parser = LinkParser()
    parser.feed(html)
    seen = set()
    result = []
    for link in parser.links:
        href = normalize_internal_href(link.get("href", ""))
        if not href:
            continue
        key = (href, link.get("text", ""))
        if key in seen:
            continue
        seen.add(key)
        item = dict(link)
        item["href"] = href
        result.append(item)
    return result


def session_for_role(client, role: str) -> None:
    with client.session_transaction() as session:
        session.clear()
        session["user_id"] = 9000
        session["username"] = f"homepage_audit_{role}"
        session["full_name"] = f"首页巡检-{role}"
        session["role"] = role


def audit_homepage_links(app, findings: list[Finding], role: str) -> dict:
    with app.test_client() as client:
        session_for_role(client, role)
        response = client.get("/", follow_redirects=False)
        body = response.get_data(as_text=True)
        result = {
            "role": role,
            "home_status": response.status_code,
            "visible_link_count": 0,
            "links": [],
            "task_card_count": body.count("erp-workbench-task-card"),
            "empty_line_count": body.count("erp-empty-line"),
        }
        if response.status_code != 200:
            findings.append(
                Finding(
                    severity="critical",
                    bug_type="homepage_status",
                    role=role,
                    location="/",
                    title="首页无法正常打开",
                    actual=f"GET / 返回 HTTP {response.status_code}",
                    expected="所有已登录角色的首页应返回 200。",
                    evidence={"status_code": response.status_code, "body_head": body[:500]},
                )
            )
            return result

        links = get_links(body)
        result["visible_link_count"] = len(links)
        if not links:
            findings.append(
                Finding(
                    severity="high",
                    bug_type="homepage_navigation_empty",
                    role=role,
                    location="/",
                    title="首页没有可见内部链接",
                    actual="渲染后的首页没有解析到任何内部 <a href> 链接。",
                    expected="首页应提供当前角色可用的业务入口。",
                    evidence={"body_head": body[:1000]},
                )
            )

        for link in links:
            href = link["href"]
            resp = client.get(href, follow_redirects=False)
            status = resp.status_code
            link_result = {"href": href, "text": link.get("text", ""), "status_code": status}
            result["links"].append(link_result)
            if status in {403, 404} or status >= 500:
                severity = "high" if status in {403, 404} else "critical"
                findings.append(
                    Finding(
                        severity=severity,
                        bug_type="visible_link_unreachable",
                        role=role,
                        location=href,
                        title="首页可见入口不可达",
                        actual=f"角色 {role} 在首页看到链接 `{link.get('text') or href}`，点击返回 HTTP {status}。",
                        expected="首页只应展示当前角色可正常访问的入口；无权限入口应隐藏或改为提示。",
                        evidence=link_result,
                    )
                )

        # Detect a common Jinja for-else bug: blocked_items exists, but role-filtered cards may be empty with no empty-state.
        if "待办队列" in body or "阻塞事项" in body:
            has_task_card = "erp-workbench-task-card" in body
            has_empty_line = "暂无待处理事项" in body or "暂无阻塞事项" in body
            if not has_task_card and not has_empty_line:
                findings.append(
                    Finding(
                        severity="medium",
                        bug_type="empty_state_missing",
                        role=role,
                        location="/",
                        title="首页待办/阻塞区域空白但没有空状态提示",
                        actual="页面包含待办或阻塞区域标题，但当前角色没有可见卡片，也没有显示暂无提示。",
                        expected="角色过滤后无可见卡片时，应显示明确的空状态提示。",
                        evidence={"task_card_count": result["task_card_count"], "empty_line_count": result["empty_line_count"]},
                    )
                )
        return result


def audit_metric_semantics(findings: list[Finding]) -> None:
    source = (ROOT / "routes" / "app_shell_routes.py").read_text(encoding="utf-8")
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    if "active_projects" in source and "FROM sales_orders" in source and "在制项目" in template:
        findings.append(
            Finding(
                severity="medium",
                bug_type="metric_definition_mismatch",
                role="all",
                location="routes/app_shell_routes.py:index active_projects",
                title="首页“在制项目”指标实际统计未关闭销售订单",
                actual="active_projects 使用 sales_orders 计数，模板显示为“在制项目”。一个项目多张订单时会虚高；无项目号订单也会被计入。",
                expected="如显示“在制项目”，应按项目号/项目档案去重统计；如按订单统计，应改名为“未关闭销售订单”。",
                evidence={"sql_fragment": "SELECT COUNT(*) FROM sales_orders WHERE status NOT IN (...)"},
            )
        )
    if "pending_delivery = max(month_sales - month_shipments, 0)" in source:
        findings.append(
            Finding(
                severity="medium",
                bug_type="metric_formula_risk",
                role="all",
                location="routes/app_shell_routes.py:pending_delivery",
                title="首页“本月待交付”用本月销售金额减本月发货金额，业务口径不严谨",
                actual="本月待交付 = max(本月销售金额 - 本月发货金额, 0)。跨月订单、部分发货、退货、作废、币种税率差异都会导致偏差。",
                expected="待交付应按销售订单行/项目/柜号维度，基于订单数量、已发数量和状态计算。",
                evidence={"formula": "pending_delivery = max(month_sales - month_shipments, 0)"},
            )
        )
    if "except Exception:\n                return {}" in source or "except Exception:\n                return []" in source:
        findings.append(
            Finding(
                severity="low",
                bug_type="metric_exception_swallowing",
                role="all",
                location="routes/app_shell_routes.py:safe_one/safe_rows",
                title="首页指标查询吞异常，可能把真实错误伪装成 0",
                actual="safe_one/safe_rows 捕获所有异常并返回空结果，首页会继续显示 0 或空图表。",
                expected="首页可以降级，但应至少记录日志，或在管理员首页显示数据源异常提示。",
                evidence={"helpers": ["safe_one", "safe_rows"]},
            )
        )


def main() -> int:
    nav_mode = os.environ.get("INVENTORY_NAV_MODE", "small_factory").strip() or "small_factory"
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    findings: list[Finding] = []
    role_results = []
    for role in ROLES:
        role_results.append(audit_homepage_links(app, findings, role))
    audit_metric_semantics(findings)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda item: (severity_order.get(item.severity, 9), item.role, item.location, item.title))
    REPORT_JSON.parent.mkdir(exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "nav_mode": nav_mode,
        "roles": ROLES,
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
        "role_results": role_results,
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {}
    for item in findings:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    lines = [
        "# 首页 BUG 巡检报告",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 导航模式：`{nav_mode}`",
        f"- 巡检角色：`{', '.join(ROLES)}`",
        f"- 发现数量：`{len(findings)}`",
        f"- Critical：`{counts.get('critical', 0)}`",
        f"- High：`{counts.get('high', 0)}`",
        f"- Medium：`{counts.get('medium', 0)}`",
        f"- Low：`{counts.get('low', 0)}`",
        "",
        "## 角色首页链接概览",
        "",
        "| 角色 | 首页状态 | 可见链接数 | 问题链接数 |",
        "|---|---:|---:|---:|",
    ]
    for row in role_results:
        bad = sum(1 for link in row.get("links", []) if link.get("status_code") in {403, 404} or link.get("status_code", 0) >= 500)
        lines.append(f"| {row['role']} | {row['home_status']} | {row['visible_link_count']} | {bad} |")
    lines.extend(["", "## 发现明细", ""])
    if not findings:
        lines.append("- 未发现首页自动巡检问题。")
    for index, item in enumerate(findings, 1):
        lines.extend([
            f"### {index}. {item.title}",
            "",
            f"- 严重级别：`{item.severity}`",
            f"- 类型：`{item.bug_type}`",
            f"- 角色：`{item.role}`",
            f"- 位置：`{item.location}`",
            f"- 实际：{item.actual}",
            f"- 期望：{item.expected}",
            f"- 证据：见 `{REPORT_JSON.relative_to(ROOT)}` 第 `{index - 1}` 条 finding",
            "",
        ])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"report={REPORT_MD}")
    print(f"json={REPORT_JSON}")
    print(f"findings={len(findings)}")
    for severity in ("critical", "high", "medium", "low"):
        print(f"{severity}={counts.get(severity, 0)}")
    return 1 if counts.get("critical", 0) or counts.get("high", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
