"""Sample portfolio generator.

Demo data in `demo/` only loads into a database created with demo enabled,
which a real client database never is. So the sample portfolio lives here as
code instead: the demo hook calls it when demo is on, and Configuration ->
Load Sample Portfolio calls the same code on demand in any database. One
source of truth, so the two paths cannot drift.

Everything is idempotent and keyed on the building code, so re-running adds
nothing.
"""

import logging
import random
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api
from odoo import fields
from odoo import models

_logger = logging.getLogger(__name__)

LANDLORDS = [
    ("Rashid Bin Hamad Real Estate Holdings", 0),
    ("Abdulla Al Mansoori Properties", 1),
    ("Horizon Gulf Investments LLC", 2),
]
# code, name, community, landlord index, head-lease cost as a share of market
# rent, floors, units/floor, commercial ground floor.
#
# The cost share is what decides whether a deal works. DEI is deliberately
# underwritten too keenly, so the portfolio has one building below cost and the
# dashboard has something real to flag.
BUILDINGS = [
    ("MKH", "Al Mankhool Residence", "Al Mankhool", 0, 0.72, 5, 4, False),
    ("KRM", "Karama Court", "Al Karama", 1, 0.75, 4, 4, False),
    ("WRQ", "Warqa Gardens", "Al Warqa", 1, 0.70, 4, 4, True),
    ("JLT", "Lake Point Tower", "Jumeirah Lakes Towers", 2, 0.78, 5, 4, True),
    ("DSL", "Silicon Heights", "Dubai Silicon Oasis", 2, 0.74, 4, 4, False),
    ("DEI", "Deira Pearl", "Deira", 0, 0.92, 3, 4, True),
]
SLOT_TYPE = {1: "studio", 2: "1br", 3: "2br", 4: "3br"}
BAND = {
    "studio": (38000, 52000),
    "1br": (55000, 78000),
    "2br": (85000, 125000),
    "3br": (120000, 170000),
    "shop": (90000, 160000),
    "office": (80000, 140000),
}
AREA = {
    "studio": (420, 560),
    "1br": (700, 950),
    "2br": (1100, 1400),
    "3br": (1500, 1900),
    "shop": (600, 1100),
    "office": (700, 1200),
}
FIRST = [
    "Omar",
    "Fatima",
    "Yusuf",
    "Aisha",
    "Bilal",
    "Noor",
    "Khalid",
    "Sara",
    "Imran",
    "Layla",
    "Tariq",
    "Huda",
    "Zain",
    "Mariam",
    "Faisal",
    "Rania",
    "Adnan",
    "Salma",
    "Nabil",
    "Dina",
    "Hassan",
    "Amal",
    "Rami",
    "Yasmin",
    "Kareem",
    "Leena",
    "Sami",
    "Nadia",
    "Jamal",
    "Hala",
    "Waleed",
    "Reem",
    "Ammar",
    "Iman",
    "Ziad",
    "Lubna",
]
LAST = [
    "Al Rashid",
    "Haddad",
    "Nasser",
    "Khoury",
    "Siddiqui",
    "Farouk",
    "Mansour",
    "Darwish",
    "Qureshi",
    "Bakr",
    "Aziz",
    "Halabi",
    "Chaudhry",
    "Salem",
    "Barakat",
]
COMPANIES = [
    "Gulf Tech Trading LLC",
    "Crescent Logistics FZE",
    "Nova Retail Group",
    "Marina Consulting DMCC",
    "Zenith Foodstuff LLC",
]
BANKS = ["ENBD", "Mashreq", "ADCB", "FAB", "RAKBANK"]
VACANCY_RATE = 0.15
SEED = 20260914

# Every counter the summary reports. defaultdict keeps a missing key from
# raising mid-run; seeding from this tuple keeps the summary stable so callers
# can read a counter that happened to create nothing. A test asserts the two
# stay in step.
COUNTERS = (
    "buildings",
    "units",
    "leases",
    "head_leases",
    "cheques",
    "landlord_cheques",
    "invoices",
    "facilities",
)


class SamplePortfolio(models.AbstractModel):
    _name = "c2p.sample.portfolio"
    _description = "Sample Portfolio Generator"

    @staticmethod
    def _rng(*parts):
        """Deterministic per-key RNG.

        A single shared stream is not safe here: on a re-run the units already
        exist, so the calls that would have drawn their attributes never happen,
        the stream shifts, and different units come out vacant. Seeding per unit
        makes every decision independent of call order, which is what makes a
        second run a no-op.
        """
        return random.Random(f"{SEED}:" + ":".join(str(p) for p in parts))

    @api.model
    def load(self, with_accounting=True):
        """Create the sample portfolio. Returns a summary dict of what was made."""
        rng = random.Random(SEED)
        created = defaultdict(int, dict.fromkeys(COUNTERS, 0))

        landlords = self._landlords()
        tag = self._tenant_tag()
        buildings = self._buildings(landlords, created)
        self._units_and_leases(buildings, tag, rng, created)
        self._head_leases(buildings, created)
        if with_accounting:
            self._cheques(rng, created)
            self._landlord_cheques(rng, created)
            self._invoices(created)
            self._facilities(created)

        _logger.info("c2p.sample.portfolio: %s", dict(created))
        return dict(created)

    # ------------------------------------------------------------------ pieces
    def _landlords(self):
        partners = []
        for name, _index in LANDLORDS:
            partner = self.env["res.partner"].search([("name", "=", name)], limit=1)
            if not partner:
                partner = self.env["res.partner"].create({"name": name, "is_company": True, "city": "Dubai"})
            partners.append(partner)
        return partners

    def _tenant_tag(self):
        tag = self.env["res.partner.category"].search([("name", "=", "Tenant")], limit=1)
        return tag or self.env["res.partner.category"].create({"name": "Tenant"})

    def _buildings(self, landlords, created):
        buildings = {}
        for code, name, community, owner_i, _cost_share, *_ in BUILDINGS:
            building = self.env["c2p.building"].search([("code", "=", code)], limit=1)
            if not building:
                building = self.env["c2p.building"].create(
                    {
                        "name": name,
                        "code": code,
                        "community": community,
                        "city": "Dubai",
                        "owner_id": landlords[owner_i].id,
                    }
                )
                created["buildings"] += 1
            buildings[code] = building
        return buildings

    def _units_and_leases(self, buildings, tag, rng, created):
        today = fields.Date.context_today(self)
        tenant_i = 0
        for code, _name, _community, _owner, _cost_share, floors, per_floor, commercial in BUILDINGS:
            building = buildings[code]
            for floor in range(1, floors + 1):
                for slot in range(1, per_floor + 1):
                    number = f"{floor}0{slot}"
                    if commercial and floor == 1:
                        unit_type = "shop" if slot <= 2 else "office"
                    else:
                        unit_type = SLOT_TYPE[slot]
                    name = f"{code}-{number}"
                    # One stream per purpose. Sharing a stream is what broke
                    # idempotency before: on a re-run the unit already exists,
                    # its attribute draws never happen, and a shared stream
                    # hands the vacancy check a different number.
                    unit = self._unit(building, name, unit_type, self._rng("unit", name), created)

                    if self._rng("vacancy", name).random() < VACANCY_RATE:
                        tenant_i += 1
                        continue
                    if unit.lease_ids:
                        tenant_i += 1
                        continue
                    self._lease(
                        unit,
                        unit_type,
                        tag,
                        tenant_i,
                        today,
                        self._rng("lease", name),
                        created,
                    )
                    tenant_i += 1

    def _unit(self, building, name, unit_type, rng, created):
        unit = self.env["c2p.unit"].search([("name", "=", name), ("building_id", "=", building.id)], limit=1)
        if unit:
            return unit
        low, high = BAND[unit_type]
        area_low, area_high = AREA[unit_type]
        created["units"] += 1
        return self.env["c2p.unit"].create(
            {
                "name": name,
                "building_id": building.id,
                "unit_type": unit_type,
                "floor": name.split("-")[1][0],
                "area_sqft": rng.randint(area_low, area_high),
                "market_rent": round(rng.uniform(low, high), -2),
                "rera_index_low": low,
                "rera_index_high": high,
                "dewa_no": str(rng.randint(2000000, 2999999)),
            }
        )

    def _lease(self, unit, unit_type, tag, tenant_i, today, rng, created):
        low, high = BAND[unit_type]
        commercial = unit_type in ("shop", "office")
        if commercial:
            who = f"{COMPANIES[tenant_i % len(COMPANIES)]} {tenant_i // len(COMPANIES) + 1}"
        else:
            who = f"{FIRST[tenant_i % len(FIRST)]} {LAST[(tenant_i * 7) % len(LAST)]}"

        tenant = self.env["res.partner"].search([("name", "=", who)], limit=1)
        if not tenant:
            tenant = self.env["res.partner"].create(
                {
                    "name": who,
                    "is_company": commercial,
                    "city": "Dubai",
                    "category_id": [(4, tag.id)],
                }
            )

        rent = round(rng.uniform(low, high), -2)
        # Spread start dates so the 90-day renewal horizon is always populated.
        days_in = rng.choice([15, 40, 70, 95, 130, 170, 210, 250, 285, 320, 350])
        start = today - relativedelta(days=days_in)
        lease = self.env["c2p.lease"].create(
            {
                "tenant_id": tenant.id,
                "unit_id": unit.id,
                "date_start": start,
                "date_end": start + relativedelta(years=1, days=-1),
                "annual_rent": rent,
                "cheque_count": rng.choice(["1", "2", "4", "4", "4", "6", "12"]),
                "security_deposit": round(rent * 0.05, 2),
                "commission": round(rent * 0.05, 2),
                "ejari_no": f"E-{rng.randint(100000, 999999)}",
                "ejari_date": start + relativedelta(days=3),
            }
        )
        lease.action_activate()
        created["leases"] += 1
        return lease

    def _head_leases(self, buildings, created):
        """What we owe each landlord, priced off the building's market rent."""
        today = fields.Date.context_today(self)
        start = today.replace(month=1, day=1)
        HeadLease = self.env["c2p.head.lease"]
        for code, _name, _community, _owner, cost_share, *_ in BUILDINGS:
            building = buildings[code]
            if HeadLease.search_count([("building_id", "=", building.id), ("state", "=", "active")]):
                continue
            potential = building.potential_rent
            if not potential:
                continue
            lease = HeadLease.create(
                {
                    "building_id": building.id,
                    "landlord_id": building.owner_id.id,
                    "date_start": start,
                    "date_end": start + relativedelta(years=1, days=-1),
                    "annual_amount": round(potential * cost_share, -3),
                    "cheque_count": "4",
                    "security_deposit": round(potential * cost_share * 0.05, -2),
                    "ejari_no": f"HL-{building.code}-{start.year}",
                    "ejari_date": start,
                }
            )
            lease.action_activate()
            created["head_leases"] += 1

    def _landlord_cheques(self, rng, created):
        """Money out. Mirrors the tenant register so the cash timeline has both
        sides of the cheque book."""
        leases = self.env["c2p.head.lease"].search([("state", "=", "active")])
        if not leases:
            return
        company = leases[0].company_id
        journal = self.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
        method_line = journal.outbound_payment_method_line_ids[:1] if journal else None
        if not journal or not method_line:
            _logger.info("c2p.sample.portfolio: no outbound payment method, skipping landlord cheques")
            return
        Payment = self.env["account.payment"]
        today = fields.Date.context_today(self)
        for lease in leases:
            if Payment.search_count([("head_lease_id", "=", lease.id)]):
                continue
            count = int(lease.cheque_count)
            step = max(1, 12 // count)
            for i in range(count):
                maturity = lease.date_start + relativedelta(months=step * i)
                if maturity < today:
                    state = "cleared"
                elif (maturity - today).days <= 30:
                    state = "deposited"
                else:
                    state = "held"
                Payment.create(
                    {
                        "partner_id": lease.landlord_id.id,
                        "partner_type": "supplier",
                        "payment_type": "outbound",
                        "amount": lease.instalment_amount,
                        "date": maturity,
                        "journal_id": journal.id,
                        "payment_method_line_id": method_line.id,
                        "company_id": company.id,
                        "head_lease_id": lease.id,
                        "cheque_no": str(rng.randint(400000, 499999)),
                        "cheque_bank": journal.name,
                        "maturity_date": maturity,
                        "pdc_state": state,
                    }
                )
                created["landlord_cheques"] += 1

    def _facilities(self, created):
        company = self.env.company
        bank = self.env["res.bank"].search([], limit=1)
        if not bank:
            bank = self.env["res.bank"].create({"name": "Emirates NBD"})
        specs = [
            ("Working Capital Overdraft", "overdraft", 5000000.0, 1850000.0),
            ("Cheque Discounting Line", "cheque_discounting", 3000000.0, 2400000.0),
        ]
        Facility = self.env["c2p.bank.facility"]
        for name, kind, limit, used in specs:
            if Facility.search_count([("name", "=", name), ("company_id", "=", company.id)]):
                continue
            Facility.create(
                {
                    "name": name,
                    "bank_id": bank.id,
                    "facility_type": kind,
                    "limit_amount": limit,
                    "utilised_amount": used,
                    "company_id": company.id,
                }
            )
            created["facilities"] += 1

    def _cheques(self, rng, created):
        """Cheques need a journal and a payment method line, so they cannot be
        data files - the ids differ per database."""
        leases = self.env["c2p.lease"].search([("state", "=", "active")])
        if not leases:
            return
        company = leases[0].company_id
        journal = self.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
        method_line = journal.inbound_payment_method_line_ids[:1] if journal else None
        if not journal or not method_line:
            _logger.info("c2p.sample.portfolio: no usable bank journal, skipping cheques")
            return

        Payment = self.env["account.payment"]
        today = fields.Date.context_today(self)
        for lease in leases:
            if Payment.search_count([("lease_id", "=", lease.id)]):
                continue
            count = int(lease.cheque_count)
            step = max(1, 12 // count)
            for i in range(count):
                maturity = lease.date_start + relativedelta(months=step * i)
                if maturity > lease.date_end:
                    break
                if maturity < today:
                    state = "bounced" if rng.random() < 0.08 else "cleared"
                elif (maturity - today).days <= 30:
                    state = "deposited"
                else:
                    state = "held"
                Payment.create(
                    {
                        "partner_id": lease.tenant_id.id,
                        "partner_type": "customer",
                        "payment_type": "inbound",
                        "amount": lease.instalment_amount,
                        "date": maturity,
                        "journal_id": journal.id,
                        "payment_method_line_id": method_line.id,
                        "company_id": company.id,
                        "lease_id": lease.id,
                        "cheque_no": str(rng.randint(300000, 799999)),
                        "cheque_bank": rng.choice(BANKS),
                        "maturity_date": maturity,
                        "pdc_state": state,
                    }
                )
                created["cheques"] += 1

    def _invoices(self, created):
        """Posted invoices so the income KPIs report something other than zero."""
        leases = self.env["c2p.lease"].search([("state", "=", "active")], limit=40)
        if not leases:
            return
        company = leases[0].company_id
        journal = self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1)
        rent_product = self._variant("product_residential_rent")
        if not journal or not rent_product:
            _logger.info("c2p.sample.portfolio: accounting not ready, skipping invoices")
            return

        Move = self.env["account.move"]
        today = fields.Date.context_today(self)
        year_start = today.replace(month=1, day=1)
        for lease in leases:
            ref = f"Sample rent - {lease.unit_id.display_name}"
            if Move.search_count([("ref", "=", ref)]):
                continue
            invoice_date = max(year_start, lease.date_start)
            if invoice_date > today:
                continue
            analytic = lease.building_id.analytic_account_id
            move = Move.create(
                {
                    "move_type": "out_invoice",
                    "company_id": company.id,
                    "partner_id": lease.tenant_id.id,
                    "journal_id": journal.id,
                    "invoice_date": invoice_date,
                    "ref": ref,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": rent_product.id,
                                "name": f"Rent - {lease.unit_id.display_name}",
                                "quantity": 1,
                                "price_unit": lease.instalment_amount,
                                "analytic_distribution": ({str(analytic.id): 100.0} if analytic else False),
                            },
                        )
                    ],
                }
            )
            move.action_post()
            created["invoices"] += 1

    def _variant(self, xml_id):
        template = self.env.ref(f"c2p_property_lease.{xml_id}", raise_if_not_found=False)
        return template.product_variant_id if template else None
