# Report catalogue

Required by BRD §9.1. Every report named in §8, mapped to its source, its
drill-through, its phase and whether it exists today.

IDs are `RPT-NNN`. The BRD does not number its reports, so these are ours;
`requirement_response_matrix.md` carries the `BR-NNN` requirement each one
serves where there is a direct link.

---

## Rules that apply to every report

Stated once here rather than repeated in 90 rows. From §8.3, §8.1.1 and §8.3.6:

**Filters.** Company, period, building, unit, landlord, tenant, account,
payment method, status and currency, wherever each is relevant. Plus
**operating model**, which §8.1 makes mandatory on the dashboard.

**Every report must** open the source transaction, export to Excel, compare
periods, support scheduled delivery, and show when it was last updated.

**Four rules that are not negotiable** and that shape the design more than any
individual report:

1. **Never aggregate across operating models.** Head-lease rental revenue,
   owner-management gross tenant rent administered, and brokerage transaction
   value are not the same kind of number and must never sum into one "revenue"
   figure (§8.1). A combined view appears only when a user deliberately asks
   for it (§4.1.2).
2. **Operational counts query property models; financial actuals query posted
   accounting and analytic lines** (§8.3.6). A unit count and a rent figure do
   not come from the same place, and a report that mixes the two sources will
   disagree with the ledger.
3. **Actuals, commitments, forecasts and assumptions are distinct data types,
   and forecast lines never post** (§8.3.6, §8.1.1).
4. **Every dashboard total traces to source transactions** (§8.1.1).

**Sensitive reports** — any containing tenant, employee, bank, identity or
cheque data — use role-based access, masked exports, retention rules and an
**export audit log** (§8.3.6). Which role sees what is **OD-06**, outstanding.

**Status** is against the repository today: `Built`, `Partial`, `—` not started.

---

## §8.1 Management dashboard

| ID | Report | Source | Drill-through | Phase | Status |
| --- | --- | --- | --- | --- | --- |
| RPT-001 | Leadership dashboard — occupancy, unit states, rent contracted/invoiced/collected/overdue/forecast, listings, brokerage pipeline, vacancy loss, head-lease commitments, margin and coverage, expiries 30/60/90, cheques due, bounce rate, maintenance and SLA, facility headroom, banking status, unreconciled items, daily-rental exceptions | `c2p.ceo.dashboard` | every tile to its records | S2–S4 | Partial |
| RPT-002 | Operating-model filter on the dashboard | `c2p.ceo.dashboard` | — | S2 | — |
| RPT-003 | Owner-management view — gross rent administered, cheques in custody, due for deposit, deposited, cleared, bounced, replaced, paid directly to landlords, fee revenue, recoverable costs, owner balances | `c2p.management.contract`, `account.payment` | cheque and statement | S2 | — |
| RPT-004 | Brokerage view — listing and requirement pipelines, property and transaction value, milestone status, expected and earned commission, broker split, invoiced and collected, reversals, outstanding documentation | brokerage models | transaction | S3 | — |

## §8.1.1 Management reporting expectations

Each of these shows current result, previous period, budget or forecast, trend,
variance, responsible person, required action and supporting detail — **not a
transaction list** (§8.1.1).

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-005 | Property performance — revenue, landlord cost, direct and allocated operating cost, gross and net profit, margin, coverage, break-even occupancy, vacancy loss, underperforming buildings and units | analytic lines + `c2p.building` | S2 | Partial |
| RPT-006 | Occupancy and leasing — unit states, days vacant, asking vs. contracted rent, lead pipeline, conversion, lost reasons | `c2p.unit`, `crm.lead` | S2 | Partial |
| RPT-007 | Lease expiry and renewals — 30/60/90, renewal status, tenant response, current and proposed rent, approved increase, rent at risk, non-renewal notice, next action | `c2p.lease` | S2 | Partial |
| RPT-008 | Brokerage performance — listings, mandates, requirements, enquiries, viewings, offers, stages, pipeline and completed value, commission expected/earned/billed/collected/reversed/outstanding, splits, conversion, cycle time, ageing, missing documents, client-fund status, lost reasons | brokerage models | S3 | — |
| RPT-009 | Accounts and collections — rent invoiced/collected/overdue, tenant ageing, cheque custody, due-date deposits, clearance, bounce, replacement, security deposits, landlord commitments, owner-management landlord-name cheques, company fees, owner balances | `account.move`, `account.payment` | S2 | Partial |
| RPT-010 | Cash and facilities — bank and cash balances, committed inflows and outflows, rolling forecast, funding gaps, landlord payments, loan instalments, facility limit, utilisation, interest, headroom | `account.payment`, `c2p.bank.facility` | S2 | Partial |
| RPT-011 | Maintenance and compliance — open requests, priority, SLA, repeat issues, cost, tenant recharge, vendor performance, PPM, insurance, certificates, expiring statutory obligations | Helpdesk, `c2p.property.compliance` | S3 | — |
| RPT-012 | Integration and banking controls — app submissions and ticket sync, duplicate prevention, failed messages, retries, SLA; host-to-host files and transactions, approvals, acknowledgements, accepted/rejected/pending, statement retrieval, reconciliation, cut-off and duplicate exceptions; DEWA and Ejari requests, acknowledgements, references, status, rejected/pending, retries, manual fallback, unresolved actions | integration logs | S3–S4 | — |
| RPT-013 | Implementation and budget — approved budget, committed cost, actual, forecast at completion, milestone and payment status, approved changes, pending change requests, contingency usage, risks, decisions required | project | S2 | — |

## §8.2 Operational reports

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-014 | Availability calendar by building, unit and term type | `c2p.unit` | S2 | — |
| RPT-015 | Lead conversion by source, agent, building, lost reason, cycle time | `crm.lead` | S2 | — |
| RPT-016 | Brokerage pipeline by listing or requirement, party, property, broker, source, stage, expected value, agreed and earned commission, invoice, collection, split, documents, ageing, lost or cancelled reason | brokerage models | S3 | — |
| RPT-017 | Rent roll | `c2p.lease` | S2 | Partial |
| RPT-018 | Lease register | `c2p.lease` | S2 | Partial |
| RPT-019 | Renewal pipeline | `c2p.lease` | S2 | Partial |
| RPT-020 | Move-in / move-out list | `c2p.property.handover` | S3 | — |
| RPT-021 | Deposit register | `account.payment`, deposits | S2 | — |
| RPT-022 | Aged receivables | `account.move.line` | S2 | — |
| RPT-023 | Collection forecast | `account.payment` | S2 | Partial |
| RPT-024 | Cheque custody and maturity | `account.payment` | S2 | Partial |
| RPT-025 | Bounced and replaced instruments | `account.payment` | S2 | Partial |
| RPT-026 | Banking host-to-host control — outbound files and transactions, approval and release, acknowledgements, accepted/rejected/pending/resubmitted, statement retrieval, reconciliation status, duplicate and cut-off exceptions, audit references | banking integration | S4 | — |
| RPT-027 | Landlord commitment schedule and 30/60/90-day cash forecast | `c2p.head.lease`, `account.payment` | S2 | Partial |
| RPT-028 | Profit and loss and cash contribution by company, building and unit | analytic lines | S2 | Partial |
| RPT-029 | Maintenance volume, cost, SLA, repeat issue, vendor performance, tenant recharge | Helpdesk | S3 | — |
| RPT-030 | Company-app maintenance intake — submissions, ticket creation status, duplicate or failed integrations, retry status, response and resolution SLA, customer status updates, manual outage entries | integration log | S3 | — |
| RPT-031 | DEWA and Ejari integration control — requests by company, property, unit, party, lease; submission and acknowledgement references; registration, utility, final-bill and clearance status; rejected, pending, duplicate, retried, resubmitted, manual items; fees and receipts; status mismatches; ageing; follow-up | integration log | S4 | — |
| RPT-032 | Monthly building maintenance budget — approved limit per building, commitments, actual spend, remaining balance, utilisation, projected month-end, CEO-approved changes, reallocations, emergency overrides, excess expenditure, variance by category and manager | maintenance limit model | S3 | — |
| RPT-033 | Exception report — overlapping dates, missing documents, inactive registration, manual price override, tax override, cancelled invoice, backdated entry, **approval bypass attempt** | multiple | S2 | — |

## §8.2.1 Tenant lifecycle monitoring

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-034 | Enquiry-to-contract funnel by source, agent, stage, property type, lost reason, elapsed time | `crm.lead` | S2 | — |
| RPT-035 | Tenant onboarding and KYC checklist — incomplete, expired, unverified, waived, due to expire | checklist model | S2 | — |
| RPT-036 | Quotation register — issued, expiring, accepted, rejected, revised, below-floor, waived-fee, pending approval | `sale.order` | S2 | — |
| RPT-037 | Third-party cheque register and exceptions by tenant, payer, building/unit, approval, undertaking, maturity, status | `account.payment` | S2 | — |
| RPT-038 | Active tenancy monitoring — arrears, bounced and held cheques, complaints, breaches, warnings, utility anomalies, missing deposits, legal cases, renewal restrictions | tenancy event model | S3 | — |
| RPT-039 | Renewal pipeline 90/60/30 with proposed and approved rent, tenant response, document and payment readiness, registration status | `c2p.lease` | S3 | Partial |
| RPT-040 | Non-renewal and termination register — basis, approval, notice dates, effective and cure dates, delivery evidence, acknowledgement, legal status, outstanding dues, move-out progress | notice workflow | S3 | — |
| RPT-041 | Move-out and settlement — inspections, utilities, keys, damages, deposit deductions and refunds, cheque disposition, final balance, unit block, next availability | handover | S3 | — |

## §8.2.2 Tenant file and addendum control

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-042 | Tenant file completeness by building, unit, lease, tenant type, stage, responsible team, checklist status | checklist | S2 | — |
| RPT-043 | Missing, rejected, waived, expired and due-to-expire identity, company, receipt, contract, Ejari, addendum and move-in documents | checklist | S2 | — |
| RPT-044 | Contract-pack exceptions — unsigned contracts or addenda, wrong or superseded template version, mismatched building/use clause set, missing signatures, unapproved clause overrides | clause library | S3 | — |
| RPT-045 | Payment readiness — reconciles deposit, first rent, administration fee, commission, utility deposit, receipts and PDCs to the approved quotation and lease schedule | checklist, `account.payment` | S2 | — |
| RPT-046 | Commercial fit-out and NOC — plans, approval, authority status, work period, inspections, completion certificate, exceptions, occupancy readiness | `c2p.tenant.fitout` | S3 | — |
| RPT-047 | Move-in and move-out readiness — inventory, meters, keys and access, parking, utilities, Ejari, damages, deposit settlement, permits, unit-release status | handover | S3 | — |

## §8.2.3 Move-in / move-out inspection

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-048 | Inspection readiness and completion by building, unit type, lease, scheduled date, inspector, template version, signature status | handover | S3 | — |
| RPT-049 | Template applicability exceptions — missing template, **multiple active templates**, room-count mismatch, missing mandatory item, unapproved override, inspection completed on a superseded template | handover template | S3 | — |
| RPT-050 | Move-in vs. move-out condition variance by room and item, damage class, responsibility, estimated and approved charge, invoice or deposit deduction, unresolved maintenance action | handover item | S3 | — |
| RPT-051 | Keys and access custody — issued, returned, missing, damaged, deactivated, replacement-charged | access custody | S3 | — |
| RPT-052 | Meter reading and utility handover exceptions — missing readings or photos, duplicate values, unlinked DEWA deposit receipts | meter readings | S3 | — |
| RPT-053 | Furnished inventory variance by expected and observed quantity, condition, serial or asset reference, replacement status | handover item | S3 | — |

## §8.2.4 Intercompany and related party

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-054 | Intercompany transaction register by providing and receiving company, related-party category, document type, source reference, service period, currency, tax, gross amount, status, approval | `account.move` | S4 | — |
| RPT-055 | Due-to / due-from reconciliation by entity pair, account, document, currency, ageing bucket, settlement date, unmatched reason | `account.move.line` | S4 | — |
| RPT-056 | Reciprocal income and expense matrix — service fees, brokerage and commission, payroll allocations, shared costs, maintenance, procurement, utilities, other recharges | `account.move` | S4 | — |
| RPT-057 | Allocation report — source cost pool, driver, recipients, allocated amounts, residual balance, evidence, approval | allocation model | S4 | — |
| RPT-058 | Intercompany settlement and netting statement — opening balances, transactions, credit notes, payments, offsets, closing balances by company pair | `account.move.line` | S4 | — |
| RPT-059 | Combined view — pre-elimination balances, matched eliminations, unresolved differences, post-elimination totals. **Seventh Heaven appears only if activated** | consolidation | S4 | — |

## §8.2.5 Employee and payroll

All restricted; see the sensitive-report rule above.

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-060 | Employee master and contract register by company, department, position, manager, location, status, join date, probation end, contract expiry, payroll eligibility | `hr.employee`, `hr.contract` | S4 | — |
| RPT-061 | Onboarding and document expiry — contracts, identity and visa, bank and WPS, insurance, equipment and access, induction, probation review | `hr` | S4 | — |
| RPT-062 | Payroll register by period and employee — basic, allowances, variable earnings, deductions, gross, net, payable days, payment method, status | `hr.payslip` | S4 | — |
| RPT-063 | Payroll variance — current vs. prior period and contract baseline, highlighting joiners, leavers, unpaid leave, component changes, bank changes, manual adjustments | `hr.payslip` | S4 | — |
| RPT-064 | Salary-transfer reconciliation — payslip count and net total, transfer-file count and total, accepted, rejected, returned and resubmitted records, accounting payment status | transfer batch | S4 | — |
| RPT-065 | Salary certificate register — request date, purpose and addressee, approved remuneration source, issuer, signatory, issue date, document version | letter request | S4 | — |

## §8.3 Accounts report and template catalogue

Each row names the client's reference workbook, which is the acceptance
baseline: §8.3.7 requires reproducing an approved month from each and
reconciling to the source workbook **and** the general ledger.

| ID | Report | Source | Reference workbook | Phase | Status |
| --- | --- | --- | --- | --- | --- |
| RPT-066 | Unit costing and pricing — by building, unit type, size, market rent, floor rent, vacancy assumption, landlord and operating cost allocation, commission, incentives, target margin; retains requested, calculated, approved and final prices with approver and effective dates | `c2p.unit.pricing.scenario` | Building income net profit fY.xlsx; building-wise P&L | S3 | — |
| RPT-067 | Property-wise profit and loss — contract value, landlord rent, recognised rental income, other income, direct expenses, indirect allocation, current and expected vacancy loss, gross profit, net profit, net margin. **Must reconcile to the trial balance** | analytic lines | building-wise P&L; P&L NS 2024 | S2 | Partial |
| RPT-068 | Daily collection and payment issued — by date, payer/payee, company, operating model, building, unit, instrument, bank or landlord deposit account, amount, invoice, status, user. **Distinguishes company receipts from landlord-name instruments** | `account.payment` | payments 31-10-26.xlsx | S2 | — |
| RPT-069 | Tenant receivable and ageing — current, 1–30, 31–60, 61–90, 90+, including disputed, promised, legal, written-off, cheque-held, bounced and payment-plan amounts, with last and next action, collector, expected collection date, provision status | `account.move.line` | Cheque holding list; BANK ANTICIPATION | S2 | — |
| RPT-070 | Property-wise expense and utility — supplier, invoice, category, building, unit, ticket, service period, tax, gross, payment status, recoverability; DEWA, electricity, water, telecoms, cleaning, lift, fire safety, pest control, pool, waste, insurance and general maintenance separated | `account.move` | P&L NS 2024; Building income net profit | S2 | — |
| RPT-071 | Budget vs. actual — approved budget, latest forecast, actual, commitment, variance amount and percentage, commentary, by company, building, account and month. **Budget baseline locked, changes versioned** | budget | CASH FLOW projection; fund flow proj | S3 | — |
| RPT-072 | Fund flow and cash-flow projection — confirmed balances, tenant collections, PDC receipts, expected renewals, other income, landlord commitments, supplier payments, loan instalments, payroll, utilities, maintenance, tax, vacancy and bad-debt assumptions; daily and monthly opening, inflow, outflow, closing, minimum cash point, funding gap, scenario. **Actual, committed, expected and assumption-based lines distinguished** | multiple | CASH FLOW projection; fund flow proj; BANK ANTICIPATION | S2 | Partial |
| RPT-073 | Bank reconciliation and anticipation — statement to ledger, plus anticipated balances from PDC receipts and committed transfers; unmatched, duplicate, stale, reversed, bounced, held and "do not deposit" items. **Anticipated receipts are never cleared cash.** Preparer and reviewer segregated | `account.bank.statement` | BANK ANTICIPATION.xlsx | S2 | — |
| RPT-074 | Payables ageing and landlord payment schedule — suppliers and landlords by due date, ageing bucket, contract, building, invoice, cheque, tax, amount, paid, balance, disputed status, planned payment date, priority. Landlord schedules link to head-lease instalments and renewal assumptions | `account.move`, `c2p.head.lease` | payments; fund flow proj | S2 | Partial |
| RPT-075 | Security deposits, DEWA deposits and cheque custody — separate liability and asset registers for tenant deposits, landlord deposits, DEWA deposits, held cheques and bounce charges; receipt, refund, deduction, transfer, balance, custody location, ageing, settlement, evidence | deposits, `account.payment` | Cheque holding list; BANK ANTICIPATION | S2 | — |
| RPT-076 | Vacancy and occupancy — unit states by building, vacancy days, potential rent, vacancy loss, occupancy percentage, next available date, reason. **Physical vacancy, economic vacancy and approved free periods separated** | `c2p.unit` | building-wise P&L; rental income record | S2 | Partial |
| RPT-077 | VAT, corporate tax and fixed assets — output and input VAT by tax code, exempt and out-of-scope tracking, adjustments, return reconciliation, payable/receivable summary; corporate tax accounting profit, adjustments, taxable income, losses and credits, provision; fixed assets by class, location, acquisition, capitalisation, depreciation, disposal, NBV | `account.tax`, assets | P&L NS 2024 + templates to prepare | S4 | — |
| RPT-078 | Maintenance stock and material usage — purchases, receipts, issues, returns, transfers, adjustments, closing stock by item, store, building, unit, ticket, supplier, quantity, unit cost, value; slow-moving, obsolete, negative and unallocated stock identified | `stock` | template to prepare | S3 | — |
| RPT-079 | Monthly rental income recognition — advance tenant rent to income by lease, building, unit, period, days, gross rent, credit note, billed, recognised, deferred balance, exceptions; annual, monthly, short-term, extensions, reversals, cancellations, discounts, credit notes | recognition lines | rental income record; Short-term leases data | S2 | — |
| RPT-080 | Monthly landlord rental expense and prepayments — source contract and bill, start and end date, total days, monthly days, opening balance, expense recognised, additions and adjustments, closing prepaid/accrual | `c2p.contract.recognition.line` | PREPAYMENTS SHEET.xlsx | S2 | — |
| RPT-081 | IFRS 16 statutory lease accounting and financial statements — population, commencement measurement, ROU assets, lease liabilities, depreciation, finance cost, payments, remeasurements, modifications, terminations, impairments, current/non-current split, closing balances; statutory statements and disclosures; **plus the management-to-statutory bridge** | `c2p.lease.accounting` | — | S4 | — |
| RPT-082 | Facility usage and borrowing — limit, drawdowns, repayment schedule, principal paid, interest paid and accrued, fees, outstanding principal, headroom, maturity, rate, covenant and renewal dates, linked bank transactions | `c2p.bank.facility` | FACILITY USAGE.xlsx | S2 | Partial |

## §8.3.1 Additional building-management reports

| ID | Report | Source | Phase | Status |
| --- | --- | --- | --- | --- |
| RPT-083 | Building management contract master — one row per contract version, with portfolio totals, annualised amounts, expiry buckets, occupancy and revenue-to-commitment. **Warns on missing or duplicate building codes, expired contracts, notice windows, unresolved vacancies, bounced cheques, missing agreements and inconsistent unit totals** | `c2p.head.lease`, `c2p.building` | S2 | — |
| RPT-084 | Insurance and statutory compliance register — property insurance and TPL tracked separately, plus lift, fire alarm and firefighting, 24×7 Civil Defence, BMS, barriers, AC, pest control, waste removal, water testing and other AMCs; 90/60/30-day reminders; dashboard for expired, expiring, missing-copy, pending-quote, uninsured and responsibility-disputed items | `c2p.property.compliance` | S2 | — |
| RPT-085 | Landlord and property directory — legal and contact details, ownership and authority documents, bank and payee instructions, properties, building codes, contract model, active contracts, deposits, outstanding obligations, communication history. Restricted bank-detail changes with maker-checker | `res.partner` | S2 | — |
| RPT-086 | Building amenities and readiness — reception, parking, gym, pool, lift, access control, CCTV, fibre, meters, common-area utilities, furniture and appliances, with availability, condition, capacity, responsible party, handover status, photos, maintenance plan. Reports unavailable, defective, unverified or contractually required but missing amenities | `c2p.property.amenity` | S2 | — |
| RPT-087 | Unit rent, cost and profitability model — per unit: type, size, kitchen, bath, balcony, market, current, proposed and discounted rent, monthly and annual rent, allocated landlord cost, common costs, direct expenses, commissions, utilities, vacancy, renewal price, break-even rent, profit, margin, scenario. **Calculations transparent and versioned; formulas not editable without authorisation. Unit totals reconcile to building totals** | `c2p.unit.pricing.scenario` | S3 | — |
| RPT-088 | Tenant, tenancy and Ejari register — building and unit, tenant, contacts, tenancy dates, annual rent, payment frequency, Ejari number and status, renewal intention, manual-contract reason, move-out and final-bill status, prior tenant. **Contact information masked by role**; validates unique active tenancy and Ejari references | `c2p.lease` | S2 | Partial |
| RPT-089 | Landlord expense and rent-recognition schedule — contract, landlord, location, income type, rent, dates, contract days, grace and free period, recognition period, daily rate, first and last month days, monthly recognised expense, prepayment and accrual movement, amendments, cumulative totals. **Actual calendar-day conventions approved by Finance; overlapping recognition versions prevented** | `c2p.contract.recognition.line` | S2 | — |
| RPT-090 | Security deposit and cheque register — building, contract, deposit type, payer and payee, cheque number, date or undated, amount, custody, cleared/uncleared/returned/cancelled, return date, replacement, evidence. **Physical-to-system monthly count**, duplicate cheque validation, maker-checker changes, outstanding-return ageing | `account.payment` | S2 | Partial |

---

## Summary

| Status | Count |
| --- | --- |
| Built | 0 |
| Partial | 22 |
| Not started | 68 |

90 reports, RPT-001 to RPT-090, no gaps or duplicates. Counts are verified
against the rows by `tools/check_requirement_matrix.py`, which fails CI if they
drift.

**Nothing is finished.** The 22 partials are dashboard tiles and list views that
show the right figure but do not yet meet §8.3's bar: open the source
transaction, export, compare periods, schedule delivery, show last-updated. None
has been reconciled to a client workbook, which §8.3.7 makes the acceptance
test.

## Where the real work is

Three observations that the row count hides.

**The acceptance bar is reconciliation, not rendering.** §8.3.7 requires
reproducing an approved month from each supplied workbook and reconciling to
both the workbook and the general ledger, then proving that duplicate
instruments, overlapping recognition periods, invalid references and
unapproved overrides are blocked or reported. A report that displays the right
columns but does not tie to the ledger fails that test.

**Several reports are the control, not a view of it.** RPT-033 (approval bypass
attempts), RPT-049 (multiple active inspection templates), RPT-073 (anticipated
receipts never counted as cleared cash) and RPT-090 (physical-to-system cheque
count) exist to catch things going wrong. They need building with the
mechanism, not after it.

**Nothing here is independent of OD-06.** Every report carrying tenant,
employee, bank, identity or cheque data needs a role-to-visibility mapping and
an export audit log. The reports can be built; who may run them, and what is
masked in the export, cannot be settled without the approval and
segregation-of-duties rules.
