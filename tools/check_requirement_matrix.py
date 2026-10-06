#!/usr/bin/env python3
"""Keep docs/requirement_response_matrix.md internally honest.

The matrix is a contract document: BRD §9.1 makes it the evidence of scope
agreement, and §11.1 fixes the BR-NNN identifier scheme. A duplicated ID, a
gap in the sequence, or a summary count that no longer matches the rows is not
a cosmetic problem — it is a traceability failure in the deliverable the client
evaluates the proposal against.

This project has now had three defects of exactly one shape: two lists that
must agree, with nothing asserting that they do (the sample-loader COUNTERS
KeyError, the tenant-lease cheque schedule, and the hand-written counts in this
matrix's own summary). So the counts are derived here rather than typed.

Checks:
  * every requirement row carries a well-formed BR-NNN id
  * no duplicate ids
  * no gaps in the sequence
  * BR-001..BR-003 are present (the BRD supplies these itself, §11.1)
  * the summary table's counts equal the rows actually present
  * every Class and Status value is one of the documented ones

Usage: python tools/check_requirement_matrix.py
"""

import collections
import pathlib
import re
import sys

MATRIX = pathlib.Path(__file__).resolve().parents[1] / "docs" / "requirement_response_matrix.md"

ROW = re.compile(r"^\|\s*\**(BR-\d{3})\**\s*\|")
SUMMARY_ROW = re.compile(r"^\|\s*(Built|Partial|Not started)\s*\|\s*(\d+)\s*\|")

CLASSES = {"Std", "Cfg", "Cus", "Int", "Rep", "Mig", "OoS", "—"}
STATUSES = {"Built", "Partial", "—"}
# The BRD seeds these in its own §11.1 traceability template.
BRD_OWN = {"BR-001", "BR-002", "BR-003"}
# Status label in the rows vs. the label used in the summary table.
SUMMARY_LABEL = {"Built": "Built", "Partial": "Partial", "—": "Not started"}


def main():
    if not MATRIX.is_file():
        print(f"{MATRIX} not found - nothing to check.")
        return 0

    text = MATRIX.read_text(encoding="utf-8")
    errors = []
    ids = []
    status_counts = collections.Counter()

    for lineno, line in enumerate(text.splitlines(), 1):
        match = ROW.match(line)
        if not match:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            errors.append(f"line {lineno}: {match.group(1)} has {len(cells)} columns, expected 9")
            continue

        rid = match.group(1)
        ids.append(rid)
        cls, status = cells[4], cells[-1]
        if cls not in CLASSES:
            errors.append(f"{rid}: class {cls!r} is not one of {sorted(CLASSES)}")
        if status not in STATUSES:
            errors.append(f"{rid}: status {status!r} is not one of {sorted(STATUSES)}")
        else:
            status_counts[SUMMARY_LABEL[status]] += 1

    if not ids:
        errors.append("no BR-NNN requirement rows found at all")
        print_errors(errors)
        return 1

    for rid, count in collections.Counter(ids).items():
        if count > 1:
            errors.append(f"{rid} appears {count} times; ids must be unique")

    numbers = sorted(int(r.split("-")[1]) for r in set(ids))
    gaps = [n for n in range(1, numbers[-1] + 1) if n not in set(numbers)]
    if gaps:
        errors.append("gaps in the sequence: " + ", ".join(f"BR-{n:03d}" for n in gaps))

    missing_brd = BRD_OWN - set(ids)
    if missing_brd:
        errors.append(
            "the BRD's own ids are missing: "
            + ", ".join(sorted(missing_brd))
            + " (§11.1 supplies these; they may not be renumbered)"
        )

    declared = {m.group(1): int(m.group(2)) for line in text.splitlines() if (m := SUMMARY_ROW.match(line))}
    for label, actual in status_counts.items():
        if label not in declared:
            errors.append(f"summary table has no row for {label!r}")
        elif declared[label] != actual:
            errors.append(f"summary says {label} = {declared[label]}, rows say {actual}")

    if errors:
        print_errors(errors)
        return 1

    total = sum(status_counts.values())
    print(f"requirement matrix: {total} requirements, BR-001..BR-{numbers[-1]:03d}, no gaps or duplicates")
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(status_counts.items())))
    return 0


def print_errors(errors):
    print("Requirement matrix check failed:\n")
    for e in errors:
        print(f"  - {e}")


if __name__ == "__main__":
    sys.exit(main())
