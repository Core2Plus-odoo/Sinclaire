from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ModelName(models.Model):
    _name = "sinclaire.model.name"
    _description = "Human readable description"
    _order = "sequence, name"
    # Blocks relational fields pointing at records of another company.
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    # v19: _sql_constraints is no longer read by the ORM - declare table
    # objects as models.Constraint / models.UniqueIndex class attributes.
    _name_company_uniq = models.Constraint(
        "UNIQUE (name, company_id)",
        "That name is already used in this company.",
    )

    @api.constrains("sequence")
    def _check_sequence(self):
        for record in self:
            if record.sequence < 0:
                raise ValidationError(self.env._("Sequence must be zero or greater."))
