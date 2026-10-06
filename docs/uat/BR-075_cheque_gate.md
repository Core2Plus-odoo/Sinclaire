# UAT — BR-075: activation with cheques outstanding

**Reference** C2P-NSPM-QA-001 · **Confidential**
**Requirement** BR-075 (BRD §5.1) · **Modules** `c2p_property_lease` 19.0.1.6.0, `c2p_ceo_command_center` 19.0.1.2.2
**Environment** Odoo.sh **staging**, restored from a copy of production — not production
**Prepared by** C2P Consultants (Core2Plus)

| | Name | Role | Signature | Date |
| --- | --- | --- | --- | --- |
| Prepared | | | | |
| Executed | | | | |
| Approved | | | | |

---

## Why this script exists

This is the first change in the build that **takes away something the leasing
team can do today**. Until now a tenancy could be activated whenever the
paperwork was ready and the cheques could follow. BRD §5.1 does not allow that:
activation with cheques outstanding is permitted only under a case-by-case
exception approved by the Leasing Manager or CEO.

So the question UAT has to answer is not only "does the gate work". It is
**"is this how the business actually wants to work?"** If the leasing team
routinely activates first and collects cheques afterwards, the exception flow
will be used daily rather than exceptionally, and that is worth knowing before
it reaches production rather than after.

Record that judgement in section 4 even if every test passes.

---

## 1. Preconditions

| # | Needed | Why |
| --- | --- | --- |
| P1 | Staging database restored from a **copy of production** | The gate reads the live cheque register; an empty database proves nothing about it |
| P2 | Two logins: one in **Property / User**, one in **Property / Manager** | The self-approval and role rules cannot be tested from one account |
| P3 | A bank journal with an inbound payment method | Needed to register cheques at all |
| P4 | One building with at least four empty units | Each scenario needs its own unit |
| P5 | Note the Command Center figures before starting: occupancy %, contracted rent, vacancy loss | Section 3 checks they have not moved |

Record the two logins used:

- Property **User**: ............................................
- Property **Manager**: ............................................

---

## 2. Test cases

Mark each **Pass** or **Fail**. A Fail needs the actual behaviour written down —
"did not work" is not a defect report. Severity: S1 blocker, S2 major,
S3 minor, S4 trivial.

### 2.1 The refusal

| ID | Steps | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| T01 | As **User**, create a lease on an empty unit: tenant, unit, 1 Jan–31 Dec, annual rent 120,000, 4 cheques. Register **all four** cheques of 30,000 via *Register PDCs*. Press **Activate**. | Lease becomes Active. Unit becomes Occupied. No exception record anywhere. | | |
| T02 | As **User**, create the same lease on another unit. Register **no** cheques. Press **Activate**. | Refused. The message names **4 cheque(s)** and **120,000.00** uncovered, and tells you to register the cheques or request an exception. Lease stays Draft; unit does **not** become Occupied. | | |
| T03 | On the T02 lease, register **two** cheques of 30,000. Press **Activate**. | Still refused, now naming **2 cheque(s)** and **60,000.00**. | | |
| T04 | On a fresh lease (120,000, 4 cheques), register **four** cheques of **15,000** each. Press **Activate**. | Refused. Four cheques is the right *count* but only 60,000 of cover. | | |
| T05 | On a fresh lease (120,000, 4 cheques), register **one** cheque of **120,000**. Press **Activate**. | Refused. The full amount in one instrument is not the agreed schedule. | | |
| T06 | On a fresh Draft lease (120,000, 4 cheques), register all four cheques of 30,000. Open one of them and press **Bounce**. Press **Activate**. | Refused, naming one cheque short. A bounced cheque is not a received one — the instrument exists and the money did not arrive. | | |
| T07 | On a cheque-less Draft lease, click **Active** directly on the status bar at the top of the form (do not use the Activate button). | Refused with the same kind of message. The control is on the transition, not only on the button. | | |

### 2.2 The exception

| ID | Steps | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| T08 | As **User**, on the T02 lease press **Request Cheque Exception**. Fill reason, conditions, a deadline two weeks out, and yourself as Responsible. Save. | Record created. **Shortfall when requested** shows the cheques and amount missing *at that moment*. The lease chatter logs the request. | | |
| T09 | Still as **User**, press **Approve** on that exception. | Refused — a Property User may not decide an exception. (The button may also be hidden for this role; either is a pass, note which.) | | |
| T10 | As **Manager**, raise your *own* exception on a different cheque-less lease, then press **Approve** on it. | Refused: you requested it, so you cannot approve it. BRD §8.4 forbids self-approval of lease changes. | | |
| T11 | As **Manager**, open the T08 exception (requested by the User) and press **Approve**. | State becomes Approved. **Decided By** and the approval date are filled. A to-do activity is raised **on the Responsible user**, dated the deadline. The lease chatter logs the approval and the conditions. | | |
| T12 | As **User**, go back to the T02 lease and press **Activate**. | Now allowed. Lease Active, unit Occupied. The lease chatter records that it was activated with cheques outstanding, naming the approver and the deadline. The exception shows an **activation date**. | | |
| T13 | On a different cheque-less lease, request an exception and have the **Manager** press **Reject**. Then press **Activate**. | Refused. A rejected exception is not permission. | | |
| T14 | On the lease from T13, try to raise a **second** exception while the first is still Requested. | Refused — one open exception per lease. | | |
| T15 | Try to raise an exception with a deadline **in the past**. | Refused. | | |
| T16 | On the T08 exception (approved, lease now active), register the two missing cheques so cover is complete. Then, as **Manager**, run *Settings → Technical → Scheduled Actions → "Leases: follow up cheque exceptions"* → **Run Manually**. | Exception becomes **Fulfilled**. The lease chatter says all cheques were received. | | |
| T17 | On another approved exception whose cheques are still missing, ask C2P to move its deadline into the past, then run the same scheduled action. | Exception becomes **Deadline Missed**. A to-do activity is raised on the Responsible user. The lease chatter records the miss. | | |
| T18 | Open *Property → Operations → Cheque Exceptions*. | The list shows every exception, defaulting to those awaiting a decision, with the shortfall, deadline, responsible user and what is still outstanding. Overdue rows are highlighted. | | |

### 2.3 Renewal

| ID | Steps | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| T19 | On an Active lease with a full cheque set, press **Renew**, set the new rent and dates, confirm. | A new lease is created for the new term, in **Draft**, with **no cheques carried over from the old one**. The outgoing lease stays **Active** — it is not closed until the successor starts. | | |
| T20 | On the renewal from T19, register the new term's cheques in full, then **Activate**. | Renewal becomes Active; the unit stays Occupied by the new tenancy. | | |
| T21 | Open the old lease and the renewal side by side and compare their **Cheques** tabs. | The two registers are separate. Neither shows the other's cheques. | | |

> T21 is a regression check on a defect this release fixed: renewing used to
> copy the tenant's cheque register onto the successor — payment records against
> cheques nobody wrote. If the two tabs share cheques, that is an **S1** and
> the release does not go.

### 2.4 Nothing else moved

| ID | Steps | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| T22 | Open three leases that were already Active before the upgrade. Edit something harmless on each (Ejari number, DEWA number) and save. | Saves normally. Existing tenancies are not retrospectively blocked, whatever their cheque position. | | |
| T23 | Open the **CEO Command Center** and compare with the figures noted in P5. | Occupancy %, contracted rent, vacancy loss and the cheque buckets are **unchanged**. | | |
| T24 | Give notice on an Active lease, then terminate it through the wizard. | Works as before. The unit returns to Vacant. | | |
| T25 | Open *Units* and check the state column. | States read Available / Occupied / Under Notice / Vacant etc. as before the upgrade — no unit has changed state because of this release. | | |

---

## 3. Migration check

This release carries no migration script of its own, but it is the first upgrade
**after** the 19.0.1.3.0 `Vacant → Available` split ran on production on
2026-10-06.

| ID | Steps | Expected | Result |
| --- | --- | --- | --- |
| T26 | Read the staging upgrade log for lines beginning `c2p_property_lease:`. | No migration runs — the database already records 19.0.1.3.0 as applied. Modules load with no errors. | |
| T27 | Count units per state and compare with production. | Identical. | |

---

## 4. The business judgement

To be answered by the business owner, not by C2P, and answered even if every
test above passes.

1. **Today, does the leasing team ever activate a tenancy before all cheques are
   in hand?** If yes, roughly how often, and in what situations?

   ..........................................................................

2. **Is the Leasing Manager the right approver?** BR-075 names the Leasing
   Manager or the CEO. The build currently requires *Property / Manager*
   because the role matrix is still open (decision **OD-06**). Who should hold
   this in the live system?

   ..........................................................................

3. **Is one open exception per lease right**, or does a tenancy sometimes need
   its shortfall revisited more than once before it is cleared?

   ..........................................................................

4. **Is a date enough for the deadline**, or does the follow-up need to escalate
   to someone other than the responsible user when it is missed?

   ..........................................................................

---

## 5. Outcome

| | |
| --- | --- |
| Cases executed | ...... of 27 |
| Passed | ...... |
| Failed | ...... (S1 ...... S2 ...... S3 ...... S4 ......) |
| Verdict | ☐ Pass ☐ Pass with conditions ☐ Fail |

**Conditions or blockers**

..............................................................................

..............................................................................

### Release gate

This release is deployable to production only when all hold:

- [ ] Every S1 and S2 closed, or formally accepted in writing by the business owner
- [ ] Section 4 answered
- [ ] T22 to T25 passed — the change did not disturb existing tenancies or reporting
- [ ] Upgrade run cleanly on this staging copy of production (T26)
- [ ] Rollback position understood: the BR-075 gate adds no schema that needs
      reversing, so rolling back is a redeploy of the previous commit; the
      earlier `Vacant → Available` migration is **not** reversible from the data
      and is out of scope here (see `docs/migration_plan.md` §8)
