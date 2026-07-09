"""Low-voltage switchgear and distribution automation control equipment industry product families, routing templates, and control points."""
from services.industry_defaults import DEFAULT_UNITS, seed_default_units


MACHINE_PRODUCT_FAMILIES = [
    {
        "name": "低压抽出式开关柜",
        "code_prefix": "GCS",
        "unit": "台",
        "routing_template": "钣金加工, 柜体喷涂, 元器件安装, 一次母排装配, 二次接线, 通电调试, 耐压试验, 终检",
        "control_points": "柜体编号、一次方案、二次原理图、元器件批次、耐压记录、出厂检验报告",
        "long_lead_focus": "断路器、接触器、继电器、PLC、触摸屏、铜排",
    },
    {
        "name": "低压固定式开关柜",
        "code_prefix": "GGD",
        "unit": "台",
        "routing_template": "钣金加工, 柜体喷涂, 元器件安装, 母排制作, 二次布线, 通电检查, 出厂检验",
        "control_points": "一次系统图、元器件清单、母排规格、接线检查、绝缘测试",
        "long_lead_focus": "框架断路器、塑壳断路器、电流互感器、铜排",
    },
    {
        "name": "低压配电柜",
        "code_prefix": "PGL",
        "unit": "台",
        "routing_template": "柜体加工, 表面处理, 元件装配, 母排连接, 二次接线, 功能测试, 包装入库",
        "control_points": "防护等级、进出线方式、元件布置、接线工艺、标识标签",
        "long_lead_focus": "双电源转换开关、浪涌保护器、多功能仪表、按钮指示灯",
    },
    {
        "name": "动力配电箱",
        "code_prefix": "XL",
        "unit": "台",
        "routing_template": "箱体加工, 喷塑, 导轨安装, 元件固定, 接线, 导通测试, 检验",
        "control_points": "回路编号、开关选型、线径规格、接线牢固、标识清晰",
        "long_lead_focus": "微型断路器、漏电保护器、接线端子、导线",
    },
    {
        "name": "照明配电箱",
        "code_prefix": "PZ",
        "unit": "台",
        "routing_template": "箱体制作, 表面处理, 导轨安装, 开关装配, 接线, 绝缘测试, 终检",
        "control_points": "回路数、开关极数、漏电保护、接地连续性",
        "long_lead_focus": "小型断路器、漏电开关、零地排、配电箱壳体",
    },
    {
        "name": "无功补偿装置",
        "code_prefix": "WB",
        "unit": "套",
        "routing_template": "柜体制作, 喷涂, 电容器安装, 电抗器装配, 控制器接线, 投切试验, 容量测试",
        "control_points": "补偿容量、电容器批次、电抗器参数、投切逻辑、谐波抑制",
        "long_lead_focus": "电力电容器、电抗器、无功补偿控制器、晶闸管投切开关",
    },
    {
        "name": "配电自动化终端DTU",
        "code_prefix": "DTU",
        "unit": "台",
        "routing_template": "机箱加工, 模块装配, 电源模块安装, 通信模块配置, 遥信遥控接线, 功能测试, 老化试验",
        "control_points": "终端地址、通信规约、遥信分辨率、遥控正确率、电源适应性",
        "long_lead_focus": "DTU核心模块、通信模块、电源模块、工业交换机、SIM卡",
    },
    {
        "name": "环网柜",
        "code_prefix": "HXGN",
        "unit": "台",
        "routing_template": "柜体加工, 气箱装配, 开关安装, 电缆室装配, 二次接线, 气密性试验, 工频耐压",
        "control_points": "充气压力、开关机械特性、联锁装置、电缆插拔头、局放测试",
        "long_lead_focus": "负荷开关、断路器、接地开关、电缆附件、SF6气体",
    },
    {
        "name": "箱式变电站",
        "code_prefix": "YB",
        "unit": "套",
        "routing_template": "箱体制作, 防腐处理, 变压器安装, 高低压柜装配, 电缆连接, 整体联调, 温升试验",
        "control_points": "变压器容量、高低压方案、防护等级、通风散热、整体联调报告",
        "long_lead_focus": "电力变压器、高压开关柜、低压开关柜、壳体、温控系统",
    },
]


DIGIWIN_MANUFACTURING_LOOPS = [
    {
        "loop": "合同到技术确认",
        "owner": "销售/技术",
        "erp_objects": "销售合同, 技术协议, 一次方案, 二次原理图, 项目号, 柜体编号",
        "next_action": "确认主回路方案、元器件选型、特殊要求和交期",
    },
    {
        "loop": "BOM到采购齐套",
        "owner": "技术/采购/仓库",
        "erp_objects": "工程BOM, 生产BOM, MRP需求, 采购订单, 到料跟踪",
        "next_action": "分开跟踪长周期元器件（断路器、PLC、模块）和常规物料",
    },
    {
        "loop": "钣金到柜体喷涂",
        "owner": "生产/外协",
        "erp_objects": "生产工单, 钣金加工, 外协喷涂, 柜体检验",
        "next_action": "跟踪钣金加工进度和喷涂质量，按柜体编号配套",
    },
    {
        "loop": "装配到二次接线",
        "owner": "生产/质检",
        "erp_objects": "元器件装配, 母排制作, 一次接线, 二次布线, 线号标识",
        "next_action": "按图施工，做好元器件批次追溯和接线工艺检查",
    },
    {
        "loop": "调试到出厂检验",
        "owner": "调试/质检",
        "erp_objects": "通电调试, 耐压试验, 功能测试, 出厂检验报告",
        "next_action": "逐项测试保护功能、联锁逻辑、通信功能，留存检验记录",
    },
    {
        "loop": "发货到现场服务",
        "owner": "销售/售后",
        "erp_objects": "发货单, 现场安装指导, 通电调试, 验收报告, 服务档案",
        "next_action": "按项目和柜体编号贯通发货、安装、调试、验收和售后服务",
    },
]


STANDARD_PROCESS_TEMPLATES = [
    {"step": 10, "process": "技术确认与BOM编制", "work_center": "技术部", "output": "一次系统图、二次原理图、BOM清单、作业指导书"},
    {"step": 20, "process": "采购与外协准备", "work_center": "采购部", "output": "元器件采购订单、钣金/喷涂外协单、到料计划"},
    {"step": 30, "process": "钣金加工与表面处理", "work_center": "钣金车间/外协", "output": "柜体、门板、安装板、支架等结构件"},
    {"step": 40, "process": "元器件装配与母排制作", "work_center": "装配车间", "output": "元器件安装到位、母排制作完成、一次线连接"},
    {"step": 50, "process": "二次接线与布线", "work_center": "接线车间", "output": "二次线布线完成、线号标识齐全、接线牢固"},
    {"step": 60, "process": "通电调试与试验", "work_center": "调试区/质检", "output": "通电检查、功能调试、耐压试验、保护定值整定"},
    {"step": 70, "process": "终检包装与发货", "work_center": "质检/仓库", "output": "出厂检验报告、合格证、包装、发货、现场服务交接"},
]


def apply_mechanical_industry_defaults(execute_db):
    return {"seeded_units": seed_default_units(execute_db)}
