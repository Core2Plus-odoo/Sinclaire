from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ModelName(models.Model):
    _name = "sinclaire.model.name"
    _description = "Human readable description"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "name_company_uniq",
            "unique(name, company_id)",
            "That name is already used in this company.",
        ),
    ]

    @api.constrains("sequence")
    def _check_sequence(self):
        for record in self:
            if record.sequence < 0:
                raise ValidationError(_("Sequence must be zero or greater."))
