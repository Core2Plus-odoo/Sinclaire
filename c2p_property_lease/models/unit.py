from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

# BRD §3.2: Draft → Available → Under Marketing → Viewing/On Hold → Reserved →
# Contracted → Occupied → Under Notice → Vacant → Under Maintenance/Blocked.
# Allowed transitions, roles and reversal rights are in docs/status_matrix.md.
UNIT_STATES = [
    ("draft", "Draft"),
    ("available", "Available"),
    ("under_marketing", "Under Marketing"),
    ("viewing_hold", "Viewing / On Hold"),
    ("reserved", "Reserved"),
    ("contracted", "Contracted"),
    ("occupied", "Occupied"),
    ("notice", "Under Notice"),
    ("vacant", "Vacant"),
    ("blocked", "Under Maintenance / Blocked"),
]

# The three groups every report and KPI must agree on. Defined once here
# because building stats, the dashboard and the leasing flow all need the same
# answer to "is this unit earning?" - and a disagreement between them is
# invisible until two screens show different occupancy.
#
# EARNING: a lease is running or about to run, so rent is being charged.
# EMPTY: in the portfolio, lettable, earning nothing. This is what vacancy loss
#   is measured over, and it is exactly the set that was a single "vacant"
#   state before the BRD's ten-state model was adopted - so the numbers on the
#   dashboard do not move.
# Draft (not yet in the portfolio) and Blocked (deliberately withdrawn) are in
# neither, which also matches the previous behaviour.
EARNING_STATES = ("contracted", "occupied", "notice")
EMPTY_STATES = ("available", "under_marketing", "viewing_hold", "reserved", "vacant")

UNIT_TYPES = [
    ("studio", "Studio"),
    ("1br", "1 Bedroom"),
    ("2br", "2 Bedroom"),
    ("3br", "3 Bedroom"),
    ("shop", "Retail Shop"),
    ("office", "Office"),
]

# BR-018: a unit is released for letting only once the data a lease depends on
# is actually present. Each entry is (field, label, test). The test is given a
# unit and answers "is this satisfied?" - so a rule that is not met names
# itself in the refusal rather than failing anonymously.
#
# Why each one is here rather than merely desirable:
#   area, type    - the lease quotes rent against them
#   floor         - the unit cannot be found for a viewing or a handover
#   market rent   - BR-017's floor-rent override and every vacancy-loss figure
#                   read it; zero silently reports the unit as worthless
#   DEWA premise  - utilities cannot be transferred at move-in without it
#   analytic a/c  - BR-012 posts all rent and cost for the building against it;
#                   letting a unit on a building without one produces rent that
#                   cannot be attributed to the property that earned it
RELEASE_REQUIREMENTS = [
    ("unit_type", "Unit type", lambda u: bool(u.unit_type)),
    ("floor", "Floor", lambda u: bool(u.floor)),
    ("area_sqft", "Area (sq ft)", lambda u: u.area_sqft > 0),
    ("market_rent", "Market rent", lambda u: u.market_rent > 0),
    ("dewa_no", "DEWA premise number", lambda u: bool(u.dewa_no)),
    (
        "building_id",
        "Analytic account on the building",
        lambda u: bool(u.building_id.analytic_account_id),
    ),
]


class C2pUnit(models.Model):
    _name = "c2p.unit"
    _description = "Property Unit"
    _inherit = ["mail.thread", "image.mixin"]
    _order = "building_id, name"
    _rec_names_search = ["name", "building_id.name"]
    _check_company_auto = True

    name = fields.Char(string="Unit No.", required=True)
    building_id = fields.Many2one("c2p.building", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="building_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    unit_type = fields.Selection(UNIT_TYPES, default="1br", required=True)
    floor = fields.Char()
    area_sqft = fields.Float(string="Area (sq ft)")
    market_rent = fields.Monetary(
        string="Market Rent (Annual)",
        help="Reference rent used when quoting. Compare against the RERA rental index band on renewal.",
    )
    rera_index_low = fields.Monetary(string="RERA Index Low")
    rera_index_high = fields.Monetary(string="RERA Index High")
    state = fields.Selection(
        UNIT_STATES,
        # BR-018. BRD §4.1 requires units to be released for marketing only
        # after mandatory data and approval checks pass, so a new unit starts
        # in Draft and reaches Available only through action_release.
        default="draft",
        required=True,
        tracking=True,
    )
    state_before_block = fields.Selection(
        UNIT_STATES,
        copy=False,
        readonly=True,
        help="Where the unit was when it was blocked, so unblocking returns it there.",
    )
    current_lease_id = fields.Many2one("c2p.lease", string="Current Lease", copy=False)
    lease_ids = fields.One2many("c2p.lease", "unit_id", string="Lease History")
    tenant_id = fields.Many2one(related="current_lease_id.tenant_id", string="Tenant", store=True)
    lease_end = fields.Date(related="current_lease_id.date_end", string="Lease Ends", store=True)
    dewa_no = fields.Char(string="DEWA Premise No.")
    release_blockers = fields.Char(
        compute="_compute_release_blockers",
        string="Missing Before Release",
        help="What still has to be filled in before this unit can be released for letting (BR-018).",
    )
    is_releasable = fields.Boolean(compute="_compute_release_blockers")

    _unit_uniq = models.Constraint(
        "UNIQUE (building_id, name)",
        "Unit numbers must be unique per building.",
    )

    @api.depends(
        "unit_type",
        "floor",
        "area_sqft",
        "market_rent",
        "dewa_no",
        "building_id.analytic_account_id",
    )
    def _compute_release_blockers(self):
        for rec in self:
            missing = [label for _f, label, ok in RELEASE_REQUIREMENTS if not ok(rec)]
            rec.release_blockers = ", ".join(missing)
            rec.is_releasable = not missing

    @api.depends("name", "building_id.code")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} – {rec.building_id.name}" if rec.building_id else rec.name

    # ------------------------------------------------------------------ actions
    # One method per transition rather than a writable state field: each is a
    # place to hang the guard and the approval the BRD asks for, and a
    # transition that is not listed here is one the user cannot make.
    # docs/status_matrix.md is the specification.

    def _move_to(self, target, allowed_from):
        for rec in self:
            if rec.state not in allowed_from:
                raise UserError(
                    self.env._(
                        "%(unit)s cannot move from %(current)s to %(target)s.",
                        unit=rec.display_name,
                        current=dict(self._fields["state"].selection)[rec.state],
                        target=dict(self._fields["state"].selection)[target],
                    )
                )
        self.state = target

    def action_release(self):
        """Draft → Available: the unit enters the lettable portfolio.

        BR-018. This is the only way out of Draft, and it is refused while
        anything a lease depends on is still missing. The refusal names every
        gap at once rather than one per attempt, because the person filling
        the record in wants the whole list.

        Releasing is a Leasing Manager action: it is the approval the BRD asks
        for, and the point after which the unit can be marketed and let.
        """
        # env.su covers the loader and any automated path: those create units
        # with complete data and have no interactive approver to be.
        if not self.env.su and not self.env.user.has_group("c2p_property_lease.group_property_manager"):
            raise UserError(self.env._("Releasing a unit for letting is a Leasing Manager action."))
        for rec in self:
            if rec.state == "draft" and rec.release_blockers:
                raise UserError(
                    self.env._(
                        "%(unit)s cannot be released for letting. Still missing: %(missing)s.",
                        unit=rec.display_name,
                        missing=rec.release_blockers,
                    )
                )
        self._move_to("available", ("draft",))

    def action_market(self):
        self._move_to("under_marketing", ("available", "viewing_hold"))

    def action_hold(self):
        self._move_to("viewing_hold", ("available", "under_marketing"))

    def action_reserve(self):
        self._move_to("reserved", ("available", "under_marketing", "viewing_hold"))

    def action_release_reservation(self):
        self._move_to("available", ("reserved",))

    def action_turnaround_complete(self):
        """Vacant → Available: the unit is re-lettable again."""
        self._move_to("available", ("vacant",))

    def action_block(self):
        """Remember where the unit was: a blocked unit returns to the state it
        left, not to Available. Returning an occupied unit to Available would
        leave a tenant in place on a unit the system believes is lettable, and
        the activation guard reads that state - so a second lease could be
        activated over the sitting tenant (BR-001)."""
        for rec in self:
            if rec.state != "blocked":
                rec.state_before_block = rec.state
        self._move_to("blocked", tuple(s for s, _ in UNIT_STATES if s != "blocked"))

    def action_unblock(self):
        for rec in self:
            if rec.state != "blocked":
                raise UserError(self.env._("%(unit)s is not blocked.", unit=rec.display_name))
            rec.state = rec.state_before_block or "available"
            rec.state_before_block = False
