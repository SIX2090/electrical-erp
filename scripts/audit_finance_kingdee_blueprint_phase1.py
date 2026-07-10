from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")


PHASE1_MENU_COVERAGE = {
    "财务工作台": [
        ("财务首页", "/finance/dashboard"),
        ("应收应付工作台", "/finance/receivable-payable"),
        ("待审核单据", "/finance/todo-documents"),
        ("待收款客户", "/finance/receivables/pending-collections"),
        ("待付款供应商", "/finance/reports/payable-warning"),
        ("逾期应收预警", "/finance/reports/receivable-warning"),
        ("逾期应付预警", "/finance/reports/payable-warning"),
        ("未开票销售", "/finance/unbilled-sales"),
        ("未到票采购", "/finance/unreceived-purchase-invoices"),
        ("业务财务异常", "/finance/business-exceptions"),
    ],
    "财务基础资料": [
        ("会计科目", "/master/chart-of-accounts"),
        ("凭证字", "/voucher-words"),
        ("币别", "/currencies"),
        ("结算方式", "/settlement-methods"),
        ("税率", "/tax-rates"),
        ("科目映射", "/finance/account-mappings"),
        ("银行账户", "/cash-bank-accounts"),
        ("收付款条件", "/payment-terms"),
        ("凭证模板", "/voucher-templates"),
        ("现金银行账户", "/finance/cash-bank/accounts"),
    ],
    "应收管理": [
        ("应收单", "/finance/receivables"),
        ("新增收款单", "/finance/receipts/new"),
        ("收款单", "/finance/receipts"),
        ("新增预收款单", "/finance/advance-receipts/new"),
        ("预收款单", "/finance/advance-receipts"),
        ("应收核销", "/finance/manual-settlement"),
        ("客户应收余额", "/finance/reports/receivable-summary"),
        ("客户对账单", "/finance/reports/customer-statement"),
        ("应收账龄分析", "/finance/reports/aging"),
        ("项目/柜号应收明细", "/finance/reports/receivable-detail"),
        ("销售发票登记列表", "/finance/sales-invoices"),
    ],
    "应付管理": [
        ("应付单", "/finance/payables"),
        ("付款申请单", "/finance/payment-requests"),
        ("新增付款单", "/finance/payments/new"),
        ("付款单", "/finance/payments"),
        ("新增预付款单", "/finance/advance-payments/new"),
        ("预付款单", "/finance/advance-payments"),
        ("应付核销", "/finance/manual-settlement"),
        ("供应商应付余额", "/finance/reports/payable-summary"),
        ("供应商对账单", "/finance/reports/supplier-statement"),
        ("应付账龄分析", "/finance/reports/aging-buckets"),
        ("项目/柜号应付明细", "/finance/reports/payable-detail"),
        ("采购发票登记列表", "/finance/purchase-invoices"),
    ],
    "发票管理": [
        ("新增销售发票", "/finance/sales-invoices/new"),
        ("销售发票", "/finance/sales-invoices"),
        ("销项发票明细", "/finance/reports/output-tax"),
        ("新增采购发票", "/finance/purchase-invoices/new"),
        ("采购发票", "/finance/purchase-invoices"),
        ("进项发票明细", "/finance/reports/input-tax"),
        ("未开票销售", "/finance/unbilled-sales"),
        ("未到票采购", "/finance/unreceived-purchase-invoices"),
        ("发票勾稽", "/finance/invoice-matching"),
        ("税额汇总表", "/finance/reports/tax-summary"),
    ],
    "资金管理": [
        ("银行账户余额", "/finance/reports/account-balance"),
        ("银行日记账", "/finance/bank-journal"),
        ("现金日记账", "/finance/cash-journal"),
        ("资金流水", "/finance/reports/cash-bank-transactions"),
        ("收款登记", "/finance/smart-collections"),
        ("付款登记", "/finance/smart-payments"),
        ("银行对账", "/finance/bank-reconciliation"),
        ("资金日报", "/finance/fund-daily"),
    ],
    "总账凭证": [
        ("凭证录入", "/finance/vouchers"),
        ("凭证列表", "/finance/vouchers"),
        ("自动生成凭证", "/finance/vouchers/generate"),
        ("科目余额表", "/finance/account-balance"),
        ("明细账", "/finance/detail-ledger"),
        ("总账", "/finance/general-ledger"),
    ],
    "存货核算": [
        ("存货核算首页", "/finance/inventory-accounting"),
        ("库存成本总账", "/finance/inventory-cost/summary"),
        ("库存成本明细账", "/finance/inventory-cost/detail"),
        ("存货与总账对账", "/finance/inventory-reconciliation"),
    ],
    "成本管理": [
        ("成本管理首页", "/finance/cost-management"),
        ("项目成本台账", "/finance/project-costs"),
        ("柜号成本台账", "/finance/cabinet-costs"),
        ("生产工单成本", "/finance/work-order-costs"),
        ("项目成本明细", "/finance/reports/project-cost"),
        ("柜号成本明细", "/finance/reports/machine-cost"),
        ("项目毛利分析", "/finance/reports/project-profit"),
        ("柜号毛利分析", "/finance/reports/cabinet-profit"),
    ],
    "期末处理": [
        ("月末结账", "/finance/period-close"),
        ("结账检查", "/finance/closing-checks"),
        ("期末调汇", "/finance/exchange-adjustment"),
    ],
    "财务报表": [
        ("经营财务快照", "/finance/financial-statements"),
        ("应收账款明细表", "/finance/reports/receivable-detail"),
        ("应付账款明细表", "/finance/reports/payable-detail"),
        ("往来余额明细", "/finance/reports/balance"),
    ],
    "财务设置": [
        ("财务设置首页", "/finance/settings"),
        ("科目映射设置", "/finance/account-mappings"),
        ("结账控制检查", "/finance/closing-checks"),
    ],
}

RUNTIME_PATHS = sorted({href for entries in PHASE1_MENU_COVERAGE.values() for _, href in entries})

LEGACY_REQUIRED = {
}

CANONICAL_FINANCE_DOCUMENT_PATHS = {
    "/finance/receipt-refunds/new",
    "/finance/advance-receipt-refunds/new",
    "/finance/other-income/new",
    "/finance/other-income-refunds/new",
    "/finance/payment-refunds/new",
    "/finance/advance-payment-refunds/new",
    "/finance/other-expenses/new",
    "/finance/other-expense-refunds/new",
}


def _finance_menu_block() -> str:
    template = (ROOT / "templates" / "base.html").read_text(encoding="utf-8", errors="ignore")
    start = template.find("{% if see_all or role == 'finance' %}")
    end = template.find("{% if see_all %}", start)
    return template[start:end] if start >= 0 and end > start else template


def _finance_menu_hrefs() -> list[str]:
    block = _finance_menu_block()
    return sorted(set(re.findall(r'href="(/finance[^"]*)"', block)))


def _audit_template() -> list[str]:
    block = _finance_menu_block()
    findings: list[str] = []
    if "财务管理" not in block:
        findings.append("templates/base.html missing finance parent 财务管理")
    if "财务/成本" in block:
        findings.append("templates/base.html still uses old parent 财务/成本")
    for group, entries in PHASE1_MENU_COVERAGE.items():
        if f">{group}</div>" not in block:
            findings.append(f"templates/base.html missing finance group {group}")
        group_pos = block.find(f">{group}</div>")
        if group_pos < 0:
            continue
        for label, href in entries:
            if label not in block:
                findings.append(f"templates/base.html missing finance menu label {label}")
            if f'href="{href}"' not in block:
                findings.append(f"templates/base.html missing finance menu href {href}")
    for href in LEGACY_REQUIRED:
        if f'href="{href}"' not in block:
            findings.append(f"templates/base.html lost existing finance document href {href}")
    for href in CANONICAL_FINANCE_DOCUMENT_PATHS:
        if f'href="{href}"' not in block:
            findings.append(f"templates/base.html missing canonical finance document href {href}")
    return findings


def _audit_permissions() -> list[str]:
    permissions = (ROOT / "services" / "pilot_permissions.py").read_text(encoding="utf-8", errors="ignore")
    findings: list[str] = []
    required_paths = {
        "/finance/receivables",
        "/finance/receipts",
        "/finance/advance-receipts",
        "/finance/receipt-refunds",
        "/finance/advance-receipt-refunds",
        "/finance/other-income",
        "/finance/other-income-refunds",
        "/finance/payables",
        "/finance/payments",
        "/finance/advance-payments",
        "/finance/payment-refunds",
        "/finance/advance-payment-refunds",
        "/finance/other-expenses",
        "/finance/other-expense-refunds",
        "/finance/sales-invoices",
        "/finance/purchase-invoices",
        "/finance/bank-journal",
    }
    for path in sorted(required_paths):
        if f'"path": "{path}"' not in permissions and f'"{path}"' not in permissions:
            findings.append(f"services/pilot_permissions.py missing canonical finance permission/path {path}")
    return findings


def _audit_routes(app) -> list[str]:
    rules = {
        rule.rule
        for rule in app.url_map.iter_rules()
        if "<" not in rule.rule and "GET" in rule.methods
    }
    findings = []
    for href in RUNTIME_PATHS:
        if href not in rules:
            findings.append(f"missing GET route for finance phase1 href {href}")
    block = _finance_menu_block()
    for href in _finance_menu_hrefs():
        if href not in rules:
            findings.append(f"finance menu href has no GET route {href}")
    return findings


def _audit_runtime(app) -> list[str]:
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "audit"
        session["role"] = "admin"
    findings = []
    runtime_paths = sorted(set(RUNTIME_PATHS) | set(_finance_menu_hrefs()))
    for path in runtime_paths:
        response = client.get(path, follow_redirects=False)
        if response.status_code >= 400:
            findings.append(f"{path} returned HTTP {response.status_code}")
    return findings


def _make_app():
    from app import create_app

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def main() -> int:
    findings = []
    app = _make_app()
    findings.extend(_audit_template())
    findings.extend(_audit_permissions())
    findings.extend(_audit_routes(app))
    findings.extend(_audit_runtime(app))
    if findings:
        print("finance_kingdee_blueprint_phase1_audit=failed")
        for finding in findings:
            print("FAIL " + finding)
        return 1
    print("finance_kingdee_blueprint_phase1_audit=ok")
    print(f"checked_groups={len(PHASE1_MENU_COVERAGE)} checked_paths={len(RUNTIME_PATHS)} checked_finance_menu_hrefs={len(_finance_menu_hrefs())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
