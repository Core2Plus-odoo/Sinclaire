from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestHeadLease(TransactionCase):
    """Under underwriting, vacancy is our cost. These assert the numbers that
    say whether a building earns its keep."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "HL Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "HL Tenant"})
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "Underwritten Tower",
                "code": "UWT",
                "owner_id": cls.landlord.id,
            }
        )
        # Two units at 100k market rent each: potential rent 200k.
        cls.unit_a, cls.unit_b = [
            cls.env["c2p.unit"].create(
                {
                    "name": f"UWT-10{i}",
                    "building_id": cls.building.id,
                    "unit_type": "2br",
                    "market_rent": 100000.0,
                    "area_sqft": 1200,
                }
            )
            for i in (1, 2)
        ]

    def _head_lease(self, amount=140000.0, **kw):
        vals = {
            "building_id": self.building.id,
            "landlord_id": self.landlord.id,
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "annual_amount": amount,
            "cheque_count": "4",
        }
        vals.update(kw)
        lease = self.env["c2p.head.lease"].create(vals)
        lease.action_activate()
        return lease

    def _let(self, unit, rent):
        lease = self.env["c2p.lease"].create(
            {
                "tenant_id": self.tenant.id,
                "unit_id": unit.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": rent,
                "cheque_count": "4",
            }
        )
        lease.action_activate()
        return lease

    def test_instalment_splits_the_annual_amount(self):
        self.assertEqual(self._head_lease().instalment_amount, 35000.0)

    def test_breakeven_occupancy_is_cost_over_market_rent(self):
        """140k owed against 200k of market rent means 70% of the building must
        be let before we make a penny."""
        head = self._head_lease()
        self.assertAlmostEqual(head.breakeven_occupancy, 70.0, places=4)

    def test_a_building_below_break_even_shows_negative_margin(self):
        head = self._head_lease()
        self._let(self.unit_a, 100000.0)  # one of two units let
        self.building.invalidate_recordset()
        head.invalidate_recordset()
        self.assertEqual(head.contracted_rent, 100000.0)
        self.assertEqual(head.gross_margin, -40000.0)
        self.assertLess(head.coverage_ratio, 1.0)

    def test_full_occupancy_covers_the_head_lease(self):
        head = self._head_lease()
        self._let(self.unit_a, 100000.0)
        self._let(self.unit_b, 100000.0)
        self.building.invalidate_recordset()
        head.invalidate_recordset()
        self.assertEqual(head.gross_margin, 60000.0)
        self.assertGreater(head.coverage_ratio, 1.0)

    def test_a_building_cannot_be_underwritten_twice_over(self):
        self._head_lease()
        with self.assertRaises(ValidationError):
            self._head_lease()

    def test_head_lease_must_end_after_it_starts(self):
        with self.assertRaises(ValidationError):
            self._head_lease(date_start="2026-12-31", date_end="2026-01-01")

    def test_expiry_cron_closes_finished_agreements(self):
        head = self._head_lease(date_start="2020-01-01", date_end="2020-12-31")
        self.env["c2p.head.lease"]._cron_expire_head_leases()
        self.assertEqual(head.state, "expired")

    def test_building_reports_its_active_head_lease(self):
        head = self._head_lease()
        self.building.invalidate_recordset()
        self.assertEqual(self.building.head_lease_id, head)
        self.assertEqual(self.building.head_lease_cost, 140000.0)

    def test_landlord_cheques_are_flagged_as_outbound(self):
        head = self._head_lease()
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.outbound_payment_method_line_ids:
            self.skipTest("no bank journal with an outbound payment method")
        payment = self.env["account.payment"].create(
            {
                "partner_id": self.landlord.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "amount": head.instalment_amount,
                "journal_id": journal.id,
                "payment_method_line_id": journal.outbound_payment_method_line_ids[0].id,
                "head_lease_id": head.id,
                "cheque_no": "400001",
            }
        )
        self.assertTrue(payment.is_landlord_cheque)
        self.assertTrue(payment.is_pdc)
        head.invalidate_recordset()
        self.assertEqual(head.outstanding_amount, head.instalment_amount)
        payment.action_pdc_clear()
        head.invalidate_recordset()
        self.assertEqual(head.paid_amount, head.instalment_amount)
        self.assertEqual(head.outstanding_amount, 0.0)
