"""System health routes: health check, monitoring dashboard, and security status."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from services.env_config import security_config_status


ROOT_DIR = Path(__file__).resolve().parents[1]
GO_LIVE_HEALTH_REPORT = ROOT_DIR / "reports" / "go_live_health_checks.json"


KEY_TABLES = [
    ("sales_orders", "销售订单"),
    ("work_orders", "生产工单"),
    ("boms", "BOM"),
    ("bom_items", "BOM子项"),
    ("products", "物料"),
    ("inventory_balances", "库存余额"),
    ("purchase_orders", "采购订单"),
    ("purchase_requisitions", "采购申请"),
    ("customer_receivables", "应收"),
    ("supplier_payables", "应付"),
    ("machine_service_cards", "服务档案"),
    ("machine_service_orders", "服务单"),
    ("machine_service_rmas", "RMA"),
]

SYSTEM_OPTION_CHECKS = [
    ("negative_stock_block", "禁止负库存"),
    ("allow_negative_stock", "允许负库存"),
    ("batch_serial_control", "批号/机号追溯"),
    ("document_approval_flow", "单据审批流"),
    ("require_project_serial", "项目号/机号规则"),
]


def _system_option_row(safe_rows, table_columns, key):
    try:
        columns = {row.get("column_name") for row in table_columns("system_options")}
    except Exception:
        columns = set()
    if {"option_key", "option_value"}.issubset(columns):
        rows = safe_rows(
            "SELECT option_key, option_value, updated_at FROM system_options WHERE option_key=%s LIMIT 1",
            (key,),
        )
        return dict(rows[0]) if rows else None
    if {"key", "value"}.issubset(columns):
        rows = safe_rows(
            "SELECT key AS option_key, value AS option_value, updated_at FROM system_options WHERE key=%s LIMIT 1",
            (key,),
        )
        return dict(rows[0]) if rows else None
    return None


ROUTE_CHECKS = [
    {"id": 1, "path": "/projects", "route_label": "项目/机号台账"},
    {"id": 2, "path": "/engineering/kitting", "route_label": "工程齐套"},
    {"id": 3, "path": "/procurement/suggestions", "route_label": "采购建议"},
    {"id": 4, "path": "/purchase_request", "route_label": "采购申请"},
    {"id": 5, "path": "/work-orders", "route_label": "生产工单"},
    {"id": 6, "path": "/finance/period-close", "route_label": "期间结账"},
    {"id": 7, "path": "/service-orders", "route_label": "服务单"},
    {"id": 8, "path": "/system/data-health", "route_label": "数据健康"},
]


def build_table_health_rows(count_rows, table_columns, has_table):
    return [
        {
            "id": idx + 1,
            "table_label": label,
            "row_count": count_rows(table),
            "column_count": len(table_columns(table)),
            "status": "存在" if has_table(table) else "缺失",
        }
        for idx, (table, label) in enumerate(KEY_TABLES)
    ]


def _health_count(safe_rows, sql):
    try:
        rows = safe_rows(sql)
    except Exception:
        return 0
    if not rows:
        return 0
    return int(rows[0].get("count") or 0)


def build_master_data_health_rows(safe_rows, has_table):
    checks = []

    def add(key, name, count, detail):
        checks.append(
            {
                "id": len(checks) + 1,
                "check_key": key,
                "check_name": name,
                "status": "通过" if count == 0 else "需处理",
                "finding_count": count,
                "detail": detail,
                "list_url": f"/system/data-health/master/{key}",
            }
        )

    if has_table("products"):
        add(
            "products_without_category",
            "无分类物料",
            _health_count(
                safe_rows,
                """
                SELECT COUNT(*) AS count
                FROM products
                WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
                  AND (category_id IS NULL OR COALESCE(category, '')='')
                """,
            ),
            "启用物料必须维护物料分类，便于采购、库存和成本归集。",
        )
        add(
            "products_without_unit",
            "无单位物料",
            _health_count(
                safe_rows,
                """
                SELECT COUNT(*) AS count
                FROM products
                WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
                  AND COALESCE(unit, '')=''
                """,
            ),
            "启用物料必须维护基本单位，避免单据数量口径不一致。",
        )
        add(
            "products_without_default_warehouse",
            "无默认仓库物料",
            _health_count(
                safe_rows,
                """
                SELECT COUNT(*) AS count
                FROM products
                WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
                  AND default_warehouse_id IS NULL
                """,
            ),
            "建议为常用物料维护默认仓库，采购、生产和库存单据可自动带出。",
        )
    if has_table("customers"):
        add(
            "customers_without_tax",
            "无税率客户",
            _health_count(
                safe_rows,
                """
                SELECT COUNT(*) AS count
                FROM customers
                WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
                  AND default_tax_rate IS NULL
                """,
            ),
            "客户默认税率用于销售订单、出库和应收口径带出。",
        )
    if has_table("suppliers"):
        add(
            "suppliers_without_settlement",
            "无结算条件供应商",
            _health_count(
                safe_rows,
                """
                SELECT COUNT(*) AS count
                FROM suppliers
                WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
                  AND settlement_term_id IS NULL
                """,
            ),
            "供应商结算条件用于采购订单、委外单和应付跟踪。",
        )
    if has_table("products") and has_table("purchase_order_items") and has_table("purchase_orders"):
        add(
            "disabled_products_open_purchase",
            "停用物料仍被未结单据引用",
            _health_count(
                safe_rows,
                """
                SELECT COUNT(DISTINCT p.id) AS count
                FROM products p
                JOIN purchase_order_items poi ON poi.product_id=p.id
                JOIN purchase_orders po ON po.id=poi.order_id
                WHERE COALESCE(p.status, '') IN ('停用','disabled','inactive')
                  AND COALESCE(po.status, '') NOT IN ('已关闭','已作废','closed','void','voided')
                """,
            ),
            "停用物料仍存在未结采购引用时，应先关闭或调整业务单据。",
        )
    if has_table("suppliers") and has_table("purchase_orders"):
        add(
            "disabled_suppliers_open_purchase",
            "停用供应商仍被未结采购引用",
            _health_count(
                safe_rows,
                """
                SELECT COUNT(DISTINCT s.id) AS count
                FROM suppliers s
                JOIN purchase_orders po ON po.supplier_id=s.id
                WHERE COALESCE(s.status, '') IN ('停用','disabled','inactive')
                  AND COALESCE(po.status, '') NOT IN ('已关闭','已作废','closed','void','voided')
                """,
            ),
            "停用供应商不能继续提交、审核或生成后续采购/委外业务。",
        )
    return checks


MASTER_HEALTH_DETAIL_CONFIGS = {
    "products_without_category": {
        "title": "无分类物料",
        "subtitle": "启用物料缺少分类会影响采购、库存、BOM和成本归集。",
        "sql": """
            SELECT id, code, name, specification, unit, status,
                   '/material/' || id || '/edit' AS detail_url
            FROM products
            WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
              AND (category_id IS NULL OR COALESCE(category, '')='')
            ORDER BY id DESC
            LIMIT 500
        """,
        "columns": (("code", "物料编码"), ("name", "物料名称"), ("specification", "规格型号"), ("unit", "单位"), ("status", "状态")),
    },
    "products_without_unit": {
        "title": "无单位物料",
        "subtitle": "启用物料缺少基本单位会造成单据数量口径不一致。",
        "sql": """
            SELECT id, code, name, specification, unit, status,
                   '/material/' || id || '/edit' AS detail_url
            FROM products
            WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
              AND COALESCE(unit, '')=''
            ORDER BY id DESC
            LIMIT 500
        """,
        "columns": (("code", "物料编码"), ("name", "物料名称"), ("specification", "规格型号"), ("unit", "单位"), ("status", "状态")),
    },
    "products_without_default_warehouse": {
        "title": "无默认仓库物料",
        "subtitle": "常用物料缺少默认仓库时，采购、生产和库存单据无法稳定带出仓库。",
        "sql": """
            SELECT p.id, p.code, p.name, p.specification, p.unit, p.status,
                   '/material/' || p.id || '/edit' AS detail_url
            FROM products p
            WHERE COALESCE(p.status, '启用') NOT IN ('停用','disabled','inactive')
              AND p.default_warehouse_id IS NULL
            ORDER BY p.id DESC
            LIMIT 500
        """,
        "columns": (("code", "物料编码"), ("name", "物料名称"), ("specification", "规格型号"), ("unit", "单位"), ("status", "状态")),
    },
    "customers_without_tax": {
        "title": "无税率客户",
        "subtitle": "客户默认税率用于销售订单、出库和应收口径带出。",
        "sql": """
            SELECT id, name, contact_person, phone, status,
                   '/customer/' || id || '/edit' AS detail_url
            FROM customers
            WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
              AND default_tax_rate IS NULL
            ORDER BY id DESC
            LIMIT 500
        """,
        "columns": (("name", "客户"), ("contact_person", "联系人"), ("phone", "电话"), ("status", "状态")),
    },
    "suppliers_without_settlement": {
        "title": "无结算条件供应商",
        "subtitle": "供应商结算条件用于采购订单、委外单和应付跟踪。",
        "sql": """
            SELECT id, name, contact_person, phone, status,
                   '/supplier/' || id || '/edit' AS detail_url
            FROM suppliers
            WHERE COALESCE(status, '启用') NOT IN ('停用','disabled','inactive')
              AND settlement_term_id IS NULL
            ORDER BY id DESC
            LIMIT 500
        """,
        "columns": (("name", "供应商"), ("contact_person", "联系人"), ("phone", "电话"), ("status", "状态")),
    },
    "disabled_products_open_purchase": {
        "title": "停用物料仍被未结采购引用",
        "subtitle": "先关闭或调整未结采购单据，再保持物料停用。",
        "sql": """
            SELECT DISTINCT p.id, p.code, p.name, p.specification, p.status,
                   '/material/' || p.id || '/edit' AS detail_url
            FROM products p
            JOIN purchase_order_items poi ON poi.product_id=p.id
            JOIN purchase_orders po ON po.id=poi.order_id
            WHERE COALESCE(p.status, '') IN ('停用','disabled','inactive')
              AND COALESCE(po.status, '') NOT IN ('已关闭','已作废','closed','void','voided')
            ORDER BY p.id DESC
            LIMIT 500
        """,
        "columns": (("code", "物料编码"), ("name", "物料名称"), ("specification", "规格型号"), ("status", "状态")),
    },
    "disabled_suppliers_open_purchase": {
        "title": "停用供应商仍被未结采购引用",
        "subtitle": "先关闭或调整未结采购单据，再保持供应商停用。",
        "sql": """
            SELECT DISTINCT s.id, s.name, s.contact_person, s.phone, s.status,
                   '/supplier/' || s.id || '/edit' AS detail_url
            FROM suppliers s
            JOIN purchase_orders po ON po.supplier_id=s.id
            WHERE COALESCE(s.status, '') IN ('停用','disabled','inactive')
              AND COALESCE(po.status, '') NOT IN ('已关闭','已作废','closed','void','voided')
            ORDER BY s.id DESC
            LIMIT 500
        """,
        "columns": (("name", "供应商"), ("contact_person", "联系人"), ("phone", "电话"), ("status", "状态")),
    },
}


def render_master_data_health_detail(check_key, safe_rows, columns, render_module_dashboard):
    config = MASTER_HEALTH_DETAIL_CONFIGS.get(check_key)
    if not config:
        rows = []
        title = "主数据健康明细"
        subtitle = "未知检查项。"
        detail_columns = columns(("check_key", "检查项"))
    else:
        rows = safe_rows(config["sql"])
        title = config["title"]
        subtitle = config["subtitle"]
        detail_columns = columns(*config["columns"])
    return render_module_dashboard(
        title,
        subtitle,
        [{"label": "问题数", "value": len(rows), "hint": "最多显示500条"}],
        [{"label": "返回数据健康", "url": "/system/data-health", "icon": "bi-arrow-left"}],
        [
            {
                "title": "待处理明细",
                "rows": rows,
                "columns": detail_columns,
                "detail_base": "use-detail-url",
                "empty_text": "暂无待处理记录。",
            }
        ],
    )


def _clean_row(row, clean_text, *keys):
    item = dict(row)
    for key in keys:
        item[key] = clean_text(item.get(key), "-")
    return item


def _latest_database_backup_row(next_id):
    backup_dir = ROOT_DIR / "backups"
    dumps = sorted(backup_dir.glob("*.dump"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not dumps:
        return {
            "id": next_id,
            "check_name": "database_backup",
            "status": "fail",
            "detail": "No database backup dump found.",
        }
    latest = dumps[0]
    modified_at = datetime.fromtimestamp(latest.stat().st_mtime)
    fresh = modified_at >= datetime.now() - timedelta(hours=24)
    return {
        "id": next_id,
        "check_name": "database_backup",
        "status": "pass" if fresh else "fail",
        "detail": f"Last backup: {modified_at:%Y-%m-%d %H:%M:%S}; file={latest.name}",
    }


def _go_live_health_rows():
    rows = [_latest_database_backup_row(1)]
    if GO_LIVE_HEALTH_REPORT.exists():
        try:
            payload = json.loads(GO_LIVE_HEALTH_REPORT.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append(
                {
                    "id": len(rows) + 1,
                    "check_name": "go_live_health_report",
                    "status": "fail",
                    "detail": f"Cannot read {GO_LIVE_HEALTH_REPORT.name}: {exc}",
                }
            )
            return rows
        for item in payload.get("checks", []):
            rows.append(
                {
                    "id": len(rows) + 1,
                    "check_name": item.get("check_name") or item.get("name") or "unknown_check",
                    "status": item.get("status") or "unknown",
                    "detail": item.get("detail") or item.get("summary") or "-",
                }
            )
    else:
        rows.append(
            {
                "id": len(rows) + 1,
                "check_name": "go_live_health_report",
                "status": "pending",
                "detail": "Run final verification to generate reports/go_live_health_checks.json.",
            }
        )
    return rows


def render_data_health_dashboard(
    render_module_dashboard,
    columns,
    safe_rows,
    count_rows,
    table_columns,
    has_table,
    database_health_rows,
    route_health_rows,
    recent_error_rows,
    backup_status,
    backup_rows,
    clean_text=None,
):
    clean_text = clean_text or (lambda value, fallback="-": value or fallback)
    table_rows = build_table_health_rows(count_rows, table_columns, has_table)
    master_health_rows = build_master_data_health_rows(safe_rows, has_table)
    raw_database_rows = database_health_rows()
    database_rows = [
        {
            "id": idx + 1,
            "check_name": clean_text(row.get("check_name") or "数据库连接", "数据库连接"),
            "status": clean_text(row.get("status"), "-"),
            "detail": "业务库连接正常" if row.get("status") == "正常" else "业务库连接异常，请查看服务器日志",
            "checked_at": row.get("checked_at"),
        }
        for idx, row in enumerate(raw_database_rows)
    ]
    route_rows = [_clean_row(row, clean_text, "route_label", "path", "status") for row in route_health_rows(ROUTE_CHECKS)]
    option_rows = []
    for idx, (key, label) in enumerate(SYSTEM_OPTION_CHECKS, start=1):
        try:
            item = _system_option_row(safe_rows, table_columns, key)
        except Exception:
            item = None
        item = item or {"option_key": key, "option_value": None, "updated_at": None}
        value = str(item.get("option_value") or "").strip()
        option_rows.append(
            {
                "id": idx,
                "option_label": label,
                "option_key": key,
                "option_value": value if value else "未设置",
                "status": "已启用" if value in {"1", "true", "on", "yes"} else ("已关闭" if value in {"0", "false", "off", "no"} else "未设置"),
                "updated_at": item.get("updated_at"),
            }
        )
    security_rows = [
        {
            "id": 1,
            "check_name": "PG_PASSWORD",
            "status": "需处理" if __import__("os").environ.get("PG_PASSWORD", "admin") in {"", "admin"} else "已配置",
            "detail": "数据库密码仍是默认值或未设置" if __import__("os").environ.get("PG_PASSWORD", "admin") in {"", "admin"} else "数据库密码已由环境变量配置",
        },
        {
            "id": 2,
            "check_name": "INVENTORY_SECRET_KEY",
            "status": "需处理" if not __import__("os").environ.get("INVENTORY_SECRET_KEY") else "已配置",
            "detail": "请在正式部署前设置随机密钥" if not __import__("os").environ.get("INVENTORY_SECRET_KEY") else "密钥已配置",
        },
        {
            "id": 3,
            "check_name": "角色权限矩阵",
            "status": "已登记",
            "detail": "通过 /permissions/roles 维护；上线前需按岗位复核销售、采购、仓库、生产、财务、售后权限。",
        },
    ]
    security_status = security_config_status()
    security_rows = [
        {
            "id": 1,
            "check_name": "运行模式",
            "status": security_status["mode_label"],
            "detail": "本地试用可使用本机生成密钥；正式上线必须由管理员保存真实数据库密码并设置生产密钥。",
        },
        {
            "id": 2,
            "check_name": "PG_PASSWORD",
            "status": "已配置" if security_status["pg_password_ready"] else "需处理",
            "detail": "已从本地运行环境读取数据库密码，页面不显示密钥值。" if security_status["pg_password_ready"] else "仍缺少有效数据库密码；本地可运行生成脚本，正式上线需保存真实数据库密码。",
        },
        {
            "id": 3,
            "check_name": "INVENTORY_SECRET_KEY",
            "status": "已配置" if security_status["secret_key_ready"] else "需处理",
            "detail": "已读取本地随机应用密钥，页面不显示密钥值。" if security_status["secret_key_ready"] else "仍缺少有效应用密钥；请生成本地密钥，正式上线前替换为生产密钥。",
        },
        {
            "id": 4,
            "check_name": "上线状态",
            "status": "可上线" if security_status["go_live_ready"] else ("本地试用" if security_status["local_bootstrapped"] else "需引导"),
            "detail": "当前是正式上线配置。" if security_status["go_live_ready"] else "当前未按正式生产环境判定；可用于本地试用，正式上线前必须复核数据库密码、密钥保存、备份和权限。",
        },
        {
            "id": 5,
            "check_name": "角色权限矩阵",
            "status": "已登记",
            "detail": "通过 /permissions/roles 维护；上线前需按岗位复核销售、采购、仓库、生产、财务、售后权限。",
        },
    ]
    error_rows = [
        {
            "id": idx + 1,
            "log_area": "应用日志",
            "modified_time": row.get("modified_time"),
            "message": clean_text(row.get("message"), "-"),
        }
        for idx, row in enumerate(recent_error_rows())
    ]
    go_live_health_rows = _go_live_health_rows()
    backups = backup_status()
    backup_summary_rows = []
    for idx, row in enumerate(backup_rows(12)):
        backup_summary_rows.append(
            {
                "id": idx + 1,
                "backup_type": "数据库备份" if str(row.get("file_name", "")).lower().endswith(".dump") else "源码备份",
                "size_mb": row.get("size_mb"),
                "modified_time": row.get("modified_time"),
            }
        )
    logs = [
        _clean_row(row, clean_text, "username", "action", "target")
        for row in safe_rows(
            """
            SELECT id, username, action, target, created_at
            FROM operation_logs
            ORDER BY id DESC
            LIMIT 30
            """
        )
    ]

    metrics = [
        {"label": "数据库", "value": database_rows[0]["status"] if database_rows else "-", "hint": "业务库"},
        {"label": "关键表", "value": len(table_rows), "hint": "当前自检范围"},
        {"label": "数据备份", "value": backups["db_count"], "hint": "最近备份已汇总"},
        {"label": "源码备份", "value": backups["source_count"], "hint": "最近备份已汇总"},
        {"label": "核心入口", "value": sum(1 for row in route_rows if row["status"] == "已注册"), "hint": f"共 {len(route_rows)} 个主路径"},
    ]
    shortcuts = [
        {"label": "系统设置", "url": "/system_settings/form", "icon": "bi-gear"},
        {"label": "操作日志", "url": "/operation_logs", "icon": "bi-clock-history"},
        {"label": "项目台账", "url": "/projects", "icon": "bi-kanban"},
    ]
    return render_module_dashboard(
        "数据健康",
        "每日自检关键表、核心入口、备份文件和最近操作日志。",
        metrics,
        shortcuts,
        [
            {
                "title": "系统安全与权限检查",
                "rows": security_rows,
                "columns": columns(("check_name", "检查项"), ("status", "状态"), ("detail", "说明")),
            },
            {
                "title": "业务控制开关",
                "rows": option_rows,
                "columns": columns(("option_label", "功能"), ("option_key", "参数键"), ("option_value", "当前值"), ("status", "状态"), ("updated_at", "更新时间")),
            },
            {
                "title": "数据库连接",
                "rows": database_rows,
                "columns": columns(("check_name", "检查项"), ("status", "状态"), ("detail", "说明"), ("checked_at", "检查时间")),
            },
            {
                "title": "关键数据表",
                "rows": table_rows,
                "columns": columns(("table_label", "业务对象"), ("row_count", "记录数"), ("column_count", "字段数"), ("status", "状态")),
            },
            {
                "title": "主数据健康检查",
                "rows": master_health_rows,
                "columns": columns(("check_name", "检查项"), ("status", "状态"), ("finding_count", "问题数"), ("detail", "说明"), ("list_url", "处理")),
            },
            {
                "title": "核心入口",
                "rows": route_rows,
                "columns": columns(("route_label", "入口"), ("path", "路径"), ("status", "状态")),
            },
            {
                "title": "Go-live closure checks",
                "rows": go_live_health_rows,
                "columns": columns(("check_name", "\u68c0\u67e5\u9879"), ("status", "\u72b6\u6001"), ("detail", "\u8be6\u60c5")),
            },
            {
                "title": "最近备份文件",
                "rows": backup_summary_rows,
                "columns": columns(("backup_type", "备份类型"), ("size_mb", "大小MB"), ("modified_time", "备份时间")),
            },
            {
                "title": "最近错误日志",
                "rows": error_rows,
                "columns": columns(("log_area", "日志范围"), ("modified_time", "修改时间"), ("message", "错误摘要")),
            },
            {
                "title": "最近操作日志",
                "rows": logs,
                "columns": columns(("username", "用户"), ("action", "动作"), ("target", "对象"), ("created_at", "时间")),
            },
        ],
    )
