"""BR-098: the tenancy event register, and the limit BR-099 puts on it.

Two kinds of test here, and the second kind matters more.

The first kind checks the register works: the transition table, the reason
rules, the evidence rule on a referral, the overdue flag.

The second kind checks the register **does not act**. BR-099 says warnings,
breach notices, non-renewals and terminations follow an approved workflow with
legal review, and that "the system must not make legal decisions on its own".
A register that quietly starts blocking renewals is the most likely way this
module goes wrong, because the gate would look like a feature to whoever added
it. Those tests fail the moment somebody wires one up - which is the point.
"""

from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.addons.c2p_property_lease.models.tenancy_event import ADVERSE_SERIOUSNESS
from odoo.addons.c2p_property_lease.models.tenancy_event import DEADLINE_ALERT_SUMMARY
from odoo.addons.c2p_property_lease.models.tenancy_event import EVENT_CATEGORIES
from odoo.addons.c2p_property_lease.models.tenancy_event import EVENT_STATES
from odoo.addons.c2p_property_lease.models.tenancy_event import EVENT_TRANSITIONS
from odoo.addons.c2p_property_lease.models.tenancy_event import OPEN_STATES
from odoo.addons.c2p_property_lease.models.tenancy_event import REASON_REQUIRED
from odoo.addons.c2p_property_lease.models.tenancy_event import SERIOUSNESS_LEVELS
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TenancyEventCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Event Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Event Tenant"})
        cls.plan = cls.env["account.analytic.plan"].create({"name": "Event Properties"})
        cls.today = fields.Date.context_today(cls.env.user)

    def _lease(self, code, start=None, end=None):
        building = self.env["c2p.building"].create(
            {
                "name": f"{code} Tower",
                "code": code,
                "owner_id": self.landlord.id,
                "operating_model": "head_lease",
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
                "market_rent": 120000.0,
                "dewa_no": f"80{abs(hash(code)) % 100000:05d}",
            }
        )
        unit.sudo().action_release()
        return self.env["c2p.lease"].create(
            {
                "unit_id": unit.id,
                "tenant_id": self.tenant.id,
                "date_start": start or fields.Date.to_string(self.today - timedelta(days=200)),
                "date_end": end or fields.Date.to_string(self.today + timedelta(days=165)),
                "annual_rent": 120000.0,
                "cheque_count": "4",
            }
        )

    def _event(self, lease, **kw):
        vals = {
            "lease_id": lease.id,
            "summary": "Noise after midnight, third time",
            "category": "disturbance",
            "seriousness": "medium",
        }
        vals.update(kw)
        return self.env["c2p.tenancy.event"].create(vals)

    def _renew(self, lease):
        """Drive the real renewal wizard; it requires the new terms."""
        wizard = self.env["c2p.lease.renew"].create(
            {
                "lease_id": lease.id,
                "new_rent": lease.annual_rent,
                "date_start": lease.date_end + timedelta(days=1),
                "date_end": lease.date_end + timedelta(days=366),
            }
        )
        wizard.action_renew()
        return self.env["c2p.lease"].search([("renewed_from_id", "=", lease.id)], limit=1)

    def _evidence(self, event):
        return self.env["ir.attachment"].create(
            {
                "name": "complaint.pdf",
                "raw": b"a neighbour's written complaint",
                "res_model": event._name,
                "res_id": event.id,
            }
        )


class TestTheRegisterRecords(TenancyEventCase):
    def test_an_event_takes_every_field_br_098_asks_for(self):
        """BRD §5.3 lists them; a missing one means a report cannot be built."""
        lease = self._lease("EAA")
        event = self._event(
            lease,
            event_date=self.today,
            seriousness="high",
            responsible_user_id=self.env.user.id,
            deadline=self.today + timedelta(days=7),
            action_taken="Spoke to the tenant, written warning drafted.",
            renewal_impact="monitor",
            description="Two neighbours complained on the same night.",
        )
        for field in (
            "event_date",
            "category",
            "seriousness",
            "responsible_user_id",
            "deadline",
            "action_taken",
            "renewal_impact",
        ):
            with self.subTest(field=field):
                self.assertTrue(event[field], f"{field} did not survive the write")
        self.assertTrue(event.name.startswith("EVT/"), "the event did not take a sequence")

    def test_the_tenant_is_stored_so_a_tenant_s_history_can_be_searched(self):
        """A non-stored related field cannot appear in a search domain at all,
        and the dossier and every report group by tenant."""
        lease = self._lease("EAB")
        event = self._event(lease)
        self.assertEqual(event.tenant_id, self.tenant)
        found = self.env["c2p.tenancy.event"].search([("tenant_id", "=", self.tenant.id)])
        self.assertIn(event, found)

    def test_an_event_cannot_predate_the_tenancy_it_is_filed_against(self):
        """Otherwise it surfaces in the wrong tenant's dossier and the wrong
        renewal pack - it is the wrong tenancy or a typo, either way."""
        lease = self._lease("EAC", start=fields.Date.to_string(self.today - timedelta(days=30)))
        with self.assertRaises(ValidationError):
            self._event(lease, event_date=self.today - timedelta(days=90))

    def test_a_deadline_cannot_fall_before_the_event(self):
        """A models.Constraint, not _sql_constraints: v19 ignores the latter
        silently, so the old spelling would let the row through."""
        lease = self._lease("EAD")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self._event(
                lease,
                event_date=self.today,
                deadline=self.today - timedelta(days=1),
            )
            self.env.flush_all()


class TestWhenAnEventMayBeDated(TenancyEventCase):
    """The date rule refuses the wrong tenancy, not merely an early date."""

    def test_an_event_before_the_tenancy_starts_is_allowed(self):
        """A missing deposit or document is chased between signature and start.

        That is a category this model offers and the commonest thing anybody
        records before a tenancy begins. Refusing it would force the recorder
        to post-date the event, and event_date means when it happened.
        """
        lease = self._lease("EHA", start=fields.Date.to_string(self.today + timedelta(days=20)))
        event = self._event(
            lease,
            category="missing_document",
            summary="Deposit cheque documents not provided",
            event_date=self.today,
        )
        self.assertEqual(event.state, "open")
        self.assertEqual(event.event_date, self.today)

    def test_an_event_dated_inside_another_tenancy_of_the_unit_is_refused(self):
        """That incident belongs to whoever had the unit at the time, and left
        here it would surface in the wrong tenant's dossier."""
        first = self._lease(
            "EHB",
            start=fields.Date.to_string(self.today - timedelta(days=400)),
            end=fields.Date.to_string(self.today - timedelta(days=40)),
        )
        successor = self.env["c2p.lease"].create(
            {
                "unit_id": first.unit_id.id,
                "tenant_id": self.tenant.id,
                "date_start": fields.Date.to_string(self.today - timedelta(days=39)),
                "date_end": fields.Date.to_string(self.today + timedelta(days=325)),
                "annual_rent": 120000.0,
                "cheque_count": "4",
            }
        )
        with self.assertRaises(ValidationError):
            self._event(successor, event_date=self.today - timedelta(days=200))


class TestTheTransitionTable(TenancyEventCase):
    def test_every_transition_names_a_state_the_model_has(self):
        """The table and the selection must agree, and nothing else asserts it.

        This is the shape that has caused six defects in this repository: two
        structures that must agree about a set of values. Here the test is the
        thing that makes them.
        """
        known = {state for state, _label in EVENT_STATES}
        self.assertEqual(set(EVENT_TRANSITIONS), known, "a state has no row in the transition table")
        for source, targets in EVENT_TRANSITIONS.items():
            for target in targets:
                with self.subTest(move=f"{source}->{target}"):
                    self.assertIn(target, known, f"{source} can move to {target}, which is not a state")

    def test_every_reason_required_move_is_an_allowed_move(self):
        """A reason rule on a move that cannot happen is dead code pretending
        to be a control."""
        for source, target in REASON_REQUIRED:
            with self.subTest(move=f"{source}->{target}"):
                self.assertIn(
                    target,
                    EVENT_TRANSITIONS.get(source, ()),
                    f"{source} -> {target} needs a reason but is not an allowed move",
                )

    def test_every_open_state_is_a_state(self):
        known = {state for state, _label in EVENT_STATES}
        self.assertTrue(set(OPEN_STATES) <= known)

    def test_every_adverse_level_is_a_level(self):
        known = {level for level, _label in SERIOUSNESS_LEVELS}
        self.assertTrue(set(ADVERSE_SERIOUSNESS) <= known)

    def test_the_categories_cover_the_brd_list(self):
        """BRD §5.3 names these. A category that is missing gets recorded in a
        notes field instead, and then the register is a lie about what
        happened."""
        keys = {key for key, _label in EVENT_CATEGORIES}
        for required in (
            "complaint",
            "disturbance",
            "subletting",
            "utility",
            "missing_document",
            "maintenance",
            "breach",
            "warning",
            "legal",
        ):
            with self.subTest(category=required):
                self.assertIn(required, keys)

    def test_a_move_outside_the_table_is_refused(self):
        lease = self._lease("EBA")
        event = self._event(lease)
        event.action_resolve(result="The tenant stopped; no further complaints.")
        # Resolved goes back to Being Actioned only; straight to Closed is not
        # a row in the table.
        with self.assertRaises(UserError):
            event.action_close(reason="tidying up")

    def test_the_status_field_cannot_be_written_directly(self):
        """`state` is writable and a statusbar writes it, so a guard that sits
        only in the action guards nothing - the same lesson as the lease and
        the payment."""
        lease = self._lease("EBB")
        event = self._event(lease)
        with self.assertRaises(UserError):
            event.state = "resolved"

    def test_a_reversal_without_a_reason_is_refused(self):
        """Resolving needs no reason; un-resolving does. The matrix marks every
        backward move reason-mandatory because the original row stays in the
        history and has to be explained."""
        lease = self._lease("EBC")
        event = self._event(lease)
        event.action_start()
        event.action_resolve(result="The tenant stopped; no further complaints.")
        self.assertEqual(event.state, "resolved")
        with self.assertRaises(UserError):
            event.action_reopen()
        event.action_reopen(reason="The tenant complained again the same week.")
        self.assertEqual(event.state, "in_progress")

    def test_closing_without_action_needs_a_reason(self):
        lease = self._lease("EBD")
        event = self._event(lease)
        with self.assertRaises(UserError):
            event.action_close()
        event.action_close(reason="Duplicate of the earlier complaint.")
        self.assertEqual(event.state, "closed")

    def test_every_move_leaves_a_history_row(self):
        """BRD §3.2: no status is overwritten without history."""
        lease = self._lease("EBE")
        event = self._event(lease)
        before = len(event.message_ids)
        event.action_start()
        self.assertGreater(len(event.message_ids), before)


class TestTheResultRule(TenancyEventCase):
    def test_resolving_without_a_result_is_refused(self):
        """BR-098 lists "result", and Resolved is the state that claims there
        was one. Without this an event could sit at Resolved saying it was
        dealt with and refusing to say how."""
        lease = self._lease("EIA")
        event = self._event(lease)
        with self.assertRaises(UserError):
            event.action_resolve()
        event.action_resolve(result="Spoke to both parties; no repeat.")
        self.assertEqual(event.state, "resolved")
        self.assertTrue(event.result)

    def test_closing_without_action_needs_no_result(self):
        """It concludes with a reason instead, and has no result by
        definition."""
        lease = self._lease("EIB")
        event = self._event(lease)
        event.action_close(reason="Duplicate of an earlier complaint.")
        self.assertEqual(event.state, "closed")
        self.assertFalse(event.result)


class TestTheEvidenceRule(TenancyEventCase):
    def test_a_referral_without_evidence_is_refused(self):
        """BR-099 requires evidence and legal review for the notices that
        follow a referral, so referring with nothing attached is refused.

        This is the only mandatory-evidence rule the BRD itself supplies. Any
        other threshold is OD-06 and is deliberately not invented.
        """
        lease = self._lease("ECA")
        event = self._event(lease, seriousness="critical", category="breach")
        with self.assertRaises(UserError):
            event.action_refer(reason="Needs legal review.")

    def test_a_referral_with_evidence_is_allowed(self):
        lease = self._lease("ECB")
        event = self._event(lease, seriousness="critical", category="breach")
        event.attachment_ids = [(4, self._evidence(event).id)]
        event.action_refer(reason="Needs legal review.")
        self.assertEqual(event.state, "referred")
        self.assertTrue(event.has_evidence)
        self.assertEqual(event.evidence_count, 1)

    def test_the_evidence_rule_ignores_the_context_key(self):
        """The key exists so an action can write a history row. It is not a way
        past a rule, or the bypass just moves one layer down - the same
        decision as the cheque-exception approver check.
        """
        from odoo.addons.c2p_property_lease.models.tenancy_event import STATE_MOVE_CONTEXT_KEY

        lease = self._lease("ECC")
        event = self._event(lease, category="breach")
        with self.assertRaises(UserError):
            event.with_context(**{STATE_MOVE_CONTEXT_KEY: True}).write({"state": "referred"})


class TestTheOverdueFlag(TenancyEventCase):
    def test_an_open_event_past_its_deadline_is_overdue(self):
        lease = self._lease("EDA")
        event = self._event(
            lease,
            event_date=self.today - timedelta(days=20),
            deadline=self.today - timedelta(days=5),
        )
        self.assertTrue(event.is_overdue)

    def test_a_concluded_event_is_not_overdue_however_late_it_was(self):
        """An event that was dealt with late is history, not a task."""
        lease = self._lease("EDB")
        event = self._event(
            lease,
            event_date=self.today - timedelta(days=20),
            deadline=self.today - timedelta(days=5),
        )
        event.action_resolve(result="The tenant stopped; no further complaints.")
        self.assertFalse(event.is_overdue)

    def test_the_overdue_flag_is_searchable(self):
        """Stored, because a filter on a non-stored compute cannot exist and a
        collections-style screen filters on exactly this."""
        lease = self._lease("EDC")
        event = self._event(
            lease,
            event_date=self.today - timedelta(days=20),
            deadline=self.today - timedelta(days=5),
        )
        self.assertIn(event, self.env["c2p.tenancy.event"].search([("is_overdue", "=", True)]))

    def test_the_cron_refreshes_a_flag_that_went_stale_on_its_own(self):
        """The case the cron exists for, and the one the others miss.

        `is_overdue` is stored and its depends hold no date, so a deadline that
        simply passes marks nothing dirty. The other tests here create events
        already overdue, so the compute runs at create and they would pass with
        no cron at all. This one makes the flag genuinely stale - the deadline
        moves into the past behind the ORM's back - and then asserts the cron
        puts it right, because the "Past deadline" filter reads the stored
        value and nothing else repairs it.
        """
        lease = self._lease("EDE")
        event = self._event(
            lease,
            event_date=self.today - timedelta(days=5),
            deadline=self.today + timedelta(days=3),
            responsible_user_id=self.env.user.id,
        )
        self.assertFalse(event.is_overdue)

        self.env.cr.execute(
            "UPDATE c2p_tenancy_event SET deadline = %s WHERE id = %s",
            (self.today - timedelta(days=1), event.id),
        )
        event.invalidate_recordset(["deadline"])
        self.assertFalse(event.is_overdue, "the stored flag was expected to be stale at this point")

        self.env["c2p.tenancy.event"]._cron_event_deadline_alerts()
        self.assertTrue(event.is_overdue, "the cron did not refresh the stored flag")
        self.assertIn(
            event,
            self.env["c2p.tenancy.event"].search([("is_overdue", "=", True)]),
            "the overdue filter still cannot see an event whose deadline has passed",
        )

    def test_an_unrelated_activity_does_not_silence_the_deadline_alert(self):
        """The duplicate guard matches this alert, not merely its owner.

        Matching on the owner alone meant any to-do somebody had scheduled on
        the event silenced the deadline alert - the one thing the cron sends.
        """
        lease = self._lease("EDF")
        event = self._event(
            lease,
            event_date=self.today - timedelta(days=20),
            deadline=self.today - timedelta(days=5),
            responsible_user_id=self.env.user.id,
        )
        event.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=self.env.user.id,
            summary="Call the tenant back",
        )
        self.env["c2p.tenancy.event"]._cron_event_deadline_alerts()
        self.assertIn(
            DEADLINE_ALERT_SUMMARY,
            event.activity_ids.mapped("summary"),
            "an unrelated activity suppressed the past-deadline alert",
        )

    def test_the_cron_raises_one_activity_per_overdue_event(self):
        lease = self._lease("EDD")
        event = self._event(
            lease,
            event_date=self.today - timedelta(days=20),
            deadline=self.today - timedelta(days=5),
            responsible_user_id=self.env.user.id,
        )
        self.env["c2p.tenancy.event"]._cron_event_deadline_alerts()
        self.assertTrue(event.activity_ids, "no follow-up was raised on an overdue event")
        raised = len(event.activity_ids)
        self.env["c2p.tenancy.event"]._cron_event_deadline_alerts()
        self.assertEqual(len(event.activity_ids), raised, "the cron raised a duplicate follow-up")


class TestTheRegisterDoesNotDecide(TenancyEventCase):
    """BR-099: "the system must not make legal decisions on its own."

    Every test here asserts an absence. They exist because the gate they forbid
    is the single most plausible thing for somebody to add later in good faith.
    """

    def _adverse(self, lease):
        event = self._event(
            lease,
            seriousness="critical",
            category="breach",
            renewal_impact="oppose",
            event_date=self.today - timedelta(days=5),
        )
        event.attachment_ids = [(4, self._evidence(event).id)]
        event.action_refer(reason="Referred for legal review.")
        return event

    def test_an_adverse_event_does_not_block_activation(self):
        lease = self._lease("EEA")
        self._adverse(lease)
        lease._activate_as_loaded()
        self.assertEqual(lease.state, "active")

    def test_an_adverse_event_does_not_block_a_renewal(self):
        """A recommendation of non-renewal is advice to a person, not a veto."""
        lease = self._lease("EEB")
        lease._activate_as_loaded()
        event = self._adverse(lease)
        self.assertEqual(event.renewal_impact, "oppose")
        self.assertTrue(
            self._renew(lease),
            "a successor tenancy was not created, so an event blocked the renewal",
        )

    def test_an_adverse_event_does_not_block_a_termination(self):
        lease = self._lease("EEC")
        lease._activate_as_loaded()
        self._adverse(lease)
        lease.action_give_notice()
        self.assertEqual(lease.state, "notice")

    def test_the_lease_exposes_counts_and_no_verdict(self):
        """No `has_blocking_event`, no `renewal_allowed`. The lease counts the
        events and says nothing about what they mean."""
        lease = self._lease("EED")
        self._adverse(lease)
        self.assertEqual(lease.event_count, 1)
        self.assertEqual(lease.open_adverse_event_count, 1)
        for forbidden in ("has_blocking_event", "renewal_allowed", "is_renewable", "event_verdict"):
            with self.subTest(field=forbidden):
                self.assertNotIn(
                    forbidden,
                    lease._fields,
                    f"c2p.lease grew {forbidden} - BR-099 keeps that decision with a person",
                )

    def test_renewal_impact_is_advisory_on_every_value(self):
        """Walks the whole selection rather than testing the worst one, so a
        value added later is covered without anybody remembering to."""
        from odoo.addons.c2p_property_lease.models.tenancy_event import RENEWAL_IMPACTS

        for impact, _label in RENEWAL_IMPACTS:
            with self.subTest(impact=impact):
                lease = self._lease(f"EF{impact[:1].upper()}{len(impact)}")
                lease._activate_as_loaded()
                self._event(lease, seriousness="critical", renewal_impact=impact)
                self.assertTrue(self._renew(lease), f"renewal_impact={impact} blocked a renewal")


class TestTheRenewalDoesNotInheritHistory(TenancyEventCase):
    def test_a_renewal_does_not_carry_the_previous_tenancy_s_events(self):
        """An incident belongs to the tenancy it happened under.

        Copied forward, last year's complaints would arrive on the successor
        dated before it began - which the event's own constraint then refuses,
        so the renewal would fail outright rather than merely misreport.
        """
        lease = self._lease("EGA")
        lease._activate_as_loaded()
        self._event(lease, event_date=self.today - timedelta(days=10))
        successor = self._renew(lease)
        self.assertTrue(successor)
        self.assertEqual(successor.event_count, 0, "the renewal inherited the previous tenancy's events")
        self.assertEqual(lease.event_count, 1, "the original lost its own event")
