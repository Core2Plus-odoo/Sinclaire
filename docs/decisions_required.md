# Decisions required

Open questions that block delivery, or that would be answered wrongly if a
developer guessed. Each needs a named owner from the client side. Nothing here
is a technical unknown — these are business, legal, tax and audit judgements.

Status: **Open**, **Answered** (with the answer and who gave it), or **Closed —
built**.

---

## B. Blocking the Stage 1 blueprint

### B1. The BRD — Answered (received 6 October 2026)

`NSPM_requirements.docx`, "Business Requirements Document and User Guide —
Odoo Property Leasing, Management and Brokerage System". 12,700 words, 28
tables, sections 1–11. Stage 1 is unblocked and underway.

Two things it settles that the build brief had differently, and the BRD wins:

- The permitted cheque schedules are **1, 2, 3, 4, 6 and 12** (§9.2), and a
  non-standard schedule is blocked "until approved by the Leasing Director or
  Leasing Manager" — **both** roles, not one. See O2.
- The second entity is **Sinclair Real Estate Brokers LLC** (§11 OD-01). See N1.

### B2. Which document is the contract baseline — Answered

`NSPM_requirements.docx` as received 6 October 2026, sections 1–11. Requirement
IDs follow the §11.1 template: **BR-NNN**, seeded there with BR-001..BR-003.

## C. Client-money and regulatory treatment

### C1. Owner-management client money — Partly answered (OD-02)

**Confirmed by the BRD:** both head-lease and management-only arrangements
exist. Where tenant cheques are in the landlord's name, New Sinclair collects
them and deposits each into **the landlord's bank account on the applicable
rental due date**. The system records landlord/payee, linked tenant obligation,
due date, custody, deposit date, deposit evidence, and cleared or bounced
status. These cheques and their proceeds are owner funds and are **never** New
Sinclair rental revenue or company cash. Owner statements are issued half-yearly
or yearly per the approved landlord agreement.

**Still open, per OD-02:** the landlord bank-account record, deposit
authorisation, and exception handling for held or replaced cheques. Also still
needed and not in the BRD: the control account to use, and whether RERA imposes
a prescribed account structure.

**Owner:** Finance / client's auditor.

### C2. Brokerage client funds — Open

Deposits, reservation amounts and sale proceeds may sit in a company bank
account but must be separately identified, restricted and never recognised as
revenue. Same questions as C1, plus whether escrow rules apply to off-plan
proceeds.

**Owner:** Finance, with legal confirmation.

---

## T. Tax

### T1. Input VAT apportionment method for mixed portfolios — Open

Residential rent is exempt, commercial is standard-rated, so input VAT on a
mixed building is recoverable only in part. The FTA permits more than one
apportionment basis and the choice is the taxpayer's, subject to approval.

Needed: the basis (floor area, rental value, transaction count, or an approved
special method), whether a special method has been agreed with the FTA, and the
annual wash-up treatment. The mechanism will be built parameterised; the method
is not ours to choose.

**Owner:** Tax advisor.

### T2. Transfer pricing between the two companies — Open

Service fees, commissions and cost recharges between New Sinclair Property
Management LLC and Sinclair Real Estate Brokers LLC need an arm's-length basis
and supporting documentation under UAE corporate tax.

**Owner:** Tax advisor.

---

## A. IFRS 16 — every item here needs Finance and auditor sign-off

Statutory books apply IFRS 16; management accounts exclude it. The mechanism can
be built now; none of the following may be chosen by a developer, and a
confidently wrong schedule is worse than an unfinished one.

| # | Question | Owner |
| --- | --- | --- |
| A1 | Lease population — which contracts are in scope | Finance + auditor |
| A2 | Discount rate: incremental borrowing rate by term and currency, and its source | Finance + auditor |
| A3 | Enforceable term, and which renewal/termination options are reasonably certain | Finance |
| A4 | Exemptions taken: short-term, low-value, and the thresholds | Finance |
| A5 | Payment scope: which components are in the liability (fixed, in-substance fixed, variable) | Finance + auditor |
| A6 | Modification and remeasurement rules | Auditor |
| A7 | Transition method and date | Auditor |
| A8 | Chart-of-accounts mapping for ROU, liability, depreciation, finance cost | Finance |
| A9 | Cash-flow statement classification | Auditor |
| A10 | Disclosure set required | Auditor |

### A11. Sublease classification — Open, and specifically flagged

Sinclair head-leases buildings and sublets the units, which makes it an
**intermediate lessor**. Whether each sublease is a finance or operating lease
under IFRS 16 is a judgement with a material effect on the statutory position.
It is not a configuration value and will not be decided here.

**Owner:** Auditor.

---

## O. Operational policy

### O1. Maintenance responsibility where the contract is silent — Open

Major to landlord, minor and routine to Sinclair is the stated rule. The routing
for unclear cases needs a named approver and an escalation path.

### O2. Non-standard cheque schedules — Answered (§9.2)

1, 2, 3, 4, 6 and 12 are permitted. A non-standard schedule is blocked "until
approved by the **Leasing Director or Leasing Manager**" — either role may
approve. Built as of PR #10 for the schedule values themselves; the approval
gate needs the Pending Approval lease state, which does not yet exist.

Still open: whether the approval is per lease or a standing exception.

### O3. Mandate stage gate for brokerage — Open (§3.2)

The BRD confirms this is a **configurable stage gate, not one rule**: the stage
by which a completed mandate is required varies by transaction type, represented
party and deal circumstances, and progression past it is blocked unless an
authorised documented exception is approved.

Needed: the actual configuration — which stage per transaction type and
represented party — and who may authorise the exception.

### O4. Ejari submission — Open

No approved interface is available. Confirm that controlled manual submission
with evidence capture is acceptable for go-live.

### O5. Landlord DEWA accounts — Open

Around 120 DEWA accounts are in the landlords' names. How bills reach Sinclair
is unresolved, and it determines whether mailbox ingestion is viable at all.

**Owner:** Client operations.

---

## D. External dependencies outside our control

### D1. Banking host-to-host — Open

The bank's file specification, certification and test cycle are the bank's.
Until certification, the delivered path is WPS SIF generation plus portal upload
and statement import. **Needed: the bank's specification pack and a named
contact.**

### D2. DEWA — no third-party interface exists

The official DEWA interface is restricted to banks and collection agencies under
partnership agreement. We will not build against an API we cannot obtain. Bill
ingestion by monitored mailbox with AI-assisted extraction and a staged human
approval before posting is the delivered path. No extracted figure posts
unreviewed.

**Status: Closed — approach fixed.** Open only insofar as O5 is unresolved.

### D3. Company maintenance app — Open

Whether the provider exposes an API, and its authentication and request-ID
semantics. If there is no API, the outage-fallback path is built and the
dependency logged; the integration is not simulated.

---

## N. Naming and data

### N1. Second company's legal name — Answered (OD-01)

**Sinclair Real Estate Brokers LLC.** The build brief was right and the
September user guide ("Sinclair Real Estate") is wrong; the guide needs
correcting before it circulates.

Still open, per OD-01: legal registration and tax details for each entity,
intercompany agreements and pricing/allocation rules, opening due-to/due-from
balances, settlement/netting process, consolidation and elimination
requirement, and whether and when Seventh Heaven is activated. Seventh Heaven
stays **inactive** unless separately approved.

### N2. Sample data must not reach production templates

Tenant names, unit numbers, salaries and dates from the source workbooks must
appear in no production template, default or export. The sample portfolio loader
is for demonstration databases only.

**Note:** as of 16 September the production database was displaying sample
portfolio figures (6 buildings, 100 units, AED 7,622,400 contracted rent).
Confirm whether that was deliberate and whether it has been cleared.

---

## OD. BRD §11 items not covered above

The BRD's own open-decision table. OD-01 is answered at N1, OD-02 at C1, OD-03
partly at O2. The rest are carried here so §11 maps cleanly onto this register.

### OD-03. Product eligibility and commercial rules — Open

Precise yearly, monthly and daily eligibility, approval limits, pricing, deposit,
refund, cancellation and notice rules. Daily rentals are **exceptional** and need
explicit approval within expressly authorised properties (§1.1, §2.1).

Blocks: product configuration, the daily-rental exception workflow, and
acceptance scenario §9.2 "create a daily stay only through exception approval".

### OD-04. Portfolio counts and emirate priority — Partly answered

**Confirmed:** residential is primary; commercial and mixed-use are included;
Dubai is the current geography with later UAE expansion. **Still needed:**
current counts by property and use type, furnished inventory, and which emirates
follow Dubai.

### OD-05. Payment methods and custody controls — Open

Confirm PDC, bank transfer, card, cash, online payment and direct debit, and the
custody controls for each. §1.3 says all methods in the document apply at go-live
"subject to the applicable transaction, user access and approval controls" — the
controls themselves are not specified.

Blocks: journal design, reconciliation and audit requirements.

### OD-06. Approval matrix and segregation-of-duties rules — Open, and blocking

**This blocks two Stage 1 deliverables**: `approval_matrix.md` and
`role_access_matrix.md` cannot be completed without it. BRD §8.4 gives
principles only — least privilege, no self-approval of lease changes, supplier
changes, bank details, refunds, write-offs or payments above limit, restricted
identity and bank documents, full action logging. It does not give the limits,
the approvers, or the role-to-permission mapping.

The twenty roles are fixed by §2.3. What is missing is who approves what, and at
what value.

Every *(proposed)* role in `status_matrix.md` is waiting on this.

### OD-07. Required integrations and source systems — Open

§8.5 lists *possible* integrations: property portals, website forms, WhatsApp,
email, e-signature, payment gateway, UAE tenancy registration, bank statements,
Excel reporting, existing accounting or document systems. "The business must
confirm which integrations are required." For each approved one: owner, data
mapping, security, error handling, retry, monitoring, reconciliation.

Note §2.2 holds government portal submission, biometric devices and external
listing portals **out of scope** until feasibility and commercial terms are
agreed.

### OD-08. Templates, numbering, notification wording, retention — Open

Needed for contracting, communication and compliance. §8.3 catalogues the
templates required; the content, numbering rules and retention periods are the
client's.

### OD-09. Opening data volumes, quality, cutover date, retention — Open

Blocks `migration_plan.md` beyond its structure. §8.6 fixes the method —
extract, clean, de-duplicate, map, test load, reconcile, approve, final load,
archive, with no record or amount omitted without a documented reason — but not
the volumes or the date.

### OD-10. Service levels, support hours, backup/recovery, environments — Open

For the implementation and support agreement.

---

## Commercial columns are not a developer's to fill

BRD §9.1 requires the requirement-response matrix to carry **estimate, one-time
cost, recurring cost and optional cost** per requirement, so that the client can
evaluate like-for-like on functional alignment, completeness, risk, timeline,
support and total cost of ownership.

Those columns will be left empty in `requirement_response_matrix.md` with the
functional classification complete. Effort and price are C2P commercial
decisions, not inferences from a specification.
