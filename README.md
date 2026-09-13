# Sinclaire

Odoo customisations for Sinclaire, maintained by C2P Consultants.

- **Odoo series:** 18.0 (Enterprise)
- **Python:** 3.11
- **Custom addons live in:** [`addons/`](addons/)

## Repository layout

```
.
├── addons/                     # Custom Odoo modules (this is the addons-path entry)
│   └── sinclaire_base/         # Shared foundation; every other module depends on it
├── conf/
│   └── odoo.conf.example       # Copy to odoo.conf (git-ignored) for local runs
├── docs/
│   └── module_template/        # Copy-paste starting point for a new module
├── tools/
│   └── validate_manifests.py   # Manifest / XML checks, also used by CI
├── .github/workflows/          # CI: lint + static checks, and Odoo integration tests
├── requirements.txt            # Extra runtime deps imported by our modules
└── requirements-dev.txt        # Lint / pre-commit tooling
```

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

1. Copy `docs/module_template/` to `addons/sinclaire_<feature>/`.
2. Fill in `__manifest__.py`; keep `"depends": ["sinclaire_base", ...]`.
3. Version strings are `18.0.<major>.<minor>.<patch>` — the series prefix is
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

Every pull request runs the lint job. The **Odoo tests** workflow (full install
of every addon into a throwaway database) runs on `main` and on demand from the
Actions tab; enable its `pull_request` trigger once the suite is worth the extra
minutes.

## Branching

Work happens on feature branches merged into `main` via pull request.
