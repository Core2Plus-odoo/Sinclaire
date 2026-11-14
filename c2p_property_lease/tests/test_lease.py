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
        plan = cls.env["account.analytic.plan"].create({"name": "Properties"})
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "Test Tower",
                "code": "TST",
                "owner_id": cls.landlord.id,
                # BR-018 refuses to release a unit whose building has no
                # analytic account, so the fixture building carries one.
                "analytic_account_id": cls.env["account.analytic.account"]
                .create({"name": "Test Tower", "plan_id": plan.id})
                .id,
            }
        )
        cls.unit = cls._lettable_unit("TST-101")

    @classmethod
    def _lettable_unit(self, name, **kw):
        """A unit created and released, which is where most of these tests start.

        BR-018 holds a new unit in Draft until its mandatory data is in, so a
        test that wants a lettable unit has to supply that data and release it.
        """
        vals = {
            "name": name,
            "building_id": self.building.id,
            "unit_type": "1br",
            "floor": "1",
            "area_sqft": 900.0,
            "market_rent": 95000.0,
            "dewa_no": "2000001",
        }
        vals.update(kw)
        unit = self.env["c2p.unit"].create(vals)
        unit.sudo().action_release()
        return unit

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

    # ------------------------------------------------------------- BR-018
    # Units are released for letting only once the data a lease depends on is
    # present, and only by a Leasing Manager.

    def test_a_new_unit_starts_in_draft(self):
        unit = self.env["c2p.unit"].create({"name": "R1", "building_id": self.building.id})
        self.assertEqual(unit.state, "draft")

    def test_an_incomplete_unit_cannot_be_released(self):
        unit = self.env["c2p.unit"].create({"name": "R2", "building_id": self.building.id})
        with self.assertRaises(UserError):
            unit.sudo().action_release()
        self.assertEqual(unit.state, "draft")

    def test_the_refusal_names_every_missing_field_at_once(self):
        unit = self.env["c2p.unit"].create({"name": "R3", "building_id": self.building.id})
        with self.assertRaises(UserError) as caught:
            unit.sudo().action_release()
        message = str(caught.exception)
        for label in ("Floor", "Area", "Market rent", "DEWA"):
            self.assertIn(label, message)

    def test_a_complete_unit_releases(self):
        unit = self._lettable_unit("R4")
        self.assertEqual(unit.state, "available")
        self.assertFalse(unit.release_blockers)
        self.assertTrue(unit.is_releasable)

    def test_a_building_without_an_analytic_account_blocks_release(self):
        """BR-012: rent that cannot be attributed to a building is the defect
        this prevents."""
        bare = self.env["c2p.building"].create({"name": "No Analytic", "code": "NAN", "owner_id": self.landlord.id})
        unit = self.env["c2p.unit"].create(
            {
                "name": "N1",
                "building_id": bare.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": 95000.0,
                "dewa_no": "2000002",
            }
        )
        self.assertIn("Analytic", unit.release_blockers)
        with self.assertRaises(UserError):
            unit.sudo().action_release()

    def test_release_is_a_manager_action(self):
        user = self.env["res.users"].create(
            {
                "name": "Leasing Clerk",
                "login": "clerk_br018",
                "group_ids": [(4, self.env.ref("c2p_property_lease.group_property_user").id)],
            }
        )
        unit = self.env["c2p.unit"].create(
            {
                "name": "R5",
                "building_id": self.building.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": 95000.0,
                "dewa_no": "2000003",
            }
        )
        with self.assertRaises(UserError):
            unit.with_user(user).action_release()

    def test_a_lease_cannot_be_activated_on_an_unreleased_unit(self):
        """Without this the release gate is decorative: the lease would put a
        tenant into a unit whose mandatory data was never checked."""
        unit = self.env["c2p.unit"].create({"name": "R6", "building_id": self.building.id, "unit_type": "1br"})
        lease = self._lease(unit_id=unit.id)
        with self.assertRaises(UserError) as caught:
            self._activate(lease)
        self.assertIn("not been released", str(caught.exception))

    # ------------------------------------------------------------- BR-017
    # Floor rent is the approved minimum, and the override is a manager action.

    def test_a_lease_at_or_above_the_floor_is_fine(self):
        unit = self._lettable_unit("F1", floor_rent=90000.0)
        lease = self._lease(unit_id=unit.id, annual_rent=90000.0)
        self.assertEqual(lease.annual_rent, 90000.0)

    def test_a_lease_below_the_floor_is_refused(self):
        unit = self._lettable_unit("F2", floor_rent=90000.0)
        with self.assertRaises(ValidationError) as caught:
            self._lease(unit_id=unit.id, annual_rent=80000.0)
        self.assertIn("floor rent", str(caught.exception))

    def test_an_approved_discount_lets_it_through(self):
        unit = self._lettable_unit("F3", floor_rent=90000.0)
        lease = self._lease(unit_id=unit.id, annual_rent=80000.0, below_floor_approved=True)
        self.assertTrue(lease.below_floor_approved)

    def test_a_unit_with_no_floor_rent_is_unconstrained(self):
        """How units behaved before BR-017, and how they still behave until a
        floor is approved for them."""
        unit = self._lettable_unit("F4")
        lease = self._lease(unit_id=unit.id, annual_rent=1000.0)
        self.assertEqual(lease.annual_rent, 1000.0)

    def test_the_override_is_a_manager_action(self):
        user = self.env["res.users"].create(
            {
                "name": "Leasing Clerk 2",
                "login": "clerk_br017",
                "group_ids": [(4, self.env.ref("c2p_property_lease.group_property_user").id)],
            }
        )
        unit = self._lettable_unit("F5", floor_rent=90000.0)
        lease = self._lease(unit_id=unit.id, annual_rent=95000.0)
        with self.assertRaises(UserError):
            lease.with_user(user).write({"below_floor_approved": True})

    def test_the_three_rate_sets_are_held_separately(self):
        """A monthly let is not an annual rent over twelve: short lets carry a
        premium, so the rates are stored, not derived."""
        unit = self._lettable_unit("F6", market_rent_monthly=9000.0, market_rent_daily=450.0, floor_rent_monthly=8000.0)
        self.assertEqual(unit.market_rent_monthly, 9000.0)
        self.assertEqual(unit.market_rent_daily, 450.0)
        self.assertEqual(unit.floor_rent_monthly, 8000.0)
        self.assertNotEqual(unit.market_rent_monthly, unit.market_rent / 12.0)

    # ------------------------------------------------------------- BR-016
    # Units are reconciled against what the building declares.

    def test_a_building_with_nothing_declared_does_not_reconcile(self):
        """It has nothing to reconcile against. Reporting it as balanced would
        hide the buildings nobody has filled in."""
        self.assertFalse(self.building.units_reconciled)

    def test_a_building_reconciles_when_the_counts_agree(self):
        building = self.env["c2p.building"].create(
            {
                "name": "Reconciled Tower",
                "code": "REC",
                "owner_id": self.landlord.id,
                "declared_residential_units": 2,
                "declared_commercial_units": 0,
            }
        )
        for n in ("1", "2"):
            self.env["c2p.unit"].create({"name": f"REC-{n}", "building_id": building.id})
        building.invalidate_recordset()
        self.assertEqual(building.declared_unit_count, 2)
        self.assertEqual(building.unit_variance, 0)
        self.assertTrue(building.units_reconciled)

    def test_a_short_building_reports_a_negative_variance(self):
        """The import dropped rows. This is the number that says so."""
        building = self.env["c2p.building"].create(
            {
                "name": "Short Tower",
                "code": "SHT",
                "owner_id": self.landlord.id,
                "declared_residential_units": 5,
            }
        )
        self.env["c2p.unit"].create({"name": "SHT-1", "building_id": building.id})
        building.invalidate_recordset()
        self.assertEqual(building.unit_variance, -4)
        self.assertFalse(building.units_reconciled)

    def test_declared_count_is_residential_plus_commercial(self):
        building = self.env["c2p.building"].create(
            {
                "name": "Mixed Tower",
                "code": "MIX",
                "owner_id": self.landlord.id,
                "declared_residential_units": 8,
                "declared_commercial_units": 3,
            }
        )
        self.assertEqual(building.declared_unit_count, 11)


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
        plan = cls.env["account.analytic.plan"].create({"name": "Properties"})
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "States Tower",
                "code": "STT",
                "owner_id": cls.landlord.id,
                # BR-018 refuses release without an analytic account.
                "analytic_account_id": cls.env["account.analytic.account"]
                .create({"name": "States Tower", "plan_id": plan.id})
                .id,
            }
        )

    def _unit(self, name, state=None, market_rent=100000.0):
        """A unit carrying the data BR-018 requires, so it can be released.

        `state` is written directly: these tests are about the state machine,
        and most of them need a unit parked in a state the transitions would
        not reach from Draft.
        """
        unit = self.env["c2p.unit"].create(
            {
                "name": name,
                "building_id": self.building.id,
                "market_rent": market_rent,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "dewa_no": f"24{abs(hash(name)) % 100000:05d}",
            }
        )
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
        unit.sudo().action_release()
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
        plan = cls.env["account.analytic.plan"].create({"name": "Properties"})
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "LS Tower",
                "code": "LST",
                "owner_id": cls.landlord.id,
                # BR-018 refuses release without an analytic account.
                "analytic_account_id": cls.env["account.analytic.account"]
                .create({"name": "LS Tower", "plan_id": plan.id})
                .id,
            }
        )

    def _lease(self, unit_name):
        unit = self.env["c2p.unit"].create(
            {
                "name": unit_name,
                "building_id": self.building.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": 100000.0,
                "dewa_no": f"25{abs(hash(unit_name)) % 100000:05d}",
            }
        )
        # BR-018: a lease cannot be activated on a unit never released.
        unit.sudo().action_release()
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
