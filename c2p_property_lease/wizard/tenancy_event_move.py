"""The event moves that need more than a button.

`docs/status_matrix.md` §7 marks five of the tenancy-event transitions "reason
mandatory" - every reversal, and closing without action. A reason typed into
the chatter afterwards is not the same record: it can be written days later, by
somebody else, and nothing ties it to the move it explains. So the dialog
collects it at the moment of the move and `_set_state` writes both together.

One wizard rather than one per move. The transition table already knows which
moves need a reason, so a second structure listing them would be the drift this
repository keeps producing - and it would be the copy that goes stale.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..models.tenancy_event import EVENT_STATES
from ..models.tenancy_event import REASON_REQUIRED


class TenancyEventMove(models.TransientModel):
    _name = "c2p.tenancy.event.move"
    _description = "Move a Tenancy Event"

    event_id = fields.Many2one("c2p.tenancy.event", required=True, readonly=True)
    current_state = fields.Selection(related="event_id.state", string="Current Status")
    move = fields.Selection(EVENT_STATES, required=True, readonly=True, string="New Status")
    # Related rather than read through event_id in the view: a view modifier
    # cannot traverse a relation, so `event_id.has_evidence` in an invisible
    # expression does not evaluate - it has to be a field on this record.
    event_has_evidence = fields.Boolean(related="event_id.has_evidence")
    reason_required = fields.Boolean(compute="_compute_requirements")
    wants_result = fields.Boolean(compute="_compute_requirements")
    result_required = fields.Boolean(compute="_compute_requirements")
    reason = fields.Text()
    result = fields.Text(help="What actually happened in the end.")

    @api.depends("event_id.state", "move")
    def _compute_requirements(self):
        """Read from the transition table, never from a second list of moves."""
        for rec in self:
            rec.reason_required = (rec.event_id.state, rec.move) in REASON_REQUIRED
            # Resolving needs a result and the model refuses without one;
            # closing without action concludes with a reason instead, so the
            # box is offered there but not demanded.
            rec.wants_result = rec.move in ("resolved", "closed")
            rec.result_required = rec.move == "resolved"

    def action_confirm(self):
        self.ensure_one()
        if self.reason_required and not (self.reason or "").strip():
            raise UserError(
                self.env._(
                    "Moving this event to %(target)s needs a reason.",
                    target=dict(EVENT_STATES).get(self.move, self.move),
                )
            )
        extra = {}
        if self.wants_result and (self.result or "").strip():
            extra["result"] = self.result
        self.event_id._set_state(self.move, reason=self.reason or None, **extra)
        return {"type": "ir.actions.act_window_close"}
