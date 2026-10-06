# Decisions required

Open questions that block delivery, or that would be answered wrongly if a
developer guessed. Each needs a named owner from the client side. Nothing here
is a technical unknown — these are business, legal, tax and audit judgements.

Status: **Open**, **Answered** (with the answer and who gave it), or **Closed —
built**.

---

## B. Blocking the Stage 1 blueprint

### B1. The BRD itself is not in this repository — Open

The build brief names the client's BRD as the contract and refers to §2.3, §3.1,
§3.2, §4.1, §4.1.2, §4.2, §4.2.4, §4.3.1, §4.4, §5.1.3, §5.1.4, §6.2, §6.2.1,
§6.2.2, §6.3, §6.3.2, §6.4.1, §6.5, §7.1, §8.3.4, §8.4, §8.6, §9.1, §9.2 and
§11. No copy of that document has been supplied, and none exists in the repo or
in any file shared with this session.

Five of the seven Stage 1 deliverables are derivations of it and cannot be
written without it:

| Deliverable | What it needs from the BRD |
| --- | --- |
| `requirement_response_matrix.md` | every requirement and its ID (§9.1) |
| `data_dictionary.md` | the approved field list (§8.3.4) |
| `status_matrix.md` | the status models in §3.2 |
| `approval_matrix.md`, `role_access_matrix.md` | the twenty roles in §2.3, SoD rules in §8.4 |
| `report_catalogue.md` | the report list in §8 |

Writing these from inference would invent requirement IDs for a contractually
required traceability matrix. **Needed: the BRD, with its section numbering
intact.**

### B2. Which document is the contract baseline — Open

If more than one BRD version exists, name the one that governs, with its version
and date. The requirement IDs in the response matrix must cite it.

---

## C. Client-money and regulatory treatment

### C1. Owner-management client money — Open

Landlord-name cheques held in custody must never touch company revenue or
company cash. Needed before build:

- the control account to use, and whether a separate bank account is held per
  landlord or one pooled account with per-landlord sub-ledger
- who is authorised to receive, deposit, refund and disburse
- the evidence required at deposit, and the retention period
- whether RERA or any other regulator imposes a prescribed account structure

**Owner:** Finance / client's auditor. Do not assume.

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

### O2. Non-standard cheque schedules — Open

1, 2, 3, 4, 6 and 12 cheques are supported. A schedule outside that set is to be
blocked pending Leasing Director or Manager approval — confirm which role, and
whether the approval is per lease or a standing exception.

### O3. Mandate stage gate for brokerage — Open

Which stage a signed mandate is mandatory by, and who may authorise a documented
exception.

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

### N1. Second company's legal name — Open

The build brief gives **Sinclair Real Estate Brokers LLC**. The user guide
produced in September gives **Sinclair Real Estate**. The repository names
neither — only New Sinclair Property Management LLC appears in code.

Needed: the exact registered legal name, for the company record, tax
registration and every document template. Confirm against the trade licence
rather than against either document.

### N2. Sample data must not reach production templates

Tenant names, unit numbers, salaries and dates from the source workbooks must
appear in no production template, default or export. The sample portfolio loader
is for demonstration databases only.

**Note:** as of 16 September the production database was displaying sample
portfolio figures (6 buildings, 100 units, AED 7,622,400 contracted rent).
Confirm whether that was deliberate and whether it has been cleared.
