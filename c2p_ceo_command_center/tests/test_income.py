from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestDashboardIncome(AccountTestInvoicingCommon):
    """Income KPIs against real posted invoices, not just field types."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # This common class runs as an accountant, who is not a property
        # manager. The dashboard is for managers, so grant the group.
        cls.env.user.group_ids |= cls.env.ref("c2p_property_lease.group_property_manager")
        cls.landlord = cls.env["res.partner"].create({"name": "Income Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Income Tenant"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Income Buildings"})
        cls.analytic = cls.env["account.analytic.account"].create(
            {
                "name": "Income Tower",
                "plan_id": cls.plan.id,
            }
        )
        cls.building = cls.env["c2p.building"].create(
            {
                "name": "Income Tower",
                "code": "INC",
                "owner_id": cls.landlord.id,
                "analytic_account_id": cls.analytic.id,
                "company_id": cls.company_data["company"].id,
            }
        )

    def _dashboard(self):
        return self.env["c2p.ceo.dashboard"].create(
            {
                "company_id": self.company_data["company"].id,
            }
        )

    def _post_invoice(self, partner, amount, fee_building=None):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "company_id": self.company_data["company"].id,
                "journal_id": self.company_data["default_journal_sale"].id,
                "invoice_date": self.env["c2p.ceo.dashboard"]._fields["date_to"].default(self.env["c2p.ceo.dashboard"]),
                "c2p_fee_building_id": fee_building.id if fee_building else False,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Rent" if not fee_building else "Management fee",
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        move.action_post()
        return move

    def test_rent_and_fee_are_reported_separately(self):
        before = self._dashboard()
        rent_before, fee_before = before.rent_invoiced, before.fee_invoiced

        self._post_invoice(self.tenant, 10000.0)
        self._post_invoice(self.landlord, 500.0, fee_building=self.building)

        after = self._dashboard()
        self.assertAlmostEqual(after.rent_invoiced, rent_before + 10000.0, places=2)
        self.assertAlmostEqual(after.fee_invoiced, fee_before + 500.0, places=2)

    def test_a_fee_invoice_never_inflates_rent(self):
        """Regression: the fee invoice carries the building's analytic account,
        so counting it as rent would double-count our own income."""
        before = self._dashboard().rent_invoiced
        self._post_invoice(self.landlord, 750.0, fee_building=self.building)
        self.assertAlmostEqual(self._dashboard().rent_invoiced, before, places=2)

    def test_draft_invoices_are_excluded(self):
        before = self._dashboard().rent_invoiced
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.tenant.id,
                "company_id": self.company_data["company"].id,
                "journal_id": self.company_data["default_journal_sale"].id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Draft rent",
                            "quantity": 1,
                            "price_unit": 8000.0,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        self.assertAlmostEqual(self._dashboard().rent_invoiced, before, places=2)
