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
    head_lease_cost = fields.Monetary(
        compute="_compute_underwriting",
        string="Committed to Landlords",
        help="Annual amount owed under active head leases, payable whether or not the units are let.",
    )
    gross_margin = fields.Monetary(
        compute="_compute_underwriting",
        help="Contracted tenant rent less what we owe landlords.",
    )
    margin_pct = fields.Float(compute="_compute_underwriting", string="Margin %")
    coverage_ratio = fields.Float(
        compute="_compute_underwriting",
        string="Coverage",
        help="Contracted rent divided by the landlord commitment. Below 1.0 the portfolio is not covering its cost.",
    )
    breakeven_occupancy = fields.Float(compute="_compute_underwriting", string="Break-even Occupancy %")
    buildings_below_cost = fields.Integer(
        compute="_compute_underwriting",
        string="Buildings Below Cost",
        help="Active head leases where contracted rent does not cover the landlord commitment.",
    )

    # --- landlord side of the cheque book ---
    landlord_due_30 = fields.Monetary(compute="_compute_landlord_cheques", string="Due in 30 Days")
    landlord_due_90 = fields.Monetary(compute="_compute_landlord_cheques", string="Due in 90 Days")
    landlord_outstanding = fields.Monetary(compute="_compute_landlord_cheques", string="Issued, Not Cleared")
    landlord_bounced_count = fields.Integer(compute="_compute_landlord_cheques", string="Our Cheques Bounced")

    # --- can we meet them? ---
    tenant_inflow_90 = fields.Monetary(compute="_compute_cash", string="Tenant Cheques In")
    net_position_90 = fields.Monetary(
        compute="_compute_cash",
        string="Net 90-Day Position",
        help="Tenant cheques maturing in the next 90 days less landlord cheques "
        "falling due in the same window. Negative means the gap needs funding.",
    )
    facility_limit = fields.Monetary(compute="_compute_cash", string="Facility Limit")
    facility_available = fields.Monetary(compute="_compute_cash", string="Headroom")
    facility_utilisation = fields.Float(compute="_compute_cash", string="Facilities Used %")
    funding_gap = fields.Monetary(
        compute="_compute_cash",
        help="Shortfall left after available banking facilities are applied. Anything above zero needs a decision.",
    )
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
            rec.rent_invoiced = rec.currency_id.round(rec._sum(Line._read_group(period, [], ["price_subtotal:sum"])))
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

    @api.depends("company_id")
    def _compute_underwriting(self):
        HeadLease = self.env["c2p.head.lease"]
        for rec in self:
            active = [
                ("company_id", "=", rec.company_id.id),
                ("state", "=", "active"),
            ]
            cost = rec._sum(HeadLease._read_group(active, [], ["annual_amount:sum"]))
            rec.head_lease_cost = rec.currency_id.round(cost)
            income = rec.contracted_rent
            rec.gross_margin = rec.currency_id.round(income - cost)
            rec.margin_pct = (rec.gross_margin / income * 100.0) if income else 0.0
            rec.coverage_ratio = (income / cost) if cost else 0.0

            potential = rec._sum(
                self.env["c2p.building"]._read_group(rec._company_domain(), [], ["potential_rent:sum"])
            )
            rec.breakeven_occupancy = (cost / potential * 100.0) if potential else 0.0
            # Per-building, because a portfolio that covers overall can still
            # hide a building bleeding money.
            rec.buildings_below_cost = len(
                HeadLease.search(active).filtered(lambda hl: hl.annual_amount and hl.coverage_ratio < 1.0)
            )

    @api.depends("company_id")
    def _compute_landlord_cheques(self):
        Payment = self.env["account.payment"]
        today = fields.Date.context_today(self)
        for rec in self:
            base = [
                ("company_id", "=", rec.company_id.id),
                ("head_lease_id", "!=", False),
            ]
            pending = [*base, ("pdc_state", "in", ("held", "deposited"))]
            rec.landlord_outstanding = rec.currency_id.round(rec._sum(Payment._read_group(pending, [], ["amount:sum"])))
            for days, field_name in ((30, "landlord_due_30"), (90, "landlord_due_90")):
                rec[field_name] = rec.currency_id.round(
                    rec._sum(
                        Payment._read_group(
                            [
                                *pending,
                                ("maturity_date", ">=", today),
                                ("maturity_date", "<=", today + relativedelta(days=days)),
                            ],
                            [],
                            ["amount:sum"],
                        )
                    )
                )
            groups = Payment._read_group([*base, ("pdc_state", "=", "bounced")], [], ["__count"])
            rec.landlord_bounced_count = groups[0][0] if groups else 0

    @api.depends("company_id")
    def _compute_cash(self):
        Payment = self.env["account.payment"]
        Facility = self.env["c2p.bank.facility"]
        today = fields.Date.context_today(self)
        for rec in self:
            horizon = today + relativedelta(days=90)
            inflow = rec._sum(
                Payment._read_group(
                    [
                        ("company_id", "=", rec.company_id.id),
                        ("lease_id", "!=", False),
                        ("pdc_state", "in", ("held", "deposited")),
                        ("maturity_date", ">=", today),
                        ("maturity_date", "<=", horizon),
                    ],
                    [],
                    ["amount:sum"],
                )
            )
            rec.tenant_inflow_90 = rec.currency_id.round(inflow)
            rec.net_position_90 = rec.currency_id.round(inflow - rec.landlord_due_90)

            facilities = Facility._read_group(
                [("company_id", "=", rec.company_id.id)],
                [],
                ["limit_amount:sum", "available_amount:sum"],
            )
            limit = (facilities[0][0] or 0.0) if facilities else 0.0
            available = (facilities[0][1] or 0.0) if facilities else 0.0
            rec.facility_limit = rec.currency_id.round(limit)
            rec.facility_available = rec.currency_id.round(available)
            rec.facility_utilisation = (limit - available) / limit * 100.0 if limit else 0.0
            # Only a negative position is a gap; a surplus is not a negative gap.
            shortfall = max(0.0, -rec.net_position_90)
            rec.funding_gap = rec.currency_id.round(max(0.0, shortfall - available))

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

    def action_open_head_leases(self):
        return self._drill(
            self.env._("Head Leases"),
            "c2p.head.lease",
            [("company_id", "=", self.company_id.id), ("state", "=", "active")],
        )

    def action_open_landlord_cheques(self):
        return self._drill(
            self.env._("Landlord Cheques"),
            "account.payment",
            [
                ("company_id", "=", self.company_id.id),
                ("head_lease_id", "!=", False),
                ("pdc_state", "in", ("held", "deposited")),
            ],
        )

    def action_open_bank_facilities(self):
        return self._drill(
            self.env._("Banking Facilities"),
            "c2p.bank.facility",
            [("company_id", "=", self.company_id.id)],
        )

    def action_open_active_leases(self):
        return self._drill(
            self.env._("Active Leases"),
            "c2p.lease",
            [*self._company_domain(), ("state", "=", "active")],
        )
