# Architecture decisions

Decisions taken during the build, recorded after the fact. These are calls the
developer is entitled to make; anything needing a business, legal, tax or audit
judgement belongs in `decisions_required.md` instead, and is not decided here.

Each entry says what was chosen, what was given up, and what would reverse it.

---

## AD-01 — Modules live at the repository root, not under `addons/`

**Chosen:** `c2p_property_lease/`, `c2p_ceo_command_center/`, `sinclaire_base/`
at the top level.

**Why:** Odoo.sh puts the repository root on the addons path. A nested
`addons/` directory would need the path configured and would not match how
Odoo.sh builds.

**Given up:** The conventional `addons/` layout some repositories use.
`tools/validate_manifests.py` and `tools/ci_addons.py` carry a `NON_ADDON_DIRS`
list so top-level tooling directories are not mistaken for modules — any new
non-module directory must be added to both.

---

## AD-02 — The `c2p.` prefix, and no `x_` on module fields

**Chosen:** `c2p.building`, `c2p.unit`, `c2p.lease`, `c2p.head.lease`, with
ordinary unprefixed field names.

**Why:** `x_` marks fields created through Studio. The BRD requires a dedicated
module, whose fields are ordinary Python attributes; the prefix would state
something untrue about how they were made. The models also already exist on the
production database with live data, so renaming is a migration with no gain.

**Given up:** Literal correspondence with the BRD's §8.3.4 and §8.3.5 proposed
names. `data_dictionary.md` §3 maps every proposed name to its implemented one,
so the BRD's tables remain traceable.

**Reversed by:** The client requiring the Studio convention for a support
reason. New fields would adopt it; existing models still should not be renamed.
The BRD marks these names as proposals requiring developer confirmation
(§8.3.4), so this is a recommendation, not a unilateral change.

---

## AD-03 — Head lease and owner management are two models, not one

**Chosen:** `c2p.head.lease` and (planned) `c2p.management.contract`, where the
BRD maps a single `x_property_contract` with an operating-model field.

**Why:** They are different economic relationships. Under a head lease Sinclair
owns the tenancy income and carries the vacancy risk. Under owner management
the landlord owns the income, Sinclair earns a fee, and **the money must never
reach company revenue or company cash** (§6.3.1, OD-02). One model would make
that rule a conditional branch on every posting, statement and report. Two
models make it structural: there is no field to set wrongly.

**Given up:** A single list of "contracts". Reporting that wants both will join
them; the BRD asks for them to be separately identifiable anyway (§4.1.2).

---

## AD-04 — Payment instruments extend `account.payment`

**Chosen:** Cheque fields on `account.payment`, where the BRD proposes a
separate `x_payment_instrument` object.

**Why:** `account.payment` already carries partner, amount, currency, journal
and the accounting link, and reconciles against bank statements. It also puts
tenant and landlord cheques in **one register**, which §6.2 asks for. A parallel
object would duplicate all of that and need syncing to the payment it shadows.

**Given up:** Freedom to model instrument states without regard to payment
states. The BRD's seven-state instrument lifecycle is carried in `pdc_state`,
separate from Odoo's own `state`, so the two do not fight.

**Watch:** If custody requirements grow beyond what fields on a payment can
carry — multiple custodians per instrument, instruments with no payment —
revisit.

---

## AD-05 — Derive documents and counts, never type them

**Chosen:** `tools/check_requirement_matrix.py` derives the matrix counts;
`tools/gen_data_dictionary.py` generates the as-built field list from the
source; `tools/check_version_bumps.py` and the percentage-widget rule in
`tools/validate_manifests.py` enforce the other invariants. All run in CI.

**Why:** Four defects in this project have had one shape — two lists that must
agree, with nothing asserting that they do:

| | What drifted |
| --- | --- |
| Sample loader | `COUNTERS` tuple vs. the counters used → `KeyError` |
| Tenant lease | cheque dropdown vs. `CHEQUE_PLAN` → unusable option, then a latent `KeyError` |
| Dashboard | field scale vs. widget scale → 8200% in production |
| Requirement matrix | typed summary counts vs. actual rows → wrong on the first pass |

A data dictionary is the most drift-prone document of all: it is correct the day
it is written and fiction a month later.

**Given up:** Free-form editing of the generated sections. The markers are
enforced — edit the field definition and regenerate.
