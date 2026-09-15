from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.head_lease import CHEQUE_PLAN


class LandlordChequeRegister(models.TransientModel):
    _name = "c2p.landlord.cheque.register"
    _description = "Issue Landlord Cheques"

    head_lease_id = fields.Many2one("c2p.head.lease", required=True, readonly=True)
    currency_id = fields.Many2one(related="head_lease_id.currency_id")
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        help="The bank account these cheques are drawn on.",
    )
    company_id = fields.Many2one(related="head_lease_id.company_id")
    first_maturity = fields.Date(required=True)
    first_cheque_no = fields.Char(string="First Cheque No.")
    line_ids = fields.One2many("c2p.landlord.cheque.line", "wizard_id")

    @api.onchange("head_lease_id", "first_maturity", "first_cheque_no")
    def _onchange_schedule(self):
        if not self.head_lease_id:
            return
        if not self.first_maturity:
            self.first_maturity = self.head_lease_id.date_start
        self.line_ids = [(5, 0, 0), *self._build_schedule()]

    def _build_schedule(self):
        lease = self.head_lease_id
        count = int(lease.cheque_count)
        step = CHEQUE_PLAN[count]
        base = None
        if self.first_cheque_no and self.first_cheque_no.isdigit():
            base = int(self.first_cheque_no)
        lines = []
        for i in range(count):
            lines.append(
                (
                    0,
                    0,
                    {
                        "maturity_date": (self.first_maturity or lease.date_start) + relativedelta(months=step * i),
                        "amount": lease.instalment_amount,
                        "cheque_no": str(base + i) if base is not None else self.first_cheque_no,
                    },
                )
            )
        return lines

    def action_issue(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._("Generate the cheque schedule before issuing."))
        lease = self.head_lease_id
        method_line = self.journal_id.outbound_payment_method_line_ids[:1]
        if not method_line:
            raise UserError(
                self.env._(
                    "%s has no outbound payment method, so cheques cannot be issued from it.",
                    self.journal_id.display_name,
                )
            )
        Payment = self.env["account.payment"]
        for line in self.line_ids:
            Payment.create(
                {
                    "partner_id": lease.landlord_id.id,
                    "partner_type": "supplier",
                    "payment_type": "outbound",
                    "amount": line.amount,
                    "date": line.maturity_date,
                    "journal_id": self.journal_id.id,
                    "payment_method_line_id": method_line.id,
                    "company_id": lease.company_id.id,
                    "head_lease_id": lease.id,
                    "cheque_no": line.cheque_no,
                    "cheque_bank": self.journal_id.name,
                    "maturity_date": line.maturity_date,
                    "pdc_state": "held",
                }
            )
        return lease.action_view_cheques()


class LandlordChequeLine(models.TransientModel):
    _name = "c2p.landlord.cheque.line"
    _description = "Landlord Cheque Schedule Line"
    _order = "maturity_date"

    wizard_id = fields.Many2one("c2p.landlord.cheque.register", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    maturity_date = fields.Date(required=True)
    amount = fields.Monetary(required=True)
    cheque_no = fields.Char(string="Cheque No.")
