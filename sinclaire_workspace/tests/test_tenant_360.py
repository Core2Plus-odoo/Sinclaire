"""Tenant 360: the figures on the dossier, and what they must never say.

BR-098 asks for tenancy and payment performance per tenant. The risk in a
screen like this is not that it crashes - it is that it quietly reports the
wrong number, which is the defect this project has shipped twice. So most of
these tests are about agreement: the dossier against the register it
summarises, the dossier against the Command Center, and the buckets against
the instrument model's own state list.
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.c2p_property_lease.models.account_payment import CUSTODY_STATES
from odoo.addons.c2p_property_lease.models.account_payment import PDC_STATES
from odoo.addons.c2p_property_lease.models.lease import RENEWAL_ALERT_DAYS
from odoo.addons.sinclaire_workspace.models.res_partner import EXPIRING_SOON_DAYS
from odoo.tests.common import TransactionCase


class Tenant360Case(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "T360 Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "T360 Tenant"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "T360 Properties"})
        cls.today = fields.Date.context_today(cls.env.user)

    def _journal(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            self.skipTest("no bank journal with an inbound payment method")
        return journal

    def _building(self, code):
        return self.env["c2p.building"].create(
            {
                "name": f"{code} Tower",
                "code": code,
                "owner_id": self.landlord.id,
                "operating_model": "head_lease",
                "analytic_account_id": self.env["account.analytic.account"]
                .create({"name": f"{code} Tower", "plan_id": self.plan.id})
                .id,
            }
        )

    def _lease(self, code, name, start="2026-01-01", end="2026-12-31", rent=120000.0, **kw):
        unit = self.env["c2p.unit"].create(
            {
                "name": name,
                "building_id": self._building(code).id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": rent,
                "dewa_no": f"31{abs(hash(name)) % 100000:05d}",
            }
        )
        unit.sudo().action_release()
        vals = {
            "unit_id": unit.id,
            "tenant_id": self.tenant.id,
            "date_start": start,
            "date_end": end,
            "annual_rent": rent,
            "cheque_count": "4",
        }
        vals.update(kw)
        return self.env["c2p.lease"].create(vals)

    def _cheque(self, lease, no, amount=30000.0, days=30, **kw):
        journal = self._journal()
        vals = {
            "partner_id": self.tenant.id,
            "partner_type": "customer",
            "payment_type": "inbound",
            "amount": amount,
            "journal_id": journal.id,
            "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
            "lease_id": lease.id,
            "cheque_no": no,
            "maturity_date": self.today + timedelta(days=days),
        }
        vals.update(kw)
        return self.env["account.payment"].create(vals)


class TestTheDossierOnlyAppearsForTenants(Tenant360Case):
    def test_a_contact_with_no_tenancies_has_no_dossier(self):
        """The block is hidden on `tenant_lease_count == 0`.

        Most contacts here are landlords, suppliers and staff. A dossier full
        of zeroes on a supplier record teaches people to ignore the block on
        the records where it matters.
        """
        supplier = self.env["res.partner"].create({"name": "T360 Supplier"})
        self.assertEqual(supplier.tenant_lease_count, 0)
        self.assertFalse(supplier.tenant_alert)
        self.assertFalse(supplier.tenant_tenure_display)

    def test_a_tenancy_makes_the_contact_a_tenant(self):
        self._lease("TAA", "TAA-101")
        self.assertEqual(self.tenant.tenant_lease_count, 1)


class TestTenure(Tenant360Case):
    def test_tenure_runs_from_the_earliest_tenancy_not_the_contact(self):
        """A migrated tenant's partner record is younger than their tenancy.

        Counting from create_date would report a long-standing tenant as a new
        one, which is how goodwill gets spent.
        """
        self._lease("TBA", "TBA-101", start="2021-03-01", end="2022-02-28")
        self._lease("TBB", "TBB-101", start="2026-01-01", end="2026-12-31")
        self.assertEqual(self.tenant.tenant_since, fields.Date.to_date("2021-03-01"))
        self.assertEqual(self.tenant.tenant_lease_count, 2)

    def test_tenure_under_a_year_is_counted_in_days(self):
        """A tenant of two months is not "0.2 years"."""
        self._lease("TBC", "TBC-101", start=fields.Date.to_string(self.today - timedelta(days=40)))
        self.assertIn("40 days", self.tenant.tenant_tenure_display)

    def test_a_renewal_is_counted_as_one(self):
        first = self._lease("TBD", "TBD-101", start="2024-01-01", end="2024-12-31")
        self._lease("TBE", "TBE-101", renewed_from_id=first.id)
        self.assertEqual(self.tenant.tenant_renewal_count, 1)


class TestStanding(Tenant360Case):
    def test_contracted_rent_counts_only_the_running_tenancies(self):
        """A tenant's previous tenancy is not rent they are still paying.

        Summing every tenancy ever signed would report a tenant of ten years
        as owing ten years of rent a year.
        """
        live = self._lease("TCA", "TCA-101", rent=120000.0, security_deposit=6000.0)
        live._activate_as_loaded()
        self._lease("TCB", "TCB-101", rent=90000.0, state="expired")
        self.tenant.invalidate_recordset()
        self.assertEqual(self.tenant.tenant_live_rent, 120000.0)
        self.assertEqual(self.tenant.tenant_deposit_held, 6000.0)
        self.assertEqual(self.tenant.tenant_lease_count, 2)

    def test_an_expired_tenancy_leaves_no_contracted_rent_behind(self):
        self._lease("TCC", "TCC-101", rent=90000.0, state="expired")
        self.assertEqual(self.tenant.tenant_live_rent, 0.0)
        self.assertEqual(self.tenant.tenant_deposit_held, 0.0)

    def test_the_shortfall_is_the_money_not_the_count(self):
        """BR-075 reports exposure, and the exposure is the dirhams."""
        lease = self._lease("TCD", "TCD-101", rent=120000.0)
        lease._activate_as_loaded()
        self._cheque(lease, "500001", amount=30000.0)
        self.tenant.invalidate_recordset()
        self.assertEqual(self.tenant.tenant_cheque_shortfall, 90000.0)


class TestTheChequeRegister(Tenant360Case):
    def test_every_instrument_state_is_classified_as_custody_or_not(self):
        """The guard on CUSTODY_STATES being a hand-written subset.

        Adding a state to PDC_STATES and forgetting it here would silently
        drop those cheques out of the "in hand" figure, and client money that
        stops being counted is the one error in this register nobody notices
        until an audit. This fails the moment a state is added without a
        decision being made about it.
        """
        known = {state for state, _label in PDC_STATES}
        self.assertTrue(set(CUSTODY_STATES) <= known, "CUSTODY_STATES names a state the model does not have")
        # Every state must be either custody or deliberately not; the test
        # exists so the list below has to be revisited, not so it stays true.
        classified = set(CUSTODY_STATES) | {"expected", "cleared", "bounced", "replaced", "cancelled"}
        self.assertEqual(known, classified, "an instrument state is neither classified as custody nor as resolved")

    def test_cheques_in_hand_counts_exactly_the_custody_states(self):
        lease = self._lease("TDA", "TDA-101")
        held = self._cheque(lease, "200001")
        deposited = self._cheque(lease, "200002")
        deposited.action_pdc_deposit()
        cleared = self._cheque(lease, "200003")
        cleared.action_pdc_deposit()
        cleared.action_pdc_clear()
        self.assertEqual(self.tenant.tenant_custody_count, 2)
        self.assertEqual(self.tenant.tenant_custody_amount, held.amount + deposited.amount)

    def test_the_breakdown_is_built_from_the_models_own_state_list(self):
        """Buckets walk PDC_STATES, so a new state cannot go uncounted."""
        lease = self._lease("TDB", "TDB-101")
        self._cheque(lease, "200010")
        labels = dict(PDC_STATES)
        self.assertIn(labels["held"], self.tenant.tenant_cheque_breakdown)

    def test_a_tenant_with_no_cheques_is_told_so_rather_than_shown_zeroes(self):
        self._lease("TDC", "TDC-101")
        self.assertIn("No cheques on record", self.tenant.tenant_cheque_breakdown)

    def test_the_drill_through_opens_exactly_what_the_dossier_counted(self):
        """A figure nobody can open is a figure nobody can check.

        This project has shipped two that were quietly wrong, so the
        drill-through is the audit rather than a convenience.
        """
        lease = self._lease("TDD", "TDD-101")
        self._cheque(lease, "200020")
        self._cheque(lease, "200021")
        action = self.tenant.action_tenant_cheques()
        opened = self.env["account.payment"].search(action["domain"])
        self.assertEqual(len(opened), 2)
        self.assertEqual(opened, self.tenant._tenant_instruments())

    def test_a_payment_not_on_a_tenancy_is_not_this_tenants_performance(self):
        """Instruments are reached through the leases, not through partner_id.

        An unrelated payment recorded against the contact landing in the
        bounce rate is a figure that gets a tenant chased for somebody else's
        cheque.
        """
        lease = self._lease("TDE", "TDE-101")
        self._cheque(lease, "200030")
        journal = self._journal()
        self.env["account.payment"].create(
            {
                "partner_id": self.tenant.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "amount": 500.0,
                "journal_id": journal.id,
                "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
                "cheque_no": "999999",
            }
        )
        self.assertEqual(len(self.tenant._tenant_instruments()), 1)


class TestTheBounceRate(Tenant360Case):
    def test_a_replaced_bounce_still_counts_against_the_tenant(self):
        """The whole reason `has_bounced` exists.

        If a replacement took the cheque out of the numerator, working through
        a backlog of returned cheques would walk the rate down to zero while
        the tenant's payment behaviour stayed exactly as bad.
        """
        lease = self._lease("TEA", "TEA-101")
        bounced = self._cheque(lease, "300001")
        bounced.action_pdc_deposit()
        bounced.action_pdc_bounce()
        replacement = self._cheque(lease, "300002")
        bounced.action_link_replacement(replacement)
        self.assertEqual(bounced.pdc_state, "replaced")
        self.assertTrue(bounced.has_bounced)
        self.assertEqual(self.tenant.tenant_ever_bounced_count, 1)

    def test_the_rate_uses_the_shared_definition(self):
        """One definition, so the dossier and the Command Center agree.

        Two copies of a ratio is how a client comes to be shown two different
        bounce rates for the same tenant on the same morning.
        """
        lease = self._lease("TEB", "TEB-101")
        bounced = self._cheque(lease, "300010")
        bounced.action_pdc_deposit()
        bounced.action_pdc_bounce()
        cleared = self._cheque(lease, "300011")
        cleared.action_pdc_deposit()
        cleared.action_pdc_clear()
        expected = self.env["account.payment"]._c2p_bounce_rate(
            self.tenant.tenant_ever_bounced_count, self.tenant.tenant_cleared_count
        )
        self.assertEqual(self.tenant.tenant_bounce_rate, expected)
        self.assertEqual(self.tenant.tenant_bounce_rate, 50.0)

    def test_cheques_still_in_hand_are_not_in_the_denominator(self):
        """Otherwise the rate improves every time a tenant hands over a
        cheque, before anybody knows whether it is good."""
        lease = self._lease("TEC", "TEC-101")
        bounced = self._cheque(lease, "300020")
        bounced.action_pdc_deposit()
        bounced.action_pdc_bounce()
        self._cheque(lease, "300021")
        self._cheque(lease, "300022")
        self.assertEqual(self.tenant.tenant_bounce_rate, 100.0)

    def test_a_tenant_with_nothing_concluded_has_no_rate_rather_than_a_bad_one(self):
        lease = self._lease("TED", "TED-101")
        self._cheque(lease, "300030")
        self.assertEqual(self.tenant.tenant_bounce_rate, 0.0)

    def test_the_bounce_date_records_the_first_failure_only(self):
        lease = self._lease("TEE", "TEE-101")
        cheque = self._cheque(lease, "300040")
        cheque.action_pdc_deposit()
        cheque.action_pdc_bounce()
        first = cheque.bounced_date
        cheque.action_pdc_bounce()
        self.assertEqual(cheque.bounced_date, first)

    def test_the_tone_follows_the_current_state_not_the_history(self):
        """A tenant who bounced two years ago and has paid since is not a
        crisis, and colouring them red forever means the colour stops
        carrying information."""
        lease = self._lease("TEF", "TEF-101")
        bounced = self._cheque(lease, "300050")
        bounced.action_pdc_deposit()
        bounced.action_pdc_bounce()
        self.assertEqual(self.tenant.tenant_cheque_tone, "critical")
        bounced.action_link_replacement(self._cheque(lease, "300051"))
        self.tenant.invalidate_recordset()
        self.assertEqual(self.tenant.tenant_cheque_tone, "warn")


class TestTheAlert(Tenant360Case):
    def test_concerns_stack_rather_than_replacing_each_other(self):
        """A tenant weeks from expiry *and* with a returned cheque is in both.

        Showing only the first hides the conversation that actually needs
        having.
        """
        lease = self._lease(
            "TFA",
            "TFA-101",
            start=fields.Date.to_string(self.today - timedelta(days=300)),
            end=fields.Date.to_string(self.today + timedelta(days=20)),
        )
        lease._activate_as_loaded()
        cheque = self._cheque(lease, "400001")
        cheque.action_pdc_deposit()
        cheque.action_pdc_bounce()
        alert = self.tenant.tenant_alert
        self.assertIn("returned unpaid", alert)
        self.assertIn("expires in 20 days", alert)

    def test_a_tenant_with_nothing_wrong_gets_no_banner(self):
        """A banner that is always there is one nobody reads."""
        lease = self._lease("TFB", "TFB-101", end=fields.Date.to_string(self.today + timedelta(days=300)))
        for i in range(4):
            self._cheque(lease, f"41000{i}", amount=30000.0)
        lease._activate_as_loaded()
        self.tenant.invalidate_recordset()
        self.assertFalse(self.tenant.tenant_alert)

    def test_the_expiry_window_is_the_crons_outermost_band(self):
        """The dossier and the renewal alert must agree about "expiring".

        Both read RENEWAL_ALERT_DAYS. A second 90 typed into this module is
        the recurring defect in this codebase, and it would show as a tenancy
        the dossier calls expiring with no activity raised, or the reverse.
        """
        self.assertEqual(EXPIRING_SOON_DAYS, max(RENEWAL_ALERT_DAYS))
        self.assertEqual(EXPIRING_SOON_DAYS, 90)
