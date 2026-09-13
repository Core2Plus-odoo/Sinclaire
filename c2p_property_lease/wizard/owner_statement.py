from odoo import api, fields, models
from odoo.exceptions import UserError


class OwnerStatement(models.TransientModel):
    _name = "c2p.owner.statement"
    _description = "Landlord Statement"

    building_id = fields.Many2one("c2p.building", required=True)
    owner_id = fields.Many2one(related="building_id.owner_id", string="Landlord")
    company_id = fields.Many2one(related="building_id.company_id")
    currency_id = fields.Many2one(related="building_id.currency_id")
    date_from = fields.Date(required=True, default=lambda s: fields.Date.context_today(s).replace(day=1))
    date_to = fields.Date(required=True, default=lambda s: fields.Date.context_today(s))
    management_fee_pct = fields.Float(related="building_id.management_fee_pct", readonly=False)

    # Invoiced, not collected: these are posted customer invoices carrying the
    # building's analytic account. A cheque that later bounces does not reduce
    # this figure, so do not pay a landlord from it without checking the PDC
    # register.
    rent_invoiced = fields.Monetary(compute="_compute_totals", string="Rent Invoiced")
    expenses = fields.Monetary(compute="_compute_totals")
    management_fee = fields.Monetary(compute="_compute_totals")
    net_payable = fields.Monetary(compute="_compute_totals")

    fee_invoice_id = fields.Many2one("account.move", compute="_compute_fee_invoice", string="Management Fee Invoice")

    @api.constrains("date_from", "date_to")
    def _check_period(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(self.env._("The statement period ends before it starts."))

    @api.depends("building_id", "date_from", "date_to", "management_fee_pct")
    def _compute_totals(self):
        for rec in self:
            data = rec._collect()
            rec.rent_invoiced = data["rent"]
            rec.expenses = data["expenses"]
            rec.management_fee = data["fee"]
            rec.net_payable = data["net"]

    @api.depends("building_id", "date_from", "date_to")
    def _compute_fee_invoice(self):
        for rec in self:
            rec.fee_invoice_id = rec._existing_fee_invoice()

    def _existing_fee_invoice(self):
        """The fee invoice already raised for this building and period, if any."""
        self.ensure_one()
        if not self.building_id:
            return self.env["account.move"]
        return self.env["account.move"].search(
            [
                ("c2p_fee_building_id", "=", self.building_id.id),
                ("c2p_fee_date_from", "=", self.date_from),
                ("c2p_fee_date_to", "=", self.date_to),
                ("state", "!=", "cancel"),
            ],
            limit=1,
        )

    @staticmethod
    def _analytic_share(distribution, analytic_id):
        """Percentage of a move line allocated to one analytic account.

        Distribution keys may be comma-joined ids for a multi-plan allocation
        ("3,7"), so match on the individual ids rather than the whole key.
        """
        share = 0.0
        for key, percentage in (distribution or {}).items():
            if str(analytic_id) in str(key).split(","):
                share += percentage or 0.0
        return share

    def _collect(self):
        """Rent and expenses are identified by the building's analytic account."""
        self.ensure_one()
        analytic = self.building_id.analytic_account_id
        empty = {
            "rent": 0.0,
            "expenses": 0.0,
            "fee": 0.0,
            "net": 0.0,
            "rent_lines": self.env["account.move.line"],
            "exp_lines": self.env["account.move.line"],
        }
        if not analytic or not self.date_from or not self.date_to:
            return empty

        lines = self.env["account.move.line"].search(
            [
                ("parent_state", "=", "posted"),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("analytic_distribution", "in", [analytic.id]),
                # A management-fee invoice carries this building's analytic account
                # too. Counting it as rent would inflate the next period's fee.
                ("move_id.c2p_fee_building_id", "=", False),
            ]
        )
        rent_lines = lines.filtered(lambda line: line.move_id.move_type == "out_invoice")
        exp_lines = lines.filtered(lambda line: line.move_id.move_type == "in_invoice")

        def weighted(records):
            return sum(
                line.price_subtotal * self._analytic_share(line.analytic_distribution, analytic.id) / 100.0
                for line in records
            )

        currency = self.building_id.currency_id
        rent = currency.round(weighted(rent_lines))
        expenses = currency.round(weighted(exp_lines))
        fee = currency.round(rent * (self.management_fee_pct / 100.0))
        return {
            "rent": rent,
            "expenses": expenses,
            "fee": fee,
            "net": currency.round(rent - expenses - fee),
            "rent_lines": rent_lines,
            "exp_lines": exp_lines,
        }

    def action_print(self):
        """Print only. Raising the fee invoice is a separate, deliberate action."""
        self.ensure_one()
        if not self.building_id.analytic_account_id:
            raise UserError(
                self.env._(
                    "%s has no analytic account, so income and costs cannot be traced to it.",
                    self.building_id.name,
                )
            )
        return self.env.ref("c2p_property_lease.action_report_owner_statement").report_action(self)

    def action_create_fee_invoice(self):
        self.ensure_one()
        existing = self._existing_fee_invoice()
        if existing:
            raise UserError(
                self.env._(
                    "A management fee invoice for %(building)s covering %(start)s to %(end)s "
                    "already exists (%(invoice)s).",
                    building=self.building_id.name,
                    start=self.date_from,
                    end=self.date_to,
                    invoice=existing.display_name,
                )
            )
        if not self.management_fee:
            raise UserError(self.env._("There is no management fee to invoice for this period."))
        invoice = self._create_fee_invoice()
        return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": invoice.id, "view_mode": "form"}

    OWNER_INVOICE_JOURNAL_CODE = "OWNI"

    def _fee_journal(self, company):
        """Journal for management-fee invoices.

        Prefer the dedicated owner-invoice journal where the company has one
        (company 1 has OWNI, company 2 does not); otherwise fall back to that
        company's ordinary sales journal so the setup still works.
        """
        journals = self.env["account.journal"]
        dedicated = journals.search(
            [
                ("code", "=", self.OWNER_INVOICE_JOURNAL_CODE),
                ("type", "=", "sale"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        return dedicated or journals.search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1)

    def _create_fee_invoice(self):
        self.ensure_one()
        company = self.building_id.company_id
        template = self.env.ref("c2p_property_lease.product_property_management_fee", raise_if_not_found=False)
        product = template.product_variant_id if template else False
        if not product:
            raise UserError(
                self.env._(
                    "The 'Property Management Fee' service product is missing. "
                    "Reinstall or repair the module data before invoicing."
                )
            )
        journal = self._fee_journal(company)
        if not journal:
            raise UserError(
                self.env._(
                    "%s has no sales journal, so the management fee cannot be invoiced.",
                    company.display_name,
                )
            )
        analytic = self.building_id.analytic_account_id
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "company_id": company.id,
                "partner_id": self.owner_id.id,
                "journal_id": journal.id,
                "invoice_date": self.date_to,
                "c2p_fee_building_id": self.building_id.id,
                "c2p_fee_date_from": self.date_from,
                "c2p_fee_date_to": self.date_to,
                "ref": self.env._(
                    "Management fee - %(building)s - %(start)s to %(end)s",
                    building=self.building_id.name,
                    start=self.date_from,
                    end=self.date_to,
                ),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "name": self.env._(
                                "Management fee %(pct)s%% - %(building)s",
                                pct=self.management_fee_pct,
                                building=self.building_id.name,
                            ),
                            "quantity": 1,
                            "price_unit": self.management_fee,
                            "analytic_distribution": {str(analytic.id): 100.0} if analytic else False,
                        },
                    )
                ],
            }
        )
