# Contributing

## Conventions

**Module naming.** `sinclaire_<feature>`, lowercase with underscores. Every
module depends on `sinclaire_base`.

**Module layout.** Mirror `docs/module_template/`:

```
sinclaire_<feature>/
├── __init__.py
├── __manifest__.py
├── models/            # one file per model, named after the model
├── views/             # one file per model: <model>_views.xml
├── security/          # ir.model.access.csv + record rules
├── data/              # noupdate="1" master data
├── wizards/           # TransientModel + their views
├── reports/           # QWeb report templates and report definitions
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
`company_id`.

**Versions.** `19.0.<major>.<minor>.<patch>`. Bump the last segment for fixes,
the middle one for new behaviour, and add a migration script when the change
needs one.

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
