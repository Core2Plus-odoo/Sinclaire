from dateutil.relativedelta import relativedelta

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

CHEQUE_PLAN = {1: 12, 2: 6, 4: 3, 6: 2, 12: 1}  # cheques -> months per instalment


class C2pLease(models.Model):
    _name = "c2p.lease"
    _description = "Tenancy Lease"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_end desc, id desc"
    _check_company_auto = True

    name = fields.Char(default="New", copy=False, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    tenant_id = fields.Many2one("res.partner", string="Tenant", required=True, tracking=True)
    unit_id = fields.Many2one("c2p.unit", required=True, tracking=True)
    building_id = fields.Many2one(related="unit_id.building_id", store=True)
    owner_id = fields.Many2one(related="building_id.owner_id", string="Landlord", store=True)

    date_start = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    annual_rent = fields.Monetary(required=True, tracking=True)
    cheque_count = fields.Selection(
        [
            ("1", "1 Cheque (Annual)"),
            ("2", "2 Cheques"),
            ("4", "4 Cheques (Quarterly)"),
            ("6", "6 Cheques"),
            ("12", "12 Cheques (Monthly)"),
        ],
        default="4",
        required=True,
        string="Payment Cheques",
    )
    instalment_amount = fields.Monetary(compute="_compute_instalment", store=True)
    security_deposit = fields.Monetary(help="Typically 5% of annual rent for unfurnished residential.")
    commission = fields.Monetary(help="Leasing commission charged to the tenant, usually 5% of annual rent.")

    is_commercial = fields.Boolean(
        compute="_compute_is_commercial",
        store=True,
        readonly=False,
        help="Commercial leases are standard-rated at 5% VAT. Residential rent is exempt.",
    )

    ejari_no = fields.Char(string="Ejari No.", tracking=True)
    ejari_date = fields.Date(string="Ejari Registered On")
    dewa_no = fields.Char(string="DEWA Premise No.")

    subscription_id = fields.Many2one("sale.order", string="Rent Subscription", copy=False, readonly=True)
    payment_ids = fields.One2many("account.payment", "lease_id", string="Cheques")
    subscriptions_available = fields.Boolean(compute="_compute_subscriptions_available")
    pdc_count = fields.Integer(compute="_compute_pdc")
    pdc_pending = fields.Monetary(compute="_compute_pdc", string="Cheques Outstanding")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("notice", "Notice Given"),
            ("expired", "Expired"),
            ("terminated", "Terminated"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    days_to_expiry = fields.Integer(compute="_compute_days_to_expiry", search="_search_days_to_expiry")
    renewed_from_id = fields.Many2one("c2p.lease", copy=False, readonly=True)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end <= rec.date_start:
                raise ValidationError(self.env._("A lease must end after it starts."))

    @api.depends("annual_rent", "cheque_count")
    def _compute_instalment(self):
        for rec in self:
            n = int(rec.cheque_count or 1)
            amount = rec.annual_rent / n if n else 0.0
            rec.instalment_amount = rec.currency_id.round(amount) if rec.currency_id else amount

    @api.depends("unit_id.unit_type")
    def _compute_is_commercial(self):
        for rec in self:
            rec.is_commercial = rec.unit_id.unit_type in ("shop", "office")

    @api.depends("payment_ids.state", "payment_ids.amount")
    def _compute_pdc(self):
        for rec in self:
            rec.pdc_count = len(rec.payment_ids)
            rec.pdc_pending = sum(
                rec.payment_ids.filtered(lambda p: p.state in ("draft", "in_process")).mapped("amount")
            )

    def _compute_days_to_expiry(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.days_to_expiry = (rec.date_end - today).days if rec.date_end else 0

    def _search_days_to_expiry(self, operator, value):
        today = fields.Date.context_today(self)
        return [("date_end", operator, today + relativedelta(days=value))]

    @api.onchange("date_start")
    def _onchange_date_start(self):
        if self.date_start and not self.date_end:
            self.date_end = self.date_start + relativedelta(years=1, days=-1)

    @api.onchange("unit_id")
    def _onchange_unit(self):
        if self.unit_id:
            self.annual_rent = self.annual_rent or self.unit_id.market_rent
            self.dewa_no = self.unit_id.dewa_no

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("c2p.lease") or "New"
        return super().create(vals_list)

    # ------------------------------------------------------------------ actions
    def action_activate(self):
        for rec in self:
            if rec.unit_id.state == "occupied" and rec.unit_id.current_lease_id != rec:
                raise UserError(
                    self.env._(
                        "Unit %(unit)s is already occupied by %(tenant)s.",
                        unit=rec.unit_id.display_name,
                        tenant=rec.unit_id.current_lease_id.tenant_id.name,
                    )
                )
            rec.state = "active"
            rec.unit_id.write({"state": "occupied", "current_lease_id": rec.id})

    def action_give_notice(self):
        for rec in self:
            rec.state = "notice"
            rec.unit_id.state = "notice"

    def _rent_product(self):
        """Resolve the rent product by XML ID - `name` is translatable."""
        xmlid = (
            "c2p_property_lease.product_commercial_rent"
            if self.is_commercial
            else "c2p_property_lease.product_residential_rent"
        )
        template = self.env.ref(xmlid, raise_if_not_found=False)
        product = template.product_variant_id if template else False
        if not product:
            raise UserError(
                self.env._(
                    "The rent service product (%s) is missing. Reinstall or repair "
                    "the module data before generating the subscription.",
                    xmlid,
                )
            )
        return product

    @api.model
    def _subscriptions_installed(self):
        """Subscriptions (Enterprise) is a soft dependency - it may be absent."""
        return "sale.subscription.plan" in self.env

    @api.depends_context("uid")
    def _compute_subscriptions_available(self):
        available = self._subscriptions_installed()
        for rec in self:
            rec.subscriptions_available = available

    def _find_subscription_plan(self):
        """Plan whose billing period matches the cheque schedule.

        Prefer a plan named for rent: a database can hold both a generic
        "Monthly" plan and a "Monthly Rent (12 cheques)" plan with the same
        period, and the rent-specific one is the intended match.
        """
        self.ensure_one()
        months = CHEQUE_PLAN[int(self.cheque_count)]
        Plan = self.env["sale.subscription.plan"]
        periods = [("month", months)]
        if months == 12:
            periods.append(("year", 1))
        for unit, value in periods:
            plans = Plan.search([("billing_period_unit", "=", unit), ("billing_period_value", "=", value)])
            if not plans:
                continue
            preferred = plans.filtered(lambda p: "rent" in (p.name or "").lower())
            return (preferred or plans)[0]
        return Plan

    def action_create_subscription(self):
        """Generate the recurring rent subscription matching the cheque schedule."""
        self.ensure_one()
        if not self._subscriptions_installed():
            raise UserError(
                self.env._(
                    "Rent subscriptions need the Subscriptions app, which is not "
                    "installed on this database. Everything else on the lease works "
                    "without it."
                )
            )
        if self.subscription_id:
            raise UserError(self.env._("A rent subscription already exists for this lease."))
        plan = self._find_subscription_plan()
        if not plan:
            raise UserError(self.env._("No subscription plan matches this cheque schedule."))
        product = self._rent_product()
        analytic = self.building_id.analytic_account_id
        # Creating with plan_id and confirming is enough: is_subscription and
        # subscription_state ("3_progress") follow from action_confirm().
        order = self.env["sale.order"].create(
            {
                "partner_id": self.tenant_id.id,
                "company_id": self.company_id.id,
                "plan_id": plan.id,
                "c2p_lease_id": self.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "name": f"{product.name} – Unit {self.unit_id.name}, {self.building_id.name}",
                            "product_uom_qty": 1,
                            "price_unit": self.instalment_amount,
                            "analytic_distribution": {str(analytic.id): 100.0} if analytic else False,
                        },
                    )
                ],
            }
        )
        order.action_confirm()
        self.subscription_id = order.id
        return self._open_record("sale.order", order.id)

    def action_register_pdcs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Register Post-Dated Cheques",
            "res_model": "c2p.pdc.register",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lease_id": self.id},
        }

    def action_renew(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Renew Lease",
            "res_model": "c2p.lease.renew",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lease_id": self.id},
        }

    def action_terminate(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Terminate Lease",
            "res_model": "c2p.lease.terminate",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lease_id": self.id},
        }

    def action_view_pdcs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Cheques",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("lease_id", "=", self.id)],
            "context": {"default_lease_id": self.id},
        }

    def _open_record(self, model, res_id):
        return {"type": "ir.actions.act_window", "res_model": model, "res_id": res_id, "view_mode": "form"}

    # ------------------------------------------------------------------ cron
    @api.model
    def _cron_lease_expiry_alerts(self):
        """Raise a renewal activity 90, 60 and 30 days before expiry."""
        today = fields.Date.context_today(self)
        for days in (90, 60, 30):
            target = today + relativedelta(days=days)
            leases = self.search([("state", "in", ("active", "notice")), ("date_end", "=", target)])
            if not leases:
                continue
            summary = f"Lease expires in {days} days"
            existing = set(
                self.env["mail.activity"]
                .search(
                    [
                        ("res_model", "=", "c2p.lease"),
                        ("res_id", "in", leases.ids),
                        ("summary", "=", summary),
                    ]
                )
                .mapped("res_id")
            )
            for lease in leases:
                if lease.id in existing:
                    continue
                lease.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=summary,
                    note=(
                        f"{lease.unit_id.display_name} – {lease.tenant_id.name}. "
                        f"Confirm renewal intent and check the RERA rental index before proposing an increase."
                    ),
                    date_deadline=today,
                )

    @api.model
    def _cron_expire_leases(self):
        today = fields.Date.context_today(self)
        expired = self.search([("state", "in", ("active", "notice")), ("date_end", "<", today)])
        expired.write({"state": "expired"})
        for lease in expired:
            if lease.unit_id.current_lease_id == lease:
                lease.unit_id.write({"state": "vacant", "current_lease_id": False})


class SaleOrder(models.Model):
    _inherit = "sale.order"

    c2p_lease_id = fields.Many2one("c2p.lease", string="Lease", copy=False, index=True)
