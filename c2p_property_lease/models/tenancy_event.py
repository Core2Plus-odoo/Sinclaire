"""BR-098: the tenancy monitoring register.

BRD §5.3 lists what has to be recorded against a running tenancy - complaints,
disturbances, unauthorised subletting, unusual utility use, missing deposits or
documents, maintenance history, breaches, warnings, legal cases, resolutions -
"each with date, category, seriousness, evidence, owner, action, deadline,
result and renewal impact". Every one of those is a field here.

Why a register and not a field on the lease: the pattern a leasing decision
turns on is never one incident. It is the third noise complaint, or the second
tenancy in a row where the deposit documents never arrived. A `notes` field
holds the same words and answers none of those questions, because nothing can
count it, sort it by seriousness or tie it to a deadline somebody owns.

**The limit on this model is as important as its contents.** BR-099 says
warnings, breach notices, non-renewals and terminations follow an approved
workflow with legal review, and that "the system must not make legal decisions
on its own". So this is a register, not a referee:

* Nothing here blocks an activation, a renewal or a termination.
* `renewal_impact` is the recorder's opinion, carried to whoever decides. It is
  not a gate, and `tests/test_tenancy_event.py` asserts that it is not - that
  kind of helpfulness is exactly what gets added later by accident.
* `referred` routes a matter to a human and stops there. The system never
  reaches the decision itself.

What seriousness does *not* do: which level compels which action, and who signs
off at each, is OD-06. The scale records a judgement; it does not infer one.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

# Straight from the BRD §5.3 list, in its order, plus the two the same sentence
# implies rather than names: a payment promise (it asks for "promises") and a
# catch-all, because a register that cannot record an event the list did not
# anticipate gets worked around in a notes field, and then the register is a
# lie about what happened.
EVENT_CATEGORIES = [
    ("complaint", "Complaint"),
    ("disturbance", "Disturbance"),
    ("subletting", "Unauthorised Subletting"),
    ("utility", "Unusual Utility Use"),
    ("missing_document", "Missing Deposit or Document"),
    ("maintenance", "Maintenance"),
    ("payment_promise", "Payment Promise"),
    ("breach", "Breach of Contract"),
    ("warning", "Warning Issued"),
    ("legal", "Legal Case"),
    ("other", "Other"),
]

# How serious the recorder judged it. A scale, not a trigger - see the module
# docstring. Ordered worst-first in the dossier, so the order here is the
# order of severity and the dossier derives its sort from it rather than
# repeating the judgement.
SERIOUSNESS_LEVELS = [
    ("critical", "Critical"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
]

# The subset the dossier and the renewal pack treat as worth a reader's
# attention. Written here, next to the scale, so one change moves both.
ADVERSE_SERIOUSNESS = ("critical", "high")

# The recorder's view of what this means for renewal. Advisory: BR-099 reserves
# the decision for a person.
RENEWAL_IMPACTS = [
    ("none", "No impact"),
    ("monitor", "Monitor at renewal"),
    ("condition", "Renew only with conditions"),
    ("oppose", "Recommend non-renewal"),
]

EVENT_STATES = [
    ("open", "Logged"),
    ("in_progress", "Being Actioned"),
    ("referred", "Referred for Decision"),
    ("resolved", "Resolved"),
    ("closed", "Closed Without Action"),
]

# docs/status_matrix.md §7 is the spec; this is that table. A move not in here
# is blocked, and the absence of a key is the rule.
EVENT_TRANSITIONS = {
    "open": ("in_progress", "referred", "resolved", "closed"),
    "in_progress": ("open", "referred", "resolved", "closed"),
    "referred": ("in_progress", "resolved"),
    "resolved": ("in_progress",),
    "closed": ("open",),
}

# Moves the matrix marks "reason mandatory", as a reversal or as a closure
# without action. Keyed by target because that is how the matrix reads.
REASON_REQUIRED = {
    ("in_progress", "open"),
    ("referred", "in_progress"),
    ("resolved", "in_progress"),
    ("open", "closed"),
    ("in_progress", "closed"),
    ("closed", "open"),
}

# Still live work: somebody owns it and nothing has concluded.
OPEN_STATES = ("open", "in_progress", "referred")

# Set by _set_state so an action can move the record while a hand-written
# `state` write still cannot. A context key is a convention, not a boundary -
# which is fine here, because the write permission is already granted and only
# the history row is at stake. It is NOT used to get past the evidence rule on
# `referred`; see _check_referable.
STATE_MOVE_CONTEXT_KEY = "c2p_event_state_recorded"

# The summary the past-deadline activity carries. A constant because the cron
# both writes it and matches on it to avoid duplicating itself - two copies of
# this string would silently stop the de-duplication working.
DEADLINE_ALERT_SUMMARY = "Tenancy event past its deadline"


class C2pTenancyEvent(models.Model):
    _name = "c2p.tenancy.event"
    _description = "Tenancy Event"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "event_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(default="New", copy=False, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    lease_id = fields.Many2one(
        "c2p.lease",
        string="Tenancy",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
        check_company=True,
    )
    # Stored so the dossier and every report can group by tenant without
    # walking the lease, and so a tenant's history survives in a search domain
    # (a non-stored compute cannot appear in one at all).
    tenant_id = fields.Many2one(related="lease_id.tenant_id", store=True, index=True, string="Tenant")
    unit_id = fields.Many2one(related="lease_id.unit_id", store=True)
    building_id = fields.Many2one(related="lease_id.building_id", store=True)

    # ------------------------------------------------------------ BR-098 fields
    event_date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        help="When the event happened, not when it was typed in.",
    )
    category = fields.Selection(EVENT_CATEGORIES, required=True, tracking=True)
    seriousness = fields.Selection(SERIOUSNESS_LEVELS, required=True, default="medium", tracking=True)
    summary = fields.Char(required=True, help="One line: what happened.")
    description = fields.Text()
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Owner",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        help="Who is accountable for dealing with this, not who typed it in.",
    )
    deadline = fields.Date(tracking=True, help="When the action is due.")
    action_taken = fields.Text(string="Action")
    result = fields.Text(help="What actually happened in the end.")
    renewal_impact = fields.Selection(
        RENEWAL_IMPACTS,
        default="none",
        tracking=True,
        help="The recorder's view, carried to whoever decides the renewal. Advisory only: "
        "BRD §5.3 (BR-099) reserves that decision for a person.",
    )
    state = fields.Selection(EVENT_STATES, default="open", required=True, copy=False, tracking=True)

    # Evidence. First-class rather than left to the chatter, because BR-098
    # asks for it by name and BR-099 requires it for anything that leads to a
    # notice - so it has to be countable, not just present somewhere in a
    # thread.
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "c2p_tenancy_event_attachment_rel",
        "event_id",
        "attachment_id",
        string="Evidence",
    )
    evidence_count = fields.Integer(compute="_compute_evidence", store=True)
    has_evidence = fields.Boolean(compute="_compute_evidence", store=True)

    is_adverse = fields.Boolean(
        compute="_compute_flags",
        store=True,
        help="Serious enough that a reader of the tenancy should see it.",
    )
    is_open = fields.Boolean(compute="_compute_flags", store=True)
    # Stored, with the date in the depends, so it can be searched and so a
    # filter on it is not quietly a day stale. The cron below keeps it true.
    is_overdue = fields.Boolean(compute="_compute_flags", store=True)

    _deadline_after_event = models.Constraint(
        "CHECK (deadline IS NULL OR event_date IS NULL OR deadline >= event_date)",
        "An event's deadline cannot fall before the event itself.",
    )

    # ------------------------------------------------------------------ compute
    @api.depends("attachment_ids")
    def _compute_evidence(self):
        for rec in self:
            rec.evidence_count = len(rec.attachment_ids)
            rec.has_evidence = bool(rec.attachment_ids)

    @api.depends("seriousness", "state", "deadline")
    def _compute_flags(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_adverse = rec.seriousness in ADVERSE_SERIOUSNESS
            rec.is_open = rec.state in OPEN_STATES
            rec.is_overdue = bool(rec.state in OPEN_STATES and rec.deadline and rec.deadline < today)

    @api.depends("name", "summary")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} – {rec.summary}" if rec.summary else rec.name or ""

    @api.constrains("lease_id", "event_date")
    def _check_event_date(self):
        """An event may not be filed against a tenancy somebody else was under.

        Deliberately not "the event cannot predate the tenancy". Plenty of
        legitimate events do: a missing deposit or document is chased between
        signature and start, which is a category this model offers and the
        commonest thing anybody records before a tenancy begins. Refusing
        those would force the recorder to post-date the event, and `event_date`
        says in its own help text that it is when the event happened.

        What is genuinely wrong is an event dated inside a *different* tenancy
        of the same unit: that belongs to whoever had the unit at the time, and
        left here it would surface in the wrong tenant's dossier and the wrong
        renewal pack. So that is what this refuses, and only that.
        """
        for rec in self:
            lease = rec.lease_id
            if not (rec.event_date and lease.date_start and rec.event_date < lease.date_start):
                continue
            clash = self.env["c2p.lease"].search(
                [
                    ("id", "!=", lease.id),
                    ("unit_id", "=", lease.unit_id.id),
                    ("date_start", "<=", rec.event_date),
                    ("date_end", ">=", rec.event_date),
                ],
                limit=1,
            )
            if clash:
                raise ValidationError(
                    self.env._(
                        "%(summary)s is dated %(date)s, when %(unit)s was let under tenancy "
                        "%(other)s rather than %(lease)s. File it against the tenancy that was "
                        "running at the time.",
                        summary=rec.summary or self.env._("This event"),
                        date=rec.event_date,
                        unit=lease.unit_id.display_name or "",
                        other=clash.name,
                        lease=lease.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("c2p.tenancy.event") or "New"
        return super().create(vals_list)

    def write(self, vals):
        """The transition table, enforced here rather than only in the actions.

        `state` is a writable field and a status-bar widget writes it directly,
        so a guard that sits only in an action guards nothing - the same lesson
        as `c2p.lease.write` and `account.payment.write`.
        """
        target = vals.get("state")
        if target:
            for rec in self:
                if rec.state == target:
                    continue
                rec._check_transition(target)
                if not self.env.context.get(STATE_MOVE_CONTEXT_KEY):
                    raise UserError(
                        rec.env._(
                            "Move %(ref)s with its buttons rather than by setting the status, so the "
                            "change is recorded with who made it and why.",
                            ref=rec.name,
                        )
                    )
        return super().write(vals)

    # ----------------------------------------------------------------- guards
    def _check_transition(self, target):
        self.ensure_one()
        allowed = EVENT_TRANSITIONS.get(self.state, ())
        if target not in allowed:
            labels = dict(EVENT_STATES)
            raise UserError(
                self.env._(
                    "%(ref)s cannot go from %(current)s to %(target)s. Allowed from here: %(allowed)s.",
                    ref=self.name,
                    current=labels.get(self.state, self.state),
                    target=labels.get(target, target),
                    allowed=", ".join(labels.get(state, state) for state in allowed) or self.env._("nothing"),
                )
            )
        if target == "referred":
            self._check_referable()

    def _check_referable(self):
        """BR-099: evidence before a matter goes up for decision.

        The BRD requires evidence and legal review for the notices that follow
        a referral, so referring one with nothing attached is refused. This is
        the only mandatory-evidence rule the BRD itself supplies - any other
        threshold is OD-06, and is deliberately not invented here.

        Deliberately ignores STATE_MOVE_CONTEXT_KEY. The key exists so an
        action can write a history row; it is not a way past a rule, or the
        bypass would just move one layer down.
        """
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError(
                self.env._(
                    "Attach the evidence before referring %(ref)s for a decision. A referral leads to a "
                    "warning or a notice, and BRD §5.3 requires the evidence and the legal review to "
                    "exist first.",
                    ref=self.name,
                )
            )

    def _set_state(self, target, reason=None, **extra):
        """Every move goes through here, so every move leaves a history row."""
        self.ensure_one()
        self._check_transition(target)
        # BR-098 lists "result" among the attributes every event carries, and
        # Resolved is the state that claims there was one. Without this an
        # event could sit at Resolved saying it was dealt with and refusing to
        # say how. Closed Without Action is deliberately exempt: it concludes
        # with a reason, which is required separately, and has no result by
        # definition.
        if target == "resolved" and not ((extra.get("result") or self.result or "").strip()):
            raise UserError(
                self.env._(
                    "Record what happened in the end before resolving %(ref)s.",
                    ref=self.name,
                )
            )
        if (self.state, target) in REASON_REQUIRED and not reason:
            labels = dict(EVENT_STATES)
            raise UserError(
                self.env._(
                    "Moving %(ref)s to %(target)s needs a reason.",
                    ref=self.name,
                    target=labels.get(target, target),
                )
            )
        labels = dict(EVENT_STATES)
        body = self.env._(
            "%(old)s → %(new)s",
            old=labels.get(self.state, self.state),
            new=labels.get(target, target),
        )
        if reason:
            body = self.env._("%(move)s. Reason: %(reason)s", move=body, reason=reason)
        self.with_context(**{STATE_MOVE_CONTEXT_KEY: True}).write({"state": target, **extra})
        self.message_post(body=body)

    # ----------------------------------------------------------------- actions
    def action_start(self):
        for rec in self:
            rec._set_state("in_progress")

    def action_refer(self, reason=None):
        for rec in self:
            rec._set_state("referred", reason=reason)

    def action_resolve(self, reason=None):
        for rec in self:
            rec._set_state("resolved", reason=reason)

    def action_close(self, reason=None):
        for rec in self:
            rec._set_state("closed", reason=reason)

    def action_reopen(self, reason=None):
        """Back to the start of the work, from either concluded state."""
        for rec in self:
            target = "open" if rec.state == "closed" else "in_progress"
            rec._set_state(target, reason=reason)

    # -------------------------------------------------------------------- cron
    @api.model
    def _cron_event_deadline_alerts(self):
        """Raise an activity on the owner when an event's deadline passes.

        The stored `is_overdue` only becomes true when something recomputes it,
        and nothing touches an event that is simply sitting there - so without
        this the flag would be correct on the day it was written and stale
        afterwards. Recomputing the open set each day is what keeps a filter on
        it honest.
        """
        open_events = self.search([("state", "in", OPEN_STATES)])
        # add_to_compute, not a direct call to the compute method. `is_overdue`
        # is stored and its depends hold no date, so nothing marks it dirty
        # when a deadline simply passes - and invalidating the cache would only
        # drop a value the database still holds. This is the supported way to
        # tell the ORM a stored computed field needs recomputing, so the flag
        # behind the "Past deadline" filter is true again after the flush.
        self.env.add_to_compute(self._fields["is_overdue"], open_events)
        open_events.flush_recordset(["is_overdue"])

        today = fields.Date.context_today(self)
        overdue = open_events.filtered(lambda rec: rec.deadline and rec.deadline < today)
        for rec in overdue:
            # Matched on the summary as well as the owner, so only this alert's
            # own duplicate suppresses it. Matching on the owner alone meant
            # any unrelated to-do somebody had scheduled on the event - "call
            # the tenant back" - silenced the deadline alert entirely, which is
            # the one thing this cron exists to send.
            #
            # `summary=` and `owner=` bind now rather than at call time: a bare
            # closure over `rec` reads whatever the loop variable holds when the
            # lambda finally runs.
            if rec.activity_ids.filtered(
                lambda act, owner=rec.responsible_user_id, summary=DEADLINE_ALERT_SUMMARY: (
                    act.user_id == owner and act.summary == summary
                )
            ):
                continue
            rec.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=rec.responsible_user_id.id,
                summary=DEADLINE_ALERT_SUMMARY,
                note=self.env._(
                    "%(summary)s was due on %(deadline)s and is still %(state)s.",
                    summary=rec.summary or rec.name,
                    deadline=rec.deadline,
                    state=dict(EVENT_STATES).get(rec.state, rec.state),
                ),
            )
        return len(overdue)
