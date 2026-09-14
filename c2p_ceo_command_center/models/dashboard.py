from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

# A lease inside this window is close enough to expiry to need a decision.
RENEWAL_HORIZON_DAYS = 90


class CeoDashboard(models.TransientModel):
    _name = "c2p.ceo.dashboard"
    _description = "CEO Command Center"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1),
        help="Year-to-date figures are measured from here.",
    )
    date_to = fields.Date(required=True, default=fields.Date.context_today)

    # ---------------------------------------------------------------- portfolio
    building_count = fields.Integer(compute="_compute_portfolio")
    unit_count = fields.Integer(compute="_compute_portfolio")
    occupied_count = fields.Integer(compute="_compute_portfolio")
    vacant_count = fields.Integer(compute="_compute_portfolio")
    occupancy_rate = fields.Float(compute="_compute_portfolio", string="Occupancy %")
    contracted_rent = fields.Monetary(compute="_compute_portfolio")

    # ---------------------------------------------------------------- leases
    active_lease_count = fields.Integer(compute="_compute_leases")
    expiring_lease_count = fields.Integer(compute="_compute_leases", string="Expiring in 90 Days")
    expiring_rent = fields.Monetary(
        compute="_compute_leases",
        string="Rent at Risk",
        help="Annual rent on leases expiring within the renewal horizon.",
    )

    # ---------------------------------------------------------------- cheques
    pdc_held_amount = fields.Monetary(compute="_compute_cheques", string="Cheques in Hand")
    pdc_held_count = fields.Integer(compute="_compute_cheques")
    pdc_bounced_amount = fields.Monetary(compute="_compute_cheques", string="Bounced")
    pdc_bounced_count = fields.Integer(compute="_compute_cheques")

    # ---------------------------------------------------------------- income
    rent_invoiced = fields.Monetary(
        compute="_compute_income",
        help="Posted customer invoices in the period. Invoiced, not collected - "
        "a cheque that later bounces does not reduce this.",
    )
    fee_invoiced = fields.Monetary(compute="_compute_income", string="Management Fees")
    overdue_receivable = fields.Monetary(compute="_compute_income", string="Overdue")

    # ------------------------------------------------------------------ helpers
    def _company_domain(self):
        return [("company_id", "in", [False, self.company_id.id])]

    @staticmethod
    def _sum(groups):
        """First aggregate of a groupby-less _read_group, or zero."""
        return groups[0][0] or 0.0 if groups else 0.0

    # ----------------------------------------------------------------- computes
    @api.depends("company_id")
    def _compute_portfolio(self):
        Unit = self.env["c2p.unit"]
        Building = self.env["c2p.building"]
        for rec in self:
            domain = rec._company_domain()
            rec.building_count = Building.search_count(domain)
            # One grouped query for the whole state breakdown rather than a
            # search_count per state.
            by_state = dict(Unit._read_group(domain, ["state"], ["__count"]))
            rec.unit_count = sum(by_state.values())
            rec.occupied_count = by_state.get("occupied", 0)
            rec.vacant_count = by_state.get("vacant", 0)
            rec.occupancy_rate = rec.occupied_count / rec.unit_count * 100.0 if rec.unit_count else 0.0
            rec.contracted_rent = rec.currency_id.round(
                rec._sum(
                    self.env["c2p.lease"]._read_group([*domain, ("state", "=", "active")], [], ["annual_rent:sum"])
                )
            )

    @api.depends("company_id")
    def _compute_leases(self):
        Lease = self.env["c2p.lease"]
        today = fields.Date.context_today(self)
        horizon = today + relativedelta(days=RENEWAL_HORIZON_DAYS)
        for rec in self:
            domain = rec._company_domain()
            rec.active_lease_count = Lease.search_count([*domain, ("state", "=", "active")])
            expiring = [
                *domain,
                ("state", "in", ("active", "notice")),
                ("date_end", ">=", today),
                ("date_end", "<=", horizon),
            ]
            groups = Lease._read_group(expiring, [], ["__count", "annual_rent:sum"])
            rec.expiring_lease_count = groups[0][0] if groups else 0
            rec.expiring_rent = rec.currency_id.round((groups[0][1] or 0.0) if groups else 0.0)

    @api.depends("company_id")
    def _compute_cheques(self):
        Payment = self.env["account.payment"]
        for rec in self:
            base = [("company_id", "=", rec.company_id.id), ("is_pdc", "=", True)]
            for state, amount_field, count_field in (
                ("held", "pdc_held_amount", "pdc_held_count"),
                ("bounced", "pdc_bounced_amount", "pdc_bounced_count"),
            ):
                groups = Payment._read_group([*base, ("pdc_state", "=", state)], [], ["__count", "amount:sum"])
                rec[count_field] = groups[0][0] if groups else 0
                rec[amount_field] = rec.currency_id.round((groups[0][1] or 0.0) if groups else 0.0)

    @api.depends("company_id", "date_from", "date_to")
    def _compute_income(self):
        Line = self.env["account.move.line"]
        today = fields.Date.context_today(self)
        for rec in self:
            period = [
                ("company_id", "=", rec.company_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", rec.date_from),
                ("date", "<=", rec.date_to),
                ("move_id.move_type", "=", "out_invoice"),
                ("display_type", "=", "product"),
            ]
            # Management-fee invoices carry c2p_fee_building_id; counting them
            # as rent would double-count our own income.
            rec.rent_invoiced = rec.currency_id.round(
                rec._sum(
                    Line._read_group(
                        [*period, ("move_id.c2p_fee_building_id", "=", False)],
                        [],
                        ["price_subtotal:sum"],
                    )
                )
            )
            rec.fee_invoiced = rec.currency_id.round(
                rec._sum(
                    Line._read_group(
                        [*period, ("move_id.c2p_fee_building_id", "!=", False)],
                        [],
                        ["price_subtotal:sum"],
                    )
                )
            )
            rec.overdue_receivable = rec.currency_id.round(
                rec._sum(
                    Line._read_group(
                        [
                            ("company_id", "=", rec.company_id.id),
                            ("parent_state", "=", "posted"),
                            ("account_id.account_type", "=", "asset_receivable"),
                            ("full_reconcile_id", "=", False),
                            ("date_maturity", "<", today),
                        ],
                        [],
                        ["amount_residual:sum"],
                    )
                )
            )

    # ------------------------------------------------------------------ actions
    def _drill(self, name, model, domain, view_mode="list,form"):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": view_mode,
            "domain": domain,
            "context": {"create": False},
        }

    def action_open_vacant_units(self):
        return self._drill(
            self.env._("Vacant Units"),
            "c2p.unit",
            [*self._company_domain(), ("state", "=", "vacant")],
            view_mode="kanban,list,form",
        )

    def action_open_expiring_leases(self):
        today = fields.Date.context_today(self)
        return self._drill(
            self.env._("Leases Expiring in %s Days", RENEWAL_HORIZON_DAYS),
            "c2p.lease",
            [
                *self._company_domain(),
                ("state", "in", ("active", "notice")),
                ("date_end", ">=", today),
                ("date_end", "<=", today + relativedelta(days=RENEWAL_HORIZON_DAYS)),
            ],
        )

    def action_open_bounced_cheques(self):
        return self._drill(
            self.env._("Bounced Cheques"),
            "account.payment",
            [
                ("company_id", "=", self.company_id.id),
                ("is_pdc", "=", True),
                ("pdc_state", "=", "bounced"),
            ],
        )

    def action_open_cheques_in_hand(self):
        return self._drill(
            self.env._("Cheques in Hand"),
            "account.payment",
            [
                ("company_id", "=", self.company_id.id),
                ("is_pdc", "=", True),
                ("pdc_state", "=", "held"),
            ],
        )

    def action_open_active_leases(self):
        return self._drill(
            self.env._("Active Leases"),
            "c2p.lease",
            [*self._company_domain(), ("state", "=", "active")],
        )
