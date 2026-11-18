from markupsafe import Markup

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.c2p_property_lease.models.account_payment import CUSTODY_STATES
from odoo.addons.c2p_property_lease.models.account_payment import PDC_STATES
from odoo.addons.c2p_property_lease.models.lease import LIVE_STATES
from odoo.addons.c2p_property_lease.models.lease import RENEWAL_ALERT_DAYS

# A tenancy inside the outermost renewal band is close enough to expiry that
# whoever opens the dossier should see it without going looking. Read from the
# cron's own bands so the dossier and the alert cannot disagree about what
# "expiring" means - the alert fires at 90 days, so the dossier says so too.
EXPIRING_SOON_DAYS = max(RENEWAL_ALERT_DAYS)


class ResPartner(models.Model):
    """Presentation-only additions for Tenant 360.

    BR-098 (§5.3) asks for tenancy monitoring - payment and cheque
    performance, arrears, bounces - and the facts are all there already,
    spread across the tenancy records and the instrument register. What was
    missing was anywhere to see them together. Answering "who is this tenant
    and should I worry?" meant opening each lease in turn and holding the
    cheque register in your head.

    Nothing here is a new rule, in keeping with this module's remit. Every
    figure is read from the property module; the dossier contributes the
    gathering and the ordering.

    The event log that BR-098 also describes - complaints, breaches, legal
    cases - does not exist yet, so the requirement stays Partial. This is
    where it will surface when it lands.
    """

    _inherit = "res.partner"

    # A real inverse rather than a computed set: the tenancy history table is
    # then just this field with a list view, and it sorts and filters like any
    # other One2many instead of needing its own plumbing.
    tenant_lease_ids = fields.One2many("c2p.lease", "tenant_id", string="Tenancies")
    tenant_lease_count = fields.Integer(compute="_compute_tenant_tenure")
    tenant_live_lease_count = fields.Integer(compute="_compute_tenant_tenure")
    tenant_renewal_count = fields.Integer(compute="_compute_tenant_tenure")
    tenant_since = fields.Date(
        compute="_compute_tenant_tenure",
        help="Start of their earliest tenancy with us.",
    )
    tenant_tenure_display = fields.Char(compute="_compute_tenant_tenure", string="Tenant for")

    tenant_currency_id = fields.Many2one("res.currency", compute="_compute_tenant_currency")
    tenant_live_rent = fields.Monetary(
        compute="_compute_tenant_standing",
        currency_field="tenant_currency_id",
        string="Contracted rent",
        help="Annual rent on their running tenancies. Contracted, not collected.",
    )
    tenant_deposit_held = fields.Monetary(
        compute="_compute_tenant_standing",
        currency_field="tenant_currency_id",
        string="Deposit held",
    )
    tenant_cheque_shortfall = fields.Monetary(
        compute="_compute_tenant_standing",
        currency_field="tenant_currency_id",
        string="Cheque shortfall",
    )
    tenant_custody_count = fields.Integer(compute="_compute_tenant_cheques", string="Cheques in hand")
    tenant_custody_amount = fields.Monetary(
        compute="_compute_tenant_cheques",
        currency_field="tenant_currency_id",
        string="Value in hand",
    )
    tenant_ever_bounced_count = fields.Integer(compute="_compute_tenant_cheques", string="Ever bounced")
    tenant_cleared_count = fields.Integer(compute="_compute_tenant_cheques", string="Cleared")
    tenant_bounce_rate = fields.Float(
        compute="_compute_tenant_cheques",
        string="Bounce rate",
        help="Share of this tenant's concluded cheques that were returned unpaid at least once.",
    )
    tenant_cheque_tone = fields.Selection(
        [("ok", "OK"), ("warn", "Needs attention"), ("critical", "Critical")],
        compute="_compute_tenant_cheques",
    )
    tenant_cheque_breakdown = fields.Html(
        compute="_compute_tenant_cheques",
        sanitize=False,
        string="Cheque register",
    )
    tenant_alert = fields.Html(
        compute="_compute_tenant_alert",
        sanitize=False,
        string="Needs attention",
    )

    # ------------------------------------------------------------------ helpers
    def _tenant_instruments(self):
        """This tenant's cheques, reached through their tenancies.

        Not through `partner_id`: that would also catch a payment somebody
        recorded against the contact for an unrelated reason, and an unrelated
        payment landing in a tenant's bounce rate is a figure that gets a
        tenant chased for somebody else's cheque.
        """
        self.ensure_one()
        leases = self.tenant_lease_ids
        if not leases:
            return self.env["account.payment"].browse()
        return self.env["account.payment"].search([("lease_id", "in", leases.ids), ("is_pdc", "=", True)])

    @api.depends_context("company")
    def _compute_tenant_currency(self):
        for rec in self:
            rec.tenant_currency_id = rec.env.company.currency_id

    @api.depends("tenant_lease_ids.date_start", "tenant_lease_ids.state", "tenant_lease_ids.renewed_from_id")
    def _compute_tenant_tenure(self):
        """Tenure counted from the earliest tenancy, not from the contact.

        A migrated tenant's partner record is younger than their tenancy, so
        create_date would report a ten-year tenant as a new one - and a
        long-standing tenant treated as new is how goodwill gets spent.
        """
        today = fields.Date.context_today(self)
        for rec in self:
            leases = rec.tenant_lease_ids
            starts = [lease.date_start for lease in leases if lease.date_start]
            first = min(starts) if starts else False
            rec.tenant_since = first
            rec.tenant_lease_count = len(leases)
            rec.tenant_live_lease_count = len(leases.filtered(lambda lease: lease.state in LIVE_STATES))
            rec.tenant_renewal_count = len(leases.filtered(lambda lease: lease.renewed_from_id))
            if not first:
                rec.tenant_tenure_display = False
                continue
            days = (today - first).days
            if days < 365:
                rec.tenant_tenure_display = rec.env._("%(days)s days", days=days)
            else:
                years = days / 365
                rec.tenant_tenure_display = rec.env._("%(years)s years", years=f"{years:.1f}")

    @api.depends(
        "tenant_lease_ids.state",
        "tenant_lease_ids.annual_rent",
        "tenant_lease_ids.security_deposit",
        "tenant_lease_ids.cheque_shortfall",
    )
    def _compute_tenant_standing(self):
        """Money on the running tenancies only.

        Lifetime contracted rent is deliberately not a headline figure here.
        It sums what was agreed, never what was received, and a tenant who
        never paid has exactly the same lifetime rent as one who always did.
        Summing it next to the cheque performance would invite reading it as
        a loyalty score.
        """
        for rec in self:
            live = rec.tenant_lease_ids.filtered(lambda lease: lease.state in LIVE_STATES)
            rec.tenant_live_rent = sum(live.mapped("annual_rent"))
            rec.tenant_deposit_held = sum(live.mapped("security_deposit"))
            rec.tenant_cheque_shortfall = sum(live.mapped("cheque_shortfall"))

    @api.depends(
        "tenant_lease_ids.payment_ids.pdc_state",
        "tenant_lease_ids.payment_ids.has_bounced",
        # The tone reads tenant_cheque_shortfall, which a different compute
        # produces. Declared here so the tone follows it: a dependency that
        # exists in the code but not in @api.depends is how a screen comes to
        # show a stale colour beside a fresh number.
        "tenant_lease_ids.cheque_shortfall",
    )
    def _compute_tenant_cheques(self):
        """The instrument register, bucketed by every state the model has.

        The buckets walk PDC_STATES rather than being listed here. A state
        added to the instrument model and forgotten in this screen would raise
        nothing at all - the cheques in it would simply stop being counted,
        and a cheque register that quietly undercounts is worse than one that
        is obviously broken.
        """
        labels = dict(PDC_STATES)
        for rec in self:
            instruments = rec._tenant_instruments()
            by_state = {state: instruments.filtered(lambda p, s=state: p.pdc_state == s) for state, _l in PDC_STATES}

            custody = sum(len(by_state[state]) for state in CUSTODY_STATES)
            rec.tenant_custody_count = custody
            rec.tenant_custody_amount = sum(sum(by_state[state].mapped("amount")) for state in CUSTODY_STATES)
            ever_bounced = len(instruments.filtered("has_bounced"))
            cleared = len(by_state["cleared"])
            rec.tenant_ever_bounced_count = ever_bounced
            rec.tenant_cleared_count = cleared
            rec.tenant_bounce_rate = self.env["account.payment"]._c2p_bounce_rate(ever_bounced, cleared)

            # Tone on the *current* state, not the history: a tenant who
            # bounced a cheque two years ago and has paid since is not a
            # crisis, and colouring them red forever means the colour stops
            # carrying information.
            if by_state["bounced"]:
                rec.tenant_cheque_tone = "critical"
            elif ever_bounced or rec.tenant_cheque_shortfall:
                rec.tenant_cheque_tone = "warn"
            else:
                rec.tenant_cheque_tone = "ok"

            rows = [
                Markup('<div class="sin-row"><span class="sin-label">%(label)s</span><span>%(count)s</span></div>')
                % {"label": labels[state], "count": len(by_state[state])}
                for state, _label in PDC_STATES
                if by_state[state]
            ]
            if not rows:
                rec.tenant_cheque_breakdown = Markup(
                    '<div class="sin-empty"><div class="sin-empty__title">%s</div>'
                    '<div class="sin-empty__body">%s</div></div>'
                ) % (
                    rec.env._("No cheques on record"),
                    rec.env._("Cheques appear here once they are registered against a tenancy."),
                )
                continue
            rec.tenant_cheque_breakdown = Markup('<div class="sin-stack">%s</div>') % Markup("").join(rows)

    @api.depends(
        "tenant_lease_ids.state",
        "tenant_lease_ids.days_to_expiry",
        "tenant_lease_ids.cheques_complete",
        "tenant_lease_ids.cheque_exception_ids.state",
        "tenant_lease_ids.payment_ids.pdc_state",
        "tenant_lease_ids.payment_ids.has_bounced",
    )
    def _compute_tenant_alert(self):
        """Every current concern, worst first - stacked, not exclusive.

        A tenant who has a returned cheque *and* is weeks from expiry is in
        both, and showing only the first hides the conversation that actually
        needs having. Same `sin-blocked` treatment as the unit release
        checklist and the building alert, so "needs attention" looks the same
        wherever it appears.
        """
        for rec in self:
            live = rec.tenant_lease_ids.filtered(lambda lease: lease.state in LIVE_STATES)
            instruments = rec._tenant_instruments()
            exceptions = rec.tenant_lease_ids.mapped("cheque_exception_ids")
            concerns = []

            if exceptions.filtered(lambda e: e.state == "breached"):
                concerns.append(rec.env._("A cheque exception passed its deadline with cheques still outstanding"))
            if instruments.filtered(lambda p: p.pdc_state == "bounced"):
                concerns.append(rec.env._("A cheque is currently returned unpaid"))
            short = live.filtered(lambda lease: not lease.cheques_complete)
            if short:
                concerns.append(rec.env._("A running tenancy does not have its full cheque set"))
            if exceptions.filtered(lambda e: e.state in ("draft", "approved")):
                concerns.append(rec.env._("A cheque exception is open on this tenant"))
            expiring = live.filtered(lambda lease: 0 <= lease.days_to_expiry <= EXPIRING_SOON_DAYS)
            if expiring:
                concerns.append(
                    rec.env._(
                        "Tenancy expires in %(days)s days",
                        days=min(expiring.mapped("days_to_expiry")),
                    )
                )
            if instruments.filtered("has_bounced") and not instruments.filtered(lambda p: p.pdc_state == "bounced"):
                concerns.append(rec.env._("Has bounced a cheque before, since made good"))

            if not concerns:
                rec.tenant_alert = False
                continue
            items = Markup("").join(Markup("<li>%s</li>") % concern for concern in concerns)
            rec.tenant_alert = Markup(
                '<div class="sin-blocked">'
                '<div class="sin-blocked__title">%(title)s</div>'
                '<ul class="sin-blocked__list">%(items)s</ul>'
                "</div>"
            ) % {"title": rec.env._("Needs attention"), "items": items}

    # ------------------------------------------------------------------ actions
    def action_tenant_cheques(self):
        """Open the register this dossier counted.

        A figure nobody can open is a figure nobody can check, and this
        project has already shipped two that were quietly wrong - an occupancy
        of 8200% and a vacancy loss that under-reported by every unit being
        marketed. The drill-through is not a convenience; it is how the number
        gets audited.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Cheques"),
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", self._tenant_instruments().ids)],
        }

    def action_tenant_ever_bounced(self):
        self.ensure_one()
        instruments = self._tenant_instruments().filtered("has_bounced")
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Ever bounced"),
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", instruments.ids)],
        }
