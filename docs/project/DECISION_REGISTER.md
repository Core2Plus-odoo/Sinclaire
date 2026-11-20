# Decision register — blueprint ADRs against this project

Maps the twelve mandatory ADRs of `docs/ERP_MASTER_BLUEPRINT.md` §2 onto what this
project has actually decided, and onto the `OD-nn` register the repository already
keeps. Three registers would drift from each other, so this one is a **map, not a
third source of truth**:

- `docs/decisions.md` — decisions **taken**, with rationale.
- `docs/decisions_required.md` — `OD-01`…`OD-10`, **open**, with what each blocks.
- this file — the blueprint's ADR frame over both, so a reader coming from the
  blueprint can find the answer or see that there is none.

Status values: **Answered by evidence** (verifiable in the repository),
**Answered by decision** (recorded in `docs/decisions.md`), **Open** (blocking or
not), **N/A** (does not apply to this scope, which is itself a decision).

---

| ADR | Decision | Status | Where / what is missing |
| --- | --- | --- | --- |
| **ADR-001** | Odoo extension vs greenfield custom vs integration | **Answered by evidence** | Odoo extension. Four addons extending `account.payment`, `account.move`, `res.partner`, `sale.order` via `_inherit`; no core fork; no accounting method overridden. **But see D1 in the audit:** the *scope* this serves is open |
| **ADR-002** | Tenant model | **Answered by evidence** | Single database, Odoo multi-company. Not a multi-tenant product |
| **ADR-003** | Company / branch / department / warehouse model | **Partially answered** | Two legal entities per BR-004 (`res.company`). No branch, department or cost-centre model; the property dimension is carried by analytic accounts on the building. **No warehouse — there is no stock.** Enforcement gap: two models carry `company_id` with no record rule (audit R2) |
| **ADR-004** | Financial source of truth | **Open — blocking** | Native `account.move` is the ledger and no posting is overridden, which is the right half. The missing half is the custody control account for landlord-name cheques: **OD-02**. Until it is answered, BR-116 cannot be completed and BR-118 cannot be fixed correctly |
| **ADR-005** | Inventory valuation | **N/A** | No stock in scope. Recorded explicitly so the absence reads as a decision rather than an oversight |
| **ADR-006** | Localization | **Open** | UAE. VAT is documented but **not enforced in code** — a recorded debt. Templates, numbering and notification wording are **OD-08**. No e-invoicing requirement identified in the BRD |
| **ADR-007** | Workflow / approval engine, thresholds, delegation, SoD | **Open — blocking** | **OD-06.** BRD §2.3 names twenty roles; the system has two groups. The *mechanisms* are built in the right place — the no-self-approval rule sits on `write`, not in a button, and the approver check deliberately ignores its context key — but *who approves what* is unanswerable. Blocks BR-023, BR-036, BR-039, BR-072, BR-079, BR-172, BR-176, and every *(proposed)* role in `status_matrix.md` |
| **ADR-008** | Integration strategy | **Open** | **OD-07** (required integrations) and **OD-09** (volumes, cutover, retention). Nothing integrated today. BR-119 (bank certification), BR-120 (no open DEWA third-party interface) and BR-152 (the company app's API) are outside our control |
| **ADR-009** | Security and identity | **Partially answered** | Odoo groups, 21 ACL rows, 6 record rules, no casual `sudo()`, no SQL bypassing validation. Missing: the role model itself (ADR-007), a `SECURITY_MATRIX.md`, and the two record rules in audit R2. No SSO/MFA requirement identified |
| **ADR-010** | Deployment and disaster recovery | **Open** | **OD-10.** Odoo.sh; GitHub is the source of truth and the code was never on the trial instance. **No staging branch has ever been used** — only CI and production, which makes CI the sole pre-production gate. RPO/RTO unagreed |
| **ADR-011** | Accounting close / correction policy | **Open** | Partly decided by evidence: `Cleared` is terminal because a reversal after clearing is a new accounting event, and no posted history is ever altered. Period locks, backdating controls and the approved correction workflow are **not** decided — rides with **OD-02**/**OD-05** |
| **ADR-012** | Stack / Odoo version and supported dependencies | **Answered by evidence** | Odoo **19.0 Enterprise**, Python 3.12 in CI, `MIN_PY_VERSION = (3, 10)`. `sale_subscription` is a deliberate **soft** dependency: a registry check, never in `depends`, because the licence forbids committing it and CI cannot install it. The actions light up when present and refuse clearly when not |

---

## Decisions already taken that the blueprint would want as ADRs

Recorded in `docs/decisions.md` and in code comments; listed here because a reader
arriving from the blueprint will look for them under an ADR heading.

| Decision | Rationale |
| --- | --- |
| Three layers with a licence boundary | `c2p_property_lease` is the supplier's work under OPL-1; `sinclaire_workspace` is client development under LGPL-3. Business rules in layer 3 would be a licensing problem as well as an architectural one |
| 360 screens inherit a form view; no OWL client action | An OWL component re-implements what a form view does and silently drops every field the underlying module adds later. One was written for Tenant 360 and deleted unmerged |
| Controls go on the transition, not the button | `state` is writable and status-bar widgets write it directly, so a guard in an action guards nothing. `c2p.lease.write`, `account.payment.write`, `c2p.lease.cheque.exception.write` and `c2p.tenancy.event.write` all refuse state moves |
| A context key is a convention, not a boundary | Acceptable where the write permission is already granted and only the audit trail is at stake; **never** for a privileged act — the cheque-exception approver check and the event evidence rule both ignore theirs deliberately |
| `has_bounced` is set on a bounce and never unset | A replacement is a recovery, not a retraction. A bounce rate read off the current state walks to zero as a backlog is worked through while behaviour stays as bad |
| The BRD's proposed `x_` field prefix was dropped | Full proposed→implemented mapping recorded in `docs/decisions.md`. **Awaiting sponsor sign-off** (audit D7) |
| The system records; it does not decide | BR-099: warnings, non-renewals and terminations keep a human in the loop. `c2p.tenancy.event` has no gate on activation, renewal or termination, and tests assert those absences |

---

## How to add to this register

1. Record the decision where it belongs — `docs/decisions.md` if taken,
   `docs/decisions_required.md` if it needs the client.
2. Add or update the row here only if it answers one of the twelve blueprint ADRs.
3. Do not copy the rationale into this file. One sentence and a pointer; the
   reason this register is a map is that a second copy of a decision is the
   defect this codebase keeps producing.
