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
    "version": "19.0.1.0.0",
    "category": "Technical",
    "author": "C2P Consultants",
    "website": "https://github.com/core2plus-odoo/sinclaire",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/sinclaire_security.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
