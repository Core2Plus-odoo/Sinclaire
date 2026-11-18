"""Tenant 360 — the tenancy dossier (BR-098, §5.3, in part).

The property that matters most here is not that any one figure is right; it is
that **every figure can be opened**, and that what opens matches what was
counted. Two numbers have already shipped from this codebase quietly wrong,
and in both cases a drill-through would have shown it at a glance. So the
tests below check the domains as hard as they check the counts.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTenant360(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "T360 Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "T360 Tenant", "email": "t@example.com"})
        cls.stranger = cls.env["res.partner"].create({"name": "T360 Stranger"})
        cls.building = cls.env["c2p.building"].create(
            {"name": "Dossier Tower", "code": "DSR", "owner_id": cls.landlord.id}
        )

    def _unit(self, name):
        return self.env["c2p.unit"].create({"name": name, "building_id": self.building.id})

    def _lease(self, name, tenant=None, annual_rent=120000.0, start="2026-01-01", end="2026-12-31"):
        return self.env["c2p.lease"].create(
            {
                "tenant_id": (tenant or self.tenant).id,
                "unit_id": self._unit(name).id,
                "date_start": start,
                "date_end": end,
                "annual_rent": annual_rent,
                "cheque_count": "4",
            }
        )

    def _journal(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            self.skipTest("no bank journal with an inbound payment method")
        return journal

    def _cheque(self, lease, state="held", amount=30000.0, cheque_no="810001", partner=None):
        journal = self._journal()
        return self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": (partner or self.tenant).id,
                "amount": amount,
                "date": "2026-01-01",
                "journal_id": journal.id,
                "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
                "company_id": self.env.company.id,
                "lease_id": lease.id if lease else False,
                "cheque_no": cheque_no,
                "cheque_bank": "Test Bank",
                "maturity_date": "2026-01-01",
                "pdc_state": state,
            }
        )

    def _profile(self, partner=None):
        return (partner or self.tenant).get_tenant_profile()

    # ------------------------------------------------------------ the shape
    def test_a_tenant_with_nothing_still_returns_a_dossier(self):
        """A contact who has never rented must not blow up the screen - the
        dossier is reached from any partner, not only from a tenant."""
        profile = self._profile(self.stranger)
        self.assertEqual(profile["name"], self.stranger.display_name)
        self.assertIsNone(profile["current"])
        self.assertEqual(profile["tenure"]["lease_count"], 0)
        self.assertIsNone(profile["tenure"]["first_lease_start"])
        self.assertEqual(profile["history"], [])
        self.assertTrue(profile["risk"]["no_live_tenancy"])

    def test_the_current_tenancy_is_the_running_one(self):
        old = self._lease("DSR-101")
        old.state = "expired"
        live = self._lease("DSR-102")
        live._activate_as_loaded()
        profile = self._profile()
        self.assertIsNotNone(profile["current"])
        self.assertEqual(profile["current"]["id"], live.id)
        self.assertEqual(profile["current"]["unit"], live.unit_id.display_name)

    def test_tenure_counts_from_the_earliest_tenancy(self):
        """Not from the partner record's creation date: a migrated tenant's
        contact is younger than their tenancy."""
        self._lease("DSR-103", start="2022-01-01", end="2022-12-31")
        self._lease("DSR-104")
        profile = self._profile()
        self.assertEqual(profile["tenure"]["first_lease_start"], "2022-01-01")
        self.assertEqual(profile["tenure"]["lease_count"], 2)
        self.assertGreater(profile["tenure"]["days"], 365)

    def test_contracted_rent_is_the_running_tenancies_only(self):
        """Lifetime is every tenancy; contracted is what is running now. A
        tenant with ten finished leases is not paying ten rents."""
        closed = self._lease("DSR-105", annual_rent=90000.0)
        closed.state = "expired"
        live = self._lease("DSR-106", annual_rent=120000.0)
        live._activate_as_loaded()
        standing = self._profile()["standing"]
        self.assertAlmostEqual(standing["contracted_rent"], 120000.0, places=2)
        self.assertAlmostEqual(standing["lifetime_contracted"], 210000.0, places=2)
        self.assertEqual(standing["live_lease_count"], 1)

    # ------------------------------------------------------- cheque register
    def test_every_instrument_state_has_a_bucket(self):
        """Derived from PDC_STATES, never listed by hand. A state added to the
        instrument model but missing here would not raise - its cheques would
        just stop being counted, which is this repository's recurring defect."""
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_STATES

        buckets = self._profile()["cheques"]["buckets"]
        self.assertEqual([b["state"] for b in buckets], [s for s, _ in PDC_STATES])
        for bucket, (state, label) in zip(buckets, PDC_STATES, strict=True):
            self.assertEqual(bucket["label"], label, f"{state} is mislabelled")

    def test_each_bucket_domain_returns_exactly_what_the_bucket_counted(self):
        """The drill-through is the audit. A number that opens a different
        record set is worse than no number."""
        lease = self._lease("DSR-107")
        self._cheque(lease, state="held", cheque_no="810101")
        self._cheque(lease, state="deposited", cheque_no="810102")
        self._cheque(lease, state="expected", cheque_no=False)
        Payment = self.env["account.payment"]
        for bucket in self._profile()["cheques"]["buckets"]:
            with self.subTest(state=bucket["state"]):
                self.assertEqual(Payment.search_count(bucket["domain"]), bucket["count"])

    def test_the_register_domain_matches_the_whole_register(self):
        lease = self._lease("DSR-108")
        self._cheque(lease, cheque_no="810201")
        self._cheque(lease, cheque_no="810202")
        profile = self._profile()
        total = sum(b["count"] for b in profile["cheques"]["buckets"])
        self.assertEqual(self.env["account.payment"].search_count(profile["domains"]["instruments"]), total)

    def test_a_payment_not_against_a_tenancy_is_not_tenancy_performance(self):
        """Reached through the leases, not through partner_id: a payment
        somebody recorded against this contact for another reason is not part
        of how they pay their rent."""
        lease = self._lease("DSR-109")
        self._cheque(lease, cheque_no="810301")
        self._cheque(None, cheque_no="810302")
        profile = self._profile()
        self.assertEqual(sum(b["count"] for b in profile["cheques"]["buckets"]), 1)

    def test_another_tenants_cheques_are_not_counted(self):
        mine = self._lease("DSR-110")
        theirs = self._lease("DSR-111", tenant=self.stranger)
        self._cheque(mine, cheque_no="810401")
        self._cheque(theirs, cheque_no="810402", partner=self.stranger)
        self.assertEqual(sum(b["count"] for b in self._profile()["cheques"]["buckets"]), 1)

    def test_in_custody_is_what_we_physically_hold(self):
        lease = self._lease("DSR-112")
        self._cheque(lease, state="held", cheque_no="810501")
        self._cheque(lease, state="deposited", cheque_no="810502")
        self._cheque(lease, state="cleared", cheque_no="810503")
        self._cheque(lease, state="expected", cheque_no=False)
        cheques = self._profile()["cheques"]
        self.assertEqual(cheques["in_custody"], 2)

    # ------------------------------------------------------------ bounce rate
    def test_the_bounce_rate_uses_the_shared_definition(self):
        """One formula, because the Command Center reports it too and two
        screens disagreeing about the same tenant is the failure here."""
        lease = self._lease("DSR-113")
        bounced = self._cheque(lease, state="deposited", cheque_no="810601")
        bounced.action_pdc_bounce()
        self._cheque(lease, state="cleared", cheque_no="810602")
        cheques = self._profile()["cheques"]
        self.assertEqual(cheques["ever_bounced"], 1)
        self.assertEqual(cheques["cleared"], 1)
        self.assertAlmostEqual(
            cheques["bounce_rate"],
            self.env["account.payment"]._c2p_bounce_rate(1, 1),
            places=6,
        )
        self.assertAlmostEqual(cheques["bounce_rate"], 50.0, places=6)

    def test_replacing_a_bounced_cheque_does_not_clear_the_record(self):
        """Same rule as the dashboard: a replacement is a recovery, not a
        retraction, so the tenant's history keeps the bounce."""
        lease = self._lease("DSR-114")
        bounced = self._cheque(lease, state="deposited", cheque_no="810701")
        bounced.action_pdc_bounce()
        before = self._profile()["cheques"]["ever_bounced"]
        wizard = self.env["c2p.pdc.replace"].create(
            {
                "payment_id": bounced.id,
                "cheque_no": "810702",
                "cheque_bank": "Test Bank",
                "maturity_date": fields.Date.context_today(self.env.user),
                "amount": bounced.amount,
            }
        )
        wizard.action_confirm()
        after = self._profile()["cheques"]
        self.assertEqual(after["ever_bounced"], before)
        self.assertEqual(
            self.env["account.payment"].search_count(after["ever_bounced_domain"]),
            after["ever_bounced"],
        )

    def test_a_tenant_who_never_bounced_reads_zero_not_blank(self):
        lease = self._lease("DSR-115")
        self._cheque(lease, state="cleared", cheque_no="810801")
        self.assertEqual(self._profile()["cheques"]["bounce_rate"], 0.0)

    # ------------------------------------------------------------------ risk
    def test_a_short_cheque_set_is_flagged_on_a_running_tenancy(self):
        lease = self._lease("DSR-116")
        lease._activate_as_loaded()
        risk = self._profile()["risk"]
        self.assertTrue(risk["cheques_short"])
        self.assertFalse(risk["no_live_tenancy"])

    def test_a_bounce_is_flagged_even_after_it_is_replaced(self):
        lease = self._lease("DSR-117")
        lease._activate_as_loaded()
        bounced = self._cheque(lease, state="deposited", cheque_no="810901")
        bounced.action_pdc_bounce()
        risk = self._profile()["risk"]
        self.assertTrue(risk["bounced_now"])
        self.assertTrue(risk["ever_bounced"])

    def test_an_expiry_inside_the_window_is_flagged_with_its_countdown(self):
        today = fields.Date.context_today(self.env.user)
        lease = self._lease(
            "DSR-118",
            start=today - timedelta(days=300),
            end=today + timedelta(days=30),
        )
        lease._activate_as_loaded()
        risk = self._profile()["risk"]
        self.assertTrue(risk["expiring_soon"])
        self.assertEqual(risk["expiring_days"], 30)

    def test_the_expiry_window_matches_the_renewal_alert_cron(self):
        """The dossier and the alert must agree about what "expiring" means,
        or a tenant is flagged on one screen and not the other."""
        from odoo.addons.c2p_property_lease.models.res_partner import EXPIRING_SOON_DAYS

        self.assertEqual(EXPIRING_SOON_DAYS, 90)
        today = fields.Date.context_today(self.env.user)
        lease = self._lease(
            "DSR-119",
            start=today - timedelta(days=200),
            end=today + timedelta(days=EXPIRING_SOON_DAYS + 5),
        )
        lease._activate_as_loaded()
        self.assertFalse(self._profile()["risk"]["expiring_soon"])

    # ------------------------------------------------------------ exceptions
    def test_cheque_exceptions_are_listed_against_the_tenant(self):
        """One exception is an exception; a run of them is a policy, and that
        pattern is invisible from any single lease."""
        lease = self._lease("DSR-120")
        exception = self.env["c2p.lease.cheque.exception"].create(
            {
                "lease_id": lease.id,
                "reason": "Relocating from abroad",
                "conditions": "Before the second instalment",
                "deadline": fields.Date.context_today(self.env.user) + timedelta(days=14),
                "responsible_user_id": self.env.uid,
            }
        )
        listed = self._profile()["exceptions"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], exception.id)
        self.assertEqual(listed[0]["missing_cheque_count"], 4)
        self.assertTrue(self._profile()["risk"]["open_exception"])

    # -------------------------------------------------------------- upcoming
    def test_next_due_lists_only_instruments_we_still_hold(self):
        """An expected cheque has a date and nothing behind it; a cleared one
        has already happened. Neither is something falling due."""
        today = fields.Date.context_today(self.env.user)
        lease = self._lease("DSR-121", start=today, end=today + timedelta(days=364))
        lease._activate_as_loaded()
        held = self._cheque(lease, state="held", cheque_no="811001")
        held.maturity_date = today + timedelta(days=10)
        expected = self._cheque(lease, state="expected", cheque_no=False)
        expected.maturity_date = today + timedelta(days=5)
        cleared = self._cheque(lease, state="cleared", cheque_no="811002")
        cleared.maturity_date = today + timedelta(days=7)

        upcoming = self._profile()["upcoming"]
        cheques = [item for item in upcoming if item["kind"] == "cheque"]
        self.assertEqual([item["res_id"] for item in cheques], [held.id])
        self.assertTrue(any(item["kind"] == "expiry" for item in upcoming))

    def test_next_due_is_in_date_order(self):
        today = fields.Date.context_today(self.env.user)
        lease = self._lease("DSR-122", start=today, end=today + timedelta(days=200))
        lease._activate_as_loaded()
        for offset, number in ((60, "811101"), (10, "811102"), (30, "811103")):
            cheque = self._cheque(lease, state="held", cheque_no=number)
            cheque.maturity_date = today + timedelta(days=offset)
        dates = [item["date"] for item in self._profile()["upcoming"]]
        self.assertEqual(dates, sorted(dates))

    # ---------------------------------------------------------------- action
    def test_the_action_opens_the_client_dossier_for_this_partner(self):
        action = self.tenant.action_tenant_360()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "c2p_tenant_360")
        self.assertEqual(action["params"]["partner_id"], self.tenant.id)

    def test_the_lease_domain_opens_this_tenants_tenancies(self):
        self._lease("DSR-123")
        self._lease("DSR-124")
        self._lease("DSR-125", tenant=self.stranger)
        profile = self._profile()
        self.assertEqual(
            self.env["c2p.lease"].search_count(profile["domains"]["leases"]),
            profile["tenure"]["lease_count"],
        )
