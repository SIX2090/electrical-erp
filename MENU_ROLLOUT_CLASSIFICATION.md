# Menu Rollout Classification

This file classifies normal-menu and direct routes by page type and rollout state.

| Route | Page Type | State | Owner | Notes |
|---|---|---|---|---|
| `/help/assistant` | system help | readonly | system | Read-only operation assistant page; answers from the operation manual and does not create, audit, post, reconcile, or mutate business data. |
| `/help/operation-manual` | system help | readonly | system | Read-only ERP operation manual page; documents existing workflows and links to existing pages only. |
| `/api/ai-assistant/help` | internal help API | readonly | system | Authenticated read-only helper endpoint for the operation assistant page; returns manual guidance only and does not mutate business data. |
| `/project-delivery-workbench` | workbench | live | sales/project | Project delivery workbench; shows flow nodes, exception queues, owner, next action, and downstream impact only; it must not render full document lists. |
| `/purchase` | workbench | `live` | purchase | Purchase workbench/root route; shows purchase follow-up queues and exception summaries only, not a replacement for purchase document lists. |
| `/production` | workbench | `live` | production | Production workbench/root route; shows production execution queues, blockers, owners, and next actions only, not a full work-order list. |
| `/service` | workbench | `live` | service | Service workbench/root route; shows after-sale queues, exceptions, cost links, and RMA follow-up only, not full service document editing. |
| `/master-data` | workbench | `live` | master data | Master-data quality workbench; shows reference-data maintenance queues and health cues only, not business document execution. |
| `/users` | system admin | live | system | User account maintenance for administrators and managers; supports create, password reset, status control, and deletion of disabled accounts only. |
| `/users/add` | system admin action | live | system | User creation endpoint; not exposed to business roles. |
| `/users/reset-password` | system admin action | live | system | Password reset endpoint for existing users; not exposed to business roles. |
| `/users/status` | system admin action | live | system | User enable/disable endpoint; current user cannot disable the active account from the UI. |
| `/users/delete` | system admin action | live | system | Deletes selected disabled/inactive users only; not a business-record deletion path. |
| `/permissions/roles` | system admin | live | system | Pilot role permission matrix; changes affect menu visibility and direct access expectations. |
| `/operation_logs` | system admin query | readonly | system | Operation log query/list for audit trace; cleanup is a system-admin action. |
| `/operation_logs/delete` | system admin action | live | system | Operation log cleanup endpoint restricted to admin and manager. |
| `/system_settings/form` | system admin | live | system | System parameter and code-rule maintenance; writes only existing system option and code-rule configuration. |
| `/system_settings/form/save` | system admin action | live | system | Saves known system parameters and code-rule rows; does not create business documents. |
| `/system_settings/form/test_ai_llm` | system admin action | live | system | Validates that AI assistant connection parameters are present; does not call external AI from this route. |
| `/system/opening-period` | system admin | live | system | Opening time and enabled period settings; saves the ERP go-live baseline in system options. |
| `/system/opening-period/save` | system admin action | live | system | Saves opening period, current finance period, opening dates, and lock/control flags; does not create business documents or post finance records. |
| `/system/doc-rules` | system admin | live | system | Dedicated document number rule settings; affects future generated document numbers only and does not rewrite historical documents. |
| `/system/doc-rules/save` | system admin action | live | system | Saves document number rule rows; no business document is created, audited, posted, or renumbered. |
| `/system/print-templates` | system admin | live | system | Print template list and maintenance entry; affects print rendering only. |
| `/system/print-templates/new` | system admin | live | system | Print template creation form/action; does not change business document data. |
| `/system/print-templates/<id>/edit` | system admin | live | system | Print template edit form/action for existing templates. |
| `/system/print-templates/<id>/preview` | system admin query | readonly | system | Print template preview route. |
| `/system/print-templates/<id>/set-default` | system admin action | live | system | Sets a document-type default print template. |
| `/system/print-templates/<id>/copy` | system admin action | live | system | Copies an existing print template for editing. |
| `/system/print-templates/<id>/toggle` | system admin action | live | system | Enables or disables a print template. |
| `/system/print-templates/<id>/delete` | system admin action | live | system | Deletes non-default, non-built-in print templates only. |
| `/system/database-backups` | system admin query | readonly | system | Backup status/list page for operational recovery readiness. |
| `/system/database-backups/run` | system admin action | live | system | Manual or pre-migration database backup endpoint; writes dump files under `backups/`. |
| `/system/version-updates` | system admin query | readonly | system | Version update package review page; reads local update package status and does not mutate business data. |
| `/system/version-updates/run` | system admin action | live | system | Controlled local version update execution endpoint; system-admin operation only and not a business document workflow. |
| `/system/data-health` | system admin query | readonly | system | System, security, route, backup, and master-data health dashboard; does not mutate business data. |
| `/system/data-health/master/<check_key>` | system admin query | readonly | system | Master-data health detail list; links operators back to existing master edit pages for treatment. |
| `/inventory/opening` | opening data | live | warehouse | Material opening balance entry/list for go-live initialization; not normal master archive maintenance. |
| `/inventory/opening/new` | opening data | live | warehouse | Material opening balance entry form/action; posts opening quantity through the existing inventory posting path only. |
| `/inventory` | workbench | live | warehouse | Inventory workbench; shows pending queues, exceptions, owner, next action, and downstream impact only, not a full balance ledger. |
| `/inventory/inbound` | document list | live | warehouse | Other inbound document list; grouped by doc_no on inventory_movement_documents, shows line count, quantity, cost amount, project/cabinet, status (draft/posted/void), and links to the detail page for audit. |
| `/inventory/inbound/new` | document entry | live | warehouse | Manual other inbound entry route; saves a draft header + lines to inventory_movement_documents and redirects to the detail page for audit. |
| `/inventory/inbound/<doc_no>` | document detail | live | warehouse | Other inbound detail; status-aware audit/unaudit actions; audit posts lines to stock_transactions and inventory_balances atomically; unaudit reverses them. |
| `/inventory/inbound/<doc_no>/audit` | document entry action | live | warehouse | Audit a draft other inbound document; promotes status to posted and posts every line through the inventory posting service. |
| `/inventory/inbound/<doc_no>/unaudit` | document entry action | live | warehouse | Reverse an audited other inbound document; reverses balance effects, removes posting stock_transactions rows, and resets status to draft. |
| `/inventory/inbound/<doc_no>/copy` | document entry action | live | warehouse | Copy an other inbound document to a new draft document number with the same line details; inventory is not posted until the copied document is audited. |
| `/inventory/outbound` | document list | live | warehouse | Other outbound document list; grouped by doc_no on inventory_movement_documents, shows line count, quantity, cost amount, project/cabinet, status (draft/posted/void), and links to the detail page for audit. |
| `/inventory/outbound/new` | document entry | live | warehouse | Manual other outbound entry route; saves a draft header + lines to inventory_movement_documents and redirects to the detail page for audit. |
| `/inventory/outbound/<doc_no>` | document detail | live | warehouse | Other outbound detail; status-aware audit/unaudit actions; audit posts lines to stock_transactions and inventory_balances atomically; unaudit reverses them. |
| `/inventory/outbound/<doc_no>/audit` | document entry action | live | warehouse | Audit a draft other outbound document; promotes status to posted and posts every line through the inventory posting service. |
| `/inventory/outbound/<doc_no>/unaudit` | document entry action | live | warehouse | Reverse an audited other outbound document; reverses balance effects, removes posting stock_transactions rows, and resets status to draft. |
| `/inventory/outbound/<doc_no>/copy` | document entry action | live | warehouse | Copy an other outbound document to a new draft document number with the same line details; inventory is not posted until the copied document is audited. |
| `/adjustments` | document list | live | warehouse | Inventory adjustment list; search, status, next action, detail links, and controlled bulk actions only. |
| `/adjustments/new` | document entry | live | warehouse | Inventory adjustment document entry; saves pending documents before posting. |
| `/adjustments/<id>` | document detail | live | warehouse | Inventory adjustment detail; status-aware post, close, cancel, print, attachments, and notes. |
| `/adjustments/<id>/edit` | document entry | live | warehouse | Inventory adjustment edit route for unposted documents only. |
| `/adjustments/<id>/delete` | document entry action | live | warehouse | Delete a draft inventory adjustment only after confirming it has no posted stock transactions; posted adjustments must be reversed before deletion. |
| `/adjustments/<id>/copy` | document entry action | live | warehouse | Copy an inventory adjustment into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/transfers` | document list | live | warehouse | Inventory transfer list; search, status, next action, detail links, and controlled bulk actions only. |
| `/stock_transfers` | document list | hidden | warehouse | Compatibility transfer list alias; normal navigation uses `/transfers`. |
| `/transfers/new` | document entry | live | warehouse | Inventory transfer document entry; posts transfer out and transfer in only after confirmation. |
| `/transfers/<id>` | document detail | live | warehouse | Inventory transfer detail; status-aware post, close, cancel, print, attachments, and notes. |
| `/transfers/<id>/edit` | document entry | live | warehouse | Inventory transfer edit route for unposted documents only. |
| `/transfers/<id>/delete` | document entry action | live | warehouse | Delete a draft inventory transfer only after confirming it has no posted stock transactions; posted transfers must be reversed before deletion. |
| `/transfers/<id>/copy` | document entry action | live | warehouse | Copy an inventory transfer into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/inventory_checks` | document list | live | warehouse | Inventory stock check list; search, status, next action, detail links, and controlled bulk actions only. |
| `/inventory_checks/new` | document entry | live | warehouse | Inventory stock check document entry; saves counted quantity before posting differences. |
| `/inventory_checks/<id>` | document detail | live | warehouse | Inventory stock check detail; status-aware post, close, cancel, print, attachments, and notes. |
| `/inventory_checks/<id>/edit` | document entry | live | warehouse | Inventory stock check edit route for unposted documents only. |
| `/inventory_checks/<id>/delete` | document entry action | live | warehouse | Delete a draft inventory stock check only after confirming it has no posted stock transactions; posted checks must be reversed before deletion. |
| `/inventory_checks/<id>/copy` | document entry action | live | warehouse | Copy an inventory stock check into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/assembly-orders` | document list | live | warehouse | Inventory assembly document list; separate from entry and report pages. |
| `/assembly-orders/new` | document entry | live | warehouse | Inventory assembly entry; posts component outbound and parent inbound only after confirmation. |
| `/assembly-orders/<id>` | document detail | live | warehouse | Inventory assembly detail; status-aware post, close, cancel, print, attachments, and notes. |
| `/assembly-orders/<id>/edit` | document entry | live | warehouse | Inventory assembly edit route for unposted documents only. |
| `/assembly-orders/<id>/delete` | document entry action | live | warehouse | Delete a draft assembly order only after confirming it has no posted stock transactions; posted assembly orders must be reversed before deletion. |
| `/assembly-orders/<id>/copy` | document entry action | live | warehouse | Copy an assembly order into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/disassembly-orders` | document list | live | warehouse | Inventory disassembly document list; separate from entry and report pages. |
| `/disassembly-orders/new` | document entry | live | warehouse | Inventory disassembly entry; posts parent outbound and component inbound only after confirmation. |
| `/disassembly-orders/<id>` | document detail | live | warehouse | Inventory disassembly detail; status-aware post, close, cancel, print, attachments, and notes. |
| `/disassembly-orders/<id>/edit` | document entry | live | warehouse | Inventory disassembly edit route for unposted documents only. |
| `/disassembly-orders/<id>/delete` | document entry action | live | warehouse | Delete a draft disassembly order only after confirming it has no posted stock transactions; posted disassembly orders must be reversed before deletion. |
| `/disassembly-orders/<id>/copy` | document entry action | live | warehouse | Copy a disassembly order into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/inventory/detail` | query list | readonly | warehouse | Inventory balance detail query by material, warehouse, location, lot, project, and cabinet number. |
| `/inventory/summary` | query list | readonly | warehouse | Inventory summary query; drill-down only, no document write actions. |
| `/inventory/aging` | query list | readonly | warehouse | Inventory aging query; drill-down/export only, no document write actions. |
| `/inventory/expiry` | query list | readonly | warehouse | Inventory expiry query; drill-down/export only, no document write actions. |
| `/transactions` | query list | readonly | warehouse | Stock transaction trace query; read-only source document and movement review. |
| `/inventory_alerts` | query list | readonly | warehouse | Inventory alert query; follow-up is handled through controlled documents. |
| `/inventory/reorder-suggestions` | query list | readonly | warehouse | Reorder suggestion query from inventory alert context; no direct purchase document creation here. |
| `/batch/tracking` | query list | readonly | warehouse | Batch and cabinet trace query; drill-down/export only. |
| `/batch_trace` | query list | hidden | warehouse | Compatibility batch trace alias; normal navigation uses `/batch/tracking`. |
| `/inventory/reports` | report | readonly | warehouse | Inventory report center; read-only released inventory reports and export only. |
| `/inventory/reports/shortage` | report | readonly | warehouse | Inventory shortage report; read-only analysis and export only. |
| `/inventory/reports/turnover` | report | readonly | warehouse | Inventory turnover report; read-only analysis and export only. |
| `/inventory/reports/batch-trace` | report | readonly | warehouse | Batch trace report; read-only analysis, drill-down, and export only. |
| `/inventory/reports/fund-occupation` | report | readonly | warehouse/finance | Inventory fund occupation report; no finance posting or cost allocation action. |
| `/inventory/reports/inout-summary` | report | readonly | warehouse | Inventory in/out summary report; read-only analysis and export only. |
| `/inventory/reports/ledger` | report | readonly | warehouse | Inventory ledger report; read-only reconciliation and export only. |
| `/inventory/reports/account-book` | report | readonly | warehouse | Inventory account book report; read-only reconciliation and export only. |
| `/inventory/reports/available-stock` | report | readonly | warehouse | Available stock report; read-only availability basis and export only. |
| `/inventory/reports/balance` | report | readonly | warehouse | Inventory balance report; read-only quantity/value basis and export only. |
| `/inventory/reports/check-difference` | report | readonly | warehouse | Inventory check difference report; read-only variance review and export only. |
| `/inventory/reports/inout-detail` | report | readonly | warehouse | Inventory in/out detail report; read-only source document analysis and export only. |
| `/inventory/reports/location-stock` | report | readonly | warehouse | Location stock report; read-only location balance analysis and export only. |
| `/inventory/reports/monthly` | report | readonly | warehouse | Monthly inventory report; read-only period summary and export only. |
| `/inventory/reports/project-occupation` | report | readonly | warehouse/project | Project inventory occupation report; read-only trace and export only. |
| `/inventory/reports/subcontract-wip` | report | readonly | purchase/outsourcing | Subcontract WIP inventory report; read-only execution analysis and export only. |
| `/inventory/reports/subcontract-execution` | report | readonly | purchase/outsourcing | Subcontract order execution report; read-only order, issue, receive, variance, and payable analysis. |
| `/inventory/reports/subcontract-inout-detail` | report | readonly | purchase/outsourcing | Subcontract issue/receive detail report; read-only subcontract material movement analysis. |
| `/inventory/reports/subcontract-variance` | report | readonly | purchase/outsourcing | Subcontract shortage/scrap variance report; read-only variance review and export only. |
| `/inventory/reports/subcontract-payable-reconcile` | report | readonly | purchase/outsourcing/finance | Subcontract payable reconciliation report; read-only reconciliation and export only. |
| `/inventory/monthly-report` | report | hidden | warehouse | Compatibility monthly inventory report alias; normal navigation uses `/inventory/reports/monthly`. |
| `/subcontract/opening` | opening data | live | subcontracting | Subcontract opening balance entry/list for go-live initialization; not normal master archive maintenance. |
| `/subcontract` | document list | live | subcontracting | Subcontract order list; shows order status, issue/receive progress, payable, and project-machine trace. |
| `/subcontract/new` | document entry | live | subcontracting | Subcontract order entry; creates order with multi-line detail items, project/cabinet trace, and auto-payable. |
| `/subcontract_issue` | document list | live | subcontracting | Subcontract issue list; shows issue status, quantity, and downstream receive reconciliation. |
| `/subcontract_issue/new` | document entry | live | subcontracting | Subcontract issue entry; creates issue document from subcontract order with warehouse/location/lot trace. |
| `/subcontract_issue/<id>/delete` | document entry action | live | subcontracting | Delete a draft subcontract issue only after confirming it has no posted stock transactions; audited issues must be reversed before deletion. |
| `/subcontract_issue/<id>/copy` | document entry action | live | subcontracting | Copy a subcontract issue into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/subcontract_receive` | document list | live | subcontracting | Subcontract receive list; shows receive status, scrap/shortage, and payable reconciliation. |
| `/subcontract_receive/new` | document entry | live | subcontracting | Subcontract receive entry; creates receive document with scrap/shortage recording and inventory posting. |
| `/subcontract_receive/<id>/delete` | document entry action | live | subcontracting | Delete a draft subcontract receive only after confirming it has no posted stock transactions; audited receives must be reversed before deletion. |
| `/subcontract_receive/<id>/copy` | document entry action | live | subcontracting | Copy a subcontract receive into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/finance/opening/receivables` | opening data | live | finance | Receivable opening balance entry/list for go-live initialization; finance-owned data. |
| `/finance/opening/payables` | opening data | live | finance | Payable opening balance entry/list for go-live initialization; finance-owned data. |
| `/material` | master data | live | master data | Primary material master entry; supports import/template/export and delete reference blocking. |
| `/engineering/technical-confirmations` | engineering document list | live | engineering | Engineering technical confirmation list; shows readiness, blocked reason, owner, next action, and project-machine trace links only. |
| `/engineering/technical-confirmations/new` | engineering document entry | live | engineering | Engineering technical confirmation entry; confirms BOM, routing, work center, released drawing, key control points, process program, tooling, and inspection basis before downstream execution. |
| `/engineering/technical-confirmations/<id>` | engineering document detail | live | engineering | Engineering technical confirmation detail; status-aware confirmation and readiness review only. |
| `/engineering/drawings` | engineering ledger | live | engineering | Engineering drawing ledger; CAD/PDM source files remain outside ERP, while ERP stores drawing number, version, controlled file location, lifecycle state, references, and downstream impact. |
| `/engineering/drawings/new` | engineering ledger entry | live | engineering | Engineering drawing ledger entry; records controlled drawing metadata and references, not CAD/PDM source editing. |
| `/engineering/drawings/<id>` | engineering ledger detail | live | engineering | Engineering drawing detail; release, change, obsolete, copy-version, references, and downstream impact actions are status-aware. |
| `/product-configurations/new` | document entry | live | engineering/sales | Product configuration entry for project option choices and engineering confirmation; it does not create purchase, production, inventory, finance, outsourcing, or shipment documents. |
| `/product-configurations` | document list | live | engineering/sales | Product configuration list/search with status, owner, next action, and drill-down only; create actions stay in the document-entry group. |
| `/product-configurations/<id>` | document detail | live | engineering/sales | Product configuration detail for review, confirmation, and project BOM link visibility only; downstream execution remains owned by other modules. |
| `/bom` | engineering master list | live | engineering | BOM list and structure entry point; supports versioned BOM governance for machine-tool products. |
| `/bom/new` | engineering master entry | live | engineering | BOM entry; creates controlled BOM headers and material lines only. |
| `/bom/<id>` | engineering master detail | live | engineering | BOM detail and structure view; exposes version, lines, and downstream read-only trace. |
| `/bom/ecn` | engineering change list | live | engineering | BOM engineering change list; tracks source BOM, target BOM, status, owner, and read-only impact. |
| `/bom/ecn/new` | engineering change entry | live | engineering | BOM engineering change entry; records change reason and impact without mutating finance, inventory, or production documents. |
| `/bom/ecn/<ecn_key>` | engineering change detail | live | engineering | BOM engineering change detail; draft, submit, approve, close, and void actions remain within BOM change governance. |
| `/production-routings` | technical master data | live | engineering/production | Routing master list; technical basis for production execution, not a work-order entry page. |
| `/production-routings/new` | technical master data | live | engineering/production | Routing master entry; maintains operation sequence and work-center basis only. |
| `/production-routings/<id>` | technical master detail | live | engineering/production | Routing detail; read and maintain routing operations without posting production or inventory. |
| `/work-centers` | technical master data | live | engineering/production | Work-center master list; capacity and operation reference data for routing and production. |
| `/work-centers/new` | technical master data | live | engineering/production | Work-center master entry; reference data only. |
| `/work-centers/<id>` | technical master detail | live | engineering/production | Work-center detail; reference data and capacity basis only. |
| `/material/import` | master data | live | master data | Material master batch import page; writes only material archive data. |
| `/material/download_template` | master data | live | master data | Material master import template endpoint. |
| `/products` | master data | hidden | master data | Compatibility material list route only; normal navigation uses `/material`. |
| `/products/new` | master data | hidden | master data | Compatibility material creation alias; redirects to `/material/new`. |
| `/products/<id>` | master data | hidden | master data | Compatibility material detail alias; normal navigation uses `/material/<id>`. |
| `/products/<id>/edit` | master data | hidden | master data | Compatibility material edit alias; redirects to `/material/<id>/edit`. |
| `/project-master` | master data | live | master data | Project master trace axis; project number is recommended traceability, not universally mandatory. |
| `/project-master/import` | master data | live | master data | Project master batch import page; project number remains a traceability field, not a mandatory document field. |
| `/project-master/download_template` | master data | live | master data | Project master import template endpoint. |
| `/project-master/new` | master data | live | master data | Project master maintenance form. |
| `/project-master/<id>` | master data | live | master data | Project master detail page. |
| `/project-master/<id>/edit` | master data | live | master data | Project master edit form. |
| `/cabinet-master` | master data | live | master data | Machine cabinet master trace axis; cabinet number is recommended traceability, not universally mandatory. |
| `/cabinet-master/import` | master data | live | master data | Machine cabinet master batch import page; writes only cabinet archive data. |
| `/cabinet-master/download_template` | master data | live | master data | Machine cabinet master import template endpoint. |
| `/cabinet-master/new` | master data | live | master data | Machine cabinet master maintenance form. |
| `/cabinet-master/<id>` | master data | live | master data | Machine cabinet master detail page. |
| `/cabinet-master/<id>/edit` | master data | live | master data | Machine cabinet master edit form. |
| `/customer` | master data | live | master data | Primary customer master entry; normal navigation uses this route. |
| `/customer/import` | master data | live | master data | Customer master batch import page. |
| `/customer/download_template` | master data | live | master data | Customer master import template endpoint. |
| `/customer/new` | master data | live | master data | Customer master maintenance form. |
| `/customer/<id>` | master data | live | master data | Customer master detail and trace page. |
| `/customer/<id>/edit` | master data | live | master data | Customer master edit form. |
| `/customers` | master data | hidden | master data | Compatibility customer list route only; normal navigation uses `/customer`. |
| `/customers/new` | master data | hidden | master data | Compatibility customer creation alias; redirects to `/customer/new`. |
| `/customers/<id>` | master data | hidden | master data | Compatibility customer detail alias; normal navigation uses `/customer/<id>`. |
| `/customers/<id>/edit` | master data | hidden | master data | Compatibility customer edit alias; redirects to `/customer/<id>/edit`. |
| `/supplier` | master data | live | master data | Primary supplier and outsourced processor master entry; normal navigation uses this route. |
| `/supplier/import` | master data | live | master data | Supplier master batch import page. |
| `/supplier/download_template` | master data | live | master data | Supplier master import template endpoint. |
| `/supplier/new` | master data | live | master data | Supplier master maintenance form. |
| `/supplier/<id>` | master data | live | master data | Supplier master detail and trace page. |
| `/supplier/<id>/edit` | master data | live | master data | Supplier master edit form. |
| `/suppliers` | master data | hidden | master data | Compatibility supplier list route only; normal navigation uses `/supplier`. |
| `/suppliers/new` | master data | hidden | master data | Compatibility supplier creation alias; redirects to `/supplier/new`. |
| `/suppliers/<id>` | master data | hidden | master data | Compatibility supplier detail alias; normal navigation uses `/supplier/<id>`. |
| `/suppliers/<id>/edit` | master data | hidden | master data | Compatibility supplier edit alias; redirects to `/supplier/<id>/edit`. |
| `/warehouse` | master data | live | warehouse | Primary warehouse master entry; normal navigation uses this route. |
| `/warehouse/import` | master data | live | warehouse | Warehouse master batch import page. |
| `/warehouse/download_template` | master data | live | warehouse | Warehouse master import template endpoint. |
| `/warehouse/new` | master data | live | warehouse | Warehouse master maintenance form. |
| `/warehouse/<id>` | master data | live | warehouse | Warehouse master detail page. |
| `/warehouse/<id>/edit` | master data | live | warehouse | Warehouse master edit form. |
| `/warehouses` | master data | hidden | warehouse | Compatibility warehouse list route only; normal navigation uses `/warehouse`. |
| `/warehouses/new` | master data | hidden | warehouse | Compatibility warehouse creation alias; redirects to `/warehouse/new`. |
| `/warehouses/<id>` | master data | hidden | warehouse | Compatibility warehouse detail alias; normal navigation uses `/warehouse/<id>`. |
| `/warehouses/<id>/edit` | master data | hidden | warehouse | Compatibility warehouse edit alias; redirects to `/warehouse/<id>/edit`. |
| `/locations` | master data | live | warehouse | Location master entry; locations must resolve to an existing warehouse. |
| `/location` | master data | hidden | warehouse | Compatibility location list alias; normal navigation uses `/locations`. |
| `/location/import` | master data | live | warehouse | Location master batch import page; imported locations must resolve to an existing warehouse. |
| `/location/download_template` | master data | live | warehouse | Location master import template endpoint. |
| `/location/new` | master data | live | warehouse | Location master maintenance form. |
| `/location/<id>` | master data | live | warehouse | Location master detail page. |
| `/location/<id>/edit` | master data | live | warehouse | Location master edit form. |
| `/locations/new` | master data | hidden | warehouse | Compatibility location creation alias; redirects to `/location/new`. |
| `/locations/<id>` | master data | hidden | warehouse | Compatibility location detail alias; normal detail links resolve to the location detail renderer. |
| `/locations/<id>/edit` | master data | hidden | warehouse | Compatibility location edit alias; redirects to `/location/<id>/edit`. |
| `/unit` | master data | live | master data | Primary unit master entry; normal navigation uses this route. |
| `/unit/import` | master data | live | master data | Unit master batch import page. |
| `/unit/download_template` | master data | live | master data | Unit master import template endpoint. |
| `/unit/new` | master data | live | master data | Unit master maintenance form. |
| `/unit/<id>` | master data | live | master data | Unit master detail page. |
| `/unit/<id>/edit` | master data | live | master data | Unit master edit form. |
| `/units` | master data | hidden | master data | Compatibility unit list route only; normal navigation uses `/unit`. |
| `/units/new` | master data | hidden | master data | Compatibility unit creation alias; redirects to `/unit/new`. |
| `/units/<id>` | master data | hidden | master data | Compatibility unit detail alias; normal navigation uses `/unit/<id>`. |
| `/units/<id>/edit` | master data | hidden | master data | Compatibility unit edit alias; redirects to `/unit/<id>/edit`. |
| `/department` | master data | live | master data | Primary department master entry; normal navigation uses this route. |
| `/department/import` | master data | live | master data | Department master batch import page. |
| `/department/download_template` | master data | live | master data | Department master import template endpoint. |
| `/department/new` | master data | live | master data | Department master maintenance form. |
| `/department/<id>` | master data | live | master data | Department master detail page. |
| `/department/<id>/edit` | master data | live | master data | Department master edit form. |
| `/departments` | master data | hidden | master data | Compatibility department list route only; normal navigation uses `/department`. |
| `/departments/new` | master data | hidden | master data | Compatibility department creation alias; redirects to `/department/new`. |
| `/departments/<id>` | master data | hidden | master data | Compatibility department detail alias; normal navigation uses `/department/<id>`. |
| `/departments/<id>/edit` | master data | hidden | master data | Compatibility department edit alias; redirects to `/department/<id>/edit`. |
| `/employee` | master data | live | master data | Primary employee master entry; normal navigation uses this route. |
| `/employee/import` | master data | live | master data | Employee master batch import page. |
| `/employee/download_template` | master data | live | master data | Employee master import template endpoint. |
| `/employee/new` | master data | live | master data | Employee master maintenance form. |
| `/employee/<id>` | master data | live | master data | Employee master detail page. |
| `/employee/<id>/edit` | master data | live | master data | Employee master edit form. |
| `/employees` | master data | hidden | master data | Compatibility employee list route only; normal navigation uses `/employee`. |
| `/employees/new` | master data | hidden | master data | Compatibility employee creation alias; redirects to `/employee/new`. |
| `/employees/<id>` | master data | hidden | master data | Compatibility employee detail alias; normal navigation uses `/employee/<id>`. |
| `/employees/<id>/edit` | master data | hidden | master data | Compatibility employee edit alias; redirects to `/employee/<id>/edit`. |
| `/categories/product` | master data | live | master data | Product/material category master. |
| `/categories/customer` | master data | live | master data | Customer category master. |
| `/categories/supplier` | master data | live | master data | Supplier category master. |
| `/categories/warehouse` | master data | live | warehouse | Warehouse category master. |
| `/categories/<kind>/import` | master data | live | master data | Category master batch import page for product, customer, supplier, and warehouse categories. |
| `/categories/<kind>/download_template` | master data | live | master data | Category master import template endpoint. |
| `/categories/<kind>/new` | master data | live | master data | Category master maintenance form. |
| `/categories/<kind>/<id>` | master data | live | master data | Category master detail page. |
| `/categories/<kind>/<id>/edit` | master data | live | master data | Category master edit form. |
| `/export/products` | master data | live | master data | Material master CSV export endpoint. |
| `/export/customers` | master data | live | master data | Customer master CSV export endpoint. |
| `/export/suppliers` | master data | live | master data | Supplier master CSV export endpoint. |
| `/export/warehouses` | master data | live | warehouse | Warehouse master CSV export endpoint. |
| `/export/locations` | master data | live | warehouse | Location master CSV export endpoint. |
| `/export/units` | master data | live | master data | Unit master CSV export endpoint. |
| `/export/departments` | master data | live | master data | Department master CSV export endpoint. |
| `/export/employees` | master data | live | master data | Employee master CSV export endpoint. |
| `/export/project-masters` | master data | live | master data | Project master CSV export endpoint. |
| `/export/cabinet-masters` | master data | live | master data | Machine cabinet master CSV export endpoint. |
| `/export/product-categories` | master data | live | master data | Product category CSV export endpoint. |
| `/export/customer-categories` | master data | live | master data | Customer category CSV export endpoint. |
| `/export/supplier-categories` | master data | live | master data | Supplier category CSV export endpoint. |
| `/export/warehouse-categories` | master data | live | warehouse | Warehouse category CSV export endpoint. |
| `/income-categories` | master data | live | master data | Income category reference data; no posting. |
| `/expense-categories` | master data | live | master data | Expense category reference data; no posting. |
| `/fee-templates` | master data | live | master data | Fee template reference data; no payable posting. |
| `/auxiliary-data` | master data | live | master data | Auxiliary reference values. |
| `/settlement-terms` | master data | live | master data | Settlement period reference values. |
| `/payment-terms` | master data | live | master data | Receipt/payment condition reference values. |
| `/currencies` | master data | live | finance | Currency reference values; no exchange adjustment posting. |
| `/settlement-methods` | master data | live | finance | Settlement method reference values. |
| `/cash-bank-accounts` | master data | live | finance | Account reference view; cash-bank journal stays in finance module. |
| `/payment-channels` | master data | live | finance | Payment channel reference values; no external channel integration. |
| `/master/chart-of-accounts` | master data | live | finance | Chart-of-account reference view; voucher entry remains in finance module. |
| `/voucher-words` | master data | live | finance | Voucher word reference values. |
| `/voucher-templates` | master data | live | finance | Voucher template reference values; no automatic voucher generation. |
| `/electronic-accounting-archives` | master data | live | finance | Archive metadata only; no cloud archive storage integration. |
| `/vat-accounting-data` | master data | live | finance | VAT accounting data scheme metadata only; no tax declaration. |
| `/shipments/<id>/delete` | document entry action | live | sales/warehouse | Delete a draft sales shipment only after confirming it has no posted stock transactions; posted shipments must be reversed before deletion. |
| `/shipments/<id>/copy` | document entry action | live | sales/warehouse | Copy a sales shipment into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/sales-returns/<id>/delete` | document entry action | live | sales/warehouse | Delete a draft sales return only after confirming it has no posted stock transactions; posted returns must be reversed before deletion. |
| `/sales-returns/<id>/copy` | document entry action | live | sales/warehouse | Copy a sales return into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/quotations/<id>/copy` | document entry action | live | sales | Copy a sales quotation into a new draft document with the same line details; does not affect customer orders or shipment records. |
| `/sales/<id>/copy` | document entry action | live | sales | Copy a sales order into a new draft document with the same line details; does not affect original order quantities or shipment records. |
| `/sales/reports` | report | live | sales | Read-only sales report center; links sales order, shipment, invoice, receivable, collection, project number, and cabinet number reports. |
| `/sales/reports/pending` | report | live | sales | Read-only pending sales delivery report; uses customer open order analysis as the operator-facing view. |
| `/sales/reports/customer-ranking` | report | live | sales | Read-only customer open delivery and open receivable ranking; supports sales follow-up prioritization. |
| `/sales/reports/execution` | report | live | sales | Read-only sales execution summary; tracks order, shipment, invoice, and collection status. |
| `/sales/reports/summary` | report | live | sales | Read-only sales summary; aggregates sales amount, shipped amount, open quantity, and receivable balance. |
| `/sales/reports/order-execution-summary` | report | live | sales | Read-only sales order execution summary; aggregates order, shipment, invoice, receipt, and delivery status. |
| `/sales/reports/order-execution-detail` | report | live | sales | Read-only sales order execution detail; tracks order, shipment, invoice, receipt, project number, and cabinet number. |
| `/sales/reports/customer-open-order-analysis` | report | live | sales | Read-only customer open order analysis; monitors unshipped quantity, open amount, and overdue delivery. |
| `/sales/reports/project-cabinet-open-order-analysis` | report | live | sales | Read-only project and machine cabinet open order analysis; monitors traceable delivery risk. |
| `/sales/reports/project-cabinet-order-tracking` | report | live | sales | Read-only project and machine cabinet sales trace report; links sales order, shipment, receivable balance, and service card count. |
| `/sales/reports/shipment-execution-detail` | report | live | sales | Read-only shipment execution detail; tracks shipment lines, inventory posting mark, invoiced amount, received amount, and delivery delay. |
| `/sales/reports/shipped-goods-detail` | report | live | sales | Read-only shipped goods detail; tracks shipment line issue amount, invoice settlement basis, open quantity basis, and open amount. |
| `/sales/reports/shipped-goods-summary` | report | live | sales | Read-only shipped goods summary; aggregates issued goods by product, customer, project number, and cabinet number. |
| `/sales/reports/shipped-unsettled-detail` | report | live | sales | Read-only shipped but unsettled detail; monitors shipped amount, uninvoiced amount, unreceived amount, and aging status. |
| `/sales/reports/invoice-execution-detail` | report | live | sales | Read-only sales invoice execution detail; compares expected order invoice amount with actual invoice amount. |
| `/sales/reports/invoice-summary` | report | live | sales | Read-only sales invoice summary; aggregates untaxed amount, tax amount, and tax-included amount. |
| `/sales/reports/receivable-collection-detail` | report | live | sales | Read-only collection execution detail; shows receipt, settlement, unapplied amount, AR balance, and aging bucket. |
| `/sales/reports/receivable-aging` | report | live | sales | Read-only sales receivable aging analysis; tracks open AR balance and aging risk by customer, project number, and cabinet number. |
| `/sales/reports/project-cabinet-gross-margin` | report | live | sales | Read-only operating gross margin analysis by project number and cabinet number; not financial period-close profit. |
| `/sales/reports/price-execution-analysis` | report | live | sales | Read-only sales price execution analysis; compares order price with customer or quotation reference price. |
| `/sales/reports/delivery-delay-analysis` | report | live | sales | Read-only delivery delay analysis; tracks planned delivery, shipment date, open quantity, and overdue days. |
| `/sales/reports/operation-snapshot` | report | live | sales | Read-only sales operation snapshot; summarizes orders, shipments, invoices, receipts, and open items. |
| `/sales/reports/daily` | report | live | sales | Read-only sales daily report; summarizes daily order, shipment, invoice, and receipt amounts. |
| `/sales/reports/return-impact-analysis` | report | hidden | sales | Hidden until a real read-only return impact report is implemented and verified. |
| `/work-orders` | document list | live | production | Production work-order list and linked entry for execution actions; document creation remains on `/work-orders/new`. |
| `/production-issues` | document list | live | production | Production material issue list; inventory posting remains controlled by the formal document detail/action flow. |
| `/production-returns` | document list | live | production | Production material return list; inventory posting remains controlled by the formal document detail/action flow. |
| `/production-completions` | document list | live | production | Production completion inbound list; completion posting remains controlled by the formal document detail/action flow. |
| `/production-completions/<id>/delete` | document entry action | live | production | Delete a draft production completion receipt before any completion posting, work-order completion item, or stock transaction exists. |
| `/production-completions/<id>/copy` | document entry action | live | production | Copy a production completion receipt into a new draft document with the same header details; inventory is not posted until the copied document is submitted and audited. |
| `/production-issues/<id>/copy` | document entry action | live | production | Copy a production issue document into a new draft document with the same line details; inventory is not posted until the copied document is submitted and audited. |
| `/production-returns/<id>/copy` | document entry action | live | production | Copy a production return document into a new draft document with the same line details; inventory is not posted until the copied document is submitted and audited. |
| `/production/operation-reports` | document list | live | production | Operation report list for process start, completion, rework, scrap, and labor/equipment hours. |
| `/production-schedules` | query list | live | production | Production schedule query list by work order, project number, cabinet number, work center, and dispatch status. |
| `/production-enhance/quality-inspections` | document list | live | production | Production quality inspection list; quality actions remain in inspection document detail pages. |
| `/engineering/kitting` | query list | live | production | Read-only kitting and shortage query shared with engineering; production uses it for execution readiness, not as a separate workbench. |
| `/requisition` | query list | live | production | Read-only work-order material requirement and picking query; formal issue/return documents remain separate. |
| `/production-enhance/mrp-requirements` | query list | live | production | Read-only MRP shortage query reused from the homepage and project delivery context; not a separate production workbench. |
| `/production/reports` | report | live | production | Read-only production report center. |
| `/production/reports/shortage` | report | live | production | Read-only production shortage report. |
| `/production/reports/bom-cost-query` | report | live | production | Read-only BOM cost query report. |
| `/production/reports/bom-forward-query` | report | live | production | Read-only BOM forward query report. |
| `/production/reports/bom-reverse-query` | report | live | production | Read-only BOM reverse query report. |
| `/production/reports/work-order-detail` | report | live | production | Read-only production work-order detail report. |
| `/production/reports/work-order-execution-detail` | report | live | production | Read-only work-order execution detail report. |
| `/production/reports/work-order-execution-summary` | report | live | production | Read-only work-order execution summary report. |
| `/production/reports/work-order-statistics` | report | live | production | Read-only work-order statistics report. |
| `/production/reports/kitting-shortage` | report | live | production | Read-only work-order kitting and shortage report. |
| `/production/reports/material-issue-detail` | report | live | production | Read-only work-order material issue detail report. |
| `/production/reports/material-issue-summary` | report | live | production | Read-only work-order material issue summary report. |
| `/production/reports/material-return-detail` | report | live | production | Read-only work-order material return detail report. |
| `/production/reports/material-variance` | report | live | production | Read-only work-order material variance report. |
| `/production/reports/completion-inbound-detail` | report | live | production | Read-only completion inbound detail report. |
| `/production/reports/completion-inbound-summary` | report | live | production | Read-only completion inbound summary report. |
| `/production/reports/operation-report-detail` | report | live | production | Read-only operation reporting detail report. |
| `/production/reports/operation-report-summary` | report | live | production | Read-only operation reporting summary report. |
| `/production/reports/project-cabinet-progress` | report | live | production | Read-only project and machine cabinet production progress report. |
| `/production/reports/quality-inspection-detail` | report | live | production | Read-only quality inspection detail report. |
| `/production/reports/quality-exception-summary` | report | live | production | Read-only quality exception summary report. |
| `/production/reports/progress-exception` | report | live | production | Read-only production progress exception report. |
| `/production/reports/wip-balance` | report | live | production | Read-only WIP balance report. |
| `/production/reports/work-order-cost-detail` | report | live | production | Read-only work-order cost detail report. |
| `/production/reports/project-cabinet-production-cost` | report | live | production | Read-only project and machine cabinet production cost report. |
| `/production/reports/production-cost-variance` | report | live | production | Read-only production cost variance report. |
| `/production/reports/cost-accounting` | report | live | production | Read-only production cost accounting report. |
| `/production/reports/monthly-summary` | report | live | production | Read-only production monthly summary report. |
| `/supplier-quotes/new` | document entry | live | purchase | Supplier quote entry; creates quote documents only, separate from quote list and purchase reports. |
| `/supplier-quotes` | document list | live | purchase | Supplier quote list; search, status, detail, print, compare, and controlled conversion links only. |
| `/supplier-quotes/<id>/copy` | document entry action | live | purchase | Copy a supplier quote into a new draft document with the same line details; does not create purchase orders until the copied document is confirmed. |
| `/purchase_request/new` | document entry | live | purchase | Purchase request entry; creates request documents from material-name line selection and trace fields. |
| `/purchase_request` | document list | live | purchase | Purchase request list; status-aware search, approval actions, detail links, and downstream order links. |
| `/purchase_order/new` | document entry | live | purchase | Purchase order entry; creates purchase order documents and keeps payable posting behind the payable posting boundary. |
| `/purchase-orders` | document list | live | purchase | Purchase order list; search, status, next action, receipt drill-down, and detail links only. |
| `/purchase_order/<id>/copy` | document entry action | live | purchase | Copy a purchase order into a new draft document with the same line details; does not affect original order quantities or receipt records. |
| `/purchase_receipts/new` | document entry | live | purchase/warehouse | Purchase receipt entry; records receipt against purchase order and leaves inventory posting to the controlled receipt flow. |
| `/purchase_receipts` | document list | live | purchase/warehouse | Purchase receipt list; search, status, source order, inventory evidence, and payable drill-down only. |
| `/purchase_receipts/<id>/delete` | document entry action | live | purchase/warehouse | Delete a draft purchase receipt only after confirming it has no posted stock transactions; posted receipts must be reversed before deletion. |
| `/purchase_receipts/<id>/copy` | document entry action | live | purchase/warehouse | Copy a purchase receipt into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/purchase-returns/new` | document entry | live | purchase/warehouse | Purchase return entry; creates controlled return documents separate from purchase receipt and reports. |
| `/purchase-returns` | document list | live | purchase/warehouse | Purchase return list; search, status, detail, print, and controlled posting actions only. |
| `/purchase-returns/<id>/delete` | document entry action | live | purchase/warehouse | Delete a draft purchase return only after confirming it has no posted stock transactions; posted returns must be reversed before deletion. |
| `/purchase-returns/<id>/copy` | document entry action | live | purchase/warehouse | Copy a purchase return into a new draft document with the same line details; inventory is not posted until the copied document is audited. |
| `/purchase-invoices/new` | finance document entry | live | finance | Purchase invoice registration entry; payable effects stay behind the payable posting boundary. |
| `/purchase-invoices` | finance document list | live | finance | Purchase invoice registration list; search, status, detail, print, confirm, void, and reverse actions only. |
| `/finance/sales-invoices/new` | finance document entry | live | finance | Canonical sales invoice registration entry alias; delegates to the existing sales invoice entry workflow. |
| `/finance/sales-invoices` | finance document list | live | finance | Canonical sales invoice registration list alias; delegates to the existing sales invoice list workflow. |
| `/finance/sales-invoices/<id>` | finance document detail | live | finance | Canonical sales invoice detail alias; redirects to existing detail workflow without changing tax or voucher rules. |
| `/finance/purchase-invoices/new` | finance document entry | live | finance | Canonical purchase invoice registration entry alias; delegates to the existing purchase invoice entry workflow. |
| `/finance/purchase-invoices` | finance document list | live | finance | Canonical purchase invoice registration list alias; delegates to the existing purchase invoice list workflow. |
| `/finance/purchase-invoices/<id>` | finance document detail | live | finance | Canonical purchase invoice detail alias; redirects to existing detail workflow without changing tax or voucher rules. |
| `/receivables` | finance query list | live | finance | Customer receivable list; finance-owned reconciliation and drill-down, not sales document entry. |
| `/finance/receivables` | finance query list | live | finance | Canonical customer receivable query alias; delegates to the existing receivable detail workflow. |
| `/finance/receivables/<id>` | finance document detail | live | finance | Canonical customer receivable detail alias; redirects to existing detail workflow without changing settlement logic. |
| `/payables` | finance query list | live | finance | Supplier payable list; finance-owned reconciliation and drill-down, not purchase document entry. |
| `/finance/payables` | finance query list | live | finance | Canonical supplier payable query alias; delegates to the existing payable detail workflow. |
| `/finance/payables/<id>` | finance document detail | live | finance | Canonical supplier payable detail alias; redirects to existing detail workflow without changing settlement logic. |
| `/payments/new` | finance document entry | live | finance | Supplier payment entry; applies payment to existing supplier payable records only. |
| `/payments` | finance document list | live | finance | Supplier payment list; finance-owned payment document list and detail workflow. |
| `/supplier-advance-payments/new` | finance document entry | live | finance | Supplier advance payment entry; finance-owned payment workflow, not a purchase document list. |
| `/supplier-advance-payments` | finance document list | live | finance | Supplier advance payment list; finance-owned query and controlled settlement follow-up. |
| `/customer-receipts/new` | finance document entry | live | finance | Customer receipt entry; applies receipt to existing customer receivable records only. |
| `/customer-receipts` | finance document list | live | finance | Customer receipt list; finance-owned receipt document list and detail workflow. |
| `/finance/receipts/new` | finance document entry | live | finance | Canonical customer receipt entry; applies receipt to existing customer receivable records only. |
| `/finance/receipts` | finance document list | live | finance | Canonical customer receipt list; finance-owned receipt document list and detail workflow. |
| `/finance/receipts/<id>` | finance document detail | live | finance | Canonical customer receipt detail alias; redirects to existing receipt detail and does not change settlement logic. |
| `/finance/advance-receipts/new` | finance document entry | live | finance | Canonical customer advance receipt entry; finance-owned prepayment workflow. |
| `/finance/advance-receipts` | finance document list | live | finance | Canonical customer advance receipt list; finance-owned query and follow-up. |
| `/finance/advance-receipts/<id>` | finance document detail | live | finance | Canonical customer advance receipt detail alias; redirects to existing detail workflow. |
| `/finance/receipt-refunds/new` | finance document entry | live | finance | Canonical customer receipt refund entry; finance-owned refund workflow. |
| `/finance/receipt-refunds` | finance document list | live | finance | Canonical customer receipt refund list; finance-owned refund follow-up. |
| `/finance/receipt-refunds/<id>` | finance document detail | live | finance | Canonical customer receipt refund detail alias; redirects to existing detail workflow. |
| `/finance/advance-receipt-refunds/new` | finance document entry | live | finance | Canonical advance receipt refund entry; finance-owned prepayment refund workflow. |
| `/finance/advance-receipt-refunds` | finance document list | live | finance | Canonical advance receipt refund list; finance-owned query and follow-up. |
| `/finance/advance-receipt-refunds/<id>` | finance document detail | live | finance | Canonical advance receipt refund detail alias; redirects to existing detail workflow. |
| `/finance/other-income/new` | finance document entry | live | finance | Canonical other income entry; finance-owned funds workflow. |
| `/finance/other-income` | finance document list | live | finance | Canonical other income list; finance-owned query and follow-up. |
| `/finance/other-income/<id>` | finance document detail | live | finance | Canonical other income detail alias; redirects to existing detail workflow. |
| `/finance/other-income-refunds/new` | finance document entry | live | finance | Canonical other income refund entry; finance-owned refund workflow. |
| `/finance/other-income-refunds` | finance document list | live | finance | Canonical other income refund list; finance-owned query and follow-up. |
| `/finance/other-income-refunds/<id>` | finance document detail | live | finance | Canonical other income refund detail alias; redirects to existing detail workflow. |
| `/finance/payments/new` | finance document entry | live | finance | Canonical supplier payment entry; finance-owned payment and settlement workflow. |
| `/finance/payments` | finance document list | live | finance | Canonical supplier payment list; finance-owned payment document list and detail workflow. |
| `/finance/payments/<id>` | finance document detail | live | finance | Canonical supplier payment detail alias; redirects to existing payment detail and does not change settlement logic. |
| `/finance/advance-payments/new` | finance document entry | live | finance | Canonical supplier advance payment entry; finance-owned prepayment workflow. |
| `/finance/advance-payments` | finance document list | live | finance | Canonical supplier advance payment list; finance-owned query and settlement follow-up. |
| `/finance/advance-payments/<id>` | finance document detail | live | finance | Canonical supplier advance payment detail alias; redirects to existing detail workflow. |
| `/finance/payment-refunds/new` | finance document entry | live | finance | Canonical supplier payment refund entry; finance-owned refund workflow. |
| `/finance/payment-refunds` | finance document list | live | finance | Canonical supplier payment refund list; finance-owned query and follow-up. |
| `/finance/payment-refunds/<id>` | finance document detail | live | finance | Canonical supplier payment refund detail alias; redirects to existing detail workflow. |
| `/finance/advance-payment-refunds/new` | finance document entry | live | finance | Canonical supplier advance payment refund entry; finance-owned prepayment refund workflow. |
| `/finance/advance-payment-refunds` | finance document list | live | finance | Canonical supplier advance payment refund list; finance-owned query and follow-up. |
| `/finance/advance-payment-refunds/<id>` | finance document detail | live | finance | Canonical supplier advance payment refund detail alias; redirects to existing detail workflow. |
| `/finance/other-expenses/new` | finance document entry | live | finance | Canonical other expense entry; finance-owned funds workflow. |
| `/finance/other-expenses` | finance document list | live | finance | Canonical other expense list; finance-owned query and follow-up. |
| `/finance/other-expenses/<id>` | finance document detail | live | finance | Canonical other expense detail alias; redirects to existing detail workflow. |
| `/finance/other-expense-refunds/new` | finance document entry | live | finance | Canonical other expense refund entry; finance-owned refund workflow. |
| `/finance/other-expense-refunds` | finance document list | live | finance | Canonical other expense refund list; finance-owned query and follow-up. |
| `/finance/other-expense-refunds/<id>` | finance document detail | live | finance | Canonical other expense refund detail alias; redirects to existing detail workflow. |
| `/customer-advance-receipts/new` | finance document entry | live | finance | Customer advance receipt entry; registers customer advance cash-in only. |
| `/customer-advance-receipts` | finance document list | live | finance | Customer advance receipt list; finance-owned query and controlled settlement follow-up. |
| `/customer-receipt-refunds/new` | finance document entry | live | finance | Customer receipt refund entry; registers controlled customer refund cash-out only. |
| `/customer-receipt-refunds` | finance document list | live | finance | Customer receipt refund list; finance-owned refund document list and detail workflow. |
| `/customer-advance-refunds/new` | finance document entry | live | finance | Customer advance refund entry; registers controlled advance refund cash-out only. |
| `/customer-advance-refunds` | finance document list | live | finance | Customer advance refund list; finance-owned refund document list and detail workflow. |
| `/customer-other-income/new` | finance document entry | live | finance | Customer other income entry; records cash-in only and does not create sales receivable or voucher postings. |
| `/customer-other-income` | finance document list | live | finance | Customer other income list; finance-owned document list and detail workflow. |
| `/customer-other-income-refunds/new` | finance document entry | live | finance | Customer other income refund entry; records cash-out only and does not reverse sales receivable automatically. |
| `/customer-other-income-refunds` | finance document list | live | finance | Customer other income refund list; finance-owned document list and detail workflow. |
| `/supplier-payment-refunds/new` | finance document entry | live | finance | Supplier payment refund entry; registers supplier refund cash-in only. |
| `/supplier-payment-refunds` | finance document list | live | finance | Supplier payment refund list; finance-owned refund document list and detail workflow. |
| `/supplier-advance-refunds/new` | finance document entry | live | finance | Supplier advance refund entry; registers supplier advance refund cash-in only. |
| `/supplier-advance-refunds` | finance document list | live | finance | Supplier advance refund list; finance-owned refund document list and detail workflow. |
| `/supplier-other-expenses/new` | finance document entry | live | finance | Supplier other expense entry; records cash-out only and does not create purchase payable, inventory cost, or voucher postings. |
| `/supplier-other-expenses` | finance document list | live | finance | Supplier other expense list; finance-owned document list and detail workflow. |
| `/supplier-other-expense-refunds/new` | finance document entry | live | finance | Supplier other expense refund entry; records cash-in only and does not reverse purchase payable automatically. |
| `/supplier-other-expense-refunds` | finance document list | live | finance | Supplier other expense refund list; finance-owned document list and detail workflow. |
| `/supplier-payment-requests` | finance document list | `hidden` | finance | Hidden high-risk payment request route; not exposed until approval and payable posting boundary is defined. |
| `/supplier-payment-requests/new` | finance document entry | `hidden` | finance | Hidden high-risk payment request entry; not exposed until approval and payable posting boundary is defined. |
| `/finance/fund-transfers` | finance document list | `hidden` | finance | Hidden high-risk fund transfer route; no transfer posting workflow is released. |
| `/finance/fund-transfers/new` | finance document entry | `hidden` | finance | Hidden high-risk fund transfer entry; no transfer posting workflow is released. |
| `/finance/receivables/bad-debt-accruals` | finance document list | `hidden` | finance | Hidden bad-debt accrual route; bad-debt accounting rule is out of scope. |
| `/finance/receivables/bad-debt-losses` | finance document list | `hidden` | finance | Hidden bad-debt loss route; bad-debt write-off accounting rule is out of scope. |
| `/finance/receivables/pending-collections` | finance query list | live | finance | Pending collection query; finance-owned follow-up list and no direct document posting. |
| `/finance/receivables/merged-collections` | finance query list | live | finance | Merged collection record query; read and drill-down only. |
| `/finance/receivable-bills` | finance query list | live | finance | Receivable bill query; finance-owned reconciliation and drill-down only. |
| `/finance/reports/receivable-detail` | report | `readonly` | finance | Read-only receivable detail report; export and drill-down only. |
| `/finance/reports/payable-detail` | report | `readonly` | finance | Read-only payable detail report; export and drill-down only. |
| `/finance/reports/receivable-summary` | report | `readonly` | finance | Read-only receivable summary report. |
| `/finance/reports/payable-summary` | report | `readonly` | finance | Read-only payable summary report. |
| `/finance/reports/payment-request-statistics` | report | `readonly` | finance | Read-only payment request statistics report; no request creation action. |
| `/finance/reports/receivable-warning` | report | `readonly` | finance | Read-only receivable warning report for finance follow-up. |
| `/finance/reports/payable-warning` | report | `readonly` | finance | Read-only payable warning report for finance follow-up. |
| `/finance/reports/bad-debt-reserve-balance` | report | `readonly` | finance | Read-only bad-debt reserve balance report; does not accrue or write off debt. |
| `/finance/reports/enterprise-income-expense-detail` | report | `readonly` | finance | Read-only enterprise income and expense detail report. |
| `/finance/reports/credit-management` | report | `readonly` | finance | Read-only credit management report; no credit limit write action. |
| `/finance/reports/account-aging-analysis` | report | `readonly` | finance | Read-only account aging analysis report. |
| `/finance/reports/other-income-expense-detail` | report | `readonly` | finance | Read-only other income and expense detail report. |
| `/finance/reports/account-income-expense-detail` | report | `readonly` | finance | Read-only account income and expense detail report. |
| `/finance/reports/account-balance` | report | `readonly` | finance | Read-only fund account balance report. |
| `/finance/reports/cash-bank-balance` | report | `readonly` | finance | Read-only cash-bank balance report. |
| `/finance/reports/cash-bank-transactions` | report | `readonly` | finance | Read-only cash-bank transaction report. |
| `/finance/reports/payment-flow-summary` | report | `readonly` | finance | Read-only payment flow summary report. |
| `/finance/reports/project-capital-occupation` | report | `readonly` | finance/project | Read-only project capital occupation report; no cost allocation action. |
| `/finance/settlement-schemes` | finance query list | live | finance | Auto-settlement scheme query page; no automatic source document mutation from classification. |
| `/finance/settlement-runs` | finance query list | live | finance | Auto-settlement run log query page. |
| `/finance/manual-settlement` | finance query list | live | finance | Manual settlement console route; controlled by existing finance permissions and does not change this repair boundary. |
| `/finance/smart-collections` | finance query list | live | finance | Smart collection queue; finance-owned follow-up query. |
| `/finance/reports/customer-vendor-matching-statement` | report | `readonly` | finance | Read-only customer-vendor matching statement. |
| `/finance/reports/statement-history` | report | `readonly` | finance | Read-only statement history report. |
| `/finance/statement-templates` | finance query list | readonly | finance | Statement template list; does not create accounting postings. |
| `/finance/exchange-adjustment` | finance document entry | live | finance | Period-end exchange adjustment entry; restricted to finance roles and existing audit flow. |
| `/finance/exchange-adjustments` | finance document list | live | finance | Period-end exchange adjustment list; query, export, and status-aware audit only. |
| `/procurement/suggestions` | query list | live | purchase/production | Procurement suggestion and shortage query; may create purchase requests only through controlled shortage gating. |
| `/purchase/reports/pending` | report | live | purchase | Read-only pending purchase arrival report; no document write action. |
| `/purchase/reports/supplier-ranking` | report | live | purchase | Read-only supplier pending arrival ranking. |
| `/purchase/reports/receipt-tracking` | report | live | purchase | Read-only purchase order receipt tracking report. |
| `/purchase/reports/received-not-invoiced-summary` | report | live | purchase/finance | Read-only received-not-invoiced summary for purchase and finance reconciliation. |
| `/purchase/reports/supplier-execution-analysis` | report | live | purchase | Read-only supplier execution analysis. |
| `/purchase/reports/purchase-price-variance` | report | live | purchase | Read-only purchase price variance analysis. |
| `/purchase/reports/purchase-exception-list` | report | live | purchase | Read-only purchase exception list for overdue, over-receipt, and invoice lag follow-up. |
| `/purchase/reports/execution` | report | live | purchase | Read-only purchase execution detail report. |
| `/purchase/reports/summary` | report | live | purchase | Read-only purchase summary report by supplier, project number, and cabinet number. |
| `/purchase/reports/request-execution-detail` | report | live | purchase | Read-only purchase request execution detail report. |
| `/purchase/reports/request-execution-summary` | report | live | purchase | Read-only purchase request execution summary report. |
| `/purchase/reports/order-execution-detail` | report | live | purchase | Read-only purchase order execution detail report. |
| `/purchase/reports/order-execution-summary` | report | live | purchase | Read-only purchase order execution summary report. |
| `/purchase/reports/receipt-detail` | report | live | purchase/warehouse | Read-only purchase receipt detail report. |
| `/purchase/reports/receipt-summary` | report | live | purchase/warehouse | Read-only purchase receipt summary report. |
| `/purchase/reports/received-not-invoiced-detail` | report | live | purchase/finance | Read-only received-not-invoiced detail report. |
| `/purchase/reports/invoice-detail` | report | live | purchase/finance | Read-only purchase invoice detail report. |
| `/purchase/reports/invoice-summary` | report | live | purchase/finance | Read-only purchase invoice summary and tax invoice summary report. |
| `/purchase/reports/payment-overview` | report | live | purchase/finance | Read-only purchase payment overview. |
| `/purchase/reports/payable-reconciliation-detail` | report | live | purchase/finance | Read-only purchase payable reconciliation detail. |
| `/purchase/reports/project-cabinet-purchase-cost-detail` | report | live | purchase/finance/project | Read-only project and machine cabinet purchase cost detail. |
| `/purchase/reports/daily` | report | live | purchase | Read-only purchase daily report. |
| `/finance/reports/purchase-payment-reconciliation` | report | live | finance | Read-only purchase payment reconciliation report owned by finance. |
| `/finance/smart-payments` | finance query list | live | finance | Finance-owned smart payment queue; no direct purchase document creation. |

## P0-1 MRP / Kitting Net-Requirement Engine

| Route | Page Type | State | Owner | Notes |
|---|---|---|---|---|
| `/mrp` | workbench | live | production/planning | MRP home/workbench; entry to run MRP, view run history, suggestions, and kitting analysis. |
| `/mrp/run` | document entry action | live | production/planning | Execute MRP run from a sales order, project, cabinet, work order, or manual product/BOM selection; persists run snapshot, items, and suggestions. |
| `/mrp/runs` | document list | live | production/planning | MRP run history list; search, status, next action, and detail links only. |
| `/mrp/runs/<id>` | document detail | live | production/planning | MRP run detail; shows source, BOM version, snapshot, net-requirement items, and suggestions. |
| `/mrp/suggestions` | document list | live | production/planning | MRP suggestions list; supports single and batch convert to purchase requisition, work order, or subcontract order. |
| `/mrp/suggestions/<id>/convert` | document entry action | live | production/planning | Convert a single MRP suggestion into a target document; writes trace_link to the new document. |
| `/mrp/suggestions/batch-convert` | document entry action | live | production/planning | Batch convert selected MRP suggestions into target documents. |
| `/mrp/kitting` | query list | readonly | production/planning | Kitting analysis query; shows coverage, shortage, and kitting rate by project/cabinet/work order; no document write actions. |
| `/api/mrp/runs/<id>/suggestions` | internal API | readonly | production/planning | JSON endpoint returning suggestions for a given MRP run; consumed by the run detail page. |

## P0-2 Project/Serial Full-Chain Trace Engine

| Route | Page Type | State | Owner | Notes |
|---|---|---|---|---|
| `/trace` | workbench | live | production/project | Trace home/workbench; entry to project, cabinet, and document trace pages. |
| `/trace/project/<project_code>` | query list | readonly | project | Forward and reverse trace by project code; read-only graph and timeline. |
| `/trace/cabinet/<cabinet_no>` | query list | readonly | production/service | Forward and reverse trace by cabinet number; read-only graph and timeline. |
| `/trace/document/<doc_type>/<doc_id>` | query list | readonly | all | Trace from any business document to its upstream and downstream documents; read-only. |
| `/trace/integrity` | query list | readonly | system | Trace integrity findings list; shows missing links, missing project/cabinet fields, and completeness score. |
| `/trace/integrity/<id>/resolve` | system admin action | live | system | Resolve a trace integrity finding after the underlying data is corrected. |
| `/trace/integrity/scan` | system admin action | live | system | Trigger a trace integrity re-scan; writes new findings to `trace_integrity_findings`. |

## P0-3 Single-Machine / Project Cost Collection Engine

| Route | Page Type | State | Owner | Notes |
|---|---|---|---|---|
| `/cost` | workbench | live | finance/production | Cost engine home/workbench; entry to run cost calculation, view runs, project/cabinet summaries, and reconciliation. |
| `/cost/run` | document entry action | live | finance | Execute a cost calculation run for a period, project, and/or cabinet; collects material, labor, overhead, outsource, service, and quality costs. |
| `/cost/runs` | document list | live | finance | Cost run history list; search, status, next action, and detail links only. |
| `/cost/runs/<id>` | document detail | live | finance | Cost run detail; shows cost items by type, source document, project, cabinet, and work order. |
| `/cost/project/<project_code>` | query list | readonly | finance/project | Project cost summary; read-only cost composition and source drill-down. |
| `/cost/cabinet/<cabinet_no>` | query list | readonly | finance/production | Serial cost summary; read-only single-machine cost composition and source drill-down. |
| `/cost/reconciliation` | query list | readonly | finance | Cost reconciliation results; compares business cost vs inventory cost vs GL cost. |
| `/cost/reconciliation/run` | document entry action | live | finance | Execute a cost reconciliation run for a period; saves results to `cost_reconciliation_results`. |

## P0-4 BOM / Drawing / Process / ECN Snapshot and Impact Control

| Route | Page Type | State | Owner | Notes |
|---|---|---|---|---|
| `/bom/versions` | document list | live | engineering | BOM version list across all BOMs; search, status, next action, and detail links only. |
| `/bom/<bom_id>/versions` | document list | live | engineering | BOM version list scoped to a single BOM; separate from the BOM entry page. |
| `/bom/versions/<id>` | document detail | live | engineering | BOM version detail; shows status, effective/expire dates, approver, and linked work-order snapshots. |
| `/bom/versions/new` | document entry | live | engineering | BOM version creation form/action; creates a draft version tied to an existing BOM. |
| `/bom/versions/<id>/approve` | document entry action | live | engineering | Approve a draft BOM version; transitions draft to approved. |
| `/bom/versions/<id>/release` | document entry action | live | engineering | Release an approved BOM version; atomically expires prior released versions of the same BOM. |
| `/bom/versions/<id>/obsolete` | document entry action | live | engineering | Mark a released BOM version obsolete. |
| `/work-orders/<id>/snapshots` | query list | readonly | engineering/production | Work-order BOM/process/drawing snapshots; read-only view of the versions frozen at work-order release. |
| `/ecn/<id>/impact` | query list | readonly | engineering | ECN impact analysis result view; read-only list of affected sales orders, purchase orders, work orders, subcontract orders, and inventory. |
| `/ecn/<id>/impact/analyze` | document entry action | live | engineering | Run ECN impact analysis; writes results to `ecn_impact_results`. |
| `/ecn/impact-tasks/<id>/resolve` | document entry action | live | engineering | Resolve an ECN impact task after the affected document is handled. |
| `/ecn/impact-tasks` | document list | live | engineering | ECN impact tasks list; search, status, next action, and detail links only. |
| `/bom/items/<id>/substitutes` | query list | readonly | engineering | BOM item substitutes list; read-only view of substitute materials and approval status. |
| `/bom/items/<id>/substitutes/new` | document entry action | live | engineering | Create a substitute material for a BOM item; upsert on `bom_item_id, substitute_product_id`. |
| `/bom/substitutes/<id>/edit` | document entry action | live | engineering | Edit an existing substitute material's priority, ratio, and auto-substitute flag. |
| `/bom/substitutes/<id>/approve` | document entry action | live | engineering | Approve a pending substitute material. |
| `/bom/substitutes/<id>/delete` | document entry action | live | engineering | Delete a substitute material; restricted to unapproved or superseded rows. |
| `/ecn/action-tasks` | document list | live | engineering | ECN action tasks list across all ECNs; search, status, owner, and next action only. |
| `/ecn/<id>/action-tasks` | document list | live | engineering | ECN action tasks scoped to a single ECN. |
| `/ecn/<id>/action-tasks/generate` | document entry action | live | engineering | Generate action tasks (purchase change, work-order change, pick adjust, drawing replace, service notice) from an ECN's impact results. |
| `/ecn/action-tasks/<id>/status` | document entry action | live | engineering | Update an ECN action task's status and assignee. |

## P0-5 Data-Level Permission Control

| Route | Page Type | State | Owner | Notes |
|---|---|---|---|---|
| `/security/data-permissions` | system admin query | live | system | Data permission rules list; filters by subject, scope, and permission. |
| `/security/data-permissions/new` | system admin | live | system | Data permission rule creation form/action; mirrors rule to `data_scope_rules` for query-scope enforcement. |
| `/security/data-permissions/<id>/update` | system admin action | live | system | Update an existing data permission rule. |
| `/security/data-permissions/<id>/delete` | system admin action | live | system | Delete a data permission rule; restricted to admin and manager. |
| `/security/data-access-logs` | system admin query | readonly | system | Data access audit log query; read-only view of view/export/edit access decisions. |
| `/security/export-approvals` | system admin query | readonly | system | Export approval queue; read-only view of pending and processed export approvals. |
| `/api/data-permissions/scopes` | internal API | readonly | system | JSON endpoint returning available scope options for a given scope type; consumed by the rule form. |
