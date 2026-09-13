from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

MONTHS = {1: 12, 2: 6, 4: 3, 6: 2, 12: 1}


class PdcRegister(models.TransientModel):
    _name = "c2p.pdc.register"
    _description = "Register Post-Dated Cheques"

    lease_id = fields.Many2one("c2p.lease", required=True, readonly=True)
    currency_id = fields.Many2one(related="lease_id.currency_id")
    journal_id = fields.Many2one(
        "account.journal",
        string="PDC Journal",
        required=True,
        domain="[('type','in',('bank','cash'))]",
        default=lambda self: self.env["account.journal"].search(
            [("code", "=", "PDCR"), ("company_id", "=", self.env.company.id)], limit=1
        ),
    )
    first_maturity = fields.Date(required=True, default=fields.Date.context_today)
    bank_name = fields.Char(string="Drawn On", required=True)
    first_cheque_no = fields.Char(required=True, help="Subsequent cheque numbers increment from this one.")
    line_ids = fields.One2many("c2p.pdc.register.line", "wizard_id", string="Cheques")

    @api.onchange("lease_id", "first_maturity", "first_cheque_no", "bank_name")
    def _onchange_generate(self):
        if not (self.lease_id and self.first_maturity and self.first_cheque_no):
            return
        step = MONTHS[int(self.lease_id.cheque_count)]
        try:
            base = int("".join(c for c in self.first_cheque_no if c.isdigit()))
        except ValueError:
            base = 0
        lines = []
        for i in range(int(self.lease_id.cheque_count)):
            lines.append(
                (
                    0,
                    0,
                    {
                        "maturity_date": self.first_maturity + relativedelta(months=step * i),
                        "amount": self.lease_id.instalment_amount,
                        "cheque_no": str(base + i) if base else self.first_cheque_no,
                        "bank_name": self.bank_name,
                    },
                )
            )
        self.line_ids = [(5, 0, 0), *lines]

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._("Generate the cheque schedule before confirming."))
        method_line = self.journal_id.inbound_payment_method_line_ids[:1]
        payments = self.env["account.payment"]
        for line in self.line_ids:
            payments |= self.env["account.payment"].create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.lease_id.tenant_id.id,
                    "amount": line.amount,
                    "date": line.maturity_date,
                    "journal_id": self.journal_id.id,
                    "payment_method_line_id": method_line.id if method_line else False,
                    "company_id": self.lease_id.company_id.id,
                    "lease_id": self.lease_id.id,
                    "cheque_no": line.cheque_no,
                    "cheque_bank": line.bank_name,
                    "maturity_date": line.maturity_date,
                    "pdc_state": "held",
                    "memo": f"PDC {line.cheque_no} {line.bank_name} – {self.lease_id.unit_id.display_name}",
                }
            )
        return self.lease_id.action_view_pdcs()


class PdcRegisterLine(models.TransientModel):
    _name = "c2p.pdc.register.line"
    _description = "PDC Schedule Line"
    _order = "maturity_date"

    wizard_id = fields.Many2one("c2p.pdc.register", ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    maturity_date = fields.Date(required=True)
    amount = fields.Monetary(required=True)
    cheque_no = fields.Char(required=True)
    bank_name = fields.Char(string="Drawn On")
