# Requirement response matrix

Required by BRD §9.1. Requirement IDs follow the §11.1 traceability template
(`BR-NNN`); **BR-001 to BR-003 are the BRD's own**, reproduced verbatim, with
the rest continuing from BR-004.

Source: `NSPM_requirements.docx`, "Business Requirements Document and User Guide
— Odoo Property Leasing, Management and Brokerage System", received 6 October
2026, sections 1–11.

## How to read this

**Class** — the §9.1 classification: `Std` standard Odoo, `Cfg` configuration,
`Cus` customization, `Int` integration, `Rep` report, `Mig` data migration,
`OoS` out of scope.

**Phase** — `S2` operational core, `S3` commercial and operations, `S4` finance
and statutory.

**Status** — against the repository today: `Built`, `Partial`, `—` not started.

**Priority** — `Must` where the BRD makes it a control, a block, or an
acceptance scenario; `Should` otherwise. Where the BRD does not state a
priority, the value here is this document's reading and is open to correction.

## What is deliberately not here

§9.1 also asks for **estimate, one-time cost, recurring cost and optional
cost** per requirement. Those columns are left for the commercial response and
are not filled in here. Effort and price are C2P commercial decisions; inferring
them from a specification would put numbers in a contract document that nobody
priced.

Dependencies on client decisions are named inline as `OD-nn` and are tracked in
`decisions_required.md`.

---

## §2–§3 Foundations

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BR-004 | 2.1 | Two legal entities, New Sinclair Property Management LLC and Sinclair Real Estate Brokers LLC, with controlled reciprocal intercompany | Must | Cfg | `res.company` | Multi-company with intercompany rules | S2 | Partial |
| BR-005 | 2.1, 4.3.1.1 | Seventh Heaven created **inactive**; activated only on separate approval | Must | Cfg | `res.company` | Inactive company record | S2 | — |
| BR-006 | 1.1, 6.4 | Financial year 1 Jan – 31 Dec, monthly periods, controlled period locking | Must | Cfg | `account` | Fiscal year and lock dates | S2 | — |
| BR-007 | 2.3 | Twenty roles exactly as listed; CEO absorbs Business Owner and General Manager and is **not** split | Must | Cfg | `res.groups` | Security groups per role | S2 | Partial |
| BR-008 | 2.3 | Tenants and landlords have **no** Odoo access | Must | Cfg | `res.users` | No portal grant | S2 | Built |
| BR-009 | 3.2 | Six controlled status models with defined transitions, roles, timestamps and reversal rights | Must | Cus | all | See `status_matrix.md` | S2–S3 | Partial |
| BR-010 | 3.2, 8.4 | No status overwritten without history; all key actions logged | Must | Std | `mail.tracking` | Tracked fields + audit | S2 | Partial |

---

## §4.1 Property and head-lease onboarding

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BR-011 | 4.1 | Owner record with required documents, validated | Must | Cfg | `res.partner` | Partner + document checklist | S2 | Partial |
| BR-012 | 4.1 | Building with its own analytic account | Must | Cus | `c2p.building` | Analytic account per building | S2 | Built |
| BR-013 | 4.1 | Head lease: term, fixed annual commitment, instalment count, deposit, registration, escalation/renewal, responsibilities, attachments | Must | Cus | `c2p.head.lease` | Extend existing model | S2 | Partial |
| BR-014 | 4.1 | **Prevent overlapping head leases on the same building** unless an approved renewal or amendment relationship exists | Must | Cus | `c2p.head.lease` | Constraint; today it blocks overlap with no renewal exception | S2 | Partial |
| BR-015 | 4.1 | Generate landlord payment schedule and outbound PDC schedule | Must | Cus | `c2p.head.lease`, `account.payment` | Wizard exists | S2 | Built |
| BR-016 | 4.1 | Units created individually or by controlled import; duplicate codes blocked; **totals reconciled to the building's declared counts** | Must | Cus | `c2p.unit`, `c2p.building` | Import + control totals | S2 | Partial |
| BR-017 | 4.1 | Market rent and floor/minimum rent by yearly, monthly and daily term | Must | Cus | `c2p.unit` | Three rate sets; floor rent drives the override block | S2 | Partial |
| BR-018 | 4.1 | Units released for marketing only after mandatory data and approval checks | Must | Cus | `c2p.unit` | Draft state and `action_release` built; the mandatory-data check is still to come, and the default moves to Draft with it | S2 | Partial |
| BR-019 | 4.1.1 | **Three operating models** — Head Lease, Owner Management, Brokerage — selecting accounting, payee, client-money, cheque, contract, approval, statement, commission and profitability behaviour | Must | Cus | `c2p.building`, contracts | Operating model drives downstream logic | S2 | Partial |
| BR-020 | 4.1.1 | Contract versions (offer/LOI, draft, approved, signed, amended, renewed, expired, terminated, archived) retained without overwriting | Must | Cus | `c2p.head.lease` | Version chain | S2 | — |
| BR-021 | 4.1.1 | Plot and municipality references, residential/commercial unit counts, amenities, handover condition, commencement trigger, free/grace period | Must | Cus | `c2p.building` | Field extension | S2 | — |
| BR-022 | 4.1.1 | Record subleasing permission, contracting/collection in owner's or manager's name, and authority to sign, register Ejari, collect, pursue arrears, appoint legal representatives, market, place staff/signage | Must | Cus | `c2p.head.lease` | Authority flags | S2 | — |
| BR-023 | 4.1.1 | Responsibility matrix per landlord agreement; major → landlord, minor/routine → New Sinclair; **unclear cases routed for case-by-case management approval** retaining assessment, evidence, approver, responsible party, recharge decision, financial treatment | Must | Cus | new model | Responsibility matrix + approval route (OD-06) | S3 | — |
| BR-024 | 4.1.1, 7.1 | Effective-dated **monthly maintenance limit per building**: amount, currency, warning threshold, responsible manager, covered categories, whether commitments consume it | Must | Cus | new model | Limit model | S3 | — |
| BR-025 | 4.1.1, 7.1 | CEO approves limit creation/change, cross-building reallocation, excess spend and emergency override, with reason, evidence and audit | Must | Cus | new model | Approval workflow | S3 | — |
| BR-026 | 4.1.1 | Dated obligations and reminders: rent instalments, guarantee cheques, insurance, TPL, lift/fire/Civil Defence AMCs, Ejari/NOC, handover, owner notices, renewal intent, deposit and cheque return | Must | Cus | `c2p.property.compliance` | Typed compliance model + activities | S2 | — |
| BR-027 | 4.1.1 | **Block activation** until mandatory ownership, authority, insurance, readiness, meter, certification and signed-contract documents are complete or an approved exception exists | Must | Cus | `c2p.head.lease`, `c2p.lease` | Activation gate | S2 | — |
| BR-028 | 4.1.2 | Head-lease landlord rent spread over the service period regardless of payment dates, free periods, deposits or PDCs | Must | Cus | new recognition model | Monthly recognition lines; amendments create reversal/delta, never overwrite posted periods | S2 | — |
| BR-029 | 4.1.2 | Owner-management fee as percentage **or** fixed amount, with basis, rate, period, limits, billing date, VAT, effective dates, leasing commission, renewal fees, reimbursable costs, owner balance | Must | Cus | `c2p.management.contract` | New model | S2 | — |
| BR-030 | 4.1.2, 6.3.2 | Brokerage commission **earned when the reservation or memorandum is signed and evidence is complete** — not on collection | Must | Cus | `c2p.brokerage.transaction` | Recognition milestone | S3 | — |
| BR-031 | 4.1.2, 8.1 | Head-lease profit, owner-management fee income and brokerage commission **separately identifiable**; combined only on deliberate user selection | Must | Rep | dashboard | Operating-model filter; no cross-model aggregation | S2–S3 | Partial |

---

## §4.2 Lead to occupancy, and brokerage

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BR-032 | 4.2 | All enquiries in CRM regardless of source (portal, website, WhatsApp, phone, walk-in, referral, broker, email, manual) | Must | Cfg | `crm.lead` | CRM pipeline | S2 | — |
| BR-033 | 4.2 | Eleven CRM stages: Enquiry → Contacted → Qualified → Viewing Scheduled → Viewed → Offer Made → Negotiation → Reserved → Contract Signed → Registration Pending → Moved In | Must | Cfg | `crm.stage` | Stage set | S2 | — |
| BR-034 | 4.2 | Lost enquiries closed with a reason | Must | Std | `crm.lead` | Lost reasons | S2 | — |
| BR-035 | 4.2 | Duplicate-contact warning; unit matching by type, dates, price, furnishing, location | Should | Cus | `crm.lead` | Duplicate detection + matcher | S2 | — |
| BR-036 | 4.2 | **Approval required before sending** offers below approved minimum rent, non-standard deposits, free periods, waived charges or daily-rental exceptions | Must | Cus | `c2p.lease` | Pending Approval state | S2 | — |
| BR-037 | 4.2.1 | Qualified enquiry flows into the Tenant Information Form without retyping; separate forms for individual and company, one linked record | Must | Cus | `res.partner` | TIF model | S2 | — |
| BR-038 | 4.2.1 | Configurable document checklist with **Required / Received / Verified / Expired / Rejected / Waived with Approval / Not Applicable**, verifier and date; contracting blocked where mandatory items incomplete | Must | Cus | new checklist model | Stage-gated checklist | S2 | — |
| BR-039 | 4.2.1 | Identity numbers and copies restricted: role-based access, export control, retention, masking, deletion/archival, approved before go-live | Must | Cus | checklist, partner | Field-level security (OD-06) | S2 | — |
| BR-040 | 4.2.1 | Duplicate applicant detection using permitted identifiers **without exposing restricted values** to unauthorised users | Must | Cus | `res.partner` | Hashed/masked match | S2 | — |
| BR-041 | 4.2.2 | Quotation built from selected unit and approved offer, showing the full charge set, payee instructions, validity and total due | Must | Cus | `sale.order` | Quotation template | S2 | — |
| BR-042 | 4.2.2 | Amounts sourced from approved pricing/tax/fee/deposit/commission rules; **manual override needs reason and approval** | Must | Cus | `sale.order` | Override gate | S2 | — |
| BR-043 | 4.2.2 | **Payee derived from the operating model**; under management-only, tenant cheques may be in the landlord's name and must not be presented as company funds | Must | Cus | `sale.order`, `account.payment` | Payee resolution | S2 | — |
| BR-044 | 4.2.2 | Quotation retains version, issue date, expiry, issuer, approver, delivery evidence, acceptance/rejection date, cancellation reason | Must | Cus | `sale.order` | Version + evidence | S2 | — |
| BR-045 | 4.2.3 | **Third-party cheque undertaking**: signed undertaking and management approval before the cheque is accepted; full payer, relationship, identity, bank, cheque and responsibility detail | Must | Cus | `account.payment` | Undertaking model | S2 | — |
| BR-046 | 4.2.3 | Validate payer against cheque details; **block activation** where undertaking or approval is missing | Must | Cus | `c2p.lease` | Activation gate | S2 | — |
| BR-047 | 4.2.3 | Third-party cheque linked to the tenant receivable while identifying the legal payer and payee separately | Must | Cus | `account.payment` | Payer vs. debtor split | S2 | — |
| BR-048 | 4.2.3 | Exception report: third-party cheques without valid documents, approval, identity verification or matching schedule line | Must | Rep | report | Exception list | S2 | — |
| BR-049 | 4.2.4 | Brokerage workflow: leads, listings, requirements, mandates, authority documents, broker assignment, marketing approval, viewings, offers, reservation/memorandum, due diligence, milestones, external coordination, commission, referral/co-broker, closure | Must | Cus | brokerage models | New model set | S3 | — |
| BR-050 | 4.2.4, 6.3.2 | **Client funds** (deposits, reservation amounts, sale proceeds) separately identified by client and transaction, reconciled, restricted, **never recognised as revenue** | Must | Cus | client-fund accounts | Control accounts + workflow (C2, OD-02) | S3 | — |

---

## §4.3 Reservations, intercompany, employees

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **BR-001** | 11.1, 4.3 | **Prevent overlapping active occupancy for a unit** *(BRD's own ID)* | Must | Cus | `c2p.unit`, `c2p.lease` | Activation now refused for any unit in an earning state, closing the notice and contracted holes; reservation and turnaround blocks still to come | S2 | Partial |
| BR-051 | 4.3 | Reservation holds a unit for a defined start and expiry date/time with a responsible agent | Must | Cus | new reservation model | Reserved state | S2 | — |
| BR-052 | 4.3 | Reservation fee, refundability, expiry, cancellation reason and conversion to lease recorded | Must | Cus | reservation | Fields + conversion | S2 | — |
| BR-053 | 4.3 | Expired unpaid reservations auto-release after a configurable grace period, with notification and audit | Must | Cus | reservation | Cron + activity | S2 | — |
| BR-054 | 4.3.1 | Each company exists as an Odoo company and a linked intercompany partner; **posting to itself prevented**; active approved relationship required | Must | Cus | `res.company`, `res.partner` | Counterparty model | S4 | — |
| BR-055 | 4.3.1 | Mirrored documents with source and counterpart references; **duplicate counterpart prevented**; reversals preserve both sides | Must | Cus | `account.move` | Mirror engine | S4 | — |
| BR-056 | 4.3.1 | Intercompany service fees and commissions with product, basis, period, rate, tax, analytic; rates effective-dated and approved | Must | Cus | `account.move` | Effective-dated rates | S4 | — |
| BR-057 | 4.3.1 | Cost recharges by actual, headcount, time, area, usage, fixed percentage or approved driver; **allocations must equal the source amount** and not duplicate external expense | Must | Cus | allocation model | Driver-based allocation | S4 | — |
| BR-058 | 4.3.1 | Separate due-to / due-from by counterparty and currency; netting requires approval and a reconciliation statement | Must | Cus | `account.account` | Control accounts | S4 | — |
| BR-059 | 4.3.1 | One employing entity per employee; cross-company allocation reconciles to payroll and **creates no duplicate salary expense** | Must | Cus | `hr.employee` | Allocation without duplication | S4 | — |
| BR-060 | 4.3.1 | Asset, inventory, key and access-device transfers between entities with dispatch/receipt confirmation; ownership and custody distinct | Should | Cus | `stock`, assets | Transfer workflow | S4 | — |
| BR-061 | 4.3.1 | Related-party classification, tax treatment, transfer-pricing basis and evidence per category; **cannot post through ordinary third-party accounts without the related-party flag** | Must | Cus | `account.move` | Related-party flag (T2) | S4 | — |
| BR-062 | 4.4 | Employee master with unique number, duplicate detection, role-based masking, effective-dated changes, expiry alerts, audit, retention | Must | Cfg | `hr.employee` | HR configuration | S4 | — |
| BR-063 | 4.4 | Onboarding tasks from approved employment details; **employment offers are prepared outside Odoo**; activation blocked until mandatory tasks complete or waived | Must | Cfg | `hr` | Onboarding plan | S4 | — |
| BR-064 | 4.4 | Bank details and compensation require **maker-checker** | Must | Cus | `hr.employee` | Two-person rule | S4 | — |
| BR-065 | 4.4 | Effective-dated contract versions; **no overwrite of signed or payroll-used terms**; amendments preserve prior versions | Must | Cfg | `hr.contract` | Version chain | S4 | — |
| BR-066 | 4.4 | Probation and fixed-term expiry reminders using the contract version effective on the decision date | Should | Cfg | `hr.contract` | Activities | S4 | — |
| BR-067 | 4.4 | Employee records kept **separate from tenant records** and restricted to HR, Payroll, Finance and designated approvers | Must | Cfg | `hr` | Access rules | S4 | — |

---

## §5 Lease products and lifecycle

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BR-068 | 5 | Yearly leasing as the default long-term product | Must | Cus | `c2p.lease` | Term type | S2 | Built |
| BR-069 | 5 | Monthly leasing with monthly rate, prorating rule and recurring invoice date | Must | Cus | `c2p.lease` | Term type | S2 | Partial |
| **BR-002** | 11.1, 5 | **Require approval for every daily-rental exception** *(BRD's own ID)* — disabled by default for ordinary users, mandatory named approver with reason and evidence | Must | Cus | `c2p.lease` | Exception workflow (OD-03) | S2 | — |
| BR-070 | 5 | Deposit 5% of annual rent **or** a fixed amount per approved tenancy terms or landlord agreement; basis and amount recorded on quotation and lease | Must | Cus | `c2p.lease` | Deposit basis field | S2 | Partial |
| BR-071 | 5, 9.2 | **1, 2, 3, 4, 6 or 12 cheques permitted**; a non-standard schedule is blocked until approved by the Leasing Director **or** Leasing Manager | Must | Cus | `c2p.lease`, `c2p.head.lease` | Schedule values built; approval gate needs the Pending Approval state | S2 | Partial |
| BR-072 | 5 | **Leasing approval rule**: Leasing Director or Leasing Manager approves any change from standard terms — payment count, rent, term, deposit, commission, free period, fees, notice terms, payment timing — before offer, reservation, contract or renewal is issued or activated | Must | Cus | `c2p.lease` | Approval gate (OD-06) | S2 | — |
| BR-073 | 5.1 | Lease inherits building, meter, analytic and approved pricing from the unit | Must | Cus | `c2p.lease` | Related fields | S2 | Partial |
| BR-074 | 5.1 | System calculates duration, rent, prorating, instalments, deposit, commission, taxes and other charges | Must | Cus | `c2p.lease` | Computes | S2 | Partial |
| BR-075 | 5.1 | **Activation without all cheques received** permitted only by case-by-case exception approved by Leasing Manager or CEO, recording missing items, reason, approval, conditions, deadline, responsible user and follow-up | Must | Cus | `c2p.lease` | `c2p.lease.cheque.exception`; gate on activation and on writing `state`; approver role provisional pending OD-06 | S2 | Built |
| BR-076 | 5.1 | On activation set the unit Occupied and create invoice/subscription and payment schedules | Must | Cus | `c2p.lease` | Existing activation | S2 | Built |
| BR-077 | 5.1.1 | Stage-gated tenant file checklist across five stages — Sales and application, Accounts and payments, Contract and registration, Move-in, Review and approval — with applicability by tenant type, use, building, furnishing, payment method, third-party payer and stage | Must | Cus | checklist model | Configurable checklist | S2 | — |
| BR-078 | 5.1.1 | Checklist amounts reconcile to the approved quotation and lease schedule; no item complete without evidence or approved non-cash treatment | Must | Cus | checklist | Reconciliation | S2 | — |
| BR-079 | 5.1.1 | Preparer, reviewer and approver **separate where configured** | Must | Cus | checklist | SoD (OD-06) | S2 | — |
| BR-080 | 5.1.2 | Bilingual tenancy contract generated from approved lease data, retaining template version, language, source lease, issuer, signatories, signature status and signed copy | Must | Cus | report + Sign | QWeb + e-signature | S2 | — |
| BR-081 | 5.1.2 | Contract **not generated from free-form retyped terms** where approved structured values exist | Must | Cus | report | Structured source only | S2 | — |
| BR-082 | 5.1.2 | Post-signature changes require an amendment or replacement version; **the signed original stays immutable** | Must | Cus | contract version | Immutability | S2 | — |
| BR-083 | 5.1.2 | Residential and commercial tenancies use distinct clause sets, approval rules and checklists | Must | Cus | clause library | Use-type split | S3 | — |
| BR-084 | 5.1.3 | Clause library of legally approved, **effective-dated** clauses; addendum generated from structured clauses, not uncontrolled per-unit copies | Must | Cus | `c2p.lease.clause`, `c2p.clause.set` | Clause engine | S3 | — |
| BR-085 | 5.1.3 | Conflicting or missing mandatory clauses **detected and blocked** before issue | Must | Cus | clause set | Conflict check | S3 | — |
| BR-086 | 5.1.3 | Exact clauses issued with each lease stored with it | Must | Cus | `c2p.lease.addendum` | Snapshot | S3 | — |
| BR-087 | 5.1.3 | Supplied residential addenda (CBD, Deyafa, Emerald, Hassan Jassim 2, Karama, Marwan, Reem, Satwa, Tawaweesh) migrated as reference clause sets **after legal harmonisation**; commercial addenda as separate commercial sets | Must | Mig | clause library | Post-legal migration | S3 | — |
| BR-088 | 5.1.3, 5.1.4 | **Sample tenant names, unit numbers, dates and contacts from source documents never become template defaults** | Must | Mig | templates | Migration rule + test | S3 | — |
| BR-089 | 5.1.4 | Handover template selected by building, unit type, bedroom/bathroom configuration, furnishing package, permitted use and effective date | Must | Cus | `c2p.handover.template` | Applicability rules | S3 | — |
| BR-090 | 5.1.4 | **Room instances generated from unit configuration**, not fixed rows; must support more than three bedrooms and bathrooms without a new template | Must | Cus | `c2p.property.handover` | Dynamic generation | S3 | — |
| BR-091 | 5.1.4 | Furnished inventory derived from the unit's approved furnishing package; brand alternatives normalised into item master plus model/variant | Should | Cus | handover item | Item master | S3 | — |
| BR-092 | 5.1.4.1 | Inspection header inherits tenant, building, unit, type, lease dates, contact, check-in date and configuration; captures inspector, AC number, electricity and water readings, DEWA account and deposit receipt, other meters, photographs; **manual change to inherited values requires authorisation and audit** | Must | Cus | handover | Inherited + locked | S3 | — |
| BR-093 | 5.1.4.2 | Each item captures expected and observed quantity, Present/Not Present/Not Applicable, move-in and move-out condition with remarks and photos, minor/major damage, tenant responsibility, action, estimated and approved charge, linked maintenance or accounting record | Must | Cus | `c2p.handover.item` | Item model | S3 | — |
| BR-094 | 5.1.4.2 | Condition scale **New / Good / Fair / Damaged / Missing / Not Applicable**; free-text Yes/No insufficient | Must | Cus | handover item | Selection | S3 | — |
| BR-095 | 5.1.4.2 | Move-out compares against the **immutable signed move-in baseline**; a changed baseline requires a documented correction workflow and both-party acknowledgement | Must | Cus | handover | Baseline lock | S3 | — |
| BR-096 | 5.1.4.2 | Charges from an approved rate, quotation or assessed amount, **approved before deposit deduction or invoice**; minor/major labels do not determine legal liability | Must | Cus | handover | Approval gate | S3 | — |
| BR-097 | 5.1.4.3 | Keys, cards, remotes, locks and devices tracked by type, identifier, quantity, issue/return condition, dates and custodian; completion needs both signatures or a documented refusal/absence process | Must | Cus | handover | Custody tracking | S3 | — |
| BR-098 | 5.3 | Tenancy monitoring: payment and cheque performance, arrears, promises, bounces, complaints, disturbances, unauthorised subletting, unusual utility use, missing deposits or documents, maintenance history, breaches, warnings, legal cases, resolutions — each with date, category, seriousness, evidence, owner, action, deadline, result and renewal impact | Must | Cus | new event model | Tenancy event log | S3 | — |
| BR-099 | 5.3 | Warnings, breach notices, non-renewals and terminations follow approved workflow with approved reason, evidence, correct notice method and legal review; **the system must not make legal decisions on its own** | Must | Cus | notice workflow | Human-gated | S3 | — |
| BR-100 | 5.4 | Renewal cases created automatically at configurable intervals, normally 90/60/30 days before expiry | Must | Cus | `c2p.lease` | Cron exists for alerts | S2 | Partial |
| BR-101 | 5.4 | Renewal calculates current and proposed rent, increase percentage, admin/renewal charges, registration fees, taxes, new period, payment count and any management-contract end-date restriction | Must | Cus | renewal wizard | Calculation | S3 | Partial |
| BR-102 | 5.4 | Proposal validated against approved market/rent-index and management rules; exceptions routed for approval | Must | Cus | renewal | Index validation (OD-03) | S3 | — |
| BR-103 | 5.4 | Notice wording, periods, automatic-renewal statements, rent-increase and fee wording **configurable by emirate, property type, contract and effective date, legally approved before use** | Must | Cfg | clause library | Effective-dated templates (OD-08) | S3 | — |
| BR-104 | 5.5 | Company-initiated non-renewal records the full fact set and approval; **final permissible occupancy date calculated but requiring human/legal confirmation before issue** | Must | Cus | notice workflow | Calculated, not issued | S3 | — |
| BR-105 | 5.5 | Non-renewal template uses neutral factual wording, **no unverified allegations, no automatic threat of legal action** | Must | Cfg | template | Approved wording (OD-08) | S3 | — |
| BR-106 | 5.6 | Early termination as a **separate workflow** distinguishing immediate notice, notice subject to cure, mutually agreed surrender, tenant-requested exit and termination at next renewal | Must | Cus | termination workflow | Separate model | S3 | — |
| BR-107 | 5.6 | Balances in a notice calculated from **posted and reconciled records as of a stated date**, authorised adjustment only | Must | Cus | termination | Posted-only source | S3 | — |
| BR-108 | 5.7 | Move-out checklist covering inspection, utility clearance, keys, dues, cheque handling, damage, deposit, final invoice, acknowledgement, filing, condition, cleaning block and next available date; **unit returns to Available only when all checks are complete** | Must | Cus | handover + unit | Closure gate | S3 | — |

---

## §6 Finance, billing and collections

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BR-109 | 6.1 | Invoices generated automatically from the activated lease per the approved schedule | Must | Cus | `account.move` | Subscription or schedule | S2 | Partial |
| BR-110 | 6.1 | Separate products and accounts for rent, deposit, commission, registration fees, service charges, utilities, maintenance recharge, penalties, discounts, refunds, credit notes and write-offs | Must | Cfg | `product` | Product set | S2 | Partial |
| BR-111 | 6.1 | Company, building, unit, lease, tenant, analytic, tax treatment and source stamped on every entry | Must | Cus | `account.move.line` | Analytic distribution | S2 | Partial |
| BR-112 | 6.1 | **Duplicate invoice generation prevented**; schedule line linked to invoice and payment | Must | Cus | `account.move` | Idempotency | S2 | — |
| BR-113 | 6.2 | Cheque schedules from lease or head lease with controlled manual change before confirmation | Must | Cus | `account.payment` | Wizard | S2 | Built |
| BR-114 | 6.2 | Daily views for instruments due, overdue, deposited, uncleared, bounced, replaced or missing | Must | Rep | `account.payment` | All seven states; daily filters for expected, due, overdue-not-received, deposited, bounced, ever-bounced, awaiting replacement and replaced | S2 | Built |
| BR-115 | 6.2 | Physical custody and handover recorded with user, date/time and acknowledgement | Must | Cus | `account.payment` | Custody history | S2 | — |
| BR-116 | 6.2, 6.3.1 | **Landlord-name cheques**: collected and held by New Sinclair, deposited to the landlord's bank account on the rent due date, with payee, tenant obligation, due date, custody, deposit date, deposit evidence and cleared/bounced status — **never company rent revenue or company cash** | Must | Cus | `account.payment`, custody account | Custody control account (C1, OD-02) | S2 | — |
| BR-117 | 6.2 | On bounce: reopen the receivable, record bank charges, create follow-up, notify, link the replacement instrument | Must | Cus | `account.payment` | Bounce reopens the receivable, raises follow-up and flags the history; replacement linked both ways. Bank charges still manual | S2 | Partial |
| BR-118 | 6.2 | Bank-statement import and reconciliation for company accounts; for landlord accounts, deposit evidence and an approved clearance/bounce confirmation process. **No cheque treated as cleared before bank or landlord confirmation** | Must | Cfg | `account.bank.statement` | Import + manual confirmation path | S2 | — |
| BR-119 | 6.2.1 | Host-to-host: transmit approved payroll/WPS files, receive technical and business acknowledgements and status, retrieve statements, feed reconciliation, with encryption, authentication, SoD, maker-checker release, identifiers, duplicate prevention, cut-off, retry, rejection/resubmission, response retention and audit | Must | Int | banking | Odoo side built; **bank certification is outside our control** (D1) | S4 | — |
| BR-120 | 6.2.2 | DEWA and Ejari connectivity assessed; approved authority interfaces or authorised providers only; requests mapped to company, building, unit, party, lease, document, payment and user; duplicates prevented; acknowledgements, status, rejection reasons and references captured | Must | Int | DEWA/Ejari | **No open DEWA third-party interface exists** (D2) | S4 | — |
| BR-121 | 6.2.2 | Where connectivity is unavailable, a controlled staff task records manual submission evidence, authority reference, status, receipt and completion — **not treated as an automated integration** | Must | Cus | Ejari task | Manual fallback (O4) | S4 | — |
| BR-122 | 6.3 | Per head lease and building: landlord cost, scheduled and paid amounts, contracted rent, invoiced rent, cash collected, operating costs, vacancy loss, gross margin, coverage, break-even occupancy and expected cash gap | Must | Rep | `c2p.building`, dashboard | Mostly built | S2 | Partial |
| BR-123 | 6.3 | **Coverage below 1.00 shown as critical**; other warning levels configurable | Must | Rep | dashboard | Threshold styling built; levels not yet configurable | S2 | Partial |
| BR-124 | 6.3.1 | Owner statement half-yearly or yearly per the agreement, showing rent due, cheques held/deposited/cleared/bounced, arrears, fees and VAT, approved expenses and closing owner balance | Must | Rep | owner statement | QWeb PDF + spreadsheet export | S2 | — |
| BR-125 | 6.3.1 | **Landlords do not use the portal**; authorised staff send approved PDF or spreadsheet by email or approved method, keeping proof of sending | Must | Cus | owner statement | Send + evidence | S2 | — |
| BR-126 | 6.3.2 | Commission calculated from approved rate, fixed amount, tier or contractual basis, retaining transaction value and calculation | Must | Cus | `c2p.commission.entitlement` | Calculation record | S3 | — |
| BR-127 | 6.3.2 | Broker, co-broker and referral shares **only from the deal-specific approved split**; no share payable until the entitlement is earned **and** its own approved payment condition is met | Must | Cus | `c2p.commission.split` | Per-deal conditions | S3 | — |
| BR-128 | 6.3.2 | Splits reconcile to the distributable amount | Must | Cus | commission split | Reconciliation constraint | S3 | — |
| BR-129 | 6.3.2 | Cancellations, failed completions, price changes, waivers, partial collections, refunds, clawbacks and disputes through approved adjustment or reversal workflows **preserving the original transaction** | Must | Cus | brokerage | Reversal workflow | S3 | — |
| BR-130 | 6.3.2 | Transaction closed only when documents and due diligence are complete, client funds settled, commission reconciled, broker liabilities settled or accrued and closure approval recorded | Must | Cus | brokerage | Closure gate | S3 | — |
| BR-131 | 6.4 | Separate books, bank accounts, taxes, receivables, payables, fixed assets, budgets and financial statements per entity | Must | Cfg | `account` | Multi-company | S2 | — |
| BR-132 | 6.4 | Combined reports identify and where required remove matched intercompany balances **without changing legal-entity records** | Must | Rep | consolidation | Pre-elimination, eliminations, unresolved differences | S4 | — |
| BR-133 | 6.4 | Tax treatment: residential rent exempt, first supply of residential zero-rated, commercial rent 5%, service charges 5%, commissions 5%, management fee 5%; VAT 201 grids separate exempt from standard-rated | Must | Cfg | `account.tax` | Tax set + grids | S2 | — |
| BR-134 | 6.4 | **Input VAT apportionment** for mixed portfolios | Must | Cus | `account.tax` | Mechanism parameterised; **method is the client's** (T1) | S4 | — |
| BR-135 | 6.4 | Final tax, transfer-pricing, tenancy, agency and client-money treatment **approved by appointed advisers before go-live** | Must | — | — | Decision gate (C1, C2, T1, T2) | S4 | — |
| BR-136 | 6.4.1 | IFRS 16 lease assessment: population, contract, identified asset, commencement, enforceable term, options, reasonably certain period, exemptions, currency and conclusion, **with Finance approval and evidence** | Must | Cus | `c2p.lease.accounting` | Assessment record (A1–A5) | S4 | — |
| BR-137 | 6.4.1 | Initial measurement: liability from in-scope payments at the approved rate; ROU asset with initial adjustments; payment scope, rate source, PV calculation and review evidence stored | Must | Cus | lease accounting | Measurement engine (A2, A5) | S4 | — |
| BR-138 | 6.4.1 | Subsequent: interest, principal reduction, ROU depreciation, closing balances, current/non-current split, remeasurement, modification, termination, impairment, FX | Must | Cus | lease accounting | Schedule generation (A6) | S4 | — |
| BR-139 | 6.4.1 | IFRS 16 posted through **dedicated statutory journals or an adjustment ledger** identifiable by company, lease, building, period and basis; **never overwriting contractual landlord bills, payments or management postings** | Must | Cus | `account.journal` | Separate ledger (A8) | S4 | — |
| BR-140 | 6.4.1 | **Management reports exclude statutory IFRS 16 by default, with no manual reversing entries** | Must | Rep | reports | Default filter | S4 | — |
| BR-141 | 6.4.1 | Reconciliations: opening to closing ROU and liability; contractual future payments to discounted liabilities; **management-to-statutory bridge** from landlord rent expense and prepaid/accrual to depreciation, finance cost and liability movement | Must | Rep | reports | Bridge report | S4 | — |
| BR-142 | 6.4.1 | **Sinclair is an intermediate lessor** — it subleases head-leased units. Sublease classification is a judgement | Must | — | — | **Flagged, not decided** (A11) | S4 | — |
| BR-143 | 6.5 | One payroll batch per company and period; joiners, leavers, unpaid leave, absences and contract changes prorated by an approved visible rule; **duplicate finalised payroll prevented** | Must | Cfg | `hr.payslip.run` | Payroll batches | S4 | — |
| BR-144 | 6.5 | Earnings and deductions with effective dates, calculation basis, accounting mapping, approval requirement and payslip display; manual adjustments need reason and evidence | Must | Cfg | `hr.salary.rule` | Rule set | S4 | — |
| BR-145 | 6.5 | Employee bank and WPS data as **restricted fields with maker-checker**; IBAN structure and mandatory identifiers validated | Must | Cus | `hr.employee` | Validation + two-person rule | S4 | — |
| BR-146 | 6.5 | **WPS SIF file** with detail and control records; layout, data types, sequence, rounding and naming **version-controlled**; employee count and net total **must reconcile to approved payslips** before release; retained with checksum, creator, approver and submission status | Must | Cus | WPS generator | File generator (D1) | S4 | — |
| BR-147 | 6.5 | Payroll stages Draft → Input Complete → Calculated → Reviewed → Approved → Transfer File Generated → Submitted → Accepted/Rejected → Posted/Paid → Closed; **preparer may not self-approve or release funds** | Must | Cus | payroll | State machine + SoD | S4 | — |
| BR-148 | 6.5 | Rejected records corrected and resubmitted **without regenerating an accepted file** and without duplicating accepted salaries | Must | Cus | payroll | Partial resubmission | S4 | — |

---

## §7 Maintenance, procurement and documents

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BR-149 | 7.1 | Maintenance requests **originate through the company app**, integrating with Odoo without duplicate entry | Must | Int | Helpdesk | App integration (D3) | S3 | — |
| BR-150 | 7.1 | Direct Odoo entry **only during a documented outage**, flagged as fallback, recording original channel, time and evidence, reconciled on restore | Must | Cus | Helpdesk | Outage path | S3 | — |
| BR-151 | 7.1 | Ten stages: New, Reviewed, Assigned, Visit Scheduled, Quote Pending, Approval Pending, In Progress, Tenant Confirmation, Completed, Closed; plus On Hold and Cancelled | Must | Cfg | Helpdesk | Stage set | S3 | — |
| BR-152 | 7.1 | Integration passes customer, building, unit, category, description, priority, access details, preferred visit time, attachments, consent and contact; returns ticket reference and status; **prevents duplicate submissions**; retains timestamps and logs; retry and exception handling | Must | Int | Helpdesk | Idempotent on request ID (D3) | S3 | — |
| BR-153 | 7.1 | Priority and SLA consider emergency, health/safety, habitability, contractual responsibility and business impact | Must | Cfg | Helpdesk | SLA policies | S3 | — |
| BR-154 | 7.1 | Classification as major repair, minor/routine, tenant-caused damage, warranty, insurance or approved category; **unclear cases routed for management approval before responsibility or financial treatment is assigned**, except urgent safety work under the emergency process | Must | Cus | Helpdesk | Triage + approval (O1) | S3 | — |
| BR-155 | 7.1 | Quotes above configurable thresholds approved before purchase or work order release | Must | Cfg | purchase | Approval threshold | S3 | — |
| BR-156 | 7.1 | Track purchase requests, orders, supplier bills, petty cash, issued materials, commitments and actual spend against the building limit; show remaining balance and projected month-end; warn at threshold; **CEO approval before exceeding** | Must | Cus | limit model | Commitment tracking | S3 | — |
| BR-157 | 7.1 | **Costs may not shift between buildings without CEO approval**, reason and audit history | Must | Cus | limit model | Reallocation block | S3 | — |
| BR-158 | 7.1 | Completion requires work notes, time, parts, supplier cost, photos where relevant, tenant confirmation or documented exception, and financial disposition | Must | Cfg | Helpdesk | Completion gate | S3 | — |
| BR-159 | 7.2 | Full procurement cycle: request, approval, RFQ, quotation comparison, PO, receipt or service confirmation, bill, payment, return, supplier performance | Must | Std | `purchase` | Standard Odoo | S3 | — |
| BR-160 | 7.2 | Maintenance materials, tools, keys, access cards and consumables tracked on receipt, movement, issue, return, adjustment and scrap, each linked to building, unit or job | Must | Cfg | `stock` | Inventory | S3 | — |
| BR-161 | 7.3 | Structured folders and access rights by company, owner, building, unit, tenant, lease, supplier, employee and ticket; documents show version, status, owner, expiry, signature trail and source links | Must | Cfg | Documents | Folder structure | S3 | — |

---

## §8 Reporting and controls

| ID | § | Requirement | Pri | Class | Module / model | Approach | Phase | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **BR-003** | 11.1, 6.3 | **Report profitability and cash exposure by building** *(BRD's own ID)* | Must | Rep | analytic + dashboard | Analytic accounting and management dashboard | S2 | Partial |
| BR-162 | 8.1 | Leadership dashboard covering occupancy, unit states, rent (contracted/invoiced/collected/overdue/forecast), listings, brokerage pipeline and commission, vacancy loss, head-lease commitments, margin and coverage, expiries at 30/60/90, cheques due, bounce rate, maintenance and SLA, facility headroom, banking status, unreconciled items and daily-rental exceptions | Must | Rep | dashboard | Partially built | S2–S4 | Partial |
| BR-163 | 8.1 | **Operating-model filter; never aggregate head-lease revenue, owner-management gross tenant rent and brokerage transaction value as company revenue** | Must | Rep | dashboard | Separate measures | S2 | — |
| BR-164 | 8.1 | Owner-management views show gross rent administered, cheques in custody, due for deposit, deposited, cleared, bounced or replaced, amounts paid directly to landlords, fee revenue, recoverable costs and owner balances — separately | Must | Rep | dashboard | Owner view | S2 | — |
| BR-165 | 8.1.1 | Reports show current result, previous period, budget or forecast, trend, variance, responsible person, required action and supporting detail — **not just transaction lists** | Must | Rep | reports | Comparative design | S3 | — |
| BR-166 | 8.1.1 | Filtering by company, operating model, building, unit, owner, tenant, period, status and responsible user | Must | Rep | reports | Standard filters | S3 | — |
| BR-167 | 8.1.1, 8.3.6 | **Actuals, commitments, forecasts and assumptions stored as distinct data types; forecast lines may not post to the ledger** | Must | Cus | reports | Type separation | S3 | — |
| BR-168 | 8.1.1 | **Dashboard totals must agree with approved source transactions** | Must | Rep | dashboard | Drill-through to source | S2 | Partial |
| BR-169 | 8.3.6 | Each approved workbook stored in Documents, linked to its report definition, process owner, version, effective date and approval status | Should | Cfg | Documents | Template governance | S3 | — |
| BR-170 | 8.3.6 | Imports reject invalid dates, duplicate document or cheque numbers, unknown building/unit codes, unbalanced totals and invalid status values | Must | Cus | import staging | Validation | S2 | — |
| BR-171 | 8.3.6 | Source file, upload batch, row number, import user, upload time, validation result, posted record and reversal reference preserved | Must | Cus | import staging | Staging model | S2 | — |
| BR-172 | 8.3.6 | Reports containing tenant, employee, bank, identity or cheque data use role-based access, masked exports, retention rules and an **export audit log** | Must | Cus | reports | Export control (OD-06) | S3 | — |
| BR-173 | 8.3.7 | Reproduce an approved month from each supplied template and reconcile to the source workbook and general ledger | Must | Rep | reports | Acceptance evidence | S3 | — |
| BR-174 | 8.3.7 | Prove duplicate instruments, overlapping recognition periods, invalid references and unapproved overrides are blocked or reported | Must | Rep | reports | Acceptance evidence | S3 | — |
| BR-175 | 8.3.7 | Reconcile opening + additions − recognised/paid/refunded to closing for prepayments, deposits, facilities, receivables, payables and deferred income | Must | Rep | reports | Roll-forward | S4 | — |
| BR-176 | 8.4 | Least-privilege access; **no self-approval** of lease changes, supplier changes, bank details, refunds, write-offs or payments above limit | Must | Cfg | `res.groups` | SoD (**blocked on OD-06**) | S2 | — |
| BR-177 | 8.4 | Identity and bank documents restricted | Must | Cus | documents | Field security | S2 | — |
| BR-178 | 8.4 | Log creation, change, approval, rejection, cancellation, posting, reconciliation **and deletion attempts** | Must | Cus | audit | Audit trail | S2 | Partial |
| BR-179 | 8.5 | Confirm which integrations are required; for each, define owner, data mapping, security, error handling, retry, monitoring and reconciliation | Must | — | — | Decision gate (OD-07) | S3 | — |
| BR-180 | 8.6 | Clean import files for owners, tenants, suppliers, buildings, units, active head leases, active tenant leases, deposits, unpaid invoices and bills, balances, cheques, tickets, documents, opening bank and ledger balances and reference data | Must | Mig | migration | Templates per object | S2 | — |
| BR-181 | 8.6 | Extract, clean, de-duplicate, map, test load, reconcile totals, obtain business approval, final load, archive. **No source record or amount omitted without a documented reason** | Must | Mig | migration | Controlled sequence (OD-09) | S2 | — |
| BR-182 | 8.6 | **Head leases, management contracts and banking facilities entered by hand from signed agreements — no import may originate them** | Must | Mig | migration | Importer exists for head leases from a transcribed CSV only | S2 | Partial |
| BR-183 | 8.7 | Browser-based, mobile-responsive access | Should | Std | — | Standard Odoo | S2 | Built |
| BR-184 | 8.7 | Multi-company data isolation, encryption, strong authentication, access review and audit export | Must | Cfg | security | Record rules + review | S2 | Partial |
| BR-185 | 8.7 | Configurable numbering, currencies, date/time zone, language, notifications, approval thresholds and retention | Must | Cfg | — | Configuration | S2 | Partial |
| BR-186 | 8.7 | Performance targets, backup, recovery, retention, availability, monitoring, incident support and environment strategy documented | Must | — | — | Decision gate (OD-10) | S2 | — |

---

## Coverage and what it means

| Status | Count |
| --- | --- |
| Built | 9 |
| Partial | 33 |
| Not started | 144 |

186 requirements, BR-001 to BR-186 with no gaps or duplicates, of which **3
carry the BRD's own IDs** (BR-001 to BR-003). Counts are generated from the
tables above, not estimated — `tools/check_requirement_matrix.py` re-derives
them and fails if they drift.

The classification spread matters more than the count. `Cus` dominates because
the BRD's controls are mostly *blocks* — activation gates, approval gates,
overlap prevention, immutable baselines, client-money segregation. Standard Odoo
supplies the records; it does not supply the refusals, and the refusals are what
the acceptance scenarios in §9.2 test.

**Blocked on client decisions:** BR-023, BR-039, BR-072, BR-079, BR-172 and
BR-176 all wait on **OD-06** (approval matrix and segregation-of-duties rules).
BR-176 is the broadest — least privilege and no self-approval cannot be
configured from principles alone.

**Outside our control:** BR-119 (bank certification), BR-120 (no open DEWA
third-party interface), BR-152 (the company app's API).

**Judgement, not configuration:** BR-134 (VAT apportionment basis), BR-135
(adviser approval), BR-136 to BR-142 (every IFRS 16 input, and BR-142 sublease
classification in particular).
