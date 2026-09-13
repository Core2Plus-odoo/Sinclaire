from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    c2p_fee_building_id = fields.Many2one(
        "c2p.building",
        string="Management Fee For",
        copy=False,
        index="btree_not_null",
        help="Set on management-fee invoices raised from a landlord statement. "
        "Carries the building's analytic account, so it must be excluded from "
        "the rent side of later statements or the fee compounds on itself.",
    )
    c2p_fee_date_from = fields.Date(string="Fee Period From", copy=False)
    c2p_fee_date_to = fields.Date(string="Fee Period To", copy=False)
