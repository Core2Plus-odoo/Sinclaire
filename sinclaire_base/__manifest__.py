{
    "name": "Sinclaire Base",
    "summary": "Shared foundation for all Sinclaire custom modules.",
    "description": """
Sinclaire Base
==============

Install-order anchor and shared foundation for the Sinclaire customisation
suite. Every other ``sinclaire_*`` module depends on this one so that common
data, security groups and assets are loaded exactly once and in a predictable
order.
""",
    "version": "19.0.1.1.1",
    "category": "Technical",
    "author": "C2P Consultants",
    "website": "https://github.com/core2plus-odoo/sinclaire",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/sinclaire_security.xml",
        "security/ir.model.access.csv",
    ],
    # The design system loads here rather than in c2p_property_lease on
    # purpose. This module is LGPL-3 and client-specific; the property module
    # is OPL-1 and the supplier's. Keeping the look-and-feel layer on the
    # client side of that boundary is what the contract's IP split asks for,
    # and it means the tokens are available to every sinclaire_* module
    # without any of them depending on the supplier module.
    "assets": {
        "web.assets_backend": [
            "sinclaire_base/static/src/scss/_tokens.scss",
            "sinclaire_base/static/src/scss/_components.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
