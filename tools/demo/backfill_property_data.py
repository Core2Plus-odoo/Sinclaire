#!/usr/bin/env python3
"""Backfill c2p.building / c2p.unit / c2p.lease from the existing Sinclair demo data.

Run AFTER c2p_property_lease is installed on the Odoo.sh branch:
    ODOO_URL=... ODOO_DB=... ODOO_USER=admin ODOO_PWD=... python3 backfill_property_data.py

Idempotent: existing buildings, units and leases are matched by name and reused.
"""

import base64
import os
import random
import re
import xmlrpc.client
from datetime import date, timedelta

URL = os.environ["ODOO_URL"]
DB = os.environ["ODOO_DB"]
USER = os.environ.get("ODOO_USER", "admin")
PWD = os.environ["ODOO_PWD"]

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
UID = common.authenticate(DB, USER, PWD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)
# Everything environment-specific is configurable. Defaults match the Sinclair
# database, but nothing here assumes a fixed id.
TENANT_TAG = os.environ.get("TENANT_TAG", "Tenant")
PDC_JOURNAL_CODE = os.environ.get("PDC_JOURNAL_CODE", "PDCR")
COMPANY_NAME = os.environ.get("ODOO_COMPANY", "New Sinclair Property Management LLC")


def _resolve_companies():
    """Operate across every company the user may see, and put the property
    company first so records land in it rather than in an arbitrary default."""
    companies = models.execute_kw(DB, UID, PWD, "res.company", "search_read", [[]], {"fields": ["name"]})
    if not companies:
        raise SystemExit("No companies found - check ODOO_DB and credentials.")
    ids = [c["id"] for c in companies]
    match = next((c for c in companies if c["name"] == COMPANY_NAME), None)
    if match is None:
        match = companies[0]
        print(
            f"! company {COMPANY_NAME!r} not found; using {match['name']!r} "
            f"(id {match['id']}). Set ODOO_COMPANY to choose another."
        )
    return match["id"], ids


COMPANY_ID, ALL_COMPANY_IDS = _resolve_companies()
CTX = {"allowed_company_ids": ALL_COMPANY_IDS}
print(f"company: {COMPANY_NAME} (id {COMPANY_ID}); visible companies: {ALL_COMPANY_IDS}")


def ex(model, method, *args, **kw):
    kw.setdefault("context", CTX)
    return models.execute_kw(DB, UID, PWD, model, method, list(args), kw)


def one(model, domain, fields=None):
    r = ex(model, "search_read", domain, fields=fields or ["id"], limit=1)
    return r[0] if r else None


def get_or_create(model, domain, vals):
    rec = one(model, domain)
    if rec:
        return rec["id"]
    return ex(model, "create", vals)


# ---------------------------------------------------------------- buildings
BUILDINGS = [
    {
        "name": "Al Mankhool Residence – Bur Dubai",
        "code": "MKH",
        "community": "Al Mankhool",
        "owner": "Rashid Bin Hamad Real Estate Holdings",
        "fee": 5.0,
    },
    {
        "name": "Karama Court – Al Karama",
        "code": "KRM",
        "community": "Al Karama",
        "owner": "Abdulla Al Mansoori Properties",
        "fee": 5.0,
    },
    {
        "name": "Warqa Gardens – Al Warqa",
        "code": "WRQ",
        "community": "Al Warqa",
        "owner": "Abdulla Al Mansoori Properties",
        "fee": 6.0,
    },
]

building_ids = {}
for b in BUILDINGS:
    owner = one("res.partner", [("name", "=", b["owner"])])
    analytic = one("account.analytic.account", [("name", "=", b["name"])])
    bid = get_or_create(
        "c2p.building",
        [("code", "=", b["code"])],
        {
            "name": b["name"],
            "code": b["code"],
            "community": b["community"],
            "city": "Dubai",
            "owner_id": owner and owner["id"],
            "management_fee_pct": b["fee"],
            "analytic_account_id": analytic and analytic["id"],
            "company_id": COMPANY_ID,
        },
    )
    building_ids[b["code"]] = bid
print("buildings:", building_ids)

# ---------------------------------------------------------------- units + leases
# Tenant records carry "Tenant of MKH-201 – Al Mankhool Residence – Bur Dubai" in the notes.
# Company 2 has no PDC journal, so this must not be assumed to exist.
pdc_journal = one("account.journal", [("code", "=", PDC_JOURNAL_CODE)], fields=["id", "name"])
pdc_journal_exists = bool(pdc_journal)
if not pdc_journal_exists:
    print(
        f"! no journal with code {PDC_JOURNAL_CODE!r}: cheques will not be attached "
        "to leases. Set PDC_JOURNAL_CODE if it is named differently."
    )

tenants = ex("res.partner", "search_read", [("category_id.name", "=", TENANT_TAG)], fields=["name", "comment"])
if not tenants:
    print(f"! no partners tagged {TENANT_TAG!r} - nothing to backfill. Check TENANT_TAG.")

TYPE_BY_SUFFIX = {"1": "studio", "2": "1br", "3": "2br", "4": "3br", "5": "2br", "6": "1br"}
RENT_BAND = {"studio": (38000, 52000), "1br": (55000, 78000), "2br": (85000, 125000), "3br": (120000, 170000)}
BANKS = ["ENBD", "Mashreq", "ADCB", "FAB", "RAKBANK"]
CHEQUES = ["1", "2", "4", "6", "12"]
random.seed(11)
today = date.today()

created_units = created_leases = attached_cheques = 0
unmatched_notes: list[str] = []
unknown_building: list[tuple[str, str]] = []
already_leased: list[str] = []
for t in tenants:
    m = re.search(r"([A-Z]{3})-(\d{3})", t.get("comment") or "")
    if not m:
        unmatched_notes.append(t["name"])
        continue
    code, unit_no = m.group(1), m.group(2)
    bid = building_ids.get(code)
    if not bid:
        unknown_building.append((t["name"], code))
        continue
    unit_name = f"{code}-{unit_no}"
    utype = TYPE_BY_SUFFIX.get(unit_no[-1], "1br")
    low, high = RENT_BAND[utype]

    unit = one("c2p.unit", [("name", "=", unit_name), ("building_id", "=", bid)])
    if unit:
        uid_ = unit["id"]
    else:
        uid_ = ex(
            "c2p.unit",
            "create",
            {
                "name": unit_name,
                "building_id": bid,
                "unit_type": utype,
                "floor": unit_no[0],
                "area_sqft": round(random.uniform(420, 1650)),
                "market_rent": round(random.uniform(low, high), -2),
                "rera_index_low": low,
                "rera_index_high": high,
                "dewa_no": f"{random.randint(2000000, 2999999)}",
            },
        )
        created_units += 1

    if one("c2p.lease", [("unit_id", "=", uid_), ("state", "=", "active")]):
        already_leased.append(unit_name)
        continue

    # Align the lease with the tenant's existing rent subscription where one exists.
    sub = one(
        "sale.order",
        [("partner_id", "=", t["id"]), ("subscription_state", "!=", False)],
        fields=["id", "plan_id", "amount_total", "date_order"],
    )
    start = today - timedelta(days=random.randint(30, 330))
    end = start + timedelta(days=364)
    instal = (sub or {}).get("amount_total") or round(random.uniform(low, high) / 4, 2)
    plan_name = ((sub or {}).get("plan_id") or [0, ""])[1]
    cheques = (
        "12"
        if "12" in plan_name
        else "6"
        if "6" in plan_name
        else "4"
        if "4" in plan_name
        else "2"
        if "2" in plan_name
        else "1"
        if "Annual" in plan_name
        else random.choice(CHEQUES)
    )
    annual = round(instal * int(cheques), 2)

    lease_id = ex(
        "c2p.lease",
        "create",
        {
            "tenant_id": t["id"],
            "unit_id": uid_,
            "date_start": start.isoformat(),
            "date_end": end.isoformat(),
            "annual_rent": annual,
            "cheque_count": cheques,
            "security_deposit": round(annual * 0.05, 2),
            "commission": round(annual * 0.05, 2),
            "ejari_no": f"E-{random.randint(100000, 999999)}",
            "ejari_date": (start + timedelta(days=3)).isoformat(),
            "subscription_id": (sub or {}).get("id"),
            "company_id": COMPANY_ID,
        },
    )
    ex("c2p.lease", "action_activate", [lease_id])
    created_leases += 1

    # Attach the existing PDC payments for this tenant to the lease.
    pays = (
        ex(
            "account.payment",
            "search",
            [("partner_id", "=", t["id"]), ("journal_id.code", "=", PDC_JOURNAL_CODE)],
        )
        if pdc_journal_exists
        else []
    )
    for pid in pays:
        attached_cheques += 1
        p = one("account.payment", [("id", "=", pid)], fields=["memo", "date", "state"])
        memo = p.get("memo") or ""
        cheque = (re.search(r"PDC (\d+)", memo) or [None, f"{random.randint(300000, 799999)}"])[1]
        bank = next((b for b in BANKS if b in memo), random.choice(BANKS))
        state = "bounced" if "RETURN" in memo.upper() else "cleared" if p["state"] == "paid" else "held"
        ex(
            "account.payment",
            "write",
            [pid],
            {
                "lease_id": lease_id,
                "cheque_no": cheque,
                "cheque_bank": bank,
                "maturity_date": p["date"],
                "pdc_state": state,
            },
        )

# ---------------------------------------------------------------- reconciliation
# Control totals, not "looks right": every tenant is either converted into a
# lease or accounted for by name.
print()
print("--- backfill reconciliation ---")
print(f"tenants read                 : {len(tenants)}")
print(f"units created                : {created_units}")
print(f"leases created               : {created_leases}")
print(f"cheques attached             : {attached_cheques}")
print(f"skipped, no unit in notes    : {len(unmatched_notes)}")
print(f"skipped, unknown building    : {len(unknown_building)}")
print(f"skipped, unit already leased : {len(already_leased)}")
accounted = created_leases + len(unmatched_notes) + len(unknown_building) + len(already_leased)
print(f"accounted for                : {accounted} of {len(tenants)}")
if accounted != len(tenants):
    print("! tenant count does not reconcile - investigate before relying on this data")
for name in unmatched_notes:
    print(f"  no unit reference in notes: {name}")
for name, code in unknown_building:
    print(f"  unknown building {code}: {name}")

# A few deliberately vacant units so occupancy is not 100%.
for code, extra in (("MKH", ["MKH-705", "MKH-706"]), ("KRM", ["KRM-305"]), ("WRQ", ["WRQ-401"])):
    for name in extra:
        get_or_create(
            "c2p.unit",
            [("name", "=", name)],
            {
                "name": name,
                "building_id": building_ids[code],
                "unit_type": "1br",
                "floor": name.split("-")[1][0],
                "area_sqft": 780,
                "market_rent": 68000,
                "rera_index_low": 55000,
                "rera_index_high": 78000,
                "state": "vacant",
            },
        )

print("done")


# ---------------------------------------------------------------- artwork
# Illustrations are generated flat artwork shipped alongside this script — no stock photos.
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_images")


def _b64(fname):
    path = os.path.join(IMG_DIR, fname)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode()


BUILDING_ART = {"MKH": "bld_mankhool.png", "KRM": "bld_karama.png", "WRQ": "bld_warqa.png"}
UNIT_ART = {"studio": "unit_studio.png", "1br": "unit_1br.png", "2br": "unit_2br.png", "3br": "unit_3br.png"}

for code, fname in BUILDING_ART.items():
    data = _b64(fname)
    if data and building_ids.get(code):
        ex("c2p.building", "write", [building_ids[code]], {"image_1920": data})
print("building artwork applied")

for utype, fname in UNIT_ART.items():
    data = _b64(fname)
    if not data:
        continue
    unit_ids = ex("c2p.unit", "search", [("unit_type", "=", utype), ("image_1920", "=", False)])
    for i in range(0, len(unit_ids), 20):
        ex("c2p.unit", "write", unit_ids[i : i + 20], {"image_1920": data})
    print(f"units {utype}: {len(unit_ids)} images applied")

print("artwork done")
