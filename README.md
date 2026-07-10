# 低压开关成套设备 ERP

这是面向广东惠电科技发展有限公司的低压开关成套设备及配电自动化控制设备制造 ERP 系统。系统重点不是通用 SaaS 看板，而是围绕该制造企业的核心业务闭环：基础资料、采购、委外、库存、销售、生产、服务、财务对账，以及按项目号和机柜序列号追踪业务全过程。

## 业务定位

- 产品和项目资料：产品系列、机型、项目号、机柜序列号。
  - 产品系列：低压抽出式开关柜（GCK）、低压固定式开关柜（GGD）、低压配电柜、动力配电箱（XL-21）、照明配电箱（PZ30）、无功补偿装置、配电自动化终端 DTU、环网柜、箱式变电站。
- 技术资料：物料（铜排、断路器、接触器、互感器等）、BOM、工艺路线、工作中心、委外工序（如外壳喷涂、铜排镀层）、关键控制点（耐压、绝缘、通电试验）。
- 核心单据闭环：请购到采购订单到收货到入库到应付；销售订单到发货到应收；工单到领料、装配、接线、测试、完工入库；服务卡和服务单按机柜序列号跟进。
- 库存管理：入库、出库、调拨、调整、盘点、余额、流水、批次、序列号、项目追踪和单据追溯。
- 财务对账：应收、应付、存货核算、成本报表、期末检查和基础财务报表。
- 追溯轴：项目号（project_code）和机柜序列号（serial_no）贯穿销售、BOM、采购、库存、委外、工单、装配、接线、测试、发货、现场服务、应收应付和成本报表；属于追溯字段而非所有场景必填，标准配电箱的备货生产、小公司简化操作和项目前期准备可留空。

## 技术结构

系统使用 Flask 和 PostgreSQL，主要面向 Windows 本地或服务器部署。

主要目录和文件：

- `app.py`：Flask 应用入口和路由注册。
- `waitress_server.py`：本地生产式服务启动入口。
- `routes/`：ERP 页面和接口路由。
- `services/`：过账、数据库结构、归档、权限和业务服务。
- `templates/`：ERP 页面模板。
- `static/`：样式、脚本和静态资源。
- `scripts/`：审计、校验、备份、恢复和运维脚本。

## 快速启动

已经安装好本地运行环境时，执行：

```cmd
start.cmd
```

默认访问地址：

```text
http://127.0.0.1:5000
```

离线安装可执行：

```cmd
install.cmd
```

或：

```cmd
offline_one_click_install.cmd
```

安装细节见 `README_INSTALL.txt`。

## 开发运行

安装依赖：

```cmd
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

本地运行：

```cmd
.venv\Scripts\python.exe app.py
```

如果系统里没有全局 `python` 命令，请直接使用：

```cmd
.venv\Scripts\python.exe
```

## 数据库和备份

系统使用 PostgreSQL。生产环境必须每天执行备份：

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py
```

数据库结构变更前，先执行迁移前备份：

```cmd
.venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_migration_<desc>.dump
```

恢复演练使用：

```cmd
.venv\Scripts\python.exe scripts\pg_restore.py --input <dump_file>
```

所有数据库 DDL 变更必须先写入 `services/schema_migrations.py`，不要在路由或服务请求过程中临时执行建表、改表、加字段等操作。

## 常用校验

代码完成后通常需要执行：

```cmd
.venv\Scripts\python.exe -m compileall app.py routes services scripts
.venv\Scripts\python.exe scripts\source_integrity_audit.py
.venv\Scripts\python.exe scripts\erp_prelaunch_audit.py
.venv\Scripts\python.exe scripts\audit_erp_crud_completeness.py
```

涉及库存时还需要执行：

```cmd
set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_inventory_balance_consistency.py
```

涉及权限或导航时还需要执行：

```cmd
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_visible_navigation.py
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin && .venv\Scripts\python.exe scripts\audit_trial_direct_access_matrix.py
```

## 重要文档

- `AGENTS.md`：项目规则、ERP 范围纪律、编码安全和验收要求。
- `DEVELOPMENT_GUIDE.md`：开发流程和验证说明。
- `OPERATIONS_MANUAL.md`：运维、备份、恢复、健康检查和故障处理。
- `MENU_ROLLOUT_CLASSIFICATION.md`：页面上线状态和路由分类。
- `ERP_BOUNDARY_STABILIZATION.md`：业务闭环边界记录。
- `PERMISSION_MATRIX_DRAFT.md`：角色和权限规划。

## 开发纪律

- 不要在没有明确要求时新增 ERP 模块、路由、数据库字段、页面或导航入口。
- 优先修复并验证现有核心流程，不要随意扩大范围。
- 单据录入、单据列表、查询列表、报表、工作台、财务页、系统管理页要分开。
- 普通用户导航标签要能看出页面类型。
- 不要提交运行状态、数据库文件、日志、备份、虚拟环境或本地密钥。

## 编码注意

ERP 操作界面的中文标签、状态和业务术语必须保持正常可读，不允许出现乱码、替换字符或占位文本。

修改中文内容时，应使用可靠的补丁方式编辑，避免通过 PowerShell 重定向、控制台管道或脚本写入造成编码损坏。
