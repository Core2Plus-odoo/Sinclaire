#!/usr/bin/env python3
"""Refuse a call to an `action_*` method with a keyword it does not accept.

Written after exactly that cost a CI run: `_set_state` was changed to refuse
Resolved without a result, the tests were updated to call
`action_resolve(result=...)`, and `action_resolve` was never given the
parameter. Five tests died with

    TypeError: C2pTenancyEvent.action_resolve() got an unexpected keyword
    argument 'result'

and nothing local noticed, because no check in this repository executes Python
against the ORM - there is no Odoo in the dev container, so CI is the first
thing that runs any of it. See `docs/project/AUDIT_WAVE0.md` risk R5.

This closes that specific gap statically. It is deliberately narrow:

* Only `action_*` methods, because those are the ones called by name from
  tests, views and other modules, and so the ones where a signature change
  silently breaks a caller.
* Keywords only. Positional arity would need real type inference to know what
  `x.action_foo(a, b)` is bound to, and guessing would produce false positives,
  which is how a checker gets switched off.
* A method name defined more than once contributes the *union* of its
  parameters. Two models may both define `action_resolve` with different
  signatures, and without resolving the receiver's type this cannot tell which
  one a call means. The union still catches the case that matters: a keyword
  no definition anywhere accepts.
* A definition taking `**kwargs` accepts anything, so its name is exempt.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".github", "node_modules"}


def python_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.py") if not any(part in SKIP_DIRS for part in path.parts))


def collect_definitions(trees: dict[Path, ast.Module]) -> tuple[dict[str, set[str]], set[str]]:
    """Every `action_*` definition's accepted keywords, keyed by method name."""
    accepted: dict[str, set[str]] = defaultdict(set)
    wildcard: set[str] = set()
    for tree in trees.values():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("action_"):
                continue
            args = node.args
            names = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
            names.discard("self")
            accepted[node.name] |= names
            if args.kwarg is not None:
                wildcard.add(node.name)
    return accepted, wildcard


def main() -> int:
    trees: dict[Path, ast.Module] = {}
    for path in python_files():
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            print(f"{path}: could not parse ({exc})")
            return 1

    accepted, wildcard = collect_definitions(trees)
    problems: list[str] = []

    for path, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or not func.attr.startswith("action_"):
                continue
            name = func.attr
            if name not in accepted or name in wildcard:
                # Not defined in this repository (an Odoo core action, say), or
                # it takes **kwargs. Either way this check has nothing to say.
                continue
            for keyword in node.keywords:
                if keyword.arg is None:
                    continue  # **expansion; cannot be checked statically
                if keyword.arg not in accepted[name]:
                    allowed = ", ".join(sorted(accepted[name])) or "no keywords"
                    problems.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: "
                        f"{name}(...) passed {keyword.arg!r}, which no definition of "
                        f"{name} accepts (accepted: {allowed})"
                    )

    if problems:
        print("Action keyword check failed:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    calls = sum(
        1
        for tree in trees.values()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.startswith("action_")
    )
    print(f"action keywords: {len(accepted)} action method(s), {calls} call site(s), all keywords accepted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
