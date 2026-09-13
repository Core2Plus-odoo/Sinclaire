#!/usr/bin/env python3
"""Decide which of this repo's addons CI can actually install.

The public `odoo:19.0` image ships Community only, so a module depending on an
Enterprise app (sale_subscription, account_accountant, documents, ...) cannot be
installed there. Rather than failing the whole job, resolve each addon's
dependency tree against the addons paths that are present and report which
modules are installable and which are being skipped, and why.

Usage:
    ci_addons.py --addons-path /usr/lib/python3/dist-packages/odoo/addons,.

Writes `names=` and `tags=` lines suitable for $GITHUB_OUTPUT to stdout, and a
human-readable summary to stderr.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NON_ADDON_DIRS = {".git", ".github", "conf", "docs", "tools", ".ruff_cache"}


def read_manifest(addon: Path) -> dict:
    try:
        manifest = ast.literal_eval((addon / "__manifest__.py").read_text(encoding="utf-8"))
    except (SyntaxError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def discover(paths: list[Path]) -> dict[str, Path]:
    """Map module name -> directory across every addons path."""
    available: dict[str, Path] = {}
    for base in paths:
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name in NON_ADDON_DIRS:
                continue
            if (child / "__manifest__.py").is_file():
                available.setdefault(child.name, child)
    return available


def missing_dependencies(name: str, available: dict[str, Path]) -> set[str]:
    """Transitively resolve depends; return the names that cannot be found."""
    missing: set[str] = set()
    seen: set[str] = set()
    stack = [name]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        addon = available.get(current)
        if addon is None:
            missing.add(current)
            continue
        stack.extend(read_manifest(addon).get("depends", []) or [])
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--addons-path", required=True)
    args = parser.parse_args()

    paths = [Path(p.strip()) for p in args.addons_path.split(",") if p.strip()]
    available = discover(paths)

    ours = sorted(
        p.name
        for p in REPO_ROOT.iterdir()
        if p.is_dir() and p.name not in NON_ADDON_DIRS and (p / "__manifest__.py").is_file()
    )

    installable, skipped = [], {}
    for name in ours:
        missing = missing_dependencies(name, available) - {name}
        if missing:
            skipped[name] = sorted(missing)
        else:
            installable.append(name)

    print(f"names={','.join(installable)}")
    print(f"tags={','.join('/' + n for n in installable)}")

    print(f"Installable here: {', '.join(installable) or '<none>'}", file=sys.stderr)
    for name, missing in skipped.items():
        print(
            f"SKIPPED {name}: depends on {', '.join(missing)}, which is not on "
            "the addons path. If those are Enterprise modules, mount the "
            "Enterprise addons to test this module in CI.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
