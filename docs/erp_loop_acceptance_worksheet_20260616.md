# ERP Loop Acceptance Worksheet

Date: 2026-06-16

This worksheet defines operator-level acceptance steps for each core business loop. It proves loops by operator action and data effect, not only HTTP 200. Every route referenced below already exists in the current package; no new route, schema field, menu entry, posting rule, or finance rule is introduced by this worksheet.

## How To Use

- Run one loop at a time. Mark `Result` only after the operator action completes and the reconciliation report confirms the expected data effect.
- `Blocked reason` must be filled whenever the step cannot complete. `Next action` must name the concrete next owner or fix.
- `Test account` uses pilot roles: `admin`, `sales`, `purchase`, `warehouse`, `production`, `service`, `finance`.
- `Source document` and `Target document` describe the business voucher flow, not the HTTP route.
- Project number (`project_code`) and cabinet number (`cabinet_no`) are recommended traceability fields. They are filled when existing data supports them and left blank when the document type does not require them (per `require_project_cabinet` system option, currently disabled).
- Reports referenced in `Report reconciliation` are read-only. No report writes business data.

Legend for `Result`: `PASS`, `FAIL`, `BLOCKED`, `PENDING`.

---

## Loop 1: Sales Order To Shipment To Receivable

- **Business loop**: sales order -> shipment -> sales invoice/receivable -> customer receipt follow-up.
- **Source document**: sales order (`/sales/new`).
- **Target document**: shipment, sales invoice, receivable, customer receipt.
- **Owner role**: `sales` (order and shipment), `finance` (invoice, receivable, receipt).

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 1.1 Create sales order | `/sales/new` | sales | Enter customer, product lines, project_code, cabinet_no; save and submit | Sales order row created with status `submitted`; appears in `/sales-orders` list | `/sales/reports/sales-order-execution-detail` shows the new order | | | PENDING |
| 1.2 Audit sales order | `/sales/<order_id>/audit` | sales | Audit the submitted order | Order status becomes `audited`; eligible for shipment | `/sales-orders` list shows `audited` status and next action `发货` | | | PENDING |
| 1.3 Create shipment | `/shipments/new` | sales | Source the audited sales order, enter shipment lines, save and audit | Shipment row created; inventory outbound posted; order shipment quantity updated | `/transactions` shows outbound stock transaction; `/sales/reports/sales-shipment-reports` shows the shipment | | | PENDING |
| 1.4 Create sales invoice | `/sales-invoices/new` | finance | Source the shipment, enter invoice amount, confirm | Sales invoice row created; receivable generated | `/sales-invoices` list shows the invoice; `/finance/reports/sales-invoice-reconciliation` reconciles invoice to shipment | | | PENDING |
| 1.5 Verify receivable | `/receivables` | finance | Open the receivable generated from the invoice | Receivable row shows source order, amount, and open balance | `/finance/reports/aging` shows the receivable in the correct aging bucket | | | PENDING |
| 1.6 Record customer receipt | `/customer-receipts/new` | finance | Apply receipt to the receivable, save | Receivable balance reduced; cash-bank journal entry posted | `/finance/receivable-payable` workbench shows reduced balance; `/finance/cash-bank/journal` shows the receipt | | | PENDING |

**Loop exit criteria**: sales order, shipment, invoice, receivable, and receipt reconcile by amount and by project/cabinet traceability where present. No sales report writes business data.

---

## Loop 2: Purchase Request To Receipt To Payable

- **Business loop**: purchase request -> purchase order -> purchase receipt -> purchase invoice/payable -> supplier payment follow-up.
- **Source document**: purchase request (`/purchase_request/new`).
- **Target document**: purchase order, purchase receipt, purchase invoice, payable, supplier payment.
- **Owner role**: `purchase` (request, order, receipt), `finance` (invoice, payable, payment).

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 2.1 Create purchase request | `/purchase_request/new` | purchase | Enter material lines, suggested supplier, project_code, cabinet_no; submit | Purchase request row created with status `submitted` | `/purchase_request` list shows the request and next action | | | PENDING |
| 2.2 Convert to purchase order | `/purchase_order/new` | purchase | Source the request, confirm supplier, price, quantity; audit | Purchase order row created with status `audited` | `/purchase-orders` list shows the order | | | PENDING |
| 2.3 Create purchase receipt | `/purchase_receipts/new` | purchase | Source the audited purchase order, enter received quantity, audit | Receipt row created; inventory inbound posted; order received quantity updated | `/transactions` shows inbound stock transaction; `/inventory/detail` shows increased balance | | | PENDING |
| 2.4 Create purchase invoice | `/purchase-invoices/new` | finance | Source the receipt, enter invoice amount, confirm | Purchase invoice row created; payable generated | `/purchase-invoices` list shows the invoice; `/finance/reports/purchase-invoice-reconciliation` reconciles invoice to receipt | | | PENDING |
| 2.5 Verify payable | `/payables` | finance | Open the payable generated from the invoice | Payable row shows source order, amount, and open balance | `/finance/reports/aging` shows the payable; `/finance/reports/unreceived-purchase-invoice` shows received-not-invoiced gaps (read-only) | | | PENDING |
| 2.6 Record supplier payment | `/payments/new` | finance | Apply payment to the payable, save | Payable balance reduced; cash-bank journal entry posted | `/finance/receivable-payable` workbench shows reduced balance; `/finance/cash-bank/journal` shows the payment | | | PENDING |

**Loop exit criteria**: purchase request, order, receipt, invoice, payable, and payment reconcile by amount and by material/project traceability. Payable view belongs to finance and is not turned into a purchase document page.

---

## Loop 3: Inventory Posting And Balance

- **Business loop**: inventory document -> stock posting -> balance -> transaction trace -> report.
- **Source document**: inventory inbound/outbound/transfer/adjustment/check.
- **Target document**: stock transaction, inventory balance, batch tracking.
- **Owner role**: `warehouse` (documents), `admin` (adjustment, check).

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 3.1 Other inbound | `/inventory/inbound/new` | warehouse | Enter material, warehouse, location, quantity, project_code, cabinet_no; audit | Stock transaction created; inventory balance increased | `/inventory/detail` shows increased balance; `/transactions` shows the inbound row | | | PENDING |
| 3.2 Other outbound | `/inventory/outbound/new` | warehouse | Enter material, warehouse, quantity; audit | Stock transaction created; inventory balance decreased | `/inventory/detail` shows decreased balance; `/transactions` shows the outbound row | | | PENDING |
| 3.3 Transfer | `/transfers/new` | warehouse | Enter source warehouse, target warehouse, material, quantity; post | Two stock transactions created (out from source, in to target); balances updated for both warehouses | `/inventory/detail` shows both warehouse balances; `/transactions` shows paired rows | | | PENDING |
| 3.4 Adjustment | `/adjustments/new` | admin | Enter material, warehouse, adjustment quantity; post | Stock transaction created; balance adjusted to target quantity | `/inventory/detail` shows adjusted balance; `/transactions` shows the adjustment row | | | PENDING |
| 3.5 Inventory check | `/inventory_checks/new` | warehouse | Enter check scope, count result; post | Stock transaction created for difference; balance adjusted to counted quantity | `/inventory/reports/check-difference` shows the check difference; `/inventory/detail` shows corrected balance | | | PENDING |
| 3.6 Balance consistency | `scripts/audit_inventory_balance_consistency.py` | admin | Run the audit script | `findings=0` | Inventory balance agrees with stock transaction trace for the tested documents | | | PENDING |

**Loop exit criteria**: inventory list, entry, detail, query, and report pages remain separate. Balance and transaction trace agree for every tested document. Inventory consistency audit returns `findings=0`.

---

## Loop 4: Engineering BOM To Kitting Readiness

- **Business loop**: sales/project trace -> engineering technical confirmation -> BOM/routing/drawing readiness -> kitting shortage.
- **Source document**: engineering technical confirmation (`/engineering/technical-confirmations/new`).
- **Target document**: BOM, BOM ECN, routing, work center, drawing ledger, kitting readiness.
- **Owner role**: `production` (engineering confirmation), `production` (BOM, routing, work center).

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 4.1 Technical confirmation | `/engineering/technical-confirmations/new` | production | Enter project_code, cabinet_no, product; confirm | Technical confirmation row created with status `confirmed` | `/engineering/technical-confirmations` list shows the confirmation | | | PENDING |
| 4.2 Create BOM | `/bom/new` | production | Enter product, material lines, quantities; approve | BOM row created with status `approved` | `/bom` list shows the BOM; `/bom/<bom_key>/structure` shows the structure | | | PENDING |
| 4.3 Create routing | `/production-routings/new` | production | Enter product, operations, work centers; save | Routing row created | `/production-routings` list shows the routing | | | PENDING |
| 4.4 Verify work center | `/work-centers/new` | production | Enter work center code, name, capacity | Work center row created | `/work-centers` list shows the work center | | | PENDING |
| 4.5 Drawing ledger | `/engineering/drawings/new` | production | Enter drawing number, product, version; release | Drawing ledger row created with status `released` | `/engineering/drawings` list shows the drawing | | | PENDING |
| 4.6 Kitting readiness | `/engineering/kitting` | production | Select product/BOM, run kitting check | Kitting result shows available, short, and blocked materials | Kitting page shows blocked reason and next action for each short material | | | PENDING |

**Loop exit criteria**: engineering pages do not act as production work-order entry pages. BOM/ECN pages do not mutate inventory, production, or finance documents directly. Kitting readiness can be reviewed from existing data.

---

## Loop 5: Work Order To Issue To Completion

- **Business loop**: work order -> material issue/return -> operation report -> completion inbound -> WIP/cost evidence.
- **Source document**: work order (`/work-orders/new`).
- **Target document**: production issue, production return, operation report, completion inbound.
- **Owner role**: `production`.

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 5.1 Create work order | `/work-orders/new` | production | Enter product, BOM, routing, project_code, cabinet_no, quantity; save | Work order row created with status `draft` | `/work-orders` list shows the order | | | PENDING |
| 5.2 Issue materials | `/work-orders/<id>/issue-materials` | production | Issue materials per BOM requirements | Production issue row created; inventory outbound posted; WIP material cost accumulated | `/transactions` shows outbound; `/production/execution-wip` shows WIP | | | PENDING |
| 5.3 Operation report | `/production/operation-reports/new` | production | Enter completed quantity, work center, labor time; submit | Operation report row created; work order completed quantity updated | `/production/operation-reports` list shows the report | | | PENDING |
| 5.4 Completion inbound | `/work-orders/<id>/complete` | production | Enter completion quantity; save | Completion inbound row created; inventory inbound posted; WIP reduced | `/transactions` shows inbound; `/inventory/detail` shows finished goods balance | | | PENDING |
| 5.5 Return materials | `/production-returns/new` | production | Return unused materials to warehouse | Production return row created; inventory inbound posted; WIP reduced | `/transactions` shows return inbound; `/production/execution-wip` shows reduced WIP | | | PENDING |
| 5.6 Work order cost | `/cost/project/<project_code>` | production | Review cost for the work order project | Cost summary shows material, labor, overhead by cabinet_no | `/cost/reconciliation` reconciles cost to inventory posting | | | PENDING |

**Loop exit criteria**: work order creation, list, detail, issue, return, operation, and completion behavior are not mixed into one ambiguous page. `/work-orders` (list) and `/work-orders/new` (entry) remain distinct. Production report pages do not post inventory or finance.

---

## Loop 6: Subcontracting Issue And Receive

- **Business loop**: subcontract order -> issue to processor -> receive from processor -> variance/WIP -> payable follow-up.
- **Source document**: subcontract order (`/subcontract/new`).
- **Target document**: subcontract issue, subcontract receive, subcontract WIP, payable.
- **Owner role**: `purchase` (subcontract order, issue, receive).

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 6.1 Create subcontract order | `/subcontract/new` | purchase | Enter processor, product, process, quantity, project_code, cabinet_no; release | Subcontract order row created with status `released` | `/subcontract` list shows the order | | | PENDING |
| 6.2 Issue to processor | `/subcontract_issue/new` | purchase | Source the subcontract order, enter material issue quantity; audit | Subcontract issue row created; inventory outbound posted; subcontract WIP increased | `/transactions` shows outbound; `/inventory/reports/subcontract-wip` shows WIP | | | PENDING |
| 6.3 Receive from processor | `/subcontract_receive/new` | purchase | Source the subcontract order, enter received quantity; audit | Subcontract receive row created; inventory inbound posted; subcontract WIP reduced | `/transactions` shows inbound; `/inventory/reports/subcontract-execution` shows execution | | | PENDING |
| 6.4 Variance check | `/inventory/reports/subcontract-variance` | purchase | Review variance between issue and receive | Variance report shows any quantity difference | `/inventory/reports/subcontract-variance` shows difference and next action | | | PENDING |
| 6.5 Payable reconciliation | `/inventory/reports/subcontract-payable-reconcile` | finance | Reconcile subcontract receive to payable | Reconciliation report matches receive to payable | `/inventory/reports/subcontract-payable-reconcile` shows matched and unmatched rows (read-only) | | | PENDING |

**Loop exit criteria**: subcontract issue and receive lists remain lists only. Issue and receive creation use document-entry pages (`/subcontract_issue/new`, `/subcontract_receive/new`), not list-page editing. Reports reconcile existing documents without posting finance.

---

## Loop 7: Service Order To RMA Closure

- **Business loop**: service card -> service order -> RMA -> recovery/cost follow-up.
- **Source document**: service card (`/service-cards`).
- **Target document**: service order, service acceptance, RMA.
- **Owner role**: `service`.

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 7.1 Verify service card | `/service-cards` | service | Open the service card for the cabinet_no | Service card shows cabinet_no, customer, installation date, warranty status | `/service-cards` list shows the card | | | PENDING |
| 7.2 Create service order | `/service-orders/new` | service | Source the service card, enter fault description, owner; dispatch | Service order row created with status `dispatched` | `/service-orders` list shows the order and owner | | | PENDING |
| 7.3 Install acceptance | `/service-acceptance/new` | service | Enter acceptance check result for the service order | Acceptance row created | `/service-acceptance` list shows the acceptance | | | PENDING |
| 7.4 Create RMA | `/service-rmas/new` | service | Source the service order, enter RMA reason, quantity; save | RMA row created with owner and next action | `/service-rmas` list shows the RMA | | | PENDING |
| 7.5 RMA closure | `/service-rmas/<rma_id>/close` | service | Enter recovery result; close the RMA | RMA status becomes `closed`; service order reflects RMA handling state | `/service-orders` detail shows RMA handling state | | | PENDING |

**Loop exit criteria**: linked RMA has non-empty owner and next action when still open. Source service order reflects RMA handling state. Service workbench remains a queue and exception surface.

---

## Loop 8: Finance AR/AP Reconciliation

- **Business loop**: receivable/payable -> receipt/payment -> aging/statement/cash-bank reconciliation.
- **Source document**: receivable (`/receivables`), payable (`/payables`).
- **Target document**: customer receipt, supplier payment, cash-bank journal, voucher, aging report.
- **Owner role**: `finance`.

| Step | Route | Test account | Operation | Expected data effect | Report reconciliation | Blocked reason | Next action | Result |
|---|---|---|---|---|---|---|---|---|
| 8.1 Customer receipt | `/customer-receipts/new` | finance | Apply receipt to receivable; save | Receivable balance reduced; cash-bank journal entry posted | `/finance/cash-bank/journal` shows the receipt; `/finance/receivable-payable` shows reduced balance | | | PENDING |
| 8.2 Supplier payment | `/payments/new` | finance | Apply payment to payable; save | Payable balance reduced; cash-bank journal entry posted | `/finance/cash-bank/journal` shows the payment; `/finance/receivable-payable` shows reduced balance | | | PENDING |
| 8.3 Aging report | `/finance/reports/aging` | finance | Run aging report for current period | Aging report shows receivables and payables by bucket | `/finance/reports/aging` reconciles to `/receivables` and `/payables` totals | | | PENDING |
| 8.4 Bank reconciliation | `/finance/bank-reconciliation` | finance | Review bank reconciliation | Reconciliation shows matched and unmatched bank/cash entries | `/finance/bank-reconciliation` shows outstanding items (read-only) | | | PENDING |
| 8.5 Invoice matching | `/finance/reports/sales-three-way-match` | finance | Run sales three-way match | Match report shows order, shipment, invoice alignment | `/finance/reports/sales-three-way-match` shows matched and unmatched rows | | | PENDING |
| 8.6 Period close | `/finance/period-closing/check` | finance | Run period close checks | Close checks show pass/fail per check item | `/finance/closing-checks` shows check results (read-only) | | | PENDING |
| 8.7 Financial statements | `/finance/financial-statements` | finance | Review balance sheet and income statement | Statements reflect posted receivable, payable, receipt, payment | `/finance/reports/balance-sheet` and `/finance/reports/income-statement` reconcile to ledger | | | PENDING |

**Loop exit criteria**: finance document pages are restricted to `finance`/`admin` roles. AR/AP reports are read-only. No route handler writes finance tables directly when a posting service should own the write.

---

## Cross-Loop Traceability

Project number (`project_code`) and cabinet number (`cabinet_no`) are the main traceability axis. They flow through sales, BOM, purchase, inventory, outsourcing, work order, assembly, wiring, testing, shipment, on-site service, AR/AP, and cost reports.

- Verify traceability: open `/projects/<id>` and confirm the project ledger shows events from sales order through finance settlement.
- Verify cabinet traceability: open `/trace` and confirm the cabinet_no appears in shipment, work order, and service records where existing data supports it.

---

## Sign-Off

| Loop | Owner | Result | Date | Notes |
|---|---|---|---|---|
| 1 Sales | | PENDING | | |
| 2 Purchase | | PENDING | | |
| 3 Inventory | | PENDING | | |
| 4 Engineering/BOM | | PENDING | | |
| 5 Production | | PENDING | | |
| 6 Subcontracting | | PENDING | | |
| 7 Service | | PENDING | | |
| 8 Finance | | PENDING | | |

All routes referenced in this worksheet exist in the current package. No new route, schema field, menu entry, posting rule, or finance rule was introduced.
