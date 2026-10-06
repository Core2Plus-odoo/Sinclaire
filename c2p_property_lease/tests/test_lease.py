from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestLease(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.landlord = cls.env["res.partner"].create({"name": "Test Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Test Tenant"})
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "Test Tower",
                "code": "TST",
                "owner_id": cls.landlord.id,
            }
        )
        cls.unit = cls.env["c2p.unit"].create(
            {
                "name": "TST-101",
                "building_id": cls.building.id,
                "unit_type": "1br",
            }
        )

    def _lease(self, **kw):
        vals = {
            "tenant_id": self.tenant.id,
            "unit_id": self.unit.id,
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "annual_rent": 100000.0,
            "cheque_count": "4",
        }
        vals.update(kw)
        return self.env["c2p.lease"].create(vals)

    def _activate(self, lease):
        """Activate a lease that has no cheques.

        BR-075 refuses that outright, so these tests - which are about other
        things - grant the approved exception BRD §5.1 requires and then use
        the ordinary action, so the state guards under test still run. The
        approval's own rules are tested in test_cheque_exception.py, which is
        why the state is set directly here rather than through action_approve.
        """
        self.env["c2p.lease.cheque.exception"].create(
            {
                "lease_id": lease.id,
                "reason": "Test fixture",
                "conditions": "Cheques to follow",
                "deadline": fields.Date.context_today(self.env.user) + timedelta(days=7),
                "responsible_user_id": self.env.uid,
                # Requested by somebody else: the approval rules now hold on
                # every write path, self-approval included, so a fixture that
                # requested and approved as the same user would be refused -
                # which is the point.
                "requested_by_id": self.env.ref("base.user_admin").id,
            }
        ).write({"state": "approved", "approved_by_id": self.env.uid})
        lease.action_activate()
        return lease

    def test_unit_number_is_unique_per_building(self):
        """Regression: _sql_constraints is ignored on 19.0, so this must be a
        models.Constraint or duplicates reach the database silently."""
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.env["c2p.unit"].create(
                    {
                        "name": "TST-101",
                        "building_id": self.building.id,
                    }
                )
                self.env.flush_all()

    def test_building_code_is_unique_per_company(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.env["c2p.building"].create(
                    {
                        "name": "Another Tower",
                        "code": "TST",
                        "owner_id": self.landlord.id,
                    }
                )
                self.env.flush_all()

    def test_instalment_is_annual_rent_over_cheques(self):
        lease = self._lease()
        self.assertEqual(lease.instalment_amount, 25000.0)

    def test_lease_must_end_after_it_starts(self):
        with self.assertRaises(ValidationError):
            self._lease(date_start="2026-12-31", date_end="2026-01-01")

    def test_activating_marks_the_unit_occupied(self):
        lease = self._activate(self._lease())
        self.assertEqual(lease.state, "active")
        self.assertEqual(self.unit.state, "occupied")
        self.assertEqual(self.unit.current_lease_id, lease)

    def test_second_lease_cannot_occupy_the_same_unit(self):
        self._activate(self._lease())
        other = self._lease(tenant_id=self.landlord.id)
        # The message matters: with BR-075 in place an activation can be
        # refused for a missing cheque instead, and a test that only asserted
        # "it raised" would pass on the wrong refusal.
        with self.assertRaises(UserError) as caught:
            self._activate(other)
        self.assertIn("already taken", str(caught.exception))

    def test_second_lease_blocked_while_the_first_is_under_notice(self):
        """BR-001. A unit under notice is still occupied - the sitting tenant
        has not left. Before the ten-state model the guard only looked for
        "occupied", so notice was a hole in it."""
        first = self._activate(self._lease())
        first.action_give_notice()
        self.assertEqual(self.unit.state, "notice")
        other = self._lease(tenant_id=self.landlord.id)
        with self.assertRaises(UserError) as caught:
            self._activate(other)
        self.assertIn("already taken", str(caught.exception))

    def test_second_lease_blocked_while_the_unit_is_contracted(self):
        """Contracted means signed but not yet moved in. The unit is spoken
        for, so a second activation must still be refused."""
        self._activate(self._lease())
        self.unit.state = "contracted"
        other = self._lease(tenant_id=self.landlord.id)
        with self.assertRaises(UserError) as caught:
            self._activate(other)
        self.assertIn("already taken", str(caught.exception))

    def test_expiring_releases_the_unit(self):
        lease = self._activate(self._lease(date_start="2020-01-01", date_end="2020-12-31"))
        self.env["c2p.lease"]._cron_expire_leases()
        self.assertEqual(lease.state, "expired")
        self.assertEqual(self.unit.state, "vacant")
        self.assertFalse(self.unit.current_lease_id)

    def test_rent_product_resolves_by_xml_id(self):
        """Regression: products were resolved by translatable name."""
        lease = self._lease()
        self.assertEqual(
            lease._rent_product(),
            self.env.ref("c2p_property_lease.product_residential_rent").product_variant_id,
        )

    def test_commercial_unit_selects_the_commercial_product(self):
        self.unit.unit_type = "office"
        lease = self._lease()
        self.assertTrue(lease.is_commercial)
        self.assertEqual(
            lease._rent_product(),
            self.env.ref("c2p_property_lease.product_commercial_rent").product_variant_id,
        )

    def test_is_pdc_recomputes_when_cheque_no_is_written_later(self):
        """Regression: is_pdc was a stored compute with no @api.depends, so the
        backfill script's write() left every cheque flagged as not-a-PDC."""
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.company.id)], limit=1
        )
        if not journal:
            self.skipTest("no bank journal in this company")
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.tenant.id,
                "amount": 25000.0,
                "journal_id": journal.id,
            }
        )
        self.assertFalse(payment.is_pdc)
        payment.write({"cheque_no": "123456"})
        self.assertTrue(payment.is_pdc)

    def test_subscription_action_refuses_without_the_enterprise_app(self):
        """Soft dependency: on Community the action must refuse clearly rather
        than raise KeyError on a missing model."""
        lease = self._lease()
        if lease._subscriptions_installed():
            self.skipTest("Subscriptions is installed on this database")
        with self.assertRaises(UserError):
            lease.action_create_subscription()

    def test_subscriptions_available_matches_the_registry(self):
        lease = self._lease()
        self.assertEqual(
            lease.subscriptions_available,
            "sale.subscription.plan" in self.env,
        )

    def test_terminating_is_safe_without_subscriptions(self):
        lease = self._activate(self._lease())
        wizard = self.env["c2p.lease.terminate"].create(
            {
                "lease_id": lease.id,
                "date_termination": "2026-06-30",
            }
        )
        wizard.action_terminate()
        self.assertEqual(lease.state, "terminated")

    def test_plan_lookup_prefers_the_rent_plan_over_the_generic_one(self):
        """The live database holds both "Monthly" and "Monthly Rent (12 cheques)"
        on the same period; a bare limit=1 search would take the generic one."""
        lease = self._lease(cheque_count="12")
        if not lease._subscriptions_installed():
            self.skipTest("Subscriptions is not installed on this database")
        plan = lease._find_subscription_plan()
        self.assertTrue(plan, "no plan matched a 12-cheque schedule")
        self.assertIn("rent", plan.name.lower())

    def test_annual_schedule_falls_back_to_a_yearly_plan(self):
        lease = self._lease(cheque_count="1")
        if not lease._subscriptions_installed():
            self.skipTest("Subscriptions is not installed on this database")
        plan = lease._find_subscription_plan()
        self.assertTrue(plan)
        self.assertEqual(plan.billing_period_unit, "year")
        self.assertEqual(plan.billing_period_value, 1)

    def test_creating_a_subscription_confirms_it(self):
        lease = self._lease(cheque_count="4")
        if not lease._subscriptions_installed():
            self.skipTest("Subscriptions is not installed on this database")
        self._activate(lease)
        lease.action_create_subscription()
        order = lease.subscription_id
        self.assertTrue(order)
        self.assertEqual(order.plan_id, lease._find_subscription_plan())
        self.assertEqual(order.subscription_state, "3_progress")
        self.assertEqual(order.c2p_lease_id, lease)
        self.assertEqual(order.order_line.price_unit, lease.instalment_amount)


@tagged("post_install", "-at_install")
class TestChequeSchedules(TransactionCase):
    """Every offered cheque count must have a schedule behind it.

    `_find_subscription_plan` indexes CHEQUE_PLAN by the selected cheque
    count, so a value offered in the dropdown but missing from the map raises
    KeyError when the lease is confirmed - which is how the 3-cheque option
    was unusable on the tenant lease while the head lease accepted it.
    """

    def test_tenant_lease_offers_the_six_uae_schedules(self):
        selection = {int(v) for v, _ in self.env["c2p.lease"]._fields["cheque_count"].selection}
        self.assertEqual(selection, {1, 2, 3, 4, 6, 12})

    def test_head_lease_offers_the_six_uae_schedules(self):
        selection = {int(v) for v, _ in self.env["c2p.head.lease"]._fields["cheque_count"].selection}
        self.assertEqual(selection, {1, 2, 3, 4, 6, 12})

    def test_tenant_lease_schedule_map_covers_every_offered_count(self):
        from odoo.addons.c2p_property_lease.models.lease import CHEQUE_PLAN

        selection = {int(v) for v, _ in self.env["c2p.lease"]._fields["cheque_count"].selection}
        self.assertEqual(selection, set(CHEQUE_PLAN), "dropdown and CHEQUE_PLAN have drifted apart")

    def test_head_lease_schedule_map_covers_every_offered_count(self):
        from odoo.addons.c2p_property_lease.models.head_lease import CHEQUE_PLAN

        selection = {int(v) for v, _ in self.env["c2p.head.lease"]._fields["cheque_count"].selection}
        self.assertEqual(selection, set(CHEQUE_PLAN), "dropdown and CHEQUE_PLAN have drifted apart")

    def test_every_schedule_divides_the_year(self):
        from odoo.addons.c2p_property_lease.models.lease import CHEQUE_PLAN

        for cheques, months in CHEQUE_PLAN.items():
            self.assertEqual(cheques * months, 12, f"{cheques} cheques x {months} months != 12")


@tagged("post_install", "-at_install")
class TestUnitStates(TransactionCase):
    """BRD §3.2's ten-state unit model, and the guarantee that adding it did
    not move any number the dashboard already showed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "States Landlord"})
        cls.building = cls.env["c2p.building"].create(
            {"name": "States Tower", "code": "STT", "owner_id": cls.landlord.id}
        )

    def _unit(self, name, state=None, market_rent=100000.0):
        unit = self.env["c2p.unit"].create({"name": name, "building_id": self.building.id, "market_rent": market_rent})
        if state:
            unit.state = state
        return unit

    def test_all_ten_brd_states_exist(self):
        from odoo.addons.c2p_property_lease.models.unit import UNIT_STATES

        self.assertEqual(
            [s for s, _ in UNIT_STATES],
            [
                "draft",
                "available",
                "under_marketing",
                "viewing_hold",
                "reserved",
                "contracted",
                "occupied",
                "notice",
                "vacant",
                "blocked",
            ],
        )

    def test_earning_and_empty_states_do_not_overlap(self):
        from odoo.addons.c2p_property_lease.models.unit import EARNING_STATES
        from odoo.addons.c2p_property_lease.models.unit import EMPTY_STATES
        from odoo.addons.c2p_property_lease.models.unit import UNIT_STATES

        self.assertFalse(set(EARNING_STATES) & set(EMPTY_STATES))
        known = {s for s, _ in UNIT_STATES}
        self.assertTrue(set(EARNING_STATES) <= known)
        self.assertTrue(set(EMPTY_STATES) <= known)
        # Draft and Blocked belong to neither, deliberately.
        self.assertEqual(known - set(EARNING_STATES) - set(EMPTY_STATES), {"draft", "blocked"})

    def test_vacancy_loss_counts_every_empty_state(self):
        """The reason EMPTY_STATES exists: a unit being marketed, held or
        reserved earns nothing, exactly as it did when all four were one
        "vacant" state."""
        from odoo.addons.c2p_property_lease.models.unit import EMPTY_STATES

        for i, state in enumerate(EMPTY_STATES):
            self._unit(f"E{i}", state, market_rent=50000.0)
        self.building.invalidate_recordset()
        self.assertEqual(self.building.vacant_count, len(EMPTY_STATES))

    def test_blocked_and_draft_are_not_vacancy_loss(self):
        self._unit("D1", "draft")
        self._unit("B1", "blocked")
        self.building.invalidate_recordset()
        self.assertEqual(self.building.vacant_count, 0)

    def test_a_unit_cannot_skip_from_draft_to_reserved(self):
        unit = self._unit("S1", "draft")
        with self.assertRaises(UserError):
            unit.action_reserve()

    def test_release_then_market_then_hold_then_reserve(self):
        unit = self._unit("S2", "draft")
        unit.action_release()
        self.assertEqual(unit.state, "available")
        unit.action_market()
        self.assertEqual(unit.state, "under_marketing")
        unit.action_hold()
        self.assertEqual(unit.state, "viewing_hold")
        unit.action_reserve()
        self.assertEqual(unit.state, "reserved")

    def test_a_handed_back_unit_is_not_available_until_turnaround(self):
        """BRD §3.2 separates Vacant from Available. A unit straight out of a
        tenancy is not re-lettable until the turnaround is done."""
        unit = self._unit("S3", "vacant")
        with self.assertRaises(UserError):
            unit.action_market()
        unit.action_turnaround_complete()
        self.assertEqual(unit.state, "available")

    def test_unblocking_returns_the_unit_to_the_state_it_left(self):
        """Not to Available. An occupied unit blocked for maintenance is still
        occupied when the work finishes."""
        unit = self._unit("S4", "occupied")
        unit.action_block()
        self.assertEqual(unit.state, "blocked")
        unit.action_unblock()
        self.assertEqual(unit.state, "occupied")

    def test_unblocking_an_available_unit_stays_available(self):
        unit = self._unit("S5", "available")
        unit.action_block()
        unit.action_unblock()
        self.assertEqual(unit.state, "available")

    def test_a_blocked_occupied_unit_cannot_be_double_let_after_unblocking(self):
        """The defect this guards: if unblocking returned the unit to
        Available, the activation guard - which reads unit state - would let a
        second tenancy start over the sitting tenant. BR-001."""
        unit = self._unit("S6", "occupied")
        unit.action_block()
        unit.action_unblock()
        self.assertIn(unit.state, ("contracted", "occupied", "notice"))


@tagged("post_install", "-at_install")
class TestLeaseStates(TransactionCase):
    """BRD §3.2's twelve-state lease model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "LS Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "LS Tenant"})
        cls.building = cls.env["c2p.building"].create({"name": "LS Tower", "code": "LST", "owner_id": cls.landlord.id})

    def _lease(self, unit_name):
        unit = self.env["c2p.unit"].create({"name": unit_name, "building_id": self.building.id})
        return self.env["c2p.lease"].create(
            {
                "unit_id": unit.id,
                "tenant_id": self.tenant.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": 100000.0,
            }
        )

    def _activate(self, lease):
        """See TestLease._activate: BR-075 refuses a cheque-less activation, so
        the exception BRD §5.1 requires is granted first and the ordinary action
        is used, keeping the state guards under test in play."""
        self.env["c2p.lease.cheque.exception"].create(
            {
                "lease_id": lease.id,
                "reason": "Test fixture",
                "conditions": "Cheques to follow",
                "deadline": fields.Date.context_today(self.env.user) + timedelta(days=7),
                "responsible_user_id": self.env.uid,
                # Requested by somebody else: the approval rules now hold on
                # every write path, self-approval included, so a fixture that
                # requested and approved as the same user would be refused -
                # which is the point.
                "requested_by_id": self.env.ref("base.user_admin").id,
            }
        ).write({"state": "approved", "approved_by_id": self.env.uid})
        lease.action_activate()
        return lease

    def test_all_twelve_brd_states_exist(self):
        from odoo.addons.c2p_property_lease.models.lease import LEASE_STATES

        self.assertEqual(
            [s for s, _ in LEASE_STATES],
            [
                "draft",
                "pending_approval",
                "offered",
                "awaiting_signature",
                "signed",
                "registration_pending",
                "active",
                "notice",
                "renewed",
                "expired",
                "terminated",
                "cancelled",
            ],
        )

    def test_the_three_groups_partition_every_state(self):
        """Every state belongs to exactly one group. A state added to the
        selection but to no group would silently vanish from the crons and the
        dashboard, which both search by group."""
        from odoo.addons.c2p_property_lease.models.lease import CLOSED_STATES
        from odoo.addons.c2p_property_lease.models.lease import LEASE_STATES
        from odoo.addons.c2p_property_lease.models.lease import LIVE_STATES
        from odoo.addons.c2p_property_lease.models.lease import PRE_ACTIVE_STATES

        groups = [set(LIVE_STATES), set(PRE_ACTIVE_STATES), set(CLOSED_STATES)]
        union = set().union(*groups)
        self.assertEqual(union, {s for s, _ in LEASE_STATES})
        for i, a in enumerate(groups):
            for b in groups[i + 1 :]:
                self.assertFalse(a & b, f"{a & b} is in two groups")

    def test_the_full_pre_active_path(self):
        lease = self._lease("P1")
        lease.action_submit_for_approval()
        self.assertEqual(lease.state, "pending_approval")
        lease.action_approve()
        self.assertEqual(lease.state, "offered")
        lease.action_send_for_signature()
        self.assertEqual(lease.state, "awaiting_signature")
        lease.action_mark_signed()
        self.assertEqual(lease.state, "signed")
        lease.action_submit_registration()
        self.assertEqual(lease.state, "registration_pending")
        self._activate(lease)
        self.assertEqual(lease.state, "active")

    def test_a_draft_lease_with_its_cheques_in_can_be_activated_directly(self):
        """The approval and signature gates are BR-036 and BR-072 and are not
        built - both wait on OD-06 - so the short path through the state model
        stays open. BR-075 is built, so the one thing the short path cannot skip
        is the cheques: this lease gets there on an approved exception."""
        lease = self._lease("P2")
        self._activate(lease)
        self.assertEqual(lease.state, "active")

    def test_the_short_path_still_cannot_skip_the_cheques(self):
        """The other half of the test above, and the one that would catch the
        gate being lost: no exception, no activation, however short the path."""
        lease = self._lease("P2b")
        with self.assertRaises(UserError) as caught:
            lease.action_activate()
        self.assertIn("cheque", str(caught.exception).lower())
        self.assertEqual(lease.state, "draft")

    def test_a_signed_lease_cannot_go_back(self):
        """BRD §5.1.2: the signed document is immutable. Correction is an
        amendment version, not a reversal."""
        lease = self._lease("P3")
        lease.action_approve()
        lease.action_send_for_signature()
        lease.action_mark_signed()
        with self.assertRaises(UserError):
            lease.action_send_for_signature()
        with self.assertRaises(UserError):
            lease.action_cancel()

    def test_an_active_lease_cannot_be_cancelled(self):
        lease = self._activate(self._lease("P4"))
        with self.assertRaises(UserError):
            lease.action_cancel()

    def test_notice_needs_a_running_tenancy(self):
        lease = self._lease("P5")
        with self.assertRaises(UserError):
            lease.action_give_notice()
        self._activate(lease)
        lease.action_give_notice()
        self.assertEqual(lease.state, "notice")

    def test_a_closed_lease_cannot_be_reactivated(self):
        lease = self._activate(self._lease("P6"))
        lease.action_give_notice()
        lease.state = "expired"
        with self.assertRaises(UserError) as caught:
            lease.action_activate()
        self.assertIn("cannot be activated", str(caught.exception))
