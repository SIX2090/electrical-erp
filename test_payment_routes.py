import os
os.environ['PG_PASSWORD'] = 'admin'
os.environ['INVENTORY_NAV_MODE'] = 'gt_pilot'

from app import app

print("\n=== 检查所有 /payments 相关路由 ===\n")

routes = [
    (r.rule, r.endpoint, sorted(r.methods - {'HEAD', 'OPTIONS'}))
    for r in app.url_map.iter_rules()
    if '/payments' in r.rule
]

for rule, endpoint, methods in sorted(routes):
    print(f"{rule:60} {endpoint:50} {methods}")

print("\n=== 检查 supplier_payment_detail endpoint ===\n")

try:
    from flask import url_for
    with app.test_request_context():
        # 尝试生成 supplier_payment_detail 的 URL
        url = url_for('supplier_payment_detail', payment_id=1)
        print(f"url_for('supplier_payment_detail', payment_id=1) = {url}")
except Exception as e:
    print(f"错误: {e}")

print("\n=== 测试完成 ===")
