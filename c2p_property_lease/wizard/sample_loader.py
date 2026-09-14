from odoo import fields, models


class SampleLoader(models.TransientModel):
    _name = "c2p.sample.loader"
    _description = "Load Sample Portfolio"

    with_accounting = fields.Boolean(
        string="Include cheques and invoices",
        default=True,
        help="Creates post-dated cheques and posted rent invoices so the "
        "collection and income figures are not zero. Needs a bank journal and "
        "a sales journal in this company; skipped quietly if either is missing.",
    )
    result = fields.Text(readonly=True)

    def action_load(self):
        self.ensure_one()
        created = self.env["c2p.sample.portfolio"].load(with_accounting=self.with_accounting)
        self.result = "\n".join(f"{label.capitalize()}: {count}" for label, count in created.items())
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_buildings(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Buildings",
            "res_model": "c2p.building",
            "view_mode": "kanban,list,form",
        }
