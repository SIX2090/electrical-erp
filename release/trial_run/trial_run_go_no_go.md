# First Machine Trial Run Go/No-Go Check

Decision: **GO**

Last refreshed: 2026-06-29

| Check | Status | Result | Command |
| --- | --- | --- | --- |
| First machine data template | PASS | errors=0 warnings=0 warnings=see output | `python scripts\validate_first_machine_template.py` |
| Master data cross-check | PASS | 6 errors=0 warnings=0 | `set PG_PASSWORD=%PG_PASSWORD% && python scripts\check_first_machine_master_data.py` |
| First machine candidate | PASS | trial_candidates=1 | `set PG_PASSWORD=%PG_PASSWORD% && python scripts\select_trial_machine_candidates.py` |
| Trial user menus | PASS | 7 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_user_menus.py` |
| Trial user backend access | PASS | 7 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_user_access.py` |
| Trial visible navigation | PASS | 1749 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_visible_navigation.py` |
| Trial direct access matrix | PASS | 2373 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_direct_access_matrix.py` |
| Trial high-risk role matrix | PASS | 46 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_high_risk_role_matrix.py` |
| Trial POST action scope | PASS | 42 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_post_action_scope.py` |
| Trial role permissions page | PASS | 37 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_role_permissions_page.py` |
| Trial sales menu entries | PASS | checked_items=58 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_sales_menu_entries.py` |
| Trial core document fields | PASS | 81 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_core_document_fields.py` |
| Trial operator task queues | PASS | checked_items=156 checked_users=7 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_trial_operator_task_queues.py` |
| Trial release documents | PASS | 19 | `python scripts\audit_trial_release_documents.py` |
| Trial issue log validator | PASS | 6 | `python scripts\audit_trial_issue_log_validator.py` |
| First machine main line visibility | PASS | 51 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_workflow.py` |
| First machine shortage to purchase suggestion | PASS | 12 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_procurement.py` |
| First machine purchase to receipt/payable | PASS | 20 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_purchase_to_receipt.py` |
| First machine inventory trace | PASS | 27 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_inventory_trace.py` |
| First machine inventory execution | PASS | 35 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_inventory_execution.py` |
| First machine work order issue | PASS | 7 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_work_order_issue.py` |
| First machine quality closure | PASS | 19 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_quality_closure.py` |
| First machine subcontract closure | PASS | 35 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_subcontract_closure.py` |
| First machine completion shipment finance | PASS | 36 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_completion_shipment_finance.py` |
| First machine finance settlement | PASS | 24 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_finance_settlement.py` |
| First machine service closure | PASS | 40 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_service_closure.py` |
| First machine lifecycle ledger | PASS | checked_items=36 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_lifecycle_ledger.py` |
| First machine detail runtime text | PASS | 87 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_detail_runtime_text.py` |
| First machine period close readiness | PASS | 20 | `set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_first_machine_period_close_readiness.py` |
| Trial issue log blockers | PASS | open_blockers=0 | `python scripts\validate_trial_issue_log.py` |
| System document gap audit | PASS | documents_checked=13 risk_high=0 risk_medium=0 risk_low=0 | `python scripts\audit_system_document_gaps.py` |
| Material opening boundary | PASS | material_opening_boundary=ok | `python scripts\audit_material_opening_boundary.py` |
| Document material name entry | PASS | checked_templates=9 findings=0 | `python scripts\audit_document_material_name_entry.py` |
| Report print controls | PASS | report_print_controls=ok | `python scripts\audit_report_print_controls.py` |
| Report performance | PASS | checked_reports=188 | `python scripts\audit_report_performance.py` |
| Inventory balance consistency | PASS | findings=0 after first-machine trial material reconciliation | `set PG_PASSWORD=%PG_PASSWORD% && python scripts\audit_inventory_balance_consistency.py` |
| Full system operator simulation | PASS | failed_pages=0 failed_post_checks=0 | `python scripts\audit_full_system_operator_simulation.py` |
| Backup and controlled restore drill | PASS | RESTORE_OK tables=331 users=8 products=66 | `python scripts\pg_restore.py --input backups\pre_inventory_balance_repair_20260629.dump --force` against `wms_restore_drill_20260629` |

## Notes

The previous automated trial-run table has been refreshed with the 2026-06-29 stabilization results. The ERP remains a trial `GO` for the scoped machine-tool manufacturing core. Production cutover still requires final business data reconciliation and named operations owners for cutover, rollback, and backup retention.
