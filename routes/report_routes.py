"""Report center routes: report section catalog and report landing pages."""
from flask import render_template, request


REPORT_SECTIONS = {
    "sales": {
        "title": "销售报表",
        "sections": [
            ("/sales/reports/pending", "销售未交专题", ["销售订单", "未发货", "交付风险"]),
            ("/sales/reports/customer-ranking", "客户未交排行", ["客户", "未交数量", "未交金额"]),
            ("/sales/reports/execution", "销售执行明细", ["销售订单", "发货", "开票", "收款"]),
            ("/sales/reports/summary", "销售汇总表", ["客户", "项目号", "机号", "销售含税金额", "未交金额"]),
            ("/sales/reports/order-execution-detail", "销售订单执行明细", ["订单数量", "已发货", "未发货", "已开票", "未收款"]),
            ("/sales/reports/order-execution-summary", "销售订单执行汇总", ["客户", "项目号", "机号", "订单金额", "发货金额"]),
            ("/sales/reports/project-serial-order-tracking", "项目/机号销售订单跟踪", ["项目号", "机号", "订单", "发货", "收款"]),
            ("/sales/reports/shipment-execution-detail", "销售发货执行明细", ["发货单", "订单", "出库成本", "未开票金额"]),
            ("/sales/reports/shipped-goods-detail", "发出商品明细", ["发货单", "物料", "未结金额", "结转"]),
            ("/sales/reports/shipped-goods-summary", "发出商品汇总", ["物料", "客户", "本期发出", "期末未结"]),
            ("/sales/reports/shipped-unsettled-detail", "销售发货未结明细", ["已发货", "未开票", "未收款", "余额"]),
            ("/sales/reports/customer-open-order-analysis", "客户未交订单分析", ["客户", "逾期未交", "部分发货"]),
            ("/sales/reports/project-serial-open-order-analysis", "项目/机号未交订单分析", ["项目号", "机号", "未交数量", "交付风险"]),
            ("/sales/reports/invoice-execution-detail", "销售开票执行明细", ["销售订单", "发货单", "应开票", "已开票"]),
            ("/sales/reports/invoice-summary", "销售发票汇总表", ["客户", "项目号", "机号", "含税金额", "税额"]),
            ("/sales/reports/receivable-collection-detail", "销售收款执行明细", ["客户", "订单", "应收", "已收", "逾期"]),
            ("/sales/reports/receivable-aging", "销售应收账龄分析", ["客户", "项目号", "机号", "账龄余额"]),
            ("/sales/reports/project-serial-gross-margin", "项目/机号销售毛利分析", ["销售收入", "发货成本", "毛利", "毛利率"]),
            ("/sales/reports/price-execution-analysis", "销售价格执行分析", ["报价", "订单价", "成交价", "价格偏差"]),
            ("/sales/reports/delivery-delay-analysis", "销售交付逾期分析", ["计划交期", "实际发货", "逾期天数", "责任人"]),
            ("/sales/reports/operation-snapshot", "销售经营快照", ["订单", "发货", "开票", "收款", "未交"]),
            ("/sales/reports/daily", "销售日报", ["日期", "客户", "订单金额", "发货金额", "回款金额"]),
        ],
    },
    "purchase": {
        "title": "采购报表",
        "sections": [
            ("/purchase/reports/pending", "采购未到专题", ["采购订单", "未到", "交期"]),
            ("/purchase/reports/supplier-ranking", "供应商未到排行", ["供应商", "未到数量", "未到金额"]),
            ("/purchase/reports/execution", "采购执行明细", ["采购订单", "收货", "应付"]),
            ("/purchase/reports/summary", "采购汇总表", ["供应商", "项目号", "机号", "采购含税金额", "未到金额"]),
            ("/purchase/reports/request-execution-detail", "采购申请执行明细", ["申请数量", "已下单", "未下单", "需求日期"]),
            ("/purchase/reports/request-execution-summary", "采购申请执行汇总", ["部门", "项目号", "物料", "转单状态"]),
            ("/purchase/reports/order-execution-detail", "采购订单执行明细", ["订单数量", "已收货", "未收货", "交期"]),
            ("/purchase/reports/order-execution-summary", "采购订单执行汇总", ["供应商", "项目号", "机号", "含税金额"]),
            ("/purchase/reports/receipt-tracking", "采购到货跟踪", ["交期", "已收货", "逾期未到"]),
            ("/purchase/reports/receipt-detail", "采购入库明细", ["收货单", "仓库", "批次", "项目号", "机号"]),
            ("/purchase/reports/receipt-summary", "采购入库汇总", ["供应商", "物料", "仓库", "收货金额"]),
            ("/purchase/reports/received-not-invoiced-detail", "收货未开票明细", ["已收货", "未开票", "账龄"]),
            ("/purchase/reports/received-not-invoiced-summary", "收货未开票汇总", ["供应商", "项目号", "机号", "未开票余额"]),
            ("/purchase/reports/invoice-detail", "采购发票明细表", ["供应商", "来源单据", "项目号", "机号", "含税金额"]),
            ("/purchase/reports/invoice-summary", "采购发票汇总表", ["供应商", "项目号", "机号", "含税金额", "税额"]),
            ("/purchase/reports/payment-overview", "采购付款一览表", ["供应商", "应付金额", "已付金额", "未付余额"]),
            ("/purchase/reports/payable-reconciliation-detail", "采购应付对账明细", ["应付", "已付", "未付", "来源单据"]),
            ("/purchase/reports/supplier-execution-analysis", "供应商采购执行分析", ["准交率", "逾期", "收货未开票"]),
            ("/purchase/reports/project-serial-purchase-cost-detail", "项目/机号采购成本明细", ["采购订单", "收货", "应付金额"]),
            ("/purchase/reports/purchase-price-variance", "采购价格波动分析", ["物料", "供应商", "最近价", "差异率"]),
            ("/purchase/reports/purchase-exception-list", "采购异常清单", ["逾期未到", "超订单收货", "超期未开票"]),
            ("/purchase/reports/daily", "采购日报", ["日期", "供应商", "采购金额", "收货金额", "付款金额"]),
        ],
    },
    "inventory": {
        "title": "库存报表",
        "sections": [
            ("/inventory/reports/ledger", "标准库存明细账", ["物料", "仓库", "库位", "批号", "机号", "项目号", "入库", "出库", "结存"]),
            ("/inventory/reports/account-book", "库存台账", ["物料", "仓库", "库位", "期初", "入库", "出库", "结存", "金额"]),
            ("/inventory/reports/monthly", "库存月报表", ["月份", "期初", "本月入库", "本月出库", "期末", "库存金额"]),
            ("/inventory/reports/inout-summary", "物料收发存汇总", ["期初", "入库", "出库", "期末"]),
            ("/inventory/reports/balance", "库存余额查询", ["物料", "仓库", "库位", "可用库存", "锁定", "金额"]),
            ("/inventory/reports/inout-detail", "物料收发存明细", ["日期", "来源单号", "入库", "出库", "结存影响"]),
            ("/inventory/reports/location-stock", "库位库存表", ["仓库", "库位", "物料", "批号", "机号", "数量"]),
            ("/inventory/reports/available-stock", "可用库存查询", ["库存数量", "锁定数量", "可用库存"]),
            ("/inventory/reports/expected-available-stock", "预计可用库存查询表", ["现存量", "待入库", "待出库", "预计可用量"]),
            ("/inventory/reports/shortage", "安全库存/短缺报表", ["安全库存", "可用库存", "缺口"]),
            ("/inventory/reports/turnover", "库存周转率报表", ["出库数量", "平均库存", "周转次数", "周转天数"]),
            ("/inventory/reports/project-occupation", "项目/机号库存占用表", ["项目号", "机号", "库存数量", "库存金额"]),
            ("/inventory/reports/check-difference", "盘点差异汇总表", ["盘点单", "盘盈", "盘亏", "金额"]),
            ("/inventory/reports/fund-occupation", "库存资金占用表", ["库存金额", "单位成本", "项目号", "机号"]),
            ("/inventory/reports/batch-trace", "批次/机号追溯表", ["批号", "机号", "项目号", "库存余额", "流水"]),
            ("/inventory/reports/batch-status", "批次状态表", ["批号", "物料", "仓库", "库位", "状态"]),
            ("/inventory/reports/serial-trace", "序列号跟踪表", ["序列号", "项目号", "来源单据", "库存状态", "流水"]),
            ("/inventory/reports/serial-status", "序列号状态表", ["序列号", "物料", "仓库", "库位", "状态"]),
            ("/inventory/reports/transfer-difference", "调拨差异处理表", ["调拨单", "调出", "调入", "差异数量", "差异金额"]),
            ("/inventory/reports/idle-materials", "呆滞物料分析", ["最后出入库", "库龄", "库存金额"]),
            ("/inventory/reports/stock-aging", "库存库龄分析", ["入库日期", "库龄区间", "库存金额"]),
            ("/inventory/reports/check-difference-detail", "盘点差异明细表", ["盘点单", "物料", "仓库", "库位", "差异"]),
            ("/inventory/reports/cost-ledger", "库存成本总账", ["期间", "物料", "入库金额", "出库金额", "结存金额"]),
            ("/inventory/reports/cost-detail", "库存成本明细账", ["库存事务", "单价", "金额", "来源单据"]),
            ("/inventory/reports/project-serial-cost", "项目/机号库存成本表", ["项目号", "机号", "领用金额", "结存金额"]),
            ("/inventory/reports/exceptions", "库存异常清单", ["负库存", "无库位", "成本为空", "来源缺失"]),
        ],
    },
    "production": {
        "title": "生产报表",
        "sections": [
            ("/production/reports/shortage", "生产缺料报表", ["工单", "缺料", "齐套"]),
            ("/production/reports/bom-forward-query", "BOM 正向查询", ["父项物料", "子件物料", "用量", "版本"]),
            ("/production/reports/bom-reverse-query", "BOM 子件反查", ["子件物料", "父项物料", "项目号", "机号"]),
            ("/production/reports/bom-cost-query", "BOM 成本查询", ["物料", "标准用量", "单位成本", "标准成本"]),
            ("/production/reports/work-order-detail", "生产工单明细", ["工单", "项目号", "机号", "状态"]),
            ("/production/reports/work-order-execution-detail", "生产工单执行明细", ["计划数", "领料数", "报工数", "完工数"]),
            ("/production/reports/work-order-execution-summary", "生产工单执行汇总", ["项目号", "机号", "在制", "完工", "延期"]),
            ("/production/reports/work-order-statistics", "生产任务单统计表", ["产品", "项目号", "机号", "计划数量", "完成数量"]),
            ("/production/reports/project-serial-progress", "项目/机号生产进度跟踪", ["销售订单", "BOM", "工单", "领料", "入库"]),
            ("/production/reports/kitting-shortage", "工单齐套/缺料分析", ["BOM需求", "可用库存", "已领料", "缺料"]),
            ("/production/reports/material-issue-detail", "工单领料明细", ["工单", "物料", "仓库", "批次", "成本"]),
            ("/production/reports/material-issue-summary", "工单领料汇总", ["工单", "项目号", "机号", "材料金额"]),
            ("/production/reports/material-return-detail", "工单退料明细", ["工单", "物料", "退料数量", "退料原因"]),
            ("/production/reports/material-variance", "工单用料差异分析", ["BOM标准用量", "实际净领料", "差异率"]),
            ("/production/reports/completion-inbound-detail", "完工入库明细", ["工单", "产品", "项目号", "机号", "仓库"]),
            ("/production/reports/completion-inbound-summary", "完工入库汇总", ["期间", "项目", "产品", "完工数量"]),
            ("/production/reports/operation-report-detail", "工序报工明细", ["工单", "工序", "工作中心", "工时"]),
            ("/production/reports/operation-report-summary", "工序报工汇总", ["工作中心", "工序", "人员", "效率"]),
            ("/production/reports/quality-inspection-detail", "质量检验明细", ["工单", "检验单", "合格", "不合格"]),
            ("/production/reports/quality-exception-summary", "质量异常汇总", ["项目号", "机号", "工序", "异常率"]),
            ("/production/reports/progress-exception", "生产进度异常报表", ["延期", "缺料", "未报工", "未入库"]),
            ("/production/reports/wip-balance", "在制品余额报表", ["投入成本", "完工转出", "在制余额"]),
            ("/production/reports/work-order-cost-detail", "工单成本明细", ["材料", "人工", "委外", "制造费用"]),
            ("/production/reports/project-serial-production-cost", "项目/机号生产成本明细", ["工单成本", "委外成本", "报废损失"]),
            ("/production/reports/production-cost-variance", "生产成本差异分析", ["计划成本", "实际成本", "差异"]),
            ("/production/reports/cost-accounting", "生产成本核算表", ["工单", "材料成本", "委外成本", "制造费用", "完工成本"]),
            ("/production/reports/monthly-summary", "生产月度汇总", ["开工", "完工", "在制", "缺料", "报废"]),
        ],
    },
    "subcontract": {
        "title": "委外报表",
        "sections": [
            ("/subcontract/reports/order-execution-detail", "委外订单执行明细", ["委外订单", "发料", "收货", "短收", "报废"]),
            ("/subcontract/reports/order-execution-summary", "委外订单执行汇总", ["加工商", "项目号", "机号", "未回数量"]),
            ("/subcontract/reports/issue-detail", "委外发料明细", ["发料单", "物料", "批次", "项目号", "机号"]),
            ("/subcontract/reports/issue-summary", "委外发料汇总", ["加工商", "物料", "发料成本", "未核销"]),
            ("/subcontract/reports/receipt-detail", "委外收货明细", ["收货单", "合格", "短收", "报废", "入库"]),
            ("/subcontract/reports/receipt-summary", "委外收货汇总", ["加工商", "收货数量", "合格率", "短收率"]),
            ("/subcontract/reports/issued-not-returned-analysis", "委外发出未回分析", ["已发料", "未收回", "超期", "在制"]),
            ("/subcontract/reports/shortage-scrap-variance", "委外短收/报废差异分析", ["短收", "报废", "差异金额", "责任加工商"]),
            ("/subcontract/reports/material-consumption-reconciliation", "委外材料核销明细", ["发出材料", "理论耗用", "实际耗用", "差异"]),
            ("/subcontract/reports/payable-reconciliation-detail", "委外应付对账明细", ["收货", "加工单价", "应付", "已付", "未付"]),
            ("/subcontract/reports/processor-balance-analysis", "加工商委外余额分析", ["在制材料", "未回数量", "未结应付"]),
            ("/subcontract/reports/project-serial-progress-tracking", "项目/机号委外进度跟踪", ["项目号", "机号", "发料", "收货", "应付"]),
            ("/subcontract/reports/project-serial-cost-detail", "项目/机号委外成本明细", ["加工费", "材料成本", "短收报废损失"]),
            ("/subcontract/reports/price-execution-analysis", "委外加工价格执行分析", ["标准加工价", "订单价", "结算价", "偏差"]),
            ("/subcontract/reports/delivery-delay-analysis", "委外交期逾期分析", ["计划交期", "实际收货", "逾期天数"]),
            ("/subcontract/reports/quality-exception-analysis", "委外质量异常分析", ["检验数量", "不良数量", "报废数量"]),
            ("/subcontract/reports/operation-snapshot", "委外经营快照", ["下单", "发料", "收货", "未回", "应付"]),
            ("/inventory/reports/subcontract-wip", "委外发出未回报表", ["加工商", "委外订单", "已发料", "未收回", "在制"]),
            ("/inventory/reports/subcontract-execution", "委外订单执行报表", ["委外订单", "加工商", "发料", "收货", "执行进度"]),
            ("/inventory/reports/subcontract-inout-detail", "委外收发明细报表", ["日期", "来源单据", "发出", "收回", "项目号", "机号"]),
            ("/inventory/reports/subcontract-variance", "委外短少报废差异报表", ["短少", "报废", "差异数量", "差异金额", "责任加工商"]),
            ("/inventory/reports/subcontract-payable-reconcile", "委外应付对账报表", ["加工商", "收货", "加工费", "应付", "未结"]),
        ],
    },
    "finance": {
        "title": "财务/成本报表",
        "sections": [
            ("/finance/reports/aging", "应收应付账龄专题", ["账龄天数", "余额"]),
            ("/finance/reports/aging-buckets", "账龄区间汇总", ["账龄区间", "单据数"]),
            ("/finance/reports/balance", "往来余额明细", ["来源单", "余额"]),
            ("/finance/reports/receivable-summary", "应收账款汇总表", ["客户", "项目号", "机号", "应收金额", "余额"]),
            ("/finance/reports/receivable-detail", "应收账款明细表", ["来源单据", "客户", "应收金额", "已收金额", "余额"]),
            ("/finance/reports/receivable-execution-detail", "应收执行明细", ["销售订单", "发货", "开票", "收款", "逾期"]),
            ("/finance/reports/receivable-execution-summary", "应收执行汇总", ["客户", "项目号", "机号", "未收余额"]),
            ("/finance/reports/receivable-aging", "应收账龄分析", ["客户", "项目号", "机号", "账龄"]),
            ("/finance/reports/customer-balance-detail", "客户往来余额明细", ["期初", "应收增加", "收款冲减", "期末"]),
            ("/finance/reports/sales-collection-reconciliation", "销售收款核对表", ["订单", "发货", "开票", "收款差异"]),
            ("/finance/reports/payable-execution-detail", "应付执行明细", ["采购订单", "收货", "开票", "付款"]),
            ("/finance/reports/payable-summary", "应付账款汇总表", ["供应商", "项目号", "机号", "应付金额", "余额"]),
            ("/finance/reports/payable-detail", "应付账款明细表", ["来源单据", "供应商", "应付金额", "已付金额", "余额"]),
            ("/finance/reports/payment-request-statistics", "付款申请统计表", ["供应商", "项目号", "机号", "申请金额", "未付余额"]),
            ("/finance/reports/receivable-warning", "应收账款预警表", ["客户", "到期日", "逾期天数", "应收余额", "预警级别"]),
            ("/finance/reports/payable-warning", "应付账款预警表", ["供应商", "到期日", "逾期天数", "应付余额", "预警级别"]),
            ("/finance/reports/bad-debt-reserve-balance", "坏账准备余额表", ["客户", "账龄区间", "应收余额", "建议比例", "建议准备"]),
            ("/finance/reports/payable-execution-summary", "应付执行汇总", ["供应商", "项目号", "机号", "未付余额"]),
            ("/finance/reports/payable-aging", "应付账龄分析", ["供应商", "项目号", "机号", "账龄"]),
            ("/finance/reports/supplier-balance-detail", "供应商往来余额明细", ["期初", "应付增加", "付款冲减", "期末"]),
            ("/finance/reports/customer-statement", "客户对账单", ["客户", "来源单据", "应收", "已收", "余额"]),
            ("/finance/reports/supplier-statement", "供应商对账单", ["供应商", "来源单据", "应付", "已付", "余额"]),
            ("/finance/reports/customer-vendor-matching-statement", "客商匹配对账单", ["客户", "供应商", "应收", "应付", "净额"]),
            ("/finance/reports/statement-history", "历史对账单", ["往来单位", "收付款单", "核销金额", "项目号", "机号"]),
            ("/finance/reports/purchase-payment-reconciliation", "采购付款核对表", ["订单", "收货", "开票", "付款差异"]),
            ("/finance/reports/received-not-invoiced-detail", "收货未开票明细", ["收货", "未开票", "账龄"]),
            ("/finance/reports/shipped-uncollected-detail", "发货未收款明细", ["已发货", "未收款", "逾期"]),
            ("/finance/reports/cash-bank-balance", "现金银行账户余额", ["账户", "收入", "支出", "余额"]),
            ("/finance/reports/cash-bank-transactions", "现金银行流水", ["账户", "来源单据", "收入", "支出"]),
            ("/finance/reports/enterprise-income-expense-detail", "企业收支明细表", ["日期", "资金账户", "收入金额", "支出金额", "净流入"]),
            ("/finance/reports/credit-management", "信用管理", ["客户", "信用额度", "应收余额", "逾期余额", "信用状态"]),
            ("/finance/reports/account-aging-analysis", "账龄分析表", ["往来类型", "账龄区间", "单据数", "余额"]),
            ("/finance/reports/other-income-expense-detail", "其他收支明细表", ["其他收入", "其他支出", "退款", "资金账户"]),
            ("/finance/reports/account-income-expense-detail", "账户收支明细表", ["账户", "来源单据", "收入", "支出", "余额"]),
            ("/finance/reports/account-balance", "账户余额表", ["账户", "收入", "支出", "余额"]),
            ("/finance/reports/pending-collection-list", "待收款清单", ["客户", "来源单据", "到期日", "逾期天数", "余额"]),
            ("/finance/reports/payment-flow-summary", "收付款流水汇总", ["期间", "账户", "客户", "供应商"]),
            ("/finance/inventory-cost/summary", "库存成本总账", ["库存余额", "单位成本", "库存金额", "项目号", "机号"]),
            ("/finance/inventory-cost/detail", "库存成本明细账", ["库存流水", "成本单价", "入库金额", "出库金额"]),
            ("/finance/reports/inventory-cost-exceptions", "库存成本异常清单", ["成本为空", "负库存", "异常单价", "来源缺失"]),
            ("/finance/reports/project-cost", "项目成本明细", ["项目号", "采购", "库存领用", "委外", "售后"]),
            ("/finance/reports/project-cost-summary", "项目成本汇总", ["项目号", "预算成本", "实际成本", "毛利"]),
            ("/finance/reports/machine-cost", "机号成本明细", ["机号", "材料", "委外", "生产", "售后"]),
            ("/finance/reports/serial-cost-summary", "机号成本汇总", ["机号", "收入", "成本", "毛利"]),
            ("/finance/reports/project-serial-margin-analysis", "项目/机号毛利分析", ["销售收入", "成本", "毛利率"]),
            ("/finance/reports/operation-finance-snapshot", "经营财务快照", ["销售", "采购", "库存", "成本", "应收应付"]),
            ("/finance/reports/open-business-items", "经营未结事项清单", ["未收款", "未付款", "未开票", "成本异常"]),
            ("/finance/reports/project-capital-occupation", "项目资金占用表", ["库存占用", "应收未收", "应付未付"]),
        ],
    },
    "service": {
        "title": "售后报表",
        "sections": [
            ("/service/reports/cost", "售后成本专题", ["服务单", "成本"]),
            ("/service/reports/rma-claim", "RMA索赔专题", ["供应商索赔", "已追回"]),
            ("/service/reports/service-detail", "售后服务明细", ["结算"]),
        ],
    },
}


def _columns(*items):
    return [{"key": key, "label": label} for key, label in items]


def _report_rows(title, words):
    return [
        {
            "report": title,
            "scope": " / ".join(words) if words else "全部",
            "status": "已生成",
        }
    ]


def _module_context(title, section_links=None, words=None):
    section_links = section_links or []
    words = words or [item[1] for item in section_links]
    filters = {
        "date_start": request.args.get("date_start", ""),
        "date_end": request.args.get("date_end", ""),
        "status": request.args.get("status", ""),
        "keyword": request.args.get("keyword", ""),
        "project": request.args.get("project", ""),
    }
    sections = []
    if section_links:
        for url, label, report_words in section_links:
            sections.append(
                {
                    "title": label,
                    "url": url,
                    "columns": _columns(("report", "报表"), ("scope", "条件"), ("status", "状态")),
                    "rows": _report_rows(label, report_words),
                }
            )
    else:
        sections.append(
            {
                "title": title,
                "url": None,
                "columns": _columns(("report", "报表"), ("scope", "条件"), ("status", "状态")),
                "rows": _report_rows(title, words),
            }
        )
    return {
        "title": title,
        "subtitle": "报表条件",
        "filters": filters,
        "export_url": f"{request.path}?export=csv",
        "export_xlsx_url": f"{request.path}?export=xlsx",
        "metrics": [
            {"label": "专题数", "value": len(sections), "hint": "当前报表入口"},
            {"label": "查询状态", "value": "就绪", "hint": "可按条件查询"},
            {"label": "导出", "value": "CSV", "hint": "保留当前筛选条件"},
        ],
        "sections": sections,
    }


def render_module_report_page(csv_response, title, section_links=None, words=None):
    if request.args.get("export") in {"csv", "xlsx", "excel"} or request.args.get("format") in {"csv", "xlsx", "excel"}:
        return csv_response([{"报表": title, "状态": "已生成"}], title)
    return render_template("module_report.html", **_module_context(title, section_links, words))


def render_clean_module_report(csv_response, kind):
    config = REPORT_SECTIONS[kind]
    words = [item[1] for item in config["sections"]]
    return render_module_report_page(csv_response, config["title"], config["sections"], words)


def render_report_center(csv_response):
    reports = []
    for config in REPORT_SECTIONS.values():
        first_url = config["sections"][0][0]
        reports.append(
            {
                "title": config["title"],
                "subtitle": " / ".join(item[1] for item in config["sections"]),
                "url": first_url.rsplit("/", 1)[0],
                "tags": [item[1] for item in config["sections"]],
                "sections": [{"url": url, "title": title} for url, title, _words in config["sections"]],
            }
        )
    if request.args.get("export") in {"csv", "xlsx", "excel"} or request.args.get("format") in {"csv", "xlsx", "excel"}:
        return csv_response([{"报表": item["title"], "状态": "已生成"} for item in reports], "报表中心")
    return render_template("report_center.html", reports=reports)


def render_clean_section_report(csv_response, path):
    for config in REPORT_SECTIONS.values():
        for url, title, words in config["sections"]:
            if url == path:
                return render_module_report_page(csv_response, title, [], words + [title])
    return render_module_report_page(csv_response, "报表中心")
