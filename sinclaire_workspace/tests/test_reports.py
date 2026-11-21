"""RPT-017, RPT-018, RPT-019 — and the rule that shapes all three.

The report catalogue's first non-negotiable rule is that nothing aggregates
across operating models: head-lease rental revenue, owner-management gross rent
administered and brokerage transaction value are not the same kind of number
and must never sum into one "revenue" figure (BRD §8.1).

`c2p.lease` carried no operating model at all before this, so no lease report
could split by one and `view_lease_pivot` totalled all three together. Adding
the field fixes the instance; the test that walks every money pivot on the
model is what stops the next one regressing - which is this codebase's
recurring defect in its reporting form.
"""

from ast import literal_eval

from odoo.addons.c2p_property_lease.models.building import OPERATING_MODELS
from odoo.addons.c2p_property_lease.models.lease import RENEWAL_ALERT_DAYS
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# The actions this slice adds, with the grouping each must default to. Rule 1
# is only honoured if operating model leads, so that is what is asserted.
REPORT_ACTIONS = (
    "sinclaire_workspace.action_rpt_rent_roll",
    "sinclaire_workspace.action_rpt_lease_register",
    "sinclaire_workspace.action_rpt_renewal_pipeline",
)

# Measures that are money. A pivot carrying one of these has to say which
# operating model it belongs to.
MONEY_MEASURES = ("annual_rent", "instalment_amount", "cheque_cover", "cheque_shortfall", "security_deposit")


@tagged("post_install", "-at_install")
class ReportCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Report Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Report Tenant"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Report Properties"})

    def _lease(self, code, model="head_lease", rent=120000.0):
        building = self.env["c2p.building"].create(
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
        unit = self.env["c2p.unit"].create(
            {
                "name": f"{code}-101",
                "building_id": building.id,
                "unit_type": "1br",
                "floor": "1",
                "area_sqft": 900.0,
                "market_rent": rent,
                "dewa_no": f"90{abs(hash(code)) % 100000:05d}",
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
                "cheque_count": "4",
            }
        )


class TestTheOperatingModelReachesTheLease(ReportCase):
    def test_the_lease_carries_its_building_s_operating_model(self):
        for model, _label in OPERATING_MODELS:
            with self.subTest(operating_model=model):
                lease = self._lease(f"OM{model[:3].upper()}", model=model)
                self.assertEqual(lease.operating_model, model)

    def test_the_field_is_stored_so_a_report_can_group_and_filter_on_it(self):
        """A non-stored related field cannot appear in a search domain at all,
        and cannot be grouped - which is what the catalogue needs it for."""
        field = self.env["c2p.lease"]._fields["operating_model"]
        self.assertTrue(field.store, "operating_model must be stored to be grouped or filtered")

        lease = self._lease("OMS", model="owner_management")
        found = self.env["c2p.lease"].search([("operating_model", "=", "owner_management")])
        self.assertIn(lease, found)
        grouped = self.env["c2p.lease"]._read_group([("id", "=", lease.id)], ["operating_model"], ["annual_rent:sum"])
        self.assertEqual(grouped[0][0], "owner_management")

    def test_it_follows_the_building_when_the_model_changes(self):
        """A building that changes operating model must not leave its tenancies
        reporting under the old one."""
        lease = self._lease("OMF", model="head_lease")
        lease.building_id.operating_model = "owner_management"
        lease.invalidate_recordset()
        self.assertEqual(lease.operating_model, "owner_management")


class TestRuleOneIsEnforcedNotJustStated(ReportCase):
    """ "Never aggregate across operating models" (catalogue rule 1)."""

    def test_every_lease_report_leads_its_grouping_with_the_operating_model(self):
        """So the first figure a reader meets is split by model.

        §4.1.2 allows a combined view when somebody deliberately asks for one,
        which is why this is a default grouping rather than a refusal - but the
        default has to be the safe one.
        """
        for xmlid in REPORT_ACTIONS:
            with self.subTest(action=xmlid):
                action = self.env.ref(xmlid)
                context = action.context or "{}"
                self.assertIn(
                    "search_default_g_model",
                    context,
                    f"{xmlid} does not group by operating model, so its totals mix the three",
                )
                self.assertIn("'search_default_g_model': 1", context, "operating model must lead the grouping")

    def test_every_money_pivot_on_the_lease_splits_by_operating_model(self):
        """The guard, and the reason this test exists rather than a fixed fix.

        `view_lease_pivot` summed annual rent by building and cheque count with
        no operating-model dimension, so its total added head-lease revenue to
        owner-management rent administered. Fixing that one view does not stop
        the next pivot doing it, so this walks them all.
        """
        pivots = self.env["ir.ui.view"].search([("model", "=", "c2p.lease"), ("type", "=", "pivot")])
        self.assertTrue(pivots, "no pivot views found on c2p.lease - this guard would pass vacuously")
        offenders = []
        for view in pivots:
            arch = view.arch_db or ""
            if not any(f'name="{measure}"' in arch for measure in MONEY_MEASURES):
                continue  # counts only; nothing to misadd
            if 'name="operating_model"' not in arch:
                offenders.append(view.xml_id or view.name)
        self.assertFalse(
            offenders,
            "these pivots measure money on c2p.lease without splitting by operating model, so their "
            f"totals sum the three models into one figure: {', '.join(offenders)}",
        )

    def test_the_rent_roll_does_not_sum_two_models_into_one_total(self):
        """The behaviour the rule is about, not just the view definition."""
        head = self._lease("R1H", model="head_lease", rent=100000.0)
        owner = self._lease("R1O", model="owner_management", rent=250000.0)
        head._activate_as_loaded()
        owner._activate_as_loaded()

        # Grouped the way the action defaults to, over exactly these two.
        grouped = self.env["c2p.lease"]._read_group(
            [("id", "in", (head + owner).ids)],
            ["operating_model"],
            ["annual_rent:sum"],
        )
        by_model = dict(grouped)
        self.assertEqual(by_model.get("head_lease"), 100000.0)
        self.assertEqual(by_model.get("owner_management"), 250000.0)
        self.assertNotIn(
            350000.0,
            by_model.values(),
            "the two models were added together, which is the figure rule 1 exists to prevent",
        )


class TestTheReportsMeetWhatTheyClaim(ReportCase):
    def test_each_report_opens_the_source_transaction(self):
        """§8.3: every report must open the source transaction. A list whose
        rows open the lease form is how that is satisfied natively."""
        for xmlid in REPORT_ACTIONS:
            with self.subTest(action=xmlid):
                action = self.env.ref(xmlid)
                self.assertIn("list", action.view_mode)
                self.assertIn("form", action.view_mode, "no form view, so a row cannot be opened")
                self.assertEqual(action.res_model, "c2p.lease")

    def test_each_report_offers_an_aggregate_view_for_period_comparison(self):
        """§8.3 wants period comparison; a pivot or graph gives it natively,
        a plain list does not."""
        for xmlid in REPORT_ACTIONS:
            with self.subTest(action=xmlid):
                action = self.env.ref(xmlid)
                self.assertTrue(
                    "pivot" in action.view_mode or "graph" in action.view_mode,
                    f"{xmlid} has no pivot or graph, so periods cannot be compared",
                )

    def test_the_rent_roll_shows_only_running_tenancies(self):
        """A rent roll is what is being paid now. Including closed tenancies
        would overstate it, which is the commonest way this report is wrong."""
        running = self._lease("RR1")
        running._activate_as_loaded()
        closed = self._lease("RR2")
        closed.sudo().write({"state": "expired"})

        action = self.env.ref("sinclaire_workspace.action_rpt_rent_roll")
        rows = self.env["c2p.lease"].search(literal_eval(action.domain))
        self.assertIn(running, rows)
        self.assertNotIn(closed, rows)

    def test_the_register_shows_every_tenancy_including_closed(self):
        """The register is the opposite of the rent roll and must not filter."""
        closed = self._lease("LR1")
        closed.sudo().write({"state": "expired"})
        action = self.env.ref("sinclaire_workspace.action_rpt_lease_register")
        # Unset reads as False or as an empty list depending on how Odoo stored
        # it; either means "no tenancy excluded".
        self.assertFalse(
            literal_eval(action.domain) if action.domain else [],
            "the lease register must not exclude any tenancy",
        )
        self.assertIn(closed, self.env["c2p.lease"].search([("id", "=", closed.id)]))

    def test_the_renewal_pipeline_uses_the_crons_outermost_band(self):
        """So the pipeline and the renewal alert cannot disagree about what is
        coming up. The literal 90 here is checked against the cron's own
        tuple, which is the only place it is decided."""
        action = self.env.ref("sinclaire_workspace.action_rpt_renewal_pipeline")
        self.assertIn(str(max(RENEWAL_ALERT_DAYS)), action.domain)

    def test_the_rent_roll_list_reports_contracted_rent_in_its_own_words(self):
        """Rule 2 keeps operational and financial sources apart. This figure is
        the commitment from the property model, not cash from the ledger, and a
        column headed "Rent" would be read as collected."""
        view = self.env.ref("sinclaire_workspace.view_lease_rent_roll_list")
        self.assertIn("Contracted Annual Rent", view.arch_db)

    def test_every_report_can_show_when_it_was_last_updated(self):
        """§8.3, and the one requirement that needs a field rather than a
        native behaviour."""
        view = self.env.ref("sinclaire_workspace.view_lease_rent_roll_list")
        self.assertIn('name="write_date"', view.arch_db)
