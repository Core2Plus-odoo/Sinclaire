from odoo import api
from odoo import fields
from odoo import models

# A cheque inside this window is the collections team's work for the week:
# confirm funds, bank it, chase the tenant. Outside it, it is a diary note.
DUE_SOON_DAYS = 7


class AccountPayment(models.Model):
    """Presentation-only additions for the Collections workspace.

    The property module already holds every fact this screen needs: the seven
    instrument states, maturity dates, the owner-funds flag and the
    replacement link. What it did not have was anywhere to look at them. The
    register existed as fields on a form nobody opens daily.

    Nothing here is a new rule. What it adds is the ordering a person would
    otherwise do in their head each morning, and the one separation they must
    never get wrong: whose money each instrument is.
    """

    _inherit = "account.payment"

    days_to_maturity = fields.Integer(
        compute="_compute_collection",
        string="Days",
        help="Negative once the maturity date has passed.",
    )
    collection_bucket = fields.Selection(
        [
            ("missing", "Not handed over"),
            ("overdue", "Past due"),
            ("due_soon", "Due this week"),
            ("later", "Later"),
            ("bounced", "Bounced"),
            ("settled", "Settled"),
            ("closed", "Closed"),
        ],
        compute="_compute_collection",
        search="_search_collection_bucket",
        string="Bucket",
        help="What this instrument needs from the collections team today.",
    )
    collection_alert = fields.Char(compute="_compute_collection", string="Needs Attention")
    funds_label = fields.Char(
        compute="_compute_funds_label",
        string="Funds",
        help="Whose money this instrument is.",
    )
    collection_tone = fields.Selection(
        [("ok", "OK"), ("warn", "Needs attention"), ("critical", "Critical")],
        compute="_compute_collection",
        search="_search_collection_tone",
    )

    @api.depends("is_owner_funds")
    def _compute_funds_label(self):
        """A word rather than a tick.

        is_owner_funds is a boolean and Odoo sizes a boolean column to the
        checkbox, which cut its own header down to "O...". A tick whose
        label cannot be read tells a clerk nothing, and this is the column
        that says whose money they are about to bank.
        """
        for rec in self:
            rec.funds_label = rec.env._("Owner") if rec.is_owner_funds else rec.env._("Company")

    @api.depends("pdc_state", "maturity_date", "is_owner_funds", "replacement_payment_id")
    def _compute_collection(self):
        """One bucket and one line per instrument, worst thing first.

        The order is the decision. A bounced cheque with no replacement is
        money that failed and nobody has made good - it outranks a cheque that
        is merely late, which outranks one nobody has handed over yet. An
        instrument that has cleared says nothing: a register where every row
        shouts is a register nobody reads.
        """
        today = fields.Date.context_today(self)
        for rec in self:
            rec.days_to_maturity = (rec.maturity_date - today).days if rec.maturity_date else 0
            rec.collection_alert = False
            rec.collection_tone = "ok"

            state = rec.pdc_state
            if state == "bounced":
                rec.collection_bucket = "bounced"
                rec.collection_tone = "critical"
                rec.collection_alert = rec.env._("Returned unpaid, no replacement linked")
                continue
            if state == "cleared":
                rec.collection_bucket = "settled"
                continue
            if state in ("replaced", "cancelled"):
                # Closed, and deliberately quiet: the replacement carries the
                # open obligation and appears in the register in its own right.
                rec.collection_bucket = "closed"
                continue
            if state == "expected":
                rec.collection_bucket = "missing"
                rec.collection_tone = "warn"
                rec.collection_alert = rec.env._("Due under the lease and not handed over")
                continue

            # held or deposited: a real instrument with a date on it.
            if not rec.maturity_date:
                rec.collection_bucket = "later"
                rec.collection_tone = "warn"
                rec.collection_alert = rec.env._("No maturity date recorded")
            elif rec.days_to_maturity < 0:
                rec.collection_bucket = "overdue"
                rec.collection_tone = "critical"
                rec.collection_alert = rec.env._(
                    "Matured %(days)s days ago and not cleared", days=abs(rec.days_to_maturity)
                )
            elif rec.days_to_maturity <= DUE_SOON_DAYS:
                rec.collection_bucket = "due_soon"
                rec.collection_tone = "warn"
                rec.collection_alert = rec.env._("Bankable in %(days)s days", days=rec.days_to_maturity)
            else:
                rec.collection_bucket = "later"

    def _matching_pdc(self, field, operator, value):
        """Filter the cheque register in Python on a field that moves with the
        calendar rather than with an edit.

        Neither the bucket nor the tone can be stored: a cheque due next week
        becomes due this week while nobody touches the record, so a stored
        value would need a nightly cron to stay true and would be wrong
        between runs. That is worse than computing on demand, because a
        collections screen that is quietly a day stale is one people stop
        trusting.

        The candidate set is the cheque register, not every payment in the
        database, and this runs on a filter click.
        """
        if operator not in ("=", "!=", "in", "not in"):
            raise ValueError(self.env._("Unsupported operator %s for %s", operator, field))
        # Odoo passes an OrderedSet for `in`/`not in`, not a list - checking
        # for list or tuple alone wrapped it in another list and set() then
        # raised "unhashable type". A string is the one iterable that means a
        # single value rather than a collection of them.
        wanted = {value} if isinstance(value, str) else set(value)
        negated = operator in ("!=", "not in")
        candidates = self.search([("is_pdc", "=", True)])
        matching = candidates.filtered(lambda p: (p[field] in wanted) != negated)
        return [("id", "in", matching.ids)]

    def _search_collection_tone(self, operator, value):
        return self._matching_pdc("collection_tone", operator, value)

    def _search_collection_bucket(self, operator, value):
        return self._matching_pdc("collection_bucket", operator, value)
