from odoo import fields
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    c2p_building_id = fields.Many2one(
        "c2p.building",
        string="Building",
        copy=False,
        index="btree_not_null",
        help="Set on invoices and bills belonging to a building, so income and "
        "cost can be traced to the deal without relying on analytic tags alone.",
    )
