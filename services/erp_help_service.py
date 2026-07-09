"""In-app operation manual content for ERP help pages."""
ERP_OPERATION_MANUAL = [
    {
        "key": "quick_start",
        "title": "快速上手",
        "summary": "先看待办和预警，再进入对应单据或报表处理。",
        "steps": [
            "从右上角预警查看库存、缺料、待办、待审核和账龄风险。",
            "从待处理单据进入今日需要处理的销售、采购、库存、生产和财务事项。",
            "新增业务单据走单据入口；查询已有单据走列表入口；汇总分析走报表入口。",
            "处理完成后回到待办、预警或报表复核状态和余额。",
        ],
        "links": [
            {"label": "待处理单据", "href": "/pending-documents"},
            {"label": "待审核", "href": "/approval/pending"},
            {"label": "报表中心", "href": "/reports"},
        ],
        "tips": ["不要在报表页新增单据；报表只用于查询、导出和查看明细。"],
    },
    {
        "key": "master_data",
        "title": "基础资料",
        "summary": "先维护物料、客户、供应商、仓库、工序和 BOM，再做业务单据。",
        "steps": [
            "物料名称、规格、单位、默认仓库和安全库存要先维护完整。",
            "机床项目按项目号和机号追踪；它们是追溯字段，不是所有场景都强制填写。",
            "BOM、工艺路线、工作中心和委外工序决定生产、采购和委外建议。",
            "客户、供应商、委外加工商要区分清楚，避免应收应付归集错误。",
        ],
        "links": [
            {"label": "物料档案", "href": "/material"},
            {"label": "客户档案", "href": "/customer"},
            {"label": "供应商档案", "href": "/supplier"},
            {"label": "BOM", "href": "/bom"},
        ],
        "tips": ["单据行只从物料名称选择物料，编码、规格、单位由系统带出。"],
    },
    {
        "key": "engineering_readiness",
        "title": "工程准备",
        "summary": "销售订单进入采购建议和生产准备前，必须锁定技术确认、BOM、图纸、工艺路线和齐套状态。",
        "steps": [
            "从项目/机号台账查看工程准备度，先确认项目号、机号和销售订单来源。",
            "缺少技术确认时，从台账进入新增技术确认单，系统会带入销售订单、产品、项目号、机号和图纸版本。",
            "技术确认单保存前要校验 BOM、图纸、工艺路线和工作中心，确认后下游才能作为 MRP、齐套和工单依据。",
            "如果工程准备未就绪，按阻塞原因分派给技术/工艺或计划/采购处理，再回到项目/机号台账复核。",
        ],
        "links": [
            {"label": "技术确认单", "href": "/engineering/technical-confirmations"},
            {"label": "齐套检查", "href": "/engineering/kitting"},
            {"label": "项目/机号台账", "href": "/projects"},
            {"label": "工程准备预警API", "href": "/api/project-machine-ledger/engineering-readiness/alerts"},
        ],
        "tips": [
            "项目/机号台账是只读追溯入口，不在台账里直接创建采购、库存或生产单据。",
            "AI助手可以按项目号、机号或销售订单号读取工程准备上下文，但不会自动确认技术资料。",
        ],
    },
    {
        "key": "purchase",
        "title": "采购业务",
        "summary": "缺料或需求形成采购申请，再生成采购订单、收货、入库和应付。",
        "steps": [
            "从采购建议查看 MRP 缺口，必要时生成采购申请。",
            "采购订单保存后按状态提交、审核，审核后才能作为收货来源。",
            "到货时从采购订单生成收货或入库，核对物料、数量、仓库和项目机号。",
            "收货形成库存和应付后，在应付或账龄报表中跟进付款。",
        ],
        "links": [
            {"label": "采购建议", "href": "/procurement/suggestions"},
            {"label": "采购订单列表", "href": "/purchase-orders"},
            {"label": "待处理单据", "href": "/pending-documents"},
            {"label": "应收应付账龄", "href": "/finance/reports/aging"},
        ],
        "tips": ["已审核但无法收货时，先检查订单状态、未收数量、物料和仓库。"],
    },
    {
        "key": "sales",
        "title": "销售业务",
        "summary": "销售订单驱动发货、应收、项目号和机号追溯。",
        "steps": [
            "录入销售订单时确认客户、交期、项目号、机号和明细物料。",
            "订单提交审核后，进入待发货队列或待处理单据。",
            "发货时核对库存、仓库、批次、机号和未发数量。",
            "发货或服务结算形成应收后，在账龄报表跟进回款风险。",
        ],
        "links": [
            {"label": "销售订单列表", "href": "/sales-orders"},
            {"label": "待处理单据", "href": "/pending-documents"},
            {"label": "应收应付账龄", "href": "/finance/reports/aging"},
        ],
        "tips": ["项目号和机号要贯穿销售、库存、生产、服务和财务报表。"],
    },
    {
        "key": "inventory",
        "title": "库存业务",
        "summary": "入库、出库、调拨、盘点和库存预警要保持账实一致。",
        "steps": [
            "入库前确认来源单据、物料、仓库、数量和成本。",
            "出库前确认可用库存、项目号、机号和业务用途。",
            "调拨和盘点要保留单据记录，不能直接改库存余额。",
            "库存预警按缺料程度、生产影响和采购周期排序处理。",
        ],
        "links": [
            {"label": "库存预警", "href": "/inventory_alerts"},
            {"label": "库存明细", "href": "/inventory/detail"},
            {"label": "库存流水", "href": "/transactions"},
            {"label": "安全库存/短缺报表", "href": "/inventory/reports/shortage"},
        ],
        "tips": ["库存报表是只读分析，调整库存必须走库存单据。"],
    },
    {
        "key": "production",
        "title": "生产业务",
        "summary": "工单围绕 BOM、领料、完工入库和项目机号闭环。",
        "steps": [
            "建工单前确认物料、BOM、工艺路线和项目机号。",
            "工单下达后生成领料需求，按仓库库存和缺料情况处理。",
            "生产完成后按合格数量做完工或入库，异常数量走返工、报废或差异说明。",
            "回到工单详情核对领退料、完工、质量和成本影响。",
        ],
        "links": [
            {"label": "工单列表", "href": "/work-orders"},
            {"label": "新增工单", "href": "/work-orders/new"},
            {"label": "齐套检查", "href": "/engineering/kitting"},
        ],
        "tips": ["工单列表看状态和下一步；新增和编辑必须进入独立单据页。"],
    },
    {
        "key": "subcontract",
        "title": "委外业务",
        "summary": "委外订单、发料、收回、短收报废和应付要分开处理。",
        "steps": [
            "先确认委外加工商、委外工序、发料物料和收回物料。",
            "委外发料减少本厂库存，并形成加工在制跟踪。",
            "委外收回时核对合格数量、短收、报废和应付金额。",
            "委外在制和应付报表用于对账，不直接新增单据。",
        ],
        "links": [
            {"label": "委外发料列表", "href": "/subcontract_issue"},
            {"label": "委外收回列表", "href": "/subcontract_receive"},
            {"label": "委外在制报表", "href": "/inventory/reports/subcontract-wip"},
            {"label": "委外订单执行报表", "href": "/inventory/reports/subcontract-execution"},
            {"label": "委外收发明细报表", "href": "/inventory/reports/subcontract-inout-detail"},
            {"label": "委外短少报废差异报表", "href": "/inventory/reports/subcontract-variance"},
            {"label": "委外应付对账报表", "href": "/inventory/reports/subcontract-payable-reconcile"},
        ],
        "tips": ["发料、收回创建必须走独立单据入口，列表只负责查询和跟进。"],
    },
    {
        "key": "finance",
        "title": "财务对账",
        "summary": "应收、应付、库存成本和期间结账用于闭环复核。",
        "steps": [
            "销售发货或服务结算后检查应收余额和账龄。",
            "采购入库或委外收回后检查应付余额和账龄。",
            "库存出入库后复核库存成本、库存余额和流水。",
            "期间结账前先处理硬性阻断项和预警项。",
        ],
        "links": [
            {"label": "应收应付账龄", "href": "/finance/reports/aging"},
            {"label": "账龄区间汇总", "href": "/finance/reports/aging-buckets"},
            {"label": "库存成本明细账", "href": "/finance/inventory-cost/detail"},
            {"label": "期间结账", "href": "/finance/period-close"},
        ],
        "tips": ["财务报表用于复核余额；实际收付款登记走对应业务入口。"],
    },
    {
        "key": "service",
        "title": "售后服务",
        "summary": "售后按机号建立服务卡、服务单、RMA和费用成本追踪。",
        "steps": [
            "按机号查询服务卡，确认客户、项目号、出厂和安装信息。",
            "服务单记录现场问题、处理过程、费用和责任归属。",
            "RMA 处理要关联机号、物料、退回、维修和索赔。",
            "服务成本报表用于复核费用，不直接改服务单状态。",
        ],
        "links": [
            {"label": "售后服务明细", "href": "/service/reports/service-detail"},
            {"label": "RMA 索赔报表", "href": "/service/reports/rma-claim"},
            {"label": "服务成本报表", "href": "/service/reports/cost"},
        ],
        "tips": ["机号是售后追溯主线，服务和财务结算都要能回查。"],
    },
    {
        "key": "system",
        "title": "系统维护",
        "summary": "参数、用户权限、数据健康和备份属于系统管理员日常工作。",
        "steps": [
            "系统参数控制库存、导入导出、财务、AI 助手等全局行为。",
            "数据健康用于检查核心页面、路由和上线风险。",
            "数据库备份要按计划执行，迁移前必须先备份。",
            "权限变更后用试运行用户检查菜单和直接访问。",
        ],
        "links": [
            {"label": "系统参数", "href": "/system_settings/form"},
            {"label": "AI 助手参数", "href": "/system_settings/form#settings-group-ai_assistant"},
            {"label": "数据健康", "href": "/system/data-health"},
            {"label": "数据库备份", "href": "/system/database-backups"},
        ],
        "tips": ["AI 助手只做辅助分析，不自动审核、过账或对账。"],
    },
]


TOPIC_KEYWORDS = [
    ("engineering_readiness", ("工程准备", "技术确认", "图纸", "项目号", "机号", "齐套", "BOM", "工艺路线")),
    ("purchase", ("采购", "收货", "到货", "供应商", "缺料", "采购建议")),
    ("sales", ("销售", "发货", "客户", "应收", "回款")),
    ("inventory", ("库存", "入库", "出库", "调拨", "盘点", "预警", "短缺")),
    ("production", ("生产", "工单", "领料", "完工", "齐套", "BOM")),
    ("subcontract", ("委外", "外协", "发料", "收回", "加工商")),
    ("finance", ("财务", "应付", "账龄", "付款", "成本", "结账", "对账")),
    ("service", ("售后", "服务", "RMA", "机号", "安装")),
    ("master_data", ("物料", "客户", "供应商", "仓库", "基础资料", "主数据")),
    ("system", ("系统", "参数", "AI", "备份", "权限", "数据健康")),
]


def manual_section_by_key(key):
    for section in ERP_OPERATION_MANUAL:
        if section["key"] == key:
            return section
    return ERP_OPERATION_MANUAL[0]


def match_manual_sections(question):
    text = (question or "").lower()
    matched = []
    for key, keywords in TOPIC_KEYWORDS:
        if any(keyword.lower() in text for keyword in keywords):
            matched.append(manual_section_by_key(key))
    return matched[:3] or [ERP_OPERATION_MANUAL[0]]


def build_ai_guidance(question, mode="operation"):
    sections = match_manual_sections(question)
    primary = sections[0]
    manual_href = f"/help/operation-manual#{primary['key']}"
    lines = [
        f"操作手册说明：{question}",
        f"优先按“{primary['title']}”处理：{primary['summary']}",
        "",
        "建议步骤：",
    ]
    lines.extend(f"{index}. {step}" for index, step in enumerate(primary["steps"], start=1))
    if primary.get("tips"):
        lines.append("")
        lines.append("注意事项：")
        lines.extend(f"- {tip}" for tip in primary["tips"])
    lines.append("")
    lines.append(f"操作手册章节：{manual_href}")
    lines.append("")
    lines.append("操作助手只提供操作手册说明和章节定位，不承载报表、单据处理、审核、过账、对账或库存修改。")
    return {
        "reply": "\n".join(lines),
        "sections": [{"title": item["title"], "href": f"/help/operation-manual#{item['key']}"} for item in sections],
        "links": [{"label": "打开操作手册", "href": manual_href}],
    }
