from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")


MENU_COVERAGE = {
    "采购单据": [
        ("新增供应商报价单", "/supplier-quotes/new"),
        ("新增采购申请单", "/purchase_request/new"),
        ("新增采购订单", "/purchase_order/new"),
        ("新增采购入库单", "/purchase_receipts/new"),
        ("新增采购退货单", "/purchase-returns/new"),
        ("新增采购发票登记", "/purchase-invoices/new"),
    ],
    "采购列表": [
        ("供应商报价单列表", "/supplier-quotes"),
        ("采购申请单列表", "/purchase_request"),
        ("采购订单列表", "/purchase-orders"),
        ("采购入库列表", "/purchase_receipts"),
        ("采购退货列表", "/purchase-returns"),
        ("采购发票登记列表", "/purchase-invoices"),
    ],
    "采购查询": [
        ("采购建议/智能补货", "/procurement/suggestions"),
        ("采购未到专题", "/purchase/reports/pending"),
        ("供应商未到排行", "/purchase/reports/supplier-ranking"),
        ("采购订单跟踪表", "/purchase/reports/receipt-tracking"),
        ("期末暂估余额表", "/purchase/reports/received-not-invoiced-summary"),
        ("供应商采购执行分析", "/purchase/reports/supplier-execution-analysis"),
        ("采购价格分析表", "/purchase/reports/purchase-price-variance"),
        ("采购异常清单", "/purchase/reports/purchase-exception-list"),
    ],
    "采购报表": [
        ("采购执行明细", "/purchase/reports/execution"),
        ("采购汇总表", "/purchase/reports/summary"),
        ("采购申请执行明细", "/purchase/reports/request-execution-detail"),
        ("采购申请执行汇总", "/purchase/reports/request-execution-summary"),
        ("采购订单执行明细", "/purchase/reports/order-execution-detail"),
        ("采购订单汇总表", "/purchase/reports/order-execution-summary"),
        ("采购入库明细表", "/purchase/reports/receipt-detail"),
        ("采购入库汇总表", "/purchase/reports/receipt-summary"),
        ("收货未开票明细表", "/purchase/reports/received-not-invoiced-detail"),
        ("采购发票明细表", "/purchase/reports/invoice-detail"),
        ("采购发票汇总表/税票汇总表", "/purchase/reports/invoice-summary"),
        ("采购付款一览表", "/purchase/reports/payment-overview"),
        ("采购应付对账明细", "/purchase/reports/payable-reconciliation-detail"),
        ("项目/柜号采购成本明细", "/purchase/reports/project-cabinet-purchase-cost-detail"),
        ("采购日报", "/purchase/reports/daily"),
    ],
}


def _fail(findings: list[str]) -> None:
    if findings:
        for finding in findings:
            print(f"FAIL {finding}")
        raise SystemExit(1)


def _audit_template() -> list[str]:
    template = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    findings: list[str] = []
    for group, entries in MENU_COVERAGE.items():
        if f">{group}</div>" not in template:
            findings.append(f"templates/base.html missing purchase group {group}")
        for label, href in entries:
            if label not in template:
                findings.append(f"templates/base.html missing purchase menu label {label}")
            if f'href="{href}"' not in template:
                findings.append(f"templates/base.html missing purchase menu href {href}")

    report_start = template.find('<div class="submenu-label">采购报表</div>')
    if report_start >= 0:
        report_block = template[report_start: template.find("</div>", report_start + 1)]
        for forbidden in ("/new", "/submit", "/audit", "/post", "/void"):
            if forbidden in report_block:
                findings.append(f"purchase report menu contains document operation link fragment {forbidden}")
    return findings


def _audit_routes(app) -> list[str]:
    concrete_rules = {
        rule.rule
        for rule in app.url_map.iter_rules()
        if "<" not in rule.rule and "GET" in rule.methods
    }
    expected_hrefs = {href for entries in MENU_COVERAGE.values() for _, href in entries}
    findings = []
    for href in sorted(expected_hrefs):
        if href not in concrete_rules:
            findings.append(f"missing GET route for purchase menu href {href}")
    return findings


def _audit_runtime(app) -> list[str]:
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit"
        session["role"] = "admin"

    sample_paths = [
        "/supplier-quotes",
        "/purchase_request",
        "/purchase-orders",
        "/purchase_receipts",
        "/purchase-returns",
        "/purchase-invoices",
        "/payables",
        "/payments",
        "/procurement/suggestions",
        "/purchase/reports/execution",
        "/purchase/reports/invoice-summary",
        "/purchase/reports/payment-overview",
        "/purchase/reports/daily",
    ]
    findings = []
    for path in sample_paths:
        response = client.get(path, follow_redirects=False)
        if response.status_code != 200:
            findings.append(f"{path} returned HTTP {response.status_code}")
    return findings


def _make_app():
    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def main() -> None:
    findings = []
    app = _make_app()
    findings.extend(_audit_template())
    findings.extend(_audit_routes(app))
    findings.extend(_audit_runtime(app))
    _fail(findings)
    print("purchase Kingdee-style coverage audit passed")


if __name__ == "__main__":
    main()
