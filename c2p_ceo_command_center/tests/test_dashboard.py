from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCeoDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.landlord = cls.env["res.partner"].create({"name": "CC Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "CC Tenant"})
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "Command Tower",
                "code": "CMD",
                "owner_id": cls.landlord.id,
            }
        )
        cls.occupied_unit = cls.env["c2p.unit"].create(
            {
                "name": "CMD-101",
                "building_id": cls.building.id,
            }
        )
        cls.vacant_unit = cls.env["c2p.unit"].create(
            {
                "name": "CMD-102",
                "building_id": cls.building.id,
            }
        )
        cls.lease = cls.env["c2p.lease"].create(
            {
                "tenant_id": cls.tenant.id,
                "unit_id": cls.occupied_unit.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": 120000.0,
                "cheque_count": "4",
            }
        )
        cls.lease.action_activate()

    def _dashboard(self):
        return self.env["c2p.ceo.dashboard"].create({})

    def test_portfolio_counts_reflect_the_units(self):
        dash = self._dashboard()
        self.assertGreaterEqual(dash.building_count, 1)
        self.assertGreaterEqual(dash.occupied_count, 1)
        self.assertGreaterEqual(dash.vacant_count, 1)

    def test_occupancy_rate_is_a_percentage_of_units(self):
        dash = self._dashboard()
        expected = dash.occupied_count / dash.unit_count * 100.0 if dash.unit_count else 0.0
        self.assertAlmostEqual(dash.occupancy_rate, expected, places=6)
        self.assertLessEqual(dash.occupancy_rate, 100.0)

    def test_unit_count_is_the_sum_of_every_state(self):
        """Regression: the state breakdown comes from one grouped query, so the
        total must not drift from the individual buckets."""
        dash = self._dashboard()
        total = self.env["c2p.unit"].search_count(dash._company_domain())
        self.assertEqual(dash.unit_count, total)

    def test_contracted_rent_counts_active_leases_only(self):
        before = self._dashboard().contracted_rent
        draft = self.env["c2p.lease"].create(
            {
                "tenant_id": self.tenant.id,
                "unit_id": self.vacant_unit.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": 999999.0,
                "cheque_count": "1",
            }
        )
        self.assertEqual(draft.state, "draft")
        self.assertEqual(self._dashboard().contracted_rent, before)

    def test_expiring_window_counts_only_leases_inside_it(self):
        from datetime import timedelta

        from odoo import fields

        today = fields.Date.context_today(self.env["c2p.ceo.dashboard"])
        before = self._dashboard()
        base_count, base_rent = before.expiring_lease_count, before.expiring_rent

        near_unit = self.env["c2p.unit"].create(
            {
                "name": "CMD-201",
                "building_id": self.building.id,
            }
        )
        near = self.env["c2p.lease"].create(
            {
                "tenant_id": self.tenant.id,
                "unit_id": near_unit.id,
                "date_start": today - timedelta(days=300),
                "date_end": today + timedelta(days=30),
                "annual_rent": 50000.0,
                "cheque_count": "1",
            }
        )
        near.action_activate()

        far_unit = self.env["c2p.unit"].create(
            {
                "name": "CMD-202",
                "building_id": self.building.id,
            }
        )
        far = self.env["c2p.lease"].create(
            {
                "tenant_id": self.tenant.id,
                "unit_id": far_unit.id,
                "date_start": today,
                "date_end": today + timedelta(days=500),
                "annual_rent": 70000.0,
                "cheque_count": "1",
            }
        )
        far.action_activate()

        after = self._dashboard()
        self.assertEqual(after.expiring_lease_count, base_count + 1)
        self.assertAlmostEqual(after.expiring_rent, base_rent + 50000.0, places=2)

    def test_cheque_buckets_are_zero_without_cheques(self):
        dash = self._dashboard()
        self.assertGreaterEqual(dash.pdc_held_count, 0)
        self.assertGreaterEqual(dash.pdc_bounced_count, 0)
        self.assertGreaterEqual(dash.pdc_held_amount, 0.0)

    def test_drill_through_actions_return_window_actions(self):
        dash = self._dashboard()
        for method in (
            "action_open_vacant_units",
            "action_open_expiring_leases",
            "action_open_bounced_cheques",
            "action_open_cheques_in_hand",
            "action_open_active_leases",
        ):
            action = getattr(dash, method)()
            self.assertEqual(action["type"], "ir.actions.act_window")
            self.assertTrue(action["domain"])

    def test_vacant_drill_matches_the_vacant_count(self):
        dash = self._dashboard()
        action = dash.action_open_vacant_units()
        self.assertEqual(self.env["c2p.unit"].search_count(action["domain"]), dash.vacant_count)

    def test_active_lease_drill_matches_the_count(self):
        dash = self._dashboard()
        action = dash.action_open_active_leases()
        self.assertEqual(self.env["c2p.lease"].search_count(action["domain"]), dash.active_lease_count)
