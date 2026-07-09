# Code Wiki — 数控机床制造业 ERP

> 本文档是对 `c:\erp` 项目的结构化代码百科，涵盖整体架构、模块职责、关键类与函数、依赖关系及运行方式。

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [项目目录结构](#3-项目目录结构)
4. [整体架构](#4-整体架构)
5. [应用入口与启动流程](#5-应用入口与启动流程)
6. [核心服务层 (services/)](#6-核心服务层-services)
7. [路由层 (routes/)](#7-路由层-routes)
8. [模板与前端 (templates/ & static/)](#8-模板与前端-templates--static)
9. [数据库与 Schema 迁移](#9-数据库与-schema-迁移)
10. [权限与安全体系](#10-权限与安全体系)
11. [业务模块详解](#11-业务模块详解)
12. [脚本与审计工具 (scripts/)](#12-脚本与审计工具-scripts)
13. [项目运行方式](#13-项目运行方式)
14. [验证与审计流程](#14-验证与审计流程)

---

## 1. 项目概述

本项目是一套面向**机床与专用设备制造业**的 ERP 系统，以 **项目号 / 机号** 为核心追溯主线，贯穿销售、BOM、采购、库存、委外、工单、装配、调试、发货、售后、应收应付及成本报表的完整业务闭环。

**行业定位**：参考达易隆（Digiwin）风格制造业 ERP，产品族包括滚筒研磨机、双头铣床、铣磨复合机、瓦楞辊专用磨床、粗框机、精铣机、龙门铣等。

**核心设计原则**：
- 构建业务闭环，而非孤立页面
- 单据录入页与列表/查询/工作台页严格分离
- 财务记录仅由指定过账服务写入，禁止在路由中直接操作财务表
- 所有 DDL 变更必须先写入 `services/schema_migrations.py`

---

## 2. 技术栈与依赖

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.x | 运行时语言 |
| Flask | 3.1.3 | Web 框架 |
| Werkzeug | 3.1.8 | WSGI 工具库（密码哈希等） |
| Flask-WTF | 1.3.0 | CSRF 保护 |
| psycopg2-binary | 2.9.12 | PostgreSQL 驱动 |
| SQLAlchemy | 2.0.49 | ORM（主要用于 Alembic） |
| Alembic | 1.18.4 | 数据库迁移工具 |
| Waitress | 3.0.2 | 生产级 WSGI 服务器 |
| psutil | 7.2.2 | 系统监控 |
| openpyxl | 3.1.5 | Excel 导入导出 |
| qrcode[pil] | 8.2 | 二维码生成 |

### 前端

| 技术 | 用途 |
|------|------|
| Bootstrap 5.3.0 | UI 框架 |
| Bootstrap Icons 1.10.0 | 图标库 |
| Jinja2 | 模板引擎（Flask 内置） |
| 原生 JavaScript | 交互逻辑（[static/js/app.js](file:///c:/erp/static/js/app.js)） |

### 数据库

| 技术 | 用途 |
|------|------|
| PostgreSQL 18 | 主数据库（内嵌于 Windows 部署包） |

### 测试

| 技术 | 用途 |
|------|------|
| pytest | 测试框架 |
| pytest-playwright | 端到端浏览器测试 |

依赖清单见 [requirements.txt](file:///c:/erp/requirements.txt)。

---

## 3. 项目目录结构

```
c:\erp/
├── app.py                      # Flask 应用工厂入口
├── config.py                   # 数据库配置（从环境变量读取）
├── waitress_server.py          # 生产 WSGI 启动脚本
├── autorun.py                  # 自动修复脚本执行器
├── requirements.txt            # Python 依赖清单
├── pytest.ini                  # 测试配置
├── alembic.ini                 # Alembic 迁移配置
├── .env.example                # 环境变量模板
├── start.cmd                   # Windows 启动脚本
├── restart_erp.cmd             # 重启脚本
├── runtime_env.cmd             # 运行时环境变量加载
├── Build-Installer.ps1         # 安装包构建脚本
├── run_inventory_fix.py        # 库存修复脚本
├── run_schema_update.py        # Schema 更新脚本
│
├── routes/                     # 路由层（~100 个文件）
├── services/                   # 服务/业务逻辑层（~50 个文件）
├── templates/                  # Jinja2 模板（200+ 文件）
├── static/                     # 静态资源（CSS/JS/CDN 缓存）
├── scripts/                    # 审计/运维/修复脚本（150+ 文件）
├── alembic/                    # Alembic 迁移环境
├── docs/                       # 财务模块开发文档
├── memory/                     # 项目记忆（FACT.md, JOURNAL.jsonl）
├── pgdata/                     # PostgreSQL 数据目录
├── db/                         # 数据库 dump 文件
└── .venv/                      # Python 虚拟环境
```

---

## 4. 整体架构

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    浏览器 (Bootstrap 5 UI)                │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│                  Flask 应用 (app.py)                      │
│  ┌─────────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │  请求拦截器  │ │ CSRF保护 │ │ 全局操作工具栏/审计日志 │ │
│  └─────────────┘ └──────────┘ └───────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              路由层 (routes/)                         │ │
│  │  注册函数模式: register_routes(app, deps)            │ │
│  │  依赖注入: query_db, execute_db, login_required...   │ │
│  └────────────────────────┬────────────────────────────┘ │
│  ┌────────────────────────▼────────────────────────────┐ │
│  │              服务层 (services/)                      │ │
│  │  纯业务逻辑, 接收 db helper 函数作为参数              │ │
│  └────────────────────────┬────────────────────────────┘ │
│  ┌────────────────────────▼────────────────────────────┐ │
│  │           数据库辅助层 (app_runtime.py)              │ │
│  │  create_db_helpers → get_db / query_db / execute_db  │ │
│  └────────────────────────┬────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────┘
                            │ psycopg2
┌───────────────────────────▼─────────────────────────────┐
│                   PostgreSQL 18                           │
│  Schema 迁移: services/schema_migrations.py (82 条迁移)  │
└─────────────────────────────────────────────────────────┘
```

### 4.2 依赖注入模式

项目采用**函数式依赖注入**，而非传统的类继承或全局单例。核心模式如下：

1. `create_app()` 在 [app.py](file:///c:/erp/app.py) 中创建 Flask 实例
2. 通过 `create_db_helpers()` 生成 `query_db`、`execute_db` 等数据库操作函数
3. 将这些函数连同 `login_required`、`log_action` 等封装为 `deps` 字典
4. 各路由模块的 `register_routes(app, deps)` 函数接收 `deps` 并注册路由

```python
# app.py 中的依赖注入示例
register_finance_routes(app, {
    "query_db": query_db,
    "execute_db": execute_db,
    "execute_and_return": execute_and_return,
    "next_doc_no": next_doc_no,
    "log_action": log_action,
    "login_required": login_required,
})
```

### 4.3 请求处理流水线

每个请求经过以下处理链：

1. **`enforce_high_risk_access_controls`**（before_request）— 高风险路径的角色权限校验
2. **`login_required`** 装饰器 — 登录状态检查
3. **路由处理函数** — 业务逻辑
4. **`add_security_headers`**（after_request）— 添加安全响应头
5. **`record_audit_log`**（after_request）— 记录 POST/PUT/DELETE 操作审计日志

---

## 5. 应用入口与启动流程

### 5.1 入口文件

| 文件 | 用途 |
|------|------|
| [app.py](file:///c:/erp/app.py) | Flask 应用工厂 `create_app()`，开发模式入口 |
| [waitress_server.py](file:///c:/erp/waitress_server.py) | 生产 WSGI 启动入口（Waitress） |
| [start.cmd](file:///c:/erp/start.cmd) | Windows 一键启动脚本 |

### 5.2 `create_app()` 核心流程

[app.py](file:///c:/erp/app.py) 中的 `create_app(config=None)` 函数执行以下步骤：

1. **创建 Flask 实例**，配置 JSON 编码为 UTF-8
2. **安全配置**：读取 `INVENTORY_SECRET_KEY`、设置 Cookie 安全策略、启用 CSRF
3. **注册上下文处理器**：注入 `current_user`、`nav_mode` 等全局模板变量
4. **创建数据库辅助函数**：`create_db_helpers()` 返回 `get_db`、`query_db`、`execute_db`、`execute_and_return`
5. **执行 Schema 迁移**：`apply_schema_migrations(cur)` 确保数据库结构最新
6. **初始化安全组件**：
   - `FixedWindowRateLimiter` — 登录速率限制
   - `LoginAttemptTracker` — 登录失败追踪与账户锁定
7. **定义核心辅助函数**：`normalize_role`、`log_action`、`next_doc_no`、`ensure_inventory` 等
8. **注册所有路由模块**（见下方路由注册表）
9. **注册 Blueprint**：通知、安全管理、系统监控

### 5.3 路由注册顺序

```python
register_help_routes(app, ...)              # 帮助文档
register_app_shell_routes(app, ...)         # 首页/登录/导航外壳
register_core_operations_routes(app, ...)   # 核心操作（委托给 registry）
register_system_management_routes(app, ...) # 系统管理
register_print_template_routes(app, ...)    # 打印模板
bind_route_dependencies(...)                # 绑定共享依赖
register_api_routes(app, ...)               # API 路由
register_finance_routes(app, ...)           # 财务模块
register_project_cost_routes(app, ...)      # 项目成本
register_project_delivery_workbench_routes  # 项目交付工作台
register_attachment_routes(app, ...)        # 附件管理
register_sales_report_routes(app, ...)      # 销售报表
register_invoice_matching_routes(...)       # 发票三单匹配
register_invoice_red_flush_routes(...)      # 发票红冲
register_invoice_reconciliation_routes(...) # 发票勾稽
register_inventory_costing_routes(...)      # 存货核算
register_serial_cost_routes(...)            # 机号成本
register_period_closing_routes(...)         # 期末结账
register_financial_report_routes(...)       # 财务报表
register_blueprints(app)                    # registry 中的 Blueprint
# + notification_bp, security_bp, monitoring_bp
```

### 5.4 角色体系

系统定义 9 种角色（见 [services/app_runtime.py](file:///c:/erp/services/app_runtime.py) `ROLE_LABELS`）：

| 角色标识 | 中文标签 | 说明 |
|----------|----------|------|
| `admin` | 系统管理员 | 全部权限 |
| `manager` | 经理 | 管理权限，可绕过数据范围限制 |
| `sales` | 销售 | 销售模块 |
| `purchase` | 采购 | 采购/委外模块 |
| `warehouse` | 仓库 | 库存模块 |
| `production` | 生产 | 生产模块 |
| `service` | 售后 | 售后服务模块 |
| `finance` | 财务 | 财务模块 |
| `staff` | 员工 | 基础操作权限 |

角色别名映射（支持中英文）定义在 [app.py](file:///c:/erp/app.py) 的 `ROLE_ALIASES` 字典中，`normalize_role()` 函数负责统一化。

---

## 6. 核心服务层 (services/)

服务层包含纯业务逻辑，所有数据库操作通过传入的 `query_db` / `execute_db` 函数完成，不直接持有数据库连接。

### 6.1 基础设施服务

#### [services/app_runtime.py](file:///c:/erp/services/app_runtime.py) — 应用运行时核心

| 函数/类 | 职责 |
|---------|------|
| `connect_db(db_config, cursor_factory)` | 创建 PostgreSQL 连接，强制 UTF-8 编码 |
| `create_db_helpers(app, db_config)` | 创建 `get_db`、`query_db`、`execute_db`、`execute_and_return` 四个数据库辅助函数，并在请求结束时自动关闭连接 |
| `create_login_required(is_logged_in)` | 工厂函数，生成 `login_required` 装饰器 |
| `create_role_required(has_any_role)` | 工厂函数，生成 `role_required` 装饰器 |
| `CurrentUser` 类 | 当前用户代理，从 Flask session 读取 `user_id`、`username`、`role` |
| `register_context_processors(app)` | 注入 `current_user`、`nav_mode`、`topbar_release_info` 等模板上下文 |
| `register_template_helpers(app)` | 注册 Jinja2 过滤器：`money`、`qty`、`erp_label`、`erp_value` |
| `initialize_database(...)` | 初始化数据库：创建 `users`、`login_attempts`、`document_sequences` 等基础表，插入默认 admin 用户 |
| `require_date(value)` | 日期解析校验 |
| `to_positive_float(value)` | 正数校验 |
| `to_non_negative_float(value)` | 非负数校验 |
| `rows_to_csv_response(rows, filename)` | 生成 CSV 导出响应 |

**数据库连接管理**：`get_db()` 在应用上下文内缓存连接（区分 `RealDictCursor` 和普通游标），通过 `teardown_appcontext` 在请求结束时关闭。

#### [services/env_config.py](file:///c:/erp/services/env_config.py) — 环境配置

| 函数 | 职责 |
|---------|------|
| `is_production_env()` | 判断是否生产环境（`INVENTORY_ENV=production`） |
| `is_local_trial_env()` | 判断是否本地试用环境 |
| `get_pg_password()` | 获取数据库密码，生产环境拒绝默认密码 |
| `get_inventory_secret_key()` | 获取应用密钥，生产环境要求 ≥32 字符 |
| `security_config_status()` | 返回安全配置状态摘要 |
| `get_login_max_failures()` | 最大登录失败次数（默认 5） |
| `get_login_lockout_seconds()` | 账户锁定时长（默认 900 秒） |
| `get_login_rate_limit()` | 登录速率限制（默认 20 次/窗口） |

#### [services/transaction_utils.py](file:///c:/erp/services/transaction_utils.py) — 事务工具

| 函数 | 职责 |
|---------|------|
| `db_transaction(get_db, cursor_factory)` | 上下文管理器，自动提交/回滚事务 |
| `execute_in_transaction(get_db, operations)` | 在事务中执行操作函数 |
| `cursor_db_helpers(cur)` | 从已有游标创建 `query_db`/`execute_db` 辅助函数（用于嵌套事务） |

#### [services/decimal_utils.py](file:///c:/erp/services/decimal_utils.py) — 数值工具

| 函数 | 职责 |
|---------|------|
| `as_decimal(value, default)` | 安全转换为 `Decimal` |
| `money_fmt(value)` | 格式化为带千位分隔符的金额字符串（2 位小数） |

### 6.2 安全服务

#### [services/login_protection.py](file:///c:/erp/services/login_protection.py) — 登录保护

**`LoginAttemptTracker` 类**：追踪登录失败次数，超过阈值后锁定账户。支持数据库持久化（`login_attempts` 表）和内存两种模式。

| 方法 | 职责 |
|------|------|
| `ensure_schema()` | 确保 `login_attempts` 表存在 |
| `is_locked(username)` | 检查账户是否被锁定 |
| `remaining_seconds(username)` | 返回剩余锁定秒数 |
| `record_failure(username)` | 记录一次失败，达到阈值自动锁定 |
| `record_success(username)` | 登录成功时清除失败记录 |

#### [services/rate_limit.py](file:///c:/erp/services/rate_limit.py) — 速率限制

**`FixedWindowRateLimiter` 类**：固定窗口速率限制器。支持数据库持久化（`rate_limit_windows` 表）和内存两种模式。

| 方法 | 职责 |
|------|------|
| `ensure_schema()` | 确保 `rate_limit_windows` 表存在 |
| `allow(key)` | 检查请求是否允许通过 |

#### [services/audit_log_service.py](file:///c:/erp/services/audit_log_service.py) — 审计日志

| 函数 | 职责 |
|---------|------|
| `log_action(user_id, username, method, endpoint, ip_address)` | 记录操作审计日志到 `audit_logs` 表，使用独立数据库连接避免影响主事务 |

#### [services/account_lock_service.py](file:///c:/erp/services/account_lock_service.py) — 账号锁定管理

提供锁定账号查询、解锁、自动解锁检查等功能。

#### [services/session_management_service.py](file:///c:/erp/services/session_management_service.py) — 会话管理

提供会话记录创建、活跃会话查询、会话终止、过期会话清理等功能。

### 6.3 库存服务

#### [services/inventory_service.py](file:///c:/erp/services/inventory_service.py) — 库存核心服务

| 函数 | 职责 |
|---------|------|
| `ensure_inventory(query_db, execute_db, product_id, ...)` | 确保物料有库存记录，不存在则创建 |
| `inventory_inbound_weighted_avg(...)` | 入库操作（移动加权平均成本） |
| `inventory_outbound(...)` | 出库操作 |
| `record_stock_transaction(...)` | 记录库存流水 |
| `ensure_document_sequence_schema(execute_db)` | 确保单据序号表存在 |
| `get_next_doc_no(query_db, prefix, table, field, ...)` | 生成下一个单据编号 |
| `_allow_negative_inventory_balance(query_db)` | 读取负库存策略（从 `system_options` 表） |
| `_sync_legacy_inventory_from_balances(...)` | 同步旧版 `inventory` 表与新版 `inventory_balances` 表 |

#### [services/inventory_posting_service.py](file:///c:/erp/services/inventory_posting_service.py) — 库存过账服务

| 函数 | 职责 |
|---------|------|
| `post_inventory_receipt(...)` | 库存收货过账（委托给 `inventory_inbound_weighted_avg`） |
| `post_inventory_issue(...)` | 库存发料过账（委托给 `inventory_outbound`） |

> **重要**：财务记录（AR/AP/成本行）只能通过指定的过账服务写入，禁止在路由中直接 INSERT/UPDATE 财务表。

#### [services/inventory_costing_service.py](file:///c:/erp/services/inventory_costing_service.py) — 存货核算服务

实现移动加权平均成本计价法，提供成本计算、核算明细记录、成本凭证生成等功能。

| 函数 | 职责 |
|---------|------|
| `calculate_weighted_average_cost(query_db, product_id, new_quantity, new_total_cost)` | 计算移动加权平均成本 |

### 6.4 财务服务

#### [services/finance_routes.py](file:///c:/erp/routes/finance_routes.py) — 财务路由（含 AR/AP 配置）

定义了收款单、预收款单、退款单、付款单等多种财务单据类型的配置字典 `AR_RECEIPT_DOCUMENT_TYPES`，每种类型包含标签、URL、前缀、金额标签等元数据。

#### [services/voucher_generation_service.py](file:///c:/erp/services/voucher_generation_service.py) — 凭证生成服务

根据业务单据自动生成会计凭证，内置凭证模板配置 `VOUCHER_TEMPLATES`：

- `sales_invoice` — 销售发票（借：应收账款，贷：主营业务收入 + 应交税费）
- `purchase_invoice` — 采购发票（借：原材料 + 应交税费，贷：应付账款）

#### [services/period_closing_service.py](file:///c:/erp/services/period_closing_service.py) — 期末处理服务

提供期末结账、反结账、损益结转功能。

| 函数 | 职责 |
|---------|------|
| `_next_voucher_no(query_db, year, month)` | 生成结转凭证编号 |
| `_insert_voucher_returning_id(...)` | 插入凭证并返回 ID |

#### [services/financial_report_service.py](file:///c:/erp/services/financial_report_service.py) — 财务报表服务

| 函数 | 职责 |
|---------|------|
| `get_account_balance(query_db, account_codes, period, balance_type)` | 获取科目余额 |

提供资产负债表、利润表、现金流量表生成功能。

#### [services/general_ledger_service.py](file:///c:/erp/services/general_ledger_service.py) — 总账服务

| 函数 | 职责 |
|---------|------|
| `query_account_balance(query_db, filters)` | 科目余额表查询 |

#### [services/payable_posting_service.py](file:///c:/erp/services/payable_posting_service.py) — 应付过账服务

| 函数 | 职责 |
|---------|------|
| `upsert_purchase_order_payable(execute_db, ...)` | 创建/更新采购订单应付记录（UPSERT） |

#### [services/project_cost_service.py](file:///c:/erp/services/project_cost_service.py) — 项目成本服务

实现项目成本归集、毛利计算和成本报表。

#### [services/serial_cost_service.py](file:///c:/erp/services/serial_cost_service.py) — 机号成本服务

实现机号成本归集、标准成本对比和成本差异分析。

### 6.5 发票服务

| 文件 | 职责 |
|------|------|
| [services/invoice_matching_service.py](file:///c:/erp/services/invoice_matching_service.py) | 发票三单匹配（销售：订单→发货→发票；采购：订单→入库→发票） |
| [services/invoice_red_flush_service.py](file:///c:/erp/services/invoice_red_flush_service.py) | 发票红冲（销售/采购发票红字冲销） |
| [services/invoice_reconciliation_service.py](file:///c:/erp/services/invoice_reconciliation_service.py) | 发票勾稽报表（检查发票与订单/收发货单一致性） |

### 6.6 生产服务

| 文件 | 职责 |
|------|------|
| [services/production_execution_service.py](file:///c:/erp/services/production_execution_service.py) | 生产执行：工序状态计算、WIP 数量计算、阻断原因分析 |
| [services/work_order_mrp_service.py](file:///c:/erp/services/work_order_mrp_service.py) | 工单 MRP：库存查询、采购申请量计算、齐套分析 |
| [services/work_order_snapshot_service.py](file:///c:/erp/services/work_order_snapshot_service.py) | 工单执行快照：创建/查询执行快照，BOM 需求行解析 |
| [services/work_order_cost_service.py](file:///c:/erp/services/work_order_cost_service.py) | 工单成本同步：领料/退料/委外/人工/设备/完工入库成本归集 |
| [services/work_order_material_service.py](file:///c:/erp/services/work_order_material_service.py) | 工单物料服务 |

### 6.7 其他服务

| 文件 | 职责 |
|------|------|
| [services/pilot_permissions.py](file:///c:/erp/services/pilot_permissions.py) | 试点权限组定义（销售/技术/采购/库存/生产/财务/售后/系统） |
| [services/system_config.py](file:///c:/erp/services/system_config.py) | 系统配置：导入导出配置、系统卡片、快捷方式 |
| [services/system_monitoring_service.py](file:///c:/erp/services/system_monitoring_service.py) | 系统监控：CPU/内存/磁盘/数据库连接/慢查询 |
| [services/notification_service.py](file:///c:/erp/services/notification_service.py) | 系统通知：创建/查询/标记已读 |
| [services/update_service.py](file:///c:/erp/services/update_service.py) | 版本更新：读取发布信息、解析更新清单 |
| [services/trace_engine.py](file:///c:/erp/services/trace_engine.py) | 追溯引擎：创建追溯快照和追溯链接 |
| [services/data_scope_service.py](file:///c:/erp/services/data_scope_service.py) | 数据范围控制：按项目/机号/部门/客户/供应商过滤数据 |
| [services/after_sale_service.py](file:///c:/erp/services/after_sale_service.py) | 售后服务：质保策略、服务工单/RMA 流程字段 |
| [services/mechanical_erp_config.py](file:///c:/erp/services/mechanical_erp_config.py) | 机床产品族配置（7 种产品族的编码前缀、工艺模板、控制点） |
| [services/industry_defaults.py](file:///c:/erp/services/industry_defaults.py) | 行业默认值（默认计量单位） |
| [services/erp_help_service.py](file:///c:/erp/services/erp_help_service.py) | ERP 操作手册内容 |
| [services/decimal_utils.py](file:///c:/erp/services/decimal_utils.py) | Decimal 工具函数 |

---

## 7. 路由层 (routes/)

路由层包含约 100 个文件，采用**注册函数模式**（`register_routes(app, deps)`）或 **Blueprint 模式**。

### 7.1 路由注册模式

#### 模式一：注册函数（主流）

```python
# routes/finance_routes.py
def register_routes(app, deps):
    query_db = deps["query_db"]
    execute_db = deps["execute_db"]
    login_required = deps["login_required"]

    @app.get("/receivables")
    @login_required
    def receivable_list():
        rows = query_db("SELECT * FROM customer_receivables")
        return render_template("receivable_list.html", rows=rows)
```

#### 模式二：Blueprint

```python
# routes/notification_routes.py
bp = Blueprint("notifications", __name__, url_prefix="/notifications")

@bp.route("/")
def list_notifications():
    ...
```

### 7.2 核心路由文件

| 文件 | 职责 |
|------|------|
| [routes/registry.py](file:///c:/erp/routes/registry.py) | **路由注册中心**（~900KB），导入所有适配器并注册核心读写路由。包含 `bind_route_dependencies()` 和 `register_blueprints()` |
| [routes/app_shell_routes.py](file:///c:/erp/routes/app_shell_routes.py) | 应用外壳：首页 `/`、登录 `/login`、登出 `/logout` |
| [routes/core_operations_routes.py](file:///c:/erp/routes/core_operations_routes.py) | 核心操作路由入口（委托给 registry） |
| [routes/api_routes.py](file:///c:/erp/routes/api_routes.py) | JSON API 路由 |
| [routes/finance_routes.py](file:///c:/erp/routes/finance_routes.py) | 财务路由：AR/AP、收付款、发票、凭证 |
| [routes/sales_routes.py](file:///c:/erp/routes/sales_routes.py) | 销售路由 |
| [routes/purchase_routes.py](file:///c:/erp/routes/purchase_routes.py) | 采购路由 |
| [routes/inventory_routes.py](file:///c:/erp/routes/inventory_routes.py) | 库存路由 |
| [routes/production_routes.py](file:///c:/erp/routes/production_routes.py) | 生产路由 |
| [routes/after_sale_routes.py](file:///c:/erp/routes/after_sale_routes.py) | 售后服务路由 |
| [routes/system_management_routes.py](file:///c:/erp/routes/system_management_routes.py) | 系统管理路由 |
| [routes/print_template_routes.py](file:///c:/erp/routes/print_template_routes.py) | 打印模板路由 |
| [routes/attachment_routes.py](file:///c:/erp/routes/attachment_routes.py) | 附件管理路由 |
| [routes/notification_routes.py](file:///c:/erp/routes/notification_routes.py) | 通知 Blueprint (`/notifications`) |
| [routes/security_routes.py](file:///c:/erp/routes/security_routes.py) | 安全管理 Blueprint (`/security`) |
| [routes/monitoring_routes.py](file:///c:/erp/routes/monitoring_routes.py) | 系统监控 Blueprint (`/monitoring`) |

### 7.3 路由辅助文件

| 文件 | 职责 |
|------|------|
| [routes/route_catalog.py](file:///c:/erp/routes/route_catalog.py) | 路由目录：`DATA_ROUTES` 列表定义所有数据路由的路径、标签、表名、列 |
| [routes/read_query_helpers.py](file:///c:/erp/routes/read_query_helpers.py) | 查询辅助：`_columns`、`_select_rows`、`_count_rows`、`_csv_response` 等 |
| [routes/display_helpers.py](file:///c:/erp/routes/display_helpers.py) | 显示辅助：乱码检测、文本清洗、金额/数量格式化 |
| [routes/form_request_helpers.py](file:///c:/erp/routes/form_request_helpers.py) | 表单请求辅助 |
| [routes/import_csv_helpers.py](file:///c:/erp/routes/import_csv_helpers.py) | CSV 导入辅助 |
| [routes/document_subject_helpers.py](file:///c:/erp/routes/document_subject_helpers.py) | 单据主题辅助 |
| [routes/route_naming_helpers.py](file:///c:/erp/routes/route_naming_helpers.py) | 路由命名辅助 |

### 7.4 适配器模式

大量路由文件采用**适配器模式**，将数据查询结果转换为模板可用的上下文：

```
routes/*_adapters.py    → 适配器函数（render_*_adapter）
routes/*_helpers.py     → 辅助函数
routes/*_routes.py      → 路由注册
```

例如：
- [routes/dashboard_adapters.py](file:///c:/erp/routes/dashboard_adapters.py) — 工作台适配器
- [routes/inventory_material_adapters.py](file:///c:/erp/routes/inventory_material_adapters.py) — 库存/物料适配器
- [routes/commercial_dashboard_adapters.py](file:///c:/erp/routes/commercial_dashboard_adapters.py) — 商务仪表板适配器
- [routes/business_partner_adapters.py](file:///c:/erp/routes/business_partner_adapters.py) — 客户/供应商适配器

---

## 8. 模板与前端 (templates/ & static/)

### 8.1 模板结构

模板使用 Jinja2，共 200+ 文件，以 [templates/base.html](file:///c:/erp/templates/base.html) 为基础布局。

**基础布局特性**：
- 左侧导航栏：按角色动态显示菜单（销售/采购/库存/生产/财务/售后/系统管理）
- 顶部全局操作工具栏：新增/保存/筛选/导出/打印/操作日志
- CSRF token 注入
- Bootstrap 5.3 + Bootstrap Icons

**关键模板**：

| 模板 | 用途 |
|------|------|
| [base.html](file:///c:/erp/templates/base.html) | 基础布局（导航栏 + 内容区） |
| [index.html](file:///c:/erp/templates/index.html) | 首页工作台 |
| [login.html](file:///c:/erp/templates/login.html) | 登录页 |
| [simple_list.html](file:///c:/erp/templates/simple_list.html) | 通用列表页 |
| [simple_detail.html](file:///c:/erp/templates/simple_detail.html) | 通用详情页 |
| [simple_document_entry.html](file:///c:/erp/templates/simple_document_entry.html) | 通用单据录入页 |
| [document_table_form.html](file:///c:/erp/templates/document_table_form.html) | 表格式单据表单 |
| [report_center.html](file:///c:/erp/templates/report_center.html) | 报表中心 |
| [pending_documents.html](file:///c:/erp/templates/pending_documents.html) | 待处理单据 |
| [finance/](file:///c:/erp/templates/finance) | 财务模块模板子目录 |
| [reports/](file:///c:/erp/templates/reports) | 报表模板子目录 |
| [partials/](file:///c:/erp/templates/partials) | 可复用模板片段 |

### 8.2 静态资源

| 文件 | 用途 |
|------|------|
| [static/css/erp_ui.css](file:///c:/erp/static/css/erp_ui.css) | ERP 自定义样式 |
| [static/js/app.js](file:///c:/erp/static/js/app.js) | 共享 UI 脚本（确认弹窗、全选、表单提交等） |
| `static/cdn/` | 本地缓存的 CDN 资源（Bootstrap CSS/JS、Bootstrap Icons） |

### 8.3 Jinja2 自定义过滤器

在 [services/app_runtime.py](file:///c:/erp/services/app_runtime.py) `register_template_helpers()` 中注册：

| 过滤器 | 用途 |
|--------|------|
| `money` / `money_fmt` / `currency_cn` | 金额格式化（千位分隔符，2 位小数） |
| `qty` | 数量格式化 |
| `erp_label` | 字段名中文翻译（查 `ERP_FIELD_LABELS` 字典） |
| `erp_value` | 枚举值中文翻译（查 `ERP_VALUE_LABELS` 字典） |

---

## 9. 数据库与 Schema 迁移

### 9.1 数据库配置

数据库连接配置通过环境变量读取，定义在 [config.py](file:///c:/erp/config.py) 和 [services/db.py](file:///c:/erp/services/db.py)：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `PG_HOST` | `127.0.0.1` | 数据库主机 |
| `PG_PORT` | `5432` | 数据库端口 |
| `PG_DATABASE` | `wms` | 数据库名 |
| `PG_USER` | `wms_user` | 数据库用户 |
| `PG_PASSWORD` | （无） | 数据库密码 |

### 9.2 Schema 迁移系统

项目使用**自研迁移系统**（[services/schema_migrations.py](file:///c:/erp/services/schema_migrations.py)），而非 Alembic 作为主要迁移工具。

**迁移机制**：
- `MIGRATIONS` 列表包含 82 条迁移，每条为 `(名称, SQL)` 元组
- `apply_schema_migrations(cur)` 在应用启动时执行
- 使用 `CREATE TABLE IF NOT EXISTS` 和 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 实现幂等迁移
- 迁移记录在 `schema_migrations` 表中跟踪

**迁移命名规则**：`YYYYMMDD_NNN_描述`

**主要迁移分组**：

| 日期范围 | 内容 |
|----------|------|
| 20260520 | 基础表：登录尝试、单据序号、速率限制 |
| 20260521 | 设备 OEE、财务期末结账 |
| 20260525-27 | 库存追溯、委外应付、销售闭环、库存装配 |
| 20260528-31 | 文档行追溯、生产状态追溯、工程技术确认、财务 AR/AP |
| 20260601-06 | 主数据完善、工单变更控制、排程派工、图纸管理、售后质保 |
| 20260607-12 | 财务汇率调整、审计审批、系统通知、主数据结构化字段 |
| 20260614-19 | 库存余额一致性、凭证系统、项目机号主数据、领料单、工序报表、工单成本、打印模板、生产完工、总账状态、追溯引擎 |
| 20260620 | 数据范围服务、销售发货库存过账 |

### 9.3 Alembic（辅助）

[alembic.ini](file:///c:/erp/alembic.ini) 和 [alembic/env.py](file:///c:/erp/alembic/env.py) 配置了 Alembic 迁移环境，数据库 URL 从 `PG_*` 环境变量动态构建。Alembic 作为辅助工具，主要迁移由自研系统处理。

### 9.4 核心数据表

根据 [routes/route_catalog.py](file:///c:/erp/routes/route_catalog.py) 和迁移脚本，主要业务表包括：

| 分类 | 表名 | 说明 |
|------|------|------|
| 基础 | `users` | 用户 |
| 基础 | `products` | 物料档案 |
| 基础 | `customers` | 客户档案 |
| 基础 | `suppliers` | 供应商档案 |
| 基础 | `warehouses` / `locations` | 仓库 / 库位 |
| 基础 | `units` | 计量单位 |
| 基础 | `departments` / `employees` | 部门 / 员工 |
| 基础 | `project_masters` / `machine_serial_masters` | 项目档案 / 机号档案 |
| 销售 | `sales_orders` | 销售订单 |
| 销售 | `sales_shipments` | 销售发货单 |
| 销售 | `sales_returns` | 销售退货单 |
| 销售 | `quotation_headers` | 报价单 |
| 销售 | `sales_invoices` | 销售发票 |
| 采购 | `purchase_orders` | 采购订单 |
| 采购 | `purchase_receipts` | 采购入库单 |
| 采购 | `purchase_requisitions` | 采购申请 |
| 采购 | `purchase_returns` | 采购退货 |
| 采购 | `purchase_invoices` | 采购发票 |
| 库存 | `inventory_balances` | 库存余额 |
| 库存 | `stock_transactions` | 库存流水 |
| 库存 | `transfer_orders` | 调拨单 |
| 库存 | `inventory_adjustments` | 库存调整 |
| 库存 | `inventory_check_orders` | 盘点单 |
| 库存 | `inventory_assembly_orders` | 组装/拆卸单 |
| 库存 | `batch_tracking` | 批次/机号追溯 |
| 生产 | `work_orders` | 生产工单 |
| 生产 | `boms` | BOM |
| 生产 | `pick_lists` | 领料单 |
| 生产 | `production_completions` | 生产完工单 |
| 委外 | `subcontract_orders` | 委外订单 |
| 委外 | `subcontract_issue_orders` | 委外发料单 |
| 委外 | `subcontract_receive_orders` | 委外收货单 |
| 财务 | `customer_receivables` | 应收账款 |
| 财务 | `supplier_payables` | 应付账款 |
| 财务 | `vouchers` | 会计凭证 |
| 财务 | `chart_of_accounts` | 会计科目 |
| 财务 | `accounting_periods` | 会计期间 |
| 财务 | `cash_bank_accounts` | 现金银行账户 |
| 财务 | `gl_account_balances` | 总账科目余额 |
| 系统 | `operation_logs` | 操作日志 |
| 系统 | `audit_logs` | 审计日志 |
| 系统 | `system_notifications` | 系统通知 |
| 系统 | `system_options` | 系统选项 |
| 系统 | `pilot_role_permissions` | 试点角色权限 |
| 系统 | `data_scope_rules` | 数据范围规则 |

---

## 10. 权限与安全体系

### 10.1 多层权限控制

系统采用**多层权限控制**架构：

```
请求进入
  │
  ├─ 1. enforce_high_risk_access_controls (before_request)
  │     ├─ 登录状态检查
  │     ├─ 高风险路径角色校验（财务/库存/系统管理）
  │     ├─ 试点模式路径权限校验
  │     └─ POST 操作角色校验（过账/关闭/取消/作废/删除）
  │
  ├─ 2. login_required 装饰器
  │     └─ 未登录重定向到 /login
  │
  ├─ 3. role_required 装饰器
  │     └─ 角色不匹配返回 403
  │
  └─ 4. pilot 权限组校验
        └─ 路径不在角色允许的权限组内返回 403
```

### 10.2 试点权限组

[services/pilot_permissions.py](file:///c:/erp/services/pilot_permissions.py) 定义了 `PILOT_PERMISSION_GROUPS`，将路由路径按业务域分组：

| 权限组 | 标签 | 说明 |
|--------|------|------|
| `sales` | 销售 | 报价、销售订单、发货、退货、发票、应收、回款 |
| `tech` | 技术/BOM | 技术确认、BOM、工艺路线、工作中心 |
| `purchase` | 采购/委外 | 采购申请、订单、入库、委外、应付 |
| `inventory` | 库存 | 库存、流水、调拨、盘点、批次追溯 |
| `production` | 生产 | 工单、齐套、MRP、领料、排程、质检 |
| `finance` | 财务 | AR/AP、收付款、凭证、期末结账、报表 |
| `service` | 售后 | 服务卡、服务工单、RMA |
| `system` | 系统 | 用户、权限、系统设置、数据健康 |

每个角色通过 `pilot_role_permissions` 表配置可访问的权限组，`default_groups_for_role()` 提供默认映射。

### 10.3 导航模式

通过 `INVENTORY_NAV_MODE` 环境变量控制：

| 模式 | 说明 |
|------|------|
| `gt_pilot` / `pilot_gtym` / `gtym_pilot` | 试点模式（启用权限组校验） |
| `full` / `all` | 完整模式（不限制导航） |
| `small_factory`（默认） | 小型工厂模式 |

### 10.4 安全措施

| 措施 | 实现 |
|------|------|
| CSRF 保护 | Flask-WTF `CSRFProtect`，生产环境强制启用 |
| 密码哈希 | `werkzeug.security.generate_password_hash` |
| 登录速率限制 | `FixedWindowRateLimiter`（默认 20 次/60 秒） |
| 账户锁定 | `LoginAttemptTracker`（默认 5 次失败后锁定 900 秒） |
| 安全响应头 | `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`、`Permissions-Policy` |
| HTML 缓存禁用 | `Cache-Control: no-cache, no-store, must-revalidate` |
| Cookie 安全 | `HTTPOnly`、`SameSite=Lax`、生产环境 `Secure` |
| 审计日志 | 所有 POST/PUT/DELETE 操作记录到 `audit_logs` 表 |
| 操作日志 | 业务操作记录到 `operation_logs` 表（含 trace_id） |
| 数据范围控制 | `data_scope_service` 按项目/机号/部门/客户/供应商过滤 |

---

## 11. 业务模块详解

### 11.1 销售模块

**业务闭环**：报价 → 销售订单 → 发货 → 发票 → 应收 → 回款

**关键路由**：
- `/quotations` — 报价单列表/录入
- `/sales-orders` — 销售订单列表
- `/sales/new` — 销售订单录入
- `/shipments` — 发货单列表
- `/sales-returns` — 退货单
- `/sales-invoices` — 销售发票
- `/receivables` — 应收账款
- `/customer-receipts` — 收款单
- `/sales/reports/*` — 销售报表（20+ 种）

**报表服务**：[services/sales_report_service.py](file:///c:/erp/services/sales_report_service.py) 及其子服务（订单报表、发货报表、发票报表、应收报表、分析报表）。

### 11.2 采购与委外模块

**业务闭环**：采购申请 → 采购订单 → 采购入库 → 采购发票 → 应付 → 付款

**委外闭环**：委外订单 → 委外发料 → 委外收货 → 委外发票 → 应付

**关键路由**：
- `/purchase_request` — 采购申请
- `/purchase-orders` — 采购订单
- `/purchase_receipts` — 采购入库
- `/subcontract` — 委外订单
- `/subcontract_issue` — 委外发料
- `/subcontract_receive` — 委外收货
- `/payables` — 应付账款
- `/payments` — 付款单
- `/procurement/suggestions` — 采购建议

### 11.3 库存模块

**核心功能**：库存余额、库存流水、调拨、盘点、调整、组装/拆卸、批次追溯

**关键路由**：
- `/inventory/detail` — 库存明细
- `/transactions` — 库存流水
- `/transfers` — 调拨单
- `/adjustments` — 调整单
- `/inventory_checks` — 盘点单
- `/assembly-orders` / `/disassembly-orders` — 组装/拆卸
- `/batch/tracking` — 批次机号追溯
- `/inventory/reports/*` — 库存报表

**成本核算**：移动加权平均法，由 `inventory_inbound_weighted_avg` 和 `inventory_outbound` 实现。

### 11.4 生产模块

**业务闭环**：BOM → 工单 → 齐套/MRP → 领料 → 排程 → 工序报工 → 完工入库

**关键路由**：
- `/work-orders` — 生产工单
- `/bom` — BOM 管理
- `/engineering/kitting` — 齐套检查
- `/production-enhance/mrp-requirements` — MRP 缺料
- `/production-issues` — 生产领料
- `/production-completions` — 生产完工
- `/production/operation-reports` — 工序报工
- `/production-routings` — 工艺路线
- `/work-centers` — 工作中心

**MRP 服务**：[services/work_order_mrp_service.py](file:///c:/erp/services/work_order_mrp_service.py) 计算库存可用量、采购在途量、工单需求量。

### 11.5 财务模块

**核心功能**：应收应付、收付款、发票、会计凭证、期末结账、财务报表、存货核算、项目/机号成本

**关键路由**：
- `/receivables` / `/payables` — 应收/应付
- `/customer-receipts` / `/payments` — 收款/付款
- `/finance/vouchers` — 会计凭证
- `/chart-of-accounts` — 会计科目
- `/finance/period-close` — 期末结账
- `/finance/balance-sheet` / `/finance/income-statement` / `/finance/cash-flow` — 财务报表
- `/finance/inventory-costing` — 存货核算
- `/finance/project-cost` / `/finance/serial-cost` — 项目/机号成本
- `/cash-bank-accounts` / `/cash-bank-journal` — 现金银行

### 11.6 售后服务模块

**业务闭环**：服务卡（按机号）→ 安装验收 → 服务工单 → RMA → 费用/成本

**关键路由**：
- `/service-cards` — 服务卡
- `/service-orders` — 服务工单
- `/service-rma` — RMA 退货
- `/service-acceptance` — 安装验收

### 11.7 工程技术模块

**核心功能**：技术确认、BOM/ECN、工艺路线、图纸管理、产品配置

**关键路由**：
- `/engineering/technical-confirmations` — 技术确认
- `/bom` / `/bom/ecn` — BOM / ECN 变更
- `/engineering/drawings` — 图纸管理
- `/product-configurations` — 产品配置
- `/production-routings` / `/work-centers` — 工艺路线 / 工作中心

---

## 12. 脚本与审计工具 (scripts/)

`scripts/` 目录包含 150+ 个脚本，分为以下几类：

### 12.1 运维脚本

| 脚本 | 用途 |
|------|------|
| [scripts/pg_backup.py](file:///c:/erp/scripts/pg_backup.py) | PostgreSQL 数据库备份 |
| [scripts/pg_restore.py](file:///c:/erp/scripts/pg_restore.py) | PostgreSQL 数据库恢复 |
| [scripts/ensure_local_security_env.py](file:///c:/erp/scripts/ensure_local_security_env.py) | 确保本地安全环境配置 |
| [scripts/ensure_local_postgres_database.py](file:///c:/erp/scripts/ensure_local_postgres_database.py) | 确保本地 PostgreSQL 数据库 |
| [scripts/check_windows_postgres_runtime.py](file:///c:/erp/scripts/check_windows_postgres_runtime.py) | 检查 Windows PostgreSQL 运行时兼容性 |
| [scripts/health_check.py](file:///c:/erp/scripts/health_check.py) | 系统健康检查 |
| [scripts/seed_master_data_samples.py](file:///c:/erp/scripts/seed_master_data_samples.py) | 种子数据填充 |
| [scripts/seed_default_units.py](file:///c:/erp/scripts/seed_default_units.py) | 默认计量单位填充 |
| [scripts/create_trial_users.py](file:///c:/erp/scripts/create_trial_users.py) | 创建试用用户 |

### 12.2 审计脚本（只读，不可修改）

> **规则**：审计脚本是系统的验证安全网，禁止修改。如果业务变更导致审计脚本失败，应修复应用代码而非审计脚本。

| 脚本 | 用途 |
|------|------|
| [scripts/source_integrity_audit.py](file:///c:/erp/scripts/source_integrity_audit.py) | 源码完整性审计（检测乱码/替换字符） |
| [scripts/erp_prelaunch_audit.py](file:///c:/erp/scripts/erp_prelaunch_audit.py) | ERP 上线前审计 |
| [scripts/audit_erp_crud_completeness.py](file:///c:/erp/scripts/audit_erp_crud_completeness.py) | CRUD 完整性审计 |
| [scripts/audit_inventory_balance_consistency.py](file:///c:/erp/scripts/audit_inventory_balance_consistency.py) | 库存余额一致性审计 |
| [scripts/audit_trial_visible_navigation.py](file:///c:/erp/scripts/audit_trial_visible_navigation.py) | 试用可见导航审计 |
| [scripts/audit_trial_direct_access_matrix.py](file:///c:/erp/scripts/audit_trial_direct_access_matrix.py) | 试用直接访问矩阵审计 |
| [scripts/audit_fk_validation_readiness.py](file:///c:/erp/scripts/audit_fk_validation_readiness.py) | 外键约束就绪审计 |
| [scripts/audit_status_transition_protection.py](file:///c:/erp/scripts/audit_status_transition_protection.py) | 状态转换保护审计 |

### 12.3 修复脚本

| 脚本 | 用途 |
|------|------|
| [scripts/repair_inventory_balance_consistency.py](file:///c:/erp/scripts/repair_inventory_balance_consistency.py) | 修复库存余额一致性 |
| [scripts/repair_inventory_negative_balances.py](file:///c:/erp/scripts/repair_inventory_negative_balances.py) | 修复负库存 |
| [scripts/repair_subcontract_closure.py](file:///c:/erp/scripts/repair_subcontract_closure.py) | 修复委外闭环 |
| [scripts/fix_data_issues.py](file:///c:/erp/scripts/fix_data_issues.py) | 修复数据问题 |
| [scripts/fix_project_traceability.py](file:///c:/erp/scripts/fix_project_traceability.py) | 修复项目追溯 |
| [scripts/clean_work_order_dirty_status.py](file:///c:/erp/scripts/clean_work_order_dirty_status.py) | 清理工单脏状态 |
| [scripts/clean_database_mojibake_master_data.py](file:///c:/erp/scripts/clean_database_mojibake_master_data.py) | 清理数据库乱码 |

### 12.4 Schema 应用脚本

| 脚本 | 用途 |
|------|------|
| [scripts/apply_finance_missing_tables.py](file:///c:/erp/scripts/apply_finance_missing_tables.py) | 应用财务缺失表 |
| [scripts/apply_finance_period_closing_schema.py](file:///c:/erp/scripts/apply_finance_period_closing_schema.py) | 应用期末结账 Schema |
| [scripts/apply_finance_inventory_costing_schema.py](file:///c:/erp/scripts/apply_finance_inventory_costing_schema.py) | 应用存货核算 Schema |
| [scripts/apply_finance_invoice_enhancement.py](file:///c:/erp/scripts/apply_finance_invoice_enhancement.py) | 应用发票增强 |
| [scripts/apply_finance_ar_ap_enhancement.py](file:///c:/erp/scripts/apply_finance_ar_ap_enhancement.py) | 应用 AR/AP 增强 |

---

## 13. 项目运行方式

### 13.1 环境准备

1. **Python 虚拟环境**：项目使用 `.venv` 虚拟环境
2. **PostgreSQL**：内嵌 PostgreSQL 18（`pgsql18/` 目录）或外部 PostgreSQL
3. **环境变量**：复制 `.env.example` 为 `.env` 并修改配置

### 13.2 环境变量配置

关键环境变量（见 [.env.example](file:///c:/erp/.env.example)）：

```ini
# 数据库
PG_HOST=127.0.0.1
PG_PORT=5432
PG_DATABASE=wms
PG_USER=wms_user
PG_PASSWORD=admin

# 应用密钥（生产环境必须修改！）
INVENTORY_SECRET_KEY=<32位以上随机字符串>

# 应用配置
FLASK_DEBUG=0
FLASK_ENV=production
ERP_HOST=0.0.0.0
PORT=5000

# 功能开关
INVENTORY_NAV_MODE=gt_pilot        # 导航模式
WTF_CSRF_ENABLED=1                  # CSRF 保护
INVENTORY_INIT_DB_ON_CREATE=0       # 启动时初始化数据库

# 登录安全
LOGIN_MAX_FAILURES=5
LOGIN_LOCKOUT_SECONDS=900
LOGIN_RATE_LIMIT=10
LOGIN_RATE_LIMIT_WINDOW_SECONDS=300
```

### 13.3 启动方式

#### 方式一：Windows 一键启动（推荐）

```cmd
start.cmd
```

[start.cmd](file:///c:/erp/start.cmd) 执行流程：
1. 加载 `runtime_env.cmd` 环境变量
2. 检查 `.venv` 虚拟环境
3. 确保安全配置（`PG_PASSWORD` 等）
4. 启动本地 PostgreSQL（如未运行）
5. 运行源码完整性审计
6. 通过 Waitress 启动应用

#### 方式二：开发模式

```cmd
.venv\Scripts\python.exe app.py
```

开发模式使用 Flask 内置服务器，默认监听 `127.0.0.1:5000`，通过 `FLASK_DEBUG=1` 启用调试。

#### 方式三：生产 WSGI

```cmd
.venv\Scripts\python.exe waitress_server.py
```

[waitress_server.py](file:///c:/erp/waitress_server.py) 使用 Waitress WSGI 服务器，默认 8 线程，监听 `ERP_HOST:PORT`。

### 13.4 数据库初始化

首次运行时，设置 `INVENTORY_INIT_DB_ON_CREATE=1` 或手动执行：

```python
from app import create_app
from services.app_runtime import initialize_database
app = create_app()
```

`initialize_database()` 会：
1. 执行所有 Schema 迁移
2. 创建 `users`、`login_attempts`、`document_sequences` 等基础表
3. 插入默认 admin 用户（用户名 `admin`，密码 `admin`）

### 13.5 数据库备份与恢复

```cmd
# 备份
python scripts\pg_backup.py --output backups\pre_migration_<desc>.dump

# 恢复
python scripts\pg_restore.py --input <dump_file>
```

> **规则**：任何 Schema 迁移前必须先备份。生产环境必须每日通过 Windows Task Scheduler 执行 `scripts/pg_backup.py`。

---

## 14. 验证与审计流程

### 14.1 代码变更后必须执行的验证

任何代码变更后，按顺序执行以下检查：

```cmd
# 1. Python 编译检查
python -m compileall app.py routes services scripts

# 2. 源码完整性审计
python scripts\source_integrity_audit.py

# 3. 上线前审计
python scripts\erp_prelaunch_audit.py

# 4. CRUD 完整性审计
python scripts\audit_erp_crud_completeness.py
```

### 14.2 库存相关变更的额外检查

```cmd
set PG_PASSWORD=admin && python scripts\audit_inventory_balance_consistency.py
```

### 14.3 权限/导航相关变更的额外检查

```cmd
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && python scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && python scripts\audit_trial_direct_access_matrix.py
```

### 14.4 预期输出

| 脚本 | 预期输出 |
|------|----------|
| `compileall` | 无语法错误 |
| `source_integrity_audit.py` | `source_integrity=ok`, `source_mojibake_findings=0` |
| `erp_prelaunch_audit.py` | `errors=0`, `warnings=0`, `core_pages=34` |
| `audit_erp_crud_completeness.py` | `targets=46`, `OK=46`, `errors=0` |
| `audit_inventory_balance_consistency.py` | `findings=0` |
| `audit_trial_visible_navigation.py` | `checked_users=7`，无异常路由 |
| `audit_trial_direct_access_matrix.py` | PASS |

### 14.5 测试

测试配置见 [pytest.ini](file:///c:/erp/pytest.ini)：

```cmd
# 运行所有测试
.venv\Scripts\python.exe -m pytest

# 运行特定测试
.venv\Scripts\python.exe -m pytest scripts\test_finance_functions.py
```

测试文件匹配模式：`test_*.py`、`*_test.py`、`audit_*.py`、`verify_*.py`、`validate_*.py`。

---

## 附录：关键设计决策

### A1. 为什么使用函数式依赖注入而非类？

服务层函数接收 `query_db` / `execute_db` 作为参数，而非使用全局数据库连接。这使得：
- 服务函数可独立测试（传入 mock 函数）
- 数据库连接生命周期由应用层统一管理
- 避免服务层与特定 ORM 耦合

### A2. 为什么使用自研迁移而非纯 Alembic？

自研迁移系统（`schema_migrations.py`）使用 `IF NOT EXISTS` 语法实现幂等迁移，在应用启动时自动执行，确保数据库结构始终最新。Alembic 作为辅助工具保留。

### A3. 为什么单据录入与列表分离？

ERP 核心原则：单据录入页（`/new`）回答"创建什么单据"，列表页回答"存在哪些单据"。列表页不暴露新建按钮，新建操作必须在独立的单据录入路由完成。

### A4. 项目号/机号追溯主线

项目号（`project_code`）和机号（`serial_no`）是机床制造业的核心追溯轴，贯穿所有业务单据。它们是追溯字段而非强制字段，仅在 `require_project_serial` 系统选项启用时才强制要求。

---

*文档生成日期: 2026-06-20*
*项目路径: c:\erp*
