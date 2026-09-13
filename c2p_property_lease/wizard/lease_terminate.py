from odoo import api, fields, models


class LeaseTerminate(models.TransientModel):
    _name = "c2p.lease.terminate"
    _description = "Terminate Lease"

    lease_id = fields.Many2one("c2p.lease", required=True, readonly=True)
    currency_id = fields.Many2one(related="lease_id.currency_id")
    date_termination = fields.Date(required=True, default=fields.Date.context_today)
    deposit_held = fields.Monetary(related="lease_id.security_deposit", string="Deposit Held")
    deduction = fields.Monetary(string="Deductions", help="Damages, unpaid utilities or cleaning charges.")
    deduction_reason = fields.Char()
    refund_amount = fields.Monetary(compute="_compute_refund")

    @api.depends("deposit_held", "deduction")
    def _compute_refund(self):
        for rec in self:
            rec.refund_amount = max(rec.deposit_held - rec.deduction, 0.0)

    def action_terminate(self):
        self.ensure_one()
        lease = self.lease_id
        lease.write({"state": "terminated", "date_end": self.date_termination})
        if lease.subscription_id:
            lease.subscription_id.write({"subscription_state": "6_churn"})
        lease.unit_id.write({"state": "vacant", "current_lease_id": False})
        lease.message_post(
            body=(
                f"Lease terminated on {self.date_termination}. Deposit held "
                f"{self.deposit_held:,.2f}, deductions {self.deduction:,.2f} "
                f"({self.deduction_reason or 'none'}), refund due {self.refund_amount:,.2f}."
            )
        )
        return {"type": "ir.actions.act_window_close"}
