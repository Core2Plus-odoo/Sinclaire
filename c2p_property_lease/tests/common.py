"""Shared test helpers.

This exists because BR-027 made the same seven fields necessary in three
different fixtures across two modules, and a fourth copy was about to be
written. Copied fixture setup drifts: one copy gets a new required field and
the others are fixed later, one failing test at a time, by whoever next runs
the suite.

These helpers build records that satisfy the gates rather than records that
bypass them, which is the point. A fixture that sidesteps a control tests the
world as it is not.
"""

from datetime import date


def building_vals(env, code, name=None, **kw):
    """A building complete enough to carry an active head lease.

    BR-021 and BR-027: without the plot and municipality references no head
    lease over this building can be activated, because a building nobody can
    identify to the municipality is one whose tenancies cannot be registered.
    """
    plan = env["account.analytic.plan"].search([], limit=1) or env["account.analytic.plan"].create(
        {"name": "Test Properties"}
    )
    vals = {
        "name": name or f"{code} Tower",
        "code": code,
        "plot_no": f"{code}-PLOT-{100 + len(code)}",
        "municipality_no": f"{600 + ord(code[0])}-{code}",
        "analytic_account_id": env["account.analytic.account"]
        .create({"name": name or f"{code} Tower", "plan_id": plan.id})
        .id,
    }
    vals.update(kw)
    return vals


def head_lease_vals(env, building, landlord, **kw):
    """A head lease that BR-027 will let you activate.

    Every value here stands for something a signed agreement would say. They
    are not placeholders chosen to satisfy a check: a fixture that fills
    `agreement_ref` with "x" would pass the gate while teaching the reader
    that the field does not matter.
    """
    bank = env["res.partner.bank"].search([("partner_id", "=", landlord.id)], limit=1) or env[
        "res.partner.bank"
    ].create(
        {
            "acc_number": f"AE07 0331 {abs(hash((landlord.id, building.id))) % 10**12:012d}",
            "partner_id": landlord.id,
        }
    )
    vals = {
        "building_id": building.id,
        "landlord_id": landlord.id,
        "date_start": date(2026, 1, 1),
        "date_end": date(2026, 12, 31),
        "annual_amount": 400000.0,
        "cheque_count": "4",
        "agreement_ref": f"HLA-{building.code}-2026",
        "date_signed": date(2025, 12, 10),
        "landlord_bank_id": bank.id,
        "insurance_expiry": date(2027, 6, 30),
        "sublease_permitted": True,
        "contracting_party": "manager",
        # BR-022: tenant cheques are made out to this company unless a test
        # says otherwise. Spelled out rather than left NULL, because NULL
        # here is an unanswered question and this one has an answer.
        "collection_party": "manager",
    }
    vals.update(kw)
    return vals
