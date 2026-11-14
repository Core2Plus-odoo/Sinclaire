from odoo import api
from odoo import fields
from odoo import models

from .unit import EMPTY_STATES

# BR-019 / BRD §4.1.2. The three models the business runs, and the single field
# that decides whose money the tenant rent is.
#
# This module was built when the engagement was head-lease only, so margin,
# coverage and break-even occupancy were computed for every building without
# asking. Under the BRD that is wrong and quietly so: an owner-managed building
# has no head lease, so head_lease_cost is zero, and the old formula reported
# the landlord's entire tenant rent as this company's gross margin. BRD §6.1
# says the opposite in terms - owner funds are "not New Sinclair cash or rental
# income".
#
# Brokerage sits under Sinclair Real Estate Brokers L.L.C. and earns commission
# on transactions rather than rent on units, so a brokerage building carries no
# margin of its own here at all.
OPERATING_MODELS = [
    ("head_lease", "Head Lease"),
    ("owner_management", "Owner Management"),
    ("brokerage", "Brokerage"),
]


class C2pBuilding(models.Model):
    _name = "c2p.building"
    _description = "Building"
    _inherit = ["mail.thread", "image.mixin"]
    _order = "name"
    _check_company_auto = True

    operating_model = fields.Selection(
        OPERATING_MODELS,
        required=True,
        default="head_lease",
        tracking=True,
        help="BRD §4.1.2. Decides how this building's money is treated: under Head Lease the "
        "tenant rent is this company's income, under Owner Management it is the landlord's.",
    )
    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, help="Short code used as the unit number prefix, e.g. MKH.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    owner_id = fields.Many2one(
        "res.partner", string="Landlord", required=True, tracking=True, domain="[('is_company','in',[True,False])]"
    )
    head_lease_ids = fields.One2many("c2p.head.lease", "building_id", string="Head Leases")
    head_lease_id = fields.Many2one(
        "c2p.head.lease",
        compute="_compute_head_lease",
        string="Current Head Lease",
        help="The underwriting agreement in force: what we owe the landlord this year.",
    )
    head_lease_cost = fields.Monetary(compute="_compute_head_lease")
    managed_rent = fields.Monetary(
        compute="_compute_unit_stats",
        store=True,
        string="Rent Administered for the Owner",
        help="Gross tenant rent collected on the landlord's behalf. Owner funds, "
        "never this company's revenue (BRD §6.1).",
    )
    gross_margin = fields.Monetary(
        compute="_compute_head_lease",
        help="Contracted tenant rent less the head lease cost. This is ours to keep, "
        "and ours to lose when units stand empty.",
    )
    coverage_ratio = fields.Float(compute="_compute_head_lease", string="Coverage")
    breakeven_occupancy = fields.Float(compute="_compute_head_lease", string="Break-even Occupancy %")
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        help="All rent, expenses and fees for this building are posted against this analytic account.",
    )
    street = fields.Char()
    city = fields.Char(default="Dubai")
    community = fields.Char()

    # BR-016: what the head lease or the building declaration says this
    # building contains. Units are then reconciled against it, so an import
    # that silently drops rows is visible as a variance rather than as a
    # portfolio that looks complete and is not.
    declared_residential_units = fields.Integer(string="Declared Residential Units")
    declared_commercial_units = fields.Integer(string="Declared Commercial Units")
    declared_unit_count = fields.Integer(compute="_compute_declared", store=True, string="Declared Units")
    unit_variance = fields.Integer(
        compute="_compute_unit_stats",
        store=True,
        string="Variance",
        help="Units on record less units declared. Zero means the building reconciles.",
    )
    units_reconciled = fields.Boolean(compute="_compute_unit_stats", store=True)

    unit_ids = fields.One2many("c2p.unit", "building_id", string="Units")
    unit_count = fields.Integer(compute="_compute_unit_stats", store=True)
    occupied_count = fields.Integer(compute="_compute_unit_stats", store=True)
    vacant_count = fields.Integer(compute="_compute_unit_stats", store=True)
    occupancy_rate = fields.Float(string="Occupancy %", compute="_compute_unit_stats", store=True, aggregator="avg")
    contracted_rent = fields.Monetary(compute="_compute_unit_stats", store=True, string="Contracted Annual Rent")
    potential_rent = fields.Monetary(
        compute="_compute_unit_stats",
        store=True,
        string="Market Rent of All Units",
        help="What the building would earn fully let at market rates. The denominator for break-even occupancy.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    _code_uniq = models.Constraint(
        "UNIQUE (code, company_id)",
        "The building code must be unique.",
    )

    @api.depends(
        "head_lease_ids.state",
        "head_lease_ids.annual_amount",
        "head_lease_ids.date_end",
        "contracted_rent",
        "potential_rent",
        "operating_model",
    )
    def _compute_head_lease(self):
        """Underwriting figures, and only where underwriting is what is happening.

        Margin, coverage and break-even answer one question: is the rent we
        collect covering the rent we owe the landlord? That question only
        exists under a head lease. Under Owner Management the landlord keeps
        the tenancy income and this company earns a fee, so there is no spread
        to measure - and reporting one would be reporting the landlord's money
        as ours. Under Brokerage there are no units let at all.

        So the three figures are zero outside Head Lease, rather than computed
        from a missing head lease and quietly coming out as the whole rent.
        """
        HeadLease = self.env["c2p.head.lease"]
        for rec in self:
            if rec.operating_model != "head_lease":
                rec.head_lease_id = False
                rec.head_lease_cost = 0.0
                rec.gross_margin = 0.0
                rec.coverage_ratio = 0.0
                rec.breakeven_occupancy = 0.0
                continue
            lease = HeadLease.search(
                [("building_id", "=", rec.id), ("state", "=", "active")],
                order="date_end desc",
                limit=1,
            )
            rec.head_lease_id = lease
            rec.head_lease_cost = lease.annual_amount
            rec.gross_margin = rec.contracted_rent - lease.annual_amount
            rec.coverage_ratio = rec.contracted_rent / lease.annual_amount if lease.annual_amount else 0.0
            rec.breakeven_occupancy = lease.annual_amount / rec.potential_rent * 100.0 if rec.potential_rent else 0.0

    @api.depends("declared_residential_units", "declared_commercial_units")
    def _compute_declared(self):
        for rec in self:
            rec.declared_unit_count = rec.declared_residential_units + rec.declared_commercial_units

    @api.depends(
        "unit_ids.state",
        "unit_ids.current_lease_id.annual_rent",
        "unit_ids.market_rent",
        "declared_unit_count",
        "operating_model",
    )
    def _compute_unit_stats(self):
        for rec in self:
            units = rec.unit_ids
            rec.unit_count = len(units)
            # A building with nothing declared is not "reconciled" - it has
            # nothing to reconcile against. Reporting it as balanced would
            # hide exactly the buildings nobody has filled in yet.
            rec.unit_variance = rec.unit_count - rec.declared_unit_count
            rec.units_reconciled = bool(rec.declared_unit_count) and rec.unit_variance == 0
            rec.occupied_count = len(units.filtered(lambda u: u.state == "occupied"))
            rec.vacant_count = len(units.filtered(lambda u: u.state in EMPTY_STATES))
            rec.occupancy_rate = (rec.occupied_count / rec.unit_count * 100.0) if rec.unit_count else 0.0
            let_rent = sum(units.mapped("current_lease_id.annual_rent"))
            # BRD §6.1: the same number means two different things depending on
            # the operating model, so it is carried in two fields rather than
            # one. Under a head lease the tenant rent is this company's income.
            # Under Owner Management it is the landlord's, administered by this
            # company, and must never reach a revenue or margin figure.
            own = rec.operating_model == "head_lease"
            rec.contracted_rent = let_rent if own else 0.0
            rec.managed_rent = 0.0 if own else let_rent
            rec.potential_rent = sum(units.mapped("market_rent"))

    def action_view_units(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "c2p.unit",
            "view_mode": "kanban,list,form",
            "domain": [("building_id", "=", self.id)],
            "context": {"default_building_id": self.id},
        }
