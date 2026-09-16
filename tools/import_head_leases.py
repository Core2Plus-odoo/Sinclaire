#!/usr/bin/env python3
"""Create c2p.head.lease records from a CSV of signed underwriting agreements.

A head lease is a commitment to pay a landlord real money whether or not the
building is let, and every margin, coverage and break-even figure on the
dashboard is computed against it. Nothing here infers one: the numbers come
from the signed agreement, typed into the CSV by someone who has read it.

    cp tools/head_leases_template.csv myleases.csv   # fill it in
    ODOO_URL=... ODOO_DB=... ODOO_PWD=... python3 tools/import_head_leases.py myleases.csv

That is a DRY RUN: it resolves every row, reports what it would do and what it
cannot, and writes nothing. Add --commit once the report looks right.

Idempotent: a head lease is matched on (building, date_start) and updated
rather than duplicated, so a corrected CSV can be re-run.

CSV columns
    building_code     required   c2p.building.code, e.g. MKH
    landlord          optional   partner name; defaults to the building's owner
    date_start        required   YYYY-MM-DD
    date_end          optional   defaults to one year less a day from the start
    annual_amount     required   what we owe the landlord for the year
    cheque_count      optional   1, 2, 3, 4, 6 or 12; defaults to 4
    security_deposit  optional
    ejari_no          optional
    ejari_date        optional
    state             optional   draft (default) or active

Only `active` head leases are counted by the dashboard and only they are
checked for overlap, so import as draft, read the figures, then activate.
"""

import argparse
import csv
import os
import sys
import xmlrpc.client
from datetime import date
from datetime import datetime
from datetime import timedelta

CHEQUE_COUNTS = {"1", "2", "3", "4", "6", "12"}
STATES = {"draft", "active"}
COLUMNS = (
    "building_code",
    "landlord",
    "date_start",
    "date_end",
    "annual_amount",
    "cheque_count",
    "security_deposit",
    "ejari_no",
    "ejari_date",
    "state",
)


def connect():
    url = os.environ["ODOO_URL"]
    db = os.environ["ODOO_DB"]
    user = os.environ.get("ODOO_USER", "admin")
    pwd = os.environ["ODOO_PWD"]
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, pwd, {})
    if not uid:
        raise SystemExit("Authentication failed - check ODOO_USER and ODOO_PWD (use an API key).")
    proxy = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    return db, uid, pwd, proxy


class Odoo:
    def __init__(self):
        self.db, self.uid, self.pwd, self.proxy = connect()
        companies = self.call("res.company", "search_read", [], fields=["name"])
        if not companies:
            raise SystemExit("No companies visible - check ODOO_DB and credentials.")
        self.ctx = {"allowed_company_ids": [c["id"] for c in companies]}

    def call(self, model, method, *args, **kw):
        kw.setdefault("context", getattr(self, "ctx", {}))
        try:
            return self.proxy.execute_kw(self.db, self.uid, self.pwd, model, method, list(args), kw)
        except xmlrpc.client.Fault as exc:
            # Odoo 19 action methods often return None and the XML-RPC
            # marshaller rejects it even though the call itself succeeded.
            if "cannot marshal None" in str(exc):
                return None
            raise

    def one(self, model, domain, fields=None):
        rows = self.call(model, "search_read", domain, fields=fields or ["id"], limit=1)
        return rows[0] if rows else None


def parse_date(value, field, row_no, errors):
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"row {row_no}: {field} {value!r} is not a YYYY-MM-DD date")
        return None


def parse_amount(value, field, row_no, errors, required=True):
    raw = value.strip().replace(",", "")
    if not raw:
        if required:
            errors.append(f"row {row_no}: {field} is required")
            return None
        return 0.0
    try:
        amount = float(raw)
    except ValueError:
        errors.append(f"row {row_no}: {field} {value!r} is not a number")
        return None
    if amount < 0 or (required and amount == 0):
        errors.append(f"row {row_no}: {field} must be greater than zero, got {amount:,.2f}")
        return None
    return amount


def one_year_less_a_day(start):
    """The Dubai convention: a 1 Jan start ends 31 Dec, not 31 Dec minus one.

    Subtracting the day last means a start on the 1st rolls back into the
    previous month correctly, and 29 Feb falls back to 28 Feb in a common year
    rather than raising.
    """
    try:
        anniversary = date(start.year + 1, start.month, start.day)
    except ValueError:  # 29 Feb -> 28 Feb
        anniversary = date(start.year + 1, start.month, start.day - 1)
    return anniversary - timedelta(days=1)


def read_rows(path):
    """Parse and validate the CSV without touching Odoo."""
    errors = []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in ("building_code", "date_start", "annual_amount") if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{path}: missing required column(s): {', '.join(missing)}")
        unknown = [c for c in (reader.fieldnames or []) if c not in COLUMNS]
        if unknown:
            print(f"! ignoring unrecognised column(s): {', '.join(unknown)}")

        for row_no, raw in enumerate(reader, start=2):
            row = {k: (raw.get(k) or "").strip() for k in COLUMNS}
            if not any(row.values()):
                continue
            code = row["building_code"]
            if not code:
                errors.append(f"row {row_no}: building_code is required")
                continue
            if not row["date_start"] or not row["annual_amount"]:
                errors.append(f"row {row_no}: {code} has no date_start or annual_amount - fill it in or delete the row")
                continue

            start = parse_date(row["date_start"], "date_start", row_no, errors)
            end = parse_date(row["date_end"], "date_end", row_no, errors) if row["date_end"] else None
            if start and not row["date_end"]:
                end = one_year_less_a_day(start)
            if start and end and end <= start:
                errors.append(f"row {row_no}: {code} ends {end}, on or before its start {start}")

            amount = parse_amount(row["annual_amount"], "annual_amount", row_no, errors)
            deposit = parse_amount(row["security_deposit"], "security_deposit", row_no, errors, required=False)

            cheques = row["cheque_count"] or "4"
            if cheques not in CHEQUE_COUNTS:
                errors.append(f"row {row_no}: cheque_count {cheques!r} is not one of {sorted(CHEQUE_COUNTS, key=int)}")

            state = (row["state"] or "draft").lower()
            if state not in STATES:
                errors.append(f"row {row_no}: state {state!r} must be draft or active")

            ejari_date = parse_date(row["ejari_date"], "ejari_date", row_no, errors) if row["ejari_date"] else None

            rows.append(
                {
                    "row_no": row_no,
                    "code": code,
                    "landlord": row["landlord"],
                    "date_start": start,
                    "date_end": end,
                    "annual_amount": amount,
                    "cheque_count": cheques,
                    "security_deposit": deposit or 0.0,
                    "ejari_no": row["ejari_no"],
                    "ejari_date": ejari_date,
                    "state": state,
                }
            )

    seen = {}
    for row in rows:
        key = (row["code"], row["date_start"])
        if key in seen:
            errors.append(
                f"row {row['row_no']}: {row['code']} starting {row['date_start']} also appears on row {seen[key]}"
            )
        seen[key] = row["row_no"]

    return rows, errors


def resolve(odoo, rows):
    """Turn building codes and landlord names into ids."""
    errors = []
    resolved = []
    for row in rows:
        building = odoo.one("c2p.building", [("code", "=", row["code"])], ["id", "name", "owner_id", "company_id"])
        if not building:
            errors.append(f"row {row['row_no']}: no building with code {row['code']!r} - import the buildings first")
            continue

        if row["landlord"]:
            partner = odoo.one("res.partner", [("name", "=", row["landlord"])], ["id", "name"])
            if not partner:
                errors.append(f"row {row['row_no']}: landlord {row['landlord']!r} not found - check the partner name")
                continue
            landlord_id, landlord_name = partner["id"], partner["name"]
        elif building["owner_id"]:
            landlord_id, landlord_name = building["owner_id"][0], building["owner_id"][1]
        else:
            errors.append(f"row {row['row_no']}: {row['code']} has no owner, so landlord cannot be left blank")
            continue

        row = dict(row, building=building, landlord_id=landlord_id, landlord_name=landlord_name)
        resolved.append(row)
    return resolved, errors


def vals_for(row):
    vals = {
        "building_id": row["building"]["id"],
        "landlord_id": row["landlord_id"],
        "date_start": row["date_start"].isoformat(),
        "date_end": row["date_end"].isoformat(),
        "annual_amount": row["annual_amount"],
        "cheque_count": row["cheque_count"],
        "security_deposit": row["security_deposit"],
        "state": row["state"],
    }
    if row["ejari_no"]:
        vals["ejari_no"] = row["ejari_no"]
    if row["ejari_date"]:
        vals["ejari_date"] = row["ejari_date"].isoformat()
    if row["building"].get("company_id"):
        vals["company_id"] = row["building"]["company_id"][0]
    return vals


def check_overlaps(odoo, rows):
    """Report clashes before writing, so an active row fails on the report
    rather than half way through the import."""
    problems = []
    for row in rows:
        if row["state"] != "active":
            continue
        clash = odoo.call(
            "c2p.head.lease",
            "search_read",
            [
                ("building_id", "=", row["building"]["id"]),
                ("state", "=", "active"),
                ("date_start", "<=", row["date_end"].isoformat()),
                ("date_end", ">=", row["date_start"].isoformat()),
            ],
            fields=["name", "date_start", "date_end"],
            limit=1,
        )
        if clash and clash[0]["date_start"] != row["date_start"].isoformat():
            c = clash[0]
            problems.append(
                f"row {row['row_no']}: {row['code']} is already underwritten "
                f"{c['date_start']}..{c['date_end']} by {c['name']}"
            )
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", help="CSV of signed head leases; see tools/head_leases_template.csv")
    ap.add_argument("--commit", action="store_true", help="actually write (default is a dry run)")
    args = ap.parse_args(argv)

    rows, errors = read_rows(args.csv_path)
    if not rows and not errors:
        raise SystemExit(f"{args.csv_path}: no rows with a date_start and annual_amount - nothing to import.")

    odoo = Odoo()
    rows, resolve_errors = resolve(odoo, rows)
    errors += resolve_errors
    errors += check_overlaps(odoo, rows)

    creates, updates = [], []
    for row in rows:
        existing = odoo.one(
            "c2p.head.lease",
            [("building_id", "=", row["building"]["id"]), ("date_start", "=", row["date_start"].isoformat())],
            ["id", "name"],
        )
        (updates if existing else creates).append((row, existing))

    print(f"\n{args.csv_path}: {len(rows)} row(s) resolved, {len(creates)} to create, {len(updates)} to update")
    print("-" * 78)
    for row, existing in creates + updates:
        cost = row["annual_amount"]
        n = int(row["cheque_count"])
        verb = f"update {existing['name']}" if existing else "create"
        print(
            f"  {row['code']:<5} {row['date_start']}..{row['date_end']}  "
            f"{cost:>12,.0f} in {n:>2} x {cost / n:>10,.0f}  "
            f"{row['state']:<6} {row['landlord_name']}  [{verb}]"
        )

    if errors:
        print("\nPROBLEMS - nothing was written:")
        for e in errors:
            print(f"  ! {e}")
        return 1

    if not args.commit:
        print("\nDry run. Re-run with --commit to write these.")
        return 0

    created = updated = 0
    for row, existing in creates + updates:
        vals = vals_for(row)
        if existing:
            odoo.call("c2p.head.lease", "write", [existing["id"]], vals)
            updated += 1
        else:
            odoo.call("c2p.head.lease", "create", vals)
            created += 1

    print(f"\nWrote {created} new and {updated} updated head lease(s).")
    total = sum(r["annual_amount"] for r, _ in creates + updates)
    print(f"Committed to landlords across these agreements: {total:,.0f}")
    print("Check the dashboard: coverage below 1.0 on any building means it is letting below its head lease cost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
