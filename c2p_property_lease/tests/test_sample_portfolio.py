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
