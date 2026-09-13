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
