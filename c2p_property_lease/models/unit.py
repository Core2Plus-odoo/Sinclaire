from odoo import api
from odoo import fields
from odoo import models

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
        [("vacant", "Vacant"), ("occupied", "Occupied"), ("notice", "Under Notice"), ("blocked", "Blocked")],
        default="vacant",
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
