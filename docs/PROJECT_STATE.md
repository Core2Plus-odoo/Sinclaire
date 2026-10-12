# Project state — resume point

**As at 2026-10-12.** Written so the work survives the loss of the Odoo.sh
trial instance and can be picked up against a new one.

Read this first, then `CLAUDE.md` for how to work in the repository.

---

## 1. What is at risk, and what is not

| Thing | Lives where | Survives the trial being deleted? |
| --- | --- | --- |
| All module code, tests, tooling, docs | **GitHub** `Core2Plus-odoo/Sinclaire` | **Yes.** Odoo.sh pulls *from* GitHub; it never held the source |
| CI history and PRs | GitHub | Yes |
| The sample portfolio (6 buildings, 100 units, cheques, invoices) | Odoo database | **Regenerable from code** — `c2p.sample.portfolio`, see §6 |
| Hand-entered head leases, owner-management contracts, banking facilities | Odoo database **only** | **No.** See §2 — this is the one irreplaceable category |
| Odoo.sh project, branch and build configuration | Odoo.sh | No, but trivial to recreate: point a new project at the same GitHub repo |
| Routines / scheduled check-ins, connectors | The claude.ai account | Yes — not tied to the instance |

**The short version: the code is already safe.** Nothing in this repository
depends on the trial instance existing.

## 2. What only you can preserve, before the instance goes

The database. Specifically, anything *entered by hand* rather than generated,
because `docs/migration_plan.md` §1 deliberately forbids importing three
objects — they are commitments to pay real money and must be transcribed from
signed agreements:

- **head leases** (`c2p.head.lease`)
- **owner-management contracts**
- **banking facilities** (`c2p.bank.facility`)

Plus any real tenancies, tenants or cheques keyed in during the trial.

Take an Odoo.sh backup before the instance is removed — the Backups tab of the
project offers a downloadable dump, which includes the filestore. Keep it
somewhere outside Odoo.sh.

If everything in the trial came from the sample loader, there is nothing to
save: §6 rebuilds it. **I cannot tell from here which it is** — that depends on
what was typed in, and it is worth five minutes to check
*Property → Operations → Head Leases* and *Finance → Banking Facilities* for
records that reflect real agreements rather than generated ones.

## 3. Where the code stands

| Module | Version | Notes |
| --- | --- | --- |
| `sinclaire_base` | 19.0.1.0.0 | Branding, company config |
| `c2p_property_lease` | 19.0.1.7.1 | Core domain |
| `c2p_ceo_command_center` | 19.0.1.3.0 | Dashboard |

- `main` is at **`7c2ae8c`** — PRs #7 through #13 merged.
- Branch **`claude/intelligent-franklin-j9gtkn`** is at **`588b49b`** and is
  **[PR #14](https://github.com/Core2Plus-odoo/Sinclaire/pull/14), open and
  green**, carrying the payment-instrument states *and a HIGH-severity security
  fix*. See §5 — I would merge this before anything else.
- Nothing uncommitted, no stashes, everything pushed.
- CI on `588b49b`: **0 failed, 0 errors of 147 tests** (106 before that PR).
  The only skips are three `Subscriptions is not installed` cases, which is
  expected — `sale_subscription` is Enterprise and cannot be installed in CI.

### Built so far

- **Buildings, units, tenancies** with the BRD's ten-state unit model (§3.2)
  and twelve-state lease model (§5.1), transitions as guarded methods.
- **Head leases** — the underwriting side: coverage ratio, break-even
  occupancy, gross margin, landlord cheque register.
- **Tenant cheque register** with the full seven-state instrument model,
  replacement chains and a permanent bounce record.
- **BR-075** — a tenancy cannot start with its cheques short without an
  approved `c2p.lease.cheque.exception`.
- **CEO Command Center** — occupancy, contracted rent, vacancy loss, expiry
  profile at 30/60/90, cheque position, bounce rate, deal margin.
- **Tooling** — six checkers in `tools/`, all wired into CI, each one written
  after a specific defect got through.
- **Stage 1 documentation** — requirement response matrix (186), report
  catalogue (90), data dictionary (generated from source), status matrix,
  migration plan, decisions log, open-decisions register.

## 4. What is deployed

Production was last upgraded on **2026-10-06 at 17:43**, to
`c2p_property_lease 19.0.1.6.0` and `c2p_ceo_command_center 19.0.1.2.2` — the
state of `main` at that moment. PR #13 was docs-only and changed no version.
**Nothing in PR #14 is deployed.**

| | Version live | Gap |
| --- | --- | --- |
| `c2p_property_lease` | 19.0.1.6.0 | PR #14 takes it to 19.0.1.7.1 |
| `c2p_ceo_command_center` | 19.0.1.2.2 | PR #14 takes it to 19.0.1.3.0 |

One migration has run against real data: **19.0.1.3.0 `pre-migrate`**, which
moved **23 units** from Vacant to Available on 2026-10-06. It logged the count
but not the identities, so that edit is **not reversible from the data** — the
reason the reversibility rule now exists. `docs/migration_plan.md` §8 carries
the register.

The **19.0.1.7.0 `post-migrate`** backfill (`has_bounced`) has **never run
anywhere** — CI builds fresh databases, so no migration executes there. Watch
for its `flagged N previously bounced cheque(s)` line on the first real
upgrade.

## 5. Open items, in the order I would take them

### Blocking the next deploy

1. **Merge PR #14.** It contains a HIGH-severity fix: before it,
   `c2p.lease.cheque.exception.state` was an ordinary writable Selection in a
   clickable status bar, so a leasing agent could approve their own cheque
   exception in two clicks and activate a lease with its cheques missing —
   defeating BRD §5.1 and §8.4's no-self-approval rule from exactly the role
   those rules constrain. **That hole is live in whatever instance is running
   19.0.1.6.0.** If the trial is being discarded anyway the exposure ends with
   it; if it is kept, deploy this.
2. **BR-075 UAT.** `docs/uat/BR-075_cheque_gate.md` — 27 cases, needs a staging
   database restored from production, two logins in different roles, and a
   named business owner. Section 4 of that script asks four questions that are
   *not* tests and matter more than the cases: whether the leasing team
   actually activates before cheques arrive, who the real approver should be,
   and whether one open exception per lease is right.
3. **Tell the leasing team** about BR-075 before they meet it cold. The
   renewal change is the one that will look like a bug: the wizard now drafts
   the successor and leaves the outgoing tenancy running, instead of
   activating it.

### Blocked on the client

| ID | What is missing | What it blocks |
| --- | --- | --- |
| **OD-06** | Approval matrix, limits, role-to-permission mapping | BR-036, BR-072, every *(proposed)* role in `status_matrix.md`, all sensitive-report visibility, and the real approver for BR-075 |
| **OD-09** | Opening data volumes, cutover date, historical retention | The whole migration schedule |
| **OD-02** | Custody control account for landlord-name cheques | BR-116 |
| — | Sign-off on dropping the BRD's proposed `x_` field prefix | Recorded with a full proposed→implemented mapping in `docs/decisions.md` |

### Next build pieces, unblocked

- **BR-018** mandatory-data check on unit release. Only half-deliverable: the
  approval half waits on OD-06. Needs a decision on *which* unit fields are
  mandatory before marketing — I would propose type, area and asking rent, and
  flag the rest rather than guess.
- **`cleared` should follow bank reconciliation, not a button.** This is a
  correction to my own design, written up in full in the architecture review:
  BR-118 says no cheque is treated as cleared before bank or landlord
  confirmation, and today that is asserted by a user action while Odoo's own
  `account.payment.state` and outstanding-account machinery sit unconnected
  beside it. Configure the PDC journal's outstanding account first, then derive
  `cleared`, keeping the manual path only for the landlord-account case the
  BRD explicitly allows.
- **Payment-term duplication.** `action_generate_expected_cheques` produces a
  forward view that Odoo already produces from invoice due dates under
  instalment payment terms. The *instrument* expectation is justified; the
  *cash forecast* should point at receivables, or the two will drift.

### Long-standing debts

- Never run on an Odoo.sh **staging** branch — only CI and production.
- VAT is documented but not enforced in code.
- No module icons; no Arabic translations (every upgrade logs
  `no translation for language ar_001`).
- The user-guide PDF documents a superseded fee model and needs rewriting.
- `actions/checkout@v4` and `actions/setup-python@v5` target deprecated Node 20.

## 6. Standing up a new instance

1. Create the Odoo.sh project (or any Odoo 19 Enterprise host) and point it at
   `Core2Plus-odoo/Sinclaire`, branch `main`.
2. Install `sinclaire_base`, `c2p_property_lease`, `c2p_ceo_command_center`.
   `account` must be configured first — a chart of accounts and a bank journal
   with an inbound payment method, or the cheque register cannot create
   instruments.
3. Create a **PDC journal with code `PDCR`** if you want the cheque register to
   default to it.
4. For a demo portfolio: *Property → Configuration → Load Sample Portfolio*.
   It is idempotent, creates 6 buildings and 100 units with leases, cheques,
   invoices, head leases and facilities, and is the reason the trial database
   is largely disposable.
5. For real data, follow `docs/migration_plan.md` — object order matters, and
   objects 11 to 13 are hand-entered before the dependent loads.
6. `docs/DEPLOY.md` has the deploy and backfill procedure. It uses
   `<placeholder>` form deliberately: **this repository is public**, so do not
   write the real host or database name into it.

## 7. Things worth knowing that are not obvious from the code

- **Production was displaying sample-portfolio figures** on 2026-09-16 (6
  buildings, 100 units, AED 7,622,400 contracted rent). Whether that was
  deliberate, and whether it was ever cleared, was never settled — logged as
  N2 in `docs/decisions_required.md`. Settle it before any real load.
- The September outage was caused by **an unbumped manifest version**, not by
  bad code. Everything passed lint and installed cleanly into an empty
  database; it only broke upgrading a database that already held the previous
  version. `tools/check_version_bumps.py` exists for that.
- Two guidance errors of mine cost time during that incident, recorded so they
  are not repeated: I gave `<db>` as an unmarked placeholder, which bash read
  as a redirect; and I recommended `odoo-bin` where Odoo.sh provides
  `odoo-update`.
- `docs/decisions.md` carries the architectural decisions with their reasoning
  (AD-01…AD-05), including why head lease and owner management are two models
  rather than one with a flag: it makes the client-money rule structural
  instead of a conditional branch.
