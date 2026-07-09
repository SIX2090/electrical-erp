"""Organization master routes: department, employee, and organization list/form."""
from flask import render_template


ORG_NON_BUSINESS_MARKERS = (
    "test",
    "lifecycle",
    "测试部门",
    "测试员工",
)


def _filter_org_rows(rows, *fields):
    clean = []
    for row in rows or []:
        text = " ".join(str(row.get(field) or "").strip().lower() for field in fields)
        if any(marker in text for marker in ORG_NON_BUSINESS_MARKERS):
            continue
        clean.append(row)
    return clean


def _keyword_where(alias, fields, keyword):
    if not keyword:
        return "", []
    return "(" + " OR ".join(f"{alias}.{field} ILIKE %s" for field in fields) + ")", [f"%{keyword}%"] * len(fields)


def render_unit_dashboard(query_rows, query_one, count_rows, render_dashboard, columns, request_args, back_url="/unit"):
    keyword = (request_args.get("keyword") or request_args.get("q") or "").strip()
    where_parts = []
    params = []
    keyword_clause, keyword_params = _keyword_where("u", ["code", "name", "category"], keyword)
    if keyword_clause:
        where_parts.append(keyword_clause)
        params.extend(keyword_params)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    summary = query_one(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE COALESCE(category, '')='base' OR COALESCE(conversion_rate, 1)=1) AS base_count,
               COUNT(DISTINCT category) AS category_count,
               COUNT(*) FILTER (WHERE COALESCE(status, '启用') NOT IN ('停用','disabled')) AS active_count
        FROM units
        """
    ) or {}
    metrics = [
        {"label": "计量单位", "value": summary.get("total", 0), "hint": "档案总数"},
        {"label": "基本单位", "value": summary.get("base_count", 0), "hint": "基础换算单位"},
        {"label": "分类数", "value": summary.get("category_count", 0), "hint": "重量、长度、件数等"},
        {"label": "启用单位", "value": summary.get("active_count", 0), "hint": "可用于业务引用"},
    ]
    shortcuts = []
    rows = query_rows(
        f"""
        SELECT u.id, u.code, u.name, u.category, u.conversion_rate, u.status, u.remark,
               base.code AS base_code, base.name AS base_name,
               COALESCE(usage.product_count, 0) AS product_count
        FROM units u
        LEFT JOIN units base ON base.id=u.base_unit_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS product_count FROM products p WHERE p.unit=u.code OR p.unit=u.name
        ) usage ON TRUE
        {where_sql}
        ORDER BY u.code
        LIMIT 200
        """,
        tuple(params),
    )
    rows = _filter_org_rows(rows, "code", "name", "category", "remark")
    for row in rows:
        row["detail_url"] = f"/unit/{row.get('id')}"
        row["edit_url"] = f"/unit/{row.get('id')}/edit"
    return render_dashboard(
        "计量单位",
        "基础资料需要直接看到单位、换算和引用情况。",
        metrics,
        shortcuts,
        [
            {
                "title": "计量单位列表",
                "rows": rows,
                "columns": columns(("code", "编码"), ("name", "名称"), ("category", "分类"), ("status", "状态"), ("conversion_rate", "换算"), ("base_name", "基本单位"), ("product_count", "物料引用"), ("remark", "备注")),
                "detail_base": back_url,
                "detail_label": "单位详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/unit/new",
                "import_url": "/unit/import",
                "template_url": "/unit/download_template",
                "export_url": "/export/units",
            }
        ],
    )


def render_department_dashboard(query_rows, count_rows, render_dashboard, columns, request_args, back_url="/department"):
    keyword = (request_args.get("keyword") or request_args.get("q") or "").strip()
    where_parts = []
    params = []
    keyword_clause, keyword_params = _keyword_where("d", ["code", "name", "manager", "remark"], keyword)
    if keyword_clause:
        where_parts.append(keyword_clause)
        params.extend(keyword_params)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    metrics = [
        {"label": "部门数", "value": count_rows("departments"), "hint": "档案总数"},
        {"label": "员工数", "value": count_rows("employees"), "hint": "在册员工"},
        {"label": "顶层部门", "value": count_rows("departments", "parent_id IS NULL"), "hint": "无上级部门"},
        {"label": "启用部门", "value": count_rows("departments", "COALESCE(status,'启用') NOT IN ('停用','disabled')"), "hint": "可用于业务引用"},
    ]
    shortcuts = []
    rows = query_rows(
        f"""
        SELECT d.id, d.code, d.name, d.manager, d.phone, d.status, d.remark,
               parent.name AS parent_name,
               COALESCE(emp.employee_count, 0) AS employee_count
        FROM departments d
        LEFT JOIN departments parent ON parent.id=d.parent_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS employee_count FROM employees e WHERE e.dept_id=d.id
        ) emp ON TRUE
        {where_sql}
        ORDER BY parent.name NULLS FIRST, d.name
        LIMIT 200
        """,
        tuple(params),
    )
    rows = _filter_org_rows(rows, "code", "name", "manager", "phone", "remark")
    for row in rows:
        row["detail_url"] = f"/department/{row.get('id')}"
        row["edit_url"] = f"/department/{row.get('id')}/edit"
    return render_dashboard(
        "部门档案",
        "基础资料需要直接看到部门层级、主管和员工数。",
        metrics,
        shortcuts,
        [
            {
                "title": "部门列表",
                "rows": rows,
                "columns": columns(("code", "编码"), ("name", "部门"), ("parent_name", "上级"), ("status", "状态"), ("manager", "主管"), ("phone", "电话"), ("employee_count", "员工"), ("remark", "备注")),
                "detail_base": back_url,
                "detail_label": "部门详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/department/new",
                "import_url": "/department/import",
                "template_url": "/department/download_template",
                "export_url": "/export/departments",
            }
        ],
    )


def render_employee_dashboard(query_rows, count_rows, render_dashboard, columns, request_args, back_url="/employee"):
    keyword = (request_args.get("keyword") or request_args.get("q") or "").strip()
    department_id = (request_args.get("department_id") or "").strip()
    where_parts = []
    params = []
    keyword_clause, keyword_params = _keyword_where("e", ["code", "name", "position", "phone", "email"], keyword)
    if keyword_clause:
        where_parts.append(keyword_clause)
        params.extend(keyword_params)
    if department_id.isdigit():
        where_parts.append("e.dept_id=%s")
        params.append(int(department_id))
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    metrics = [
        {"label": "员工数", "value": count_rows("employees"), "hint": "档案总数"},
        {"label": "销售岗", "value": count_rows("employees", "COALESCE(is_sales,false)=true"), "hint": "参与销售流程"},
        {"label": "部门覆盖", "value": count_rows("employees", "dept_id IS NOT NULL"), "hint": "已分配部门"},
        {"label": "在职员工", "value": count_rows("employees", "COALESCE(status,'在职') NOT IN ('离职','停用','disabled')"), "hint": "可用于业务引用"},
    ]
    shortcuts = []
    rows = query_rows(
        f"""
        SELECT e.id, e.code, e.name, e.position, e.phone, e.email, e.status, e.employment_type, e.hire_date,
               d.name AS department_name,
               CASE WHEN COALESCE(e.is_sales, false) THEN '是' ELSE '否' END AS is_sales_label,
               e.standard_labor_rate_per_hour AS labor_rate
        FROM employees e
        LEFT JOIN departments d ON d.id=e.dept_id
        {where_sql}
        ORDER BY d.name NULLS LAST, e.name
        LIMIT 300
        """,
        tuple(params),
    )
    rows = _filter_org_rows(rows, "code", "name", "department_name", "position", "phone", "email")
    for row in rows:
        row["detail_url"] = f"/employee/{row.get('id')}"
        row["edit_url"] = f"/employee/{row.get('id')}/edit"
    return render_dashboard(
        "员工档案",
        "基础资料需要直接看到员工部门、岗位和联系方式。",
        metrics,
        shortcuts,
        [
            {
                "title": "员工列表",
                "rows": rows,
                "columns": columns(("code", "工号"), ("name", "姓名"), ("department_name", "部门"), ("status", "状态"), ("employment_type", "用工类型"), ("hire_date", "入职日期"), ("position", "岗位"), ("phone", "电话"), ("email", "邮箱"), ("is_sales_label", "销售岗"), ("labor_rate", "工时单价")),
                "detail_base": back_url,
                "detail_label": "员工详情",
                "edit_label": "编辑",
                "disable_table_tools": True,
                "add_url": "/employee/new",
                "import_url": "/employee/import",
                "template_url": "/employee/download_template",
                "export_url": "/export/employees",
            }
        ],
    )


def render_unit_detail(unit_id, query_one, query_rows, columns, back_url="/unit"):
    unit = query_one(
        """
        SELECT u.*, base.code AS base_code, base.name AS base_name
        FROM units u
        LEFT JOIN units base ON base.id=u.base_unit_id
        WHERE u.id=%s
        """,
        (unit_id,),
    )
    if not unit:
        return render_template("simple_detail.html", title="计量单位详情", row=None, back_url=back_url, labels={})
    products = query_rows(
        """
        SELECT id, code, name, specification, unit, status
        FROM products
        WHERE unit=%s OR unit=%s
        ORDER BY code
        LIMIT 80
        """,
        (unit.get("code"), unit.get("name")),
    )
    info_rows = [
        ("编码", unit.get("code")),
        ("名称", unit.get("name")),
        ("分类", unit.get("category")),
        ("状态", unit.get("status")),
        ("换算率", unit.get("conversion_rate")),
        ("基本单位", unit.get("base_name")),
        ("备注", unit.get("remark")),
    ]
    metrics = [
        {"label": "物料引用", "value": len(products), "hint": "按物料单位字段匹配"},
        {"label": "换算率", "value": unit.get("conversion_rate") or "-", "hint": "相对基本单位"},
        {"label": "状态", "value": unit.get("status") or "-", "hint": "启用/停用"},
        {"label": "基本单位", "value": unit.get("base_code") or "-", "hint": "换算基准"},
    ]
    sections = [
        {
            "title": "使用本单位的物料",
            "rows": products,
            "columns": columns(("code", "物料编码"), ("name", "物料名称"), ("specification", "规格"), ("unit", "单位"), ("status", "状态")),
            "detail_base": "/material",
        }
    ]
    return render_template(
        "basic_data_detail.html",
        title="计量单位详情",
        kind="unit",
        record=unit,
        record_name=f"{unit.get('code') or ''} {unit.get('name') or ''}".strip(),
        record_id=unit_id,
        back_url=back_url,
        edit_url=f"/unit/{unit_id}/edit",
        delete_url=f"/unit/{unit_id}/delete",
        info_rows=info_rows,
        metrics=metrics,
        sections=sections,
    )


def render_department_detail(department_id, query_one, query_rows, columns, back_url="/department"):
    department = query_one(
        """
        SELECT d.*, parent.name AS parent_name, parent.code AS parent_code
        FROM departments d
        LEFT JOIN departments parent ON parent.id=d.parent_id
        WHERE d.id=%s
        """,
        (department_id,),
    )
    if not department:
        return render_template("simple_detail.html", title="部门详情", row=None, back_url=back_url, labels={})
    employees = query_rows(
        """
        SELECT id, code, name, position, phone, email,
               status, employment_type, hire_date,
               CASE WHEN COALESCE(is_sales, false) THEN '是' ELSE '否' END AS is_sales_label
        FROM employees
        WHERE dept_id=%s
        ORDER BY name
        LIMIT 200
        """,
        (department_id,),
    )
    children = query_rows(
        """
        SELECT id, code, name, manager, phone, status, remark
        FROM departments
        WHERE parent_id=%s
        ORDER BY name
        LIMIT 100
        """,
        (department_id,),
    )
    info_rows = [
        ("编码", department.get("code")),
        ("名称", department.get("name")),
        ("上级部门", department.get("parent_name")),
        ("状态", department.get("status")),
        ("主管", department.get("manager")),
        ("电话", department.get("phone")),
        ("备注", department.get("remark")),
    ]
    metrics = [
        {"label": "员工数", "value": len(employees), "hint": "在本部门"},
        {"label": "下级部门", "value": len(children), "hint": "直属子部门"},
        {"label": "状态", "value": department.get("status") or "-", "hint": "启用/停用"},
        {"label": "电话", "value": department.get("phone") or "-", "hint": "联系电话"},
    ]
    sections = [
        {
            "title": "本部门员工",
            "rows": employees,
            "columns": columns(("code", "工号"), ("name", "姓名"), ("status", "状态"), ("employment_type", "用工类型"), ("hire_date", "入职日期"), ("position", "岗位"), ("phone", "电话"), ("email", "邮箱"), ("is_sales_label", "销售岗")),
            "detail_base": "/employee",
        },
        {
            "title": "下级部门",
            "rows": children,
            "columns": columns(("code", "编码"), ("name", "部门"), ("status", "状态"), ("manager", "主管"), ("phone", "电话"), ("remark", "备注")),
            "detail_base": back_url,
        },
    ]
    return render_template(
        "basic_data_detail.html",
        title="部门详情",
        kind="department",
        record=department,
        record_name=department.get("name") or "",
        record_id=department_id,
        back_url=back_url,
        edit_url=f"/department/{department_id}/edit",
        delete_url=f"/department/{department_id}/delete",
        info_rows=info_rows,
        metrics=metrics,
        sections=sections,
    )


def render_employee_detail(employee_id, query_one, query_rows, columns, back_url="/employee"):
    employee = query_one(
        """
        SELECT e.*, d.name AS department_name, d.code AS department_code
        FROM employees e
        LEFT JOIN departments d ON d.id=e.dept_id
        WHERE e.id=%s
        """,
        (employee_id,),
    )
    if not employee:
        return render_template("simple_detail.html", title="员工详情", row=None, back_url=back_url, labels={})
    info_rows = [
        ("工号", employee.get("code")),
        ("姓名", employee.get("name")),
        ("部门", employee.get("department_name")),
        ("状态", employee.get("status")),
        ("用工类型", employee.get("employment_type")),
        ("入职日期", employee.get("hire_date")),
        ("岗位", employee.get("position")),
        ("电话", employee.get("phone")),
        ("邮箱", employee.get("email")),
        ("销售岗", "是" if employee.get("is_sales") else "否"),
        ("工时单价", employee.get("standard_labor_rate_per_hour")),
        ("备注", employee.get("remark")),
    ]
    metrics = [
        {"label": "部门", "value": employee.get("department_name") or "-", "hint": "所属组织"},
        {"label": "状态", "value": employee.get("status") or "-", "hint": "在职/离职/停用"},
        {"label": "销售岗", "value": "是" if employee.get("is_sales") else "否", "hint": "是否参与销售流程"},
        {"label": "工时单价", "value": employee.get("standard_labor_rate_per_hour") or "-", "hint": "工单成本基础"},
    ]
    log_rows = query_rows(
        """
        SELECT id, action, target, remark, created_at
        FROM operation_logs
        WHERE username=%s OR username=%s
        ORDER BY id DESC LIMIT 50
        """,
        (employee.get("code") or "", employee.get("name") or ""),
    )
    sections = [
        {
            "title": "员工操作记录",
            "rows": log_rows,
            "columns": columns(("created_at", "时间"), ("action", "动作"), ("target", "对象"), ("remark", "备注")),
        }
    ]
    return render_template(
        "basic_data_detail.html",
        title="员工详情",
        kind="employee",
        record=employee,
        record_name=f"{employee.get('code') or ''} {employee.get('name') or ''}".strip(),
        record_id=employee_id,
        back_url=back_url,
        edit_url=f"/employee/{employee_id}/edit",
        delete_url=f"/employee/{employee_id}/delete",
        info_rows=info_rows,
        metrics=metrics,
        sections=sections,
    )
