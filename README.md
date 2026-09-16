# Sinclaire

Odoo customisations for Sinclaire, maintained by C2P Consultants.

- **Odoo series:** 19.0 (Enterprise)
- **Python:** 3.12 in CI (Odoo 19.0 itself requires >= 3.10 — `MIN_PY_VERSION` in `odoo/release.py`)
- **Custom addons live at the repository root** — Odoo.sh puts the repo root on the addons path

## Repository layout

```
.
├── sinclaire_base/             # Shared security groups and privileges
├── c2p_property_lease/         # Buildings, units, head leases, leases, cheques, bank facilities
├── c2p_ceo_command_center/     # Portfolio KPI dashboard, built on c2p_property_lease
├── conf/
│   └── odoo.conf.example       # Copy to odoo.conf (git-ignored) for local runs
├── docs/
│   └── module_template/        # Copy-paste starting point for a new module
├── tools/
│   ├── validate_manifests.py   # Manifest / XML checks, also used by CI
│   └── ci_addons.py            # Resolves which addons CI can install here
├── .github/workflows/          # CI: lint + static checks, and Odoo integration tests
├── requirements.txt            # Extra runtime deps imported by our modules
└── requirements-dev.txt        # Lint / pre-commit tooling
```

Modules sit at the top level because that is what Odoo.sh puts on the addons
path. Everything that is *not* a module (`conf/`, `docs/`, `tools/`,
`.github/`) is excluded by name in `tools/validate_manifests.py` and
`tools/ci_addons.py` — add any new non-module directory to `NON_ADDON_DIRS` in
both.

## What the system models

Sinclaire **underwrites** buildings; it is not an agency earning a percentage.
The company pays the landlord a fixed sum for the year in an agreed number of
cheques, Ejari transfers to Sinclaire, and Sinclaire then sets the leasing
rates and keeps the spread. The landlord's return is fixed and does not depend
on occupancy.

That reverses who carries vacancy: an empty unit costs Sinclaire, not the
landlord, because the head-lease cheques clear either way. Three numbers follow
from it and appear on both the head lease and the building:

```
break-even occupancy = head lease cost / market rent of all units
coverage             = contracted tenant rent / head lease cost
gross margin         = contracted tenant rent - head lease cost
```

Any change that reintroduces percentage-of-collections logic is a change to the
business model, not a refactor — raise it before building it.

## Getting started

```bash
# 1. Dev tooling
python -m pip install -r requirements-dev.txt
pre-commit install

# 2. Server config
cp conf/odoo.conf.example odoo.conf   # then edit paths, db credentials, ports

# 3. Run Odoo with this repo on the addons path
odoo -c odoo.conf -d sinclaire -u all
```

`odoo.conf`, log files, filestores and database dumps are git-ignored — keep
credentials out of the repository.

## Adding a module

1. Copy `docs/module_template/` to `sinclaire_<feature>/` at the repository root.
2. Fill in `__manifest__.py`; keep `"depends": ["sinclaire_base", ...]`.
3. Version strings are `19.0.<major>.<minor>.<patch>` — the series prefix is
   enforced by CI.
4. Declare every data file in the manifest; CI fails if a listed path is missing.
5. Add tests under `tests/` and import them from `tests/__init__.py`.

## Checks

| Command | What it does |
| --- | --- |
| `ruff check .` | Lint (pycodestyle, pyflakes, isort, bugbear, pyupgrade) |
| `ruff format .` | Format |
| `python tools/validate_manifests.py` | Manifest keys, versions, data paths, XML well-formedness |
| `pre-commit run --all-files` | All of the above, as run on commit |

Every pull request runs both workflows: the fast lint job, and **Odoo tests**,
which installs each addon into a throwaway database and runs *our* test suites
against the `odoo:19.0` image (scoped with `--test-tags=/<module>`; the core
suite of every dependency is not our gate to keep green). The lint job cannot see an install failure — a
field renamed between series passes every static check and still breaks `-i` —
so the integration job is the gate that decides whether a change is releasable.

The public `odoo:19.0` image is Community only, so a module depending on an
Enterprise app cannot be installed there. `tools/ci_addons.py` resolves each
addon's dependency tree and skips those, naming them in the job log rather than
failing the run — **so a skipped module's install is never verified by CI.**
No module is skipped today: all three install and test on the Community image.

`c2p_property_lease` reaches `sale_subscription` (Enterprise) through a *soft*
dependency — it is absent from `depends`, and the code checks the registry at
runtime. Odoo's Enterprise licence does not permit vendoring that source here,
so this is the sanctioned way to use it without making CI unable to install us.
The cost is that the three subscription tests **skip** on the Community image
and report as passes:

```
skipped TestLease.test_creating_a_subscription_confirms_it : Subscriptions is not installed
skipped TestLease.test_annual_schedule_falls_back_to_a_yearly_plan
skipped TestLease.test_plan_lookup_prefers_the_rent_plan_over_the_generic_one
```

A regression in the subscription path therefore reaches production unflagged.
Exercise it on an Odoo.sh staging branch before release, or mount the
Enterprise addons onto the job's addons-path to close the gap properly.

## Branching

Work happens on feature branches merged into `main` via pull request.
