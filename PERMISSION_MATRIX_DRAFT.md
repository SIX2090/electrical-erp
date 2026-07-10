# 上线权限矩阵草案

> 草案版本：1.1  
> 权威来源：`services/pilot_permissions.py`（`PILOT_PERMISSION_GROUPS`、`PILOT_PERMISSION_FEATURES`、`PILOT_DEFAULT_ROLE_GROUPS`、`PILOT_ROLE_ACTION_OVERRIDES`）  
> 状态：已落地代码，全部审计通过。

## 1. 目的

定义 ERP 上线的角色-权限映射，覆盖 8 个角色与 9 个权限组，重点为 6 个主力业务角色（销售、采购、仓库、生产、财务、管理员）。确认后将对 `services/pilot_permissions.py` 的 `PILOT_DEFAULT_ROLE_GROUPS` 与动作覆盖机制做最小修改。

## 2. 已确认决策

| # | 决策项 | 选择 |
|---|---|---|
| 1 | 上线角色范围 | 保留 8 角色（admin、manager、sales、purchase、warehouse、production、service、finance），manager 镜像 admin |
| 2 | 财务跨组查询 | 财务对销售订单/发货/采购订单/采购入库/库存报表开放 view+export+print（销售/采购单据可打印，库存报表仅查看+导出），不可创建/审核/操作 |
| 3 | 基础资料访问 | 业务角色（sales/purchase/warehouse/production/service/finance）仅 view，仅 admin/manager 可创建/修改 |
| 4 | 输出形式 | 同时输出 Markdown 预览与本草案文件 |
| 5 | sales 含 service 组 | 保留，销售需跟进项目交付与售后 |
| 6 | warehouse 不含 production 组 | 保持，仓库无需看工单上下文 |
| 7 | production 不含 purchase 组 | 保持，已有 procurement_suggestion 够用 |
| 8 | service 仅 master V | 保持，售后不改基础档案 |
| 9 | 财务跨组 V+X+P | 保持，对账可导出与打印销售/采购单据 |
| 10 | manager 保留全权 | 保留，系统主管需全权 |

## 3. 角色 → 权限组 矩阵

图例：
- `FULL` = 该组内功能的完整 default_actions
- `V+X` = 仅查看 + 导出（不可创建/编辑/审核/删除/操作/打印）
- `V+X+P` = 仅查看 + 导出 + 打印（不可创建/编辑/审核/删除/操作）
- `V` = 仅查看
- `—` = 无权限

| 权限组（标签） | admin | manager | sales | purchase | warehouse | production | service | finance |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| sales（销售/应收/项目柜号） | FULL | FULL | FULL | — | — | — | — | V+X+P |
| tech（技术/BOM/工艺） | FULL | FULL | — | FULL | — | FULL | — | — |
| purchase（采购/委外/应付） | FULL | FULL | — | FULL | — | — | — | V+X+P |
| inventory（库存/流水/盘点） | FULL | FULL | — | FULL | FULL | FULL | — | V+X |
| production（工单/领料/完工/MRP/质检） | FULL | FULL | — | — | — | FULL | — | — |
| service（售后/安装验收/RMA） | FULL | FULL | FULL | — | — | — | FULL | — |
| finance（财务/成本/凭证/结账） | FULL | FULL | — | — | — | — | — | FULL |
| master（基础资料） | FULL | FULL | V | V | V | V | V | V |
| system（用户/权限/日志/备份） | FULL | FULL | — | — | — | — | — | — |

## 4. 关键功能动作矩阵

动作缩写：`V`=查看、`C`=新增、`E`=修改、`A`=审核、`D`=删除、`O`=操作、`P`=打印、`X`=导出、`—`=无权限。

### 4.1 销售组

| 功能（标签） | admin | manager | sales | finance |
|---|:---:|:---:|:---:|:---:|
| sales_order（销售订单） | VCAEOPX | VCAEOPX | VCAEOPX | VXP |
| shipment（销售发货） | VCAOPX | VCAOPX | VCAOPX | VXP |
| quotation（设备报价） | VCAEPX | VCAEPX | VCAEPX | VXP |
| sales_return（销售退货） | VCAOPX | VCAOPX | VCAOPX | VXP |
| sales_invoice（销售发票） | VCAOPX | VCAOPX | VCAOPX | VXP |
| receivable（应收账款） | VAOX | VAOX | VAOX | VX |

### 4.2 技术/BOM 组

| 功能（标签） | admin | manager | purchase | production |
|---|:---:|:---:|:---:|:---:|
| bom（BOM清单） | VEPX | VEPX | VEPX | VEPX |
| bom_ecn（BOM工程变更） | VCAEPX | VCAEPX | V | V |
| routing（工艺路线） | VCAEDPX | VCAEDPX | V | V |
| work_center（工作中心） | VCAEDPX | VCAEDPX | V | V |
| technical_confirmation（技术确认单） | VCAEPX | VCAEPX | V | V |

### 4.3 采购/委外组

| 功能（标签） | admin | manager | purchase | finance |
|---|:---:|:---:|:---:|:---:|
| purchase_request（采购申请） | VCAEOPX | VCAEOPX | VCAEOPX | VXP |
| purchase_order（采购订单） | VCAEOPX | VCAEOPX | VCAEOPX | VXP |
| purchase_receipt（采购入库） | VCAOPX | VCAOPX | VCAOPX | VXP |
| subcontract（委外订单） | VCAEOPX | VCAEOPX | VCAEOPX | VXP |
| subcontract_issue（委外发料） | VCAEOPX | VCAEOPX | VCAEOPX | VXP |
| subcontract_receive（委外收货） | VCAEOPX | VCAEOPX | VCAEOPX | VXP |
| payable（应付单） | VAOX | VAOX | VAOX | VX |

### 4.4 库存组

| 功能（标签） | admin | manager | purchase | warehouse | production | finance |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| inventory_balance（库存明细） | VX | VX | VX | VX | VX | VX |
| stock_transactions（库存流水） | VPX | VPX | VPX | VPX | VPX | VX |
| inventory_adjustment（库存调整） | VCAEOPX | VCAEOPX | V | VCAEOPX | V | VX |
| inventory_transfer（库存调拨） | VCAEOPX | VCAEOPX | V | VCAEOPX | V | VX |
| inventory_check（库存盘点） | VCAEOPX | VCAEOPX | — | VCAEOPX | — | VX |
| inventory_assembly（组装单） | VCAEOPX | VCAEOPX | — | VCAEOPX | — | VX |
| inventory_disassembly（拆卸单） | VCAEOPX | VCAEOPX | — | VCAEOPX | — | VX |

### 4.5 生产组

| 功能（标签） | admin | manager | production |
|---|:---:|:---:|:---:|
| work_order（生产工单） | VCAEOPX | VCAEOPX | VCAEOPX |
| production_issue（生产领料单） | VCAOPX | VCAOPX | VCAOPX |
| production_return（生产退料单） | VCAEOPX | VCAEOPX | VCAEOPX |
| production_completion（完工入库单） | VCAOPX | VCAOPX | VCAOPX |
| operation_report（工序报工） | VCAEOX | VCAEOX | VCAEOX |
| kitting（齐套检查） | VOX | VOX | VOX |
| mrp_shortage（MRP缺料） | VOX | VOX | VOX |
| quality（质量检验） | VCAEOX | VCAEOX | VCAEOX |

### 4.6 售后组

| 功能（标签） | admin | manager | sales | service |
|---|:---:|:---:|:---:|:---:|
| service_card（服务档案） | VCEPX | VCEPX | VCEPX | VCEPX |
| service_acceptance（安装验收） | VCAEOPX | VCAEOPX | VCAEOPX | VCAEOPX |
| service_order（服务单） | VCAEOPX | VCAEOPX | VCAEOPX | VCAEOPX |
| service_rma（RMA） | VCAEOPX | VCAEOPX | VCAEOPX | VCAEOPX |

### 4.7 财务/成本组

| 功能（标签） | admin | manager | finance |
|---|:---:|:---:|:---:|
| finance_receivable（应收单） | VAOX | VAOX | VAOX |
| finance_receipt（收款单） | VCEDX | VCEDX | VCEDX |
| finance_payable（应付单） | VAOX | VAOX | VAOX |
| supplier_payment（付款单） | VCEDX | VCEDX | VCEDX |
| finance_sales_invoice（销售发票） | VCAEOPX | VCAEOPX | VCAEOPX |
| finance_purchase_invoice（采购发票） | VCAEOPX | VCAEOPX | VCAEOPX |
| period_close（期间结账） | VAOPX | VAOPX | VAOPX |
| financial_statements（经营财务快照） | VX | VX | VX |
| project_cost_report（项目成本明细） | VX | VX | VX |
| machine_cost_report（柜号成本明细） | VX | VX | VX |
| aging_report（应收应付账龄） | VX | VX | VX |

### 4.8 基础资料组

| 功能（标签） | admin | manager | sales | purchase | warehouse | production | service | finance |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| material（物料档案） | VCAEDPX | VCAEDPX | V | V | V | V | V | V |
| customer（客户档案） | VCEDPX | VCEDPX | V | V | V | V | V | V |
| supplier（供应商档案） | VCEDPX | VCEDPX | V | V | V | V | V | V |
| warehouse_master（仓库档案） | VCEDX | VCEDX | V | V | V | V | V | V |
| project_master（项目档案） | VCEX | VCEX | V | V | V | V | V | V |
| cabinet_master（柜号档案） | VCEX | VCEX | V | V | V | V | V | V |
| material_opening（物料期初） | VCEX | VCEX | — | — | VCEX | — | — | VX |
| subcontract_opening（委外期初） | VCEX | VCEX | — | VCEX | — | — | — | VXP |
| receivable_opening（应收期初） | VCEX | VCEX | — | — | — | — | — | VCEX |
| payable_opening（应付期初） | VCEX | VCEX | — | — | — | — | — | VCEX |

### 4.9 系统组

| 功能（标签） | admin | manager |
|---|:---:|:---:|
| users（用户管理） | VCEDO | VCEDO |
| role_permissions（角色权限） | VEO | VEO |
| operation_logs（操作日志） | VDX | VDX |
| system_settings（系统参数） | VEO | VEO |
| database_backups（数据库备份） | VOX | VOX |
| data_health（数据健康） | VX | VX |

## 5. 与当前默认值的差异

| 角色 | 当前所属组 | 草案所属组 | 变更 |
|---|---|---|---|
| admin | 全部 9 组 | 全部 9 组 | 无 |
| manager | 全部 9 组 | 全部 9 组 | 无 |
| sales | sales, service | sales, service, **master(V)** | +基础资料查看 |
| purchase | tech, purchase, inventory | tech, purchase, inventory, **master(V)** | +基础资料查看 |
| warehouse | inventory | inventory, **master(V)** | +基础资料查看 |
| production | tech, inventory, production | tech, inventory, production, **master(V)** | +基础资料查看 |
| service | service | service, **master(V)** | +基础资料查看 |
| finance | finance | finance, **sales(V+X+P)**, **purchase(V+X+P)**, **inventory(V+X)**, **master(V)** | +4 组跨组查询 |

## 6. 实施说明

已落地内容：

- `PILOT_DEFAULT_ROLE_GROUPS`：所有业务角色加 `master`，finance 加 `sales`/`purchase`/`inventory`。
- `PILOT_ROLE_ACTION_OVERRIDES`：按 `(role, group)` 限制动作子集，实现 finance 跨组 V+X+P（销售/采购）、V+X（库存），业务角色 master 仅 V。
- `default_actions_for_role()`：与 `default_actions` 求交集，确保 override 不超出默认范围。
- 期初数据路径从 `master` 组移至业务组：物料期初→inventory、委外期初→purchase、应收/应付期初→finance。
- `app.py` 硬编码 GET 检查：为期初路径、库存入出库、采购退货、发货新建、委外库存报表、调整单、组装/拆卸单等添加 `finance` 角色。
- `routes/sales_report_routes.py`：`sales_report_required` 添加 `finance` 角色，支持财务对账查看销售报表。
- `templates/finance/voucher_generate_batch.html`：修复 `invoice.amount_with_tax` → `invoice.amount`（SQL 别名匹配）。
- 数据库 `pilot_role_permissions` 表已重置为代码默认值。

审计结果（全部通过）：

```
python -m compileall app.py routes services scripts          # 无语法错误
python scripts/source_integrity_audit.py                     # source_integrity=ok, mojibake=0
python scripts/erp_prelaunch_audit.py                        # core_pages=34, errors=0, warnings=0
python scripts/audit_erp_crud_completeness.py                # targets=46, ok=46, errors=0
set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=admin
  python scripts/audit_trial_visible_navigation.py           # checked_users=7, 全部 ok
  python scripts/audit_trial_direct_access_matrix.py         # audit=ok, checked_users=7, checked_paths=419
  python scripts/audit_inventory_balance_consistency.py      # findings=0
```
