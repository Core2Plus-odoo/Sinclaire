#!/usr/bin/env python3
"""Verify the design system's accessibility claims against WCAG 2.1 AA.

The design brief asks for an experience that is "Accessible" and supplies a
palette. Those two things are not automatically compatible, and measuring
showed they are not: five of the brief's eleven colours cannot carry
normal-size text on the brief's own backgrounds, and the colour named
"Secondary Text" is among them - it reaches 4.50:1 on white but only 4.18:1
on the page background it will nearly always be read on.

So _tokens.scss carries two tokens for each affected colour: the brand one
for fills and large numerals, and a darkened one for body copy. This script
is what stops that from being a comment that drifts away from the file. It
parses the real token values out of the SCSS and re-measures every pairing
the design system promises, so the claim stays true or CI goes red.

Thresholds (WCAG 2.1):
  4.5:1  normal text
  3.0:1  large text (>=24px, or >=19px bold) and UI component boundaries

Usage:
    python tools/check_contrast.py

Exits non-zero if any promised pairing falls below its threshold.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOKENS = REPO / "sinclaire_base/static/src/scss/_tokens.scss"

AA_NORMAL = 4.5
AA_LARGE = 3.0


def relative_luminance(hex_colour: str) -> float:
    """WCAG relative luminance of an #RRGGBB colour."""
    raw = hex_colour.lstrip("#")
    channels = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two #RRGGBB colours, 1.0 to 21.0."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def read_tokens(path: Path = TOKENS) -> dict[str, str]:
    """The literal hex values declared in the SCSS, by token name.

    Tokens defined as var() aliases are skipped: this measures real colours,
    and an alias is measured through whatever it points at.
    """
    text = path.read_text(encoding="utf-8")
    return {name: value.upper() for name, value in re.findall(r"(--sin-[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\s*;", text)}


# What the design system promises. Each row is (foreground, background,
# threshold, what it is for). If a row fails, either the token is wrong or
# the promise is - both are worth a red build.
PROMISES = [
    # Body copy on both surfaces.
    ("--sin-text", "--sin-surface", AA_NORMAL, "primary text on a card"),
    ("--sin-text", "--sin-bg", AA_NORMAL, "primary text on the page"),
    ("--sin-text-muted-text", "--sin-surface", AA_NORMAL, "secondary text on a card"),
    ("--sin-text-muted-text", "--sin-bg", AA_NORMAL, "secondary text on the page"),
    # The accessible status text variants, which exist precisely for this.
    ("--sin-teal-text", "--sin-bg", AA_NORMAL, "teal as body text"),
    ("--sin-emerald-text", "--sin-bg", AA_NORMAL, "emerald as body text"),
    ("--sin-amber-text", "--sin-bg", AA_NORMAL, "amber as body text"),
    ("--sin-red-text", "--sin-bg", AA_NORMAL, "critical red as body text"),
    ("--sin-blue", "--sin-bg", AA_NORMAL, "royal blue as body text"),
    ("--sin-navy", "--sin-bg", AA_NORMAL, "navy as body text"),
    ("--sin-navy-deep", "--sin-bg", AA_NORMAL, "deep navy as body text"),
    # Dark text on the tinted status fills - how a badge is built.
    ("--sin-text", "--sin-ok-fill", AA_NORMAL, "text on the success fill"),
    ("--sin-text", "--sin-warn-fill", AA_NORMAL, "text on the warning fill"),
    ("--sin-text", "--sin-critical-fill", AA_NORMAL, "text on the critical fill"),
    ("--sin-text", "--sin-info-fill", AA_NORMAL, "text on the info fill"),
    ("--sin-text", "--sin-neutral-fill", AA_NORMAL, "text on the neutral fill"),
    # Amber is only ever a fill with navy on it.
    ("--sin-text", "--sin-amber", AA_NORMAL, "navy on an amber fill"),
    # Brand colours carrying large numerals only - the KPI figure.
    ("--sin-teal", "--sin-surface", AA_LARGE, "teal as a large KPI numeral"),
    ("--sin-emerald", "--sin-surface", AA_LARGE, "emerald as a large KPI numeral"),
    ("--sin-red", "--sin-surface", AA_LARGE, "critical red as a large KPI numeral"),
    # WCAG 1.4.11: the outline of an interactive control needs 3:1. The
    # decorative divider tokens are deliberately not tested here - see the
    # note beside them in _tokens.scss.
    ("--sin-border-control", "--sin-surface", AA_LARGE, "a control outline on a card"),
    ("--sin-border-control", "--sin-bg", AA_LARGE, "a control outline on the page"),
]

# Colours the system must never use for normal-size text. Asserting the
# failure keeps the rule honest: if someone "fixes" amber by darkening the
# brand token, this fires and the two-token split gets revisited on purpose
# rather than by accident.
NEVER_BODY_TEXT = [
    ("--sin-amber", "--sin-surface", "amber"),
    ("--sin-amber", "--sin-bg", "amber"),
]


def run():
    if not TOKENS.exists():
        return [f"{TOKENS.relative_to(REPO)} is missing"], []
    tokens = read_tokens()
    failures, measured = [], []

    for fg, bg, threshold, what in PROMISES:
        if fg not in tokens or bg not in tokens:
            failures.append(f"{what}: {fg if fg not in tokens else bg} is not defined in _tokens.scss")
            continue
        ratio = contrast(tokens[fg], tokens[bg])
        measured.append((what, tokens[fg], tokens[bg], ratio, threshold))
        if ratio < threshold:
            failures.append(
                f"{what}: {fg} {tokens[fg]} on {bg} {tokens[bg]} is {ratio:.2f}:1, below the {threshold}:1 it needs."
            )

    for token, bg, name in NEVER_BODY_TEXT:
        if token not in tokens or bg not in tokens:
            continue
        ratio = contrast(tokens[token], tokens[bg])
        if ratio >= AA_NORMAL:
            failures.append(
                f"{token} {tokens[token]} now reaches {ratio:.2f}:1 on {bg}. {name} is "
                f"documented as fill-only; if it has been darkened deliberately, update "
                f"_tokens.scss and this rule together."
            )
    return failures, measured


def main():
    failures, measured = run()
    for what, fg, bg, ratio, threshold in measured:
        mark = "ok  " if ratio >= threshold else "FAIL"
        print(f"  {mark} {ratio:5.2f}:1  (needs {threshold})  {fg} on {bg}  - {what}")
    if failures:
        print("\nContrast check failed:\n")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"\ncontrast: {len(measured)} pairing(s) checked, all meet WCAG 2.1 AA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
