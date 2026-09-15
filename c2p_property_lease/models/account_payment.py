from odoo import api
from odoo import fields
from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    lease_id = fields.Many2one("c2p.lease", string="Lease", index=True, copy=False)
    head_lease_id = fields.Many2one(
        "c2p.head.lease",
        string="Head Lease",
        index="btree_not_null",
        copy=False,
        help="Set on cheques we issue to a landlord under an underwriting agreement.",
    )
    is_landlord_cheque = fields.Boolean(
        compute="_compute_is_landlord_cheque",
        store=True,
        help="Money out to a landlord, as opposed to rent in from a tenant.",
    )
    unit_id = fields.Many2one(related="lease_id.unit_id", store=True)
    building_id = fields.Many2one(related="lease_id.building_id", store=True)
    cheque_no = fields.Char(string="Cheque No.", copy=False)
    cheque_bank = fields.Char(string="Drawn On")
    maturity_date = fields.Date(help="Date the cheque may be banked.")
    is_pdc = fields.Boolean(string="Post-Dated Cheque", compute="_compute_is_pdc", store=True)
    pdc_state = fields.Selection(
        [("held", "In Hand"), ("deposited", "Deposited"), ("cleared", "Cleared"), ("bounced", "Bounced")],
        default="held",
        copy=False,
        tracking=True,
    )

    @api.depends("head_lease_id")
    def _compute_is_landlord_cheque(self):
        for rec in self:
            rec.is_landlord_cheque = bool(rec.head_lease_id)

    @api.depends("cheque_no")
    def _compute_is_pdc(self):
        for rec in self:
            rec.is_pdc = bool(rec.cheque_no)

    def action_pdc_deposit(self):
        self.filtered(lambda p: p.pdc_state == "held").write({"pdc_state": "deposited"})

    def action_pdc_clear(self):
        self.filtered(lambda p: p.pdc_state in ("held", "deposited")).write({"pdc_state": "cleared"})

    def action_pdc_bounce(self):
        for rec in self:
            rec.pdc_state = "bounced"
            rec.message_post(body=self.env._("Cheque returned unpaid. Follow up with the tenant."))
