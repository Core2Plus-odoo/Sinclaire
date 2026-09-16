# Contributing

## Conventions

**Module naming.** Lowercase with underscores. Two prefixes are in use and
both are current: `sinclaire_<feature>` for shared foundation pieces, and
`c2p_<feature>` for the delivered functional modules (`c2p_property_lease`,
`c2p_ceo_command_center`). Pick the one that matches what the module is.

`sinclaire_base` holds the shared security groups and privileges. Depend on it
when you need those; the `c2p_*` modules currently do not, so treat it as
available rather than mandatory. If you want it to become mandatory, say so and
we will make the existing modules comply rather than leaving the rule aspirational.

**Module layout.** Modules live at the repository root (Odoo.sh's addons
path), not in a subdirectory. Mirror `docs/module_template/`:

```
<prefix>_<feature>/
├── __init__.py
├── __manifest__.py
├── models/            # one file per model, named after the model
├── views/             # one file per model: <model>_views.xml
├── security/          # ir.model.access.csv + record rules
├── data/              # noupdate="1" master data
├── wizard/            # TransientModel + their views
├── report/            # QWeb report templates and report definitions
├── static/            # src/ for JS/SCSS, description/ for the app icon
├── i18n/              # .pot template and .po catalogues
└── tests/             # imported from tests/__init__.py
```

**Licence.** `LGPL-3` for modules depending only on Community. A module that
depends on an Enterprise app must be `OPL-1` — Odoo's Enterprise licence does
not permit an LGPL derivative of it.

**Models.** Prefer extending over replacing. Use `_inherit` for existing models
and keep custom fields prefixed with `x_` only when they must stay
Studio-compatible. No raw SQL unless there is a measured reason, and never
string-interpolate values into a query.

**XML.** One record per logical change, stable XML IDs, `noupdate="1"` for data
a user is expected to edit. Never edit core views by replacing them wholesale —
use `xpath` inheritance.

**Security.** Every new model needs an `ir.model.access.csv` line. Record rules
go in `security/`, not in the model.

**v19 gotchas.** `_sql_constraints` is no longer read by the ORM — declare
`models.Constraint(...)` / `models.UniqueIndex(...)` class attributes instead, or
your constraint silently never reaches the database. `res.groups.category_id` is
now `privilege_id` pointing at `res.groups.privilege`, and `res.users.groups_id`
is `group_ids`. Set `_check_company_auto = True` on any model with a
`company_id`. In a search view `<group>` accepts neither `expand` nor `string`
— the v18 idiom `<group expand="0" string="Group By">` fails at install. Demo
data is **off** by default; pass `--with-demo` if you want it (`--without-demo`
is now a boolean and rejects `=all`).

**Computes.** A stored compute without `@api.depends` never recomputes. It
raises nothing — it just serves the value from whenever the record was last
written, so the screen quietly shows stale figures. If the compute reads a
related record, add the One2many you need in order to declare the dependency
properly rather than omitting it. A *non-stored* compute cannot appear in a
search domain or filter at all; give it `store=True` or a `search=` method.

**Versions.** `19.0.<major>.<minor>.<patch>`. Bump the last segment for fixes,
the middle one for new behaviour, and add a migration script when the change
needs one.

## Things static analysis will not catch

`ruff check` and `tools/validate_manifests.py` passed in **every one** of the
five broken states that preceded the underwriting merge. Four distinct install
failures got through them. What each teaches:

| Failure | Lesson |
| --- | --- |
| `ImportError: cannot import name 'owner_statement'` | A formatter had reflowed the package imports, so a line-based removal matched nothing and silently no-opped. `force-single-line` is now set in the isort config so import lists cannot collapse; **assert on the anchor** of any scripted string replacement. |
| `KeyError: Field potential_rent ... does not exist` | Same cause: the declaration replace missed while the compute assignment landed. A field assigned but never declared passes lint. |
| `Unsearchable field "coverage_ratio"` | A filter searched a non-stored compute. |
| `KeyError: 'head_leases'` | A summary dict built from a hand-written key tuple that drifted from the counters actually used. Seed it from a `COUNTERS` constant and test that the two stay in step. |

The install job is the only gate that sees these. Run the module up locally, or
expect CI to find it for you.

## Before you push

```bash
pre-commit run --all-files
python tools/validate_manifests.py
```

## Pull requests

- One logical change per PR; keep generated files (`.pot`, lockfiles) in their
  own commit.
- Describe what changes for the user, not just what changed in the code.
- CI must be green before review.
