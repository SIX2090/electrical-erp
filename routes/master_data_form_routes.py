"""Master data form routes: render create/edit forms for categories, customers, suppliers, etc."""
from flask import render_template

from routes.category_master_routes import CATEGORY_TYPES


def _one(query_one, sql, params):
    return query_one(sql, params) if query_one else None


def _rows(query_rows, sql, params=None):
    return query_rows(sql, params or ()) if query_rows else []


def render_customer_form(query_one, query_rows, customer_id=None):
    customer = _one(query_one, "SELECT * FROM customers WHERE id=%s", (customer_id,)) if customer_id else None
    customer_categories = _rows(query_rows, "SELECT id, name FROM customer_categories ORDER BY name LIMIT 300")
    settlement_terms = _rows(query_rows, "SELECT id, name FROM settlement_terms ORDER BY code LIMIT 200")
    payment_terms = _rows(query_rows, "SELECT id, name FROM payment_terms WHERE direction IN ('receipt','both') OR direction IS NULL ORDER BY code LIMIT 200")
    return render_template(
        "operation_form.html",
        title="编辑客户" if customer else "新增客户",
        subtitle="维护客户联系人、电话、地址、等级和信用额度；付款条件可先记录在备注，系统不自动生成信用或收款数据。",
        back_url="/customer",
        action_url=f"/customer/{customer_id}/edit" if customer else "/customer/new",
        sections=[
            {
                "title": "客户信息",
                "fields": [
                    {"name": "name", "label": "客户名称", "required": True, "value": customer.get("name") if customer else ""},
                    {"name": "contact_person", "label": "联系人", "value": customer.get("contact_person") if customer else ""},
                    {"name": "phone", "label": "电话", "value": customer.get("phone") if customer else ""},
                    {"name": "category_id", "label": "客户分类", "type": "select", "options": customer_categories, "value": customer.get("category_id") if customer else ""},
                    {"name": "customer_level", "label": "客户等级", "value": customer.get("customer_level") if customer else ""},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "启用", "name": "启用"}, {"id": "停用", "name": "停用"}], "value": customer.get("status") if customer else "启用"},
                    {"name": "credit_limit", "label": "信用额度", "type": "number", "step": "0.01", "value": customer.get("credit_limit") if customer else "0"},
                    {"name": "default_tax_rate", "label": "默认税率%", "type": "number", "step": "0.01", "value": customer.get("default_tax_rate") if customer else "13"},
                    {"name": "settlement_term_id", "label": "结算期限", "type": "select", "options": settlement_terms, "value": customer.get("settlement_term_id") if customer else ""},
                    {"name": "payment_term_id", "label": "收款条件", "type": "select", "options": payment_terms, "value": customer.get("payment_term_id") if customer else ""},
                    {"name": "tax_no", "label": "税号", "value": customer.get("tax_no") if customer else ""},
                    {"name": "invoice_title", "label": "开票抬头", "value": customer.get("invoice_title") if customer else ""},
                    {"name": "address", "label": "地址", "type": "textarea", "value": customer.get("address") if customer else ""},
                    {"name": "remark", "label": "付款条件/备注", "type": "textarea", "value": customer.get("remark") if customer else ""},
                ],
            }
        ],
    )


def render_supplier_form(query_one, query_rows, supplier_id=None):
    supplier = _one(query_one, "SELECT * FROM suppliers WHERE id=%s", (supplier_id,)) if supplier_id else None
    supplier_categories = _rows(query_rows, "SELECT id, name FROM supplier_categories ORDER BY name LIMIT 300")
    settlement_terms = _rows(query_rows, "SELECT id, name FROM settlement_terms ORDER BY code LIMIT 200")
    payment_terms = _rows(query_rows, "SELECT id, name FROM payment_terms WHERE direction IN ('payment','both') OR direction IS NULL ORDER BY code LIMIT 200")
    return render_template(
        "operation_form.html",
        title="编辑供应商" if supplier else "新增供应商",
        subtitle="维护供应商联系人、电话、收票/结算地址和默认交期；付款条件可先记录在备注，系统不自动生成应付或付款数据。",
        back_url="/supplier",
        action_url=f"/supplier/{supplier_id}/edit" if supplier else "/supplier/new",
        sections=[
            {
                "title": "供应商信息",
                "fields": [
                    {"name": "name", "label": "供应商名称", "required": True, "value": supplier.get("name") if supplier else ""},
                    {"name": "contact_person", "label": "联系人", "value": supplier.get("contact_person") if supplier else ""},
                    {"name": "phone", "label": "电话", "value": supplier.get("phone") if supplier else ""},
                    {"name": "category_id", "label": "供应商分类", "type": "select", "options": supplier_categories, "value": supplier.get("category_id") if supplier else ""},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "启用", "name": "启用"}, {"id": "停用", "name": "停用"}], "value": supplier.get("status") if supplier else "启用"},
                    {"name": "is_outsourced_processor", "label": "委外加工商", "type": "select", "options": [{"id": "true", "name": "是"}, {"id": "false", "name": "否"}], "value": "true" if (supplier and supplier.get("is_outsourced_processor")) else "false"},
                    {"name": "lead_time_days", "label": "默认交期天数", "type": "number", "step": "1", "value": supplier.get("lead_time_days") if supplier else "0"},
                    {"name": "default_tax_rate", "label": "默认税率%", "type": "number", "step": "0.01", "value": supplier.get("default_tax_rate") if supplier else "13"},
                    {"name": "settlement_term_id", "label": "结算期限", "type": "select", "options": settlement_terms, "value": supplier.get("settlement_term_id") if supplier else ""},
                    {"name": "payment_term_id", "label": "付款条件", "type": "select", "options": payment_terms, "value": supplier.get("payment_term_id") if supplier else ""},
                    {"name": "tax_no", "label": "税号", "value": supplier.get("tax_no") if supplier else ""},
                    {"name": "invoice_title", "label": "开票抬头", "value": supplier.get("invoice_title") if supplier else ""},
                    {"name": "address", "label": "收票/结算地址", "type": "textarea", "value": supplier.get("address") if supplier else ""},
                    {"name": "remark", "label": "付款条件/结算资料备注", "type": "textarea", "value": supplier.get("remark") if supplier else ""},
                ],
            }
        ],
    )


def render_warehouse_form(query_one, query_rows, warehouse_id=None):
    warehouse = _one(query_one, "SELECT * FROM warehouses WHERE id=%s", (warehouse_id,)) if warehouse_id else None
    warehouse_categories = _rows(query_rows, "SELECT id, name FROM warehouse_categories ORDER BY name LIMIT 300")
    locations = _rows(query_rows, "SELECT id, code || ' / ' || name AS name FROM locations WHERE warehouse_id=%s AND COALESCE(is_active, TRUE)=TRUE AND COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY code LIMIT 300", (warehouse_id,)) if warehouse_id else []
    return render_template(
        "operation_form.html",
        title="编辑仓库" if warehouse else "新增仓库",
        subtitle="维护仓库编码、名称和备注；默认仓库由物料档案引用，不在这里自动回填。",
        back_url="/warehouse",
        action_url=f"/warehouse/{warehouse_id}/edit" if warehouse else "/warehouse/new",
        sections=[
            {
                "title": "仓库信息",
                "fields": [
                    {"name": "code", "label": "仓库编码", "required": True, "value": warehouse.get("code") if warehouse else ""},
                    {"name": "name", "label": "仓库名称", "required": True, "value": warehouse.get("name") if warehouse else ""},
                    {"name": "category_id", "label": "仓库分类", "type": "select", "options": warehouse_categories, "value": warehouse.get("category_id") if warehouse else ""},
                    {"name": "warehouse_type", "label": "仓库类型", "type": "select", "options": [{"id": "原料仓", "name": "原料仓"}, {"id": "半成品仓", "name": "半成品仓"}, {"id": "成品仓", "name": "成品仓"}, {"id": "委外仓", "name": "委外仓"}, {"id": "不良品仓", "name": "不良品仓"}, {"id": "备件仓", "name": "备件仓"}], "value": warehouse.get("warehouse_type") if warehouse else ""},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "启用", "name": "启用"}, {"id": "停用", "name": "停用"}], "value": warehouse.get("status") if warehouse else "启用"},
                    {"name": "default_location_id", "label": "默认库位", "type": "select", "options": locations, "value": warehouse.get("default_location_id") if warehouse else ""},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": warehouse.get("remark") if warehouse else ""},
                ],
            }
        ],
    )


def render_location_form(query_one, query_rows, location_id=None):
    location = _one(query_one, "SELECT * FROM locations WHERE id=%s", (location_id,)) if location_id else None
    return render_template(
        "operation_form.html",
        title="编辑库位" if location else "新增库位",
        subtitle="维护库位编码、所属仓库和启用状态。",
        back_url="/locations",
        action_url=f"/location/{location_id}/edit" if location else "/location/new",
        sections=[
            {
                "title": "库位信息",
                "fields": [
                    {"name": "code", "label": "库位编码", "required": True, "value": location.get("code") if location else ""},
                    {"name": "name", "label": "库位名称", "required": True, "value": location.get("name") if location else ""},
                    {"name": "warehouse_id", "label": "所属仓库", "type": "select", "required": True, "options": _rows(query_rows, "SELECT id, name FROM warehouses WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY name LIMIT 300"), "value": location.get("warehouse_id") if location else ""},
                    {"name": "location_type", "label": "库位类型", "type": "select", "options": [{"id": "普通", "name": "普通"}, {"id": "收货", "name": "收货"}, {"id": "发料", "name": "发料"}, {"id": "质检", "name": "质检"}, {"id": "冻结", "name": "冻结"}, {"id": "委外", "name": "委外"}], "value": location.get("location_type") if location else "普通"},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "启用", "name": "启用"}, {"id": "停用", "name": "停用"}], "value": location.get("status") if location else "启用"},
                    {"name": "is_active", "label": "状态", "type": "select", "options": [{"id": "true", "name": "启用"}, {"id": "false", "name": "停用"}], "value": ("true" if (location is None or location.get("is_active")) else "false")},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": location.get("remark") if location else ""},
                ],
            }
        ],
    )


def render_unit_form(query_one, query_rows, unit_id=None):
    unit = _one(query_one, "SELECT * FROM units WHERE id=%s", (unit_id,)) if unit_id else None
    return render_template(
        "operation_form.html",
        title="编辑计量单位" if unit else "新增计量单位",
        subtitle="维护单位编码、名称、分类和换算关系。",
        back_url="/unit",
        action_url=f"/unit/{unit_id}/edit" if unit else "/unit/new",
        sections=[
            {
                "title": "单位信息",
                "fields": [
                    {"name": "code", "label": "编码", "required": True, "value": unit.get("code") if unit else ""},
                    {"name": "name", "label": "名称", "required": True, "value": unit.get("name") if unit else ""},
                    {"name": "category", "label": "分类", "value": unit.get("category") if unit else ""},
                    {"name": "conversion_rate", "label": "换算率", "type": "number", "step": "0.0001", "value": unit.get("conversion_rate") if unit else "1"},
                    {"name": "base_unit_id", "label": "基本单位", "type": "select", "options": _rows(query_rows, "SELECT id, code || ' / ' || name AS name FROM units WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY code LIMIT 200"), "value": unit.get("base_unit_id") if unit else ""},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "启用", "name": "启用"}, {"id": "停用", "name": "停用"}], "value": unit.get("status") if unit else "启用"},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": unit.get("remark") if unit else ""},
                ],
            }
        ],
    )


def render_department_form(query_one, query_rows, department_id=None):
    department = _one(query_one, "SELECT * FROM departments WHERE id=%s", (department_id,)) if department_id else None
    return render_template(
        "operation_form.html",
        title="编辑部门" if department else "新增部门",
        subtitle="维护部门层级、主管和联系电话。",
        back_url="/department",
        action_url=f"/department/{department_id}/edit" if department else "/department/new",
        sections=[
            {
                "title": "部门信息",
                "fields": [
                    {"name": "code", "label": "部门编码", "value": department.get("code") if department else ""},
                    {"name": "name", "label": "部门名称", "required": True, "value": department.get("name") if department else ""},
                    {"name": "parent_id", "label": "上级部门", "type": "select", "options": _rows(query_rows, "SELECT id, name FROM departments WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY name LIMIT 300"), "value": department.get("parent_id") if department else ""},
                    {"name": "manager", "label": "部门主管", "value": department.get("manager") if department else ""},
                    {"name": "phone", "label": "电话", "value": department.get("phone") if department else ""},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "启用", "name": "启用"}, {"id": "停用", "name": "停用"}], "value": department.get("status") if department else "启用"},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": department.get("remark") if department else ""},
                ],
            }
        ],
    )


def render_employee_form(query_one, query_rows, employee_id=None):
    employee = _one(query_one, "SELECT * FROM employees WHERE id=%s", (employee_id,)) if employee_id else None
    return render_template(
        "operation_form.html",
        title="编辑员工" if employee else "新增员工",
        subtitle="维护员工部门、岗位、联系方式和工时单价。",
        back_url="/employee",
        action_url=f"/employee/{employee_id}/edit" if employee else "/employee/new",
        sections=[
            {
                "title": "员工信息",
                "fields": [
                    {"name": "code", "label": "工号", "value": employee.get("code") if employee else ""},
                    {"name": "name", "label": "姓名", "required": True, "value": employee.get("name") if employee else ""},
                    {"name": "dept_id", "label": "部门", "type": "select", "options": _rows(query_rows, "SELECT id, name FROM departments WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY name LIMIT 300"), "value": employee.get("dept_id") if employee else ""},
                    {"name": "position", "label": "岗位", "value": employee.get("position") if employee else ""},
                    {"name": "phone", "label": "电话", "value": employee.get("phone") if employee else ""},
                    {"name": "email", "label": "邮箱", "value": employee.get("email") if employee else ""},
                    {"name": "is_sales", "label": "销售岗", "type": "select", "options": [{"id": "true", "name": "是"}, {"id": "false", "name": "否"}], "value": ("true" if (employee and employee.get("is_sales")) else "false")},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "在职", "name": "在职"}, {"id": "停用", "name": "停用"}, {"id": "离职", "name": "离职"}], "value": employee.get("status") if employee else "在职"},
                    {"name": "employment_type", "label": "用工类型", "type": "select", "options": [{"id": "正式", "name": "正式"}, {"id": "临时", "name": "临时"}, {"id": "外协", "name": "外协"}, {"id": "实习", "name": "实习"}], "value": employee.get("employment_type") if employee else "正式"},
                    {"name": "hire_date", "label": "入职日期", "type": "date", "value": employee.get("hire_date") if employee else ""},
                    {"name": "standard_labor_rate_per_hour", "label": "工时单价", "type": "number", "step": "0.01", "value": employee.get("standard_labor_rate_per_hour") if employee else "0"},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": employee.get("remark") if employee else ""},
                ],
            }
        ],
    )


def render_project_master_form(query_one, query_rows, project_id=None):
    project = _one(query_one, "SELECT * FROM project_masters WHERE id=%s", (project_id,)) if project_id else None
    return render_template(
        "operation_form.html",
        title="编辑项目档案" if project else "新增项目档案",
        subtitle="维护项目号、客户、产品系列、机型、负责人和计划交期；项目号用于销售、BOM、采购、委外、生产、库存、财务和售后追溯。",
        back_url="/project-master",
        action_url=f"/project-master/{project_id}/edit" if project else "/project-master/new",
        sections=[
            {
                "title": "项目资料",
                "fields": [
                    {"name": "project_code", "label": "项目号", "required": True, "value": project.get("project_code") if project else ""},
                    {"name": "project_name", "label": "项目名称", "value": project.get("project_name") if project else ""},
                    {"name": "customer_id", "label": "客户", "type": "select", "options": _rows(query_rows, "SELECT id, name FROM customers WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY name LIMIT 500"), "value": project.get("customer_id") if project else ""},
                    {"name": "product_family", "label": "产品系列", "value": project.get("product_family") if project else ""},
                    {"name": "machine_model", "label": "机型", "value": project.get("machine_model") if project else ""},
                    {"name": "source_order_no", "label": "来源销售/合同号", "value": project.get("source_order_no") if project else ""},
                    {"name": "owner_name", "label": "负责人", "value": project.get("owner_name") if project else ""},
                    {"name": "planned_delivery_date", "label": "计划交期", "type": "date", "value": project.get("planned_delivery_date") if project else ""},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "准备", "name": "准备"}, {"id": "执行", "name": "执行"}, {"id": "暂停", "name": "暂停"}, {"id": "关闭", "name": "关闭"}], "value": project.get("status") if project else "准备"},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": project.get("remark") if project else ""},
                ],
            }
        ],
    )


def render_cabinet_master_form(query_one, query_rows, machine_id=None):
    machine = _one(query_one, "SELECT * FROM cabinet_masters WHERE id=%s", (machine_id,)) if machine_id else None
    return render_template(
        "operation_form.html",
        title="编辑柜号档案" if machine else "新增柜号档案",
        subtitle="维护整机柜号、所属项目、客户、成品物料、机型和售后状态；柜号用于单机成本、发货、安装和售后追溯。",
        back_url="/cabinet-master",
        action_url=f"/cabinet-master/{machine_id}/edit" if machine else "/cabinet-master/new",
        sections=[
            {
                "title": "柜号资料",
                "fields": [
                    {"name": "cabinet_no", "label": "柜号", "required": True, "value": machine.get("cabinet_no") if machine else ""},
                    {"name": "project_id", "label": "所属项目", "type": "select", "options": _rows(query_rows, "SELECT id, project_code || COALESCE(' / ' || NULLIF(project_name,''), '') AS name FROM project_masters ORDER BY project_code LIMIT 500"), "value": machine.get("project_id") if machine else ""},
                    {"name": "customer_id", "label": "客户", "type": "select", "options": _rows(query_rows, "SELECT id, name FROM customers WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive') ORDER BY name LIMIT 500"), "value": machine.get("customer_id") if machine else ""},
                    {"name": "product_id", "label": "成品物料", "type": "select", "options": _rows(query_rows, "SELECT id, code || ' / ' || name AS name FROM products ORDER BY code LIMIT 500"), "value": machine.get("product_id") if machine else ""},
                    {"name": "product_family", "label": "产品系列", "value": machine.get("product_family") if machine else ""},
                    {"name": "machine_model", "label": "机型", "value": machine.get("machine_model") if machine else ""},
                    {"name": "production_stage", "label": "生产阶段", "type": "select", "options": [{"id": "准备", "name": "准备"}, {"id": "加工", "name": "加工"}, {"id": "装配", "name": "装配"}, {"id": "调试", "name": "调试"}, {"id": "已入库", "name": "已入库"}, {"id": "已发货", "name": "已发货"}], "value": machine.get("production_stage") if machine else "准备"},
                    {"name": "service_status", "label": "售后状态", "type": "select", "options": [{"id": "未安装", "name": "未安装"}, {"id": "安装中", "name": "安装中"}, {"id": "已验收", "name": "已验收"}, {"id": "保内", "name": "保内"}, {"id": "保外", "name": "保外"}], "value": machine.get("service_status") if machine else "未安装"},
                    {"name": "warranty_start_date", "label": "质保开始", "type": "date", "value": machine.get("warranty_start_date") if machine else ""},
                    {"name": "warranty_end_date", "label": "质保结束", "type": "date", "value": machine.get("warranty_end_date") if machine else ""},
                    {"name": "status", "label": "状态", "type": "select", "options": [{"id": "启用", "name": "启用"}, {"id": "停用", "name": "停用"}, {"id": "关闭", "name": "关闭"}], "value": machine.get("status") if machine else "启用"},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": machine.get("remark") if machine else ""},
                ],
            }
        ],
    )


def render_category_form(query_one, query_rows, kind, category_id=None):
    config = CATEGORY_TYPES.get(kind)
    if not config:
        return render_template("simple_detail.html", title="未知分类", row=None, back_url="/material", labels={})
    table = config["table"]
    record = _one(query_one, f"SELECT * FROM {table} WHERE id=%s", (category_id,)) if category_id else None
    return render_template(
        "operation_form.html",
        title=f"编辑{config['title']}" if record else f"新增{config['title']}",
        subtitle=config["subtitle"],
        back_url=config["back_url"],
        action_url=f"/categories/{kind}/{category_id}/edit" if record else f"/categories/{kind}/new",
        sections=[
            {
                "title": "分类信息",
                "fields": [
                    {"name": "code", "label": "编码", "value": record.get("code") if record else ""},
                    {"name": "name", "label": "名称", "required": True, "value": record.get("name") if record else ""},
                    {"name": "parent_id", "label": "上级分类", "type": "select", "options": _rows(query_rows, f"SELECT id, name FROM {table} ORDER BY name LIMIT 200"), "value": record.get("parent_id") if record else ""},
                    {"name": "remark", "label": "备注", "type": "textarea", "value": record.get("remark") if record else ""},
                ],
            }
        ],
    )
