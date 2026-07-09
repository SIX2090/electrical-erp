"""System management routes: backup, update, security config, and admin settings."""
import os
import re
from datetime import datetime
from pathlib import Path

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from services.env_config import security_config_status
from services.update_service import get_update_status, launch_update
from scripts.pg_backup import run_backup


def _bool_value(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "启用"}


def _env_default(key, default=""):
    return os.environ.get(key, default)


def _setting(key, label, remark, value="", setting_type="text", **extra):
    item = {
        "key": key,
        "label": label,
        "remark": remark,
        "value": value,
        "type": setting_type,
    }
    item.update(extra)
    if setting_type == "bool":
        item["checked"] = _bool_value(value)
    if setting_type == "secret":
        item["has_value"] = bool(value)
        item["value"] = ""
    return item


def _get_system_option(query_one, key, default=""):
    try:
        row = query_one("SELECT option_value FROM system_options WHERE option_key=%s", (key,))
    except Exception:
        try:
            row = query_one("SELECT value AS option_value FROM system_options WHERE key=%s", (key,))
        except Exception:
            return default
    return (row or {}).get("option_value") or default


def _save_system_option(execute_db, query_one, key, value, remark):
    execute_db(
        """
        UPDATE system_options
        SET key=COALESCE(key, %s), value=%s, option_value=%s, remark=%s, updated_at=NOW()
        WHERE option_key=%s
        """,
        (key, value, value, remark, key),
    )
    if not query_one("SELECT id FROM system_options WHERE option_key=%s LIMIT 1", (key,)):
        execute_db(
            """
            INSERT INTO system_options (key, value, option_key, option_value, remark, updated_at)
            VALUES (%s,%s,%s,%s,%s,NOW())
            """,
            (key, value, key, value, remark),
        )
    execute_db(
        """
        UPDATE system_options
        SET key=COALESCE(key, option_key), value=option_value
        WHERE option_key=%s
        """,
        (key,),
    )


def _validate_period_value(value, label):
    value = (value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError(f"{label}必须使用 YYYY-MM 格式")
    datetime.strptime(value + "-01", "%Y-%m-%d")
    return value


def _validate_date_value(value, label, required=True):
    value = (value or "").strip()
    if not value and not required:
        return ""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD 格式") from exc
    return value


def _opening_period_view_model(query_one):
    current_period = datetime.now().strftime("%Y-%m")
    return {
        "system_start_period": _get_system_option(query_one, "system_start_period", current_period),
        "system_period_start_date": _get_system_option(query_one, "system_period_start_date", f"{current_period}-01"),
        "system_period_end_date": _get_system_option(query_one, "system_period_end_date", ""),
        "finance_start_period": _get_system_option(query_one, "finance_start_period", current_period),
        "finance_current_period": _get_system_option(query_one, "finance_current_period", current_period),
        "period_control_enabled": _bool_value(_get_system_option(query_one, "period_control_enabled", "1")),
        "opening_lock_date": _get_system_option(query_one, "opening_lock_date", ""),
        "opening_data_locked": _bool_value(_get_system_option(query_one, "opening_data_locked", "0")),
    }


def system_parameter_effect_rows():
    return [
        {
            "area": "导航与试运行",
            "keys": "nav_mode, hide_unstable_modules",
            "effect": "控制普通菜单范围和未稳定模块是否进入导航。",
            "owner": "系统管理员",
            "acceptance": "用试运行用户检查菜单可见性和直接访问矩阵。",
        },
        {
            "area": "项目/机号追踪",
            "keys": "require_project_serial, batch_serial_control",
            "effect": "控制项目号、机号作为推荐追踪字段或强制校验字段的行为。",
            "owner": "系统管理员/生产计划",
            "acceptance": "检查销售、采购、库存、生产、售后页面的项目号和机号提示。",
        },
        {
            "area": "库存与成本",
            "keys": "negative_stock_block, allow_negative_stock, cost_method",
            "effect": "影响库存出入库校验、负库存风险和库存金额口径。",
            "owner": "仓库/财务",
            "acceptance": "执行库存一致性审计并抽查出库、领料、委外发料。",
        },
        {
            "area": "采购与委外",
            "keys": "purchase_receipt_requires_order, subcontract_issue_requires_order",
            "effect": "控制采购入库、委外发料和委外收回是否必须关联来源单据。",
            "owner": "采购/仓库",
            "acceptance": "按采购申请到采购入库、委外订单到收回闭环验收。",
        },
        {
            "area": "销售与应收",
            "keys": "sales_shipment_requires_order, receivable_confirm_on_shipment",
            "effect": "控制销售发货来源和应收生成口径。",
            "owner": "销售/财务",
            "acceptance": "按销售订单到发货到应收闭环验收。",
        },
        {
            "area": "生产与售后",
            "keys": "work_order_requires_bom, service_requires_machine_serial",
            "effect": "控制工单来源 BOM、服务单机号追踪和成本归集提示。",
            "owner": "生产/售后",
            "acceptance": "按工单领料完工、服务卡到服务单闭环验收。",
        },
        {
            "area": "财务与结账",
            "keys": "ar_ap_auto_from_documents, period_close_requires_backup",
            "effect": "控制应收应付生成和期间关闭前备份检查口径。",
            "owner": "财务/系统管理员",
            "acceptance": "复核期间关闭前最近备份和 AR/AP 对账结果。",
        },
        {
            "area": "系统审计",
            "keys": "operation_log_retention_days",
            "effect": "控制操作日志无关键字清理时保留最近多少天的日志。",
            "owner": "系统管理员",
            "acceptance": "无关键字清理只删除保留期之前的日志。",
        },
        {
            "area": "AI 助手",
            "keys": "ai_enabled, ai_model, ai_api_key",
            "effect": "只控制助手入口和服务端调用参数，不参与单据审核、过账或报表生成。",
            "owner": "系统管理员",
            "acceptance": "关闭后不显示助手入口；参数测试不改变业务数据。",
        },
    ]


def latest_restore_status(root_dir):
    log_path = Path(root_dir) / "backups" / "backup_log.txt"
    if not log_path.exists():
        return {
            "status": "未演练",
            "detail": "尚未发现恢复演练日志。上线前需在受控目标库执行 scripts/pg_restore.py。",
            "checked_at": "-",
        }
    latest = None
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "RESTORE_" in line:
            latest = line.strip()
    if not latest:
        return {
            "status": "未演练",
            "detail": "备份日志存在，但未发现 RESTORE_OK/RESTORE_FAIL 记录。",
            "checked_at": "-",
        }
    checked_at = latest[:19] if len(latest) >= 19 else "-"
    if "RESTORE_OK" in latest:
        status = "已通过"
    elif "RESTORE_FAIL" in latest:
        status = "失败"
    elif "RESTORE_CANCELLED" in latest:
        status = "已取消"
    else:
        status = "待确认"
    return {"status": status, "detail": latest, "checked_at": checked_at}


def build_setting_groups(query_one=None):
    def option_value(key, default=""):
        if not query_one:
            return default
        try:
            row = query_one("SELECT option_value FROM system_options WHERE option_key=%s", (key,))
        except Exception:
            try:
                row = query_one("SELECT value AS option_value FROM system_options WHERE key=%s", (key,))
            except Exception:
                return default
        return (row or {}).get("option_value") or default

    return [
        {
            "key": "public_parameters",
            "title": "公共参数",
            "icon": "bi-building-gear",
            "description": "维护系统启用期间、本位币和企业基础信息。",
            "settings": [
                _setting("system_start_period", "系统启用期间", "系统上线启用的会计期间，例如 2025年01期。", option_value("system_start_period", "2025年01期")),
                _setting("system_period_start_date", "开始日期", "启用期间的开始日期。", option_value("system_period_start_date", "2025-01-01")),
                _setting("system_period_end_date", "结束日期", "启用期间的结束日期。", option_value("system_period_end_date", "2025-01-31")),
                _setting("base_currency", "本位币", "财务、库存成本、应收应付和报表默认使用的本位币。", option_value("base_currency", "CNY"), "select", options=[
                    {"value": "CNY", "label": "人民币"},
                    {"value": "USD", "label": "美元"},
                    {"value": "EUR", "label": "欧元"},
                ]),
                _setting("company_name", "公司名称", "单据打印、开票资料、报表抬头使用的企业名称。", option_value("company_name", "通用行业（旗舰版）"), wide=True),
                _setting("company_address", "公司地址", "企业通讯地址，用于打印和开票资料。", option_value("company_address", ""), wide=True),
                _setting("company_phone", "公司电话", "企业联系电话。", option_value("company_phone", "")),
                _setting("company_fax", "公司传真", "企业传真号码。", option_value("company_fax", "")),
                _setting("company_postcode", "公司邮编", "企业邮政编码。", option_value("company_postcode", "")),
            ],
        },
        {
            "key": "basic_master_parameters",
            "title": "基础资料参数",
            "icon": "bi-archive",
            "description": "维护物料、客户、供应商、仓库等基础资料的编码和停用控制。",
            "settings": [
                _setting("master_code_unique_check", "基础资料编码唯一检查", "启用后物料、客户、供应商、仓库等编码不允许重复。", option_value("master_code_unique_check", "1"), "bool"),
                _setting("master_name_duplicate_warning", "基础资料名称重复提醒", "启用后新增同名资料时提示操作员复核。", option_value("master_name_duplicate_warning", "1"), "bool"),
                _setting("disabled_master_block_document", "停用资料禁止制单", "启用后停用的物料、客户、供应商、仓库不允许被新单据引用。", option_value("disabled_master_block_document", "1"), "bool"),
                _setting("material_name_search_only", "单据按物料名称选料", "启用后单据明细通过物料名称搜索选择，隐藏单独可编辑物料选择列。", option_value("material_name_search_only", "1"), "bool"),
                _setting("require_material_specification", "物料规格型号建议维护", "保存物料时提示维护规格型号，便于采购、库存和生产识别。", option_value("require_material_specification", "1"), "bool"),
            ],
        },
        {
            "key": "purchase_sales_inventory_parameters",
            "title": "进销存参数",
            "icon": "bi-boxes",
            "description": "维护采购、销售、库存流转的来源单、税率、超量和价格控制。",
            "settings": [
                _setting("default_business_tax_rate", "默认业务税率", "采购、销售和委外业务未指定税率时使用的默认税率。", option_value("default_business_tax_rate", "13"), "int", min=0, max=99, unit="%"),
                _setting("pis_purchase_receipt_requires_order", "采购入库要求来源订单", "开启后采购入库必须关联采购订单。", option_value("pis_purchase_receipt_requires_order", option_value("purchase_receipt_requires_order", "1")), "bool"),
                _setting("pis_sales_shipment_requires_order", "销售发货要求来源订单", "开启后销售发货必须关联销售订单。", option_value("pis_sales_shipment_requires_order", option_value("sales_shipment_requires_order", "1")), "bool"),
                _setting("business_default_tax_included", "业务单价默认含税", "启用后采购、销售、委外单价默认按含税价解释。", option_value("business_default_tax_included", option_value("default_tax_included", "1")), "bool"),
                _setting("business_allow_self_audit", "允许制单人审核本人业务单据", "小公司人员较少时可启用；关闭后采购订单制单人不能审核本人单据。", option_value("business_allow_self_audit", "1"), "bool"),
                _setting("over_delivery_policy", "超订单出入库控制", "控制超过订单未执行数量时的处理方式。", option_value("over_delivery_policy", "warn"), "select", options=[
                    {"value": "block", "label": "禁止"},
                    {"value": "warn", "label": "提示"},
                    {"value": "allow", "label": "允许"},
                ]),
            ],
        },
        {
            "key": "inventory_cost_parameters",
            "title": "存货核算参数",
            "icon": "bi-calculator",
            "description": "维护库存成本、负库存、批号库位和期末核算规则。",
            "settings": [
                _setting("inventory_cost_method", "存货计价方法", "库存金额默认使用的成本核算方法。", option_value("inventory_cost_method", option_value("cost_method", "weighted_average")), "select", options=[
                    {"value": "weighted_average", "label": "移动加权"},
                    {"value": "monthly_weighted", "label": "月末一次加权"},
                    {"value": "manual", "label": "手工成本"},
                ]),
                _setting("cost_negative_stock_block", "禁止负库存", "启用后出库、领料、委外发料必须先校验可用库存。", option_value("cost_negative_stock_block", option_value("negative_stock_block", "1")), "bool"),
                _setting("cost_warehouse_location_required", "启用库位管理", "启用后库存单据需要维护仓库和库位。", option_value("cost_warehouse_location_required", option_value("warehouse_location_required", "1")), "bool"),
                _setting("cost_inventory_batch_required", "启用批号管理", "启用后入库、出库、调拨和盘点维护批号。", option_value("cost_inventory_batch_required", option_value("inventory_batch_required", "0")), "bool"),
                _setting("cost_period_close_inventory_check", "结账前库存核算检查", "期间结账前检查负库存、未核成本和待过账库存单据。", option_value("cost_period_close_inventory_check", option_value("period_close_inventory_check", "1")), "bool"),
            ],
        },
        {
            "key": "ar_ap_parameters",
            "title": "应收应付参数",
            "icon": "bi-receipt-cutoff",
            "description": "维护应收、应付、核销、发票匹配和账龄控制。",
            "settings": [
                _setting("arap_auto_from_documents", "业务单据自动生成应收应付", "启用后销售发货、采购入库、委外收回按规则生成往来待结算数据。", option_value("arap_auto_from_documents", option_value("ar_ap_auto_from_documents", "1")), "bool"),
                _setting("arap_receivable_confirm_on_shipment", "销售发货生成应收", "启用后销售发货审核后生成应收待结算数据。", option_value("arap_receivable_confirm_on_shipment", option_value("receivable_confirm_on_shipment", "1")), "bool"),
                _setting("arap_purchase_invoice_match_required", "应付要求三单匹配", "启用后采购应付需要匹配订单、入库和发票。", option_value("arap_purchase_invoice_match_required", option_value("purchase_invoice_match_required", "1")), "bool"),
                _setting("manual_settlement_required", "收付款要求手工核销", "启用后收款单、付款单需要录入本次核销金额。", option_value("manual_settlement_required", "1"), "bool"),
                _setting("aging_warning_days", "账龄预警天数", "超过该天数未核销的应收应付进入预警。", option_value("aging_warning_days", "30"), "int", min=1, max=365),
            ],
        },
        {
            "key": "finance_parameters_full",
            "title": "财务参数",
            "icon": "bi-journal-check",
            "description": "维护财务启用期间、会计制度、凭证、账簿报表和期末处理控制。",
            "settings": [
                _setting("finance_start_period", "启用期间", "财务模块启用的首个会计期间。", option_value("finance_start_period", option_value("system_start_period", "2025年01期"))),
                _setting("finance_current_period", "当前期间", "财务当前打开的会计期间。", option_value("finance_current_period", option_value("system_start_period", "2025年01期"))),
                _setting("accounting_standard", "会计制度", "账簿、科目和报表使用的会计制度口径。", option_value("accounting_standard", "小企业会计准则(2013年颁)"), "select", options=[
                    {"value": "小企业会计准则(2013年颁)", "label": "小企业会计准则(2013年颁)"},
                    {"value": "企业会计准则", "label": "企业会计准则"},
                    {"value": "民间非营利组织会计制度", "label": "民间非营利组织会计制度"},
                ]),
                _setting("voucher_cash_bank_negative_check", "现金、银行类科目赤字检查", "凭证保存或过账时检查现金、银行科目余额是否透支。", option_value("voucher_cash_bank_negative_check", "1"), "bool"),
                _setting("voucher_aux_by_category", "录凭证科目辅助核算显示类别", "启用后凭证分录按科目辅助核算类别显示录入项。", option_value("voucher_aux_by_category", "0"), "bool"),
                _setting("voucher_product_spec_in_aux", "科目辅助核算商品显示规格型号", "启用后商品类辅助核算显示规格型号。", option_value("voucher_product_spec_in_aux", "0"), "bool"),
                _setting("voucher_hide_modifier", "录凭证界面不显示修改人", "启用后凭证录入界面隐藏修改人字段。", option_value("voucher_hide_modifier", "0"), "bool"),
                _setting("voucher_auto_fill_number", "自动填补凭证断号", "启用后新增凭证优先使用当前期间断号。", option_value("voucher_auto_fill_number", "0"), "bool"),
                _setting("voucher_block_business_generated_edit", "不允许修改业务系统生成凭证", "启用后业务来源凭证不能被手工修改。", option_value("voucher_block_business_generated_edit", "0"), "bool"),
                _setting("voucher_block_business_generated_delete", "不允许删除业务系统生成凭证", "启用后业务来源凭证不能被手工删除。", option_value("voucher_block_business_generated_delete", "0"), "bool"),
                _setting("voucher_block_other_user_edit_delete", "不允许修改/删除别人录入的凭证", "启用后凭证录入人以外的用户不能修改或删除。", option_value("voucher_block_other_user_edit_delete", "1"), "bool"),
                _setting("voucher_auditor_not_creator", "凭证审核与制单不能为同一人", "启用后凭证制单人不能审核本人凭证。", option_value("voucher_auditor_not_creator", "0"), "bool"),
                _setting("voucher_auditor_not_reviewer", "凭证审核与复核不能为同一人", "启用后凭证审核人不能同时作为复核人。", option_value("voucher_auditor_not_reviewer", "0"), "bool"),
                _setting("voucher_review_reverse_not_same", "凭证审核与反审核必须为同一人", "启用后只有原审核人可反审核凭证。", option_value("voucher_review_reverse_not_same", "0"), "bool"),
                _setting("voucher_amount_quantity_price_warning", "录凭证数量*单价不等于金额时提示", "启用后凭证明细数量、单价、金额不一致时提示。", option_value("voucher_amount_quantity_price_warning", "1"), "bool"),
                _setting("voucher_attachment_lock_after_audit", "凭证审核后不允许再上传/删除附件", "启用后已审核凭证附件进入锁定状态。", option_value("voucher_attachment_lock_after_audit", "0"), "bool"),
                _setting("voucher_attachment_lock_after_close", "财务结账后凭证不允许上传/删除附件", "启用后已结账期间凭证附件进入锁定状态。", option_value("voucher_attachment_lock_after_close", "0"), "bool"),
                _setting("cash_flow_required_mode", "凭证保存现金流量提醒", "控制现金流量项目的提醒范围。", option_value("cash_flow_required_mode", "cash_bank_direction"), "select", options=[
                    {"value": "all", "label": "所有凭证提醒"},
                    {"value": "cash_bank_unbalanced", "label": "仅现金流量不平衡时提醒"},
                    {"value": "cash_bank_direction", "label": "仅现金银行科目所在方向为多借或多贷时提醒"},
                    {"value": "none", "label": "不提醒"},
                ]),
                _setting("ledger_balance_direction_match_account", "账簿余额方向与科目方向一致", "启用后账簿余额方向按科目余额方向显示。", option_value("ledger_balance_direction_match_account", "0"), "bool"),
                _setting("ledger_first_line_summary", "明细账取凭证第一行分录摘要", "启用后明细账默认取凭证第一行分录摘要。", option_value("ledger_first_line_summary", "0"), "bool"),
                _setting("cash_flow_supplement_enabled", "启用现金流量表补充资料", "启用后现金流量表显示补充资料维护入口。", option_value("cash_flow_supplement_enabled", "0"), "bool"),
                _setting("period_close_requires_voucher_audit", "凭证必须审核才能结账", "启用后存在未审核凭证时不允许期间结账。", option_value("period_close_requires_voucher_audit", "0"), "bool"),
                _setting("period_close_block_voucher_gap", "凭证断号不允许结账", "启用后当前期间存在凭证断号时不允许结账。", option_value("period_close_block_voucher_gap", "1"), "bool"),
                _setting("period_close_monthly_pl_transfer", "期末结账前必须结转损益", "启用后未生成期末损益结转凭证时不允许结账。", option_value("period_close_monthly_pl_transfer", "0"), "bool"),
                _setting("period_close_yearly_pl_transfer", "年结前必须结转损益", "启用后年度结账前必须完成损益结转。", option_value("period_close_yearly_pl_transfer", "0"), "bool"),
                _setting("period_close_auto_pl_transfer", "结账时自动结转损益", "启用后结账动作可触发损益结转流程。", option_value("period_close_auto_pl_transfer", "0"), "bool"),
                _setting("period_close_no_reverse", "不允许反结账", "启用后普通用户不能执行反结账。", option_value("period_close_no_reverse", "0"), "bool"),
            ],
        },
        {
            "key": "cashier_parameters",
            "title": "出纳参数",
            "icon": "bi-bank",
            "description": "维护现金银行、收付款和资金流水控制。",
            "settings": [
                _setting("cashier_bank_account_required", "收付款必须选择银行账户", "启用后收款单、付款单必须维护现金或银行账户。", option_value("cashier_bank_account_required", "1"), "bool"),
                _setting("cashier_journal_auto_from_receipt_payment", "收付款自动生成资金流水", "启用后收款单、付款单审核后自动写入现金银行流水。", option_value("cashier_journal_auto_from_receipt_payment", "1"), "bool"),
                _setting("cashier_reconcile_required_before_close", "结账前要求资金对账", "启用后期间结账前检查现金银行流水与收付款是否一致。", option_value("cashier_reconcile_required_before_close", "1"), "bool"),
                _setting("cashier_attachment_required", "收付款附件提醒", "启用后收付款保存时提醒上传银行回单、票据或对账依据。", option_value("cashier_attachment_required", "0"), "bool"),
            ],
        },
        {
            "key": "asset_parameters",
            "title": "资产参数",
            "icon": "bi-pc-display",
            "description": "维护固定资产启用和折旧口径；核心稳定前默认不开放资产月结。",
            "settings": [
                _setting("fixed_asset_enabled", "启用固定资产", "启用后显示固定资产基础资料和折旧参数。", option_value("fixed_asset_enabled", "0"), "bool"),
                _setting("fixed_asset_depreciation_method", "默认折旧方法", "固定资产新增时默认使用的折旧方法。", option_value("fixed_asset_depreciation_method", "straight_line"), "select", options=[
                    {"value": "straight_line", "label": "平均年限法"},
                    {"value": "workload", "label": "工作量法"},
                ]),
                _setting("fixed_asset_close_required", "财务结账前要求资产月结", "启用后财务期间结账前检查资产月结状态。", option_value("fixed_asset_close_required", "0"), "bool"),
            ],
        },
        {
            "key": "tax_parameters",
            "title": "税务参数",
            "icon": "bi-file-earmark-ruled",
            "description": "维护开票信息、默认税率和税务资料。",
            "settings": [
                _setting("taxpayer_name", "纳税人名称", "发票抬头和税务资料使用的纳税人名称。", option_value("taxpayer_name", "-"), wide=True),
                _setting("taxpayer_id_no", "纳税人识别号", "统一社会信用代码或纳税人识别号。", option_value("taxpayer_id_no", "-")),
                _setting("tax_company_address", "公司地址", "开票资料中的公司地址。", option_value("tax_company_address", "-"), wide=True),
                _setting("tax_company_phone", "公司电话", "开票资料中的公司电话。", option_value("tax_company_phone", "-")),
                _setting("tax_bank_name", "开户银行", "开票资料中的开户银行。", option_value("tax_bank_name", "-")),
                _setting("tax_bank_account", "银行账号", "开票资料中的银行账号。", option_value("tax_bank_account", "-")),
                _setting("default_output_tax_rate", "默认销项税率", "销售发票未指定税率时使用的销项税率。", option_value("default_output_tax_rate", "13"), "int", min=0, max=99, unit="%"),
                _setting("default_input_tax_rate", "默认进项税率", "采购发票未指定税率时使用的进项税率。", option_value("default_input_tax_rate", "13"), "int", min=0, max=99, unit="%"),
            ],
        },
        {
            "key": "customer_operation_parameters",
            "title": "客户经营参数",
            "icon": "bi-people",
            "description": "维护客户信用、账期、价格等级和经营分析口径。",
            "settings": [
                _setting("customer_sales_credit_limit_check", "启用客户信用检查", "保存或审核销售订单时提示客户信用额度、逾期应收和未结发货风险。", option_value("customer_sales_credit_limit_check", option_value("sales_credit_limit_check", "0")), "bool"),
                _setting("default_customer_payment_days", "默认客户账期天数", "新客户未指定账期时使用的默认账期。", option_value("default_customer_payment_days", "30"), "int", min=0, max=365),
                _setting("customer_price_level_enabled", "启用客户价格等级", "启用后销售价格可按客户价格等级取价。", option_value("customer_price_level_enabled", "1"), "bool"),
                _setting("customer_profit_report_basis", "客户毛利报表口径", "客户经营报表默认使用的金额口径。", option_value("customer_profit_report_basis", "tax_included"), "select", options=[
                    {"value": "tax_included", "label": "含税金额"},
                    {"value": "untaxed", "label": "未税金额"},
                ]),
            ],
        },
        {
            "key": "international_parameters",
            "title": "国际化参数",
            "icon": "bi-globe2",
            "description": "维护币种、汇率、语言和境外业务默认口径。",
            "settings": [
                _setting("multi_currency_enabled", "启用多币种", "启用后业务单据可维护币种和汇率。", option_value("multi_currency_enabled", "0"), "bool"),
                _setting("international_default_currency", "默认币种", "单据未指定币种时使用的默认币种。", option_value("international_default_currency", option_value("default_currency", "CNY")), "select", options=[
                    {"value": "CNY", "label": "人民币"},
                    {"value": "USD", "label": "美元"},
                    {"value": "EUR", "label": "欧元"},
                ]),
                _setting("international_exchange_rate_decimals", "汇率小数位", "外币折算和计量单位换算率的小数位。", option_value("international_exchange_rate_decimals", option_value("exchange_rate_decimals", "6")), "int", min=0, max=10),
                _setting("default_language", "默认语言", "系统默认显示语言。", option_value("default_language", "zh_CN"), "select", options=[
                    {"value": "zh_CN", "label": "简体中文"},
                    {"value": "en_US", "label": "English"},
                ]),
            ],
        },
        {
            "key": "common_control",
            "title": "公共控制",
            "icon": "bi-grid-3x3-gap",
            "description": "控制公司级基础选项、价格口径、用户角色和公共精度。",
            "settings": [
                _setting("price_management_enabled", "启用调价单管理", "启用后销售、采购价格调整需要通过调价单留痕。", option_value("price_management_enabled", "1"), "bool"),
                _setting("price_not_editable", "价格本不可编辑", "启用后业务单据只能引用价格本价格，不能直接改价。", option_value("price_not_editable", "0"), "bool"),
                _setting("review_after_price_change", "审核后自动更新价格本", "启用后已审核调价单会同步更新客户、供应商或物料价格本。", option_value("review_after_price_change", "1"), "bool"),
                _setting("user_multi_role_enabled", "用户支持多角色", "启用后用户可拥有多个业务角色，权限按角色集合计算。", option_value("user_multi_role_enabled", "0"), "bool"),
                _setting("multi_unit_auto_price", "多计量单位自动换算价格", "启用后按计量单位换算率自动换算单价和金额。", option_value("multi_unit_auto_price", "1"), "bool"),
                _setting("default_customer_price_level", "客户价格等级默认", "新建客户和销售单据默认使用的价格等级。", option_value("default_customer_price_level", "normal"), "select", options=[
                    {"value": "normal", "label": "普通客户价"},
                    {"value": "dealer", "label": "经销商价"},
                    {"value": "vip", "label": "重点客户价"},
                ]),
                _setting("default_tax_included", "默认含税", "销售、采购和委外价格默认是否按含税价录入。", option_value("default_tax_included", "1"), "bool"),
                _setting("default_currency", "默认币种", "单据未指定币种时使用的本位币。", option_value("default_currency", "CNY"), "select", options=[
                    {"value": "CNY", "label": "人民币"},
                    {"value": "USD", "label": "美元"},
                    {"value": "EUR", "label": "欧元"},
                ]),
            ],
        },
        {
            "key": "data_precision",
            "title": "数据精度",
            "icon": "bi-123",
            "description": "统一数量、价格、金额、税额、汇率、工价和折扣的小数位。",
            "settings": [
                _setting("exchange_rate_decimals", "换算率小数位", "计量单位换算率和辅助单位换算率的小数位。", option_value("exchange_rate_decimals", "6"), "int", min=0, max=10),
                _setting("quantity_decimals", "数量小数位", "采购、销售、库存、生产和委外数量的小数位。", option_value("quantity_decimals", "3"), "int", min=0, max=8),
                _setting("quantity_rounding", "数量舍零", "启用后数量按设置小数位自动舍入。", option_value("quantity_rounding", "0"), "bool"),
                _setting("unit_price_decimals", "单价小数位", "销售、采购、委外、服务费用单价的小数位。", option_value("unit_price_decimals", "4"), "int", min=0, max=8),
                _setting("unit_price_tax_included", "单价含税", "启用后单价字段默认按含税单价解释。", option_value("unit_price_tax_included", "1"), "bool"),
                _setting("amount_decimals", "金额小数位", "未税金额、含税金额、成本金额和库存金额的小数位。", option_value("amount_decimals", "2"), "int", min=0, max=6),
                _setting("invoice_price_decimals", "发票单价小数位", "销售发票、采购发票和费用发票单价的小数位。", option_value("invoice_price_decimals", "4"), "int", min=0, max=8),
                _setting("invoice_amount_decimals", "发票金额小数位", "发票未税金额、税额和价税合计的小数位。", option_value("invoice_amount_decimals", "2"), "int", min=0, max=6),
                _setting("yield_rate_decimals", "成品率小数位", "生产、委外收回和质量统计成品率的小数位。", option_value("yield_rate_decimals", "2"), "int", min=0, max=6),
                _setting("loss_rate_decimals", "损耗率小数位", "BOM、生产领料、委外发料和库存损耗率的小数位。", option_value("loss_rate_decimals", "2"), "int", min=0, max=6),
                _setting("discount_rate_decimals", "折扣率小数位", "销售折扣、采购折扣和费用折扣的小数位。", option_value("discount_rate_decimals", "4"), "int", min=0, max=6),
                _setting("labor_rate_decimals", "计件工价小数位", "工序、报工和计件工资工价的小数位。", option_value("labor_rate_decimals", "2"), "int", min=0, max=6),
            ],
        },
        {
            "key": "business_control",
            "title": "业务控制",
            "icon": "bi-kanban",
            "description": "控制试运行期间的菜单范围、单据流转、审批和数据完整性要求。",
            "settings": [
                _setting("nav_mode", "导航模式", "建议试运行保持 gt_pilot，只开放核心业务闭环。", option_value("nav_mode", _env_default("NAV_MODE", "gt_pilot")), "select", options=[
                    {"value": "gt_pilot", "label": "试点核心菜单"},
                    {"value": "full", "label": "完整菜单"},
                ]),
                _setting("require_project_serial", "强制项目号/机号", "关闭时项目号和机号作为建议追溯字段；预测生产、备库生产、小公司简化流程可不填。", option_value("require_project_serial", "0"), "bool"),
                _setting("hide_unstable_modules", "隐藏未稳定模块", "高级售后、质量、资产、物流、营销等模块在核心稳定前不进入普通导航。", option_value("hide_unstable_modules", "1"), "bool"),
                _setting("document_approval_flow", "启用单据审批流", "销售、采购、库存、生产、委外、售后和财务单据按保存、提交、审核、反审核、作废控制动作。", option_value("document_approval_flow", "1"), "bool"),
                _setting("draft_document_number_policy", "草稿单据编号方式", "控制草稿保存时是否立即占用正式单号。", option_value("draft_document_number_policy", "reserve"), "select", options=[
                    {"value": "reserve", "label": "保存即占号"},
                    {"value": "submit", "label": "提交时占号"},
                ]),
                _setting("void_requires_reason", "作废必须填写原因", "启用后所有已保存业务单据作废时必须填写原因。", option_value("void_requires_reason", "1"), "bool"),
            ],
        },
        {
            "key": "inventory_control",
            "title": "库存与成本",
            "icon": "bi-box-seam",
            "description": "控制仓库执行、库存金额和期间关闭前置检查。",
            "settings": [
                _setting("negative_stock_block", "禁止负库存", "出库、领料、委外发料必须先校验可用库存。关闭后允许临时负库存，但数据健康会提示风险。", option_value("negative_stock_block", "1"), "bool"),
                _setting("allow_negative_stock", "允许负库存", "仅用于试运行或历史补录；正式上线建议关闭，并以禁止负库存作为主控制。", option_value("allow_negative_stock", "0"), "bool"),
                _setting("batch_serial_control", "启用批号/机号追溯", "启用后库存单据、委外、生产领料和售后备件需保留批号、机号或项目号追溯字段。", option_value("batch_serial_control", "1"), "bool"),
                _setting("period_close_inventory_check", "结账前库存检查", "期间结账前检查待过账单据、负库存、未核成本和未关闭异常。", option_value("period_close_inventory_check", "1"), "bool"),
                _setting("warehouse_location_required", "启用库位管理", "启用后库存单据需要维护仓库和库位。", option_value("warehouse_location_required", "1"), "bool"),
                _setting("inventory_batch_required", "启用批号管理", "启用后入库、出库、调拨和盘点需要维护批号。", option_value("inventory_batch_required", "0"), "bool"),
                _setting("inventory_check_freeze_stock", "盘点期间冻结库存", "启用后盘点范围内物料在盘点完成前不允许出入库。", option_value("inventory_check_freeze_stock", "0"), "bool"),
                _setting("cost_method", "成本方法", "当前系统按移动加权成本作为库存金额口径。", option_value("cost_method", "weighted_average"), "select", options=[
                    {"value": "weighted_average", "label": "移动加权"},
                    {"value": "manual", "label": "手工成本"},
                ]),
            ],
        },
        {
            "key": "purchase_control",
            "title": "采购参数",
            "icon": "bi-cart-check",
            "description": "控制请购、采购订单、到货入库和应付衔接规则。",
            "settings": [
                _setting("purchase_require_source_request", "采购订单要求来源请购", "开启后采购订单应从已审核请购单生成；临时补录需管理员复核。", option_value("purchase_require_source_request", "0"), "bool"),
                _setting("purchase_receipt_requires_order", "采购入库要求来源订单", "开启后采购入库必须关联采购订单，便于到货、库存和应付对账。", option_value("purchase_receipt_requires_order", "1"), "bool"),
                _setting("default_purchase_tax_rate", "默认采购税率", "采购单据行未带税率时使用的默认税率。", option_value("default_purchase_tax_rate", "13"), "int", min=0, max=99, unit="%"),
                _setting("purchase_over_receipt_policy", "超订单收货控制", "控制采购入库数量超过订单未收数量时的处理方式。", option_value("purchase_over_receipt_policy", "warn"), "select", options=[
                    {"value": "block", "label": "禁止"},
                    {"value": "warn", "label": "提示"},
                    {"value": "allow", "label": "允许"},
                ]),
                _setting("purchase_price_source", "采购价格来源", "采购单价默认取供应商价格、最近采购价或手工录入。", option_value("purchase_price_source", "supplier_price"), "select", options=[
                    {"value": "supplier_price", "label": "供应商价格"},
                    {"value": "last_price", "label": "最近采购价"},
                    {"value": "manual", "label": "手工录入"},
                ]),
                _setting("purchase_invoice_match_required", "应付要求三单匹配", "启用后采购应付需要匹配订单、入库和发票。", option_value("purchase_invoice_match_required", "1"), "bool"),
            ],
        },
        {
            "key": "sales_control",
            "title": "销售参数",
            "icon": "bi-receipt",
            "description": "控制销售订单、发货、应收和项目机号追踪规则。",
            "settings": [
                _setting("sales_shipment_requires_order", "发货要求来源销售订单", "开启后销售发货必须关联销售订单，便于发货、应收和项目交付对账。", option_value("sales_shipment_requires_order", "1"), "bool"),
                _setting("sales_credit_limit_check", "启用客户信用检查", "保存或审核销售订单时提示客户信用额度、逾期应收和未结发货风险。", option_value("sales_credit_limit_check", "0"), "bool"),
                _setting("default_sales_tax_rate", "默认销售税率", "销售单据行未带税率时使用的默认税率。", option_value("default_sales_tax_rate", "13"), "int", min=0, max=99, unit="%"),
                _setting("sales_price_source", "销售价格来源", "销售单价默认取客户价格、物料价格、最近成交价或手工录入。", option_value("sales_price_source", "customer_price"), "select", options=[
                    {"value": "customer_price", "label": "客户价格"},
                    {"value": "material_price", "label": "物料价格"},
                    {"value": "last_price", "label": "最近成交价"},
                    {"value": "manual", "label": "手工录入"},
                ]),
                _setting("shipment_over_order_policy", "超订单发货控制", "控制发货数量超过销售订单未发数量时的处理方式。", option_value("shipment_over_order_policy", "block"), "select", options=[
                    {"value": "block", "label": "禁止"},
                    {"value": "warn", "label": "提示"},
                    {"value": "allow", "label": "允许"},
                ]),
                _setting("receivable_confirm_on_shipment", "发货生成应收", "启用后销售发货审核后生成应收待结算数据。", option_value("receivable_confirm_on_shipment", "1"), "bool"),
            ],
        },
        {
            "key": "production_control",
            "title": "生产参数",
            "icon": "bi-gear-wide-connected",
            "description": "控制工单、BOM、领料、完工入库和项目机号追踪规则。",
            "settings": [
                _setting("work_order_requires_bom", "工单要求有效BOM", "开启后生产工单必须关联有效BOM；研发试制可先关闭并由工程复核。", option_value("work_order_requires_bom", "1"), "bool"),
                _setting("production_pick_requires_work_order", "生产领料要求来源工单", "开启后领料必须关联工单，便于材料耗用、成本和项目追踪。", option_value("production_pick_requires_work_order", "1"), "bool"),
                _setting("completion_requires_material_issue", "完工入库检查领料", "完工入库前检查是否存在未领关键物料或负库存风险。", option_value("completion_requires_material_issue", "1"), "bool"),
            ],
        },
        {
            "key": "subcontract_control",
            "title": "委外参数",
            "icon": "bi-diagram-3",
            "description": "控制委外订单、发料、收回、报废短收和应付衔接规则。",
            "settings": [
                _setting("subcontract_issue_requires_order", "委外发料要求来源订单", "开启后委外发料必须关联委外订单，避免无来源发料。", option_value("subcontract_issue_requires_order", "1"), "bool"),
                _setting("subcontract_receive_requires_issue", "委外收回检查发料", "开启后委外收回时检查对应发料和未回数量。", option_value("subcontract_receive_requires_issue", "1"), "bool"),
                _setting("subcontract_scrap_requires_reason", "委外报废要求原因", "委外报废、短收必须填写原因和责任归属。", option_value("subcontract_scrap_requires_reason", "1"), "bool"),
            ],
        },
        {
            "key": "service_control",
            "title": "售后参数",
            "icon": "bi-tools",
            "description": "控制服务卡、安装验收、服务单、RMA 和费用成本归集规则。",
            "settings": [
                _setting("service_requires_machine_serial", "服务单建议关联机号", "开启后服务单保存时提示机号；是否强制仍由项目号/机号总开关控制。", option_value("service_requires_machine_serial", "1"), "bool"),
                _setting("rma_requires_service_order", "RMA要求来源服务单", "开启后退换修必须从服务单生成，便于问题关闭和费用追踪。", option_value("rma_requires_service_order", "1"), "bool"),
                _setting("service_cost_collection", "启用服务成本归集", "开启后服务材料、工时和委外费用进入服务成本报表。", option_value("service_cost_collection", "1"), "bool"),
            ],
        },
        {
            "key": "finance_control",
            "title": "财务参数",
            "icon": "bi-cash-coin",
            "description": "控制应收应付、期间关闭、发票和基础财务报表口径。",
            "settings": [
                _setting("ar_ap_auto_from_documents", "单据自动生成应收应付", "开启后销售发货、采购入库、委外收回按业务规则生成往来待结算数据。", option_value("ar_ap_auto_from_documents", "1"), "bool"),
                _setting("period_close_requires_backup", "结账前要求数据库备份", "开启后期间关闭前必须存在最近24小时数据库备份。", option_value("period_close_requires_backup", "1"), "bool"),
                _setting("finance_statement_basis", "财务报表口径", "基础财务报表默认展示的金额口径。", option_value("finance_statement_basis", "tax_included"), "select", options=[
                    {"value": "tax_included", "label": "含税金额"},
                    {"value": "untaxed", "label": "未税金额"},
                ]),
            ],
        },
        {
            "key": "ai_assistant",
            "title": "AI 助手",
            "icon": "bi-cpu",
            "description": "用于操作手册说明和入口指引，不参与自动审核、过账、报表生成或业务处理。",
            "settings": [
                _setting("ai_enabled", "启用 AI 助手", "关闭后不显示 AI 辅助分析入口。", option_value("ai_enabled", "0"), "bool"),
                _setting("ai_model", "模型名称", "填写部署环境允许使用的模型名称。", option_value("ai_model", _env_default("OPENAI_MODEL", ""))),
                _setting("ai_api_key", "API Key", "密钥只用于服务器端调用，留空保存会保留原值。", option_value("ai_api_key", _env_default("OPENAI_API_KEY", "")), "secret", wide=True),
            ],
        },
        {
            "key": "system_audit",
            "title": "系统审计",
            "icon": "bi-shield-check",
            "description": "控制操作日志保留和系统运维审计口径。",
            "settings": [
                _setting("operation_log_retention_days", "操作日志保留天数", "无关键字清理操作日志时，系统只清理早于该天数的日志，避免误删近期审计追踪。", option_value("operation_log_retention_days", "180"), "int", min=30, max=3650, unit="天"),
            ],
        },
    ]


def ensure_system_options_table(execute_db):
    # DDL 已迁移至 services/schema_migrations.py（20260615_001_system_options_unique_key）
    # 请求期不再执行 CREATE TABLE / ALTER TABLE
    pass


def ensure_code_rules_table(execute_db):
    for row in complete_code_rule_rows(default_code_rule_rows()) + document_number_rule_definitions():
        execute_db(
            """
            INSERT INTO erp_code_rules
                (rule_key, target_type, prefix, date_format, sequence_length, separator, reset_scope, manual_allowed, is_active, remark)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (rule_key) DO NOTHING
            """,
            (
                row["rule_key"],
                row["target_type"],
                row["prefix"],
                row["date_format"],
                row["sequence_length"],
                row["separator"],
                row["reset_scope"],
                row["manual_allowed"],
                row["is_active"],
                row["remark"],
            ),
        )


def default_code_rule_rows():
    return [
        {
            "rule_key": "material:products.code",
            "label": "物料编码",
            "target_type": "material",
            "prefix": "MAT",
            "date_format": "NONE",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "continuous",
            "manual_allowed": True,
            "is_active": True,
            "remark": "新增物料未填写编码时按物料分类编码生成；未选分类时使用默认前缀。",
        },
        {
            "rule_key": "document:default",
            "label": "单据默认规则",
            "target_type": "document",
            "prefix": "DOC",
            "date_format": "YYYYMMDD",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "daily",
            "manual_allowed": True,
            "is_active": False,
            "remark": "仅在未配置单据专用规则时使用；默认不启用。",
        },
        {
            "rule_key": "document:PR",
            "label": "采购申请",
            "target_type": "document",
            "prefix": "PR",
            "date_format": "YYYYMMDD",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "daily",
            "manual_allowed": True,
            "is_active": False,
            "remark": "启用后接管采购申请号。",
        },
        {
            "rule_key": "document:PO",
            "label": "采购订单",
            "target_type": "document",
            "prefix": "PO",
            "date_format": "YYYYMMDD",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "daily",
            "manual_allowed": True,
            "is_active": False,
            "remark": "启用后接管采购订单号。",
        },
        {
            "rule_key": "document:SO",
            "label": "销售订单",
            "target_type": "document",
            "prefix": "SO",
            "date_format": "YYYYMMDD",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "daily",
            "manual_allowed": True,
            "is_active": False,
            "remark": "启用后接管销售订单号。",
        },
        {
            "rule_key": "document:WO",
            "label": "生产工单",
            "target_type": "document",
            "prefix": "WO",
            "date_format": "YYYYMMDD",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "daily",
            "manual_allowed": True,
            "is_active": False,
            "remark": "启用后接管生产工单号。",
        },
        {
            "rule_key": "document:TR",
            "label": "库存调拨",
            "target_type": "document",
            "prefix": "TR",
            "date_format": "YYYYMMDD",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "daily",
            "manual_allowed": True,
            "is_active": False,
            "remark": "启用后接管库存调拨单号。",
        },
    ]


def document_code_rule_coverage():
    return [
        ("document:PR", "采购申请", "purchase_requisitions", "req_no", "PR"),
        ("document:PO", "采购订单", "purchase_orders", "order_no", "PO"),
        ("document:SO", "销售订单", "sales_orders", "order_no", "SO"),
        ("document:WO", "生产工单", "work_orders", "wo_no", "WO"),
        ("document:TR", "库存调拨", "transfer_orders", "transfer_no", "TR"),
        ("document:IC", "库存盘点", "inventory_check_orders", "check_no", "IC"),
        ("document:IA", "库存调整", "inventory_adjustments", "adj_no", "IA"),
        ("document:OS", "委外订单", "subcontract_orders", "order_no", "OS"),
        ("document:OSI", "委外发料", "subcontract_issue_orders", "issue_no", "OSI"),
        ("document:OSR", "委外收回", "subcontract_receive_orders", "receive_no", "OSR"),
        ("document:SS", "销售发货", "sales_shipments", "shipment_no", "SS"),
        ("document:SVO", "服务单", "machine_service_orders", "order_no", "SVO"),
        ("document:RMA", "服务RMA", "machine_service_rmas", "rma_no", "RMA"),
    ]


DOCUMENT_NUMBER_RULE_DEFINITIONS = [
    ("document:purchase_requisitions.req_no", "采购申请", "purchase_requisitions", "req_no", "PR"),
    ("document:purchase_orders.order_no", "采购订单", "purchase_orders", "order_no", "PO"),
    ("document:purchase_receipts.receipt_no", "采购入库", "purchase_receipts", "receipt_no", "PIR"),
    ("document:sales_orders.order_no", "销售订单", "sales_orders", "order_no", "SO"),
    ("document:sales_shipments.shipment_no", "销售发货", "sales_shipments", "shipment_no", "SS"),
    ("document:work_orders.wo_no", "生产工单", "work_orders", "wo_no", "WO"),
    ("document:pick_lists.doc_no", "生产领料", "pick_lists", "doc_no", "PIK"),
    ("document:production_completion_orders.completion_no", "完工入库", "production_completion_orders", "completion_no", "PC"),
    ("document:operation_reports.report_no", "工序报工", "operation_reports", "report_no", "OPR"),
    ("document:subcontract_orders.order_no", "委外订单", "subcontract_orders", "order_no", "OS"),
    ("document:subcontract_issue_orders.issue_no", "委外发料", "subcontract_issue_orders", "issue_no", "OSI"),
    ("document:subcontract_receive_orders.receive_no", "委外收回", "subcontract_receive_orders", "receive_no", "OSR"),
    ("document:transfer_orders.transfer_no", "库存调拨", "transfer_orders", "transfer_no", "TR"),
    ("document:inventory_check_orders.check_no", "库存盘点", "inventory_check_orders", "check_no", "IC"),
    ("document:inventory_adjustments.adj_no", "库存调整", "inventory_adjustments", "adj_no", "IA"),
    ("document:inventory_assembly_orders.assembly_no", "组装拆卸", "inventory_assembly_orders", "assembly_no", "ASM"),
    ("document:stock_transactions.reference_no", "其他出入库", "stock_transactions", "reference_no", "OI"),
    ("document:machine_service_cards.card_no", "设备服务档案", "machine_service_cards", "card_no", "SC"),
    ("document:machine_service_acceptance_checks.acceptance_no", "安装验收", "machine_service_acceptance_checks", "acceptance_no", "SA"),
    ("document:machine_service_return_visits.visit_no", "服务回访", "machine_service_return_visits", "visit_no", "SV"),
    ("document:machine_service_orders.order_no", "服务单", "machine_service_orders", "order_no", "SVO"),
    ("document:machine_service_rmas.rma_no", "服务RMA", "machine_service_rmas", "rma_no", "RMA"),
    ("document:customer_receivables.receivable_no", "应收单", "customer_receivables", "receivable_no", "AR"),
    ("document:supplier_payables.payable_no", "应付单", "supplier_payables", "payable_no", "AP"),
    ("document:customer_receipts.receipt_no", "收款单", "customer_receipts", "receipt_no", "CR"),
    ("document:supplier_payments.payment_no", "付款单", "supplier_payments", "payment_no", "SP"),
    ("document:sales_invoices.invoice_no", "销售发票", "sales_invoices", "invoice_no", "SI"),
    ("document:purchase_invoices.invoice_no", "采购发票", "purchase_invoices", "invoice_no", "PI"),
    ("document:vouchers.voucher_no", "会计凭证", "vouchers", "voucher_no", "V"),
    ("document:quotation_headers.quote_no", "销售报价", "quotation_headers", "quote_no", "QT"),
    ("document:supplier_quotes.quote_no", "供应商报价", "supplier_quotes", "quote_no", "SQ"),
    ("document:quality_inspection_records.inspection_no", "质量检验", "quality_inspection_records", "inspection_no", "QI"),
    ("document:engineering_technical_confirmations.confirm_no", "技术确认", "engineering_technical_confirmations", "confirm_no", "ETC"),
    ("document:product_configurations.config_no", "产品配置", "product_configurations", "config_no", "PCFG"),
]


def document_number_rule_definitions():
    return [
        {
            "rule_key": rule_key,
            "label": label,
            "target_type": "document",
            "source_table": source_table,
            "source_field": source_field,
            "prefix": prefix,
            "date_format": "YYYYMMDD",
            "sequence_length": 4,
            "separator": "",
            "reset_scope": "daily",
            "manual_allowed": True,
            "is_active": False,
            "remark": f"{label}单据编号规则",
        }
        for rule_key, label, source_table, source_field, prefix in DOCUMENT_NUMBER_RULE_DEFINITIONS
    ]


def code_rule_coverage_map():
    mapping = {
        "material:products.code": {"label": "物料编码", "source_table": "products", "source_field": "code"},
        "document:default": {"label": "单据默认规则", "source_table": "", "source_field": ""},
    }
    for rule_key, label, source_table, source_field, _prefix in document_code_rule_coverage():
        mapping[rule_key] = {"label": label, "source_table": source_table, "source_field": source_field}
    for row in document_number_rule_definitions():
        mapping[row["rule_key"]] = {"label": row["label"], "source_table": row["source_table"], "source_field": row["source_field"]}
    return mapping


def complete_code_rule_rows(rows):
    existing = {row["rule_key"] for row in rows}
    completed = list(rows)
    for rule_key, label, source_table, source_field, prefix in document_code_rule_coverage():
        if rule_key in existing:
            continue
        completed.append(
            {
                "rule_key": rule_key,
                "label": label,
                "target_type": "document",
                "prefix": prefix,
                "date_format": "YYYYMMDD",
                "sequence_length": 4,
                "separator": "",
                "reset_scope": "daily",
                "manual_allowed": True,
                "is_active": False,
                "remark": f"启用后接管{label}编号。",
                "source_table": source_table,
                "source_field": source_field,
            }
        )
    return completed


def load_code_rule_rows(query_db):
    defaults = code_rule_coverage_map()
    rows = query_db(
        """
        SELECT rule_key, target_type, prefix, date_format, sequence_length, separator,
               reset_scope, manual_allowed, is_active, remark, updated_at
        FROM erp_code_rules
        ORDER BY CASE
            WHEN rule_key='material:products.code' THEN 0
            WHEN rule_key='document:default' THEN 1
            ELSE 2
        END, rule_key
        """,
        (),
    )
    result = []
    for row in rows:
        item = dict(row)
        item["label"] = defaults.get(item["rule_key"], {}).get("label") or item["rule_key"]
        item["source_table"] = defaults.get(item["rule_key"], {}).get("source_table") or ""
        item["source_field"] = defaults.get(item["rule_key"], {}).get("source_field") or ""
        item["next_preview"] = preview_code_rule(item, query_db)
        result.append(item)
    return complete_code_rule_rows(result)


def load_document_number_rule_rows(query_db):
    defaults = {row["rule_key"]: row for row in document_number_rule_definitions()}
    rows = query_db(
        """
        SELECT rule_key, target_type, prefix, date_format, sequence_length, separator,
               reset_scope, manual_allowed, is_active, remark, updated_at
        FROM erp_code_rules
        WHERE rule_key = ANY(%s)
        ORDER BY rule_key
        """,
        (list(defaults.keys()),),
    )
    saved = {row["rule_key"]: dict(row) for row in rows}
    result = []
    for default in document_number_rule_definitions():
        item = dict(default)
        item.update(saved.get(default["rule_key"], {}))
        item["label"] = default["label"]
        item["source_table"] = default["source_table"]
        item["source_field"] = default["source_field"]
        item["next_preview"] = preview_code_rule(item, query_db)
        result.append(item)
    return result


def _safe_sql_identifier(name):
    text = str(name or "")
    if not text.replace("_", "").isalnum():
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return '"' + text.replace('"', '""') + '"'


def _code_rule_date_part(date_format):
    fmt = (date_format or "").strip().upper()
    if fmt in {"", "NONE", "NO_DATE"}:
        return ""
    if fmt == "YYYYMM":
        return f"{datetime.now():%Y%m}"
    if fmt == "YYMMDD":
        return f"{datetime.now():%y%m%d}"
    return f"{datetime.now():%Y%m%d}"


def _code_rule_base(rule):
    prefix = str(rule.get("prefix") or "")
    separator = str(rule.get("separator") or "")
    date_part = _code_rule_date_part(rule.get("date_format"))
    if separator:
        parts = [part for part in (prefix, date_part) if part]
        return separator.join(parts) + separator
    return f"{prefix}{date_part}"


def preview_code_rule(rule, query_db):
    if (rule.get("target_type") or "") == "material":
        rule = dict(rule)
        rule["date_format"] = "NONE"
    base = _code_rule_base(rule)
    sequence_length = int(rule.get("sequence_length") or 4)
    source_table = rule.get("source_table") or ""
    source_field = rule.get("source_field") or ""
    next_number = 1
    if source_table and source_field and (rule.get("reset_scope") or "daily") in {"daily", "monthly"}:
        try:
            rows = query_db(
                f"""
                SELECT {_safe_sql_identifier(source_field)} AS code
                FROM {_safe_sql_identifier(source_table)}
                WHERE {_safe_sql_identifier(source_field)} LIKE %s
                ORDER BY {_safe_sql_identifier(source_field)} DESC
                LIMIT 1
                """,
                (f"{base}%",),
            )
            if rows and rows[0].get("code"):
                suffix = str(rows[0]["code"]).replace(base, "", 1)
                next_number = int(suffix or "0") + 1
        except Exception:
            next_number = 1
    return f"{base}{next_number:0{sequence_length}d}"


def _save_code_rules(request_form, execute_db):
    allowed_date_formats = {"YYYYMMDD", "YYYYMM", "YYMMDD", "NONE"}
    allowed_reset_scopes = {"daily", "monthly", "continuous"}
    allowed_target_types = {"material", "document"}
    count = int(request_form.get("code_rule_count") or 0)
    saved = 0
    for idx in range(count):
        rule_key = (request_form.get(f"code_rule_key_{idx}") or "").strip()
        if not rule_key:
            continue
        target_type = (request_form.get(f"code_rule_target_type_{idx}") or "").strip()
        if target_type not in allowed_target_types:
            target_type = "document" if rule_key.startswith("document:") else "material"
        prefix = (request_form.get(f"code_rule_prefix_{idx}") or "").strip().upper()
        date_format = (request_form.get(f"code_rule_date_format_{idx}") or "YYYYMMDD").strip().upper()
        if date_format not in allowed_date_formats:
            date_format = "YYYYMMDD"
        reset_scope = (request_form.get(f"code_rule_reset_scope_{idx}") or "daily").strip().lower()
        if reset_scope not in allowed_reset_scopes:
            reset_scope = "daily"
        try:
            sequence_length = int(request_form.get(f"code_rule_sequence_length_{idx}") or 4)
        except ValueError:
            sequence_length = 4
        sequence_length = max(2, min(sequence_length, 8))
        separator = (request_form.get(f"code_rule_separator_{idx}") or "").strip()[:4]
        manual_allowed = bool(request_form.get(f"code_rule_manual_allowed_{idx}"))
        is_active = bool(request_form.get(f"code_rule_is_active_{idx}"))
        remark = (request_form.get(f"code_rule_remark_{idx}") or "").strip()
        if not prefix:
            prefix = "MAT" if target_type == "material" else "DOC"
        if target_type == "material":
            date_format = "NONE"
            reset_scope = "continuous"
        execute_db(
            """
            INSERT INTO erp_code_rules
                (rule_key, target_type, prefix, date_format, sequence_length, separator,
                 reset_scope, manual_allowed, is_active, remark, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (rule_key)
            DO UPDATE SET
                target_type=EXCLUDED.target_type,
                prefix=EXCLUDED.prefix,
                date_format=EXCLUDED.date_format,
                sequence_length=EXCLUDED.sequence_length,
                separator=EXCLUDED.separator,
                reset_scope=EXCLUDED.reset_scope,
                manual_allowed=EXCLUDED.manual_allowed,
                is_active=EXCLUDED.is_active,
                remark=EXCLUDED.remark,
                updated_at=NOW()
            """,
            (
                rule_key,
                target_type,
                prefix,
                date_format,
                sequence_length,
                separator,
                reset_scope,
                manual_allowed,
                is_active,
                remark,
            ),
        )
        saved += 1
    return saved


def render_system_dashboard(root_dir, query_rows, count_rows, backup_rows, columns, render_dashboard, clean_text=None):
    clean_text = clean_text or (lambda value, fallback="-": value or fallback)
    security_status = security_config_status()
    option_rows = query_rows(
        """
        SELECT id, option_key, option_value, remark, updated_at
        FROM system_options
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 30
        """
    )
    logs = query_rows(
        """
        SELECT id, username, action, target, created_at
        FROM operation_logs
        ORDER BY id DESC
        LIMIT 30
        """
    )
    backups = backup_rows(12) if backup_rows else []
    backup_items = [
        {
            "id": idx + 1,
            "file_name": row.get("file_name"),
            "size_mb": row.get("size_mb"),
            "modified_time": row.get("modified_time"),
            "next_step": "按恢复预案保留最近可用备份",
            "owner_role": "系统管理员",
        }
        for idx, row in enumerate(backups)
    ]
    health_rows = [
        {
            "id": 0,
            "check_item": "安全配置",
            "status": "可上线" if security_status["go_live_ready"] else ("本地试用" if security_status["local_bootstrapped"] else "需引导"),
            "next_step": "正式上线前保存真实数据库密码并替换生产密钥" if not security_status["go_live_ready"] else "定期轮换密钥并复核备份",
            "owner_role": "系统管理员",
            "downstream_impact": "影响登录会话、数据库连接、安装启动和上线验收",
        },
        {
            "id": 1,
            "check_item": "系统参数",
            "status": "正常",
            "next_step": "仅由管理员维护影响业务闭环的参数",
            "owner_role": "系统管理员",
            "downstream_impact": "影响导航范围、库存控制、期间关闭和 AI 辅助",
        },
        {
            "id": 2,
            "check_item": "操作日志",
            "status": "正常" if count_rows("operation_logs") >= 0 else "待检查",
            "next_step": "定期复核关键单据和系统设置变更",
            "owner_role": "系统管理员",
            "downstream_impact": "影响审计追踪和试运行问题定位",
        },
    ]
    return render_dashboard(
        "系统工作台",
        "系统管理员使用的参数、日志、备份和健康检查入口；普通业务处理不在此页面完成。",
        [
            {"label": "系统参数", "value": len(option_rows), "hint": "已保存参数"},
            {"label": "用户", "value": count_rows("users"), "hint": "系统账号"},
            {"label": "操作日志", "value": count_rows("operation_logs"), "hint": "审计追踪"},
            {"label": "备份文件", "value": len(backup_items), "hint": "最近备份"},
        ],
        [
            {"label": "系统参数", "url": "/system_settings/form", "icon": "bi-sliders"},
            {"label": "用户", "url": "/users", "icon": "bi-people"},
            {"label": "角色权限", "url": "/permissions/roles", "icon": "bi-shield-lock"},
            {"label": "数据健康", "url": "/system/data-health", "icon": "bi-heart-pulse"},
            {"label": "数据库备份", "url": "/system/database-backups", "icon": "bi-database-down"},
            {"label": "操作日志", "url": "/operation_logs", "icon": "bi-clock-history"},
        ],
        [
            {
                "title": "系统健康待办",
                "rows": health_rows,
                "columns": columns(
                    ("check_item", "检查项"),
                    ("status", "状态"),
                    ("next_step", "下一步"),
                    ("owner_role", "责任角色"),
                    ("downstream_impact", "下游影响"),
                ),
            },
            {
                "title": "最近系统参数",
                "rows": option_rows,
                "columns": columns(
                    ("option_key", "参数键"),
                    ("option_value", "参数值"),
                    ("remark", "说明"),
                    ("updated_at", "更新时间"),
                ),
                "empty_text": "暂无已保存系统参数。",
            },
            {
                "title": "最近备份",
                "rows": backup_items,
                "columns": columns(
                    ("file_name", "文件"),
                    ("size_mb", "大小MB"),
                    ("modified_time", "备份时间"),
                    ("next_step", "下一步"),
                    ("owner_role", "责任角色"),
                ),
                "empty_text": "暂无备份文件。",
            },
            {
                "title": "最近操作日志",
                "rows": [
                    {
                        "id": row.get("id"),
                        "username": clean_text(row.get("username"), "-"),
                        "action": clean_text(row.get("action"), "-"),
                        "target": clean_text(row.get("target"), "-"),
                        "created_at": row.get("created_at"),
                    }
                    for row in logs
                ],
                "columns": columns(
                    ("username", "用户"),
                    ("action", "动作"),
                    ("target", "对象"),
                    ("created_at", "时间"),
                ),
                "empty_text": "暂无操作日志。",
            },
        ],
    )


def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    login_required = deps["login_required"]
    role_required = deps.get("role_required")
    log_action = deps.get("log_action") or (lambda *args, **kwargs: None)

    def query_one(sql, params=None):
        return query_db(sql, params or (), one=True)

    admin_required = role_required("admin", "manager") if role_required else (lambda func: func)

    @app.get("/system_settings/form", endpoint="system_settings")
    @login_required
    @admin_required
    def system_settings():
        ensure_system_options_table(execute_db)
        ensure_code_rules_table(execute_db)
        return render_template(
            "system_settings.html",
            setting_groups=build_setting_groups(query_one),
            coding_rules=load_code_rule_rows(query_db),
            parameter_effects=system_parameter_effect_rows(),
        )

    @app.get("/system/doc-rules", endpoint="system_doc_rules")
    @login_required
    @admin_required
    def system_doc_rules():
        ensure_code_rules_table(execute_db)
        return render_template(
            "document_number_rules.html",
            coding_rules=load_document_number_rule_rows(query_db),
        )

    @app.post("/system/doc-rules/save", endpoint="system_doc_rules_save")
    @login_required
    @admin_required
    def system_doc_rules_save():
        ensure_code_rules_table(execute_db)
        saved = _save_code_rules(request.form, execute_db)
        log_action("单据编号设置", "保存规则", f"{saved} 项")
        flash(f"已保存 {saved} 项单据编号规则。", "success")
        return redirect(url_for("system_doc_rules"))

    @app.get("/system/opening-period", endpoint="system_opening_period")
    @login_required
    @admin_required
    def system_opening_period():
        ensure_system_options_table(execute_db)
        return render_template(
            "opening_period_settings.html",
            settings=_opening_period_view_model(query_one),
            impact_rows=[
                {
                    "area": "物料期初",
                    "path": "/inventory/opening",
                    "impact": "启用期间前的库存基准；开账锁定后不应随意改期初数量和金额。",
                },
                {
                    "area": "委外期初",
                    "path": "/subcontract/opening",
                    "impact": "启用期间前已发给加工商、未收回的委外在制基准。",
                },
                {
                    "area": "应收期初",
                    "path": "/finance/opening/receivables",
                    "impact": "启用期间前客户欠款基准，影响后续收款、对账和账龄。",
                },
                {
                    "area": "应付期初",
                    "path": "/finance/opening/payables",
                    "impact": "启用期间前供应商和委外加工商欠款基准，影响付款和对账。",
                },
                {
                    "area": "期间结账",
                    "path": "/finance/period-close",
                    "impact": "当前期间作为后续结账、反结账和单据期间校验的起点。",
                },
            ],
        )

    @app.post("/system/opening-period/save", endpoint="system_opening_period_save")
    @login_required
    @admin_required
    def system_opening_period_save():
        ensure_system_options_table(execute_db)
        try:
            system_start_period = _validate_period_value(request.form.get("system_start_period"), "系统启用期间")
            finance_start_period = _validate_period_value(request.form.get("finance_start_period"), "财务启用期间")
            finance_current_period = _validate_period_value(request.form.get("finance_current_period"), "当前期间")
            period_start_date = _validate_date_value(request.form.get("system_period_start_date"), "启用开始日期")
            period_end_date = _validate_date_value(request.form.get("system_period_end_date"), "启用结束日期", required=False)
            opening_lock_date = _validate_date_value(request.form.get("opening_lock_date"), "期初锁定日期", required=False)
            if period_end_date and period_end_date < period_start_date:
                raise ValueError("启用结束日期不能早于启用开始日期")
            if finance_current_period < finance_start_period:
                raise ValueError("当前期间不能早于财务启用期间")
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("system_opening_period"))

        values = {
            "system_start_period": (system_start_period, "系统启用期间"),
            "system_period_start_date": (period_start_date, "启用开始日期"),
            "system_period_end_date": (period_end_date, "启用结束日期"),
            "finance_start_period": (finance_start_period, "财务启用期间"),
            "finance_current_period": (finance_current_period, "当前期间"),
            "period_control_enabled": ("1" if request.form.get("period_control_enabled") else "0", "启用期间控制"),
            "opening_lock_date": (opening_lock_date, "期初锁定日期"),
            "opening_data_locked": ("1" if request.form.get("opening_data_locked") else "0", "开账后锁定期初数据"),
        }
        for key, (value, remark) in values.items():
            _save_system_option(execute_db, query_one, key, value, remark)
        log_action("开账时间/启用期间", "保存设置", f"{system_start_period} / {finance_current_period}")
        flash("开账时间和启用期间已保存。", "success")
        return redirect(url_for("system_opening_period"))

    @app.get("/system/database-backups", endpoint="system_database_backups")
    @login_required
    @admin_required
    def system_database_backups():
        backup_dir = Path(__file__).resolve().parents[1] / "backups"
        dumps = []
        if backup_dir.exists():
            for path in sorted(backup_dir.glob("*.dump"), key=lambda item: item.stat().st_mtime, reverse=True):
                if path.stat().st_size <= 0:
                    continue
                dumps.append(
                    {
                        "file_name": path.name,
                        "size_mb": f"{path.stat().st_size / 1024 / 1024:.1f}",
                        "modified_time": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "path": str(path.relative_to(Path(__file__).resolve().parents[1])),
                    }
                )
        root_dir = Path(__file__).resolve().parents[1]
        return render_template(
            "database_backup.html",
            backups=dumps[:30],
            restore_status=latest_restore_status(root_dir),
        )

    @app.post("/system/database-backups/run", endpoint="system_database_backup_run")
    @login_required
    @admin_required
    def system_database_backup_run():
        backup_type = (request.form.get("backup_type") or "manual").strip()
        output = None
        if backup_type == "pre_migration":
            desc = (request.form.get("description") or "manual").strip()
            safe_desc = "".join(ch for ch in desc if ch.isalnum() or ch in {"_", "-"}).strip("_-") or "manual"
            output = Path(__file__).resolve().parents[1] / "backups" / f"pre_migration_{safe_desc}.dump"
        try:
            dump_path = run_backup(output)
        except Exception as exc:
            log_action("数据库备份", "执行失败", str(exc)[:180])
            return jsonify({"status": "error", "msg": f"备份失败：{str(exc)[:180]}"}), 500
        log_action("数据库备份", "执行成功", dump_path.name)
        return jsonify({"status": "success", "msg": f"备份完成：{dump_path.name}"})

    @app.get("/system/version-updates", endpoint="system_version_updates")
    @login_required
    @admin_required
    def system_version_updates():
        return render_template("version_updates.html", update_status=get_update_status())

    @app.post("/system/version-updates/run", endpoint="system_version_update_run")
    @login_required
    @admin_required
    def system_version_update_run():
        package_id = (request.form.get("package_id") or "").strip()
        try:
            result = launch_update(package_id)
        except Exception as exc:
            log_action("版本更新", package_id or "未选择更新包", f"启动失败: {str(exc)[:180]}")
            return jsonify({"status": "error", "msg": f"更新启动失败：{str(exc)[:180]}"}), 400
        log_action("版本更新", result["package"]["package_name"], f"pid={result['pid']} log={result['log_path']}")
        return jsonify(
            {
                "status": "success",
                "msg": "更新程序已启动，请等待脚本执行完成后重新打开系统。",
                "pid": result["pid"],
                "log_path": result["log_path"],
            }
        )

    @app.post("/system_settings/form/save", endpoint="system_settings_save")
    @login_required
    @admin_required
    def system_settings_save():
        ensure_system_options_table(execute_db)
        ensure_code_rules_table(execute_db)
        _save_code_rules(request.form, execute_db)
        groups = build_setting_groups(query_one)
        saved = 0
        known_setting_keys = {setting["key"] for group in groups for setting in group["settings"]}
        if any(key in request.form for key in known_setting_keys):
            for group in groups:
                for setting in group["settings"]:
                    key = setting["key"]
                    if setting["type"] == "bool":
                        value = "1" if request.form.get(key) else "0"
                    elif setting["type"] == "secret" and not request.form.get(key):
                        continue
                    else:
                        value = (request.form.get(key) or "").strip()
                    execute_db(
                        """
                        UPDATE system_options
                        SET key=COALESCE(key, %s), value=%s, option_value=%s, remark=%s, updated_at=NOW()
                        WHERE option_key=%s
                        """,
                        (key, value, value, setting.get("label"), key),
                    )
                    if not query_one("SELECT id FROM system_options WHERE option_key=%s LIMIT 1", (key,)):
                        execute_db(
                            """
                            INSERT INTO system_options (key, value, option_key, option_value, remark, updated_at)
                            VALUES (%s,%s,%s,%s,%s,NOW())
                            """,
                            (key, value, key, value, setting.get("label")),
                        )
                    try:
                        execute_db(
                            """
                            UPDATE system_options
                            SET key=COALESCE(key, option_key), value=option_value
                            WHERE option_key=%s
                            """,
                            (key,),
                        )
                    except Exception as sync_exc:
                        app.logger.warning("系统参数 %s 字段同步失败: %s", key, sync_exc)
                    saved += 1
        log_action("系统参数", "保存参数", f"{saved} 项")
        return jsonify({"status": "success", "msg": f"已保存 {saved} 项系统参数"})

    @app.post("/system_settings/form/test_ai_llm", endpoint="system_settings_test_ai_llm")
    @login_required
    @admin_required
    def system_settings_test_ai_llm():
        model = (request.form.get("ai_model") or "").strip()
        api_key = (request.form.get("ai_api_key") or os.environ.get("OPENAI_API_KEY") or "").strip()
        if not model:
            return jsonify({"status": "error", "msg": "请先填写模型名称"}), 400
        if not api_key:
            return jsonify({"status": "error", "msg": "请先填写或配置 API Key"}), 400
        return jsonify({"status": "success", "msg": "参数已具备连接测试条件"})

    @app.get("/users", endpoint="users")
    @login_required
    @admin_required
    def users():
        role = (request.args.get("role") or "").strip()
        status = (request.args.get("status") or "").strip()
        search = (request.args.get("search") or "").strip()
        sort_by = request.args.get("sort_by") or "id"
        sort_order = "desc" if (request.args.get("sort_order") or "desc").lower() == "desc" else "asc"
        allowed_sort = {"id", "username", "role", "status", "created_at"}
        if sort_by not in allowed_sort:
            sort_by = "id"
        where = []
        params = []
        if role:
            where.append("role=%s")
            params.append(role)
        if status:
            where.append("COALESCE(status,'normal')=%s")
            params.append(status)
        if search:
            where.append("(username ILIKE %s OR role ILIKE %s OR COALESCE(status,'normal') ILIKE %s)")
            params.extend([f"%{search}%"] * 3)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = query_db(
            f"""
            SELECT id, username, role, COALESCE(status,'normal') AS status, created_at
            FROM users
            {where_sql}
            ORDER BY {sort_by} {sort_order}
            LIMIT 300
            """,
            tuple(params),
        )
        return render_template(
            "user.html",
            users=rows,
            filters={"role": role, "status": status, "search": search},
            sort_by=sort_by,
            sort_order=sort_order,
        )

    @app.post("/users/add", endpoint="add_user")
    @login_required
    @admin_required
    def add_user():
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "user").strip()
        full_name = (request.form.get("full_name") or username).strip()
        if not username or not password:
            return jsonify({"status": "error", "msg": "用户名和密码不能为空"}), 400
        exists = query_one("SELECT id FROM users WHERE username=%s", (username,))
        if exists:
            return jsonify({"status": "error", "msg": "用户名已存在"}), 400
        execute_db(
            "INSERT INTO users (username, password_hash, full_name, role, status, created_at) VALUES (%s,%s,%s,%s,'normal',NOW())",
            (username, generate_password_hash(password), full_name, role),
        )
        log_action("用户管理", "新增用户", username)
        return jsonify({"status": "success", "msg": "用户已创建"})

    @app.post("/users/reset-password", endpoint="reset_user_password")
    @login_required
    @admin_required
    def reset_user_password():
        user_id = request.form.get("user_id")
        password = request.form.get("new_password") or ""
        if not str(user_id or "").isdigit() or not password:
            return jsonify({"status": "error", "msg": "参数不完整"}), 400
        execute_db("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash(password), int(user_id)))
        log_action("用户管理", "重置密码", str(user_id))
        return jsonify({"status": "success", "msg": "密码已重置"})

    @app.post("/users/status", endpoint="update_user_status")
    @login_required
    @admin_required
    def update_user_status():
        payload = request.get_json(silent=True) or {}
        user_id = payload.get("user_id")
        status = (payload.get("status") or "normal").strip()
        if not str(user_id or "").isdigit() or status not in {"normal", "disabled", "inactive"}:
            return jsonify({"status": "error", "msg": "参数不正确"}), 400
        if int(user_id) == int(session.get("user_id") or 0) and status != "normal":
            return jsonify({"status": "error", "msg": "\u4e0d\u80fd\u7981\u7528\u6216\u505c\u7528\u5f53\u524d\u767b\u5f55\u8d26\u53f7"}), 400
        execute_db("UPDATE users SET status=%s WHERE id=%s", (status, int(user_id)))
        log_action("用户管理", "更新状态", f"{user_id}:{status}")
        return jsonify({"status": "success", "msg": "用户状态已更新"})

    @app.post("/users/delete", endpoint="delete_user")
    @login_required
    @admin_required
    def delete_user():
        payload = request.get_json(silent=True) or {}
        ids = payload.get("ids") or ([payload.get("id")] if payload.get("id") else [])
        ids = [int(value) for value in ids if str(value).isdigit()]
        if not ids:
            return jsonify({"status": "error", "msg": "请选择用户"}), 400
        if int(session.get("user_id") or 0) in ids:
            return jsonify({"status": "error", "msg": "\u4e0d\u80fd\u5220\u9664\u5f53\u524d\u767b\u5f55\u8d26\u53f7"}), 400
        placeholders = ",".join(["%s"] * len(ids))
        execute_db(f"DELETE FROM users WHERE id IN ({placeholders}) AND COALESCE(status,'normal') IN ('disabled','inactive')", tuple(ids))
        log_action("用户管理", "删除用户", ",".join(map(str, ids)))
        return jsonify({"status": "success", "msg": "已删除禁用用户"})
