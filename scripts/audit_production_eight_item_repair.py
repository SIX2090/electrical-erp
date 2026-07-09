from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


ROUTES = [
    ("/work-orders", ("生产", "状态"), ()),
    ("/work-orders/new", ("生产", "项目", "机号"), ()),
    ("/production-completions", ("完工", "状态"), ()),
    ("/production-completions/new", ("完工", "来源"), ()),
    ("/production-enhance/quality-inspections", ("质量", "状态"), ()),
    ("/production-enhance/quality-inspections/new", ("质量",), ()),
    ("/production-schedules", ("生产排程", "下一步"), ()),
    ("/production-routings", ("工艺",), ()),
    ("/work-centers", ("工作中心",), ()),
    ("/engineering/kitting", ("齐套",), ()),
    ("/production-enhance/mrp-requirements", ("MRP",), ()),
    ("/procurement/suggestions", ("采购",), ()),
    ("/requisition", ("工单领料查询", "生产领料单列表"), ("新增生产领料单", "正式领料", "直接领料")),
    ("/production/reports/shortage", ("生产", "缺料"), ("新增", "提交", "过账")),
    ("/production/reports/work-order-detail", ("生产", "工单"), ("新增", "提交", "过账")),
    ("/production/reports", ("生产", "报表"), ("新增", "提交", "过账")),
]

DIRTY_MARKERS = tuple(chr(codepoint) for codepoint in (0x95BB, 0x7039, 0x5A75, 0x9420, 0x93C9, 0xFFFD))


def main() -> int:
    app = create_app()
    checks = []
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
            session["username"] = "audit"
        for path, required, forbidden in ROUTES:
            response = client.get(path)
            text = response.data.decode("utf-8", "ignore")
            main_text = text.split('<main class="main">', 1)[-1].split("</main>", 1)[0]
            checks.append((response.status_code == 200, path, "status", str(response.status_code)))
            for marker in required:
                checks.append((marker in main_text, path, f"visible:{marker}", "visible" if marker in main_text else "missing"))
            for marker in forbidden:
                checks.append((marker not in main_text, path, f"absent:{marker}", "absent" if marker not in main_text else "present"))
            dirty = any(marker in main_text for marker in DIRTY_MARKERS)
            checks.append((not dirty, path, "clean_text", "clean" if not dirty else "dirty"))

    failed = [item for item in checks if not item[0]]
    print(f"production_eight_item_repair_audit={'ok' if not failed else 'failed'}")
    print(f"checked_items={len(checks)}")
    for ok, path, name, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {path} | {name} | {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
