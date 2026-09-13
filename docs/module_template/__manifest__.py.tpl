{
    "name": "Sinclaire <Feature>",
    "summary": "One line describing what this module does for the user.",
    "version": "19.0.1.0.0",
    "category": "Sinclaire",
    "author": "C2P Consultants",
    "website": "https://github.com/core2plus-odoo/sinclaire",
    "license": "LGPL-3",
    "depends": ["sinclaire_base"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/model_name_views.xml",
        "views/menus.xml",
    ],
    "demo": [],
    "assets": {
        # "web.assets_backend": ["sinclaire_<feature>/static/src/**/*"],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
