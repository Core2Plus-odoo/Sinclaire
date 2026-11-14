#!/usr/bin/env python3
"""Flag unreachable statements in test fixtures.

This exists because of a defect that cost a day. In
c2p_ceo_command_center/tests/test_dashboard.py the lease fixture had been
pasted after `return unit` inside the unit factory:

    unit = cls.env["c2p.unit"].create(vals)
    unit.sudo().action_release()
    return unit
    cls.lease = cls.env["c2p.lease"].create({...})   # never runs
    cls.lease._activate_as_loaded()                  # never runs

So cls.lease never existed and no unit was ever occupied. Nothing failed:
the assertions were all of the form `assertGreaterEqual(count, 1)`, which
any populated database satisfies, so on a CI image carrying demo data the
suite went green while measuring records that had nothing to do with it.

That is the worst failure mode a test suite has - not a red test, but a
green one that is not testing what it claims. Python itself says nothing
about unreachable code, and ruff's own rule for it is preview-only, so this
check is here rather than in the linter.

It reports any statement that can never execute because the statement before
it in the same block always leaves: return, raise, continue or break.

Usage:
    python tools/check_test_hygiene.py [paths...]

Exits non-zero if anything is found.
"""

from __future__ import annotations

import ast
import sys
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Statements after which nothing in the same block can run.
TERMINAL = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _blocks(node: ast.AST):
    """Every statement list hanging off this node.

    Deliberately does NOT walk into `handlers`: ast.walk reaches each
    ExceptHandler itself, and its body comes back through the "body" field
    below. Yielding it here as well reported every finding inside an except
    handler twice.
    """
    for field in ("body", "orelse", "finalbody"):
        block = getattr(node, field, None)
        if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
            yield block


def unreachable_in(tree: ast.AST):
    """(line, what-was-skipped) for every statement that can never run."""
    found = []
    for node in ast.walk(tree):
        for block in _blocks(node):
            for before, after in pairwise(block):
                if isinstance(before, TERMINAL):
                    found.append((after.lineno, type(before).__name__.lower()))
    return found


def check(paths):
    problems = []
    for path in sorted(paths):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            problems.append(f"{path.relative_to(REPO)}: could not parse - {exc}")
            continue
        for lineno, after_what in unreachable_in(tree):
            problems.append(
                f"{path.relative_to(REPO)}:{lineno}: unreachable - the preceding "
                f"`{after_what}` always leaves this block, so nothing below it runs."
            )
    return problems


def test_files():
    return [p for p in REPO.glob("*/tests/*.py") if p.name != "__init__.py"]


def main(argv):
    paths = [Path(a).resolve() for a in argv[1:]] if len(argv) > 1 else test_files()
    problems = check(paths)
    if problems:
        print("Unreachable code found:\n")
        for line in problems:
            print(f"  - {line}")
        print(
            "\nA fixture below a `return` never runs, and tests whose assertions "
            "are loose enough will pass anyway against unrelated data."
        )
        return 1
    print(f"test hygiene: {len(paths)} test file(s) checked, no unreachable code")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
