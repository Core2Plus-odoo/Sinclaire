from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class LeaseRenew(models.TransientModel):
    _name = "c2p.lease.renew"
    _description = "Renew Lease"

    lease_id = fields.Many2one("c2p.lease", required=True, readonly=True)
    currency_id = fields.Many2one(related="lease_id.currency_id")
    current_rent = fields.Monetary(related="lease_id.annual_rent", string="Current Rent")
    new_rent = fields.Monetary(required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    cheque_count = fields.Selection(related="lease_id.cheque_count", readonly=False)
    increase_pct = fields.Float(compute="_compute_increase", string="Increase %")
    rera_warning = fields.Char(compute="_compute_increase")

    @api.onchange("lease_id")
    def _onchange_lease(self):
        if self.lease_id:
            self.date_start = self.lease_id.date_end + relativedelta(days=1)
            self.date_end = self.date_start + relativedelta(years=1, days=-1)
            self.new_rent = self.lease_id.annual_rent

    @api.depends("new_rent", "current_rent")
    def _compute_increase(self):
        """RERA caps renewal increases by how far the current rent sits below the market index."""
        for rec in self:
            cur = rec.current_rent or 0.0
            rec.increase_pct = ((rec.new_rent - cur) / cur * 100.0) if cur else 0.0
            unit = rec.lease_id.unit_id
            msg = ""
            if unit.rera_index_low and cur:
                gap = (unit.rera_index_low - cur) / unit.rera_index_low * 100.0
                if gap <= 10:
                    cap = 0
                elif gap <= 20:
                    cap = 5
                elif gap <= 30:
                    cap = 10
                elif gap <= 40:
                    cap = 15
                else:
                    cap = 20
                if rec.increase_pct > cap:
                    msg = (
                        f"Proposed increase of {rec.increase_pct:.1f}% exceeds the RERA calculator "
                        f"cap of {cap}% for this unit. Review before issuing the renewal notice."
                    )
                else:
                    msg = f"Within the RERA cap of {cap}% for this unit."
            rec.rera_warning = msg

    def action_renew(self):
        self.ensure_one()
        old = self.lease_id
        new = old.copy(
            {
                "name": "New",
                "date_start": self.date_start,
                "date_end": self.date_end,
                "annual_rent": self.new_rent,
                "cheque_count": self.cheque_count,
                "state": "draft",
                "subscription_id": False,
                "ejari_no": False,
                "ejari_date": False,
                "renewed_from_id": old.id,
            }
        )
        old.state = "expired"
        new.action_activate()
        return {"type": "ir.actions.act_window", "res_model": "c2p.lease", "res_id": new.id, "view_mode": "form"}
