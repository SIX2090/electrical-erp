# Page Type Inventory

Generated from `MENU_ROLLOUT_CLASSIFICATION.md`.

## Summary

| Level | Count |
|---|---:|
| `live` | 4 |
| `fix` | 0 |
| `readonly` | 20 |
| `internal` | 0 |
| `hidden` | 6 |

## Routes

| Path | Page Type | Level | Reason / Next Action |
|---|---|---|---|
| `/purchase` | workbench | `live` | purchase | Purchase workbench/root route; shows purchase follow-up queues and exception summaries only, not a replacement for purchase document lists. |
| `/production` | workbench | `live` | production | Production workbench/root route; shows production execution queues, blockers, owners, and next actions only, not a full work-order list. |
| `/service` | workbench | `live` | service | Service workbench/root route; shows after-sale queues, exceptions, cost links, and RMA follow-up only, not full service document editing. |
| `/master-data` | workbench | `live` | master data | Master-data quality workbench; shows reference-data maintenance queues and health cues only, not business document execution. |
| `/supplier-payment-requests` | finance document list | `hidden` | finance | Hidden high-risk payment request route; not exposed until approval and payable posting boundary is defined. |
| `/supplier-payment-requests/new` | finance document entry | `hidden` | finance | Hidden high-risk payment request entry; not exposed until approval and payable posting boundary is defined. |
| `/finance/fund-transfers` | finance document list | `hidden` | finance | Hidden high-risk fund transfer route; no transfer posting workflow is released. |
| `/finance/fund-transfers/new` | finance document entry | `hidden` | finance | Hidden high-risk fund transfer entry; no transfer posting workflow is released. |
| `/finance/receivables/bad-debt-accruals` | finance document list | `hidden` | finance | Hidden bad-debt accrual route; bad-debt accounting rule is out of scope. |
| `/finance/receivables/bad-debt-losses` | finance document list | `hidden` | finance | Hidden bad-debt loss route; bad-debt write-off accounting rule is out of scope. |
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
| `/finance/reports/customer-vendor-matching-statement` | report | `readonly` | finance | Read-only customer-vendor matching statement. |
| `/finance/reports/statement-history` | report | `readonly` | finance | Read-only statement history report. |
