"""Tenant 360 — everything known about a tenant, in one round trip.

BR-098 (§5.3) asks for tenancy monitoring: payment and cheque performance,
arrears, bounces and the rest, each tied to a date and an owner. The event log
that requirement also describes does not exist yet, so this is the half that
can be built from what the system already holds — the tenancy history and the
instrument register — and it is where that log will surface when it lands.

The shape follows the dossier pattern rather than a form view with a dozen
related tabs: one backend call returns the whole screen, because fetching a
dozen record sets one `search` at a time from the browser means a dozen
sequential round trips before anything paints.

Every summary figure carries the **domain that produced it**. A number on a
dossier that cannot be opened is a number nobody can check, and this module
has already shipped two figures that were quietly wrong (an occupancy of
8200%, a vacancy loss that under-reported by every unit being marketed). The
drill-through is not a convenience; it is how the figure gets audited.
"""

from odoo import api
from odoo import fields
from odoo import models

from .account_payment import CUSTODY_STATES
from .account_payment import PDC_STATES
from .lease import CLOSED_STATES
from .lease import LIVE_STATES
from .lease import PRE_ACTIVE_STATES

# A tenancy inside this window is close enough to expiry that whoever opens the
# dossier should see it without going looking. Matches the outermost band of
# the 90/60/30 renewal alerts the lease cron already raises, so the dossier and
# the alert agree about what "expiring" means.
EXPIRING_SOON_DAYS = 90


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _tenant_lease_domain(self):
        self.ensure_one()
        return [("tenant_id", "=", self.id)]

    @api.model
    def _tenant_instrument_domain(self, lease_ids):
        """Cheques are reached through the leases, not through the partner.

        A tenant's instruments are the ones written against their tenancies.
        `partner_id` would also catch a payment somebody recorded against the
        contact for an unrelated reason, which is not tenancy performance.
        """
        return [("lease_id", "in", list(lease_ids)), ("is_pdc", "=", True)]

    # ------------------------------------------------------------------ dossier
    def get_tenant_profile(self):
        """Everything the Tenant 360 renders, in a single round trip."""
        self.ensure_one()
        leases = self.env["c2p.lease"].search(self._tenant_lease_domain(), order="date_start desc")
        instruments = self.env["account.payment"].search(self._tenant_instrument_domain(leases.ids))
        live = leases.filtered(lambda lease: lease.state in LIVE_STATES)
        current = live[:1]

        return {
            "id": self.id,
            "name": self.display_name,
            "avatar": f"/web/image/res.partner/{self.id}/avatar_128",
            "is_company": self.is_company,
            "email": self.email or "",
            "phone": self.phone or "",
            "city": self.city or "",
            "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in self.category_id],
            "currency": (self.env.company.currency_id.name or "AED"),
            "tenure": self._tenant_tenure(leases),
            "current": self._tenant_current(current),
            "standing": self._tenant_standing(leases, live),
            "cheques": self._tenant_cheques(leases, instruments),
            "risk": self._tenant_risk(leases, live, instruments),
            "exceptions": self._tenant_exceptions(leases),
            "history": self._tenant_history(leases),
            "upcoming": self._tenant_upcoming(live, instruments),
            "domains": {
                "leases": self._tenant_lease_domain(),
                "instruments": self._tenant_instrument_domain(leases.ids),
            },
        }

    # --- sections ---------------------------------------------------------
    def _tenant_tenure(self, leases):
        """How long this tenant has been one, counted from the earliest
        tenancy rather than from when the contact record was created — a
        migrated tenant's partner record is younger than their tenancy."""
        starts = [lease.date_start for lease in leases if lease.date_start]
        first = min(starts) if starts else None
        today = fields.Date.context_today(self)
        return {
            "first_lease_start": fields.Date.to_string(first) if first else None,
            "days": (today - first).days if first else None,
            "lease_count": len(leases),
            "renewal_count": len(leases.filtered(lambda lease: lease.renewed_from_id)),
        }

    def _tenant_current(self, current):
        if not current:
            return None
        labels = dict(current._fields["state"].selection)
        return {
            "id": current.id,
            "name": current.name,
            "state": current.state,
            "state_label": labels.get(current.state, current.state),
            "unit": current.unit_id.display_name or "",
            "unit_id": current.unit_id.id,
            "building": current.building_id.name or "",
            "building_id": current.building_id.id,
            "landlord": current.owner_id.name or "",
            "date_start": fields.Date.to_string(current.date_start) if current.date_start else None,
            "date_end": fields.Date.to_string(current.date_end) if current.date_end else None,
            "days_to_expiry": current.days_to_expiry,
            "annual_rent": current.annual_rent,
            "instalment_amount": current.instalment_amount,
            "cheque_count": int(current.cheque_count or 0),
            "ejari_no": current.ejari_no or "",
            "cheques_complete": current.cheques_complete,
            "cheque_shortfall": current.cheque_shortfall,
        }

    def _tenant_standing(self, leases, live):
        """Money, split between what is running and what has ever run.

        Lifetime rent sums the contracted annual rent of every tenancy. It is
        a contracted figure, not a collected one: what was actually received
        is the cheque register below, and conflating the two is how a tenant
        who never paid comes to look like a good one.
        """
        return {
            "contracted_rent": sum(live.mapped("annual_rent")),
            "deposit_held": sum(live.mapped("security_deposit")),
            "commission": sum(live.mapped("commission")),
            "lifetime_contracted": sum(leases.mapped("annual_rent")),
            "live_lease_count": len(live),
        }

    def _tenant_cheques(self, leases, instruments):
        """The instrument register, bucketed by every state the model has.

        The buckets are derived from PDC_STATES rather than listed here. A
        state added to the instrument model but missing from this dossier
        would not raise anything — the cheques in it would simply stop being
        counted — and that is the failure this repository keeps repeating.
        """
        buckets = {
            state: {
                "label": label,
                "count": 0,
                "amount": 0.0,
                "domain": [*self._tenant_instrument_domain(leases.ids), ("pdc_state", "=", state)],
            }
            for state, label in PDC_STATES
        }
        for payment in instruments:
            bucket = buckets.get(payment.pdc_state)
            if bucket is None:
                continue
            bucket["count"] += 1
            bucket["amount"] += payment.amount

        ever_bounced = instruments.filtered("has_bounced")
        cleared = instruments.filtered(lambda p: p.pdc_state == "cleared")
        # Concluded, for the ratio, means the instrument reached an outcome:
        # it cleared, or it failed at least once. Same numerator as the
        # Command Center, through the same helper, so the two screens cannot
        # drift into reporting different bounce rates for the same tenant.
        return {
            "buckets": [dict(buckets[state], state=state) for state, _label in PDC_STATES],
            "in_custody": sum(buckets[state]["count"] for state in CUSTODY_STATES),
            "in_custody_amount": sum(buckets[state]["amount"] for state in CUSTODY_STATES),
            "expected_total": sum(leases.mapped("cheques_expected")),
            "received_total": sum(leases.mapped("cheques_received")),
            "cover": sum(leases.mapped("cheque_cover")),
            "shortfall": sum(leases.mapped("cheque_shortfall")),
            "ever_bounced": len(ever_bounced),
            "cleared": len(cleared),
            "bounce_rate": self.env["account.payment"]._c2p_bounce_rate(len(ever_bounced), len(cleared)),
            "ever_bounced_domain": [
                *self._tenant_instrument_domain(leases.ids),
                ("has_bounced", "=", True),
            ],
        }

    def _tenant_risk(self, leases, live, instruments):
        """The flags worth seeing before speaking to this tenant.

        Stacked, not exclusive: a tenant who has bounced a cheque *and* is
        weeks from expiry is in both, and showing only the first would hide
        the conversation that actually needs having.
        """
        exceptions = leases.mapped("cheque_exception_ids")
        expiring = live.filtered(
            lambda lease: lease.days_to_expiry is not None and 0 <= lease.days_to_expiry <= EXPIRING_SOON_DAYS
        )
        return {
            "ever_bounced": bool(instruments.filtered("has_bounced")),
            "bounced_now": bool(instruments.filtered(lambda p: p.pdc_state == "bounced")),
            "cheques_short": bool(live.filtered(lambda lease: not lease.cheques_complete)),
            "open_exception": bool(exceptions.filtered(lambda e: e.state in ("draft", "approved"))),
            "breached_exception": bool(exceptions.filtered(lambda e: e.state == "breached")),
            "expiring_soon": bool(expiring),
            "expiring_days": min(expiring.mapped("days_to_expiry")) if expiring else None,
            "no_live_tenancy": not live,
            "window_days": EXPIRING_SOON_DAYS,
        }

    def _tenant_exceptions(self, leases):
        """BR-075 exceptions raised against this tenant's tenancies.

        On the dossier because a tenant who has repeatedly been let in without
        their cheques is a pattern, and the pattern is invisible from any one
        lease.
        """
        labels = dict(self.env["c2p.lease.cheque.exception"]._fields["state"].selection)
        return [
            {
                "id": exception.id,
                "lease": exception.lease_id.name,
                "lease_id": exception.lease_id.id,
                "state": exception.state,
                "state_label": labels.get(exception.state, exception.state),
                "missing_cheque_count": exception.missing_cheque_count,
                "missing_amount": exception.missing_amount,
                "deadline": fields.Date.to_string(exception.deadline) if exception.deadline else None,
                "approved_by": exception.approved_by_id.name or "",
                "responsible": exception.responsible_user_id.name or "",
                "is_overdue": exception.is_overdue,
            }
            for exception in leases.mapped("cheque_exception_ids")
        ]

    def _tenant_history(self, leases):
        labels = dict(self.env["c2p.lease"]._fields["state"].selection)
        return [
            {
                "id": lease.id,
                "name": lease.name,
                "unit": lease.unit_id.display_name or "",
                "building": lease.building_id.name or "",
                "date_start": fields.Date.to_string(lease.date_start) if lease.date_start else None,
                "date_end": fields.Date.to_string(lease.date_end) if lease.date_end else None,
                "annual_rent": lease.annual_rent,
                "state": lease.state,
                "state_label": labels.get(lease.state, lease.state),
                "is_live": lease.state in LIVE_STATES,
                "is_closed": lease.state in CLOSED_STATES,
                "is_pre_active": lease.state in PRE_ACTIVE_STATES,
                "renewed_from": lease.renewed_from_id.name or "",
            }
            for lease in leases
        ]

    def _tenant_upcoming(self, live, instruments):
        """What falls due next: maturities still in our hands, then expiry.

        Only instruments in custody, because an expected cheque has a date but
        nothing behind it, and a cleared one has already happened.
        """
        today = fields.Date.context_today(self)
        due = instruments.filtered(
            lambda p: p.pdc_state in CUSTODY_STATES and p.maturity_date and p.maturity_date >= today
        ).sorted("maturity_date")
        items = [
            {
                "kind": "cheque",
                "date": fields.Date.to_string(payment.maturity_date),
                "days_away": (payment.maturity_date - today).days,
                "label": payment.cheque_no or "",
                "detail": payment.cheque_bank or "",
                "amount": payment.amount,
                "res_id": payment.id,
                "res_model": "account.payment",
            }
            for payment in due[:5]
        ]
        for lease in live:
            if lease.date_end and lease.date_end >= today:
                items.append(
                    {
                        "kind": "expiry",
                        "date": fields.Date.to_string(lease.date_end),
                        "days_away": (lease.date_end - today).days,
                        "label": lease.name,
                        "detail": lease.unit_id.display_name or "",
                        "amount": lease.annual_rent,
                        "res_id": lease.id,
                        "res_model": "c2p.lease",
                    }
                )
        return sorted(items, key=lambda item: item["date"])

    # ------------------------------------------------------------------ action
    def action_tenant_360(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "c2p_tenant_360",
            "name": self.env._("Tenant 360"),
            "params": {"partner_id": self.id},
            "context": {"active_id": self.id},
        }
