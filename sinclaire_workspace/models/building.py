from odoo import api
from odoo import fields
from odoo import models

# Occupancy below this reads as a problem worth surfacing on the card rather
# than a number to go and look up. Not a target - the business sets those -
# just the point at which a portfolio screen should stop being quiet.
LOW_OCCUPANCY = 75.0

# Coverage is contracted tenant rent over the head lease cost. Below 1.0 the
# building is not covering what we owe the landlord, which is the single most
# serious thing a head-leased building can be.
COVERAGE_FLOOR = 1.0


class C2pBuilding(models.Model):
    """Presentation-only additions for the portfolio screen.

    Nothing here is a new business rule. Every value is read off fields the
    property module already computes; what this adds is the ranking - which
    one of several true statements about a building is the one to put on its
    card.

    That ranking is the whole point. A card with six badges on it has told
    the reader nothing, because they still have to decide what matters. A
    card with one line has done the deciding.
    """

    _inherit = "c2p.building"

    portfolio_alert = fields.Char(
        compute="_compute_portfolio_alert",
        string="Needs Attention",
        help="The most serious open issue on this building, in plain language.",
    )
    portfolio_tone = fields.Selection(
        [("ok", "OK"), ("warn", "Needs attention"), ("critical", "Critical")],
        compute="_compute_portfolio_alert",
        search="_search_portfolio_tone",
        help="Severity of portfolio_alert, used to colour the occupancy meter.",
    )
    # The money figure on the card means two different things depending on the
    # operating model, and the two must never be confused - that is BR-019 and
    # BRD §6.1. Rather than let a view pick the wrong field, the label travels
    # with the value.
    portfolio_money_label = fields.Char(compute="_compute_portfolio_money")
    portfolio_money = fields.Monetary(compute="_compute_portfolio_money")
    portfolio_money_display = fields.Char(
        compute="_compute_portfolio_money",
        string="Card Figure",
        help="The money figure shortened to fit a card, e.g. AED 1.3m.",
    )

    @api.depends(
        "operating_model",
        "coverage_ratio",
        "occupancy_rate",
        "vacant_count",
        "unit_count",
        "units_reconciled",
        "unit_variance",
        "head_lease_id",
    )
    def _compute_portfolio_alert(self):
        """One line per building, worst thing first.

        The order below is the argument. Money the company is losing beats a
        data-quality problem, which beats an empty flat, because that is the
        order somebody would deal with them in. A building with nothing wrong
        says nothing - an "All good" badge on every card is noise that trains
        people to stop reading the badges.
        """
        for rec in self:
            rec.portfolio_alert = False
            rec.portfolio_tone = "ok"

            if rec.operating_model == "brokerage":
                # Brokerage buildings carry no tenancies of ours, so occupancy
                # and coverage say nothing about them.
                continue

            if rec.unit_count == 0:
                rec.portfolio_alert = rec.env._("No units recorded yet")
                rec.portfolio_tone = "warn"
                continue

            if rec.operating_model == "head_lease":
                if rec.head_lease_id and rec.coverage_ratio < COVERAGE_FLOOR:
                    rec.portfolio_alert = rec.env._(
                        "Coverage %(ratio).2f — tenant rent is not covering the head lease",
                        ratio=rec.coverage_ratio,
                    )
                    rec.portfolio_tone = "critical"
                    continue
                if not rec.head_lease_id:
                    rec.portfolio_alert = rec.env._("Head leased, but no active head lease on record")
                    rec.portfolio_tone = "critical"
                    continue

            if not rec.units_reconciled:
                # BR-016. A building that does not reconcile is one whose
                # figures cannot be trusted, so it outranks an empty flat.
                if rec.declared_unit_count:
                    rec.portfolio_alert = rec.env._(
                        "%(count)s units on record against %(declared)s declared",
                        count=rec.unit_count,
                        declared=rec.declared_unit_count,
                    )
                else:
                    rec.portfolio_alert = rec.env._("No declared unit count to reconcile against")
                rec.portfolio_tone = "warn"
                continue

            if rec.occupancy_rate < LOW_OCCUPANCY and rec.vacant_count:
                rec.portfolio_alert = rec.env._(
                    "%(vacant)s of %(total)s units vacant",
                    vacant=rec.vacant_count,
                    total=rec.unit_count,
                )
                rec.portfolio_tone = "warn"

    def _search_portfolio_tone(self, operator, value):
        """Make "Needs attention" one click rather than a filter each person
        builds for themselves.

        The tone cannot simply be stored: it depends on coverage_ratio and
        head_lease_id, which are non-stored computes in the property module,
        and a stored field hanging off those would go stale without anything
        saying so. Storing it properly means storing those two first, which is
        a change to the supplier module and a migration - worth doing, but not
        smuggled in behind a search filter.

        So this computes in Python over the building set. A portfolio is
        hundreds of rows, not millions, and this runs on a user clicking a
        filter rather than in a loop. If the portfolio ever reaches a size
        where this is slow, the fix is to store the two underlying fields,
        not to make this cleverer.
        """
        if operator not in ("=", "!=", "in", "not in"):
            raise ValueError(self.env._("Unsupported operator %s for portfolio_tone", operator))

        wanted = set(value if isinstance(value, (list, tuple)) else [value])
        negated = operator in ("!=", "not in")

        matching = (
            self.with_context(active_test=False).search([]).filtered(lambda b: (b.portfolio_tone in wanted) != negated)
        )
        return [("id", "in", matching.ids)]

    @api.depends("operating_model", "gross_margin", "managed_rent")
    def _compute_portfolio_money(self):
        """Whose money this is, carried with the number.

        A head-leased building earns this company a margin. An owner-managed
        one earns it a fee, and the rent passing through is the landlord's -
        so the card shows what is being administered, labelled as such. Showing
        a margin there would be the exact error BR-019 was opened to fix, back
        again one layer up.
        """
        for rec in self:
            if rec.operating_model == "head_lease":
                rec.portfolio_money_label = rec.env._("Gross margin")
                rec.portfolio_money = rec.gross_margin
            elif rec.operating_model == "owner_management":
                rec.portfolio_money_label = rec.env._("Managed rent")
                rec.portfolio_money = rec.managed_rent
            else:
                rec.portfolio_money_label = False
                rec.portfolio_money = 0.0
            rec.portfolio_money_display = (
                rec._format_card_amount(rec.portfolio_money) if rec.portfolio_money_label else False
            )

    def _format_card_amount(self, amount):
        """AED 1.3m rather than AED 1,301,900.00.

        Rendering this with the monetary widget overflowed the card and the
        figure came out clipped mid-number - "$ 1,301,900." - which is worse
        than imprecise, because a truncated number still looks like a number.

        A portfolio card answers "which building should I look at?", and two
        significant figures answer that. The exact amount belongs on Building
        360, where there is room for it and where somebody is actually
        reconciling rather than scanning.
        """
        self.ensure_one()
        currency = self.currency_id.name or ""
        value = amount or 0.0
        # U+2212, the real minus sign: a hyphen at this weight reads as a dash
        # against the digits.
        sign = "−" if value < 0 else ""
        magnitude = abs(value)
        if magnitude >= 1_000_000:
            body = f"{magnitude / 1_000_000:.1f}m"
        elif magnitude >= 1_000:
            body = f"{magnitude / 1_000:.0f}k"
        else:
            body = f"{magnitude:.0f}"
        return f"{currency} {sign}{body}".strip()
