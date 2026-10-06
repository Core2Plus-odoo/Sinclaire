"""BR-075: a tenancy may not start with its cheques missing.

BRD §5.1 permits it only under a case-by-case exception approved by the Leasing
Manager or CEO. The tests here cover the refusal, the exception that lifts it,
the two rules on who may approve, and the follow-up that closes the loop.

The refusal tests need no cheques, so they always run. The ones that prove a
*complete* set lets a lease through need a bank journal with an inbound payment
method, which a database without accounting configured does not have; those
skip, following the existing convention in test_lease.py.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestChequeException(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "Exception Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "Exception Tenant"})
        cls.building = cls.env["c2p.building"].create(
            {"name": "Exception Tower", "code": "EXC", "owner_id": cls.landlord.id}
        )
        cls.manager = new_test_user(
            cls.env,
            login="c2p_exc_manager",
            groups="c2p_property_lease.group_property_manager",
            name="Exception Manager",
        )
        cls.agent = new_test_user(
            cls.env,
            login="c2p_exc_agent",
            groups="c2p_property_lease.group_property_user",
            name="Exception Agent",
        )

    def _unit(self, name):
        return self.env["c2p.unit"].create({"name": name, "building_id": self.building.id})

    def _lease(self, name, **kw):
        vals = {
            "tenant_id": self.tenant.id,
            "unit_id": self._unit(name).id,
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "annual_rent": 120000.0,
            "cheque_count": "4",
        }
        vals.update(kw)
        return self.env["c2p.lease"].create(vals)

    def _request(self, lease, requested_by=None):
        values = {
            "lease_id": lease.id,
            "reason": "Tenant relocating from abroad; two cheques follow on arrival.",
            "conditions": "Remaining cheques before the second instalment falls due.",
            "deadline": fields.Date.context_today(self.env.user) + timedelta(days=14),
            "responsible_user_id": self.agent.id,
        }
        model = self.env["c2p.lease.cheque.exception"]
        if requested_by:
            model = model.with_user(requested_by)
        return model.create(values)

    def _cheque_journal(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            return None
        return journal

    def _register_cheques(self, lease, count=None, amount=None, pdc_state="held"):
        """Create the cheque instruments for a lease the way the register does."""
        journal = self._cheque_journal()
        if not journal:
            self.skipTest("no bank journal with an inbound payment method")
        count = count if count is not None else int(lease.cheque_count)
        amount = amount if amount is not None else lease.instalment_amount
        Payment = self.env["account.payment"]
        for i in range(count):
            Payment.create(
                {
                    "partner_id": lease.tenant_id.id,
                    "partner_type": "customer",
                    "payment_type": "inbound",
                    "amount": amount,
                    "date": lease.date_start,
                    "journal_id": journal.id,
                    "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
                    "company_id": lease.company_id.id,
                    "lease_id": lease.id,
                    "cheque_no": f"{900000 + i}",
                    "cheque_bank": "Test Bank",
                    "maturity_date": lease.date_start,
                    "pdc_state": pdc_state,
                }
            )
        lease.invalidate_recordset()
        return lease

    # --------------------------------------------------------------- the refusal
    def test_a_lease_with_no_cheques_is_not_complete(self):
        lease = self._lease("EXC-101")
        self.assertEqual(lease.cheques_expected, 4)
        self.assertEqual(lease.cheques_received, 0)
        self.assertFalse(lease.cheques_complete)
        self.assertAlmostEqual(lease.cheque_shortfall, 120000.0, places=2)

    def test_activation_is_refused_without_the_cheques(self):
        lease = self._lease("EXC-102")
        with self.assertRaises(UserError) as caught:
            lease.action_activate()
        self.assertIn("cheque", str(caught.exception).lower())
        self.assertEqual(lease.state, "draft")
        self.assertNotEqual(lease.unit_id.state, "occupied")

    def test_the_refusal_names_the_shortfall(self):
        """An error that does not say what is missing sends the user hunting."""
        lease = self._lease("EXC-103", annual_rent=80000.0, cheque_count="2")
        with self.assertRaises(UserError) as caught:
            lease.action_activate()
        message = str(caught.exception)
        self.assertIn("2 cheque(s)", message)
        self.assertIn("80,000.00", message)

    # ------------------------------------------------------- the exception path
    def test_an_approved_exception_lets_the_lease_activate(self):
        lease = self._lease("EXC-104")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_approve()
        lease.action_activate()
        self.assertEqual(lease.state, "active")
        self.assertEqual(lease.unit_id.state, "occupied")
        self.assertTrue(exception.activation_date, "the exception should record that it was used")

    def test_a_requested_but_undecided_exception_does_not_let_it_through(self):
        """The record is not the permission; the approval is."""
        lease = self._lease("EXC-105")
        self._request(lease, requested_by=self.agent)
        with self.assertRaises(UserError):
            lease.action_activate()
        self.assertEqual(lease.state, "draft")

    def test_a_rejected_exception_does_not_let_it_through(self):
        lease = self._lease("EXC-106")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_reject()
        self.assertEqual(exception.state, "rejected")
        with self.assertRaises(UserError):
            lease.action_activate()

    def test_the_shortfall_on_the_record_is_frozen_at_request_time(self):
        """It is evidence of why the approval was given. A computed shortfall
        would fall to zero as the cheques arrived and the record would stop
        explaining itself."""
        lease = self._lease("EXC-107")
        exception = self._request(lease, requested_by=self.agent)
        self.assertEqual(exception.missing_cheque_count, 4)
        self._register_cheques(lease)
        exception.invalidate_recordset()
        self.assertEqual(exception.missing_cheque_count, 4)
        self.assertEqual(exception.outstanding_cheque_count, 0)

    def test_the_request_cannot_overstate_what_was_missing(self):
        """The snapshot comes from the lease, not from the form: a request that
        could inflate the shortfall would make its own approval look better
        justified than it was."""
        lease = self._lease("EXC-108")
        exception = self.env["c2p.lease.cheque.exception"].create(
            {
                "lease_id": lease.id,
                "reason": "r",
                "conditions": "c",
                "deadline": fields.Date.context_today(self.env.user) + timedelta(days=7),
                "responsible_user_id": self.agent.id,
                "missing_cheque_count": 99,
                "missing_amount": 999999.0,
            }
        )
        self.assertEqual(exception.missing_cheque_count, 4)
        self.assertAlmostEqual(exception.missing_amount, 120000.0, places=2)

    # ------------------------------------------------------------- who approves
    def test_a_property_user_cannot_approve(self):
        lease = self._lease("EXC-109")
        exception = self._request(lease, requested_by=self.agent)
        with self.assertRaises(UserError):
            exception.with_user(self.agent).action_approve()
        self.assertEqual(exception.state, "draft")

    def test_the_requester_cannot_approve_their_own_exception(self):
        """BRD §8.4: no self-approval of lease changes. This half of the control
        does not wait on OD-06 - it holds whichever role ends up approving."""
        lease = self._lease("EXC-110")
        exception = self._request(lease, requested_by=self.manager)
        with self.assertRaises(UserError) as caught:
            exception.with_user(self.manager).action_approve()
        self.assertIn("self-approval", str(caught.exception).lower())
        self.assertEqual(exception.state, "draft")

    def test_approval_records_who_and_when(self):
        lease = self._lease("EXC-111")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_approve()
        self.assertEqual(exception.state, "approved")
        self.assertEqual(exception.approved_by_id, self.manager)
        self.assertTrue(exception.approval_date)

    def test_approval_raises_the_follow_up_activity(self):
        """BR-075 asks for follow-up, not just a record."""
        lease = self._lease("EXC-112")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_approve()
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "c2p.lease.cheque.exception"), ("res_id", "=", exception.id)]
        )
        self.assertTrue(activities)
        self.assertEqual(activities.user_id, self.agent)
        self.assertEqual(activities.date_deadline, exception.deadline)

    def test_an_already_decided_exception_cannot_be_approved_again(self):
        lease = self._lease("EXC-113")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_approve()
        with self.assertRaises(UserError):
            exception.with_user(self.manager).action_approve()

    def test_only_one_open_exception_per_lease(self):
        """Two open exceptions would each half-justify the same activation."""
        lease = self._lease("EXC-114")
        self._request(lease, requested_by=self.agent)
        with self.assertRaises(ValidationError):
            self._request(lease, requested_by=self.agent)

    def test_a_deadline_in_the_past_is_refused(self):
        lease = self._lease("EXC-115")
        with self.assertRaises(ValidationError):
            self.env["c2p.lease.cheque.exception"].create(
                {
                    "lease_id": lease.id,
                    "reason": "r",
                    "conditions": "c",
                    "deadline": fields.Date.context_today(self.env.user) - timedelta(days=1),
                    "responsible_user_id": self.agent.id,
                }
            )

    # ---------------------------------------------------------------- follow-up
    def test_the_cron_closes_an_exception_once_the_cheques_arrive(self):
        lease = self._lease("EXC-116")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_approve()
        lease.action_activate()
        self._register_cheques(lease)
        self.env["c2p.lease.cheque.exception"]._cron_cheque_exception_followup()
        self.assertEqual(exception.state, "fulfilled")

    def test_the_cron_marks_a_missed_deadline(self):
        lease = self._lease("EXC-117")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_approve()
        lease.action_activate()
        # Move the deadline into the past in SQL: _check_deadline refuses it
        # through the ORM, which is right for a request and wrong for
        # simulating the passage of time.
        self.env.cr.execute(
            "UPDATE c2p_lease_cheque_exception SET deadline = %s WHERE id = %s",
            (fields.Date.context_today(self.env.user) - timedelta(days=1), exception.id),
        )
        exception.invalidate_recordset()
        self.env["c2p.lease.cheque.exception"]._cron_cheque_exception_followup()
        self.assertEqual(exception.state, "breached")

    def test_the_cron_leaves_a_live_exception_alone(self):
        lease = self._lease("EXC-118")
        exception = self._request(lease, requested_by=self.agent)
        exception.with_user(self.manager).action_approve()
        self.env["c2p.lease.cheque.exception"]._cron_cheque_exception_followup()
        self.assertEqual(exception.state, "approved")

    # ------------------------------------------------------- the complete route
    def test_a_full_cheque_set_activates_without_any_exception(self):
        lease = self._lease("EXC-119")
        self._register_cheques(lease)
        self.assertTrue(lease.cheques_complete)
        lease.action_activate()
        self.assertEqual(lease.state, "active")
        self.assertFalse(lease.cheque_exception_ids)

    def test_the_right_number_of_cheques_for_too_little_money_is_not_complete(self):
        """Four cheques covering half the rent is a complete-looking set and an
        incomplete one, so the count alone cannot be the test."""
        lease = self._lease("EXC-120")
        self._register_cheques(lease, amount=lease.instalment_amount / 2)
        self.assertEqual(lease.cheques_received, 4)
        self.assertFalse(lease.cheques_complete)
        with self.assertRaises(UserError):
            lease.action_activate()

    def test_the_right_money_in_too_few_cheques_is_not_complete(self):
        """And the money alone cannot be it either: the agreed schedule is part
        of the deal, not just the total."""
        lease = self._lease("EXC-121")
        self._register_cheques(lease, count=1, amount=lease.annual_rent)
        self.assertEqual(lease.cheques_received, 1)
        self.assertAlmostEqual(lease.cheque_cover, lease.annual_rent, places=2)
        self.assertFalse(lease.cheques_complete)

    def test_a_bounced_cheque_does_not_count_as_received(self):
        """The instrument exists; the money never arrived. That is the exact
        situation BR-075 is about."""
        lease = self._lease("EXC-122")
        self._register_cheques(lease, pdc_state="bounced")
        self.assertEqual(lease.cheques_received, 0)
        self.assertFalse(lease.cheques_complete)

    def test_a_cleared_cheque_still_counts_as_received(self):
        lease = self._lease("EXC-123")
        self._register_cheques(lease, pdc_state="cleared")
        self.assertTrue(lease.cheques_complete)

    # ------------------------------------------------------------ the load path
    def test_the_load_path_activates_without_cheques(self):
        """A migrated tenancy is already running, and the migration plan loads
        leases (object 14) before cheques (object 16)."""
        lease = self._lease("EXC-124")
        lease._activate_as_loaded()
        self.assertEqual(lease.state, "active")
        self.assertEqual(lease.unit_id.state, "occupied")

    def test_writing_the_state_straight_to_active_is_refused(self):
        """The form's statusbar writes `state` directly, so a gate that only
        guarded the button would guard nothing."""
        lease = self._lease("EXC-124b")
        with self.assertRaises(UserError) as caught:
            lease.state = "active"
        self.assertIn("cheque", str(caught.exception).lower())
        self.assertEqual(lease.state, "draft")

    def test_the_loader_context_is_what_lets_that_write_through(self):
        lease = self._lease("EXC-124c")
        lease.with_context(c2p_lease_loaded=True).state = "active"
        self.assertEqual(lease.state, "active")

    def test_writing_other_fields_on_an_active_lease_still_works(self):
        """Regression guard on the write override: a short lease that is already
        active (loaded, or activated under an exception since fulfilled) must
        stay editable."""
        lease = self._lease("EXC-124d")
        lease._activate_as_loaded()
        lease.write({"state": "active", "ejari_no": "E-123456"})
        self.assertEqual(lease.ejari_no, "E-123456")

    def test_the_load_path_has_not_replaced_the_gate(self):
        """The guard against the bypass becoming the normal route: the
        user-facing action must still refuse on the same data."""
        lease = self._lease("EXC-125")
        with self.assertRaises(UserError):
            lease.action_activate()

    # ----------------------------------------------------------------- renewal
    def test_a_renewal_does_not_inherit_the_cheque_register(self):
        """`copy()` copies One2many fields by default, so a renewal used to
        duplicate the tenant's cheques onto the successor - payment records
        against cheques nobody wrote, and, now that BR-075 reads this register,
        cover that would walk a renewal straight through the gate."""
        lease = self._lease("EXC-126")
        self._register_cheques(lease)
        lease.action_activate()
        renewal = lease.copy({"date_start": "2027-01-01", "date_end": "2027-12-31", "state": "draft"})
        self.assertFalse(renewal.payment_ids)
        self.assertFalse(renewal.cheques_complete)

    def test_renewal_drafts_the_successor_when_its_cheques_are_missing(self):
        """And leaves the outgoing tenancy running: a successor that has not
        started has not taken over."""
        lease = self._lease("EXC-127")
        lease._activate_as_loaded()
        wizard = self.env["c2p.lease.renew"].create(
            {
                "lease_id": lease.id,
                "new_rent": 130000.0,
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
            }
        )
        wizard.action_renew()
        renewal = self.env["c2p.lease"].search([("renewed_from_id", "=", lease.id)])
        self.assertEqual(len(renewal), 1)
        self.assertEqual(renewal.state, "draft")
        self.assertEqual(lease.state, "active")
