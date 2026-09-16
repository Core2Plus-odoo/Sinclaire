{
    "name": "C2P Property & Lease Management",
    "version": "19.0.1.1.1",
    "category": "Services/Real Estate",
    "summary": "Underwritten buildings, tenancy leases, tenant and landlord "
    "cheque registers, and deal margin for UAE property management",
    "author": "C2P Consultants",
    "website": "https://www.core2plus.com",
    "license": "OPL-1",
    # sale_subscription (Enterprise) is a SOFT dependency on purpose: it cannot
    # be vendored into this repo or installed in CI, so hard-depending on it
    # would mean this module is never install-tested. Everything here works on
    # Community; the rent-subscription actions light up when Subscriptions is
    # present and refuse with a clear message when it is not.
    "depends": [
        "base",
        "mail",
        "account",
        "sale",
        "analytic",
        "contacts",
    ],
    "data": [
        "security/c2p_security.xml",
        "security/ir.model.access.csv",
        "data/product_data.xml",
        "data/ir_sequence.xml",
        "data/ir_cron.xml",
        "views/head_lease_views.xml",
        "views/bank_facility_views.xml",
        "wizard/landlord_cheque_register_views.xml",
        "views/building_views.xml",
        "views/unit_views.xml",
        "views/lease_views.xml",
        "views/account_payment_views.xml",
        "wizard/pdc_register_views.xml",
        "wizard/lease_renew_views.xml",
        "wizard/lease_terminate_views.xml",
        "wizard/sample_loader_views.xml",
        "views/menus.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
}
