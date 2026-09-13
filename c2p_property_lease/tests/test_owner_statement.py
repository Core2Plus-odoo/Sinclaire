from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestOwnerStatement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Statement Landlord"})
        cls.analytic_plan = cls.env["account.analytic.plan"].create({"name": "Buildings"})
        cls.analytic = cls.env["account.analytic.account"].create(
            {
                "name": "Statement Tower",
                "plan_id": cls.analytic_plan.id,
            }
        )
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "Statement Tower",
                "code": "STM",
                "owner_id": cls.landlord.id,
                "analytic_account_id": cls.analytic.id,
                "management_fee_pct": 5.0,
            }
        )

    def _statement(self):
        return self.env["c2p.owner.statement"].create(
            {
                "building_id": self.building.id,
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
            }
        )

    def test_period_must_not_be_inverted(self):
        with self.assertRaises(UserError):
            self.env["c2p.owner.statement"].create(
                {
                    "building_id": self.building.id,
                    "date_from": "2026-12-31",
                    "date_to": "2026-01-01",
                }
            )

    def test_analytic_share_splits_comma_joined_keys(self):
        """A line split across plans stores a comma-joined key; only this
        building's percentage may be counted."""
        share = self.env["c2p.owner.statement"]._analytic_share(
            {f"{self.analytic.id},999": 60.0, "888": 40.0}, self.analytic.id
        )
        self.assertEqual(share, 60.0)

    def test_analytic_share_ignores_other_accounts(self):
        share = self.env["c2p.owner.statement"]._analytic_share({"888": 100.0}, self.analytic.id)
        self.assertEqual(share, 0.0)

    def test_printing_does_not_raise_an_invoice(self):
        """Regression: action_print used to post a management fee invoice every
        time the statement was printed."""
        statement = self._statement()
        before = self.env["account.move"].search_count([("c2p_fee_building_id", "=", self.building.id)])
        statement.action_print()
        after = self.env["account.move"].search_count([("c2p_fee_building_id", "=", self.building.id)])
        self.assertEqual(before, after)

    def test_fee_invoice_is_refused_twice_for_the_same_period(self):
        statement = self._statement()
        if not statement.management_fee:
            # No rent in the period, so the fee action refuses for that reason.
            with self.assertRaises(UserError):
                statement.action_create_fee_invoice()
            return
        statement.action_create_fee_invoice()
        statement.invalidate_recordset(["fee_invoice_id"])
        with self.assertRaises(UserError):
            statement.action_create_fee_invoice()

    def test_statement_without_analytic_account_is_refused(self):
        self.building.analytic_account_id = False
        with self.assertRaises(UserError):
            self._statement().action_print()

    def test_fee_journal_prefers_the_dedicated_owner_journal(self):
        company = self.building.company_id
        sales = self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)])
        if not sales:
            self.skipTest("no sales journal in this company")
        statement = self._statement()
        owni = self.env["account.journal"].create(
            {
                "name": "Owner Invoices (test)",
                "code": "OWNI",
                "type": "sale",
                "company_id": company.id,
            }
        )
        self.assertEqual(statement._fee_journal(company), owni)

    def test_fee_journal_falls_back_to_the_sales_journal(self):
        company = self.building.company_id
        self.env["account.journal"].search([("code", "=", "OWNI"), ("company_id", "=", company.id)]).unlink()
        sales = self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1)
        if not sales:
            self.skipTest("no sales journal in this company")
        self.assertEqual(self._statement()._fee_journal(company), sales)
