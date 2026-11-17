from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSamplePortfolio(TransactionCase):
    """The loader runs against real databases, where a second click must not
    double the portfolio."""

    def test_loading_twice_adds_nothing(self):
        Portfolio = self.env["c2p.sample.portfolio"]
        # Accounting is skipped: this asserts the structural records, and
        # cheques need a bank journal that a bare test database may not have.
        Portfolio.load(with_accounting=False)
        again = Portfolio.load(with_accounting=False)
        self.assertEqual(again["buildings"], 0)
        self.assertEqual(again["units"], 0)
        self.assertEqual(
            again["leases"],
            0,
            "a re-run created leases: the vacancy decision is not stable across runs",
        )

    def test_vacancy_decision_is_independent_of_call_order(self):
        """Regression: vacancy used to be drawn from a shared RNG stream, so on
        a re-run - where existing units skip their attribute draws - the stream
        shifted and different units came out vacant."""
        Portfolio = self.env["c2p.sample.portfolio"]
        first = [Portfolio._rng("vacancy", f"MKH-10{i}").random() for i in range(1, 5)]
        # Draw unrelated streams in between; the vacancy values must not move.
        for i in range(1, 5):
            Portfolio._rng("unit", f"MKH-10{i}").random()
        second = [Portfolio._rng("vacancy", f"MKH-10{i}").random() for i in range(1, 5)]
        self.assertEqual(first, second)

    def test_loader_populates_an_empty_database(self):
        Portfolio = self.env["c2p.sample.portfolio"]
        Portfolio.load(with_accounting=False)
        self.assertTrue(self.env["c2p.building"].search_count([]))
        self.assertTrue(self.env["c2p.unit"].search_count([]))
        self.assertTrue(self.env["c2p.lease"].search_count([("state", "=", "active")]))

    def test_wizard_reports_what_it_created(self):
        wizard = self.env["c2p.sample.loader"].create({"with_accounting": False})
        wizard.action_load()
        self.assertTrue(wizard.result)
        self.assertIn("Buildings", wizard.result)

    def test_every_counter_is_declared(self):
        """Regression: the summary used a hand-written key tuple, and adding a
        counter without updating it blew up mid-load with a KeyError."""
        import re
        from pathlib import Path

        from odoo.addons.c2p_property_lease.models import sample_portfolio

        src = Path(sample_portfolio.__file__).read_text()
        used = set(re.findall(r'created\["(\w+)"\]', src))
        self.assertFalse(
            used - set(sample_portfolio.COUNTERS),
            "a counter is incremented but missing from COUNTERS",
        )

    def test_summary_reports_every_counter_even_when_nothing_is_created(self):
        Portfolio = self.env["c2p.sample.portfolio"]
        Portfolio.load(with_accounting=False)
        again = Portfolio.load(with_accounting=False)
        for counter in ("buildings", "units", "leases", "head_leases"):
            self.assertIn(counter, again)
            self.assertEqual(again[counter], 0)


@tagged("post_install", "-at_install")
class TestThePortfolioCoversTheBusiness(TransactionCase):
    """BR-019, BR-022, BRD §4.1.2.

    A seed where every building is head-leased demonstrates a third of the
    business, and it lets the head-lease assumption look correct: the margin
    defect BR-019 fixed was invisible for weeks precisely because no
    owner-managed building existed to contradict it. These tests exist so the
    portfolio cannot quietly narrow back to one operating model.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["c2p.sample.portfolio"].load(with_accounting=False)

    def test_all_three_operating_models_are_represented(self):
        found = set(self.env["c2p.building"].search([]).mapped("operating_model"))
        for model in ("head_lease", "owner_management", "brokerage"):
            self.assertIn(model, found, f"the portfolio has no {model} building to demonstrate")

    def test_no_head_lease_sits_on_a_building_that_cannot_carry_one(self):
        """BR-019. Underwriting is what head leasing means, and the model
        refuses the contradiction outright - so a seed that offered one would
        fail to load at all."""
        for head in self.env["c2p.head.lease"].search([]):
            self.assertEqual(
                head.building_id.operating_model,
                "head_lease",
                f"{head.building_id.code} carries a head lease but is not head-leased",
            )

    def test_one_head_lease_collects_in_the_landlords_name(self):
        """BR-022. The case that separates the two halves of BRD §4.2.2: we may
        be authorised to sign the tenancy while the rent is still collected in
        the landlord's name, and only the contract authority says so."""
        collecting_for_owner = self.env["c2p.head.lease"].search([("collection_party", "=", "owner")])
        self.assertTrue(
            collecting_for_owner,
            "no head lease collects in the landlord's name, so contract authority is never exercised",
        )
        for head in collecting_for_owner:
            self.assertEqual(head.building_id.operating_model, "head_lease")

    def test_the_brokerage_building_holds_no_tenancies_of_ours(self):
        brokerage = self.env["c2p.building"].search([("operating_model", "=", "brokerage")])
        self.assertTrue(brokerage.unit_ids, "a brokerage building with no listing stock shows nothing")
        self.assertFalse(
            self.env["c2p.lease"].search_count([("building_id", "in", brokerage.ids)]),
            "brokerage earns commission on transactions; we do not hold those tenancies",
        )


@tagged("post_install", "-at_install")
class TestTheChequeRegisterIsFullyExercised(TransactionCase):
    """BR-114, BR-116, BR-117, BR-047.

    The register carries seven states, owner funds, third-party drawers and a
    replacement chain. A seed that reaches four of the seven leaves the rest
    untested by every screen, report and demo that reads it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            raise cls.skipTest(cls, "no bank journal with an inbound payment method")
        cls.env["c2p.sample.portfolio"].load()
        cls.cheques = cls.env["account.payment"].search([("lease_id", "!=", False)])

    def test_every_instrument_state_appears(self):
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_STATES

        found = set(self.cheques.mapped("pdc_state"))
        for state, label in PDC_STATES:
            self.assertIn(state, found, f"no instrument is {label}, so that column is never demonstrated")

    def test_an_expected_instrument_carries_no_number(self):
        """BR-114. Expected means the schedule says one is due and nobody has
        handed it over. A number would make it indistinguishable from In Hand,
        which is the difference between a collection problem and a data-entry
        one."""
        for cheque in self.cheques.filtered(lambda c: c.pdc_state == "expected"):
            self.assertFalse(cheque.cheque_no, "an expected instrument has not been received, so it has no number")

    def test_owner_funds_arise_from_both_routes(self):
        """Owner Management is one route to owner funds; a head lease collected
        in the landlord's name is the other, and it is the one the operating
        model alone cannot express."""
        owner_funds = self.cheques.filtered("is_owner_funds")
        self.assertTrue(owner_funds, "no owner funds in the portfolio")
        models = set(owner_funds.mapped("building_id.operating_model"))
        self.assertIn("owner_management", models)
        self.assertIn("head_lease", models, "no head-leased building collects in the landlord's name")

    def test_no_head_leased_building_produces_owner_funds_by_accident(self):
        for cheque in self.cheques.filtered(
            lambda c: c.is_owner_funds and c.building_id.operating_model == "head_lease"
        ):
            active = cheque.building_id.head_lease_ids.filtered(lambda h: h.state == "active")
            self.assertEqual(
                active[:1].collection_party,
                "owner",
                "a head-leased building is producing owner funds without the authority to",
            )

    def test_cleared_owner_funds_record_where_the_money_went(self):
        """BR-116. A cleared owner-funds instrument with no destination is
        indistinguishable from one this company banked for itself."""
        for cheque in self.cheques.filtered(lambda c: c.is_owner_funds and c.pdc_state == "cleared"):
            self.assertTrue(
                cheque.owner_deposit_bank_id,
                f"{cheque.cheque_no} cleared as owner funds with no landlord account recorded",
            )
            self.assertEqual(cheque.owner_deposit_bank_id.partner_id, cheque.payee_partner_id)

    def test_a_replaced_instrument_links_to_the_one_that_made_it_good(self):
        replaced = self.cheques.filtered(lambda c: c.pdc_state == "replaced")
        self.assertTrue(replaced, "no bounce has been made good, so the replacement chain is never shown")
        for cheque in replaced:
            self.assertTrue(cheque.replacement_payment_id)
            self.assertEqual(cheque.replacement_payment_id.lease_id, cheque.lease_id)

    def test_some_bounces_remain_outstanding(self):
        """A register where every bounce has been replaced shows nothing to
        chase; one where none has shows a company that never collects."""
        self.assertTrue(
            self.cheques.filtered(lambda c: c.pdc_state == "bounced"),
            "every bounce has been made good, so the bounce register is empty",
        )

    def test_a_bounce_records_why(self):
        for cheque in self.cheques.filtered(lambda c: c.pdc_state == "bounced"):
            self.assertTrue(cheque.bounce_reason, "a bounce with no reason cannot be followed up")

    def test_third_party_cheques_exist_and_do_not_move_the_debtor(self):
        """BR-047. Somebody else paying does not move the obligation: the
        receivable stays against the tenant."""
        third_party = self.cheques.filtered("is_third_party")
        self.assertTrue(third_party, "no third-party instrument, so the drawer distinction is never exercised")
        for cheque in third_party:
            self.assertNotEqual(cheque.drawer_partner_id, cheque.lease_id.tenant_id)
            self.assertEqual(cheque.partner_id, cheque.lease_id.tenant_id)
