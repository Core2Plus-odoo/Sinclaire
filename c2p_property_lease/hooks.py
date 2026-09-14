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
