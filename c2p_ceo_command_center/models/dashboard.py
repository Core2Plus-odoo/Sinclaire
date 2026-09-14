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
    vacant_market_rent = fields.Monetary(
        compute="_compute_portfolio",
        string="Revenue Foregone",
        help="Annual market rent of the units standing empty - what vacancy costs per year.",
    )
    avg_rent_per_unit = fields.Monetary(compute="_compute_portfolio", string="Average Rent")
    avg_rent_per_sqft = fields.Float(
        compute="_compute_portfolio",
        string="Rent per sq ft",
        help="Contracted annual rent divided by the leased area.",
    )

    # ---------------------------------------------------------------- leases
    active_lease_count = fields.Integer(compute="_compute_leases")
    expiring_lease_count = fields.Integer(compute="_compute_leases", string="Expiring in 90 Days")
    expiring_rent = fields.Monetary(
        compute="_compute_leases",
        string="Rent at Risk",
        help="Annual rent on leases expiring within the renewal horizon.",
    )
    expiring_30 = fields.Integer(compute="_compute_leases", string="Within 30 Days")
    expiring_60 = fields.Integer(compute="_compute_leases", string="31-60 Days")
    expiring_90 = fields.Integer(compute="_compute_leases", string="61-90 Days")
    lease_at_risk_rate = fields.Float(
        compute="_compute_leases",
        string="Portfolio at Risk %",
        help="Share of active leases expiring inside the renewal horizon.",
    )

    # ---------------------------------------------------------------- cheques
    pdc_held_amount = fields.Monetary(compute="_compute_cheques", string="Cheques in Hand")
    pdc_held_count = fields.Integer(compute="_compute_cheques")
    pdc_bounced_amount = fields.Monetary(compute="_compute_cheques", string="Bounced")
    pdc_bounced_count = fields.Integer(compute="_compute_cheques")
    pdc_deposited_amount = fields.Monetary(compute="_compute_cheques", string="Deposited")
    pdc_deposited_count = fields.Integer(compute="_compute_cheques")
    pdc_cleared_amount = fields.Monetary(compute="_compute_cheques", string="Cleared")
    pdc_cleared_count = fields.Integer(compute="_compute_cheques")
    bounce_rate = fields.Float(
        compute="_compute_cheques",
        string="Bounce Rate %",
        help="Bounced cheques as a share of those that reached a conclusion "
        "(cleared or bounced). Cheques still in hand are not counted.",
    )

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
        Lease = self.env["c2p.lease"]
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

            active = [*domain, ("state", "=", "active")]
            groups = Lease._read_group(active, [], ["__count", "annual_rent:sum"])
            lease_count = groups[0][0] if groups else 0
            contracted = (groups[0][1] or 0.0) if groups else 0.0
            rec.contracted_rent = rec.currency_id.round(contracted)
            rec.avg_rent_per_unit = rec.currency_id.round(contracted / lease_count if lease_count else 0.0)

            # What the empty units would earn at market rate.
            rec.vacant_market_rent = rec.currency_id.round(
                rec._sum(Unit._read_group([*domain, ("state", "=", "vacant")], [], ["market_rent:sum"]))
            )

            leased_area = rec._sum(Unit._read_group([*domain, ("state", "=", "occupied")], [], ["area_sqft:sum"]))
            rec.avg_rent_per_sqft = contracted / leased_area if leased_area else 0.0

    @api.depends("company_id")
    def _compute_leases(self):
        Lease = self.env["c2p.lease"]
        today = fields.Date.context_today(self)
        for rec in self:
            domain = rec._company_domain()
            rec.active_lease_count = Lease.search_count([*domain, ("state", "=", "active")])

            def window(start_day, end_day, _dom=domain, _today=today):
                return Lease._read_group(
                    [
                        *_dom,
                        ("state", "in", ("active", "notice")),
                        ("date_end", ">=", _today + relativedelta(days=start_day)),
                        ("date_end", "<=", _today + relativedelta(days=end_day)),
                    ],
                    [],
                    ["__count", "annual_rent:sum"],
                )

            for field_name, (start, end) in (
                ("expiring_30", (0, 30)),
                ("expiring_60", (31, 60)),
                ("expiring_90", (61, 90)),
            ):
                bucket = window(start, end)
                rec[field_name] = bucket[0][0] if bucket else 0

            groups = window(0, RENEWAL_HORIZON_DAYS)
            rec.expiring_lease_count = groups[0][0] if groups else 0
            rec.expiring_rent = rec.currency_id.round((groups[0][1] or 0.0) if groups else 0.0)
            rec.lease_at_risk_rate = (
                rec.expiring_lease_count / rec.active_lease_count * 100.0 if rec.active_lease_count else 0.0
            )

    @api.depends("company_id")
    def _compute_cheques(self):
        Payment = self.env["account.payment"]
        for rec in self:
            base = [("company_id", "=", rec.company_id.id), ("is_pdc", "=", True)]
            # One grouped query covers every cheque state.
            by_state = {
                state: (count, amount or 0.0)
                for state, count, amount in Payment._read_group(base, ["pdc_state"], ["__count", "amount:sum"])
            }

            def bucket(state, _by=by_state):
                return _by.get(state, (0, 0.0))

            for state, amount_field, count_field in (
                ("held", "pdc_held_amount", "pdc_held_count"),
                ("deposited", "pdc_deposited_amount", "pdc_deposited_count"),
                ("cleared", "pdc_cleared_amount", "pdc_cleared_count"),
                ("bounced", "pdc_bounced_amount", "pdc_bounced_count"),
            ):
                count, amount = bucket(state)
                rec[count_field] = count
                rec[amount_field] = rec.currency_id.round(amount)

            # Only cheques that reached a conclusion belong in the ratio;
            # counting those still in hand would flatter it.
            concluded = rec.pdc_cleared_count + rec.pdc_bounced_count
            rec.bounce_rate = rec.pdc_bounced_count / concluded * 100.0 if concluded else 0.0

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

    def action_open_vacant_market_rent(self):
        return self.action_open_vacant_units()

    def action_lease_expiry_profile(self):
        """Expiry by month - where the renewal workload actually falls."""
        return self._drill(
            self.env._("Lease Expiry Profile"),
            "c2p.lease",
            [*self._company_domain(), ("state", "in", ("active", "notice"))],
            view_mode="graph,pivot,list,form",
        )

    def action_rent_by_building(self):
        return self._drill(
            self.env._("Rent by Building"),
            "c2p.lease",
            [*self._company_domain(), ("state", "=", "active")],
            view_mode="pivot,graph,list,form",
        )

    def action_open_unit_mix(self):
        return self._drill(
            self.env._("Unit Mix"),
            "c2p.unit",
            self._company_domain(),
            view_mode="graph,pivot,kanban,list,form",
        )

    def action_open_cheque_register(self):
        return self._drill(
            self.env._("Cheque Register"),
            "account.payment",
            [("company_id", "=", self.company_id.id), ("is_pdc", "=", True)],
            view_mode="pivot,graph,list,form",
        )

    def action_open_active_leases(self):
        return self._drill(
            self.env._("Active Leases"),
            "c2p.lease",
            [*self._company_domain(), ("state", "=", "active")],
        )
