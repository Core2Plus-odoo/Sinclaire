{
    "name": "Sinclaire Workspace",
    "summary": "Role-aware property workspaces built over the standard Odoo records.",
    "description": """
Sinclaire Workspace
===================

Layer 3 of the Sinclaire architecture: a premium interface over the existing
property records, not a second ERP.

It holds no business logic of its own. Buildings, units, leases and cheques
stay where they are, in ``c2p_property_lease``; everything here is
presentation plus the handful of derived fields a screen needs in order to
answer "what should I look at first?" without the user computing it.

It lives in its own module, rather than inside ``c2p_property_lease``, because
the contract separates the Supplier Module from Client Development. The
property module is the supplier's work under OPL-1; the look and feel is the
client's under LGPL-3. Keeping them apart means the boundary stays legible
instead of becoming an argument later.
""",
    "version": "19.0.1.2.1",
    "category": "Services/Real Estate",
    "author": "C2P Consultants",
    "website": "https://github.com/core2plus-odoo/sinclaire",
    "license": "LGPL-3",
    "depends": ["sinclaire_base", "c2p_property_lease"],
    "data": [
        "views/portfolio_views.xml",
        "views/building_360_views.xml",
        "views/collections_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
