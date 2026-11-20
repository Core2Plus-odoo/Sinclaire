# CLAUDE.md

Working notes for anyone — person or agent — picking this repository up.
`docs/PROJECT_STATE.md` is the resume point: read it first for *where things
stand*. This file is *how to work here*.

## What this is

Odoo 19 Enterprise property-management modules for **New Sinclair Property
Management LLC**, built by C2P Consultants. Four addons, in three layers:

| Module | Layer | What it is |
| --- | --- | --- |
| `sinclaire_base` | 1 | Company branding, shared config, and the `sin-*` design tokens and components |
| `c2p_property_lease` | 2 | Buildings, units, tenancies, head leases, cheque register, bank facilities |
| `c2p_ceo_command_center` | 2 | Leadership dashboard over the above |
| `sinclaire_workspace` | 3 | Role-aware workspaces and the 360 screens — presentation only |

Versions are in the manifests; this table deliberately does not repeat them,
because a version typed in two places is the defect described below.

**The layering is a contract term, not a preference.** `c2p_property_lease` is
the supplier's work under OPL-1; `sinclaire_workspace` is client development
under LGPL-3. So business rules go in layer 2 and *only* presentation plus
derived display fields go in layer 3. A rule that creeps into the workspace
module is a licensing problem as well as an architectural one.

New screens follow the existing 360s: **inherit the form view** and add
derived fields, with the `sin-*` components from `sinclaire_base`. Do not reach
for an OWL client action — one was written for Tenant 360 and thrown away,
because a bespoke component re-implements what a form view already does and
drops every field the underlying module adds later.

The **BRD is the contract.** Requirements are catalogued in
`docs/requirement_response_matrix.md` as `BR-001`…`BR-186`; reports in
`docs/report_catalogue.md` as `RPT-001`…`RPT-090`. State machines are specified
in `docs/status_matrix.md` — that file is the spec, the code follows it.

Where this file and the BRD disagree, **the BRD wins and you flag the
conflict** rather than resolving it silently. Where the BRD is silent on a
policy, **do not guess it** — log it in `docs/decisions_required.md` as an
`OD-nn` and build the mechanism without inventing the value.

## Engineering standard

C2P's ERP delivery standard (the Claude Code ERP Blueprint Pack) governs how work
is planned and reported here. `docs/project/AUDIT_WAVE0.md` is the Wave 0 audit of
this repository against it — read it for where the project stands against the
standard, the open blockers and the next task. `docs/project/DECISION_REGISTER.md`
maps the blueprint's twelve mandatory ADRs onto this project's evidence and its
open `OD-nn` decisions.

The pack itself is **not vendored**: this repository is public and the pack is
C2P's commercial methodology. Whether it may be committed is an open decision
(audit §8, D8), so the blueprint is referenced by section number rather than
copied in.

Report development work in the pack's form: task, repository status, impact,
plan, what was actually implemented, what was **verified** (or `NOT RUN`, which
is the honest answer for any Odoo test in this container), reconciliation,
remaining decisions, next action.

## Hard rules

1. **This repository is public.** Never commit a live hostname, database name,
   Odoo.sh build name, API key or password. `docs/DEPLOY.md` uses
   `<placeholder>` form; keep it that way. Credentials come from environment
   variables (`ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD`) and an
   **API key, never the admin password**.
2. **Never vendor Odoo Enterprise source.** `sale_subscription` is a
   deliberate *soft* dependency — a registry check, not an entry in `depends`
   — because the licence forbids committing it and CI cannot install it. The
   subscription actions light up when it is present and refuse with a clear
   message when it is not.
3. **Bump the manifest version on every change that must reach a database.**
   Odoo.sh upgrades a module on deploy only when the manifest version is
   higher than the one recorded in the database. Shipping changed code under
   an unchanged version restarts the build with new Python and an untouched
   schema — fields exist in the registry with no column behind them, and the
   first read raises `UndefinedColumn`. That is exactly what took production
   down on 2026-09-16. `tools/check_version_bumps.py` enforces it.
4. **Sample tenant, contact and salary data from the source workbooks must
   appear in no production template and no test export** (BRD §9.2.4).

## Before you push

```bash
ruff check . && ruff format --check .
python tools/validate_manifests.py
python tools/check_test_hygiene.py
python tools/check_contrast.py
python tools/check_version_bumps.py
python tools/check_requirement_matrix.py
python tools/gen_data_dictionary.py --check
python -m unittest discover -s tools/tests
```

All eight run in CI (`.github/workflows/ci.yml`). The Odoo tests
(`.github/workflows/odoo-tests.yml`) install the addons into a real database
and are the **only** gate that catches an install failure — there is no Odoo in
the dev container, so CI is the first execution of any Odoo test you write.
Say so when you report, rather than implying you ran them.

## Odoo 19 specifics that have bitten here

- `models.Constraint` replaces `_sql_constraints` — **v19 ignores the latter
  silently**, so a uniqueness rule written the old way lets duplicates through.
- **`ir.ui.view` has no `groups_id` in v19.** Setting it on a view record does
  not degrade — it raises `ValueError: Invalid field 'groups_id'` while the
  module's data loads and **fails the whole install**, leaving the database
  half-upgraded. Restrict view *content* with a `groups=` attribute on the
  elements inside the arch, which also strips them from the arch the reader
  is sent. `tools/validate_manifests.py` now refuses the field.
- `res.groups.privilege_id`, `res.users.group_ids`, `<list>` not `<tree>`, no
  `attrs`/`states`, and `<group>` inside a search view takes neither `expand`
  nor `string`.
- `widget="percentage"` expects a **0–1 fraction**; `widget="progressbar"`
  expects 0–100. Fifteen fields were showing `8200%` because of this.
  `tools/validate_manifests.py` now bans `widget="percentage"`.
- `fields.Selection([...])` passes its list **positionally**, not by keyword.
- A **non-stored compute cannot appear in a search domain** at all, and a
  stored compute with an incomplete `@api.depends` serves stale values with no
  error — the screen just quietly shows the wrong number.
- `has_group()` is a **genuine membership check even for the superuser**.
  Neither OdooBot nor admin is in this module's groups, so server-side code and
  test fixtures are not authorised approvers. Design for that rather than
  assuming root passes.
- Odoo demo data is off by default in v19 (`--with-demo`), so CI databases have
  a chart of accounts but no demo records.

## The recurring defect in this codebase

**Two structures that must agree about a set of values, with nothing asserting
that they do.** It has caused six separate defects here: a cheque-schedule map
that never gained the 3-cheque option; a summary dict built from a hand-written
key tuple; a state group that drifted from the state selection; counts typed
into a markdown table; a months-per-instalment map duplicated in a wizard; and
the renewal-alert bands, which existed as a literal `(90, 60, 30)` inside the
cron while a second screen decided separately what "expiring soon" meant.

The wizard's map is worth dwelling on, because it was fixed on a branch and the
defect still reached `main` from a different direction. Two people removing the
same duplication independently is not redundant work — whichever copy survives
is the one that drifts next. The fix is never "delete the copy"; it is *delete
the copy and add the test that fails if one comes back.*

So: **derive, don't type.** One constant, one place, and a test that walks the
whole set. `tools/check_requirement_matrix.py` and
`tools/gen_data_dictionary.py --check` exist because docs drift the same way.

## Migration scripts

A script that changes rows must capture them with `RETURNING` and log the
statement that puts them back — Odoo keeps no undo, and after an in-place edit
the set of affected rows exists nowhere else. Primary keys only, the whole
list, `_logger` not `print()`. `tools/tests/test_migration_reversibility.py`
enforces it over every script under `*/migrations/`, including ones not yet
written. `docs/migration_plan.md` §8 has the reasoning and the register of
scripts already applied to production.

## Controls, and what they are worth

Several requirements are **refusals** rather than features — activation gates,
overlap prevention, immutable baselines, client-money segregation. Two things
learned the hard way:

- Put the rule on the **transition, not the button**. `state` fields are
  writable and status-bar widgets write them directly, so a guard that only
  sits in an action guards nothing. Both `c2p.lease.write` and
  `account.payment.write` refuse state moves for this reason.
- A **context key is a convention, not a boundary.** `c2p_lease_loaded` and
  `c2p_pdc_move_recorded` mark the data-load path; anyone can set them. That is
  acceptable where the underlying write permission is already granted and only
  the audit trail is at stake. It is **not** acceptable for a privileged act:
  the cheque-exception approver check deliberately ignores its context key,
  because otherwise the bypass just moves one layer down.

## Style

Match the surrounding code: same comment density, same naming, same idiom.
Comments here explain **why**, and often cite the BRD section or the defect
that motivated the line. Tests are named as sentences describing the property
under test. Keep that.

When a test exists to catch a specific past defect, say so in its docstring —
and make sure it actually fails against the old behaviour before trusting it.
A test written against a bug makes the bug permanent; that has happened here.
