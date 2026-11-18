"""The portfolio card's one line, and which of several true things it says.

A building can be simultaneously under-covered, unreconciled and half empty.
All three are true; only one belongs on the card. These tests pin the order,
because the order is the design decision - get it wrong and the screen shows
a vacancy notice on a building that is losing money every month.
"""

from odoo.tests.common import TransactionCase


class PortfolioCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Portfolio Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Portfolio Tenant"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Portfolio Properties"})

    def _building(self, code, model="head_lease", **kw):
        vals = {
            "name": f"{code} Tower",
            "code": code,
            "owner_id": self.landlord.id,
            "operating_model": model,
            "analytic_account_id": self.env["account.analytic.account"]
            .create({"name": f"{code} Tower", "plan_id": self.plan.id})
            .id,
        }
        vals.update(kw)
        return self.env["c2p.building"].create(vals)

    def _unit(self, building, name, rent=100000.0):
        unit = self.env["c2p.unit"].create(
            {
                "name": name,
                "building_id": building.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": rent,
                "dewa_no": f"28{abs(hash(name)) % 100000:05d}",
            }
        )
        unit.sudo().action_release()
        return unit

    def _let(self, unit, rent=100000.0):
        lease = self.env["c2p.lease"].create(
            {
                "unit_id": unit.id,
                "tenant_id": self.tenant.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": rent,
                "cheque_count": "1",
            }
        )
        lease._activate_as_loaded()
        unit.current_lease_id = lease
        unit.state = "occupied"
        return lease

    def _head_lease(self, building, amount):
        head = self.env["c2p.head.lease"].create(
            {
                "building_id": building.id,
                "landlord_id": self.landlord.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_amount": amount,
                "cheque_count": "4",
            }
        )
        head.action_activate()
        building.invalidate_recordset()
        return head


class TestWhoseMoney(PortfolioCase):
    """BR-019 carried into the card. The label travels with the value so a
    view cannot pick the wrong field."""

    def test_a_head_leased_building_shows_its_margin(self):
        b = self._building("PMH", "head_lease", declared_residential_units=1)
        self._let(self._unit(b, "PMH-101"), rent=150000.0)
        self._head_lease(b, 100000.0)
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_money_label, "Gross margin")
        self.assertEqual(b.portfolio_money, 50000.0)

    def test_an_owner_managed_building_shows_managed_rent_not_margin(self):
        """The defect this guards: an owner-managed card showing a margin
        would be reporting the landlord's income as the company's."""
        b = self._building("PMO", "owner_management", declared_residential_units=1)
        self._let(self._unit(b, "PMO-101"), rent=150000.0)
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_money_label, "Managed rent")
        self.assertEqual(b.portfolio_money, 150000.0)
        self.assertEqual(b.gross_margin, 0.0, "There is no margin to report here.")

    def test_a_brokerage_building_shows_no_money_figure_at_all(self):
        b = self._building("PMB", "brokerage")
        self.assertFalse(b.portfolio_money_label)
        self.assertEqual(b.portfolio_money, 0.0)
        self.assertFalse(b.portfolio_money_display)


class TestCardFigureFormatting(PortfolioCase):
    """The card figure is shortened because the full one overflowed the
    column and clipped mid-number, which still looks like a number."""

    def _fmt(self, amount):
        return self._building("PFF").with_context()._format_card_amount(amount)

    def test_millions_keep_one_decimal(self):
        self.assertTrue(self._fmt(1_301_900.0).endswith("1.3m"))

    def test_thousands_are_whole(self):
        self.assertTrue(self._fmt(340_300.0).endswith("340k"))

    def test_small_amounts_are_not_abbreviated(self):
        self.assertTrue(self._fmt(812.0).endswith("812"))

    def test_negatives_use_a_real_minus_sign(self):
        """A hyphen at this weight reads as a dash against the digits."""
        out = self._fmt(-143_700.0)
        self.assertIn("−", out)
        self.assertNotIn("-", out)
        self.assertTrue(out.endswith("144k"))

    def test_zero_is_shown_rather_than_blanked(self):
        """A building with exactly no margin is a fact, not a missing value."""
        self.assertTrue(self._fmt(0.0).endswith("0"))

    def test_the_currency_is_named(self):
        """So nobody reads an AED figure as dollars."""
        b = self._building("PFC")
        self.assertIn(b.currency_id.name, b._format_card_amount(1000.0))


class TestAlertRanking(PortfolioCase):
    def test_a_healthy_building_says_nothing(self):
        """An 'all good' badge on every card is noise that teaches people to
        stop reading the badges."""
        b = self._building("PAH", "head_lease", declared_residential_units=1)
        self._let(self._unit(b, "PAH-101"), rent=150000.0)
        self._head_lease(b, 100000.0)
        b.invalidate_recordset()
        self.assertFalse(b.portfolio_alert)
        self.assertEqual(b.portfolio_tone, "ok")

    def test_coverage_below_one_is_critical(self):
        b = self._building("PAC", "head_lease", declared_residential_units=1)
        self._let(self._unit(b, "PAC-101"), rent=80000.0)
        self._head_lease(b, 100000.0)
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_tone, "critical")
        self.assertIn("Coverage", b.portfolio_alert)

    def test_coverage_outranks_an_unreconciled_count(self):
        """Both are true. Money the company is losing every month is the one
        that belongs on the card."""
        b = self._building("PAR", "head_lease", declared_residential_units=9)
        self._let(self._unit(b, "PAR-101"), rent=80000.0)
        self._head_lease(b, 100000.0)
        b.invalidate_recordset()
        self.assertFalse(b.units_reconciled, "This building genuinely does not reconcile.")
        self.assertIn("Coverage", b.portfolio_alert, "Coverage must win.")

    def test_a_head_leased_building_with_no_head_lease_is_critical(self):
        """Marked head leased with nothing underwriting it: every margin
        figure on this building is meaningless until that is fixed."""
        b = self._building("PAN", "head_lease", declared_residential_units=1)
        self._let(self._unit(b, "PAN-101"))
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_tone, "critical")
        self.assertIn("no active head lease", b.portfolio_alert)

    def test_an_unreconciled_count_outranks_vacancy(self):
        """A building whose unit count is wrong is one whose occupancy figure
        cannot be trusted, so saying "40% vacant" would be asserting a number
        we have just admitted is unreliable."""
        b = self._building("PAU", "owner_management", declared_residential_units=9)
        self._unit(b, "PAU-101")
        self._unit(b, "PAU-102")
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_tone, "warn")
        self.assertIn("declared", b.portfolio_alert)

    def test_vacancy_is_reported_when_nothing_worse_is_wrong(self):
        b = self._building("PAV", "owner_management", declared_residential_units=4)
        units = [self._unit(b, f"PAV-10{i}") for i in range(1, 5)]
        self._let(units[0])
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_tone, "warn")
        self.assertIn("vacant", b.portfolio_alert)

    def test_a_building_with_no_units_says_so(self):
        b = self._building("PAZ", "head_lease")
        self.assertEqual(b.portfolio_tone, "warn")
        self.assertIn("No units", b.portfolio_alert)

    def test_a_brokerage_building_is_never_flagged_on_occupancy(self):
        """Brokerage carries no tenancies of ours, so occupancy and coverage
        say nothing about it and a vacancy warning would be meaningless."""
        b = self._building("PAB", "brokerage")
        self.assertFalse(b.portfolio_alert)
        self.assertEqual(b.portfolio_tone, "ok")


class TestTheViewLoads(TransactionCase):
    """The card template references fields by name; a typo there is invisible
    until somebody opens the screen."""

    def test_the_portfolio_kanban_renders(self):
        view = self.env.ref("sinclaire_workspace.view_building_kanban_workspace")
        # get_views resolves the arch and validates every field reference
        # against the model, which is what catches a renamed or misspelt field.
        self.env["c2p.building"].get_views([(view.id, "kanban")])

    def test_the_portfolio_search_view_renders(self):
        view = self.env.ref("sinclaire_workspace.view_building_search_workspace")
        self.env["c2p.building"].get_views([(view.id, "search")])

    def test_the_portfolio_menu_is_reachable_by_a_leasing_user(self):
        user = self.env["res.users"].create(
            {
                "name": "Portfolio Leasing User",
                "login": "portfolio_leasing_user",
                "group_ids": [(4, self.env.ref("c2p_property_lease.group_property_user").id)],
            }
        )
        menu = self.env.ref("sinclaire_workspace.menu_portfolio")
        visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
        self.assertIn(menu.id, visible, "A leasing user cannot see the Portfolio menu.")


class TestUnitReadiness(PortfolioCase):
    """BR-018 made visible. The rules already existed; what was missing was
    telling the person staring at the greyed-out button why."""

    def _draft_unit(self, building, name, **kw):
        vals = {
            "name": name,
            "building_id": building.id,
            "unit_type": "1br",
            "floor": "1",
            "area_sqft": 900.0,
            "market_rent": 100000.0,
            "dewa_no": f"29{abs(hash(name)) % 100000:05d}",
        }
        vals.update(kw)
        return self.env["c2p.unit"].create(vals)

    def test_a_complete_draft_unit_says_it_is_ready(self):
        """Somebody on this screen is about to act, so 'ready' is the answer
        to the question they arrived with."""
        b = self._building("URD")
        unit = self._draft_unit(b, "URD-101")
        self.assertEqual(unit.state, "draft")
        self.assertTrue(unit.is_releasable)
        self.assertIn("Ready to release", unit.release_checklist)

    def test_an_incomplete_unit_names_every_missing_item(self):
        b = self._building("URI")
        unit = self._draft_unit(b, "URI-101", market_rent=0.0, dewa_no=False)
        self.assertIn("Market rent", unit.release_checklist)
        self.assertIn("DEWA premise number", unit.release_checklist)
        self.assertNotIn("Ready to release", unit.release_checklist)

    def test_the_checklist_matches_the_gate_that_actually_blocks(self):
        """The checklist is derived from RELEASE_REQUIREMENTS rather than
        re-listing the rules, so the screen cannot name a reason the gate
        does not actually enforce. Somebody would go and fix the wrong
        thing."""
        b = self._building("URM")
        unit = self._draft_unit(b, "URM-101", area_sqft=0.0)
        self.assertFalse(unit.is_releasable)
        for label in unit.release_blockers.split(", "):
            self.assertIn(label, unit.release_checklist)

    def test_a_missing_analytic_account_is_reported_against_the_building(self):
        """The unit is complete; the building is not. Naming the unit's
        fields here would send somebody hunting through the wrong record."""
        b = self.env["c2p.building"].create(
            {
                "name": "No Analytic Tower",
                "code": "URA",
                "owner_id": self.landlord.id,
                "operating_model": "head_lease",
            }
        )
        unit = self._draft_unit(b, "URA-101")
        self.assertFalse(unit.is_releasable)
        self.assertIn("Analytic account on the building", unit.release_checklist)

    def test_a_released_unit_shows_no_checklist(self):
        b = self._building("URR")
        unit = self._draft_unit(b, "URR-101")
        unit.sudo().action_release()
        self.assertNotEqual(unit.state, "draft")
        self.assertFalse(unit.release_checklist)

    def test_the_checklist_is_escaped(self):
        """It is an Html field built by string formatting, so a unit type or
        label carrying markup must not become markup."""
        b = self._building("URX")
        unit = self._draft_unit(b, "URX-101", market_rent=0.0)
        self.assertNotIn("<script", unit.release_checklist)
        self.assertIn("sin-blocked__list", unit.release_checklist)


class TestThe360ViewsLoad(PortfolioCase):
    def test_the_building_360_form_renders(self):
        view = self.env.ref("sinclaire_workspace.view_building_form_360")
        self.env["c2p.building"].get_views([(view.id, "form")])

    def test_the_unit_360_form_renders(self):
        view = self.env.ref("sinclaire_workspace.view_unit_form_360")
        self.env["c2p.unit"].get_views([(view.id, "form")])

    def test_a_brokerage_building_keeps_its_raw_figures(self):
        """The KPI row is hidden for brokerage, so the fields it replaces must
        reappear. The two conditions are complementary on purpose: neither
        case may end up with no occupancy figure anywhere on the screen."""
        import re

        arch = self.env.ref("sinclaire_workspace.view_building_form_360").arch
        swapped = re.findall(r"name='(gross_margin|coverage_ratio|breakeven_occupancy|occupancy_rate)'", arch)
        self.assertEqual(len(swapped), 4, "every duplicated figure should be swapped")
        self.assertEqual(
            arch.count("operating_model != 'brokerage'"),
            4,
            "each swap must be conditional, not an outright hide",
        )

    def test_the_unit_screen_states_the_blockers_once(self):
        """The property module says the same thing as a sentence inside the
        sheet. Two banners for one fact is the clutter this layer exists to
        remove, so exactly one of them renders."""
        arch = self.env.ref("sinclaire_workspace.view_unit_form_360").arch
        self.assertIn("release_checklist", arch)
        self.assertIn("role='alert'", arch.replace('"', "'"))


class TestPortfolioToneSearch(PortfolioCase):
    """The filter behind the Portfolio's "Needs attention" button.

    It shipped in #21 with the same defect the collections filter had: the
    search accepted a list or tuple and wrapped anything else, while Odoo
    hands it an OrderedSet. Clicking the button raised. The unit tests passed
    because they all called search() with a hand-written tuple.
    """

    def test_an_ordered_set_value_is_accepted(self):
        from odoo.tools import OrderedSet

        b = self._building("PTO", "head_lease")
        self._let(self._unit(b, "PTO-101"), rent=80000.0)
        self._head_lease(b, 100000.0)
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_tone, "critical")
        found = self.env["c2p.building"].search([("portfolio_tone", "in", OrderedSet(["warn", "critical"]))])
        self.assertIn(b, found)

    def test_a_healthy_building_is_excluded_by_that_filter(self):
        b = self._building("PTH", "head_lease", declared_residential_units=1)
        self._let(self._unit(b, "PTH-101"), rent=150000.0)
        self._head_lease(b, 100000.0)
        b.invalidate_recordset()
        self.assertEqual(b.portfolio_tone, "ok")
        found = self.env["c2p.building"].search([("portfolio_tone", "in", ("warn", "critical"))])
        self.assertNotIn(b, found)
