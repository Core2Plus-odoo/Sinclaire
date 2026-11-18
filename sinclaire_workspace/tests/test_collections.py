"""The Collections register: which bucket an instrument lands in, and why.

A cheque can be simultaneously late, unbanked and somebody else's money. The
bucket decides what the collections team does about it this morning, so the
order is the design decision and these tests pin it.

The separation that must not blur is BRD §6.1: owner funds are held and
banked for the landlord and are never company cash. That shows on every row
of the register, and is tested here rather than left to the view.
"""

from ast import literal_eval
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class CollectionsCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Collections Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Collections Tenant"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Collections Properties"})
        cls.today = fields.Date.context_today(cls.env.user)

    def _journal(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            self.skipTest("no bank journal with an inbound payment method")
        return journal

    def _building(self, code, model="head_lease"):
        return self.env["c2p.building"].create(
            {
                "name": f"{code} Tower",
                "code": code,
                "owner_id": self.landlord.id,
                "operating_model": model,
                "analytic_account_id": self.env["account.analytic.account"]
                .create({"name": f"{code} Tower", "plan_id": self.plan.id})
                .id,
            }
        )

    def _lease(self, building, name):
        unit = self.env["c2p.unit"].create(
            {
                "name": name,
                "building_id": building.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": 120000.0,
                "dewa_no": f"31{abs(hash(name)) % 100000:05d}",
            }
        )
        unit.sudo().action_release()
        return self.env["c2p.lease"].create(
            {
                "unit_id": unit.id,
                "tenant_id": self.tenant.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": 120000.0,
                "cheque_count": "4",
            }
        )

    def _cheque(self, lease, no, days=None, **kw):
        journal = self._journal()
        vals = {
            "partner_id": self.tenant.id,
            "partner_type": "customer",
            "payment_type": "inbound",
            "amount": 30000.0,
            "journal_id": journal.id,
            "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
            "lease_id": lease.id,
            "cheque_no": no,
        }
        if days is not None:
            vals["maturity_date"] = self.today + timedelta(days=days)
        vals.update(kw)
        return self.env["account.payment"].create(vals)


class TestBuckets(CollectionsCase):
    def test_a_matured_uncleared_cheque_is_past_due(self):
        lease = self._lease(self._building("CBO"), "CBO-101")
        cheque = self._cheque(lease, "100001", days=-10)
        self.assertEqual(cheque.collection_bucket, "overdue")
        self.assertEqual(cheque.collection_tone, "critical")
        self.assertEqual(cheque.days_to_maturity, -10)
        self.assertIn("10 days ago", cheque.collection_alert)

    def test_a_cheque_bankable_within_the_week_is_due_soon(self):
        lease = self._lease(self._building("CBD"), "CBD-101")
        cheque = self._cheque(lease, "100002", days=3)
        self.assertEqual(cheque.collection_bucket, "due_soon")
        self.assertEqual(cheque.collection_tone, "warn")

    def test_a_cheque_further_out_is_quiet(self):
        """A register where every row shouts is one nobody reads."""
        lease = self._lease(self._building("CBL"), "CBL-101")
        cheque = self._cheque(lease, "100003", days=60)
        self.assertEqual(cheque.collection_bucket, "later")
        self.assertEqual(cheque.collection_tone, "ok")
        self.assertFalse(cheque.collection_alert)

    def test_the_boundary_day_is_still_due_this_week(self):
        lease = self._lease(self._building("CBB"), "CBB-101")
        self.assertEqual(self._cheque(lease, "100004", days=7).collection_bucket, "due_soon")
        self.assertEqual(self._cheque(lease, "100005", days=8).collection_bucket, "later")

    def test_today_is_due_not_overdue(self):
        """A cheque bankable today has not failed; it is this morning's work."""
        lease = self._lease(self._building("CBT"), "CBT-101")
        self.assertEqual(self._cheque(lease, "100006", days=0).collection_bucket, "due_soon")

    def test_a_bounced_cheque_outranks_a_late_one(self):
        """Money that failed beats money that is merely late."""
        lease = self._lease(self._building("CBX"), "CBX-101")
        cheque = self._cheque(lease, "100007", days=-30)
        cheque.action_pdc_bounce()
        self.assertEqual(cheque.collection_bucket, "bounced")
        self.assertEqual(cheque.collection_tone, "critical")

    def test_an_expected_cheque_is_flagged_as_never_handed_over(self):
        """BR-114. Distinct from a cheque nobody has entered: this one the
        lease schedule says should exist."""
        lease = self._lease(self._building("CBM"), "CBM-101")
        cheque = self._cheque(lease, "100008", days=5, pdc_state="expected")
        self.assertEqual(cheque.collection_bucket, "missing")
        self.assertIn("not handed over", cheque.collection_alert)

    def test_a_cleared_cheque_settles_and_says_nothing(self):
        lease = self._lease(self._building("CBC"), "CBC-101")
        cheque = self._cheque(lease, "100009", days=-5)
        cheque.action_pdc_clear()
        self.assertEqual(cheque.collection_bucket, "settled")
        self.assertFalse(cheque.collection_alert)

    def test_a_replaced_cheque_closes_quietly(self):
        """The replacement carries the open obligation and appears in the
        register in its own right. Showing both would double the work."""
        lease = self._lease(self._building("CBR"), "CBR-101")
        original = self._cheque(lease, "100010", days=-20)
        original.action_pdc_bounce()
        replacement = self._cheque(lease, "100011", days=5)
        original.action_link_replacement(replacement)
        self.assertEqual(original.collection_bucket, "closed")
        self.assertEqual(original.collection_tone, "ok")
        self.assertEqual(replacement.collection_bucket, "due_soon")

    def test_a_cancelled_cheque_closes_quietly(self):
        lease = self._lease(self._building("CBN"), "CBN-101")
        cheque = self._cheque(lease, "100012", days=20)
        cheque.action_pdc_cancel(reason="Lease terminated early")
        self.assertEqual(cheque.collection_bucket, "closed")

    def test_a_cheque_with_no_maturity_date_is_flagged(self):
        """It cannot be banked and it cannot be chased on a date. That is a
        data problem, and silence would hide it."""
        lease = self._lease(self._building("CBZ"), "CBZ-101")
        cheque = self._cheque(lease, "100013")
        self.assertEqual(cheque.collection_bucket, "later")
        self.assertEqual(cheque.collection_tone, "warn")
        self.assertIn("No maturity date", cheque.collection_alert)


class TestWhoseMoneyOnTheRegister(CollectionsCase):
    """BRD §6.1, visible on every row."""

    def test_a_head_lease_tenant_cheque_is_company_funds(self):
        lease = self._lease(self._building("CWH", "head_lease"), "CWH-101")
        cheque = self._cheque(lease, "200001", days=5)
        self.assertFalse(cheque.is_owner_funds)
        self.assertEqual(cheque.payee_partner_id, self.env.company.partner_id)

    def test_an_owner_managed_tenant_cheque_is_owner_funds(self):
        lease = self._lease(self._building("CWO", "owner_management"), "CWO-101")
        cheque = self._cheque(lease, "200002", days=5)
        self.assertTrue(cheque.is_owner_funds)
        self.assertEqual(cheque.payee_partner_id, self.landlord)

    def test_owner_funds_are_still_chased_on_the_same_clock(self):
        """Whose money it is changes where it goes, not whether it is late.
        An owner-funds cheque past due is still the team's problem."""
        lease = self._lease(self._building("CWL", "owner_management"), "CWL-101")
        cheque = self._cheque(lease, "200003", days=-12)
        self.assertTrue(cheque.is_owner_funds)
        self.assertEqual(cheque.collection_bucket, "overdue")


class TestWhatTheRowOffers(CollectionsCase):
    """What a clerk can press, and on what."""

    def test_an_expected_cheque_cannot_be_bounced(self):
        """It was never handed over. Offering to bounce it invites recording
        a failure for an instrument that does not exist, which would then
        read as a tenant who paid badly rather than one who has not paid."""
        lease = self._lease(self._building("CRE"), "CRE-101")
        cheque = self._cheque(lease, "350001", days=5, pdc_state="expected")
        arch = self.env.ref("sinclaire_workspace.view_collections_list").arch
        self.assertIn("pdc_state not in ('held','deposited')", arch)
        self.assertEqual(cheque.collection_bucket, "missing")

    def test_whose_money_reads_as_a_word(self):
        """is_owner_funds is a boolean and Odoo sizes a boolean column to the
        checkbox, which cut its own header to "O...". This is the column that
        says whose money is about to be banked."""
        head = self._lease(self._building("CRC", "head_lease"), "CRC-101")
        owned = self._lease(self._building("CRO", "owner_management"), "CRO-101")
        self.assertEqual(self._cheque(head, "350002", days=3).funds_label, "Company")
        self.assertEqual(self._cheque(owned, "350003", days=3).funds_label, "Owner")


class TestTheFilters(CollectionsCase):
    """The search method is what makes the buckets usable, and it is the part
    most likely to break quietly."""

    def test_searching_a_bucket_finds_exactly_that_bucket(self):
        lease = self._lease(self._building("CFB"), "CFB-101")
        overdue = self._cheque(lease, "300001", days=-4)
        soon = self._cheque(lease, "300002", days=2)
        later = self._cheque(lease, "300003", days=90)
        found = self.env["account.payment"].search([("collection_bucket", "=", "overdue")])
        self.assertIn(overdue, found)
        self.assertNotIn(soon, found)
        self.assertNotIn(later, found)

    def test_searching_several_buckets_at_once(self):
        lease = self._lease(self._building("CFI"), "CFI-101")
        overdue = self._cheque(lease, "310001", days=-4)
        soon = self._cheque(lease, "310002", days=2)
        later = self._cheque(lease, "310003", days=90)
        found = self.env["account.payment"].search([("collection_bucket", "in", ("overdue", "due_soon"))])
        self.assertIn(overdue, found)
        self.assertIn(soon, found)
        self.assertNotIn(later, found)

    def test_the_still_open_filter_excludes_settled_and_closed(self):
        """This is the default the screen opens on, so it has to be right."""
        lease = self._lease(self._building("CFO"), "CFO-101")
        open_one = self._cheque(lease, "320001", days=3)
        cleared = self._cheque(lease, "320002", days=-3)
        cleared.action_pdc_clear()
        found = self.env["account.payment"].search([("collection_bucket", "not in", ("settled", "closed"))])
        self.assertIn(open_one, found)
        self.assertNotIn(cleared, found)

    def test_an_ordered_set_value_is_accepted(self):
        """What Odoo actually passes.

        The first version of this search checked for a list or tuple and
        wrapped anything else in a list. Odoo 19 hands an OrderedSet to an
        `in` search, so the filter raised "unhashable type: OrderedSet" the
        moment anyone clicked it. Every unit test passed, because they all
        called search() with a tuple written by hand - the one shape the real
        caller never uses.
        """
        from odoo.tools import OrderedSet

        lease = self._lease(self._building("COS"), "COS-101")
        overdue = self._cheque(lease, "330001", days=-5)
        found = self.env["account.payment"].search([("collection_bucket", "in", OrderedSet(["overdue"]))])
        self.assertIn(overdue, found)

    def test_a_bare_string_still_means_one_value(self):
        """A string is the one iterable that is a single value, not a set of
        characters to match."""
        lease = self._lease(self._building("CSS"), "CSS-101")
        overdue = self._cheque(lease, "340001", days=-5)
        self.assertIn(
            overdue,
            self.env["account.payment"].search([("collection_bucket", "=", "overdue")]),
        )

    def test_an_unsupported_operator_is_refused_rather_than_ignored(self):
        """A silently wrong filter on a money register is worse than an error."""
        with self.assertRaises(ValueError):
            self.env["account.payment"].search([("collection_bucket", "like", "overdue")])


class TestTheViewsLoad(CollectionsCase):
    def test_the_collections_list_renders(self):
        view = self.env.ref("sinclaire_workspace.view_collections_list")
        self.env["account.payment"].get_views([(view.id, "list")])

    def test_the_collections_search_renders(self):
        view = self.env.ref("sinclaire_workspace.view_collections_search")
        self.env["account.payment"].get_views([(view.id, "search")])

    def _domain_of(self, xmlid):
        return literal_eval(self.env.ref(xmlid).domain)

    def test_collections_excludes_landlord_cheques(self):
        """Money out under a head lease is not collections. They share the
        model and nothing else."""
        domain = self._domain_of("sinclaire_workspace.action_collections")
        self.assertIn(("head_lease_id", "=", False), domain)
        self.assertIn(("is_pdc", "=", True), domain)

    def test_the_landlord_cheque_screen_shows_only_those(self):
        self.assertIn(
            ("head_lease_id", "!=", False),
            self._domain_of("sinclaire_workspace.action_landlord_cheques"),
        )

    def test_a_manager_sees_the_collections_menus(self):
        """Gated on the manager group because these screens read and write
        account.payment, which needs billing access."""
        manager = self.env["res.users"].create(
            {
                "name": "Collections Manager",
                "login": "collections_manager_menu",
                "group_ids": [(4, self.env.ref("c2p_property_lease.group_property_manager").id)],
            }
        )
        visible = self.env["ir.ui.menu"].with_user(manager)._visible_menu_ids()
        self.assertIn(self.env.ref("sinclaire_workspace.menu_collections").id, visible)
        self.assertIn(self.env.ref("sinclaire_workspace.menu_landlord_cheques").id, visible)

    def test_a_plain_leasing_user_does_not_see_them(self):
        """A leasing agent does not bank cheques. This is the tighter default
        on purpose: money handling should not widen by accident."""
        agent = self.env["res.users"].create(
            {
                "name": "Leasing Agent",
                "login": "collections_agent_menu",
                "group_ids": [(4, self.env.ref("c2p_property_lease.group_property_user").id)],
            }
        )
        visible = self.env["ir.ui.menu"].with_user(agent)._visible_menu_ids()
        self.assertNotIn(self.env.ref("sinclaire_workspace.menu_collections").id, visible)
        self.assertIn(self.env.ref("sinclaire_workspace.menu_portfolio").id, visible)

    def test_the_manager_group_can_actually_read_the_register(self):
        """The gate is only half of it. Without billing access the menu is
        visible and the screen behind it raises - which is worse than a
        hidden menu, because it looks like a bug rather than a permission.
        """
        manager = self.env["res.users"].create(
            {
                "name": "Register Reader",
                "login": "collections_reader",
                "group_ids": [(4, self.env.ref("c2p_property_lease.group_property_manager").id)],
            }
        )
        self.assertTrue(manager.has_group("account.group_account_invoice"))
        self.env["account.payment"].with_user(manager).check_access("read")
