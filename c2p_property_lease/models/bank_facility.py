from odoo import api
from odoo import fields
from odoo import models


class BankFacility(models.Model):
    """Credit lines available to fund the gap between landlord cheques going
    out and tenant cheques coming in."""

    _name = "c2p.bank.facility"
    _description = "Banking Facility"
    _order = "bank_id, name"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    bank_id = fields.Many2one("res.bank", string="Bank", required=True)
    journal_id = fields.Many2one(
        "account.journal",
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        help="The account this facility is attached to, where it has one.",
    )
    facility_type = fields.Selection(
        [
            ("overdraft", "Overdraft"),
            ("cheque_discounting", "Cheque Discounting"),
            ("term_loan", "Term Loan"),
            ("guarantee", "Bank Guarantee"),
            ("other", "Other"),
        ],
        default="overdraft",
        required=True,
    )
    limit_amount = fields.Monetary(string="Limit", required=True)
    utilised_amount = fields.Monetary(string="Utilised")
    available_amount = fields.Monetary(compute="_compute_available", store=True)
    utilisation_pct = fields.Float(compute="_compute_available", store=True, string="Utilised %")
    review_date = fields.Date(help="When the facility is next reviewed or expires.")
    active = fields.Boolean(default=True)

    @api.depends("limit_amount", "utilised_amount")
    def _compute_available(self):
        for rec in self:
            available = (rec.limit_amount or 0.0) - (rec.utilised_amount or 0.0)
            rec.available_amount = rec.currency_id.round(available) if rec.currency_id else available
            rec.utilisation_pct = rec.utilised_amount / rec.limit_amount * 100.0 if rec.limit_amount else 0.0
