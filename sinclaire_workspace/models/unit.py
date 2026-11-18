from markupsafe import Markup

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.c2p_property_lease.models.unit import RELEASE_REQUIREMENTS


class C2pUnit(models.Model):
    """Presentation-only additions for Unit 360.

    The property module already knows exactly why a unit cannot be released:
    RELEASE_REQUIREMENTS is a list of named checks and release_blockers joins
    the failing ones into a sentence. What was missing was putting that in
    front of the person looking at the greyed-out button.

    A disabled control that will not say why is the most common complaint
    about internal systems, and it is entirely avoidable here, because the
    reason already exists as data.
    """

    _inherit = "c2p.unit"

    release_checklist = fields.Html(
        compute="_compute_release_checklist",
        sanitize=False,
        string="Readiness",
        help="What is still missing before this unit can be released for letting.",
    )

    @api.depends(
        "state",
        "unit_type",
        "floor",
        "area_sqft",
        "market_rent",
        "dewa_no",
        "building_id.analytic_account_id",
    )
    def _compute_release_checklist(self):
        """The same checks the release gate runs, rendered as a list.

        Deliberately derived from RELEASE_REQUIREMENTS rather than re-listed
        here. A second copy of the rules would drift from the first, and the
        screen would start confidently naming the wrong reason - which is
        worse than saying nothing, because somebody would go and fix the
        thing it named.
        """
        for rec in self:
            if rec.state != "draft":
                rec.release_checklist = False
                continue
            missing = [label for _f, label, ok in RELEASE_REQUIREMENTS if not ok(rec)]
            if not missing:
                rec.release_checklist = Markup(
                    "<div class=\"sin-blocked sin-blocked--ready\"><div class='sin-blocked__title'>%s</div></div>"
                ) % rec.env._("Ready to release for letting")
                continue
            items = Markup("").join(Markup("<li>%s</li>") % label for label in missing)
            rec.release_checklist = Markup(
                '<div class="sin-blocked">'
                '<div class="sin-blocked__title">%(title)s</div>'
                '<ul class="sin-blocked__list">%(items)s</ul>'
                "</div>"
            ) % {
                "title": rec.env._("This unit cannot be released for letting yet"),
                "items": items,
            }
