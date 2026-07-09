from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(findings, name, condition, detail):
    if not condition:
        findings.append(f"{name}: {detail}")


def audit_production_completion_source():
    route_text = (ROOT / "routes" / "production_completion_routes.py").read_text(encoding="utf-8")
    list_text = (ROOT / "templates" / "production_completion_list.html").read_text(encoding="utf-8")
    detail_text = (ROOT / "templates" / "production_completion_detail.html").read_text(encoding="utf-8")
    form_text = (ROOT / "templates" / "production_completion_form.html").read_text(encoding="utf-8")
    findings = []

    require(
        findings,
        "unified_completion_query",
        "def unified_completion_query(" in route_text
        and "production_completion_orders pc" in route_text
        and "wo_complete_items wc" in route_text
        and "'legacy' AS source" in route_text
        and "'new' AS source" in route_text,
        "completion query must combine formal completion documents and legacy completion rows",
    )
    require(
        findings,
        "completion_list_uses_unified_query",
        "rows = unified_completion_query(include_legacy=True, keyword=keyword, status=status)" in route_text,
        "completion list must use unified completion query for normal display and filters",
    )
    require(
        findings,
        "completion_detail_summary",
        "def completion_summary_for_order(" in route_text
        and "completion_summary=completion_summary" in route_text
        and "本工单完工汇总" in detail_text,
        "completion detail must show formal, legacy, stock, and reverse-posting summary",
    )
    require(
        findings,
        "completion_source_badges",
        "历史完工" in list_text and "正式单据" in list_text and "row.source == 'legacy'" in list_text,
        "completion list must visibly distinguish legacy rows from formal documents",
    )
    require(
        findings,
        "completion_reverse_posting",
        "def reverse_post_document(" in route_text
        and "完工入库反过账" in route_text
        and "/production-completions/{{ doc.id }}/reverse" in detail_text,
        "posted completion documents must expose controlled reverse posting",
    )
    require(
        findings,
        "completion_posting_writes_downstream",
        "INSERT INTO wo_complete_items" in route_text
        and "apply_inventory_movement(" in route_text
        and "recompute_work_order_status(order)" in route_text
        and "source_doc_no" in route_text,
        "posting must write completion detail, inventory movement, source link, and work-order status",
    )
    require(
        findings,
        "entry_and_list_separated",
        "/production-completions/new" in form_text
        or ("完工入库单" in form_text and "work_order_id" in form_text and "返回列表" in form_text),
        "completion entry page must remain separate from the list page",
    )
    return findings


def main() -> int:
    findings = audit_production_completion_source()
    if findings:
        print("production_completion_source_audit=failed")
        for item in findings:
            print(item)
        return 1
    print("production_completion_source_audit=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
