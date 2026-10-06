from dateutil.relativedelta import relativedelta

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

from .unit import EARNING_STATES

CHEQUE_PLAN = {1: 12, 2: 6, 3: 4, 4: 3, 6: 2, 12: 1}  # cheques -> months per instalment

# BRD §3.2: Draft → Pending Approval → Offered → Awaiting Signature → Signed →
# Registration Pending → Active → Under Notice → Renewed/Expired/Terminated/
# Cancelled. Allowed transitions and roles are in docs/status_matrix.md.
LEASE_STATES = [
    ("draft", "Draft"),
    ("pending_approval", "Pending Approval"),
    ("offered", "Offered"),
    ("awaiting_signature", "Awaiting Signature"),
    ("signed", "Signed"),
    ("registration_pending", "Registration Pending"),
    ("active", "Active"),
    ("notice", "Under Notice"),
    ("renewed", "Renewed"),
    ("expired", "Expired"),
    ("terminated", "Terminated"),
    ("cancelled", "Cancelled"),
]

# Shared groups, for the same reason the unit has them: every report and cron
# needs one answer to "is this tenancy running?", and two places disagreeing is
# invisible until two screens differ.
#
# LIVE: the tenancy is running and charging rent. Exactly the ("active",
#   "notice") pair that was written out by hand in five places before.
# PRE_ACTIVE: agreed or being agreed, not yet running.
# CLOSED: finished, by any route.
# A cheque counts as received once it is physically in hand, and still counts
# once banked or cleared. A bounced cheque does not: the instrument exists but
# the money never arrived, which is precisely the situation BR-075 is about.
RECEIVED_CHEQUE_STATES = ("held", "deposited", "cleared")

LIVE_STATES = ("active", "notice")
PRE_ACTIVE_STATES = (
    "draft",
    "pending_approval",
    "offered",
    "awaiting_signature",
    "signed",
    "registration_pending",
)
CLOSED_STATES = ("renewed", "expired", "terminated", "cancelled")


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
            ("3", "3 Cheques"),
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
    # copy=False, which is NOT the One2many default. Without it `copy()` - which
    # is how a renewal is created - duplicates the tenant's cheque register onto
    # the successor lease: fabricated payment records against cheques that were
    # never written, and, since BR-075 reads this register, a renewal that walks
    # through the cheque gate on phantom cover.
    payment_ids = fields.One2many("account.payment", "lease_id", string="Cheques", copy=False)
    subscriptions_available = fields.Boolean(compute="_compute_subscriptions_available")
    pdc_count = fields.Integer(compute="_compute_pdc")
    pdc_pending = fields.Monetary(compute="_compute_pdc", string="Cheques Outstanding")

    # --- BR-075: is the cheque set complete? Stored so it can be searched and
    # reported on; a non-stored compute cannot appear in a domain at all.
    cheques_expected = fields.Integer(compute="_compute_cheque_cover", store=True)
    cheques_received = fields.Integer(compute="_compute_cheque_cover", store=True)
    cheque_cover = fields.Monetary(
        compute="_compute_cheque_cover",
        store=True,
        string="Rent Covered by Cheques",
    )
    cheque_shortfall = fields.Monetary(compute="_compute_cheque_cover", store=True)
    cheques_complete = fields.Boolean(compute="_compute_cheque_cover", store=True)
    # copy=False for the same reason as payment_ids, and with sharper teeth: a
    # renewal is made with copy(), and an *approved* exception copied onto the
    # successor would carry the approval for one tenancy over to another.
    cheque_exception_ids = fields.One2many(
        "c2p.lease.cheque.exception",
        "lease_id",
        string="Cheque Exceptions",
        copy=False,
    )
    cheque_exception_count = fields.Integer(compute="_compute_cheque_exceptions")
    has_open_cheque_exception = fields.Boolean(compute="_compute_cheque_exceptions")

    state = fields.Selection(
        LEASE_STATES,
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

    @api.depends(
        "cheque_count",
        "annual_rent",
        "currency_id",
        "payment_ids.pdc_state",
        "payment_ids.amount",
    )
    def _compute_cheque_cover(self):
        """Both halves of "all cheques received" (BR-075).

        The count alone is not enough: four cheques covering half the rent is a
        complete-looking set and an incomplete one. The count alone is not
        redundant either - twelve cheques' worth of value in one instrument is
        not the agreed schedule. So completeness needs both, and the shortfall
        reported to the approver is the money, because that is the exposure.
        """
        for rec in self:
            received = rec.payment_ids.filtered(lambda p: p.pdc_state in RECEIVED_CHEQUE_STATES)
            cover = sum(received.mapped("amount"))
            rec.cheques_expected = int(rec.cheque_count or 0)
            rec.cheques_received = len(received)
            rec.cheque_cover = cover
            shortfall = (rec.annual_rent or 0.0) - cover
            currency = rec.currency_id
            rec.cheque_shortfall = max(currency.round(shortfall) if currency else shortfall, 0.0)
            covered = currency.compare_amounts(cover, rec.annual_rent) >= 0 if currency else cover >= rec.annual_rent
            rec.cheques_complete = bool(rec.cheques_received >= rec.cheques_expected and covered)

    @api.depends("cheque_exception_ids.state")
    def _compute_cheque_exceptions(self):
        for rec in self:
            rec.cheque_exception_count = len(rec.cheque_exception_ids)
            rec.has_open_cheque_exception = any(e.state in ("draft", "approved") for e in rec.cheque_exception_ids)

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

    # The context key `_activate_as_loaded` sets. Writing it by hand is
    # possible, which is the point of naming it after what it means: a caller
    # that sets this is asserting the tenancy is being loaded, not transacted.
    LOADED_CONTEXT_KEY = "c2p_lease_loaded"

    def write(self, vals):
        """Refuse a move into Active that BR-075 would not allow.

        `action_activate` is where the gate belongs, but it is not the only way
        to reach Active: `state` is a writable field, and the form's statusbar
        lets a user click straight to it. Without this, the control would guard
        the button and not the transition.

        Deliberately *not* extended to `create`. The migration plan loads
        running tenancies as records (object 14) before their cheques (object
        16), so creating an already-active lease is the import path and has to
        stay open; this is the boundary between loading a tenancy and starting
        one. Which means the gate is a workflow control, not a permission
        boundary - anyone who may create a lease may create an active one.
        """
        if vals.get("state") == "active":
            for rec in self:
                if rec.state == "active" or self.env.context.get(self.LOADED_CONTEXT_KEY):
                    continue
                if not (rec.cheques_complete or rec._approved_cheque_exception()):
                    raise UserError(
                        self.env._(
                            "%(lease)s cannot be made Active with %(count)s cheque(s) "
                            "outstanding. BRD §5.1 requires an exception approved by the "
                            "Leasing Manager or CEO.",
                            lease=rec.display_name,
                            count=max(rec.cheques_expected - rec.cheques_received, 0),
                        )
                    )
        return super().write(vals)

    # ------------------------------------------------------------------ actions
    def action_activate(self):
        """The leasing process's activation, and the gated one.

        A tenancy loaded from a legacy system is already running and is not
        passing through this gate - see `_activate_as_loaded`.
        """
        for rec in self:
            if rec.state not in PRE_ACTIVE_STATES:
                raise UserError(
                    self.env._(
                        "%(lease)s is %(state)s and cannot be activated.",
                        lease=rec.display_name,
                        state=dict(self._fields["state"].selection)[rec.state],
                    )
                )
            if rec.unit_id.state in EARNING_STATES and rec.unit_id.current_lease_id != rec:
                raise UserError(
                    self.env._(
                        "Unit %(unit)s is already taken (%(state)s) by %(tenant)s.",
                        unit=rec.unit_id.display_name,
                        state=dict(rec.unit_id._fields["state"].selection)[rec.unit_id.state],
                        tenant=rec.unit_id.current_lease_id.tenant_id.name or "another lease",
                    )
                )
            exception = rec._approved_cheque_exception()
            if not rec.cheques_complete and not exception:
                raise UserError(
                    self.env._(
                        "%(lease)s is %(count)s cheque(s) short, leaving %(amount)s of the "
                        "annual rent uncovered. BRD §5.1 allows activation anyway only under "
                        "an exception approved by the Leasing Manager or CEO. Register the "
                        "missing cheques, or request an exception from this lease.",
                        lease=rec.display_name,
                        count=max(rec.cheques_expected - rec.cheques_received, 0),
                        amount=f"{rec.cheque_shortfall:,.2f}",
                    )
                )
            rec.state = "active"
            rec.unit_id.write({"state": "occupied", "current_lease_id": rec.id})
            if exception and not rec.cheques_complete:
                exception.activation_date = fields.Datetime.now()
                rec.message_post(
                    body=self.env._(
                        "Activated with %(count)s cheque(s) outstanding under the exception "
                        "approved by %(approver)s, due %(deadline)s.",
                        count=exception.missing_cheque_count,
                        approver=exception.approved_by_id.name,
                        deadline=exception.deadline,
                    )
                )

    def _approved_cheque_exception(self):
        """The approved exception standing behind a short activation, if any."""
        self.ensure_one()
        return self.cheque_exception_ids.filtered(lambda e: e.state == "approved")[:1]

    def _activate_as_loaded(self):
        """Mark an already-running tenancy active without the BR-075 gate.

        This is the data-load path, not the leasing process. The migration plan
        loads active tenancies (object 14) before their cheques (object 16),
        because that is the order the dependencies allow - so a migrated
        tenancy is legitimately short of cheques at the moment it is created,
        and refusing it would make the opening load impossible.

        It is deliberately not a parameter on `action_activate`: a flag that
        skips a control tends to spread to the callers that find the control
        inconvenient. Only the sample loader and the import tooling use this,
        and a test asserts that the user-facing path still refuses.
        """
        for rec in self:
            rec.with_context(**{self.LOADED_CONTEXT_KEY: True}).state = "active"
            rec.unit_id.write({"state": "occupied", "current_lease_id": rec.id})

    def action_request_cheque_exception(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Request Cheque Exception"),
            "res_model": "c2p.lease.cheque.exception",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lease_id": self.id,
                "default_responsible_user_id": self.env.uid,
            },
        }

    def action_view_cheque_exceptions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Cheque Exceptions"),
            "res_model": "c2p.lease.cheque.exception",
            "view_mode": "list,form",
            "domain": [("lease_id", "=", self.id)],
            "context": {"default_lease_id": self.id},
        }

    def action_give_notice(self):
        for rec in self:
            if rec.state not in LIVE_STATES:
                raise UserError(
                    self.env._(
                        "Notice can only be served on a running tenancy, not one that is %(state)s.", state=rec.state
                    )
                )
            rec.state = "notice"
            rec.unit_id.state = "notice"

    # --- the pre-active path, BRD §3.2 -------------------------------------
    # Transitions are methods so each is a place to hang the gate the BRD asks
    # for. BR-075 now hangs on activation, above. The two that remain are
    # BR-036 (approval before an off-pricing offer is sent) and BR-072 (the
    # leasing approval rule), and both are blocked on OD-06: the BRD gives the
    # principles but not the approvers or the limits, and inventing either
    # would bake a guess into a control. So `action_approve` below records that
    # an approval happened without yet asserting who was entitled to give it.

    def _advance(self, target, allowed_from):
        for rec in self:
            if rec.state not in allowed_from:
                raise UserError(
                    self.env._(
                        "%(lease)s cannot move from %(current)s to %(target)s.",
                        lease=rec.display_name,
                        current=dict(self._fields["state"].selection)[rec.state],
                        target=dict(self._fields["state"].selection)[target],
                    )
                )
        self.state = target

    def action_submit_for_approval(self):
        self._advance("pending_approval", ("draft",))

    def action_approve(self):
        """Leasing Director or Manager approves off-standard terms (BR-072)."""
        self._advance("offered", ("draft", "pending_approval"))

    def action_send_for_signature(self):
        self._advance("awaiting_signature", ("offered",))

    def action_mark_signed(self):
        """Signed is the point of no return: BRD §5.1.2 makes the signed
        document immutable, so there is no transition back out of here."""
        self._advance("signed", ("awaiting_signature",))

    def action_submit_registration(self):
        self._advance("registration_pending", ("signed",))

    def action_cancel(self):
        self._advance("cancelled", ("draft", "pending_approval", "offered", "awaiting_signature"))

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
            leases = self.search([("state", "in", LIVE_STATES), ("date_end", "=", target)])
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
        expired = self.search([("state", "in", LIVE_STATES), ("date_end", "<", today)])
        expired.write({"state": "expired"})
        for lease in expired:
            if lease.unit_id.current_lease_id == lease:
                lease.unit_id.write({"state": "vacant", "current_lease_id": False})


class SaleOrder(models.Model):
    _inherit = "sale.order"

    c2p_lease_id = fields.Many2one("c2p.lease", string="Lease", copy=False, index=True)
