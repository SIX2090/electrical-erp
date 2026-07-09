"""System configuration stubs for database info, visibility checkers, and master data exports."""
def _empty(*args, **kwargs):
    return []


def build_database_info(query_db=None, **kwargs):
    """Return static database metadata (engine name and database name)."""
    return {"database": "wms", "engine": "PostgreSQL"}


def create_visibility_checker(has_any_role):
    """Return a callable that checks whether the current user has any of the given roles."""
    return lambda *roles: has_any_role(*roles) if roles else True


MASTER_DATA_EXPORT_ITEMS = [
    {
        "key": "products",
        "title": "物料档案导出",
        "path": "/export/products",
        "table": "products",
        "filename": "products",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("code", "物料编码"),
            ("name", "物料名称"),
            ("category", "历史分类"),
            ("category_id", "物料分类ID"),
            ("specification", "规格型号"),
            ("unit", "单位"),
            ("standard_price", "标准单价"),
            ("safety_stock", "安全库存"),
            ("default_tax_rate", "默认税率"),
            ("item_type", "物料类型"),
            ("barcode", "条码"),
            ("drawing_no", "图号"),
            ("material_grade", "材质"),
            ("brand", "品牌"),
            ("origin_place", "产地"),
            ("default_supplier_name", "默认供应商文本"),
            ("default_supplier_id", "默认供应商ID"),
            ("default_warehouse", "默认仓库文本"),
            ("default_warehouse_id", "默认仓库ID"),
            ("default_location", "默认库位文本"),
            ("default_location_id", "默认库位ID"),
            ("purchase_lead_days", "采购提前期"),
            ("min_order_qty", "最小采购量"),
            ("shelf_life_days", "保质期天数"),
            ("batch_control", "批次管理"),
            ("serial_control", "序列号管理"),
            ("inspection_required", "检验要求"),
            ("net_weight", "净重"),
            ("gross_weight", "毛重"),
            ("length_mm", "长度mm"),
            ("width_mm", "宽度mm"),
            ("height_mm", "高度mm"),
            ("abc_class", "ABC分类"),
            ("status", "状态"),
            ("remark", "备注"),
        ],
    },
    {
        "key": "customers",
        "title": "客户档案导出",
        "path": "/export/customers",
        "table": "customers",
        "filename": "customers",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("name", "客户名称"),
            ("contact_person", "联系人"),
            ("phone", "电话"),
            ("address", "地址"),
            ("customer_level", "客户等级"),
            ("category_id", "客户分类ID"),
            ("tax_no", "税号"),
            ("invoice_title", "开票抬头"),
            ("default_tax_rate", "默认税率"),
            ("settlement_term_id", "结算期限ID"),
            ("payment_term_id", "收款条件ID"),
            ("credit_limit", "信用额度"),
            ("credit_used", "已用信用"),
            ("status", "状态"),
            ("remark", "备注"),
        ],
    },
    {
        "key": "suppliers",
        "title": "供应商档案导出",
        "path": "/export/suppliers",
        "table": "suppliers",
        "filename": "suppliers",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("name", "供应商名称"),
            ("contact_person", "联系人"),
            ("phone", "电话"),
            ("address", "地址"),
            ("lead_time_days", "交期天数"),
            ("category_id", "供应商分类ID"),
            ("tax_no", "税号"),
            ("invoice_title", "开票抬头"),
            ("default_tax_rate", "默认税率"),
            ("settlement_term_id", "结算期限ID"),
            ("payment_term_id", "付款条件ID"),
            ("is_outsourced_processor", "是否委外加工商"),
            ("status", "状态"),
            ("remark", "备注"),
        ],
    },
    {
        "key": "warehouses",
        "title": "仓库档案导出",
        "path": "/export/warehouses",
        "table": "warehouses",
        "filename": "warehouses",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("code", "仓库编码"),
            ("name", "仓库名称"),
            ("category_id", "仓库分类ID"),
            ("warehouse_type", "仓库类型"),
            ("status", "状态"),
            ("default_location_id", "默认库位ID"),
            ("remark", "备注"),
        ],
    },
    {
        "key": "locations",
        "title": "库位档案导出",
        "path": "/export/locations",
        "table": "locations",
        "filename": "locations",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("warehouse_id", "所属仓库ID"),
            ("code", "库位编码"),
            ("name", "库位名称"),
            ("location_type", "库位类型"),
            ("is_active", "是否启用"),
            ("status", "状态"),
            ("remark", "备注"),
        ],
    },
    {
        "key": "units",
        "title": "计量单位导出",
        "path": "/export/units",
        "table": "units",
        "filename": "units",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("code", "单位编码"),
            ("name", "单位名称"),
            ("category", "单位分类"),
            ("conversion_rate", "换算率"),
            ("base_unit_id", "基准单位ID"),
            ("status", "状态"),
            ("remark", "备注"),
            ("created_at", "创建时间"),
        ],
    },
    {
        "key": "departments",
        "title": "部门档案导出",
        "path": "/export/departments",
        "table": "departments",
        "filename": "departments",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("code", "部门编码"),
            ("name", "部门名称"),
            ("parent_id", "上级部门ID"),
            ("manager", "负责人"),
            ("phone", "电话"),
            ("status", "状态"),
            ("remark", "备注"),
            ("created_at", "创建时间"),
        ],
    },
    {
        "key": "employees",
        "title": "员工档案导出",
        "path": "/export/employees",
        "table": "employees",
        "filename": "employees",
        "group": "master_data",
        "fields": [
            ("id", "ID"),
            ("code", "员工编码"),
            ("name", "员工姓名"),
            ("dept_id", "所属部门ID"),
            ("position", "岗位"),
            ("phone", "电话"),
            ("email", "邮箱"),
            ("is_sales", "是否销售员"),
            ("standard_labor_rate_per_hour", "标准工时费率"),
            ("status", "状态"),
            ("employment_type", "用工类型"),
            ("hire_date", "入职日期"),
            ("remark", "备注"),
            ("created_at", "创建时间"),
        ],
    },
]


EXPORT_GROUPS = [
    {
        "key": "master_data",
        "title": "基础资料",
        "description": "客户、供应商、仓库、库位、单位、部门、员工、物料等基础资料导出。",
    }
]


EXPORT_ITEMS = {item["key"]: item for item in MASTER_DATA_EXPORT_ITEMS}


def get_export_config(export_type):
    config = EXPORT_ITEMS.get(export_type)
    if not config:
        return {"type": export_type, "title": export_type}
    fields = [{"key": key, "label": label} for key, label in config["fields"]]
    return {
        "type": export_type,
        "key": config["key"],
        "title": config["title"],
        "path": config["path"],
        "table": config["table"],
        "filename": config["filename"],
        "group": config["group"],
        "fields": fields,
        "columns": fields,
    }


def get_export_groups(*args, **kwargs):
    return list(EXPORT_GROUPS)


def get_export_items_by_format(export_format=None, *args, **kwargs):
    return [get_export_config(item["key"]) for item in MASTER_DATA_EXPORT_ITEMS]


def get_import_config(import_type):
    return {"type": import_type, "title": import_type}


get_import_groups = _empty
get_import_items = _empty


def get_system_admin_actions(is_visible_for_roles=None):
    return []


def get_system_shortcuts():
    return []


def get_system_top_cards(is_visible_for_roles=None):
    return []
