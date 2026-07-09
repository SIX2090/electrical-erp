# P0 Data Standardization and Traceability Engine Boundary Design

Date: 2026-06-19
Phase: P0 Stage A (read-only analysis, no code/migration/route/menu changes)
Scope owner: ERP stabilization team

This document is a read-only analysis of the current ERP schema, document flows, and traceability gaps. It defines the boundary for the future P0-2 traceability engine and drafts the `trace_links` / `trace_snapshots` table structure. It does NOT authorize any migration, route, page, menu, audit-script change, or MRP work.

All narrative text is in English to avoid encoding damage. Chinese business terms are referenced by their English equivalents; the canonical Chinese label is listed once in the doc_type registry (section 3.2) as ASCII-safe English with a parenthetical pinyin note where needed. No mojibake, replacement characters, or corrupt CJK text is present.

---

## 1. Current Core Data Dictionary Draft

Source of truth: `services/schema_migrations.py` (77 migrations, 92+ `CREATE TABLE IF NOT EXISTS` statements) plus pre-existing core tables referenced via `ALTER TABLE`.

### 1.1 Master Data Tables

| Domain | Table | Key Columns | Owner Module | Notes |
|---|---|---|---|---|
| Product master | `products` | id, code, name, spec, unit, category_id | Master data | Pre-existing core table |
| Material master | `materials` | id, code, name, spec, unit | Master data | Pre-existing |
| Customer | `customers` | id, code, name | Master data | Pre-existing |
| Supplier | `suppliers` | id, code, name | Master data | Pre-existing |
| Outsourced processor | `outsourced_processors` | id, code, name | Master data | Pre-existing |
| Warehouse | `warehouses` | id, code, name | Master data | Pre-existing |
| Location | `locations` | id, code, warehouse_id | Master data | Pre-existing |
| Unit | `units` | id, code, name | Master data | Pre-existing |
| Department | `departments` | id, code, name | Master data | Pre-existing |
| Employee | `employees` | id, code, name, department_id | Master data | Pre-existing |
| Category | `categories` | id, code, name | Master data | Pre-existing |
| Project master | `project_masters` | id, project_code (UNIQUE), project_name, customer_id, product_family, machine_model, source_order_no, owner_name, planned_delivery_date, status | Master data / traceability | Created in `20260605_001_project_machine_master` |
| Machine serial master | `machine_serial_masters` | id, serial_no (UNIQUE), project_id, project_code, customer_id, product_id, product_family, machine_model, production_stage, service_status, warranty_start_date, warranty_end_date | Master data / traceability | Created in `20260605_001_project_machine_master` |
| Equipment | `equipment` | id, code, name, model, work_center, manufacturer, status | Master data | Created in `20260521_001_equipment_oee` |
| Product configuration | `product_configurations` | id, project_code, serial_no, sales_order_id | Engineering | Created in `20260606_003_product_configuration_boundary` |

### 1.2 Technical Master Tables

| Domain | Table | Key Columns | Notes |
|---|---|---|---|
| BOM | `boms`, `bom_items` | Pre-existing | Referenced by work orders, ECN |
| BOM ECN | `bom_engineering_changes` | id, project_code, serial_no | `20260605_001` |
| Routing | `routings`, `routing_operations` | Pre-existing | Referenced by work orders, operation reports |
| Work center | `work_centers` | Pre-existing | Referenced by equipment, operation reports |
| Engineering drawings | `engineering_drawings`, `engineering_drawing_links`, `engineering_drawing_change_logs` | drawing_no, version, lifecycle status | `20260606_001b_engineering_drawing_ledger` |
| Engineering technical confirmation | `engineering_technical_confirmations` | id, project_code, serial_no, sales_order_id | `20260529_002` |

### 1.3 Document Tables by Module

#### Purchase
| Table | Type | Trace Fields |
|---|---|---|
| `purchase_requisitions` / `purchase_requisition_items` | Document entry | line_project_code, line_serial_no (items) |
| `purchase_orders` / `purchase_order_items` | Document entry | project_code, serial_no (header), line_project_code, line_serial_no (items) |
| `purchase_receipts` | Document entry | source_type, source_no |
| `purchase_invoices` / `purchase_invoice_items` | Finance document | project_code, serial_no, source_type, source_id, source_no, source_doc_type, source_doc_id, source_doc_no |
| `supplier_payables` / `supplier_payable_items` | Finance | project_code, serial_no, doc_type, doc_id, doc_no, source_type, source_id, source_no, source_doc_type, source_doc_id, source_doc_no |
| `supplier_payments` / `supplier_payment_lines` | Finance document | project_code, serial_no, source_type, source_id, source_no |

#### Sales
| Table | Type | Trace Fields |
|---|---|---|
| `quotation_headers` | Document entry | project_code, serial_no, source_no |
| `sales_orders` / `sales_order_items` | Document entry | project_code, serial_no (header), line_project_code, line_serial_no (items) |
| `sales_shipments` | Document entry | project_code, serial_no, source_type (default 'sales_order'), source_no |
| `sales_returns` | Document entry | project_code, serial_no, source_no |
| `sales_invoices` / `sales_invoice_items` | Finance document | project_code, serial_no, source_type, source_id, source_no, source_doc_type, source_doc_id, source_doc_no |
| `customer_receivables` / `customer_receivable_items` | Finance | project_code, serial_no, source_type, source_id, source_no, source_doc_type, source_doc_id, source_doc_no |
| `customer_receipts` / `customer_receipt_lines` | Finance document | project_code, serial_no, source_type, source_id, source_no |

#### Inventory
| Table | Type | Trace Fields |
|---|---|---|
| `stock_transactions` | Transaction log | project_code, serial_no, source_type, source_doc_type, source_doc_no, source_line_no, reference_no, lot_no |
| `inventory_balances` | Balance snapshot | project_code, lot_no, serial_no |
| `inventory_adjustments` | Document entry | project_code, serial_no, line_project_code |
| `inventory_adjustment_orders` | Document entry | Created `20260527_004` |
| `transfer_orders` / `transfer_order_items` | Document entry | project_code, line_project_code (items) |
| `inventory_check_orders` / `inventory_check_order_items` | Document entry | project_code, line_project_code (items) |
| `inventory_assembly_orders` / `inventory_assembly_items` | Document entry | serial_no, project_code, line_project_code (items) |
| `batch_tracking` | Trace log | serial_no, project_code, lot_no |
| `inventory_costing` | Cost snapshot | product_id, costing_method |

#### Outsourcing
| Table | Type | Trace Fields |
|---|---|---|
| `subcontract_orders` | Document entry | project_code, serial_no, line_project_code, line_serial_no, parent_work_order_id |
| `subcontract_issue_orders` / `subcontract_issue_lines` | Document entry | project_code, serial_no (lines) |
| `subcontract_receive_orders` / `subcontract_receive_lines` | Document entry | project_code, serial_no (lines) |

#### Production
| Table | Type | Trace Fields |
|---|---|---|
| `work_orders` / `wo_material_items` | Document entry | project_code, serial_no, line_project_code, line_serial_no |
| `wo_complete_items` | Completion line | source_doc_type |
| `work_order_status_logs` | Status log | work_order_id |
| `work_order_change_records` | Change log | work_order_id |
| `production_schedules` | Dispatch | work_order_id |
| `pick_lists` / `pick_list_items` | Document entry | doc_type, doc_no, work_order_id, project_code, serial_no, line_project_code, line_serial_no |
| `operation_reports` | Document entry | work_order_id, work_order_process_id, routing_operation_id, report_type |
| `production_completion_orders` | Document entry | work_order_id, serial_no, project_code, wo_complete_item_id |
| `work_order_costs` / `work_order_cost_lines` | Cost | work_order_id |

#### Service
| Table | Type | Trace Fields |
|---|---|---|
| `machine_service_cards` | Master/entry | sales_order_id, project_code, serial_no, product_id, customer_id, machine_model |
| `machine_service_orders` / `machine_service_order_items` | Document entry | project_code, serial_no (items) |
| `machine_service_rmas` | Document entry | line_project_code, line_serial_no, product_id |
| `machine_service_acceptance_checks` | Document entry | project_code, serial_no |
| `machine_service_return_visits` | Document entry | satisfaction_score |

#### Finance
| Table | Type | Trace Fields |
|---|---|---|
| `vouchers` / `voucher_lines` | Accounting | source_type, source_id, source_no, project_code, serial_no |
| `general_ledger` | Ledger | source_type, source_id, source_no, project_code, serial_no |
| `cash_bank_accounts` / `cash_bank_journal_entries` | Cash | project_code, serial_no, source_type, source_no |
| `chart_of_accounts` / `gl_account_balances` | Master | account code |
| `accounting_periods` / `finance_period_closes` | Period | year, month, status |
| `customer_receipt_settlements` | Settlement | receipt_id, receivable_id |
| `supplier_payment_settlements` | Settlement | payment_id, payable_id |
| `finance_exchange_adjustments` / `finance_exchange_adjustment_lines` | Period-end | doc_no, project_code, serial_no |
| `project_cost_ledger` | Cost | project_code (NOT NULL), source_type, source_no |
| `serial_cost_ledger` | Cost | serial_no (NOT NULL), project_code, source_type, source_no |

### 1.4 System Tables

| Table | Purpose |
|---|---|
| `users`, `roles`, `user_roles` | Auth |
| `login_attempts`, `rate_limit_windows` | Security |
| `document_sequences` | Doc number generation (prefix + scope) |
| `audit_logs` | Operation audit |
| `operation_logs` | Request-level log |
| `system_options` | System parameters (e.g. `require_project_serial`) |
| `system_notifications` | In-app notification |
| `schema_migrations` | Migration tracking |
| `print_templates` | Print template registry |

---

## 2. Project Number / Machine Serial Field Inventory

### 2.1 Field Naming Audit

The codebase uses **three different column names** for the same business concept across tables. This is the single largest traceability consistency risk.

| Business concept | Column names found | Where used |
|---|---|---|
| Project number (project_code) | `project_code` (preferred, VARCHAR(120)) | 30+ tables - dominant convention |
| Project number | `line_project_code` | Document line tables (purchase_order_items, sales_order_items, work_orders, wo_material_items, transfer_order_items, inventory_check_order_items, inventory_assembly_items, inventory_adjustments, pick_list_items, machine_service_rmas) |
| Project number | `project_id` (INTEGER FK) | `machine_serial_masters.project_id` references `project_masters.id` |
| Machine serial (serial_no) | `serial_no` (preferred, VARCHAR(120)) | 30+ tables - dominant convention |
| Machine serial | `line_serial_no` | Document line tables (same set as line_project_code) |
| Machine serial | `machine_serial_no` | NOT found in schema (only referenced in AGENTS.md narrative) |
| Machine serial | `machine_model` | Used as a descriptive attribute, NOT a unique serial identifier |

### 2.2 Field Coverage by Module

| Module | Header project_code | Header serial_no | Line project_code | Line serial_no | Gap |
|---|---|---|---|---|---|
| Purchase requisition | - | - | (items have warehouse_id but no line_project_code in 20260528_002) | - | **Gap: purchase_requisition_items lacks line_project_code / line_serial_no** |
| Purchase order | YES | YES | YES | YES | OK |
| Purchase receipt | source_type only | - | - | - | **Gap: purchase_receipts lacks explicit project_code/serial_no columns** |
| Purchase invoice | YES | YES | (items have source_doc_*) | - | **Gap: purchase_invoice_items lacks line_project_code/line_serial_no** |
| Sales quotation | YES | YES | - | - | **Gap: quotation line items lack trace fields** |
| Sales order | YES | YES | YES | YES | OK |
| Sales shipment | YES | YES | - | - | **Gap: shipment line items lack trace fields** |
| Sales return | YES | YES | - | - | **Gap: return line items lack trace fields** |
| Sales invoice | YES | YES | (items have source_doc_*) | - | **Gap: sales_invoice_items lacks line_project_code/line_serial_no** |
| Inventory adjustment | YES | YES | YES (line_project_code) | - | **Gap: adjustments lack line_serial_no** |
| Transfer order | YES | - | YES | - | **Gap: transfer lacks header serial_no and line_serial_no** |
| Inventory check | YES | - | YES | - | **Gap: check lacks header serial_no and line_serial_no** |
| Inventory assembly | - | YES | YES | - | **Gap: assembly lacks header project_code and line_serial_no** |
| Stock transaction | YES | YES | (source_line_no) | - | OK (transaction is line-level by nature) |
| Subcontract order | YES | YES | YES | YES | OK |
| Subcontract issue | - | - | YES (lines) | YES (lines) | **Gap: header lacks project_code/serial_no** |
| Subcontract receive | - | - | YES (lines) | YES (lines) | **Gap: header lacks project_code/serial_no** |
| Work order | YES | YES | YES | YES | OK |
| Pick list | YES | YES | YES | YES | OK |
| Operation report | - | - | - | - | **Gap: operation_reports lacks project_code/serial_no entirely** |
| Production completion | YES | YES | - | - | OK (single-product completion) |
| Service card | YES | YES | - | - | OK (card is machine-level) |
| Service order | YES | YES | YES (items) | YES (items) | OK |
| Service RMA | - | - | YES | YES | **Gap: RMA header lacks project_code/serial_no** |
| Service acceptance | YES | YES | - | - | OK |
| Customer receivable | YES | YES | (items have source_doc_*) | - | OK (header-level sufficient) |
| Supplier payable | YES | YES | (items have source_doc_*) | - | OK |
| Customer receipt | YES | YES | - | - | OK |
| Supplier payment | YES | YES | - | - | OK |
| Cash bank journal | YES | YES | - | - | OK |
| Voucher / Voucher line | - | - | YES (lines) | YES (lines) | OK |
| General ledger | YES | YES | - | - | OK |
| Project cost ledger | YES (NOT NULL) | - | - | - | OK (project-level by design) |
| Serial cost ledger | YES | YES (NOT NULL) | - | - | OK (serial-level by design) |

### 2.3 Naming Inconsistency Findings

1. **Header vs line split is inconsistent.** Some documents carry trace fields only on header (sales_shipment, sales_return, customer_receipt), others only on lines (subcontract_issue/receive, service RMA), others on both (purchase_order, sales_order, work_order, pick_list). There is no rule that says when a field belongs on header vs line.
2. **`project_id` (INTEGER FK) vs `project_code` (VARCHAR).** `machine_serial_masters` uses both: `project_id` (FK to project_masters.id) and `project_code` (denormalized string). All other tables use only `project_code` string. This creates a dual-key ambiguity for project identity.
3. **`source_type` vs `source_doc_type`.** Both exist. `source_type` is the older convention (sales_shipments, customer_receipts, supplier_payments, vouchers, general_ledger, cash_bank_journal_entries, stock_transactions). `source_doc_type` is the newer convention (customer_receivable_items, supplier_payable_items, sales_invoice_items, purchase_invoice_items, stock_transactions, wo_complete_items). `stock_transactions` has BOTH columns. `supplier_payables` has BOTH `doc_type` and `source_type`. This is the second-largest consistency risk.
4. **`source_id` vs `source_doc_id`.** Same dual convention. Older tables use `source_id`, newer item tables use `source_doc_id` plus `source_doc_line_id`.
5. **No `machine_serial_no` column exists** despite AGENTS.md narrative mentioning it. The actual column is `serial_no`. Documentation and code must align on `serial_no`.
6. **`line_serial_no` is missing from many line tables** that have `line_project_code` (inventory adjustments, transfer orders, inventory check, inventory assembly). For machine-tool manufacturing where a single project may have multiple machine serials, line-level serial is needed when one document serves multiple machines.

### 2.4 Traceability Field Gaps Summary (P0-1 candidates, NOT to be implemented in Stage A)

- purchase_requisition_items: add line_project_code, line_serial_no
- purchase_receipts: add project_code, serial_no (header)
- purchase_invoice_items: add line_project_code, line_serial_no
- quotation line items: add line_project_code, line_serial_no
- sales_shipment line items: add line_project_code, line_serial_no
- sales_return line items: add line_project_code, line_serial_no
- sales_invoice_items: add line_project_code, line_serial_no
- inventory_adjustments: add line_serial_no
- transfer_orders: add serial_no (header); transfer_order_items: add line_serial_no
- inventory_check_orders: add serial_no (header); items: add line_serial_no
- inventory_assembly_orders: add project_code (header); items: add line_serial_no
- subcontract_issue_orders: add project_code, serial_no (header)
- subcontract_receive_orders: add project_code, serial_no (header)
- operation_reports: add project_code, serial_no
- machine_service_rmas: add project_code, serial_no (header)

These gaps are recorded for a future P0-1 migration decision. **Stage A does not write any migration.**

---

## 3. Document Type Code Draft (doc_type)

### 3.1 Current State

The codebase has **no single doc_type registry**. Instead, document identity is spread across:
- `source_type` VARCHAR(80) on older tables (values: `sales_order`, `sales_shipment`, `sales_invoice`, `purchase_order`, `purchase_receipt`, `purchase_invoice`, `customer_receipt`, `supplier_payment`, `customer_receivable`, `exchange_adjustment`, `period_close`, `inventory_costing`, `subcontract_receive`)
- `source_doc_type` VARCHAR(80) on newer item tables (values not yet populated consistently)
- `doc_type` VARCHAR(80) on `supplier_payables` (values: `purchase_order`, `purchase_receipt`, `subcontract_order`, `subcontract_receipt`)
- `doc_type` VARCHAR(60) on `pick_lists` (values not yet enforced)
- Hardcoded Chinese strings in `stock_transactions.source_type` (e.g. completion-inbound, completion-inbound-reversal) - **inconsistent with English snake_case convention used elsewhere**
- `tx_type` on stock_transactions (`inbound`, `outbound`, etc.)

### 3.2 Proposed Unified doc_type Registry (draft, NOT to be implemented)

All document types use lowercase snake_case, grouped by module prefix. This becomes the canonical enum for `trace_links.source_doc_type` and `trace_links.target_doc_type`.

The Chinese operator-facing label for each doc_type is maintained in the UI layer (templates / labels), NOT in this design document, to avoid encoding damage. The English doc_type code is the canonical key.

#### Purchase (prefix `purchase_`)
| doc_type | English label | Table | Direction |
|---|---|---|---|
| `purchase_requisition` | Purchase requisition | purchase_requisitions | Source for purchase_order |
| `purchase_order` | Purchase order | purchase_orders | Source for purchase_receipt |
| `purchase_receipt` | Purchase receipt | purchase_receipts | Source for stock_transaction (inbound), purchase_invoice |
| `purchase_invoice` | Purchase invoice | purchase_invoices | Source for supplier_payable |
| `purchase_return` | Purchase return | (if exists) | Source for stock_transaction (outbound) |

#### Sales (prefix `sales_`)
| doc_type | English label | Table | Direction |
|---|---|---|---|
| `sales_quotation` | Sales quotation | quotation_headers | Optional source for sales_order |
| `sales_order` | Sales order | sales_orders | Source for sales_shipment, sales_invoice, machine_service_card |
| `sales_shipment` | Sales shipment | sales_shipments | Source for stock_transaction (outbound), customer_receivable |
| `sales_return` | Sales return | sales_returns | Source for stock_transaction (inbound) |
| `sales_invoice` | Sales invoice | sales_invoices | Source for customer_receivable |

#### Inventory (prefix `inventory_`)
| doc_type | English label | Table | Direction |
|---|---|---|---|
| `inventory_receipt` | Inbound receipt | (receipt doc) | Source for stock_transaction (inbound) |
| `inventory_issue` | Outbound issue | (issue doc) | Source for stock_transaction (outbound) |
| `inventory_transfer` | Transfer order | transfer_orders | Source for stock_transaction (transfer) |
| `inventory_adjustment` | Adjustment order | inventory_adjustment_orders | Source for stock_transaction (adjust) |
| `inventory_check` | Check order | inventory_check_orders | Source for stock_transaction (adjust) |
| `inventory_assembly` | Assembly order | inventory_assembly_orders | Source for stock_transaction (assembly) |
| `inventory_movement` | Stock movement | stock_transactions | Leaf transaction (no downstream doc, but linked to cost ledger) |

#### Outsourcing (prefix `subcontract_`)
| doc_type | English label | Table | Direction |
|---|---|---|---|
| `subcontract_order` | Subcontract order | subcontract_orders | Source for subcontract_issue, subcontract_receive |
| `subcontract_issue` | Subcontract issue | subcontract_issue_orders | Source for stock_transaction (outbound) |
| `subcontract_receive` | Subcontract receive | subcontract_receive_orders | Source for stock_transaction (inbound), supplier_payable |

#### Production (prefix `production_`)
| doc_type | English label | Table | Direction |
|---|---|---|---|
| `work_order` | Work order | work_orders | Source for pick_list, operation_report, production_completion, subcontract_order |
| `pick_list` | Pick list | pick_lists | Source for stock_transaction (outbound) |
| `operation_report` | Operation report | operation_reports | Source for production_completion, work_order_cost |
| `production_completion` | Production completion | production_completion_orders | Source for stock_transaction (inbound), work_order_cost |
| `work_order_cost` | Work order cost | work_order_costs | Leaf cost record |

#### Service (prefix `service_`)
| doc_type | English label | Table | Direction |
|---|---|---|---|
| `service_card` | Service card | machine_service_cards | Source for service_order, RMA; links to sales_order |
| `service_order` | Service order | machine_service_orders | Source for stock_transaction, service_fee |
| `service_rma` | RMA | machine_service_rmas | Source for stock_transaction |
| `service_acceptance` | Installation acceptance | machine_service_acceptance_checks | Updates machine_serial_masters.service_status |

#### Finance (prefix `finance_`)
| doc_type | English label | Table | Direction |
|---|---|---|---|
| `customer_receivable` | Customer receivable | customer_receivables | Settled by customer_receipt |
| `supplier_payable` | Supplier payable | supplier_payables | Settled by supplier_payment |
| `customer_receipt` | Customer receipt | customer_receipts | Settles receivable; source for voucher, cash_bank_journal |
| `supplier_payment` | Supplier payment | supplier_payments | Settles payable; source for voucher, cash_bank_journal |
| `sales_invoice` | Sales invoice | sales_invoices | (shared with sales module) |
| `purchase_invoice` | Purchase invoice | purchase_invoices | (shared with purchase module) |
| `voucher` | Voucher | vouchers | Source for general_ledger |
| `exchange_adjustment` | Exchange adjustment | finance_exchange_adjustments | Source for voucher |
| `period_close` | Period close | finance_period_closes | Source for voucher |

#### Traceability master
| doc_type | English label | Table |
|---|---|---|
| `project_master` | Project master | project_masters |
| `machine_serial_master` | Machine serial master | machine_serial_masters |

### 3.3 Migration Strategy for doc_type (NOT in Stage A)

When P0-1 implementation is approved:
1. Add a `doc_type` column to every document table that lacks one, defaulting to the canonical value above.
2. Backfill `doc_type` from existing `source_type` / `source_doc_type` / `tx_type` using a mapping table.
3. Replace Chinese strings in `stock_transactions.source_type` with canonical English codes; keep Chinese only in `tx_type` description and UI labels.
4. Do NOT remove `source_type` / `source_doc_type` columns in P0-1 - keep them as aliases and deprecate gradually.

---

## 4. Existing Upstream/Downstream Document Relationships

### 4.1 Purchase Loop

```
purchase_requisition
    -> purchase_order
            -> purchase_receipt
                    -> stock_transaction (inbound)
                    -> inventory_balances (update)
                    -> purchase_invoice
                            -> supplier_payable
                                    -> supplier_payment
                                            -> supplier_payment_settlement (settles payable)
                                            -> voucher (auto)
                                            -> cash_bank_journal_entry
```

**Current linkage mechanism:**
- `purchase_orders.source_type` not set; `purchase_order_items.source_line_no` links back to requisition line.
- `purchase_receipts.source_type='purchase_order'`, `source_id`, `source_no` link back to PO.
- `purchase_invoices.source_type`, `source_id`, `source_no` link back to receipt or order.
- `supplier_payables.doc_type='purchase_order'` or `'purchase_receipt'` or `'purchase_invoice'`, with `doc_id`, `doc_no`.
- `supplier_payment_settlements` links payment to payable.

**Gap:** No forward link from purchase_order to its downstream receipts. Traceability currently requires reverse queries.

### 4.2 Sales Loop

```
sales_quotation (optional)
    -> sales_order
            -> sales_shipment
                    -> stock_transaction (outbound)
                    -> customer_receivable
                            -> customer_receipt
                                    -> customer_receipt_settlement
                                    -> voucher (auto)
                                    -> cash_bank_journal_entry
            -> sales_invoice
                    -> customer_receivable
            -> machine_service_card (post-shipment service anchor)
                    -> service_order / service_rma
```

**Current linkage mechanism:**
- `sales_shipments.source_type='sales_order'`, `source_id`, `source_no`.
- `customer_receivables.source_type='sales_order'` or `'sales_shipment'` or `'sales_invoice'`, with `source_id`, `source_no`.
- `machine_service_cards.sales_order_id` links card to originating order.

**Gap:** No forward link from sales_order to shipments/invoices. Quotation-to-order link is via `source_no` only (no `source_id`).

### 4.3 Production Loop

```
sales_order / project_master / machine_serial_master
    -> work_order
            -> pick_list
                    -> stock_transaction (outbound)
            -> operation_report
                    -> work_order_cost
            -> production_completion
                    -> stock_transaction (inbound)
                    -> work_order_cost
            -> subcontract_order (parent_work_order_id)
                    -> subcontract_issue
                            -> stock_transaction (outbound)
                    -> subcontract_receive
                            -> stock_transaction (inbound)
                            -> supplier_payable
```

**Current linkage mechanism:**
- `work_orders` carry project_code, serial_no, and (via `line_project_code`/`line_serial_no`) line-level trace.
- `pick_lists.work_order_id`, `pick_list_items.wo_material_item_id`.
- `operation_reports.work_order_id`, `work_order_process_id`.
- `production_completion_orders.work_order_id`, `wo_complete_item_id`.
- `subcontract_orders.parent_work_order_id`.
- `work_order_costs.work_order_id`.

**Gap:** No forward link from work_order to its pick lists / operation reports / completions. No link from operation_report to production_completion (only via `wo_complete_item_id` which is a line FK, not a doc-level link).

### 4.4 Service Loop

```
sales_order
    -> machine_service_card (sales_order_id, serial_no)
            -> machine_service_acceptance_check (updates service_status)
            -> machine_service_order
                    -> stock_transaction (issue/return)
            -> machine_service_rma
                    -> stock_transaction (inbound)
```

**Current linkage mechanism:**
- `machine_service_cards.sales_order_id`, `serial_no` (unique index on pair).
- `machine_service_orders.project_code`, `serial_no`.
- `machine_service_rmas.line_project_code`, `line_serial_no`.

**Gap:** No explicit `service_card_id` FK on service_order or RMA. Linkage is via serial_no string match only.

### 4.5 Finance Posting Loop

```
Any business document (sales_invoice, purchase_invoice, customer_receipt, supplier_payment, exchange_adjustment, period_close)
    -> voucher (source_type, source_id, source_no)
            -> voucher_lines
                    -> general_ledger (source_type, source_id, source_no, project_code, serial_no)
```

**Current linkage mechanism:**
- `vouchers.source_type`, `source_id`, `source_no`.
- `voucher_lines.source_type`, `source_id`, `source_no`, `project_code`, `serial_no`.
- `general_ledger.source_type`, `source_id`, `source_no`, `project_code`, `serial_no`.

**Gap:** `source_type` values are not from a controlled registry (see section 3.1). GL lines inherit project_code/serial_no from voucher lines, but there is no validation that they match the originating business document.

### 4.6 Cost Traceability Loop

```
project_master / machine_serial_master
    -> project_cost_ledger (project_code NOT NULL)
    -> serial_cost_ledger (serial_no NOT NULL, project_code)
            sourced from:
            - stock_transactions (inventory cost)
            - work_order_costs (production cost)
            - supplier_payables (subcontract cost)
            - customer_receivables (revenue)
```

**Current linkage mechanism:**
- `project_cost_ledger.source_type`, `source_no` (string reference, no `source_id`).
- `serial_cost_ledger.source_type`, `source_no` (string reference, no `source_id`).

**Gap:** Cost ledger has no `source_id` INTEGER FK, only `source_no` string. Cannot reliably join back to source document if doc_no is duplicated or renamed.

---

## 5. P0-2 Traceability Engine Boundary Definition

### 5.1 Business Loop Boundary

**In scope (P0-2 traceability engine):**
- Read-only traversal of document relationships defined in section 4.
- Forward and reverse link discovery: given a doc_type + doc_id, return all upstream sources and downstream targets.
- Project/serial-centric view: given a project_code or serial_no, return all documents and transactions touching it.
- Snapshot capture: at the moment a document is posted/audited, capture a read-only snapshot of its header, lines, and trace context for later reconstruction.
- Trace query API for workbench queues, exception lists, and audit (no new UI pages in Stage A).

**Out of scope (P0-2):**
- MRP calculation (see section 7).
- Cost engine / cost rollup (see section 7).
- BOM snapshot versioning (see section 7).
- Row-level data permission enforcement (see section 7).
- New report pages, new menu entries (see section 7).
- Writing or mutating any business document. The traceability engine is read-only with respect to business documents; it only writes to `trace_links` and `trace_snapshots` (its own tables).
- Replacing existing `source_type` / `source_doc_type` columns. The engine reads them but does not modify them.

### 5.2 Page Type

- **Internal query service**: no operator-facing page in Stage A. Exposed only as a service-layer API consumed by existing workbench, document detail, and audit pages.
- **Future (post Stage A)**: a read-only trace query page classified as `internal` in `MENU_ROLLOUT_CLASSIFICATION.md`, reachable only by admin/audit roles. This page is NOT authorized by this design document.

### 5.3 Route Exposure

- **Stage A**: No new Flask route. The traceability engine is a Python service module (`services/trace_engine.py` - to be created in a future stage, NOT in Stage A) called by existing route handlers.
- **Future**: A `/trace/query` route may be added in a later stage, classified `internal`, registered in `services/pilot_permissions.py`, catalogued in `routes/route_catalog.py`, and audited by `audit_trial_visible_navigation.py`. This route is NOT authorized by this design document.

### 5.4 Data Owner

- **trace_links / trace_snapshots tables**: owned by the traceability engine service. No other module may INSERT/UPDATE/DELETE these tables directly.
- **Source business documents**: remain owned by their respective modules (purchase, sales, inventory, production, service, finance). The traceability engine only reads them.
- **project_code / serial_no values**: owned by the originating document. The traceability engine does not normalize or rewrite them; it only records what the source document carried at snapshot time.

### 5.5 Upstream Source Documents

The traceability engine consumes (read-only):
- All document tables listed in section 1.3.
- `project_masters`, `machine_serial_masters`.
- `stock_transactions`, `inventory_balances`, `batch_tracking`.
- `vouchers`, `voucher_lines`, `general_ledger`.
- `project_cost_ledger`, `serial_cost_ledger`.

### 5.6 Downstream Impact

- **Stage A**: None. Read-only analysis only.
- **Future P0-2 implementation**: The engine will write to `trace_links` and `trace_snapshots` at document post/audit events. This adds two tables and triggers on existing posting services (`services/inventory_posting_service.py`, `services/payable_posting_service.py`, `services/receivable_posting_service.py`, `services/voucher_generation_service.py`). No existing business document table is altered.
- **Workbench impact**: Existing workbench pages may consume the trace query API to surface "upstream source" and "downstream impact" columns. This is a read-only enhancement and does not change workbench write actions.

### 5.7 Acceptance Checks (for future P0-2 implementation, NOT Stage A)

- Given a `sales_order` id, the engine returns all shipments, invoices, receivables, receipts, service cards, and GL lines linked to it.
- Given a `work_order` id, the engine returns its pick lists, operation reports, completions, subcontract orders, and cost records.
- Given a `project_code`, the engine returns all documents and transactions carrying that project_code across all modules.
- Given a `serial_no`, the engine returns all documents and transactions carrying that serial_no, plus the machine_serial_master record.
- Given a `stock_transaction` id, the engine returns its source document and any downstream cost ledger entries.
- Snapshot reconstruction: given a document id and a snapshot timestamp, the engine returns the document header, lines, and trace context as it existed at that timestamp.
- Trace integrity audit: for every document with `source_type` + `source_id`, a corresponding `trace_links` row exists. A new audit script `scripts/audit_trace_links_integrity.py` (to be created when P0-2 is implemented, NOT in Stage A) reports any missing links.
- All existing audit scripts (`source_integrity_audit.py`, `erp_prelaunch_audit.py`, `audit_erp_crud_completeness.py`, `audit_inventory_balance_consistency.py`, `audit_trial_visible_navigation.py`, `audit_trial_direct_access_matrix.py`) continue to pass with their current expected outputs.

---

## 6. trace_links / trace_snapshots Table Structure Draft

**This is a design draft only. No migration is written in Stage A.** When P0-2 implementation is approved, the DDL goes into `services/schema_migrations.py` after a `scripts/pg_backup.py --output backups/pre_migration_trace_engine.dump` backup.

### 6.1 Link Direction Rule (MANDATORY)

All `trace_links` rows MUST follow this direction convention:

- **source_doc** = the upstream / original document (the document that exists first, that was created earlier in the business loop, or that is being acted upon).
- **target_doc** = the downstream / generated / action document (the document that was created later, derived from the source, or performing an action on the source).

The `link_type` field describes the action the **target** performs relative to the **source**:

| link_type | Meaning (target does X to source) | Example (source -> target) |
|---|---|---|
| `source_of` | Target was created/sourced from source | sales_order -> sales_shipment |
| `settles` | Target settles source (financial settlement) | customer_receivable -> customer_receipt |
| `reverses` | Target reverses source (red invoice, void) | original_invoice -> red_invoice |
| `replaces` | Target replaces source (ECN replaces original) | bom -> bom_engineering_change |
| `posts_to` | Target is the accounting posting generated from source | sales_invoice -> voucher |
| `dispatches_to` | Target is a dispatch/allocation generated from source | work_order -> pick_list |
| `returns_to` | Target is a return generated against source | sales_shipment -> sales_return |

**Direction verification checklist (every link must satisfy):**
1. sales_order -> sales_shipment (source_of): order exists first, shipment is generated from it. OK.
2. sales_invoice -> customer_receivable (source_of): invoice exists first, receivable is generated from it. OK.
3. customer_receivable -> customer_receipt (settles): receivable exists first (the open AR), receipt is the action that settles it. OK.
4. original_invoice -> red_invoice (reverses): original exists first, red invoice is the reversal action. OK.
5. sales_invoice -> voucher (posts_to): invoice exists first, voucher is the accounting posting generated from it. OK.
6. work_order -> pick_list (dispatches_to): work order exists first, pick list is the material dispatch generated from it. OK.
7. sales_shipment -> sales_return (returns_to): shipment exists first, return is the return action against it. OK.

### 6.2 trace_links

Purpose: directed graph of document-to-document relationships. One row per (source_doc, target_doc) edge.

```sql
CREATE TABLE IF NOT EXISTS trace_links (
    id SERIAL PRIMARY KEY,
    source_doc_type VARCHAR(80) NOT NULL,          -- canonical doc_type from section 3.2
    source_doc_id INTEGER NOT NULL,                 -- PK of source (upstream/original) document
    source_doc_no VARCHAR(120),                     -- denormalized for query convenience
    source_line_id INTEGER,                         -- NULL for header-level link
    source_line_no VARCHAR(80),                     -- denormalized line number
    target_doc_type VARCHAR(80) NOT NULL,
    target_doc_id INTEGER NOT NULL,                 -- PK of target (downstream/action) document
    target_doc_no VARCHAR(120),
    target_line_id INTEGER,                         -- NULL for header-level link
    target_line_no VARCHAR(80),
    link_type VARCHAR(40) NOT NULL,                 -- see section 6.1 link direction rule
    link_strength VARCHAR(20) NOT NULL DEFAULT 'hard',  -- 'hard' = FK-backed, 'soft' = string match only
    project_code VARCHAR(120),                      -- denormalized from source for project-centric query
    serial_no VARCHAR(120),                         -- denormalized from source for serial-centric query
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,                             -- user or system action that created the link
    created_event VARCHAR(80)                       -- 'post' | 'audit' | 'settle' | 'reverse' | 'void'
);
```

**Indexes:**

```sql
-- Primary query patterns
CREATE INDEX IF NOT EXISTS idx_trace_links_source ON trace_links(source_doc_type, source_doc_id);
CREATE INDEX IF NOT EXISTS idx_trace_links_target ON trace_links(target_doc_type, target_doc_id);
CREATE INDEX IF NOT EXISTS idx_trace_links_project ON trace_links(project_code) WHERE project_code IS NOT NULL AND project_code <> '';
CREATE INDEX IF NOT EXISTS idx_trace_links_serial ON trace_links(serial_no) WHERE serial_no IS NOT NULL AND serial_no <> '';
CREATE INDEX IF NOT EXISTS idx_trace_links_source_line ON trace_links(source_doc_type, source_line_id) WHERE source_line_id IS NOT NULL;
```

**Unique constraint - NULL-safe edge deduplication:**

PostgreSQL treats NULL as distinct in UNIQUE indexes, so a naive unique index on `(source_doc_type, source_doc_id, source_line_id, target_doc_type, target_doc_id, target_line_id, link_type)` would allow duplicate header-level edges (where both line_ids are NULL). The design below uses `COALESCE(line_id, 0)` in an expression unique index so that NULL line_ids are treated as the same value (0), preventing duplicate edges regardless of whether the link is header-level or line-level.

```sql
-- Single NULL-safe unique index covering both header-level and line-level edges.
-- COALESCE maps NULL line_ids to 0 so that two header-level edges with the same
-- (source, target, link_type) are treated as duplicates and rejected.
CREATE UNIQUE INDEX IF NOT EXISTS uq_trace_links_edge
    ON trace_links(
        source_doc_type,
        source_doc_id,
        COALESCE(source_line_id, 0),
        target_doc_type,
        target_doc_id,
        COALESCE(target_line_id, 0),
        link_type
    );
```

**Why COALESCE over alternatives:**
- `NULLS NOT DISTINCT` (PostgreSQL 15+): requires PostgreSQL 15 minimum, which may not be the deployed version. COALESCE works on PostgreSQL 9.5+.
- Splitting into four partial indexes (header/header, line/line, header/line, line/header): correct but verbose, harder to maintain, and easy to get wrong when a new link pattern is added. A single COALESCE expression index is simpler and covers all four cases in one constraint.
- COALESCE(line_id, 0) is safe because line_id is a SERIAL-derived INTEGER primary key on line tables, so 0 is never a valid line_id value.

**Write timing:**
- INSERT only. Never UPDATE or DELETE (audit immutability).
- Written by the traceability engine service at the same transaction as the business event that creates the link (e.g. when a purchase_receipt is posted, the engine inserts a `source_of` link from purchase_order to purchase_receipt within the same `db_transaction`).
- Reversal/void does NOT delete the original link; it inserts a new `reverses` link from the original document to the reversal document.

### 6.3 trace_snapshots

Purpose: point-in-time read-only capture of a document's header, lines, and trace context at the moment of a state transition (post, audit, reverse, void). Enables reconstruction even if the source document is later edited or deleted.

```sql
CREATE TABLE IF NOT EXISTS trace_snapshots (
    id SERIAL PRIMARY KEY,
    doc_type VARCHAR(80) NOT NULL,
    doc_id INTEGER NOT NULL,
    doc_no VARCHAR(120),
    snapshot_event VARCHAR(40) NOT NULL,            -- 'post' | 'audit' | 'reverse' | 'void' | 'settle' | 'close'
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    snapshot_by INTEGER,                            -- user id
    project_code VARCHAR(120),
    serial_no VARCHAR(120),
    header_payload JSONB NOT NULL,                  -- full header row as JSON
    lines_payload JSONB NOT NULL DEFAULT '[]',      -- array of line rows as JSON
    trace_context_payload JSONB NOT NULL DEFAULT '{}',  -- summary of upstream/downstream links at snapshot time
    source_hash CHAR(64),                           -- SHA-256 of (header_payload + lines_payload) for tamper detection
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trace_snapshots_doc ON trace_snapshots(doc_type, doc_id);
CREATE INDEX IF NOT EXISTS idx_trace_snapshots_doc_no ON trace_snapshots(doc_type, doc_no);
CREATE INDEX IF NOT EXISTS idx_trace_snapshots_project ON trace_snapshots(project_code) WHERE project_code IS NOT NULL AND project_code <> '';
CREATE INDEX IF NOT EXISTS idx_trace_snapshots_serial ON trace_snapshots(serial_no) WHERE serial_no IS NOT NULL AND serial_no <> '';
CREATE INDEX IF NOT EXISTS idx_trace_snapshots_event ON trace_snapshots(doc_type, doc_id, snapshot_event);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trace_snapshots_event
    ON trace_snapshots(doc_type, doc_id, snapshot_event, snapshot_at);
```

**Write timing:**
- INSERT only. Never UPDATE or DELETE.
- Written by the traceability engine service at the same transaction as the state transition event.
- `header_payload` and `lines_payload` are JSONB captures of the document row(s) at snapshot time. Schema is intentionally flexible to accommodate all document types without altering the table.
- `trace_context_payload` captures a summary of upstream source documents and known downstream documents at snapshot time, so reconstruction does not depend on the live `trace_links` table (which may have later additions).
- `source_hash` is computed by the engine before insert. A future audit script can recompute the hash from `header_payload` + `lines_payload` to detect tampering.

**Storage estimate:** Each snapshot is roughly 2-10 KB JSONB. For an estimated 1000 documents/month with 3 events each, annual storage is ~360 MB. Acceptable for Postgres JSONB.

### 6.4 Relationship Between trace_links and trace_snapshots

- `trace_links` is the live graph: always current, supports forward/reverse traversal.
- `trace_snapshots` is the historical record: immutable, supports point-in-time reconstruction.
- They are independent. A link may exist without a snapshot (e.g. soft links backfilled from existing `source_type` columns). A snapshot may exist without a new link (e.g. an audit event on a document with no new downstream).
- Both tables are owned by the traceability engine service. No other module writes to them.

### 6.5 Backfill Strategy (for future P0-2 implementation, NOT Stage A)

When P0-2 is implemented:
1. Run a one-time backfill script that reads every document table's `source_type` / `source_doc_type` / `source_id` / `source_doc_id` / `source_no` / `source_doc_no` columns and inserts corresponding `trace_links` rows with `link_type='source_of'` and `link_strength='hard'` (where INTEGER FK exists) or `'soft'` (where only string match exists).
2. For documents with `project_code` / `serial_no` but no explicit source link, insert a `source_of` link from `project_master` or `machine_serial_master` to the document.
3. Do NOT backfill `trace_snapshots` for historical documents - snapshots begin from the P0-2 go-live event forward. Historical reconstruction relies on `trace_links` + live document tables.

---

## 7. Explicitly Out of Scope

The following are explicitly excluded from P0 Stage A and P0-2 implementation unless the user issues a separate written request:

1. **MRP (Material Requirements Planning)** - no BOM explosion, no net requirement calculation, no planned order generation. The traceability engine only records existing document relationships; it does not compute future requirements.
2. **Cost engine / cost rollup** - no standard cost recompute, no actual cost allocation, no variance analysis. `project_cost_ledger` and `serial_cost_ledger` remain as-is; the traceability engine reads them but does not write them.
3. **BOM snapshot versioning** - no BOM version freeze at work-order release, no BOM-as-of-date query. BOM ECN (`bom_engineering_changes`) remains the only change-control mechanism.
4. **Row-level data permission (RLS)** - the traceability engine does not enforce per-user document visibility. Role-group permissions remain the only access control. Row-level enforcement is a separate security project.
5. **New report pages** - no new operator-facing report. The trace query API is internal only.
6. **New menu entries** - no additions to `MENU_ROLLOUT_CLASSIFICATION.md` or navigation. The future `/trace/query` route, if ever added, requires a separate boundary definition and user approval.
7. **New database tables other than trace_links / trace_snapshots** - no other schema additions.
8. **New routes** - no Flask route additions in Stage A.
9. **Audit script modifications** - no edits to `scripts/audit_*.py`, `scripts/verify_*.py`, `scripts/validate_*.py`, or `scripts/erp_prelaunch_audit.py`.
10. **Migration execution** - no DDL is run in Stage A. The section 6 drafts are design only.
11. **Doc_type registry enforcement** - the section 3.2 registry is a draft. No code change enforces it in Stage A. Existing `source_type` / `source_doc_type` values remain as-is.
12. **Field renaming** - the section 2.3 naming inconsistencies are recorded but not fixed. `project_id` vs `project_code`, `source_type` vs `source_doc_type`, `source_id` vs `source_doc_id` all remain as-is.

---

## 8. Stage A Deliverable Confirmation

This document is the sole deliverable of P0 Stage A. It is read-only analysis. No file other than this document was created or modified. No migration, route, page, menu, audit script, or business code was changed.

Next stage (P0-1 / P0-2 implementation) requires explicit user approval of this boundary definition before any code or migration work begins.
