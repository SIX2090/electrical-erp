"""Import page helpers: render CSV import pages and process uploaded files."""
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from flask import flash, redirect, render_template


CsvResponseFactory = Callable[[Sequence[Mapping[str, str]], str], Any]
RenderTemplate = Callable[..., Any]
Redirect = Callable[[str], Any]
Flash = Callable[[str, str], None]


MATERIAL_IMPORT_COLUMNS = [
    "\u7269\u6599\u7f16\u7801",
    "\u7269\u6599\u540d\u79f0",
    "\u89c4\u683c\u578b\u53f7",
    "\u57fa\u672c\u5355\u4f4d",
    "\u7269\u6599\u5206\u7c7b\u540d\u79f0",
    "\u56fe\u53f7",
    "\u6750\u8d28",
    "\u54c1\u724c",
    "\u6807\u51c6\u4ef7",
    "\u5b89\u5168\u5e93\u5b58",
    "\u9ed8\u8ba4\u4f9b\u5e94\u5546",
    "\u9ed8\u8ba4\u7a0e\u7387",
    "\u4f7f\u7528\u72b6\u6001",
]


def render_material_import_page(
    precheck_report: Mapping[str, Any] | None = None,
    render: RenderTemplate = render_template,
) -> Any:
    return render("material_import.html", precheck_report=precheck_report)


def material_import_template_response(csv_response: CsvResponseFactory) -> Any:
    sample = {
        "\u7269\u6599\u7f16\u7801": "MAT-001",
        "\u7269\u6599\u540d\u79f0": "\u793a\u4f8b\u7269\u6599",
        "\u89c4\u683c\u578b\u53f7": "M8x20",
        "\u57fa\u672c\u5355\u4f4d": "PCS",
        "\u7269\u6599\u5206\u7c7b\u540d\u79f0": "\u539f\u6750\u6599",
        "\u56fe\u53f7": "DRW-001",
        "\u6750\u8d28": "45#",
        "\u54c1\u724c": "",
        "\u6807\u51c6\u4ef7": "0",
        "\u5b89\u5168\u5e93\u5b58": "0",
        "\u9ed8\u8ba4\u4f9b\u5e94\u5546": "",
        "\u9ed8\u8ba4\u7a0e\u7387": "13",
        "\u4f7f\u7528\u72b6\u6001": "\u542f\u7528",
    }
    return csv_response([sample], "material_import_template")


BASIC_IMPORT_CONFIGS = {
    "customer": {
        "label": "\u5ba2\u6237\u6863\u6848",
        "table": "customers",
        "back_url": "/customer",
        "import_url": "/customer/import",
        "template_url": "/customer/download_template",
        "key": "name",
        "columns": [
            ("\u5ba2\u6237\u540d\u79f0", "name", True),
            ("\u8054\u7cfb\u4eba", "contact_person", False),
            ("\u7535\u8bdd", "phone", False),
            ("\u5730\u5740", "address", False),
            ("\u5ba2\u6237\u7b49\u7ea7", "customer_level", False),
            ("\u4fe1\u7528\u989d\u5ea6", "credit_limit", False),
            ("\u5907\u6ce8", "remark", False),
            ("\u5ba2\u6237\u5206\u7c7bID", "category_id", False),
            ("\u7a0e\u53f7", "tax_no", False),
            ("\u5f00\u7968\u62ac\u5934", "invoice_title", False),
            ("\u9ed8\u8ba4\u7a0e\u7387", "default_tax_rate", False),
            ("\u7ed3\u7b97\u671f\u9650ID", "settlement_term_id", False),
            ("\u6536\u6b3e\u6761\u4ef6ID", "payment_term_id", False),
            ("\u72b6\u6001", "status", False),
        ],
    },
    "supplier": {
        "label": "\u4f9b\u5e94\u5546\u6863\u6848",
        "table": "suppliers",
        "back_url": "/supplier",
        "import_url": "/supplier/import",
        "template_url": "/supplier/download_template",
        "key": "name",
        "columns": [
            ("\u4f9b\u5e94\u5546\u540d\u79f0", "name", True),
            ("\u8054\u7cfb\u4eba", "contact_person", False),
            ("\u7535\u8bdd", "phone", False),
            ("\u5730\u5740", "address", False),
            ("\u4ea4\u8d27\u5929\u6570", "lead_time_days", False),
            ("\u5907\u6ce8", "remark", False),
            ("\u4f9b\u5e94\u5546\u5206\u7c7bID", "category_id", False),
            ("\u7a0e\u53f7", "tax_no", False),
            ("\u5f00\u7968\u62ac\u5934", "invoice_title", False),
            ("\u9ed8\u8ba4\u7a0e\u7387", "default_tax_rate", False),
            ("\u7ed3\u7b97\u671f\u9650ID", "settlement_term_id", False),
            ("\u4ed8\u6b3e\u6761\u4ef6ID", "payment_term_id", False),
            ("\u662f\u5426\u59d4\u5916\u52a0\u5de5\u5546", "is_outsourced_processor", False),
            ("\u72b6\u6001", "status", False),
        ],
    },
    "warehouse": {
        "label": "\u4ed3\u5e93\u6863\u6848",
        "table": "warehouses",
        "back_url": "/warehouse",
        "import_url": "/warehouse/import",
        "template_url": "/warehouse/download_template",
        "key": "code",
        "columns": [
            ("\u4ed3\u5e93\u7f16\u7801", "code", True),
            ("\u4ed3\u5e93\u540d\u79f0", "name", True),
            ("\u5907\u6ce8", "remark", False),
            ("\u4ed3\u5e93\u5206\u7c7bID", "category_id", False),
            ("\u4ed3\u5e93\u7c7b\u578b", "warehouse_type", False),
            ("\u9ed8\u8ba4\u5e93\u4f4dID", "default_location_id", False),
            ("\u72b6\u6001", "status", False),
        ],
    },
    "location": {
        "label": "\u5e93\u4f4d\u6863\u6848",
        "table": "locations",
        "back_url": "/locations",
        "import_url": "/location/import",
        "template_url": "/location/download_template",
        "key": "code",
        "columns": [
            ("\u5e93\u4f4d\u7f16\u7801", "code", True),
            ("\u5e93\u4f4d\u540d\u79f0", "name", True),
            ("\u6240\u5c5e\u4ed3\u5e93\u7f16\u7801", "warehouse_code", False),
            ("\u6240\u5c5e\u4ed3\u5e93\u540d\u79f0", "warehouse_name", False),
            ("\u662f\u5426\u542f\u7528", "is_active", False),
            ("\u5907\u6ce8", "remark", False),
            ("\u5e93\u4f4d\u7c7b\u578b", "location_type", False),
            ("\u72b6\u6001", "status", False),
        ],
    },
    "unit": {
        "label": "\u8ba1\u91cf\u5355\u4f4d",
        "table": "units",
        "back_url": "/unit",
        "import_url": "/unit/import",
        "template_url": "/unit/download_template",
        "key": "code",
        "columns": [
            ("\u5355\u4f4d\u7f16\u7801", "code", True),
            ("\u5355\u4f4d\u540d\u79f0", "name", True),
            ("\u5206\u7c7b", "category", False),
            ("\u6362\u7b97\u7387", "conversion_rate", False),
            ("\u57fa\u672c\u5355\u4f4d\u7f16\u7801", "base_unit_code", False),
            ("\u5907\u6ce8", "remark", False),
            ("\u72b6\u6001", "status", False),
        ],
    },
    "department": {
        "label": "\u90e8\u95e8\u6863\u6848",
        "table": "departments",
        "back_url": "/department",
        "import_url": "/department/import",
        "template_url": "/department/download_template",
        "key": "name",
        "columns": [
            ("\u90e8\u95e8\u7f16\u7801", "code", False),
            ("\u90e8\u95e8\u540d\u79f0", "name", True),
            ("\u4e0a\u7ea7\u90e8\u95e8\u540d\u79f0", "parent_name", False),
            ("\u4e3b\u7ba1", "manager", False),
            ("\u7535\u8bdd", "phone", False),
            ("\u5907\u6ce8", "remark", False),
            ("\u72b6\u6001", "status", False),
        ],
    },
    "employee": {
        "label": "\u5458\u5de5\u6863\u6848",
        "table": "employees",
        "back_url": "/employee",
        "import_url": "/employee/import",
        "template_url": "/employee/download_template",
        "key": "code",
        "columns": [
            ("\u5de5\u53f7", "code", True),
            ("\u59d3\u540d", "name", True),
            ("\u90e8\u95e8\u540d\u79f0", "department_name", False),
            ("\u5c97\u4f4d", "position", False),
            ("\u7535\u8bdd", "phone", False),
            ("\u90ae\u7bb1", "email", False),
            ("\u662f\u5426\u9500\u552e", "is_sales", False),
            ("\u5de5\u65f6\u5355\u4ef7", "standard_labor_rate_per_hour", False),
            ("\u5907\u6ce8", "remark", False),
            ("\u72b6\u6001", "status", False),
            ("\u7528\u5de5\u7c7b\u578b", "employment_type", False),
            ("\u5165\u804c\u65e5\u671f", "hire_date", False),
        ],
    },
    "project": {
        "label": "\u9879\u76ee\u6863\u6848",
        "table": "project_masters",
        "back_url": "/project-master",
        "import_url": "/project-master/import",
        "template_url": "/project-master/download_template",
        "key": "project_code",
        "columns": [
            ("\u9879\u76ee\u53f7", "project_code", True),
            ("\u9879\u76ee\u540d\u79f0", "project_name", False),
            ("\u5ba2\u6237\u540d\u79f0", "customer_name", False),
            ("\u4ea7\u54c1\u65cf", "product_family", False),
            ("\u673a\u578b", "machine_model", False),
            ("\u6765\u6e90\u9500\u552e/\u5408\u540c\u53f7", "source_order_no", False),
            ("\u8d1f\u8d23\u4eba", "owner_name", False),
            ("\u8ba1\u5212\u4ea4\u671f", "planned_delivery_date", False),
            ("\u72b6\u6001", "status", False),
            ("\u5907\u6ce8", "remark", False),
        ],
    },
    "cabinet": {
        "label": "\u673a\u53f7\u6863\u6848",
        "table": "cabinet_masters",
        "back_url": "/cabinet-master",
        "import_url": "/cabinet-master/import",
        "template_url": "/cabinet-master/download_template",
        "key": "cabinet_no",
        "columns": [
            ("\u673a\u53f7", "cabinet_no", True),
            ("\u6240\u5c5e\u9879\u76ee\u53f7", "project_code", False),
            ("\u5ba2\u6237\u540d\u79f0", "customer_name", False),
            ("\u6210\u54c1\u7269\u6599\u7f16\u7801", "product_code", False),
            ("\u4ea7\u54c1\u65cf", "product_family", False),
            ("\u673a\u578b", "machine_model", False),
            ("\u751f\u4ea7\u9636\u6bb5", "production_stage", False),
            ("\u552e\u540e\u72b6\u6001", "service_status", False),
            ("\u8d28\u4fdd\u5f00\u59cb", "warranty_start_date", False),
            ("\u8d28\u4fdd\u7ed3\u675f", "warranty_end_date", False),
            ("\u72b6\u6001", "status", False),
            ("\u5907\u6ce8", "remark", False),
        ],
    },
}


def basic_import_template_response(
    kind: str,
    configs: Mapping[str, Mapping[str, Any]],
    csv_response: CsvResponseFactory,
    flash_message: Flash = flash,
    redirect_to: Redirect = redirect,
) -> Any:
    config = configs.get(kind)
    if not config:
        flash_message("\u672a\u77e5\u5bfc\u5165\u7c7b\u578b\u3002", "warning")
        return redirect_to("/material")

    sample = {}
    for label, column, _required in config["columns"]:
        if column == "code":
            sample[label] = f"{kind.upper()}-001"
        elif column == "name":
            sample[label] = f"\u793a\u4f8b{config['label']}"
        elif column in {"credit_limit", "conversion_rate", "standard_labor_rate_per_hour"}:
            sample[label] = "0"
        elif column == "default_tax_rate":
            sample[label] = "13"
        elif column == "lead_time_days":
            sample[label] = "7"
        elif column in {"is_sales", "is_active"}:
            sample[label] = "\u5426"
        elif column == "is_outsourced_processor":
            sample[label] = "false"
        elif column in {"status"}:
            sample[label] = "\u5728\u804c" if kind == "employee" else "\u542f\u7528"
        elif column in {"planned_delivery_date", "hire_date"}:
            sample[label] = "2026-12-31"
        elif column in {"warehouse_type"}:
            sample[label] = "\u6210\u54c1\u4ed3"
        elif column in {"location_type"}:
            sample[label] = "\u666e\u901a\u5e93\u4f4d"
        elif column in {"employment_type"}:
            sample[label] = "\u6b63\u5f0f"
        else:
            sample[label] = ""
    return csv_response([sample], f"{kind}_import_template")


def render_basic_import_page(
    kind: str,
    configs: Mapping[str, Mapping[str, Any]],
    precheck_report: Mapping[str, Any] | None = None,
    render: RenderTemplate = render_template,
    redirect_to: Redirect = redirect,
) -> Any:
    config = configs.get(kind)
    if not config:
        return redirect_to("/material")
    return render(
        "basic_import.html",
        title=f"{config['label']}\u5bfc\u5165",
        subtitle=f"\u6279\u91cf\u65b0\u589e\u6216\u66f4\u65b0{config['label']}\u3002",
        back_url=config["back_url"],
        import_url=config["import_url"],
        template_url=config["template_url"],
        columns=[label for label, _column, _required in config["columns"]],
        precheck_report=precheck_report,
    )


def category_import_template_response(
    kind: str,
    category_types: Mapping[str, Mapping[str, Any]],
    csv_response: CsvResponseFactory,
    redirect_to: Redirect = redirect,
) -> Any:
    config = category_types.get(kind)
    if not config:
        return redirect_to("/material")
    return csv_response(
        [
            {
                "\u5206\u7c7b\u7f16\u7801": f"{kind.upper()}-001",
                "\u5206\u7c7b\u540d\u79f0": f"\u793a\u4f8b{config['title']}",
                "\u4e0a\u7ea7\u5206\u7c7b\u7f16\u7801": "",
                "\u4e0a\u7ea7\u5206\u7c7b\u540d\u79f0": "",
                "\u5907\u6ce8": "",
            }
        ],
        f"{kind}_category_import_template",
    )


def render_category_import_page(
    kind: str,
    category_types: Mapping[str, Mapping[str, Any]],
    render: RenderTemplate = render_template,
    redirect_to: Redirect = redirect,
) -> Any:
    config = category_types.get(kind)
    if not config:
        return redirect_to("/material")
    return render(
        "basic_import.html",
        title=f"{config['title']}\u5bfc\u5165",
        subtitle=f"\u6279\u91cf\u65b0\u589e\u6216\u66f4\u65b0{config['title']}\u3002",
        back_url=config["back_url"],
        import_url=f"/categories/{kind}/import",
        template_url=f"/categories/{kind}/download_template",
        columns=["\u5206\u7c7b\u7f16\u7801", "\u5206\u7c7b\u540d\u79f0", "\u4e0a\u7ea7\u5206\u7c7b\u7f16\u7801", "\u4e0a\u7ea7\u5206\u7c7b\u540d\u79f0", "\u5907\u6ce8"],
    )
