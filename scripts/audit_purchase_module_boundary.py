from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message):
    raise SystemExit(f"purchase boundary audit failed: {message}")


def main():
    dashboard = (ROOT / "templates" / "purchase_dashboard.html").read_text(encoding="utf-8")
    if "/payables/{{ row.id }}" in dashboard or "应付账款</h2>" in dashboard:
        fail("purchase workbench renders a payable list")
    if 'method="post" action="/purchase_order/{{ row.id }}/receive"' in dashboard:
        fail("purchase workbench posts receipt creation directly")

    order_list = (ROOT / "templates" / "purchase_order_list.html").read_text(encoding="utf-8")
    for term in ("预计到货", "未收", "待收货"):
        if term not in order_list:
            fail(f"purchase order list missing arrival warning term: {term}")

    receipt_list = (ROOT / "templates" / "purchase_receipt_dashboard.html").read_text(encoding="utf-8")
    for term in ("质检待检", "已入库记账", "采购入库单列表"):
        if term not in receipt_list:
            fail(f"purchase receipt list missing status filter term: {term}")

    payable_list = (ROOT / "templates" / "payable_list.html").read_text(encoding="utf-8")
    for term in ("供应商", "账期/到期", "未付余额"):
        if term not in payable_list:
            fail(f"payable list missing key field: {term}")

    print("purchase boundary audit passed")


if __name__ == "__main__":
    main()
