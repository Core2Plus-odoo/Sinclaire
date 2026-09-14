"""Install hooks.

The Sinclair database already carries the rent and fee products, created by
script with no XML ID and no internal reference. Shipping them as module data
would create a second set of duplicates - and the existing ones are the records
that carry the correct UAE tax records and that existing subscriptions point at.

So before the data file loads, claim the existing products under this module's
XML IDs. The loader then treats them as already-present `noupdate` records and
leaves them alone; only a database without them gets fresh ones.
"""

import logging
import random

_logger = logging.getLogger(__name__)

# XML ID (in this module) -> the product name to adopt if it already exists.
ADOPTED_PRODUCTS = {
    "product_residential_rent": "Residential Rent",
    "product_commercial_rent": "Commercial Rent",
    "product_property_management_fee": "Property Management Fee",
}


def pre_init_hook(env):
    data = env["ir.model.data"]
    templates = env["product.template"].with_context(active_test=False)
    for xml_id, name in ADOPTED_PRODUCTS.items():
        if data.search_count([("module", "=", "c2p_property_lease"), ("name", "=", xml_id)]):
            continue
        template = templates.search([("name", "=", name)], order="id", limit=1)
        if not template:
            continue
        data.create(
            {
                "module": "c2p_property_lease",
                "name": xml_id,
                "model": "product.template",
                "res_id": template.id,
                "noupdate": True,
            }
        )
        _logger.info(
            "c2p_property_lease: adopted existing product %r (id %s) as %r",
            name,
            template.id,
            xml_id,
        )


# Cheques cannot be shipped as XML: account.payment needs a journal and a
# payment method line, and those ids differ per database. So build them here,
# only when the module was installed with demo data and only if the accounting
# setup can actually support them.
DEMO_BANKS = ["ENBD", "Mashreq", "ADCB", "FAB", "RAKBANK"]


def post_init_hook(env):
    module = env["ir.module.module"].search([("name", "=", "c2p_property_lease")], limit=1)
    if not module.demo:
        return
    _create_demo_cheques(env)
    _create_demo_invoices(env)


def _create_demo_cheques(env):
    leases = env["c2p.lease"].search([("state", "=", "active")])
    if not leases:
        return

    company = leases[0].company_id
    journal = env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
    method_line = journal.inbound_payment_method_line_ids[:1] if journal else None
    if not journal or not method_line:
        _logger.info(
            "c2p_property_lease: no bank journal with an inbound payment method in %s, skipping demo cheques",
            company.display_name,
        )
        return

    Payment = env["account.payment"]
    if Payment.search_count([("lease_id", "in", leases.ids)]):
        return  # already generated

    rng = random.Random(20260914)
    today = env["c2p.lease"]._fields["date_start"].today()
    created = 0
    for lease in leases:
        count = int(lease.cheque_count)
        step = max(1, 12 // count)
        for i in range(count):
            maturity = lease.date_start + _months(step * i)
            if maturity > lease.date_end:
                break
            if maturity < today:
                # A matured cheque has been banked: mostly clears, occasionally
                # bounces, so the collection KPIs have something real to show.
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
                    "cheque_bank": rng.choice(DEMO_BANKS),
                    "maturity_date": maturity,
                    "pdc_state": state,
                }
            )
            created += 1
    _logger.info("c2p_property_lease: created %s demo cheques", created)


def _months(n):
    from dateutil.relativedelta import relativedelta

    return relativedelta(months=n)


def _create_demo_invoices(env):
    """Posted rent and fee invoices so the income KPIs report something real.

    Without these the dashboard's Income section is a row of zeros, which makes
    it impossible to tell a working figure from a broken one.
    """
    leases = env["c2p.lease"].search([("state", "=", "active")], limit=40)
    if not leases:
        return

    company = leases[0].company_id
    journal = env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1)
    if not journal:
        _logger.info(
            "c2p_property_lease: no sales journal in %s, skipping demo invoices",
            company.display_name,
        )
        return

    Move = env["account.move"]
    if Move.search_count([("journal_id", "=", journal.id), ("ref", "like", "Demo rent%")]):
        return

    today = env["c2p.lease"]._fields["date_start"].today()
    year_start = today.replace(month=1, day=1)
    rent_product = _template_variant(env, "product_residential_rent")
    fee_product = _template_variant(env, "product_property_management_fee")
    if not rent_product or not fee_product:
        return

    created = 0
    for index, lease in enumerate(leases):
        # Spread invoices across the year to date so period filters have range.
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
                "ref": f"Demo rent - {lease.unit_id.display_name}",
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
        created += 1
        # Leave a couple unpaid and back-dated so "overdue" is not always zero.
        if index % 5 == 0:
            move.invoice_date_due = invoice_date

    _create_demo_fee_invoice(env, company, journal, fee_product, year_start, today)
    _logger.info("c2p_property_lease: created %s demo rent invoices", created)


def _create_demo_fee_invoice(env, company, journal, product, date_from, date_to):
    building = env["c2p.building"].search([("analytic_account_id", "!=", False)], limit=1) or env[
        "c2p.building"
    ].search([], limit=1)
    if not building:
        return
    analytic = building.analytic_account_id
    move = env["account.move"].create(
        {
            "move_type": "out_invoice",
            "company_id": company.id,
            "partner_id": building.owner_id.id,
            "journal_id": journal.id,
            "invoice_date": date_to,
            "ref": f"Demo management fee - {building.name}",
            "c2p_fee_building_id": building.id,
            "c2p_fee_date_from": date_from,
            "c2p_fee_date_to": date_to,
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": f"Management fee - {building.name}",
                        "quantity": 1,
                        "price_unit": 18500.0,
                        "analytic_distribution": {str(analytic.id): 100.0} if analytic else False,
                    },
                )
            ],
        }
    )
    move.action_post()


def _template_variant(env, xml_id):
    template = env.ref(f"c2p_property_lease.{xml_id}", raise_if_not_found=False)
    return template.product_variant_id if template else None
