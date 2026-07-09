"""ERP 综合测试运行器 - 方案 A：轻量整合器。

把 scripts/ 下分散的审计脚本按业务模块分组，提供统一命令行入口，
一键运行并汇总通过/失败/跳过数量。

使用方式:
    python scripts/erp_test_runner.py --list           # 列出所有可用测试组
    python scripts/erp_test_runner.py --group core     # 只跑核心审计
    python scripts/erp_test_runner.py --group all      # 跑全部测试
    python scripts/erp_test_runner.py --group core,permissions  # 跑多个组
    python scripts/erp_test_runner.py --group core --verbose    # 显示详细输出
    python scripts/erp_test_runner.py --group core --report md  # 生成 Markdown 报告
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# 环境默认值（可被外部环境变量覆盖）
# ---------------------------------------------------------------------------
DEFAULT_ENV = {
    "PG_PASSWORD": "admin",
    "PG_HOST": "127.0.0.1",
    "PG_PORT": "5432",
    "PG_DATABASE": "wms",
    "PG_USER": "wms_user",
    "INVENTORY_NAV_MODE": "gt_pilot",
    "WTF_CSRF_ENABLED": "0",
    "PYTHONIOENCODING": "utf-8",
}


# ---------------------------------------------------------------------------
# 测试分组定义
# ---------------------------------------------------------------------------
@dataclass
class TestItem:
    """单个测试项。"""

    name: str
    command: list[str]
    description: str = ""
    timeout: int = 300  # 单个脚本超时秒数

    @property
    def label(self) -> str:
        return self.name


@dataclass
class TestGroup:
    """测试分组。"""

    key: str
    title: str
    description: str
    items: list[TestItem] = field(default_factory=list)


def _py(script_name: str, description: str = "", timeout: int = 300) -> TestItem:
    """构造一个运行 scripts/ 下脚本的 TestItem。"""
    return TestItem(
        name=script_name,
        command=[PYTHON, str(SCRIPTS_DIR / script_name)],
        description=description,
        timeout=timeout,
    )


def _compileall(targets: list[str], description: str = "") -> TestItem:
    """构造一个 compileall 检查项。"""
    return TestItem(
        name=f"compileall({' '.join(targets)})",
        command=[PYTHON, "-m", "compileall", *targets],
        description=description,
        timeout=120,
    )


def _ruff(targets: list[str], description: str = "") -> TestItem:
    """构造一个 ruff 静态分析检查项。"""
    return TestItem(
        name=f"ruff({' '.join(targets)})",
        command=[PYTHON, "-m", "ruff", "check", *targets],
        description=description,
        timeout=120,
    )


def _bandit(targets: list[str], description: str = "") -> TestItem:
    """构造一个 bandit 安全扫描检查项。"""
    return TestItem(
        name=f"bandit({' '.join(targets)})",
        command=[PYTHON, "-m", "bandit", "-r", *targets, "-ll"],
        description=description,
        timeout=120,
    )


def build_groups() -> list[TestGroup]:
    """构建所有测试分组。"""
    groups: list[TestGroup] = []

    # -----------------------------------------------------------------------
    # core: 核心审计（AGENTS.md Verification 章节要求的必跑项）
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="core",
        title="核心审计",
        description="AGENTS.md 要求的必跑审计：语法、源码完整性、上线前审计、CRUD 完整性",
        items=[
            _compileall(["app.py", "routes", "services", "scripts"], "Python 语法编译检查"),
            _py("source_integrity_audit.py", "源码完整性（中文乱码检测）"),
            _py("erp_prelaunch_audit.py", "ERP 上线前审计"),
            _py("audit_erp_crud_completeness.py", "CRUD 完整性审计"),
        ],
    ))

    # -----------------------------------------------------------------------
    # permissions: 权限与导航
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="permissions",
        title="权限与导航",
        description="pilot 角色权限矩阵、菜单可见性、直连路由访问控制",
        items=[
            _py("audit_trial_direct_access_matrix.py", "直连路由访问矩阵"),
            _py("audit_trial_visible_navigation.py", "可见导航审计"),
            _py("audit_trial_user_menus.py", "用户菜单审计"),
            _py("audit_trial_user_access.py", "用户访问权限审计"),
            _py("audit_trial_high_risk_role_matrix.py", "高风险角色矩阵"),
            _py("audit_trial_action_boundary.py", "操作边界审计"),
            _py("audit_trial_post_action_scope.py", "提交操作范围审计"),
            _py("audit_trial_role_permissions_page.py", "角色权限页面审计"),
            _py("audit_trial_core_document_fields.py", "核心单据字段审计"),
            _py("audit_trial_sales_menu_entries.py", "销售菜单条目审计"),
            _py("audit_trial_operator_task_queues.py", "操作员任务队列审计"),
            _py("verify_role_permission_matrix.py", "角色权限矩阵验证"),
            _py("verify_navigation_integrity.py", "导航完整性验证"),
        ],
    ))

    # -----------------------------------------------------------------------
    # inventory: 库存
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="inventory",
        title="库存模块",
        description="库存余额一致性、出入库操作、调拨、盘点",
        items=[
            _py("audit_inventory_balance_consistency.py", "库存余额一致性"),
            _py("audit_inventory_operation_gaps.py", "库存操作缺口审计"),
            _py("audit_inventory_movement_line_fields.py", "库存移动单行字段审计"),
            _py("audit_inventory_pending_posting_flow.py", "库存待过账流程审计"),
            _py("audit_inventory_return_and_reports.py", "库存退货与报表审计"),
            _py("audit_inventory_batch_balance.py", "库存批次余额审计"),
            _py("audit_inventory_bulk_list_runtime.py", "库存批量列表运行时审计"),
            _py("audit_inventory_bulk_list_actions.py", "库存批量列表操作审计"),
            _py("audit_inventory_other_movement_backend.py", "库存其他移动后端审计"),
            _py("audit_inventory_12_issue_closure.py", "库存 12 项问题闭环审计"),
            _py("audit_inventory_screenshot4_scope.py", "库存截图4范围审计"),
        ],
    ))

    # -----------------------------------------------------------------------
    # finance: 财务
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="finance",
        title="财务模块",
        description="AR/AP、凭证、银行对账、期末关账",
        items=[
            _py("audit_finance_phase1_closure.py", "财务一期闭环审计"),
            _py("audit_finance_business_exceptions.py", "财务业务异常审计"),
            _py("audit_finance_bank_reconciliation.py", "银行对账审计"),
            _py("audit_finance_voucher_generation_preview.py", "凭证生成预览审计"),
            _py("audit_finance_period_close_voucher_date.py", "期末关账凭证日期审计"),
            _py("audit_finance_ar_documents.py", "应收单据审计"),
            _py("audit_finance_ap_documents.py", "应付单据审计"),
            _py("audit_finance_ar_ap_enhancement.py", "应收应付增强审计"),
            _py("audit_finance_cash_bank_account_governance.py", "现金银行账户治理审计"),
            _py("audit_finance_cash_bank_multiline_journal.py", "现金银行多行日记账审计"),
            _py("audit_finance_counterparty_reports.py", "交易对手报表审计"),
            _py("audit_finance_counterparty_tools.py", "交易对手工具审计"),
            _py("audit_finance_fund_analysis.py", "资金分析审计"),
            _py("audit_finance_kingdee_blueprint_phase1.py", "金蝶蓝图一期审计"),
            _py("audit_finance_period_end_exchange.py", "期末汇率审计"),
        ],
    ))

    # -----------------------------------------------------------------------
    # production: 生产
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="production",
        title="生产模块",
        description="工单、领料、完工入库、报工",
        items=[
            _py("audit_production_module_closure.py", "生产模块闭环审计"),
            _py("audit_production_completion_closure.py", "生产完工闭环审计"),
            _py("audit_production_completion_source.py", "生产完工来源审计"),
            _py("audit_production_execution_closure.py", "生产执行闭环审计"),
            _py("audit_production_pick_return_closure.py", "领料退料闭环审计"),
            _py("audit_production_eight_item_repair.py", "生产八项修复审计"),
            _py("audit_production_screenshot5_scope.py", "生产截图5范围审计"),
            _py("audit_phase4_production_closure.py", "四期生产闭环审计"),
            _py("verify_phase4_production_loop.py", "四期生产循环验证"),
            _py("verify_phase4_integration.py", "四期集成验证"),
            _py("verify_production_completion_closure.py", "生产完工闭环验证"),
        ],
    ))

    # -----------------------------------------------------------------------
    # first_machine: 首机全生命周期闭环
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="first_machine",
        title="首机闭环",
        description="首台机器从销售→BOM→采购→库存→生产→发货→售后→财务的全流程闭环",
        items=[
            _py("audit_first_machine_workflow.py", "首机工作流审计"),
            _py("audit_first_machine_lifecycle_ledger.py", "首机生命周期台账审计"),
            _py("audit_first_machine_procurement.py", "首机采购审计"),
            _py("audit_first_machine_purchase_to_receipt.py", "首机采购到收货审计"),
            _py("audit_first_machine_inventory_execution.py", "首机库存执行审计"),
            _py("audit_first_machine_inventory_trace.py", "首机库存追溯审计"),
            _py("audit_first_machine_work_order_issue.py", "首机工单领料审计"),
            _py("audit_first_machine_quality_closure.py", "首机质量闭环审计"),
            _py("audit_first_machine_subcontract_closure.py", "首机外协闭环审计"),
            _py("audit_first_machine_service_closure.py", "首机售后闭环审计"),
            _py("audit_first_machine_finance_settlement.py", "首机财务结算审计"),
            _py("audit_first_machine_completion_shipment_finance.py", "首机完工发货财务审计"),
            _py("audit_first_machine_period_close_readiness.py", "首机期末关账就绪审计"),
            _py("audit_first_machine_detail_runtime_text.py", "首机详情运行时文本审计"),
        ],
    ))

    # -----------------------------------------------------------------------
    # business: 业务模块（采购/销售/外协/质量/工程）
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="business",
        title="业务模块",
        description="采购、销售、外协、质量、工程 BOM",
        items=[
            _py("audit_purchase_module_boundary.py", "采购模块边界审计"),
            _py("audit_purchase_kingdee_coverage.py", "采购金蝶覆盖审计"),
            _py("audit_purchase_request_detail_blockers.py", "采购申请明细阻塞审计"),
            _py("audit_purchase_request_downpush_readiness.py", "采购申请下推就绪审计"),
            _py("audit_phase3_procurement_closure.py", "三期采购闭环审计"),
            _py("audit_sales_dashboard_boundary.py", "销售仪表盘边界审计"),
            _py("audit_phase2_sales_engineering_bom_kitting.py", "二期销售工程 BOM 配套审计"),
            _py("audit_subcontract_posting_state.py", "外协过账状态审计"),
            _py("audit_subcontract_report_coverage.py", "外协报表覆盖审计"),
            _py("audit_phase5_delivery_outsourcing_service_closure.py", "五期交付外协售后闭环审计"),
            _py("verify_phase5_integration.py", "五期集成验证"),
            _py("verify_phase5_delivery_outsourcing_service_loops.py", "五期交付外协售后循环验证"),
            _py("verify_subcontract_closure.py", "外协闭环验证"),
            _py("verify_service_closure.py", "售后闭环验证"),
            _py("audit_quality_basics_closure.py", "质量基础闭环审计"),
            _py("audit_engineering_bom_routing_readiness.py", "工程 BOM 工艺就绪审计"),
            _py("audit_engineering_drawing_scope.py", "工程图纸范围审计"),
            _py("audit_engineering_runtime_smoke.py", "工程运行时冒烟审计"),
            _py("audit_bom_ecn_scope.py", "BOM ECN 范围审计"),
            _py("audit_mrp_kitting_shortage_closure.py", "MRP 配套缺料闭环审计"),
            _py("audit_after_sale_boundary.py", "售后边界审计"),
            _py("audit_after_sale_service_boundary.py", "售后服务边界审计"),
        ],
    ))

    # -----------------------------------------------------------------------
    # system: 系统与安全
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="system",
        title="系统与安全",
        description="本地安全配置、模块路由、报表性能、状态流转保护、编码规则",
        items=[
            _py("audit_local_security_config.py", "本地安全配置审计"),
            _py("audit_module_root_routes.py", "模块根路由审计"),
            _py("audit_report_performance.py", "报表性能审计"),
            _py("audit_report_print_controls.py", "报表打印控制审计"),
            _py("audit_status_transition_protection.py", "状态流转保护审计"),
            _py("audit_system_document_gaps.py", "系统单据缺口审计"),
            _py("audit_coding_rules.py", "编码规则审计"),
            _py("audit_source_mojibake.py", "源码乱码审计"),
            _py("audit_database_mojibake.py", "数据库乱码审计"),
            _py("audit_fk_validation_readiness.py", "外键校验就绪审计"),
            _py("audit_installer_package.py", "安装包审计"),
            _py("audit_print_template_feature.py", "打印模板功能审计"),
            _py("audit_project_serial_option.py", "项目机号选项审计"),
            _py("audit_project_machine_cost_boundary.py", "项目机号成本边界审计"),
            _py("audit_master_data_completion_scope.py", "主数据完整性范围审计"),
            _py("audit_material_opening_boundary.py", "物料期初边界审计"),
            _py("audit_product_configuration_boundary.py", "产品配置边界审计"),
            _py("audit_document_material_name_entry.py", "单据物料名称录入审计"),
            _py("audit_order_edit_execution_quantities.py", "订单编辑执行数量审计"),
            _py("audit_rectification_closure.py", "整改闭环审计"),
            _py("audit_tonight_fix_patterns.py", "今夜修复模式审计"),
            _py("audit_screenshot11_main_scope.py", "截图11主范围审计"),
            _py("audit_homepage_bug_candidates.py", "首页 BUG 候选审计"),
            _py("validate_core_fk_constraints.py", "核心外键约束验证"),
            _py("validate_first_machine_template.py", "首机模板验证"),
            _py("validate_trial_issue_log.py", "试点问题日志验证"),
            _py("verify_project_serial_traceability.py", "项目机号追溯验证"),
            _py("verify_filter_removed.py", "过滤器移除验证"),
            _py("verify_agent_f_production_inventory_closure.py", "生产库存闭环验证"),
        ],
    ))

    # -----------------------------------------------------------------------
    # e2e: 端到端测试
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="e2e",
        title="端到端测试",
        description="按业务流程顺序执行的端到端测试（主数据→采购→销售→生产→库存）",
        items=[
            _py("_e2e_step1_master_data.py", "端到端步骤1：主数据"),
            _py("_e2e_step1_1_crud.py", "端到端步骤1.1：CRUD"),
            _py("_e2e_step2_purchase.py", "端到端步骤2：采购"),
            _py("_e2e_step2b_purchase.py", "端到端步骤2b：采购"),
            _py("_e2e_step2c_purchase.py", "端到端步骤2c：采购"),
            _py("_e2e_step2d_purchase.py", "端到端步骤2d：采购"),
            _py("_e2e_step2e_purchase.py", "端到端步骤2e：采购"),
            _py("_e2e_step2f_purchase.py", "端到端步骤2f：采购"),
            _py("_e2e_step2g_purchase.py", "端到端步骤2g：采购"),
            _py("_e2e_step2h_purchase.py", "端到端步骤2h：采购"),
            _py("_e2e_step2i_invoice.py", "端到端步骤2i：发票"),
            _py("_e2e_step2j_payment.py", "端到端步骤2j：付款"),
            _py("_e2e_step3_sales.py", "端到端步骤3：销售"),
            _py("_e2e_step4_production.py", "端到端步骤4：生产"),
            _py("_e2e_step5_inventory.py", "端到端步骤5：库存"),
        ],
    ))

    # -----------------------------------------------------------------------
    # full: 综合大测试
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="full",
        title="综合测试",
        description="全系统综合测试：完整审计、BUG 猎手、前端审计、操作员模拟、人工验收",
        items=[
            _py("run_full_erp_audit.py", "完整 ERP 审计", timeout=600),
            _py("erp_bug_hunter.py", "ERP BUG 猎手", timeout=600),
            _py("erp_frontend_bug_audit.py", "前端 BUG 审计", timeout=600),
            _py("run_homepage_bug_audit.py", "首页 BUG 审计", timeout=600),
            _py("audit_full_system_operator_simulation.py", "全系统操作员模拟", timeout=600),
            _py("menu_browser_audit.py", "菜单浏览器审计", timeout=600),
            _py("browser_full_human_acceptance.py", "浏览器全人工验收", timeout=600),
            _py("p0_acceptance_test.py", "P0 验收测试", timeout=600),
            _py("trial_run_go_no_go.py", "试点 Go/No-Go 评估", timeout=600),
        ],
    ))

    # -----------------------------------------------------------------------
    # static: 静态代码分析（方案 B 新增）
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="static",
        title="静态代码分析",
        description="ruff 代码规范检查 + bandit 安全漏洞扫描（无需运行代码即可发现 BUG）",
        items=[
            _ruff(["app.py"], "ruff 检查 app.py"),
            _ruff(["routes"], "ruff 检查 routes/"),
            _ruff(["services"], "ruff 检查 services/"),
            _ruff(["scripts"], "ruff 检查 scripts/"),
            _bandit(["app.py"], "bandit 安全扫描 app.py"),
            _bandit(["routes"], "bandit 安全扫描 routes/"),
            _bandit(["services"], "bandit 安全扫描 services/"),
        ],
    ))

    # -----------------------------------------------------------------------
    # ui: Playwright UI 自动化测试（方案 C 新增）
    # -----------------------------------------------------------------------
    groups.append(TestGroup(
        key="ui",
        title="UI 自动化测试",
        description="Playwright 浏览器自动化：7 个 pilot 角色登录、菜单遍历、表单检查、截图",
        items=[
            TestItem(
                name="ui_test_playwright.py",
                command=[PYTHON, str(SCRIPTS_DIR / "ui_test_playwright.py")],
                description="Playwright UI 测试（7 个角色，菜单遍历，表单检查，截图）",
                timeout=600,
            ),
        ],
    ))

    return groups


# ---------------------------------------------------------------------------
# 运行器
# ---------------------------------------------------------------------------
@dataclass
class TestResult:
    """单个测试运行结果。"""

    item: TestItem
    group_key: str
    passed: bool
    skipped: bool = False
    duration: float = 0.0
    exit_code: int = 0
    output_tail: str = ""  # 最后若干行输出（用于失败诊断）
    error: str = ""


def _prepare_env() -> dict[str, str]:
    """合并默认环境变量与当前进程环境变量（当前进程优先）。"""
    env = os.environ.copy()
    for key, value in DEFAULT_ENV.items():
        if key not in env or not env[key]:
            env[key] = value
    return env


def run_item(item: TestItem, group_key: str, verbose: bool = False) -> TestResult:
    """运行单个测试项。"""
    start = time.time()
    env = _prepare_env()

    if verbose:
        print(f"  >>> 运行: {item.label}")
        sys.stdout.flush()

    try:
        proc = subprocess.run(
            item.command,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=item.timeout,
            encoding="utf-8",
            errors="replace",
        )
        duration = time.time() - start
        passed = proc.returncode == 0
        output = (proc.stdout or "") + (proc.stderr or "")
        tail = "\n".join(output.splitlines()[-15:]) if output else ""

        if verbose and output:
            # 详细模式打印全部输出
            print(output)
        elif not passed:
            # 非详细模式只打印失败的最后 15 行
            if tail:
                print(f"  --- 输出末尾 ---")
                for line in tail.splitlines():
                    print(f"  {line}")

        return TestResult(
            item=item,
            group_key=group_key,
            passed=passed,
            duration=duration,
            exit_code=proc.returncode,
            output_tail=tail,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        print(f"  !!! 超时（{item.timeout}s）")
        return TestResult(
            item=item,
            group_key=group_key,
            passed=False,
            duration=duration,
            error=f"超时（{item.timeout}s）",
        )
    except FileNotFoundError as exc:
        duration = time.time() - start
        print(f"  !!! 文件不存在: {exc}")
        return TestResult(
            item=item,
            group_key=group_key,
            passed=False,
            duration=duration,
            error=str(exc),
        )
    except Exception as exc:
        duration = time.time() - start
        print(f"  !!! 异常: {exc}")
        return TestResult(
            item=item,
            group_key=group_key,
            passed=False,
            duration=duration,
            error=str(exc),
        )


def run_groups(groups: list[TestGroup], verbose: bool = False) -> list[TestResult]:
    """按顺序运行多个分组。"""
    results: list[TestResult] = []
    total = sum(len(g.items) for g in groups)

    print(f"\n{'=' * 70}")
    print(f"ERP 测试运行器 - 共 {len(groups)} 组 {total} 项测试")
    print(f"{'=' * 70}\n")

    idx = 0
    for group in groups:
        print(f"\n{'─' * 70}")
        print(f"[{group.key}] {group.title}（{len(group.items)} 项）")
        print(f"  {group.description}")
        print(f"{'─' * 70}")

        for item in group.items:
            idx += 1
            prefix = f"[{idx}/{total}]"
            print(f"\n{prefix} {item.label}")
            if item.description:
                print(f"  {item.description}")

            result = run_item(item, group.key, verbose=verbose)
            results.append(result)

            status = "PASS" if result.passed else "FAIL"
            marker = "✓" if result.passed else "✗"
            print(f"  {marker} {status}（{result.duration:.1f}s）")

    return results


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------
def print_summary(results: list[TestResult], groups: list[TestGroup]) -> None:
    """打印汇总报告。"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    duration = sum(r.duration for r in results)

    print(f"\n{'=' * 70}")
    print(f"测试汇总")
    print(f"{'=' * 70}")
    print(f"  总数: {total}    通过: {passed}    失败: {failed}    跳过: {skipped}")
    print(f"  总耗时: {duration:.1f}s")
    print()

    # 按分组汇总
    print(f"{'分组':<20} {'总数':>6} {'通过':>6} {'失败':>6} {'耗时':>8}")
    print(f"{'─' * 50}")
    for group in groups:
        group_results = [r for r in results if r.group_key == group.key]
        if not group_results:
            continue
        g_total = len(group_results)
        g_passed = sum(1 for r in group_results if r.passed)
        g_failed = sum(1 for r in group_results if not r.passed)
        g_duration = sum(r.duration for r in group_results)
        print(f"{group.key:<20} {g_total:>6} {g_passed:>6} {g_failed:>6} {g_duration:>7.1f}s")

    # 失败项明细
    failures = [r for r in results if not r.passed]
    if failures:
        print(f"\n{'─' * 70}")
        print(f"失败项明细（{len(failures)} 项）")
        print(f"{'─' * 70}")
        for r in failures:
            print(f"\n✗ [{r.group_key}] {r.item.label}")
            if r.error:
                print(f"  错误: {r.error}")
            if r.output_tail:
                for line in r.output_tail.splitlines()[-5:]:
                    print(f"  {line}")

    print(f"\n{'=' * 70}")
    if failed == 0:
        print(f"结果: 全部通过 ✓")
    else:
        print(f"结果: {failed} 项失败 ✗")
    print(f"{'=' * 70}\n")


def write_markdown_report(results: list[TestResult], groups: list[TestGroup], output_path: Path) -> None:
    """生成 Markdown 报告。"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    duration = sum(r.duration for r in results)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# ERP 测试报告",
        f"",
        f"- 生成时间: {now}",
        f"- 总数: {total}",
        f"- 通过: {passed}",
        f"- 失败: {failed}",
        f"- 总耗时: {duration:.1f}s",
        f"",
        f"## 分组汇总",
        f"",
        f"| 分组 | 总数 | 通过 | 失败 | 耗时 |",
        f"|------|------|------|------|------|",
    ]

    for group in groups:
        group_results = [r for r in results if r.group_key == group.key]
        if not group_results:
            continue
        g_total = len(group_results)
        g_passed = sum(1 for r in group_results if r.passed)
        g_failed = sum(1 for r in group_results if not r.passed)
        g_duration = sum(r.duration for r in group_results)
        lines.append(f"| {group.key} | {g_total} | {g_passed} | {g_failed} | {g_duration:.1f}s |")

    lines.extend([
        f"",
        f"## 详细结果",
        f"",
        f"| 分组 | 测试 | 状态 | 耗时 |",
        f"|------|------|------|------|",
    ])
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"| {r.group_key} | {r.item.label} | {status} | {r.duration:.1f}s |")

    failures = [r for r in results if not r.passed]
    if failures:
        lines.extend([f"", f"## 失败项明细", f""])
        for r in failures:
            lines.append(f"### ✗ [{r.group_key}] {r.item.label}")
            if r.error:
                lines.append(f"- 错误: {r.error}")
            if r.output_tail:
                lines.append(f"- 输出末尾:")
                lines.append(f"```")
                lines.extend(r.output_tail.splitlines()[-10:])
                lines.append(f"```")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Markdown 报告已生成: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def list_groups(groups: list[TestGroup]) -> None:
    """列出所有可用测试分组。"""
    print(f"\n可用测试分组:\n")
    for group in groups:
        print(f"  {group.key:<15} {group.title}（{len(group.items)} 项）")
        print(f"                  {group.description}")
    print(f"\n  {'all':<15} 全部测试（{sum(len(g.items) for g in groups)} 项）")
    print()


def parse_groups(group_arg: str, groups: list[TestGroup]) -> list[TestGroup]:
    """解析 --group 参数。"""
    if group_arg == "all":
        return groups

    keys = [k.strip() for k in group_arg.split(",") if k.strip()]
    group_map = {g.key: g for g in groups}
    selected: list[TestGroup] = []
    for key in keys:
        if key not in group_map:
            print(f"错误: 未知分组 '{key}'，可用分组: {', '.join(g.key for g in groups)}")
            sys.exit(2)
        selected.append(group_map[key])
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ERP 综合测试运行器 - 一键运行所有审计脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--group",
        default="core",
        help="测试分组（core/permissions/inventory/finance/production/first_machine/business/system/e2e/full/all），多个用逗号分隔，默认 core",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用测试分组",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示每个测试的完整输出",
    )
    parser.add_argument(
        "--report",
        choices=["text", "md"],
        default="text",
        help="报告格式：text（默认，控制台输出）或 md（生成 Markdown 文件）",
    )
    parser.add_argument(
        "--report-path",
        default="logs/erp_test_report.md",
        help="Markdown 报告输出路径（默认 logs/erp_test_report.md）",
    )

    args = parser.parse_args()
    groups = build_groups()

    if args.list:
        list_groups(groups)
        return 0

    selected = parse_groups(args.group, groups)
    results = run_groups(selected, verbose=args.verbose)
    print_summary(results, selected)

    if args.report == "md":
        report_path = ROOT / args.report_path
        write_markdown_report(results, selected, report_path)

    failed = sum(1 for r in results if not r.passed)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
