"""BR-075: activating a tenancy before every cheque is in hand.

BRD §5.1 permits it only as a case-by-case exception approved by the Leasing
Manager or CEO, and requires the record to carry the missing items, the reason,
the approval, the conditions, the deadline, the responsible user and the
follow-up. This model is that record, and `c2p.lease.action_activate` will not
activate a short lease without an approved one.

The record exists because the approval is the control. An approval that lives
in an email thread is not auditable: nobody can later answer who allowed this
tenancy to start with two cheques missing, on what conditions, or whether the
cheques ever arrived. Each of those is a field here, and the last one is a cron.

Two deliberate design points:

* The shortfall is **captured at request time and frozen**, not computed. A
  computed shortfall would shrink to zero as the cheques arrive and the record
  would stop evidencing why the exception was ever granted.
* The approver may not be the requester. BRD §8.4 gives "no self-approval of
  lease changes" as a principle, which is enough to enforce without waiting on
  OD-06. What OD-06 still owes is *which* role approves; see `action_approve`.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

EXCEPTION_STATES = [
    ("draft", "Requested"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("fulfilled", "Fulfilled"),
    ("breached", "Deadline Missed"),
]

# An exception that is still capable of letting a lease through, or still
# waiting on a decision. One of these at a time per lease: two open exceptions
# would let each half-justify the same activation.
OPEN_STATES = ("draft", "approved")


class C2pLeaseChequeException(models.Model):
    _name = "c2p.lease.cheque.exception"
    _description = "Lease Activation Cheque Exception"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deadline, id desc"
    _check_company_auto = True

    lease_id = fields.Many2one(
        "c2p.lease",
        required=True,
        ondelete="cascade",
        index=True,
        readonly=True,
        tracking=True,
    )
    company_id = fields.Many2one(related="lease_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    unit_id = fields.Many2one(related="lease_id.unit_id", store=True)
    tenant_id = fields.Many2one(related="lease_id.tenant_id", store=True)

    state = fields.Selection(EXCEPTION_STATES, default="draft", required=True, tracking=True)

    # --- what was missing, as at the request. Frozen on purpose: see module docstring.
    expected_cheque_count = fields.Integer(readonly=True)
    received_cheque_count = fields.Integer(readonly=True)
    missing_cheque_count = fields.Integer(readonly=True)
    missing_amount = fields.Monetary(
        readonly=True,
        help="Rent not covered by cheques in hand when the exception was requested.",
    )

    # --- BR-075's required record
    reason = fields.Text(required=True, help="Why this tenancy cannot wait for the outstanding cheques.")
    conditions = fields.Text(required=True, help="Conditions attached to the approval.")
    deadline = fields.Date(required=True, tracking=True, help="Date by which the missing cheques must be received.")
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        required=True,
        tracking=True,
        help="Who chases the outstanding cheques.",
    )
    requested_by_id = fields.Many2one(
        "res.users",
        string="Requested By",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    approved_by_id = fields.Many2one("res.users", string="Decided By", readonly=True, copy=False, tracking=True)
    approval_date = fields.Datetime(readonly=True, copy=False)
    decision_note = fields.Text(help="The approver's note, and the reason when an exception is rejected.")
    activation_date = fields.Datetime(
        readonly=True,
        copy=False,
        help="When the lease was actually activated under this exception.",
    )

    # --- follow-up, live rather than frozen: this is the open question today
    outstanding_cheque_count = fields.Integer(compute="_compute_outstanding")
    outstanding_amount = fields.Monetary(compute="_compute_outstanding")
    is_overdue = fields.Boolean(compute="_compute_outstanding")

    @api.depends("lease_id.cheques_received", "lease_id.cheques_expected", "lease_id.cheque_shortfall", "deadline")
    def _compute_outstanding(self):
        today = fields.Date.context_today(self)
        for rec in self:
            lease = rec.lease_id
            rec.outstanding_cheque_count = max(lease.cheques_expected - lease.cheques_received, 0)
            rec.outstanding_amount = lease.cheque_shortfall
            rec.is_overdue = bool(
                rec.state == "approved" and rec.deadline and rec.deadline < today and not lease.cheques_complete
            )

    @api.depends("lease_id.name", "missing_cheque_count")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = self.env._(
                "%(lease)s – %(count)s cheque(s) short",
                lease=rec.lease_id.name or "",
                count=rec.missing_cheque_count,
            )

    @api.constrains("deadline")
    def _check_deadline(self):
        for rec in self:
            if rec.deadline and rec.create_date and rec.deadline < rec.create_date.date():
                raise ValidationError(self.env._("The deadline for the missing cheques cannot be in the past."))

    @api.constrains("state", "lease_id")
    def _check_one_open_exception(self):
        for rec in self:
            if rec.state not in OPEN_STATES:
                continue
            clash = self.search_count(
                [("lease_id", "=", rec.lease_id.id), ("state", "in", OPEN_STATES), ("id", "!=", rec.id)]
            )
            if clash:
                raise ValidationError(
                    self.env._(
                        "%s already has an open cheque exception. Close or reject it before raising another.",
                        rec.lease_id.display_name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        """Snapshot the shortfall from the lease, ignoring anything passed in.

        The numbers are evidence, so they are taken from the lease rather than
        from the form: a request that could overstate what was missing would
        make the approval look better justified than it was.
        """
        for vals in vals_list:
            lease = self.env["c2p.lease"].browse(vals.get("lease_id"))
            if not lease.exists():
                continue
            vals.update(
                expected_cheque_count=lease.cheques_expected,
                received_cheque_count=lease.cheques_received,
                missing_cheque_count=max(lease.cheques_expected - lease.cheques_received, 0),
                missing_amount=lease.cheque_shortfall,
            )
        records = super().create(vals_list)
        for rec in records:
            rec.lease_id.message_post(
                body=self.env._(
                    "Cheque exception requested by %(user)s: %(count)s cheque(s) and "
                    "%(amount)s outstanding, to be received by %(deadline)s.",
                    user=rec.requested_by_id.name,
                    count=rec.missing_cheque_count,
                    amount=f"{rec.missing_amount:,.2f}",
                    deadline=rec.deadline,
                )
            )
        return records

    # ------------------------------------------------------------------ actions
    def _check_approver(self):
        """BRD §5.1 names the Leasing Manager or the CEO.

        Neither role exists as a group yet - OD-06 owes the role-to-permission
        mapping, and inventing it here would hard-code a guess into the audit
        trail. `group_property_manager` is the closest role the module defines,
        so it holds the gate meanwhile; `approved_by_id` records the actual
        person, so re-pointing this at the real role later loses no history.

        The self-approval refusal does not depend on OD-06: §8.4 states it as a
        principle, and it is the half of the control that a wrong group mapping
        would not weaken.
        """
        if not self.env.user.has_group("c2p_property_lease.group_property_manager"):
            raise UserError(
                self.env._(
                    "Only a property manager may decide a cheque exception. "
                    "BRD §5.1 reserves this to the Leasing Manager or the CEO."
                )
            )
        for rec in self:
            if rec.requested_by_id == self.env.user:
                raise UserError(
                    self.env._(
                        "You requested this exception, so you cannot approve it. "
                        "BRD §8.4 forbids self-approval of lease changes."
                    )
                )

    def action_approve(self):
        self._check_approver()
        for rec in self:
            if rec.state != "draft":
                raise UserError(self.env._("Only a requested exception can be approved."))
            rec.write(
                {
                    "state": "approved",
                    "approved_by_id": self.env.user.id,
                    "approval_date": fields.Datetime.now(),
                }
            )
            # The follow-up BR-075 asks for, owned by a named person and dated.
            rec.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=rec.responsible_user_id.id,
                date_deadline=rec.deadline,
                summary=self.env._("Collect %s outstanding cheque(s)", rec.missing_cheque_count),
                note=rec.conditions,
            )
            rec.lease_id.message_post(
                body=self.env._(
                    "Cheque exception approved by %(user)s. Conditions: %(conditions)s",
                    user=self.env.user.name,
                    conditions=rec.conditions,
                )
            )

    def action_reject(self):
        self._check_approver()
        for rec in self:
            if rec.state != "draft":
                raise UserError(self.env._("Only a requested exception can be rejected."))
            rec.write(
                {
                    "state": "rejected",
                    "approved_by_id": self.env.user.id,
                    "approval_date": fields.Datetime.now(),
                }
            )

    def action_open_lease(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "c2p.lease",
            "res_id": self.lease_id.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------------ cron
    @api.model
    def _cron_cheque_exception_followup(self):
        """Close out approved exceptions: fulfilled when the cheques arrive,
        breached when the deadline passes and they have not.

        Breached is not a failure state to hide - it is the output of the
        control. An exception that is never followed up is indistinguishable
        from no approval process at all.
        """
        today = fields.Date.context_today(self)
        for rec in self.search([("state", "=", "approved")]):
            if rec.lease_id.cheques_complete:
                rec.state = "fulfilled"
                rec.lease_id.message_post(
                    body=self.env._("All cheques received; cheque exception closed as fulfilled.")
                )
            elif rec.deadline and rec.deadline < today:
                rec.state = "breached"
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=rec.responsible_user_id.id,
                    date_deadline=today,
                    summary=self.env._("Cheque exception deadline missed"),
                    note=self.env._(
                        "%(count)s cheque(s) and %(amount)s are still outstanding past %(deadline)s. "
                        "Escalate to the approver.",
                        count=rec.outstanding_cheque_count,
                        amount=f"{rec.outstanding_amount:,.2f}",
                        deadline=rec.deadline,
                    ),
                )
                rec.lease_id.message_post(
                    body=self.env._(
                        "Cheque exception deadline of %(deadline)s missed with %(count)s cheque(s) outstanding.",
                        deadline=rec.deadline,
                        count=rec.outstanding_cheque_count,
                    )
                )
