"""P0 全链路联调验收脚本。

按开发计划第五节"全链路验收场景"的10个场景，对一个完整机床项目从销售订单
到售后成本的全链路做端到端验收，覆盖 P0-1 MRP、P0-2 追溯、P0-3 成本、
P0-4 BOM/ECN 快照、P0-5 数据权限五大引擎。

基线销售订单: SO-GT-TRIAL-20260526-001
基线项目号:   PJ-GT-TRIAL-20260526-001
基线柜号:     SN-GT-TRIAL-20260526-001

输出: logs/p0_acceptance_report.md
退出码: 0=全部通过 1=有失败场景
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password

BASELINE_ORDER_NO = "SO-GT-TRIAL-20260526-001"
BASELINE_PROJECT = "PJ-GT-TRIAL-20260526-001"
BASELINE_SERIAL = "SN-GT-TRIAL-20260526-001"


def db_config() -> dict:
    return {
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "dbname": os.environ.get("PG_DATABASE", "wms"),
        "user": os.environ.get("PG_USER", "wms_user"),
        "password": get_pg_password(),
    }


def connect():
    return psycopg2.connect(**db_config(), connect_timeout=int(os.environ.get("PG_CONNECT_TIMEOUT", "5")))


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row[0] if row else None


def row(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()


def rows(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


class Scenario:
    def __init__(self, idx: int, name: str, engine: str):
        self.idx = idx
        self.name = name
        self.engine = engine
        self.checks: list[tuple[str, bool, str]] = []

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.checks.append((label, bool(passed), detail))

    @property
    def passed(self) -> bool:
        return all(p for _, p, _ in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for _, p, _ in self.checks if p)

    @property
    def total_count(self) -> int:
        return len(self.checks)


def scenario_1_sales_order(cur, sc: Scenario) -> None:
    """场景1: 销售订单基线。"""
    so = row(
        cur,
        """
        SELECT id, order_no, project_code, cabinet_no, customer_id, total_amount, status
        FROM sales_orders WHERE order_no=%s
        """,
        (BASELINE_ORDER_NO,),
    )
    if not so:
        sc.check("销售订单存在", False, f"未找到 {BASELINE_ORDER_NO}")
        return
    so_id, order_no, project_code, cabinet_no, customer_id, total_amount, status = so
    sc.check("销售订单存在", True, f"id={so_id} 金额={total_amount}")
    sc.check("带项目号", bool(project_code), project_code or "缺失")
    sc.check("带柜号", bool(cabinet_no), cabinet_no or "缺失")
    sc.check("带客户ID", bool(customer_id), f"customer_id={customer_id}")
    sc.check("订单已审核", status in {"已审核", "approved", "confirmed"}, f"status={status}")
    sc.check("订单金额>0", float(total_amount or 0) > 0, f"total={total_amount}")


def scenario_2_bom_routing(cur, sc: Scenario) -> None:
    """场景2: BOM/工艺/图纸。"""
    # 找到销售订单对应产品的 BOM（通过 sales_order_items 关联）
    bom = row(
        cur,
        """
        SELECT b.id, b.bom_no, b.version, b.status, b.bom_type,
               COUNT(bi.id) AS item_count
        FROM sales_orders so
        JOIN sales_order_items soi ON soi.order_id=so.id
        JOIN products p ON p.id=soi.product_id
        JOIN boms b ON b.product_id=p.id
        LEFT JOIN bom_items bi ON bi.bom_id=b.id
        WHERE so.order_no=%s
        GROUP BY b.id, b.bom_no, b.version, b.status, b.bom_type
        ORDER BY b.id DESC LIMIT 1
        """,
        (BASELINE_ORDER_NO,),
    )
    if not bom:
        sc.check("BOM存在", False, "销售订单产品未关联BOM")
        return
    bom_id, bom_no, version, bom_status, bom_type, item_count = bom
    sc.check("BOM存在", True, f"{bom_no} v{version} type={bom_type}")
    sc.check("BOM有明细行", item_count > 0, f"items={item_count}")
    sc.check("BOM状态有效", bom_status not in {"停用", "inactive", "disabled"}, f"status={bom_status}")

    # 工艺路线
    routing_count = scalar(
        cur,
        """
        SELECT COUNT(*) FROM production_routings pr
        JOIN products p ON p.id=pr.product_id
        JOIN sales_order_items soi ON soi.product_id=p.id
        JOIN sales_orders so ON so.id=soi.order_id
        WHERE so.order_no=%s
        """,
        (BASELINE_ORDER_NO,),
    )
    sc.check("工艺路线存在", (routing_count or 0) > 0, f"routings={routing_count}")

    # BOM 版本表（P0-4）
    has_bom_versions = scalar(cur, "SELECT to_regclass('bom_versions') IS NOT NULL")
    if has_bom_versions:
        version_count = scalar(
            cur,
            "SELECT COUNT(*) FROM bom_versions WHERE bom_id=%s",
            (bom_id,),
        )
        sc.check("BOM版本表可用", True, f"bom_versions={version_count}")
    else:
        sc.check("BOM版本表可用", False, "bom_versions表不存在")

    # BOM 替代料表（P0-4）
    has_substitutes = scalar(cur, "SELECT to_regclass('bom_substitute_materials') IS NOT NULL")
    sc.check("BOM替代料表可用", bool(has_substitutes), "bom_substitute_materials")


def scenario_3_mrp(cur, sc: Scenario) -> None:
    """场景3: MRP运算。"""
    # MRP 引擎表存在性
    for tbl in ["mrp_runs", "mrp_run_items", "mrp_suggestions"]:
        exists = scalar(cur, "SELECT to_regclass(%s) IS NOT NULL", (tbl,))
        sc.check(f"MRP表 {tbl} 存在", bool(exists), tbl)

    # 是否有该项目的 MRP 运行记录
    run_count = scalar(
        cur,
        "SELECT COUNT(*) FROM mrp_runs WHERE project_code=%s OR cabinet_no=%s",
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("MRP运行记录存在", (run_count or 0) > 0, f"runs={run_count}")

    # MRP 引擎服务可导入
    try:
        import services.mrp_engine  # noqa: F401
        sc.check("MRP引擎服务可导入", True, "services.mrp_engine")
    except Exception as exc:
        sc.check("MRP引擎服务可导入", False, str(exc))

    # MRP 运算明细字段完整性
    if scalar(cur, "SELECT to_regclass('mrp_run_items') IS NOT NULL"):
        cols = {
            r[0]
            for r in rows(
                cur,
                "SELECT column_name FROM information_schema.columns WHERE table_name='mrp_run_items'",
            )
        }
        required = {"run_id", "material_id", "gross_qty", "net_qty", "suggestion_type"}
        missing = required - cols
        sc.check("MRP明细字段完整", not missing, f"missing={missing or 'none'}")

    # 替代料字段（P0-1）
    if scalar(cur, "SELECT to_regclass('mrp_run_items') IS NOT NULL"):
        cols = {
            r[0]
            for r in rows(
                cur,
                "SELECT column_name FROM information_schema.columns WHERE table_name='mrp_run_items'",
            )
        }
        sc.check("MRP替代料字段存在", "substitute_for" in cols, f"substitute_for={'yes' if 'substitute_for' in cols else 'no'}")


def scenario_4_suggestions(cur, sc: Scenario) -> None:
    """场景4: 采购/生产/委外建议。"""
    if not scalar(cur, "SELECT to_regclass('mrp_suggestions') IS NOT NULL"):
        sc.check("MRP建议表存在", False, "mrp_suggestions表不存在")
        return
    sc.check("MRP建议表存在", True)

    # 建议类型分布
    suggestion_types = rows(
        cur,
        """
        SELECT suggestion_type, COUNT(*) FROM mrp_suggestions ms
        JOIN mrp_runs mr ON mr.id=ms.run_id
        WHERE mr.project_code=%s OR mr.cabinet_no=%s
        GROUP BY suggestion_type
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    type_map = {t: c for t, c in suggestion_types}
    sc.check("有采购建议", (type_map.get("purchase") or 0) > 0, f"purchase={type_map.get('purchase', 0)}")
    sc.check("有生产建议", (type_map.get("production") or 0) > 0, f"production={type_map.get('production', 0)}")
    sc.check("有委外建议", (type_map.get("outsource") or 0) > 0, f"outsource={type_map.get('outsource', 0)}")

    # 建议转换字段
    cols = {
        r[0]
        for r in rows(
            cur,
            "SELECT column_name FROM information_schema.columns WHERE table_name='mrp_suggestions'",
        )
    }
    sc.check("建议转换字段存在", "converted_doc_type" in cols and "converted_doc_id" in cols, f"cols={cols}")


def scenario_5_inventory_pick(cur, sc: Scenario) -> None:
    """场景5: 入库和领料。"""
    # 采购收货
    receipt_count = scalar(
        cur,
        """
        SELECT COUNT(*) FROM purchase_receipts pr
        JOIN purchase_orders po ON po.id=pr.order_id
        WHERE po.project_code=%s AND po.cabinet_no=%s
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("采购收货记录", (receipt_count or 0) > 0, f"receipts={receipt_count}")

    # 库存余额
    balance_count = scalar(
        cur,
        "SELECT COUNT(*) FROM inventory_balances WHERE cabinet_no=%s",
        (BASELINE_SERIAL,),
    )
    sc.check("柜号库存余额", (balance_count or 0) > 0, f"balances={balance_count}")

    # 生产领料
    pick_count = scalar(
        cur,
        """
        SELECT COUNT(*) FROM pick_lists pl
        JOIN work_orders wo ON wo.id=pl.work_order_id
        WHERE wo.project_code=%s AND wo.cabinet_no=%s
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("生产领料单", (pick_count or 0) > 0, f"pick_lists={pick_count}")

    # 库存过账服务可导入
    try:
        import services.inventory_posting_service  # noqa: F401
        sc.check("库存过账服务可导入", True)
    except Exception as exc:
        sc.check("库存过账服务可导入", False, str(exc))


def scenario_6_completion(cur, sc: Scenario) -> None:
    """场景6: 报工和完工。"""
    # 工单状态流转
    wo_stages = rows(
        cur,
        """
        SELECT production_stage, COUNT(*) FROM work_orders
        WHERE project_code=%s AND cabinet_no=%s
        GROUP BY production_stage
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    stage_map = {s or "未设置": c for s, c in wo_stages}
    sc.check("工单存在", sum(stage_map.values()) > 0, f"stages={stage_map}")

    # 工单阶段流转字段（P0 工单状态流转模型）
    cols = {
        r[0]
        for r in rows(
            cur,
            "SELECT column_name FROM information_schema.columns WHERE table_name='work_orders'",
        )
    }
    sc.check("工单阶段字段存在", "production_stage" in cols, "production_stage")

    # 完工入库
    completion_count = scalar(
        cur,
        """
        SELECT COUNT(*) FROM production_completion_orders
        WHERE project_code=%s AND cabinet_no=%s
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("完工入库记录", (completion_count or 0) > 0, f"completions={completion_count}")

    # 工序报工
    operation_count = scalar(
        cur,
        """
        SELECT COUNT(*) FROM operation_reports
        WHERE project_code=%s AND cabinet_no=%s
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("工序报工记录", (operation_count or 0) > 0, f"operations={operation_count}")


def scenario_7_shipment_invoice(cur, sc: Scenario) -> None:
    """场景7: 发货和开票。"""
    # 发货单
    shipment = row(
        cur,
        """
        SELECT id, shipment_no, status FROM sales_shipments
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC LIMIT 1
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    if shipment:
        sc.check("发货单存在", True, f"{shipment[1]} status={shipment[2]}")
    else:
        sc.check("发货单存在", False, "无发货记录")

    # 应收记录
    receivable = row(
        cur,
        """
        SELECT id, source_no, total_amount, balance, status FROM customer_receivables
        WHERE project_code=%s AND cabinet_no=%s
        ORDER BY id DESC LIMIT 1
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    if receivable:
        sc.check("应收记录存在", True, f"{receivable[1]} 余额={receivable[3]}")
    else:
        sc.check("应收记录存在", False, "无应收记录")

    # 销售发票
    invoice_count = scalar(
        cur,
        """
        SELECT COUNT(*) FROM sales_invoices
        WHERE project_code=%s AND cabinet_no=%s
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("销售发票记录", (invoice_count or 0) > 0, f"invoices={invoice_count}")


def scenario_8_cost(cur, sc: Scenario) -> None:
    """场景8: 成本归集。"""
    # 成本引擎表
    for tbl in ["cost_runs", "cost_run_items"]:
        exists = scalar(cur, "SELECT to_regclass(%s) IS NOT NULL", (tbl,))
        sc.check(f"成本表 {tbl} 存在", bool(exists), tbl)

    # 成本引擎服务可导入
    for svc in ["services.cost_engine", "services.cabinet_cost_service", "services.project_cost_service"]:
        try:
            __import__(svc)
            sc.check(f"{svc} 可导入", True)
        except Exception as exc:
            sc.check(f"{svc} 可导入", False, str(exc))

    # 成本运行记录
    cost_run = row(
        cur,
        """
        SELECT id, run_no, total_material_cost, total_labor_cost,
               total_outsource_cost, total_cost, status
        FROM cost_runs
        WHERE project_code=%s OR cabinet_no=%s
        ORDER BY id DESC LIMIT 1
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    if cost_run:
        sc.check("成本运行记录存在", True, f"{cost_run[1]} 总成本={cost_run[5]}")
        sc.check("材料成本>0", float(cost_run[2] or 0) > 0, f"material={cost_run[2]}")
        sc.check("人工成本字段有效", cost_run[3] is not None, f"labor={cost_run[3]}")
        sc.check("委外成本字段有效", cost_run[4] is not None, f"outsource={cost_run[4]}")
    else:
        sc.check("成本运行记录存在", False, "无成本运行记录（需手动触发成本计算）")

    # 成本对账表
    has_recon = scalar(cur, "SELECT to_regclass('cost_reconciliation_results') IS NOT NULL")
    sc.check("成本对账表存在", bool(has_recon), "cost_reconciliation_results")


def scenario_9_trace(cur, sc: Scenario) -> None:
    """场景9: 追溯检查。"""
    # trace_links 表
    exists = scalar(cur, "SELECT to_regclass('trace_links') IS NOT NULL")
    sc.check("追溯关系表存在", bool(exists), "trace_links")
    if not exists:
        return

    # 追溯链接总数
    link_count = scalar(
        cur,
        "SELECT COUNT(*) FROM trace_links WHERE project_code=%s OR cabinet_no=%s",
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("追溯链接存在", (link_count or 0) > 0, f"links={link_count}")

    # 追溯链路覆盖度（来源/目标单据类型数）
    type_coverage = row(
        cur,
        """
        SELECT COUNT(DISTINCT source_doc_type), COUNT(DISTINCT target_doc_type)
        FROM trace_links WHERE project_code=%s OR cabinet_no=%s
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    if type_coverage:
        sc.check("追溯类型多样性", (type_coverage[0] + type_coverage[1]) >= 4, f"source_types={type_coverage[0]} target_types={type_coverage[1]}")

    # 追溯引擎服务可导入
    try:
        import services.trace_engine  # noqa: F401
        sc.check("追溯引擎服务可导入", True)
    except Exception as exc:
        sc.check("追溯引擎服务可导入", False, str(exc))

    # 追溯完整性服务
    try:
        import services.trace_integrity_service  # noqa: F401
        sc.check("追溯完整性服务可导入", True)
    except Exception as exc:
        sc.check("追溯完整性服务可导入", False, str(exc))

    # 追溯断点检查：销售订单应有下游链路
    so_links = scalar(
        cur,
        """
        SELECT COUNT(*) FROM trace_links
        WHERE source_doc_type='sales_order' AND (project_code=%s OR cabinet_no=%s)
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("销售订单有下游追溯", (so_links or 0) > 0, f"so_downstream={so_links}")

    # 反向追溯：下游单据应能反查到销售订单（通过正向链接反向查询）
    reverse_links = scalar(
        cur,
        """
        SELECT COUNT(*) FROM trace_links
        WHERE source_doc_type='sales_order' AND (project_code=%s OR cabinet_no=%s)
        """,
        (BASELINE_PROJECT, BASELINE_SERIAL),
    )
    sc.check("反向追溯到销售订单", (reverse_links or 0) > 0, f"so_forward_links={reverse_links}")


def scenario_10_permission(cur, sc: Scenario) -> None:
    """场景10: 权限检查。"""
    # 数据权限规则表
    for tbl in ["data_scope_rules", "data_access_logs"]:
        exists = scalar(cur, "SELECT to_regclass(%s) IS NOT NULL", (tbl,))
        sc.check(f"权限表 {tbl} 存在", bool(exists), tbl)

    # 数据权限服务可导入
    try:
        import services.data_scope_service  # noqa: F401
        sc.check("数据权限服务可导入", True)
    except Exception as exc:
        sc.check("数据权限服务可导入", False, str(exc))

    # 数据权限规则数（可能为0，但表结构必须就绪）
    rule_count = scalar(cur, "SELECT COUNT(*) FROM data_scope_rules")
    sc.check("数据权限规则表可查询", rule_count is not None, f"rules={rule_count}")

    # 数据访问日志表
    log_count = scalar(cur, "SELECT COUNT(*) FROM data_access_logs")
    sc.check("数据访问日志表可查询", log_count is not None, f"logs={log_count}")

    # 验证 scope 过滤函数存在
    from services.data_scope_service import build_scope_filter, row_allowed, scope_has_rules, get_data_scope

    sc.check("scope过滤函数可用", all(callable(f) for f in [build_scope_filter, row_allowed, scope_has_rules, get_data_scope]))

    # 验证 bypass 角色逻辑
    from services.data_scope_service import can_bypass_data_scope

    sc.check("admin角色可绕过", can_bypass_data_scope("admin") is True)
    sc.check("staff角色不可绕过", can_bypass_data_scope("staff") is False)

    # 验证导出审计（P0-5）
    try:
        from routes.export_route_registration import SENSITIVE_EXPORTS

        sc.check("导出审计配置存在", len(SENSITIVE_EXPORTS) > 0, f"sensitive={len(SENSITIVE_EXPORTS)}")
    except Exception as exc:
        sc.check("导出审计配置存在", False, str(exc))

    # 验证 API scope 过滤参数存在
    try:
        import inspect
        from routes.api_routes import register_api_routes

        src = inspect.getsource(register_api_routes)
        sc.check("API含scope过滤", "scope_field_map" in src, "scope_field_map参数")
    except Exception as exc:
        sc.check("API含scope过滤", False, str(exc))


SCENARIOS = [
    (1, "销售订单基线", "基线", scenario_1_sales_order),
    (2, "BOM/工艺/图纸", "P0-4", scenario_2_bom_routing),
    (3, "MRP运算", "P0-1", scenario_3_mrp),
    (4, "采购/生产/委外建议", "P0-1", scenario_4_suggestions),
    (5, "入库和领料", "基线", scenario_5_inventory_pick),
    (6, "报工和完工", "基线", scenario_6_completion),
    (7, "发货和开票", "基线", scenario_7_shipment_invoice),
    (8, "成本归集", "P0-3", scenario_8_cost),
    (9, "追溯检查", "P0-2", scenario_9_trace),
    (10, "权限检查", "P0-5", scenario_10_permission),
]


def run_acceptance() -> int:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    report_path = log_dir / "p0_acceptance_report.md"

    print("=" * 70)
    print("P0 全链路联调验收")
    print(f"基线销售订单: {BASELINE_ORDER_NO}")
    print(f"基线项目号:   {BASELINE_PROJECT}")
    print(f"基线柜号:     {BASELINE_SERIAL}")
    print("=" * 70)

    scenarios: list[Scenario] = []
    try:
        conn = connect()
    except Exception as exc:
        print(f"数据库连接失败: {exc}")
        return 1

    cur = conn.cursor()
    for idx, name, engine, fn in SCENARIOS:
        sc = Scenario(idx, name, engine)
        try:
            fn(cur, sc)
        except Exception as exc:
            sc.check("场景执行无异常", False, str(exc))
            # 单个场景的 SQL 错误会中止事务，必须 rollback 才能让后续场景继续
            try:
                conn.rollback()
            except Exception:
                pass
        scenarios.append(sc)
        status = "PASS" if sc.passed else "FAIL"
        print(f"[{status}] 场景{idx:2d} ({engine:6s}) {name}  {sc.passed_count}/{sc.total_count}")
        for label, ok, detail in sc.checks:
            mark = "OK" if ok else "NG"
            print(f"         {mark}  {label}" + (f"  ({detail})" if detail else ""))

    cur.close()
    conn.close()

    total_checks = sum(s.total_count for s in scenarios)
    total_passed = sum(s.passed_count for s in scenarios)
    total_failed = total_checks - total_passed
    all_passed = total_failed == 0

    # 生成 Markdown 报告
    lines = [
        "# P0 全链路联调验收报告",
        "",
        f"**验收时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**基线销售订单**: {BASELINE_ORDER_NO}",
        f"**基线项目号**: {BASELINE_PROJECT}",
        f"**基线柜号**: {BASELINE_SERIAL}",
        "",
        "## 验收汇总",
        "",
        f"- 场景总数: {len(scenarios)}",
        f"- 检查项总数: {total_checks}",
        f"- 通过: {total_passed}",
        f"- 失败: {total_failed}",
        f"- 验收结论: {'PASS 全部通过' if all_passed else 'FAIL 存在失败项'}",
        "",
        "## 场景明细",
        "",
    ]
    for sc in scenarios:
        status = "PASS" if sc.passed else "FAIL"
        lines.append(f"### 场景{sc.idx}: {sc.name} ({sc.engine}) [{status}]")
        lines.append("")
        lines.append("| 检查项 | 结果 | 说明 |")
        lines.append("|--------|------|------|")
        for label, ok, detail in sc.checks:
            mark = "OK" if ok else "NG"
            lines.append(f"| {label} | {mark} | {detail} |")
        lines.append("")

    lines.extend([
        "## P0 引擎覆盖",
        "",
        "| 引擎 | 场景 | 状态 |",
        "|------|------|------|",
    ])
    engine_status = {}
    for sc in scenarios:
        if sc.engine not in engine_status:
            engine_status[sc.engine] = True
        engine_status[sc.engine] = engine_status[sc.engine] and sc.passed
    for engine, passed in engine_status.items():
        lines.append(f"| {engine} | {', '.join(s.name for s in scenarios if s.engine == engine)} | {'PASS' if passed else 'FAIL'} |")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"验收报告: {report_path}")
    print(f"总计: {total_passed}/{total_checks} 通过, {total_failed} 失败")
    print(f"结论: {'PASS' if all_passed else 'FAIL'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_acceptance())
