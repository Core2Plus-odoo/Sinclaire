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
        # BRD §4.1 requires units to be released for marketing only after
        # mandatory data and approval checks pass, which would make Draft the
        # right default. That gate is BR-018 and is not built yet; defaulting
        # to Draft before it exists would strand every unit a loader or import
        # creates. The default moves to "draft" with BR-018.
        default="available",
        required=True,
        tracking=True,
    )
    current_lease_id = fields.Many2one("c2p.lease", string="Current Lease", copy=False)
    lease_ids = fields.One2many("c2p.lease", "unit_id", string="Lease History")
    tenant_id = fields.Many2one(related="current_lease_id.tenant_id", string="Tenant", store=True)
    lease_end = fields.Date(related="current_lease_id.date_end", string="Lease Ends", store=True)
    dewa_no = fields.Char(string="DEWA Premise No.")

    _unit_uniq = models.Constraint(
        "UNIQUE (building_id, name)",
        "Unit numbers must be unique per building.",
    )

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
        """Draft → Available. BR-018 will add the mandatory-data check here."""
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
        self._move_to("blocked", tuple(s for s, _ in UNIT_STATES if s != "blocked"))

    def action_unblock(self):
        self._move_to("available", ("blocked",))
