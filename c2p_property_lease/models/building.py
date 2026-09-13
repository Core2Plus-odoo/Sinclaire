from odoo import api, fields, models


class C2pBuilding(models.Model):
    _name = "c2p.building"
    _description = "Building"
    _inherit = ["mail.thread", "image.mixin"]
    _order = "name"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, help="Short code used as the unit number prefix, e.g. MKH.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    owner_id = fields.Many2one(
        "res.partner", string="Landlord", required=True, tracking=True, domain="[('is_company','in',[True,False])]"
    )
    management_fee_pct = fields.Float(
        string="Management Fee %",
        default=5.0,
        tracking=True,
        help="Percentage of rent collected retained by Sinclair as the management fee.",
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        help="All rent, expenses and fees for this building are posted against this analytic account.",
    )
    street = fields.Char()
    city = fields.Char(default="Dubai")
    community = fields.Char()

    unit_ids = fields.One2many("c2p.unit", "building_id", string="Units")
    unit_count = fields.Integer(compute="_compute_unit_stats", store=True)
    occupied_count = fields.Integer(compute="_compute_unit_stats", store=True)
    vacant_count = fields.Integer(compute="_compute_unit_stats", store=True)
    occupancy_rate = fields.Float(string="Occupancy %", compute="_compute_unit_stats", store=True, aggregator="avg")
    contracted_rent = fields.Monetary(compute="_compute_unit_stats", store=True, string="Contracted Annual Rent")
    currency_id = fields.Many2one(related="company_id.currency_id")

    _code_uniq = models.Constraint(
        "UNIQUE (code, company_id)",
        "The building code must be unique.",
    )

    @api.depends("unit_ids.state", "unit_ids.current_lease_id.annual_rent")
    def _compute_unit_stats(self):
        for rec in self:
            units = rec.unit_ids
            rec.unit_count = len(units)
            rec.occupied_count = len(units.filtered(lambda u: u.state == "occupied"))
            rec.vacant_count = len(units.filtered(lambda u: u.state == "vacant"))
            rec.occupancy_rate = (rec.occupied_count / rec.unit_count * 100.0) if rec.unit_count else 0.0
            rec.contracted_rent = sum(units.mapped("current_lease_id.annual_rent"))

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
