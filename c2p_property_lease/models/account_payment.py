"""The payment instrument and its seven states.

BRD §3.2 and §6.2: Expected → In Hand → Deposited/Presented → Cleared or
Bounced → Replaced / Cancelled, with the standing rule that **no status may be
overwritten without history**. `docs/status_matrix.md` §3 is the specification,
including which moves reverse and which do not.

The three states added here are the ones that were missing:

* **Expected** — the instrument the schedule says is coming but which nobody
  has handed over yet. Without it a cheque slot and a cheque in the drawer are
  the same record, so there is no forward cash forecast (BR-114) and no honest
  answer to "what is outstanding".
* **Replaced** — required by the bounce scenario (BR-117). A replacement is
  linked both ways, so the chain from the returned cheque to the one that made
  good is readable from either end.
* **Cancelled** — an instrument withdrawn before it was ever banked, which is
  not the same as one that failed.

Two rules the states alone would not carry:

* `has_bounced` is set on a bounce and **never unset**. Replacing a cheque is a
  recovery, not a retraction: without this, replacing bounced cheques would
  quietly walk the bounce rate down to zero, which is the opposite of what the
  history rule is for.
* `write` refuses a direct `pdc_state` change. Each move is its own action with
  its own reason and chatter entry; a writable status field would make the
  history optional.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

PDC_STATES = [
    ("expected", "Expected"),
    ("held", "In Hand"),
    ("deposited", "Deposited"),
    ("cleared", "Cleared"),
    ("bounced", "Bounced"),
    ("replaced", "Replaced"),
    ("cancelled", "Cancelled"),
]

# Physically with us, and therefore part of the custody count that §8.3.1 wants
# reconciled to the safe every month.
CUSTODY_STATES = ("held", "deposited")

# Nothing further will happen to the instrument itself.
CONCLUDED_STATES = ("cleared", "bounced", "replaced", "cancelled")

# Allowed moves, from docs/status_matrix.md §3. Read as "to: from which".
# Cleared has no entry pointing out of it on purpose - a reversal after
# clearing is a new accounting event, not a status change.
PDC_TRANSITIONS = {
    "held": ("expected", "deposited"),
    "expected": ("held",),
    "deposited": ("held",),
    "cleared": ("deposited",),
    "bounced": ("deposited",),
    "replaced": ("bounced",),
    "cancelled": ("expected", "held"),
}

# Moves the BRD marks "reason mandatory": the two reversals and a cancellation.
REASON_REQUIRED = {("held", "expected"), ("deposited", "held"), ("expected", "cancelled"), ("held", "cancelled")}


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # The context key the state actions set. Named for what it asserts rather
    # than for the check it passes: a caller setting this is saying it has
    # recorded the move, not that it would like to skip the rule.
    PDC_MOVE_CONTEXT_KEY = "c2p_pdc_move_recorded"

    lease_id = fields.Many2one("c2p.lease", string="Lease", index=True, copy=False)
    head_lease_id = fields.Many2one(
        "c2p.head.lease",
        string="Head Lease",
        index="btree_not_null",
        copy=False,
        help="Set on cheques we issue to a landlord under an underwriting agreement.",
    )
    is_landlord_cheque = fields.Boolean(
        compute="_compute_is_landlord_cheque",
        store=True,
        help="Money out to a landlord, as opposed to rent in from a tenant.",
    )
    unit_id = fields.Many2one(related="lease_id.unit_id", store=True)
    building_id = fields.Many2one(related="lease_id.building_id", store=True)
    cheque_no = fields.Char(string="Cheque No.", copy=False)
    cheque_bank = fields.Char(string="Drawn On")
    maturity_date = fields.Date(help="Date the cheque may be banked.")
    is_pdc = fields.Boolean(string="Post-Dated Cheque", compute="_compute_is_pdc", store=True)
    pdc_state = fields.Selection(
        PDC_STATES,
        default="held",
        copy=False,
        tracking=True,
        string="Instrument Status",
    )
    pdc_state_reason = fields.Text(
        copy=False,
        readonly=True,
        help="Why the instrument was reversed, recalled or cancelled.",
    )
    has_bounced = fields.Boolean(
        readonly=True,
        copy=False,
        help="This instrument was returned unpaid at least once. Never cleared, "
        "so replacing it does not erase the bounce from the record.",
    )
    bounced_date = fields.Date(readonly=True, copy=False)
    replacement_payment_id = fields.Many2one(
        "account.payment",
        string="Replaced By",
        readonly=True,
        copy=False,
        help="The instrument received in place of this one.",
    )
    replaces_payment_id = fields.Many2one(
        "account.payment",
        string="Replaces",
        readonly=True,
        copy=False,
        help="The returned instrument this one makes good.",
    )

    @api.depends("head_lease_id")
    def _compute_is_landlord_cheque(self):
        for rec in self:
            rec.is_landlord_cheque = bool(rec.head_lease_id)

    @api.depends("cheque_no", "pdc_state", "lease_id", "head_lease_id")
    def _compute_is_pdc(self):
        """A cheque number is the usual marker, but an Expected instrument does
        not have one yet - it is a slot in the agreed schedule, and the number
        arrives with the cheque.

        `pdc_state` cannot carry this alone because it defaults to "held" on
        every payment in the database, cheque or not; that default predates
        these states and changing it would mean rewriting every existing row.
        So Expected additionally requires a lease or head lease behind it.
        """
        for rec in self:
            rec.is_pdc = bool(rec.cheque_no) or (
                rec.pdc_state == "expected" and bool(rec.lease_id or rec.head_lease_id)
            )

    # ------------------------------------------------------------------- guard
    def write(self, vals):
        """§3's standing rule: status may not be set directly.

        Each move is its own action, which is where the reason and the chatter
        entry come from. A status field anyone can write makes that history
        optional, and the form's status bar writes it directly.

        `create` is left alone: an import or the sample loader builds
        instruments that are already in some state, and the register creates
        cheques that are already in hand.
        """
        if "pdc_state" in vals and not self.env.context.get(self.PDC_MOVE_CONTEXT_KEY):
            for rec in self:
                if rec.pdc_state != vals["pdc_state"]:
                    raise UserError(
                        self.env._(
                            "The status of cheque %(cheque)s cannot be changed directly. "
                            "Use the buttons on the cheque - each move records who made it "
                            "and why.",
                            cheque=rec.cheque_no or rec.display_name,
                        )
                    )
        return super().write(vals)

    def _pdc_move(self, target, reason=None):
        """Apply one transition, after checking it is one the BRD allows."""
        allowed_from = PDC_TRANSITIONS.get(target, ())
        labels = dict(PDC_STATES)
        for rec in self:
            if rec.pdc_state not in allowed_from:
                raise UserError(
                    self.env._(
                        "Cheque %(cheque)s is %(current)s and cannot move to %(target)s.",
                        cheque=rec.cheque_no or rec.display_name,
                        current=labels.get(rec.pdc_state, rec.pdc_state),
                        target=labels[target],
                    )
                )
            if (rec.pdc_state, target) in REASON_REQUIRED and not (reason or "").strip():
                raise UserError(
                    self.env._(
                        "Moving cheque %(cheque)s to %(target)s needs a reason.",
                        cheque=rec.cheque_no or rec.display_name,
                        target=labels[target],
                    )
                )
            previous = rec.pdc_state
            values = {"pdc_state": target}
            if reason:
                values["pdc_state_reason"] = reason
            rec.with_context(**{self.PDC_MOVE_CONTEXT_KEY: True}).write(values)
            note = self.env._(
                "Instrument status: %(old)s → %(new)s.",
                old=labels.get(previous, previous),
                new=labels[target],
            )
            rec.message_post(body=f"{note} {reason}" if reason else note)

    # ----------------------------------------------------------------- actions
    def action_pdc_receive(self):
        """Expected → In Hand. The cheque has physically arrived.

        Its number is required here, and not only because a cheque in hand
        without one is not much of a record: `is_pdc` keys off the number for
        the in-custody states, so an unnumbered instrument would drop straight
        out of the register the moment it was received.
        """
        missing = self.filtered(lambda p: not (p.cheque_no or "").strip())
        if missing:
            raise UserError(
                self.env._(
                    "Enter the cheque number before recording it as received. %s instrument(s) have none.",
                    len(missing),
                )
            )
        self._pdc_move("held")

    def action_pdc_deposit(self):
        self._pdc_move("deposited")

    def action_pdc_clear(self):
        """Deposited → Cleared.

        Only from Deposited, which is a tightening: a cheque cannot clear
        without having been presented, and BR-118 requires bank or landlord
        confirmation before anything is treated as cleared.
        """
        self._pdc_move("cleared")

    def action_pdc_bounce(self):
        """Deposited → Bounced. Reopens the receivable and raises follow-up."""
        self._pdc_move("bounced")
        today = fields.Date.context_today(self)
        for rec in self:
            rec.with_context(**{self.PDC_MOVE_CONTEXT_KEY: True}).write({"has_bounced": True, "bounced_date": today})
            rec.message_post(
                body=self.env._(
                    "Cheque returned unpaid. The receivable is open again; record any "
                    "bank charges and obtain a replacement instrument."
                )
            )
            if rec.lease_id:
                rec.lease_id.activity_schedule(
                    "mail.mail_activity_data_todo",
                    date_deadline=today,
                    summary=self.env._("Cheque %s returned unpaid", rec.cheque_no or ""),
                    note=self.env._("Chase the tenant for a replacement cheque and recover bank charges."),
                )

    def action_pdc_replace(self):
        """Open the wizard that creates the replacement and links it both ways."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Replace Cheque"),
            "res_model": "c2p.pdc.replace",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }

    def _pdc_reason_wizard(self, move):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": dict(PDC_STATES).get(move, move),
            "res_model": "c2p.pdc.reason",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id, "default_move": move},
        }

    def action_pdc_unreceive(self):
        """In Hand → Expected, with a reason. The instrument was recorded as
        received and was not."""
        return self._pdc_reason_wizard("expected")

    def action_pdc_recall(self):
        """Deposited → In Hand, with a reason: the deposit was recalled."""
        return self._pdc_reason_wizard("held")

    def action_pdc_cancel(self):
        """Expected or In Hand → Cancelled, with a reason."""
        return self._pdc_reason_wizard("cancelled")
