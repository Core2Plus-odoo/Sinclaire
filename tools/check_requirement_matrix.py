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

DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs"

SUMMARY_ROW = re.compile(r"^\|\s*(Built|Partial|Not started)\s*\|\s*(\d+)\s*\|")

CLASSES = {"Std", "Cfg", "Cus", "Int", "Rep", "Mig", "OoS", "—"}
STATUSES = {"Built", "Partial", "—"}
# Status label in the rows vs. the label used in the summary table.
SUMMARY_LABEL = {"Built": "Built", "Partial": "Partial", "—": "Not started"}

# Both catalogues are contract documents with the same failure mode: an id that
# duplicates, a gap in the sequence, or a summary that has drifted from the
# rows. One spec drives both so a third document costs a line, not a fork.
SPECS = (
    {
        "file": "requirement_response_matrix.md",
        "prefix": "BR",
        "min_columns": 9,
        "class_column": 4,
        # The BRD seeds these in its own §11.1 traceability template.
        "reserved": {"BR-001", "BR-002", "BR-003"},
        "reserved_note": "§11.1 supplies these; they may not be renumbered",
    },
    {
        "file": "report_catalogue.md",
        "prefix": "RPT",
        "min_columns": 4,
        "class_column": None,
        "reserved": set(),
        "reserved_note": "",
    },
)


def check_one(spec):
    """Return (errors, summary line) for one catalogue."""
    path = DOCS / spec["file"]
    if not path.is_file():
        return [], f"{spec['file']}: not present, skipped"

    text = path.read_text(encoding="utf-8")
    row_re = re.compile(rf"^\|\s*\**({spec['prefix']}-\d{{3}})\**\s*\|")
    errors, ids = [], []
    status_counts = collections.Counter()

    for lineno, line in enumerate(text.splitlines(), 1):
        match = row_re.match(line)
        if not match:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rid = match.group(1)
        if len(cells) < spec["min_columns"]:
            errors.append(
                f"{spec['file']} line {lineno}: {rid} has {len(cells)} columns, expected at least {spec['min_columns']}"
            )
            continue

        ids.append(rid)
        if spec["class_column"] is not None:
            cls = cells[spec["class_column"]]
            if cls not in CLASSES:
                errors.append(f"{spec['file']}: {rid} class {cls!r} is not one of {sorted(CLASSES)}")

        status = cells[-1]
        if status not in STATUSES:
            errors.append(f"{spec['file']}: {rid} status {status!r} is not one of {sorted(STATUSES)}")
        else:
            status_counts[SUMMARY_LABEL[status]] += 1

    if not ids:
        return [f"{spec['file']}: no {spec['prefix']}-NNN rows found at all"], ""

    for rid, count in collections.Counter(ids).items():
        if count > 1:
            errors.append(f"{spec['file']}: {rid} appears {count} times; ids must be unique")

    numbers = sorted(int(r.split("-")[1]) for r in set(ids))
    gaps = [n for n in range(1, numbers[-1] + 1) if n not in set(numbers)]
    if gaps:
        errors.append(f"{spec['file']}: gaps in the sequence: " + ", ".join(f"{spec['prefix']}-{n:03d}" for n in gaps))

    missing = spec["reserved"] - set(ids)
    if missing:
        errors.append(
            f"{spec['file']}: reserved ids are missing: "
            + ", ".join(sorted(missing))
            + (f" ({spec['reserved_note']})" if spec["reserved_note"] else "")
        )

    declared = {m.group(1): int(m.group(2)) for line in text.splitlines() if (m := SUMMARY_ROW.match(line))}
    for label, actual in status_counts.items():
        if label not in declared:
            errors.append(f"{spec['file']}: summary table has no row for {label!r}")
        elif declared[label] != actual:
            errors.append(f"{spec['file']}: summary says {label} = {declared[label]}, rows say {actual}")

    total = sum(status_counts.values())
    summary = (
        f"{spec['file']}: {total} entries, {spec['prefix']}-001..{spec['prefix']}-{numbers[-1]:03d}, "
        "no gaps or duplicates\n    " + ", ".join(f"{k} {v}" for k, v in sorted(status_counts.items()))
    )
    return errors, summary


def main():
    all_errors, summaries = [], []
    for spec in SPECS:
        errors, summary = check_one(spec)
        all_errors.extend(errors)
        if summary:
            summaries.append(summary)

    if all_errors:
        print_errors(all_errors)
        return 1

    for line in summaries:
        print(f"  {line}")
    return 0


def print_errors(errors):
    print("Requirement matrix check failed:\n")
    for e in errors:
        print(f"  - {e}")


if __name__ == "__main__":
    sys.exit(main())
