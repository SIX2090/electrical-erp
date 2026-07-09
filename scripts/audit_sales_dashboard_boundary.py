from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SALES_ROUTES = ROOT / "routes" / "sales_routes.py"
SALES_DASHBOARD = ROOT / "templates" / "sales_dashboard.html"


def fail(message):
    print(f"sales_dashboard_boundary=failed {message}")
    raise SystemExit(1)


def main():
    source = SALES_ROUTES.read_text(encoding="utf-8")
    template = SALES_DASHBOARD.read_text(encoding="utf-8")

    if "if not document_list:" not in source:
        fail("sales dashboard must branch away from full document-list queries")
    if "shipments=[]" not in source or "receipts=[]" not in source:
        fail("workbench must not pass recent shipment or receipt full lists")
    if "credit_alerts=credit_alerts" not in source:
        fail("workbench must expose credit alert queue")
    forbidden_template_terms = ("shipments", "receipts", "orders[:")
    for term in forbidden_template_terms:
        if term in template:
            fail(f"workbench template still renders full-list term {term}")
    required_terms = ("待发货", "应收跟进", "信用预警")
    for term in required_terms:
        if term not in template:
            fail(f"workbench template missing queue term {term}")
    print("sales_dashboard_boundary=ok")


if __name__ == "__main__":
    main()
