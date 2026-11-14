from dateutil.relativedelta import relativedelta

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

# Cheques per year -> months between instalments.
CHEQUE_PLAN = {1: 12, 2: 6, 3: 4, 4: 3, 6: 2, 12: 1}

# BR-022 / BRD §4.1.1. Who the landlord agreement authorises to contract with
# tenants, and in whose name rent is collected. These are two separate
# permissions and a landlord may grant one without the other: an agreement can
# let New Sinclair sign tenancy contracts while requiring every dirham to be
# collected in the owner's name.
AUTHORITY_PARTY = [
    ("manager", "New Sinclair"),
    ("owner", "The landlord"),
]

# BR-027 / BRD §4.1.1. A head lease may not be activated until these are on
# record. Each is (field, what to call it, is it satisfied) - the same shape
# as the unit release gate, because it answers the same question: why is this
# button refusing me?
#
# Activating a head lease commits the company to pay a landlord a fixed sum
# whether or not a single unit is let. Doing that from an agreement nobody has
# produced, over a building with no municipality reference, is how a company
# ends up owing money on a property it cannot legally let.
HEAD_LEASE_REQUIREMENTS = [
    ("agreement_ref", "Signed agreement reference", lambda r: bool(r.agreement_ref)),
    ("date_signed", "Date the agreement was signed", lambda r: bool(r.date_signed)),
    ("annual_amount", "Annual amount payable", lambda r: r.annual_amount > 0),
    ("landlord_id", "Landlord", lambda r: bool(r.landlord_id)),
    (
        "landlord_bank_id",
        "Landlord bank account for the instalments",
        lambda r: bool(r.landlord_bank_id),
    ),
    ("contracting_party", "Who may sign tenancy contracts", lambda r: bool(r.contracting_party)),
    ("collection_party", "In whose name rent is collected", lambda r: bool(r.collection_party)),
    (
        "building_ready",
        "Building plot and municipality references",
        lambda r: bool(r.building_id.plot_no and r.building_id.municipality_no),
    ),
    (
        "insurance_expiry",
        "Property insurance in force",
        lambda r: bool(r.insurance_expiry) and r.insurance_expiry >= fields.Date.context_today(r),
    ),
]


class HeadLease(models.Model):
    """What we pay the landlord to take the building.

    This is the underwriting contract: a fixed sum for the year in an agreed
    number of cheques. It is owed whether or not the units are let, which is
    what makes vacancy our cost rather than the landlord's.
    """

    _name = "c2p.head.lease"
    _description = "Head Lease (Underwriting Agreement)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_end desc, id desc"
    _check_company_auto = True

    name = fields.Char(default="New", copy=False, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    building_id = fields.Many2one("c2p.building", required=True, tracking=True, index=True)
    landlord_id = fields.Many2one("res.partner", string="Landlord", required=True, tracking=True)

    date_start = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    annual_amount = fields.Monetary(
        required=True,
        tracking=True,
        string="Annual Amount Payable",
        help="What we owe the landlord for the year, regardless of occupancy.",
    )
    cheque_count = fields.Selection(
        [
            ("1", "1 Cheque"),
            ("2", "2 Cheques"),
            ("3", "3 Cheques"),
            ("4", "4 Cheques"),
            ("6", "6 Cheques"),
            ("12", "12 Cheques"),
        ],
        default="4",
        required=True,
        string="Paid In",
    )
    instalment_amount = fields.Monetary(compute="_compute_instalment", store=True)
    security_deposit = fields.Monetary(help="Deposit lodged with the landlord.")

    ejari_no = fields.Char(string="Ejari No.", tracking=True)
    ejari_date = fields.Date(string="Ejari Registered On")

    # --- BR-013: what the signed agreement actually says -------------------
    agreement_ref = fields.Char(
        string="Agreement Reference",
        tracking=True,
        help="The reference on the signed head-lease agreement. Entered from the document, never assumed.",
    )
    date_signed = fields.Date(string="Signed On", tracking=True)
    landlord_bank_id = fields.Many2one(
        "res.partner.bank",
        string="Landlord Bank Account",
        help="Where the instalments are paid. Used to check a landlord cheque is "
        "drawn to an account the agreement names.",
    )
    free_period_days = fields.Integer(
        string="Rent-Free Days",
        help="BRD §4.1.1. A fit-out or grace period at the start of the term. The "
        "amount is still owed for the year; this records when it starts running.",
    )
    escalation_pct = fields.Float(
        string="Escalation %",
        help="Agreed uplift applied on renewal. Recorded here so a renewal is "
        "checked against the agreement rather than negotiated afresh.",
    )
    insurance_expiry = fields.Date(
        string="Insurance Expires",
        tracking=True,
        help="BR-027. A head lease cannot be activated without insurance in force.",
    )

    # --- BR-014: a renewal is not an overlap -------------------------------
    renewal_ids = fields.One2many("c2p.head.lease", "renewal_of_id", string="Renewed By")
    renewal_of_id = fields.Many2one(
        "c2p.head.lease",
        string="Renewal Of",
        copy=False,
        index="btree_not_null",
        help="The agreement this one renews. Two head leases on one building overlap only when they are unrelated.",
    )

    # --- BR-022: what the landlord authorises ------------------------------
    contracting_party = fields.Selection(
        AUTHORITY_PARTY,
        string="Tenancy Contracts Signed By",
        tracking=True,
        help="BRD §4.1.1. Who the landlord agreement authorises to sign tenancy contracts.",
    )
    collection_party = fields.Selection(
        AUTHORITY_PARTY,
        string="Rent Collected In The Name Of",
        tracking=True,
        help="BRD §4.2.2. The contract authority half of the payee rule: tenant "
        "cheques are made out to whoever this names.",
    )
    sublease_permitted = fields.Boolean(
        string="Subleasing Permitted",
        help="Whether the landlord agreement permits units to be sublet. A head "
        "lease is subleasing by definition, so an agreement that forbids it is "
        "one that cannot be operated as a head lease.",
    )
    may_register_ejari = fields.Boolean(string="May Register Ejari", default=True)
    may_pursue_arrears = fields.Boolean(string="May Pursue Arrears", default=True)
    may_appoint_legal = fields.Boolean(string="May Appoint Legal Representatives")
    may_place_signage = fields.Boolean(string="May Market And Place Signage", default=True)

    # --- BR-027: the activation gate ---------------------------------------
    activation_blockers = fields.Char(compute="_compute_activation", string="Still Missing")
    is_activatable = fields.Boolean(compute="_compute_activation")

    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("expired", "Expired"), ("terminated", "Terminated")],
        default="draft",
        required=True,
        tracking=True,
    )

    payment_ids = fields.One2many("account.payment", "head_lease_id", string="Landlord Cheques")
    cheque_count_issued = fields.Integer(compute="_compute_cheque_position")
    outstanding_amount = fields.Monetary(
        compute="_compute_cheque_position",
        string="Still to Clear",
        help="Cheques issued to the landlord that have not yet cleared.",
    )
    paid_amount = fields.Monetary(compute="_compute_cheque_position", string="Cleared")

    # --- the numbers that decide whether the deal works ---
    potential_rent = fields.Monetary(related="building_id.potential_rent", string="Market Rent of All Units")
    contracted_rent = fields.Monetary(related="building_id.contracted_rent", string="Contracted Tenant Rent")
    gross_margin = fields.Monetary(compute="_compute_margin", store=True)
    margin_pct = fields.Float(compute="_compute_margin", store=True, string="Margin %")
    coverage_ratio = fields.Float(
        compute="_compute_margin",
        store=True,
        string="Coverage",
        help="Contracted tenant rent divided by what we owe the landlord. Below 1.0 the building is losing money.",
    )
    breakeven_occupancy = fields.Float(
        compute="_compute_margin",
        store=True,
        string="Break-even Occupancy %",
        help="Share of the building's market rent that must be let to cover "
        "the head lease. Compare it against actual occupancy.",
    )

    @api.depends("annual_amount", "cheque_count")
    def _compute_instalment(self):
        for rec in self:
            n = int(rec.cheque_count or 1)
            amount = rec.annual_amount / n if n else 0.0
            rec.instalment_amount = rec.currency_id.round(amount) if rec.currency_id else amount

    @api.depends("payment_ids.pdc_state", "payment_ids.amount")
    def _compute_cheque_position(self):
        for rec in self:
            rec.cheque_count_issued = len(rec.payment_ids)
            cleared = rec.payment_ids.filtered(lambda p: p.pdc_state == "cleared")
            rec.paid_amount = sum(cleared.mapped("amount"))
            rec.outstanding_amount = sum(
                rec.payment_ids.filtered(lambda p: p.pdc_state in ("held", "deposited")).mapped("amount")
            )

    @api.depends("annual_amount", "building_id.contracted_rent", "building_id.potential_rent")
    def _compute_margin(self):
        for rec in self:
            cost = rec.annual_amount or 0.0
            income = rec.building_id.contracted_rent or 0.0
            potential = rec.building_id.potential_rent or 0.0
            rec.gross_margin = rec.currency_id.round(income - cost) if rec.currency_id else income - cost
            rec.margin_pct = (rec.gross_margin / income * 100.0) if income else 0.0
            rec.coverage_ratio = (income / cost) if cost else 0.0
            rec.breakeven_occupancy = (cost / potential * 100.0) if potential else 0.0

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end <= rec.date_start:
                raise ValidationError(self.env._("A head lease must end after it starts."))

    @api.constrains("building_id")
    def _check_building_is_head_leased(self):
        """BR-019. A head lease on an owner-managed building is a contradiction.

        Head leasing means this company pays the landlord a fixed rent and
        keeps the tenant rent. Owner Management means the landlord keeps the
        tenant rent and this company earns a fee. A building cannot be both,
        and attaching a head lease to one marked Owner Management is how the
        margin figures would silently start reporting the landlord's money
        again.
        """
        for rec in self:
            model = rec.building_id.operating_model
            if model and model != "head_lease":
                raise ValidationError(
                    self.env._(
                        "%(building)s is set to %(model)s, so it cannot carry a head lease. "
                        "Change the building's operating model first if it is being "
                        "underwritten.",
                        building=rec.building_id.display_name,
                        model=dict(rec.building_id._fields["operating_model"].selection)[model],
                    )
                )

    @api.depends(
        "agreement_ref",
        "date_signed",
        "annual_amount",
        "landlord_id",
        "landlord_bank_id",
        "contracting_party",
        "collection_party",
        "insurance_expiry",
        "building_id.plot_no",
        "building_id.municipality_no",
    )
    def _compute_activation(self):
        """BR-027, and the same shape as the unit release gate.

        Activating a head lease commits this company to pay a landlord a fixed
        sum whether or not a single unit is let. The list is derived from
        HEAD_LEASE_REQUIREMENTS rather than restated, so the screen cannot name
        a reason the gate does not enforce.
        """
        for rec in self:
            missing = [label for _f, label, ok in HEAD_LEASE_REQUIREMENTS if not ok(rec)]
            rec.activation_blockers = ", ".join(missing)
            rec.is_activatable = not missing

    @api.constrains("sublease_permitted", "state")
    def _check_subleasing_is_permitted(self):
        """A head lease IS subleasing.

        Underwriting a building means taking it in and letting the units out.
        An agreement that forbids that cannot be operated this way, and
        discovering it after the tenancies are signed is discovering it far
        too late.
        """
        for rec in self.filtered(lambda r: r.state == "active" and not r.sublease_permitted):
            raise ValidationError(
                self.env._(
                    "%(name)s cannot be activated: the landlord agreement does not permit "
                    "subleasing, and a head lease is subleasing by definition. Confirm the "
                    "agreement, or record this building as Owner Management instead.",
                    name=rec.display_name,
                )
            )

    @api.constrains("state", "building_id", "date_start", "date_end", "renewal_of_id")
    def _check_no_overlap(self):
        """A building cannot be underwritten twice for the same period.

        BR-014 excepts an approved renewal: a term that begins as the previous
        one ends is the same commercial arrangement continuing, and the two
        records touch at the boundary by design. Only unrelated agreements
        are a genuine double commitment.
        """
        for rec in self.filtered(lambda r: r.state == "active" and r.date_start and r.date_end):
            clash = self.search(
                [
                    ("id", "!=", rec.id),
                    ("building_id", "=", rec.building_id.id),
                    ("state", "=", "active"),
                    ("date_start", "<=", rec.date_end),
                    ("date_end", ">=", rec.date_start),
                    ("id", "not in", (rec.renewal_of_id | rec.renewal_ids).ids),
                ],
                limit=1,
            )
            if clash:
                raise ValidationError(
                    self.env._(
                        "%(building)s is already underwritten over that period by %(other)s.",
                        building=rec.building_id.display_name,
                        other=clash.display_name,
                    )
                )

    @api.onchange("building_id")
    def _onchange_building(self):
        if self.building_id and not self.landlord_id:
            self.landlord_id = self.building_id.owner_id

    @api.onchange("date_start")
    def _onchange_date_start(self):
        if self.date_start and not self.date_end:
            self.date_end = self.date_start + relativedelta(years=1, days=-1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("c2p.head.lease") or "New"
        return super().create(vals_list)

    # ------------------------------------------------------------------ actions
    def action_activate(self):
        """BR-027. The gate, not a suggestion.

        An exception needs the agreement itself to change, not an override on
        this button: the missing items are facts about a signed document and
        a building, and clicking past them would record a commitment the
        company cannot evidence.
        """
        for rec in self:
            if not rec.is_activatable:
                raise UserError(
                    rec.env._(
                        "%(name)s cannot be activated yet. Still missing: %(missing)s.",
                        name=rec.display_name,
                        missing=rec.activation_blockers,
                    )
                )
            rec.state = "active"

    def action_terminate(self):
        for rec in self:
            rec.state = "terminated"

    def action_issue_cheques(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Issue Landlord Cheques"),
            "res_model": "c2p.landlord.cheque.register",
            "view_mode": "form",
            "target": "new",
            "context": {"default_head_lease_id": self.id},
        }

    def action_view_cheques(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Landlord Cheques"),
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("head_lease_id", "=", self.id)],
            "context": {"default_head_lease_id": self.id},
        }

    # ------------------------------------------------------------------ cron
    @api.model
    def _cron_expire_head_leases(self):
        today = fields.Date.context_today(self)
        self.search([("state", "=", "active"), ("date_end", "<", today)]).write({"state": "expired"})

    @api.model
    def _cron_landlord_cheque_alerts(self):
        """Warn before a landlord cheque falls due - a bounced cheque to a
        landlord costs the building."""
        today = fields.Date.context_today(self)
        horizon = today + relativedelta(days=14)
        due = self.env["account.payment"].search(
            [
                ("head_lease_id", "!=", False),
                ("pdc_state", "=", "held"),
                ("maturity_date", ">=", today),
                ("maturity_date", "<=", horizon),
            ]
        )
        for payment in due:
            lease = payment.head_lease_id
            summary = self.env._("Landlord cheque due %s", payment.maturity_date)
            if self.env["mail.activity"].search_count(
                [
                    ("res_model", "=", "c2p.head.lease"),
                    ("res_id", "=", lease.id),
                    ("summary", "=", summary),
                ]
            ):
                continue
            lease.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=self.env._(
                    "Cheque %(no)s to %(landlord)s for %(amount)s clears on %(date)s. Confirm funds are in place.",
                    no=payment.cheque_no or "-",
                    landlord=lease.landlord_id.name,
                    amount=payment.amount,
                    date=payment.maturity_date,
                ),
                date_deadline=payment.maturity_date,
            )
