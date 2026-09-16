#!/usr/bin/env python3
"""Fail when a module's source changed but its manifest version did not.

Odoo.sh upgrades a module on a production push only when the manifest version
is higher than the version recorded in the database. Ship changed code under an
unchanged version and the build restarts with the new Python loaded but the
schema untouched: fields exist in the registry with no column behind them, and
the first read raises

    psycopg2.errors.UndefinedColumn: column account_move.c2p_building_id
    does not exist

which is what happened in production on 2026-09-16 after the underwriting
change added fields and models under an unchanged 19.0.1.0.0.

Nothing in `ruff`, the manifest validator or the install job can see this: the
code is correct, the module installs cleanly into an empty database, and every
test passes. It only breaks when upgrading a database that already holds the
previous version - which is every real deployment.

Usage:
    python tools/check_version_bumps.py [--base <ref>]

The base defaults to $GITHUB_BASE_REF (set on pull requests), then origin/main.
Requires enough git history to read the base; in CI, checkout with
fetch-depth: 0.
"""

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NON_ADDON_DIRS = {".git", ".github", "conf", "docs", "tools", ".ruff_cache"}


def git(*args, check=True):
    result = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def parse_version(text):
    """Pull the version out of a manifest's source without importing it."""
    try:
        manifest = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None
    return manifest.get("version") if isinstance(manifest, dict) else None


def version_tuple(version):
    try:
        return tuple(int(p) for p in version.split("."))
    except (AttributeError, ValueError):
        return None


def addons():
    return sorted(
        p.name
        for p in REPO.iterdir()
        if p.is_dir() and p.name not in NON_ADDON_DIRS and (p / "__manifest__.py").is_file()
    )


def exists(ref):
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def resolve_base(explicit):
    """An explicit --base that cannot be resolved is an error, never a silent
    fall back to main: a typo there would pass the check green while comparing
    against the wrong thing."""
    if explicit:
        for candidate in (explicit, f"origin/{explicit}") if "/" not in explicit else (explicit,):
            if exists(candidate):
                return candidate
        raise SystemExit(f"--base {explicit!r} does not resolve to a commit.")

    for ref in (os.environ.get("GITHUB_BASE_REF"), "origin/main", "main"):
        if not ref:
            continue
        for candidate in (ref, f"origin/{ref}") if "/" not in ref else (ref,):
            if exists(candidate):
                return candidate
    return None


def version_at(ref, addon):
    text = git("show", f"{ref}:{addon}/__manifest__.py", check=False)
    return parse_version(text) if text else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="ref to compare against (default: $GITHUB_BASE_REF, then origin/main)")
    args = ap.parse_args(argv)

    base = resolve_base(args.base)
    if base is None:
        print("! no base ref to compare against - skipping the version check.")
        print("  In CI, check out with fetch-depth: 0 so the base branch is available.")
        return 0

    merge_base = git("merge-base", "HEAD", base, check=False) or base
    changed = git("diff", "--name-only", f"{merge_base}...HEAD").splitlines()

    problems = []
    checked = []
    for addon in addons():
        touched = [f for f in changed if f.startswith(f"{addon}/")]
        if not touched:
            continue

        now = parse_version((REPO / addon / "__manifest__.py").read_text(encoding="utf-8"))
        before = version_at(merge_base, addon)
        if before is None:
            checked.append(f"  {addon}: new module at {now}")
            continue

        new_t, old_t = version_tuple(now), version_tuple(before)
        if new_t is None:
            problems.append(f"{addon}: version {now!r} is not a dotted number")
        elif new_t == old_t:
            files = ", ".join(sorted(touched)[:3]) + (" ..." if len(touched) > 3 else "")
            problems.append(
                f"{addon}: {len(touched)} file(s) changed but version is still {before} "
                f"- an Odoo.sh deploy will NOT upgrade it, so any schema change is "
                f"left unapplied.\n      changed: {files}"
            )
        elif new_t < old_t:
            problems.append(f"{addon}: version went backwards, {before} -> {now}")
        else:
            checked.append(f"  {addon}: {before} -> {now}, {len(touched)} file(s) changed")

    if checked:
        print(f"Version check against {base}:")
        for line in checked:
            print(line)

    if problems:
        print("\nVersion bump missing:")
        for p in problems:
            print(f"  ! {p}")
        print(
            "\nBump the manifest version: 19.0.<major>.<minor>.<patch>, the last "
            "segment for a fix, the middle one for new behaviour. A data-only or "
            "comment-only change still needs one if it must reach an existing database."
        )
        return 1

    if not checked:
        print(f"Version check against {base}: no addon source changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
