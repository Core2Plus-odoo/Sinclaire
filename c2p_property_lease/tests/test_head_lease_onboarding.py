"""BR-013, BR-014, BR-021, BR-022, BR-027: onboarding a head lease properly.

Activating a head lease commits this company to pay a landlord a fixed sum for
a year whether or not a single unit is let. Before this, nothing stopped that
commitment being recorded from an agreement nobody had produced, over a
building with no municipality reference, with no insurance and no bank account
to pay into.

The most consequential test in this file is the last class. BRD §4.2.2 derives
the payee from "the operating model and contract authority", and only the
operating model was implemented. A head-lease agreement can authorise this
company to sign tenancies while still requiring rent to be collected in the
landlord's name, and where it does, those cheques are the landlord's money
passing through our hands - exactly as under Owner Management, and regardless
of what the building's operating model says.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class OnboardingCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Onboarding Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Onboarding Tenant"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Onboarding Properties"})
        cls.today = fields.Date.context_today(cls.env.user)

    def _building(self, code, complete=True, model="head_lease"):
        vals = {
            "name": f"{code} Tower",
            "code": code,
            "owner_id": self.landlord.id,
            "operating_model": model,
            "analytic_account_id": self.env["account.analytic.account"]
            .create({"name": f"{code} Tower", "plan_id": self.plan.id})
            .id,
        }
        if complete:
            # BR-021. Deliberately omitted when complete=False, so a test can
            # prove the gate catches a building that cannot be identified.
            vals.update({"plot_no": f"PLOT-{code}", "municipality_no": f"MUN-{code}"})
        return self.env["c2p.building"].create(vals)

    def _bank(self, partner=None):
        """Reused, not recreated.

        A landlord has one account. Creating a second with a generated number
        tripped res_partner_bank_unique_number the moment a test made two
        head leases for the same landlord - which the renewal tests do by
        definition.
        """
        partner = partner or self.landlord
        return self.env["res.partner.bank"].search([("partner_id", "=", partner.id)], limit=1) or self.env[
            "res.partner.bank"
        ].create(
            {
                "acc_number": f"AE070331{partner.id:012d}",
                "partner_id": partner.id,
            }
        )

    def _head_lease(self, building, complete=True, **kw):
        vals = {
            "building_id": building.id,
            "landlord_id": self.landlord.id,
            "date_start": self.today,
            "date_end": self.today + timedelta(days=364),
            "annual_amount": 400000.0,
            "cheque_count": "4",
        }
        if complete:
            vals.update(
                {
                    "agreement_ref": "HL-2026-001",
                    "date_signed": self.today,
                    "landlord_bank_id": self._bank().id,
                    "contracting_party": "manager",
                    "collection_party": "manager",
                    "sublease_permitted": True,
                    "insurance_expiry": self.today + timedelta(days=200),
                }
            )
        vals.update(kw)
        return self.env["c2p.head.lease"].create(vals)


class TestTheActivationGate(OnboardingCase):
    """BR-027."""

    def test_a_complete_head_lease_activates(self):
        head = self._head_lease(self._building("OGC"))
        self.assertTrue(head.is_activatable, head.activation_blockers)
        head.action_activate()
        self.assertEqual(head.state, "active")

    def test_an_agreement_nobody_has_produced_cannot_be_activated(self):
        """The commitment is real money. The evidence for it should be too."""
        head = self._head_lease(self._building("OGA"), agreement_ref=False)
        self.assertFalse(head.is_activatable)
        self.assertIn("Signed agreement reference", head.activation_blockers)
        with self.assertRaises(UserError):
            head.action_activate()
        self.assertEqual(head.state, "draft")

    def test_a_building_with_no_municipality_reference_blocks_activation(self):
        """BR-021 feeding BR-027. A building nobody can identify to the
        municipality is one whose tenancies cannot be registered, so
        committing to pay for it is committing to something unlettable."""
        head = self._head_lease(self._building("OGM", complete=False))
        self.assertFalse(head.is_activatable)
        self.assertIn("plot and municipality references", head.activation_blockers)

    def test_lapsed_insurance_blocks_activation(self):
        head = self._head_lease(self._building("OGI"), insurance_expiry=self.today - timedelta(days=1))
        self.assertFalse(head.is_activatable)
        self.assertIn("insurance", head.activation_blockers.lower())

    def test_no_landlord_bank_account_blocks_activation(self):
        """There is no point agreeing instalments with nowhere to send them."""
        head = self._head_lease(self._building("OGB"), landlord_bank_id=False)
        self.assertFalse(head.is_activatable)
        self.assertIn("bank account", head.activation_blockers)

    def test_the_blockers_match_the_gate_that_refuses(self):
        """Derived from HEAD_LEASE_REQUIREMENTS rather than restated, so the
        screen cannot name a reason the gate does not enforce. Somebody would
        go and fix the wrong thing."""
        head = self._head_lease(
            self._building("OGX", complete=False),
            agreement_ref=False,
            date_signed=False,
            insurance_expiry=False,
        )
        self.assertFalse(head.is_activatable)
        with self.assertRaises(UserError) as caught:
            head.action_activate()
        for label in head.activation_blockers.split(", "):
            self.assertIn(label, str(caught.exception))

    def test_every_missing_item_is_listed_not_just_the_first(self):
        """A gate that reveals one problem at a time turns onboarding into
        a guessing game."""
        head = self._head_lease(self._building("OGL", complete=False), agreement_ref=False, insurance_expiry=False)
        self.assertGreaterEqual(len(head.activation_blockers.split(", ")), 3)


class TestSubleasingPermission(OnboardingCase):
    """BR-022. A head lease is subleasing by definition."""

    def test_an_agreement_forbidding_subleasing_cannot_be_activated(self):
        head = self._head_lease(self._building("OSF"), sublease_permitted=False)
        with self.assertRaises(ValidationError) as caught:
            head.action_activate()
        self.assertIn("subleasing", str(caught.exception).lower())

    def test_the_message_offers_the_right_alternative(self):
        """If the landlord will not permit subleasing, the arrangement is
        management, not underwriting. Saying so saves an argument."""
        head = self._head_lease(self._building("OSA"), sublease_permitted=False)
        with self.assertRaises(ValidationError) as caught:
            head.action_activate()
        self.assertIn("Owner Management", str(caught.exception))


class TestRenewalIsNotAnOverlap(OnboardingCase):
    """BR-014."""

    def test_two_unrelated_head_leases_still_clash(self):
        building = self._building("ORC")
        first = self._head_lease(building)
        first.action_activate()
        second = self._head_lease(building)
        with self.assertRaises(ValidationError):
            second.action_activate()

    def test_a_renewal_may_touch_the_term_it_renews(self):
        """A term that begins as the previous one ends is the same commercial
        arrangement continuing, not a double commitment."""
        building = self._building("ORR")
        first = self._head_lease(building)
        first.action_activate()
        renewal = self._head_lease(
            building,
            date_start=first.date_end,
            date_end=first.date_end + timedelta(days=364),
            renewal_of_id=first.id,
        )
        renewal.action_activate()
        self.assertEqual(renewal.state, "active")
        self.assertEqual(renewal.renewal_of_id, first)

    def test_the_link_works_in_both_directions(self):
        """Checked from either record, because the clash is checked from
        whichever one is being activated."""
        building = self._building("ORB")
        first = self._head_lease(building)
        first.action_activate()
        renewal = self._head_lease(
            building,
            date_start=first.date_end,
            date_end=first.date_end + timedelta(days=364),
            renewal_of_id=first.id,
        )
        renewal.action_activate()
        self.assertIn(renewal, first.renewal_ids)
        first._check_no_overlap()


class TestContractAuthorityDecidesThePayee(OnboardingCase):
    """BR-022 completing BR-043.

    BRD §4.2.2: payee names derive from "the operating model and contract
    authority". Only the operating model was implemented. This is the other
    half, and it is the one that moves money.
    """

    def _lease_and_cheque(self, building, name):
        unit = self.env["c2p.unit"].create(
            {
                "name": name,
                "building_id": building.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": 120000.0,
                "dewa_no": f"33{abs(hash(name)) % 100000:05d}",
            }
        )
        unit.sudo().action_release()
        lease = self.env["c2p.lease"].create(
            {
                "unit_id": unit.id,
                "tenant_id": self.tenant.id,
                "date_start": self.today,
                "date_end": self.today + timedelta(days=364),
                "annual_rent": 120000.0,
                "cheque_count": "1",
            }
        )
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            self.skipTest("no bank journal with an inbound payment method")
        return self.env["account.payment"].create(
            {
                "partner_id": self.tenant.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "amount": 30000.0,
                "journal_id": journal.id,
                "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
                "lease_id": lease.id,
                "cheque_no": f"5{abs(hash(name)) % 100000:05d}",
            }
        )

    def test_collection_in_our_name_keeps_the_rent_ours(self):
        building = self._building("OAM")
        self._head_lease(building, collection_party="manager").action_activate()
        cheque = self._lease_and_cheque(building, "OAM-101")
        self.assertEqual(cheque.payee_partner_id, self.env.company.partner_id)
        self.assertFalse(cheque.is_owner_funds)

    def test_collection_in_the_landlords_name_makes_it_owner_funds(self):
        """The defect this closes. A head-leased building whose agreement
        requires collection in the owner's name was producing cheques payable
        to this company - money that is not ours, recorded as though it were.
        """
        building = self._building("OAO")
        self._head_lease(building, collection_party="owner").action_activate()
        cheque = self._lease_and_cheque(building, "OAO-101")
        self.assertEqual(
            cheque.payee_partner_id,
            self.landlord,
            "The agreement requires collection in the landlord's name.",
        )
        self.assertTrue(
            cheque.is_owner_funds,
            "These are the landlord's funds passing through our hands, head lease or not.",
        )

    def test_owner_funds_under_a_head_lease_still_need_a_deposit_account(self):
        """BR-116 applies to the money, not to the operating model."""
        building = self._building("OAD")
        self._head_lease(building, collection_party="owner").action_activate()
        cheque = self._lease_and_cheque(building, "OAD-101")
        with self.assertRaises(UserError):
            cheque.action_pdc_clear()

    def test_changing_the_authority_moves_existing_cheques(self):
        """Correcting the record against the signed agreement has to move the
        money with it - that is the whole reason the migration flags assumed
        values for checking."""
        building = self._building("OAC")
        head = self._head_lease(building, collection_party="manager")
        head.action_activate()
        cheque = self._lease_and_cheque(building, "OAC-101")
        self.assertFalse(cheque.is_owner_funds)
        head.collection_party = "owner"
        # Deliberately no invalidate_recordset(): the point is that the
        # recompute triggers on its own. The first version of this depended on
        # building_id.head_lease_id, a non-stored compute, so the trigger
        # never fired and only a forced invalidation made this pass.
        self.assertTrue(cheque.is_owner_funds)
        self.assertEqual(cheque.payee_partner_id, self.landlord)
