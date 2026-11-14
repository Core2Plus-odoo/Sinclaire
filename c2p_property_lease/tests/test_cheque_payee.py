"""BR-043, BR-047, BR-114, BR-116, BR-117: whose cheque is it, and whose money.

BRD §4.2.2 is one sentence and it governs this whole file: "Payee names shall
be derived from the operating model and contract authority. For management-only
arrangements, tenant cheques or payments may be in the landlord's name and must
not be presented as company funds."

Before this, every tenant cheque on the register was implicitly the company's,
because the module was written when head leasing was the only model. The
landlord-name cheque - money this company holds and banks on the landlord's
behalf - had nowhere to live, and a register that cannot tell the two apart is
one that reports other people's money as cash.
"""

from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class ChequeCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Payee Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Payee Tenant"})
        cls.employer = cls.env["res.partner"].create({"name": "Tenant's Employer"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Payee Properties"})

    def _journal(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            self.skipTest("no bank journal with an inbound payment method")
        return journal

    def _building(self, code, model):
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

    def _lease(self, building, name, rent=120000.0):
        unit = self.env["c2p.unit"].create(
            {
                "name": name,
                "building_id": building.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": rent,
                "dewa_no": f"27{abs(hash(name)) % 100000:05d}",
            }
        )
        unit.sudo().action_release()
        return self.env["c2p.lease"].create(
            {
                "unit_id": unit.id,
                "tenant_id": self.tenant.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": rent,
                "cheque_count": "1",
            }
        )

    def _cheque(self, lease, cheque_no="500001", **kw):
        journal = self._journal()
        vals = {
            "partner_id": self.tenant.id,
            "partner_type": "customer",
            "payment_type": "inbound",
            "amount": 30000.0,
            "journal_id": journal.id,
            "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
            "lease_id": lease.id,
            "cheque_no": cheque_no,
            "maturity_date": "2026-03-01",
        }
        vals.update(kw)
        return self.env["account.payment"].create(vals)


class TestPayeeDerivation(ChequeCase):
    """BR-043 / BRD §4.2.2."""

    def test_a_head_leased_building_s_rent_is_payable_to_the_company(self):
        """We bought the income, so the cheque is ours to bank."""
        lease = self._lease(self._building("PHL", "head_lease"), "PHL-101")
        cheque = self._cheque(lease)
        self.assertEqual(cheque.payee_partner_id, self.env.company.partner_id)
        self.assertFalse(cheque.is_owner_funds)

    def test_an_owner_managed_building_s_rent_is_payable_to_the_landlord(self):
        """The defect, stated as a test: this cheque is not company money."""
        lease = self._lease(self._building("POM", "owner_management"), "POM-101")
        cheque = self._cheque(lease)
        self.assertEqual(
            cheque.payee_partner_id,
            self.landlord,
            "Under Owner Management the tenant cheque is written in the landlord's name.",
        )
        self.assertTrue(
            cheque.is_owner_funds,
            'BRD §6.1 calls this money "not New Sinclair cash or rental income".',
        )

    def test_the_payee_follows_the_operating_model_when_it_changes(self):
        """A building reclassified mid-year must not leave its cheques pointing
        at the wrong party - that is the silent half of the same defect."""
        building = self._building("PSW", "head_lease")
        lease = self._lease(building, "PSW-101")
        cheque = self._cheque(lease)
        self.assertFalse(cheque.is_owner_funds)
        building.operating_model = "owner_management"
        cheque.invalidate_recordset()
        self.assertEqual(cheque.payee_partner_id, self.landlord)
        self.assertTrue(cheque.is_owner_funds)

    def test_the_payee_can_be_overridden_where_the_contract_says_otherwise(self):
        """BRD §4.2.2 derives the payee from the operating model AND contract
        authority. The model is the default, not a cage."""
        lease = self._lease(self._building("POV", "owner_management"), "POV-101")
        cheque = self._cheque(lease)
        agent = self.env["res.partner"].create({"name": "Appointed Collection Agent"})
        cheque.payee_partner_id = agent
        self.assertEqual(cheque.payee_partner_id, agent)

    def test_a_landlord_cheque_we_issue_is_not_owner_funds(self):
        """Money out under a head lease is payable to the landlord, but it was
        always ours. Payee alone does not decide whose funds these are."""
        building = self._building("PLC", "head_lease")
        head = self.env["c2p.head.lease"].create(
            {
                "building_id": building.id,
                "landlord_id": self.landlord.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_amount": 400000.0,
                "cheque_count": "4",
            }
        )
        journal = self._journal()
        cheque = self.env["account.payment"].create(
            {
                "partner_id": self.landlord.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "amount": 100000.0,
                "journal_id": journal.id,
                "head_lease_id": head.id,
                "cheque_no": "600001",
            }
        )
        self.assertEqual(cheque.payee_partner_id, self.landlord)
        self.assertFalse(cheque.is_owner_funds, "Our own payment out is not owner funds.")


class TestDrawer(ChequeCase):
    """BR-047 / BRD §4.2.3: the legal payer and the debtor are two questions."""

    def test_a_cheque_signed_by_the_tenant_is_not_third_party(self):
        lease = self._lease(self._building("DTN", "head_lease"), "DTN-101")
        cheque = self._cheque(lease, drawer_partner_id=self.tenant.id)
        self.assertFalse(cheque.is_third_party)

    def test_a_cheque_signed_by_somebody_else_is_flagged(self):
        """The employer pays, the tenant still owes. Both have to be on record:
        the receivable follows the tenant, the bank follows the drawer."""
        lease = self._lease(self._building("DTP", "head_lease"), "DTP-101")
        cheque = self._cheque(lease, drawer_partner_id=self.employer.id)
        self.assertTrue(cheque.is_third_party)
        self.assertEqual(
            cheque.partner_id,
            self.tenant,
            "A third party paying does not move the obligation off the tenant.",
        )
        self.assertEqual(cheque.drawer_partner_id, self.employer)

    def test_the_register_wizard_records_the_tenant_as_the_drawer(self):
        """So the common case is on record rather than blank, which is what
        makes the third-party flag mean something."""
        lease = self._lease(self._building("DWZ", "head_lease"), "DWZ-101")
        journal = self._journal()
        wizard = self.env["c2p.pdc.register"].create(
            {
                "lease_id": lease.id,
                "journal_id": journal.id,
                "first_maturity": "2026-01-01",
                "bank_name": "Emirates NBD",
                "first_cheque_no": "700001",
            }
        )
        wizard._onchange_generate()
        self.assertTrue(wizard.line_ids)
        for line in wizard.line_ids:
            self.assertEqual(line.drawer_partner_id, self.tenant)

    def test_the_wizard_warns_which_name_to_ask_for(self):
        """Whoever takes the cheques in needs to know before the tenant writes
        them, not after."""
        om = self.env["c2p.pdc.register"].create(
            {
                "lease_id": self._lease(self._building("DWO", "owner_management"), "DWO-101").id,
                "journal_id": self._journal().id,
                "first_maturity": "2026-01-01",
                "bank_name": "Emirates NBD",
                "first_cheque_no": "700101",
            }
        )
        self.assertTrue(om.payee_is_landlord)
        self.assertEqual(om.payee_partner_id, self.landlord)


class TestChequeStates(ChequeCase):
    """BR-114 and BR-117: where every instrument is, and how a bounce closes."""

    def test_an_expected_cheque_is_not_a_received_one(self):
        """BR-075 counts cover from cheques in hand. A cheque the schedule says
        is due and nobody has handed over must not tick that box."""
        lease = self._lease(self._building("SEX", "head_lease"), "SEX-101")
        self._cheque(lease, amount=120000.0, pdc_state="expected")
        lease.invalidate_recordset()
        self.assertEqual(lease.cheques_received, 0)
        self.assertEqual(lease.cheque_cover, 0.0)
        self.assertFalse(lease.cheques_complete)

    def test_a_bounce_is_closed_by_its_replacement(self):
        """BR-117. The bounced instrument moves to Replaced, so the bounce
        register shows what is still outstanding rather than every bounce that
        ever happened."""
        lease = self._lease(self._building("SRP", "head_lease"), "SRP-101")
        original = self._cheque(lease, cheque_no="800001")
        original.action_pdc_bounce()
        self.assertEqual(original.pdc_state, "bounced")
        replacement = self._cheque(lease, cheque_no="800002")
        original.action_link_replacement(replacement)
        self.assertEqual(original.pdc_state, "replaced")
        self.assertEqual(original.replacement_payment_id, replacement)

    def test_a_replaced_cheque_does_not_count_towards_cover_twice(self):
        """The replacement is a payment record of its own and is counted there."""
        lease = self._lease(self._building("SCV", "head_lease"), "SCV-101")
        original = self._cheque(lease, cheque_no="810001", amount=120000.0)
        original.action_pdc_bounce()
        replacement = self._cheque(lease, cheque_no="810002", amount=120000.0)
        original.action_link_replacement(replacement)
        lease.invalidate_recordset()
        self.assertEqual(lease.cheques_received, 1, "Only the replacement is in hand.")
        self.assertEqual(lease.cheque_cover, 120000.0, "Not 240,000 - the cover is not doubled.")

    def test_only_a_bounced_cheque_can_be_replaced(self):
        lease = self._lease(self._building("SOB", "head_lease"), "SOB-101")
        held = self._cheque(lease, cheque_no="820001")
        other = self._cheque(lease, cheque_no="820002")
        with self.assertRaises(UserError):
            held.action_link_replacement(other)

    def test_a_replacement_must_sit_on_the_same_lease(self):
        """Otherwise a bounce on one tenancy could be closed with another
        tenant's cheque, and both registers would read as covered."""
        head = self._building("SSL", "head_lease")
        lease_a = self._lease(head, "SSL-101")
        lease_b = self._lease(head, "SSL-102")
        bounced = self._cheque(lease_a, cheque_no="830001")
        bounced.action_pdc_bounce()
        stranger = self._cheque(lease_b, cheque_no="830002")
        with self.assertRaises(ValidationError):
            bounced.replacement_payment_id = stranger

    def test_a_cheque_cannot_replace_itself(self):
        lease = self._lease(self._building("SSF", "head_lease"), "SSF-101")
        cheque = self._cheque(lease, cheque_no="840001")
        with self.assertRaises(ValidationError):
            cheque.replacement_payment_id = cheque


class TestOwnerFundsCustody(ChequeCase):
    """BR-116 / BRD §6.1: where the landlord's money went."""

    def test_owner_funds_cannot_clear_without_the_landlord_s_bank_account(self):
        """An owner-funds cheque marked Cleared with no destination is
        indistinguishable from one this company banked for itself."""
        lease = self._lease(self._building("CUS", "owner_management"), "CUS-101")
        cheque = self._cheque(lease, cheque_no="900001")
        self.assertTrue(cheque.is_owner_funds)
        with self.assertRaises(UserError):
            cheque.action_pdc_clear()
        self.assertNotEqual(cheque.pdc_state, "cleared")

    def test_owner_funds_clear_once_the_deposit_account_is_recorded(self):
        lease = self._lease(self._building("CUD", "owner_management"), "CUD-101")
        cheque = self._cheque(lease, cheque_no="900002")
        cheque.partner_bank_id = self.env["res.partner.bank"].create(
            {"acc_number": "AE070331234567890123456", "partner_id": self.landlord.id}
        )
        cheque.action_pdc_clear()
        self.assertEqual(cheque.pdc_state, "cleared")

    def test_company_cheques_clear_without_one(self):
        """The guard is about other people's money, not paperwork for its own
        sake."""
        lease = self._lease(self._building("CUC", "head_lease"), "CUC-101")
        cheque = self._cheque(lease, cheque_no="900003")
        cheque.action_pdc_clear()
        self.assertEqual(cheque.pdc_state, "cleared")
