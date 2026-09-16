#!/usr/bin/env python3
"""Static checks for the Odoo addons in this repository.

Runs without an Odoo installation, so it is cheap enough for every push:

* every addon has a parseable ``__manifest__.py`` with the required keys;
* the manifest ``version`` carries the expected Odoo series prefix;
* every path listed under ``data`` / ``demo`` / ``assets`` exists;
* every tracked XML file is well formed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parent.parent
# Odoo.sh puts the repository root on the addons path, so modules live at the
# top level. Everything else at that level is tooling, not an addon.
ADDONS_DIR = REPO_ROOT
NON_ADDON_DIRS = {".git", ".github", "conf", "docs", "tools", ".ruff_cache"}
ODOO_SERIES = "19.0"
REQUIRED_KEYS = ("name", "version", "license", "depends")
PATH_KEYS = ("data", "demo", "qweb")


def iter_addons() -> list[Path]:
    return sorted(
        p
        for p in ADDONS_DIR.iterdir()
        if p.is_dir() and p.name not in NON_ADDON_DIRS and (p / "__manifest__.py").is_file()
    )


def check_manifest(addon: Path, errors: list[str]) -> None:
    manifest_path = addon / "__manifest__.py"
    try:
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError) as exc:
        errors.append(f"{manifest_path}: not a literal dict ({exc})")
        return

    if not isinstance(manifest, dict):
        errors.append(f"{manifest_path}: manifest must evaluate to a dict")
        return

    for key in REQUIRED_KEYS:
        if not manifest.get(key):
            errors.append(f"{manifest_path}: missing required key {key!r}")

    version = str(manifest.get("version", ""))
    if not version.startswith(f"{ODOO_SERIES}."):
        errors.append(
            f"{manifest_path}: version {version!r} should start with {ODOO_SERIES!r} (<series>.<major>.<minor>.<patch>)"
        )

    for key in PATH_KEYS:
        for relative in manifest.get(key, []) or []:
            if not (addon / relative).is_file():
                errors.append(f"{manifest_path}: {key} entry {relative!r} does not exist")

    for bundle, entries in (manifest.get("assets") or {}).items():
        for entry in entries:
            target = entry[1] if isinstance(entry, (list, tuple)) else entry
            if "*" in target:
                continue
            module, _, relative = str(target).partition("/")
            asset = addon / relative if module == addon.name else ADDONS_DIR / module / relative
            if not asset.is_file() and module == addon.name:
                errors.append(f"{manifest_path}: asset {bundle} entry {target!r} does not exist")


def check_xml(errors: list[str]) -> None:
    for xml_file in sorted(ADDONS_DIR.rglob("*.xml")):
        try:
            tree = ElementTree.parse(xml_file)
        except ElementTree.ParseError as exc:
            errors.append(f"{xml_file}: malformed XML ({exc})")
            continue
        check_percentage_widget(xml_file, tree, errors)


def check_percentage_widget(xml_file: Path, tree: ElementTree.ElementTree, errors: list[str]) -> None:
    """Ban widget="percentage", which silently multiplies by 100 again.

    Every percentage in this repo is computed and stored on a 0-100 scale
    (`occupied / total * 100`), which is what `widget="progressbar"` expects.
    `widget="percentage"` expects a 0-1 fraction and multiplies by 100 itself,
    so the same field rendered both ways shows "8200%" above a bar reading 82%
    - which is exactly what production showed on 2026-09-16.

    No test catches this: the stored value is correct and every assertion on it
    passes. Only the rendering is wrong. Render these with `digits="[16,1]"`
    and let the field label or literal `%` carry the sign; rescaling the fields
    to 0-1 instead would need a migration, since several are stored.
    """
    for field in tree.iter("field"):
        if field.get("widget") == "percentage":
            name = field.get("name", "?")
            errors.append(
                f'{xml_file}: field "{name}" uses widget="percentage", but this repo '
                f"stores percentages on a 0-100 scale, so it would render 100x too "
                f'large. Use digits="[16,1]" and carry the % in the label or markup.'
            )


def main() -> int:
    addons = iter_addons()
    if not addons:
        print("No addons found at the repository root - nothing to validate.")
        return 0

    errors: list[str] = []
    for addon in addons:
        check_manifest(addon, errors)
    check_xml(errors)

    if errors:
        print("Manifest validation failed:\n")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"Validated {len(addons)} addon(s): {', '.join(a.name for a in addons)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
