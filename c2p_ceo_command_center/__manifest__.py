{
    "name": "C2P CEO Command Center",
    "version": "19.0.1.0.0",
    "category": "Services/Real Estate",
    "summary": "One screen of portfolio, cash and risk KPIs for the leadership team",
    "description": """
CEO Command Center
==================

A single curated screen aggregating the numbers a property-management CEO asks
for: occupancy, contracted rent, cheque position, expiring leases and fee
income. Every figure is clickable through to the records behind it.

This deliberately does not re-implement reporting. Odoo's pivot, graph,
Spreadsheet Dashboards and My Dashboard already cover ad-hoc analysis; what
they do not give is one screen aggregating across buildings, leases, cheques
and invoices. That aggregation is all this module adds.
""",
    "author": "C2P Consultants",
    "website": "https://www.core2plus.com",
    "license": "OPL-1",
    "depends": ["c2p_property_lease"],
    "data": [
        "security/ir.model.access.csv",
        "views/dashboard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
