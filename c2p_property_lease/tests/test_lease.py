from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
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
        lease = self._lease()
        lease.action_activate()
        self.assertEqual(lease.state, "active")
        self.assertEqual(self.unit.state, "occupied")
        self.assertEqual(self.unit.current_lease_id, lease)

    def test_second_lease_cannot_occupy_the_same_unit(self):
        self._lease().action_activate()
        other = self._lease(tenant_id=self.landlord.id)
        with self.assertRaises(UserError):
            other.action_activate()

    def test_expiring_releases_the_unit(self):
        lease = self._lease(date_start="2020-01-01", date_end="2020-12-31")
        lease.action_activate()
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
