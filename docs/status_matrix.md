# Status transition matrix

Source: BRD §3.2, which names the six controlled status models and then says
"the developer shall define allowed transitions, responsible roles, timestamps,
and reversal rights." That definition is this document.

Rules that hold across every model:

- **No status is overwritten without history.** Every transition writes who, when,
  from, to, and reason where one is required (BRD §3.2, §8.4).
- A transition not listed here is **blocked**. The absence of a row is a rule.
- Backward transitions are **reversals**, never ordinary edits: each needs the
  stated role and a reason, and the original row stays in the history.
- Roles are from the twenty in BRD §2.3. Where a role is marked *(proposed)*, the
  approval matrix needed to confirm it is **OD-06**, still outstanding — these are
  this document's recommendation, not an agreed rule.
- The CEO combines Business Owner and General Manager and is not split into
  separate roles (BRD §2.3).

Implementation status is shown against each model so the gap is visible rather
than discovered during build.

---

## 1. Unit — `c2p.unit`

BRD: Draft → Available → Under Marketing → Viewing/On Hold → Reserved →
Contracted → Occupied → Under Notice → Vacant → Under Maintenance/Blocked.

| From | To | Role | Trigger / condition | Reversal |
| --- | --- | --- | --- | --- |
| — | Draft | Property Administrator | Unit created | n/a |
| Draft | Available | Property Administrator | Mandatory master data complete; mandatory compliance cover in date | Available → Draft, Property Administrator, reason |
| Available | Under Marketing | Leasing Agent | Listed for letting | free both ways |
| Under Marketing | Viewing/On Hold | Leasing Agent | Viewing booked, or held for a named prospect with an expiry | free both ways |
| Viewing/On Hold | Reserved | Reservations Officer | Reservation approved and reservation amount received | Reserved → Available, Leasing Manager *(proposed)*, reason |
| Available / Under Marketing | Reserved | Reservations Officer | Direct reservation without viewing | as above |
| Reserved | Contracted | Leasing Agent | Lease reaches Signed | Contracted → Reserved, Leasing Manager *(proposed)*, reason |
| Contracted | Occupied | Property Administrator | Move-in inspection signed | Occupied → Contracted, Leasing Manager *(proposed)*, reason |
| Occupied | Under Notice | Property Administrator | Notice served or received | Under Notice → Occupied, Leasing Manager *(proposed)* — notice withdrawn |
| Under Notice | Vacant | Property Administrator | Move-out inspection signed, keys returned | Vacant → Under Notice, Property Administrator, reason |
| Occupied | Vacant | Leasing Manager *(proposed)* | Termination without notice period | reason mandatory |
| Vacant | Available | Property Administrator | Turnaround complete, compliance in date | free both ways |
| any | Under Maintenance/Blocked | Facilities Manager | Unit withdrawn from availability | returns to the state it left, Facilities Manager |

**Blocked by rule**

- Two units may not hold an active reservation or lease over the same period —
  BRD §1.1 "a unit must never have overlapping active reservations or leases",
  acceptance scenario §9.2.
- Draft → anything beyond Available is blocked.
- Available ← Occupied directly is blocked: a unit passes through Under Notice or
  Vacant so the move-out record exists.
- Activation is blocked where mandatory compliance cover has lapsed.

**Current implementation:** `c2p.unit` has four states — Vacant, Occupied, Under
Notice, Blocked. **Six are missing**: Draft, Available, Under Marketing,
Viewing/On Hold, Reserved, Contracted. Note that the BRD separates *Vacant*
(just handed back, not yet re-lettable) from *Available* (re-lettable); the
current model has only the one. Vacancy-loss reporting depends on that split.

---

## 2. Lease — `c2p.lease`

BRD: Draft → Pending Approval → Offered → Awaiting Signature → Signed →
Registration Pending → Active → Under Notice → Renewed/Expired/Terminated/Cancelled.

| From | To | Role | Trigger / condition | Reversal |
| --- | --- | --- | --- | --- |
| — | Draft | Leasing Agent | Lease created | n/a |
| Draft | Pending Approval | Leasing Agent | Submitted; required where price is off approved pricing, or the cheque schedule is non-standard | Pending Approval → Draft, Leasing Agent |
| Pending Approval | Offered | Leasing Director or Leasing Manager | Approved (BRD §9.2 names both for non-standard schedules) | Offered → Draft, Leasing Manager *(proposed)*, reason |
| Draft | Offered | Leasing Agent | Approved pricing, standard schedule — no approval needed | as above |
| Offered | Awaiting Signature | Leasing Agent | Tenant accepts; contract pack generated | free both ways, reason |
| Awaiting Signature | Signed | Leasing Agent | All parties signed; signed document immutable from here | **No reversal.** Correction is an amendment version (BRD §5.1.3) |
| Signed | Registration Pending | Property Administrator | Ejari submission raised | free both ways |
| Registration Pending | Active | Property Administrator | Registration confirmed **and** payment instruments registered **and** mandatory documents verified | Active → Registration Pending, Leasing Manager *(proposed)*, reason |
| Active | Under Notice | Property Administrator | Notice served or received | Under Notice → Active, Leasing Manager *(proposed)* — notice withdrawn |
| Active / Under Notice | Renewed | Leasing Agent | Successor lease activated; links to it | **No reversal** once the successor is Active |
| Active / Under Notice | Expired | *system* | Term end reached with no renewal | Expired → Active, Leasing Manager *(proposed)*, reason |
| Active / Under Notice | Terminated | Leasing Manager *(proposed)* | Early termination; final settlement raised | reason mandatory, CEO *(proposed)* |
| Draft / Pending Approval / Offered / Awaiting Signature | Cancelled | Leasing Agent | Abandoned before signature | Cancelled → Draft, Leasing Manager *(proposed)* |

**Blocked by rule**

- Activation without mandatory documents verified and payment instruments
  registered, **unless** a named Leasing Manager or CEO approval is recorded with
  the outstanding items, conditions, deadline and follow-up (BRD §5.1).
- Activation of a third-party cheque lease without a signed undertaking and
  management approval (BRD §4.2.3, acceptance §9.2).
- A cheque schedule outside 1, 2, 3, 4, 6, 12 until approved by the Leasing
  Director or Leasing Manager (BRD §9.2).
- Any price override outside approved pricing without approval (BRD §9.2).
- Signed → anything backwards. Signed documents are immutable.

**Current implementation:** five states — Draft, Active, Notice Given, Expired,
Terminated. **Seven are missing**: Pending Approval, Offered, Awaiting Signature,
Signed, Registration Pending, Renewed, Cancelled. The approval gate, the
signature gate and the Ejari registration gate all live in the missing states, so
none of the §9.2 blocking scenarios can currently be demonstrated.

---

## 3. Payment instrument — `account.payment`

BRD: Expected → In Hand → Deposited/Presented → Cleared or Bounced →
Replaced/Cancelled. "No status may be overwritten without history."

| From | To | Role | Trigger / condition | Reversal |
| --- | --- | --- | --- | --- |
| — | Expected | Leasing Agent | Schedule generated from the lease, instrument not yet received | n/a |
| Expected | In Hand | Accounts Receivable | Physical receipt, custody recorded | In Hand → Expected, Accounts Receivable, reason |
| In Hand | Deposited/Presented | Treasury/Banking User | Banked or presented | Deposited → In Hand, Treasury *(proposed)*, reason (recall) |
| Deposited/Presented | Cleared | Treasury/Banking User | Clearing confirmed, usually by statement | **No reversal.** A reversal after clearing is a new accounting event |
| Deposited/Presented | Bounced | Treasury/Banking User | Return advice; reopens the receivable, posts bank charges, raises follow-up | — |
| Bounced | Replaced | Credit Controller | Replacement instrument received and linked both ways | — |
| Expected / In Hand | Cancelled | Credit Controller | Instrument withdrawn | reason mandatory |

**Blocked by rule**

- Undated and held cheques are **never** counted as cleared cash, in any report.
- A landlord-name cheque under Owner Management never reaches company revenue or
  company cash at any status — it posts to the custody control account only
  (BRD §1.1, OD-02, acceptance §9.2).
- Status may not be set directly; each move is its own action with its own
  history row.

**Current implementation:** four states — In Hand, Deposited, Cleared, Bounced.
**Three are missing**: Expected, Replaced, Cancelled. *Expected* is what makes a
forward cash forecast possible (BRD §9.2 "generate and monitor landlord
commitments and a forward cash forecast"); *Replaced* is required by the bounce
acceptance scenario.

---

## 4. Property listing — `c2p.property.listing` (Stage 3, not yet built)

BRD: Draft → Mandate Pending → Approval Pending → Active → Offer in Progress →
Under Transaction → Sold/Leased → Withdrawn/Expired/Cancelled.

| From | To | Role | Trigger / condition |
| --- | --- | --- | --- |
| — | Draft | Property Broker | Listing created |
| Draft | Mandate Pending | Property Broker | Awaiting signed mandate |
| Mandate Pending | Approval Pending | Property Broker | Mandate received |
| Approval Pending | Active | Sales/Brokerage Manager | Listing approved for market |
| Active | Offer in Progress | Property Broker | Offer received |
| Offer in Progress | Under Transaction | Property Broker | Offer accepted; brokerage transaction opened |
| Under Transaction | Sold/Leased | Sales/Brokerage Manager | Transaction completed |
| any | Withdrawn / Expired / Cancelled | Sales/Brokerage Manager | Reason mandatory, history preserved |

**Blocked by rule:** progression past the stage that requires a completed mandate
is blocked unless an authorised, documented exception is approved. **Which stage
that is, is configurable by transaction type, represented party and deal
circumstances** (BRD §3.2) — it is a stage gate, not one fixed rule. The
configuration values are **OD-03/OD-06 territory and not yet supplied**.

**Current implementation:** model does not exist.

---

## 5. Buyer or tenant requirement — `c2p.property.requirement` (Stage 3)

BRD: New → Qualified → Matching → Viewing → Offer/Negotiation → Converted →
Lost/Withdrawn/Expired.

| From | To | Role |
| --- | --- | --- |
| — | New | Property Broker / Leasing Agent |
| New | Qualified | Property Broker | 
| Qualified | Matching | Property Broker |
| Matching | Viewing | Property Broker |
| Viewing | Offer/Negotiation | Property Broker |
| Offer/Negotiation | Converted | Sales/Brokerage Manager |
| any | Lost / Withdrawn / Expired | Property Broker, reason mandatory |

**Current implementation:** model does not exist.

---

## 6. Brokerage transaction — `c2p.brokerage.transaction` (Stage 3)

BRD: Draft → Qualification/Due Diligence → Viewing/Marketing → Offer →
Negotiation → Reserved or Memorandum Pending → Contracted → Completion Pending →
Completed → Commission Billed → Commission Collected → Closed. May instead move
to Lost, Withdrawn, Cancelled or Reversed with an approved reason and preserved
history.

| From | To | Role | Note |
| --- | --- | --- | --- |
| — | Draft | Property Broker | |
| Draft | Qualification/Due Diligence | Property Broker | |
| Qualification/Due Diligence | Viewing/Marketing | Property Broker | |
| Viewing/Marketing | Offer | Property Broker | |
| Offer | Negotiation | Property Broker | |
| Negotiation | Reserved or Memorandum Pending | Sales/Brokerage Manager | |
| Reserved or Memorandum Pending | Contracted | Sales/Brokerage Manager | **Commission is earned here** — on signature with supporting evidence complete, not on collection (BRD §6.3.2) |
| Contracted | Completion Pending | Sales/Brokerage Manager | |
| Completion Pending | Completed | Sales/Brokerage Manager | |
| Completed | Commission Billed | Accounts Receivable | |
| Commission Billed | Commission Collected | Accounts Receivable | |
| Commission Collected | Closed | Sales/Brokerage Manager | Splits settled or provided |
| any | Lost / Withdrawn / Cancelled / Reversed | Sales/Brokerage Manager | Approved reason, history preserved |

**Blocked by rule**

- No commission share becomes payable until its own approved condition is met;
  splits must reconcile to the distributable amount (BRD §6.3.2).
- Client funds — deposits, reservation amounts, sale proceeds — are separately
  identified by client and transaction, restricted, and **never recognised as
  revenue** at any status.

**Current implementation:** model does not exist.

---

## Summary of gaps

| Model | BRD states | Built | Missing |
| --- | --- | --- | --- |
| Unit | 10 | 4 | 6 |
| Lease | 12 | 5 | 7 |
| Payment instrument | 7 | 4 | 3 |
| Property listing | 8 | 0 | 8 — model not created |
| Buyer/tenant requirement | 7 | 0 | 7 — model not created |
| Brokerage transaction | 15 | 0 | 15 — model not created |

Every *(proposed)* role in this document is a recommendation pending **OD-06**,
which asks the client for the approval matrix and segregation-of-duties rules.
Until OD-06 is answered, the transitions can be built but the role assignments
are not agreed.
