"""The two instrument moves that need more than a button.

BRD §3.2 marks three transitions "reason mandatory" — In Hand → Expected,
Deposited → In Hand (a recall) and a cancellation — and requires a replacement
instrument to be "linked both ways". Neither fits on a list button, so each
gets a dialog: the reason is captured where it is given rather than typed into
a chatter message afterwards.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..models.account_payment import PDC_STATES


class PdcReason(models.TransientModel):
    _name = "c2p.pdc.reason"
    _description = "Cheque Status Change"

    payment_id = fields.Many2one("account.payment", required=True, readonly=True)
    cheque_no = fields.Char(related="payment_id.cheque_no", string="Cheque No.")
    current_state = fields.Selection(related="payment_id.pdc_state", string="Current Status")
    move = fields.Selection(
        PDC_STATES,
        required=True,
        readonly=True,
        string="New Status",
    )
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.payment_id._pdc_move(self.move, reason=self.reason)
        return {"type": "ir.actions.act_window_close"}


class PdcReplace(models.TransientModel):
    _name = "c2p.pdc.replace"
    _description = "Replace a Returned Cheque"

    payment_id = fields.Many2one("account.payment", required=True, readonly=True)
    currency_id = fields.Many2one(related="payment_id.currency_id")
    returned_cheque_no = fields.Char(related="payment_id.cheque_no", string="Returned Cheque")
    returned_amount = fields.Monetary(related="payment_id.amount", string="Returned Amount")
    cheque_no = fields.Char(string="Replacement Cheque No.", required=True)
    cheque_bank = fields.Char(string="Drawn On", required=True)
    maturity_date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(required=True)
    reason = fields.Text(help="Anything worth recording about the replacement.")

    @api.onchange("payment_id")
    def _onchange_payment(self):
        if self.payment_id:
            self.amount = self.payment_id.amount
            self.cheque_bank = self.payment_id.cheque_bank

    def action_confirm(self):
        """Create the replacement in hand and link the two instruments.

        The replacement is a **new** record rather than an edit of the old one:
        the returned cheque is evidence, and §3's rule that no status may be
        overwritten without history applies to the instrument as much as to the
        status. Linking both ways means the chain is readable from either end -
        from the bounce forward, and from the cheque that made good back.
        """
        self.ensure_one()
        original = self.payment_id
        if original.pdc_state != "bounced":
            raise UserError(self.env._("Only a returned cheque can be replaced."))
        if original.replacement_payment_id:
            raise UserError(
                self.env._(
                    "Cheque %s has already been replaced by %s.",
                    original.cheque_no or "",
                    original.replacement_payment_id.cheque_no or "",
                )
            )
        # Built field by field rather than with copy(): the returned cheque may
        # be posted or part-reconciled by now, and duplicating an accounting
        # record to get an instrument carries whatever state it has acquired.
        # Everything the replacement needs is named here, including lease_id and
        # head_lease_id - copy=False on both, so a copy would have dropped the
        # lease link and with it the cover BR-075 reads.
        replacement = self.env["account.payment"].create(
            {
                "payment_type": original.payment_type,
                "partner_type": original.partner_type,
                "partner_id": original.partner_id.id,
                "journal_id": original.journal_id.id,
                "payment_method_line_id": original.payment_method_line_id.id,
                "company_id": original.company_id.id,
                "lease_id": original.lease_id.id,
                "head_lease_id": original.head_lease_id.id,
                "amount": self.amount,
                "date": self.maturity_date,
                "maturity_date": self.maturity_date,
                "cheque_no": self.cheque_no,
                "cheque_bank": self.cheque_bank,
                "pdc_state": "held",
                "memo": self.env._(
                    "Replaces cheque %(cheque)s returned unpaid",
                    cheque=original.cheque_no or "",
                ),
            }
        )
        key = {original.PDC_MOVE_CONTEXT_KEY: True}
        replacement.with_context(**key).write({"replaces_payment_id": original.id})
        original.with_context(**key).write({"replacement_payment_id": replacement.id})
        original._pdc_move("replaced", reason=self.reason)
        original.message_post(
            body=self.env._(
                "Replaced by cheque %(cheque)s for %(amount)s, maturing %(date)s.",
                cheque=self.cheque_no,
                amount=f"{self.amount:,.2f}",
                date=self.maturity_date,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "res_id": replacement.id,
            "view_mode": "form",
        }
