from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def require(condition: bool, message: str, findings: list[str]) -> None:
    if not condition:
        findings.append(message)


def main() -> int:
    findings: list[str] = []
    finance_routes = read_text("routes/finance_routes.py")
    base = read_text("templates/base.html")
    workbench = read_text("templates/finance_ar_ap_workbench.html")
    permissions = read_text("services/pilot_permissions.py")
    classification = read_text("MENU_ROLLOUT_CLASSIFICATION.md")
    schema = read_text("services/schema_migrations.py")
    route_catalog = read_text("routes/route_catalog.py")
    app = read_text("app.py")
    entry_template = read_text("templates/finance_exchange_adjustment.html")
    list_template = read_text("templates/finance_exchange_adjustment_list.html")

    for route in (
        "/finance/exchange-adjustment",
        "/finance/exchange-adjustments",
        "/finance/exchange-adjustments/<int:adjustment_id>/audit",
    ):
        require(route in finance_routes, f"missing route: {route}", findings)

    for token in (
        "finance_exchange_adjustments",
        "finance_exchange_adjustment_lines",
        "exchange_gain_loss",
    ):
        require(token in schema, f"missing schema token: {token}", findings)

    for label in ("期末调汇", "调汇单查询"):
        require(label in base, f"missing base navigation label: {label}", findings)
        require(label in workbench, f"missing workbench shortcut label: {label}", findings)

    require("finance_exchange_adjustment" in permissions, "missing exchange adjustment permission feature", findings)
    require("finance_exchange_adjustment_list" in permissions, "missing exchange adjustment list permission feature", findings)
    require('{"view", "export"}' in permissions, "readonly list permission should include view/export only", findings)
    require("/finance/exchange-adjustment" in classification, "missing exchange adjustment classification", findings)
    require("/finance/exchange-adjustments" in classification, "missing exchange adjustment list classification", findings)
    require("/finance/exchange-adjustment" in route_catalog, "missing exchange adjustment route catalog", findings)
    require("/finance/exchange-adjustments" in route_catalog, "missing exchange adjustment list route catalog", findings)
    require("path in {\"/finance/period-close\", \"/finance/exchange-adjustment\", \"/finance/exchange-adjustments\"}" in app, "missing high-risk access guard", findings)

    require("生成调汇单" in entry_template, "entry template must expose generate action", findings)
    require("生成并审核" in entry_template, "entry template must expose audit workflow", findings)
    require("本页只做查询、导出和跳转" in list_template, "list template must state readonly boundary", findings)
    require('href="/finance/exchange-adjustment"' in list_template, "list template should link to independent entry page", findings)
    require('action="/finance/exchange-adjustments/{{ row.id }}/audit"' in list_template, "list template should support status-aware audit", findings)

    forbidden_list_tokens = ('name="action" value="generate"', "生成调汇单</button>")
    for token in forbidden_list_tokens:
        require(token not in list_template, f"list page contains document generation action: {token}", findings)

    if findings:
        print("finance_period_end_exchange_audit=failed")
        for item in findings:
            print(f"error | {item}")
        return 1
    print("finance_period_end_exchange_audit=ok")
    print("routes=3 permissions=2 templates=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
