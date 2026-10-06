"""BRD §3.2 / §6.2: the payment instrument's seven states.

`docs/status_matrix.md` §3 is the specification. The classes split by what they
need: the consistency checks run against constants and always execute, while the
state machine needs real `account.payment` records and therefore a bank journal
with an inbound payment method, which a database without accounting configured
does not have.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestInstrumentStateConsistency(TransactionCase):
    """No records needed, so these always run.

    They are the guard against the failure shape this repository has hit five
    times: two structures that must agree about a set of states, with nothing
    asserting that they do.
    """

    def test_all_seven_brd_states_exist_in_order(self):
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_STATES

        self.assertEqual(
            [s for s, _ in PDC_STATES],
            ["expected", "held", "deposited", "cleared", "bounced", "replaced", "cancelled"],
        )

    def test_every_transition_names_a_real_state(self):
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_STATES
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_TRANSITIONS

        known = {s for s, _ in PDC_STATES}
        for target, sources in PDC_TRANSITIONS.items():
            self.assertIn(target, known, f"{target} is a transition target but not a state")
            for source in sources:
                self.assertIn(source, known, f"{source} is a transition source but not a state")

    def test_cleared_is_terminal(self):
        """§3: a reversal after clearing is a new accounting event, not a status
        change. So nothing may move out of Cleared."""
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_TRANSITIONS

        out_of_cleared = [target for target, sources in PDC_TRANSITIONS.items() if "cleared" in sources]
        self.assertEqual(out_of_cleared, [])

    def test_every_state_is_reachable(self):
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_STATES
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_TRANSITIONS

        reachable = set(PDC_TRANSITIONS)
        for state, _label in PDC_STATES:
            self.assertIn(state, reachable, f"{state} is a state nothing can move to")

    def test_reason_required_moves_are_real_transitions(self):
        from odoo.addons.c2p_property_lease.models.account_payment import PDC_TRANSITIONS
        from odoo.addons.c2p_property_lease.models.account_payment import REASON_REQUIRED

        for source, target in REASON_REQUIRED:
            self.assertIn(
                source,
                PDC_TRANSITIONS.get(target, ()),
                f"{source} -> {target} needs a reason but is not an allowed move",
            )

    def test_received_cheques_are_exactly_the_ones_in_our_hands(self):
        """BR-075 reads this set. Expected must not be in it - an instrument
        nobody has handed over is the whole situation the gate is about - and
        neither may Replaced or Cancelled."""
        from odoo.addons.c2p_property_lease.models.account_payment import CONCLUDED_STATES
        from odoo.addons.c2p_property_lease.models.account_payment import CUSTODY_STATES
        from odoo.addons.c2p_property_lease.models.lease import RECEIVED_CHEQUE_STATES

        self.assertNotIn("expected", RECEIVED_CHEQUE_STATES)
        self.assertNotIn("replaced", RECEIVED_CHEQUE_STATES)
        self.assertNotIn("cancelled", RECEIVED_CHEQUE_STATES)
        # Everything in custody counts as received, plus cleared - the money
        # arrived, which is the strongest form of received there is.
        self.assertEqual(set(RECEIVED_CHEQUE_STATES), set(CUSTODY_STATES) | {"cleared"})
        self.assertNotIn("expected", CONCLUDED_STATES)


@tagged("post_install", "-at_install")
class TestInstrumentStates(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "PI Landlord"})
        cls.tenant = cls.env["res.partner"].create({"name": "PI Tenant"})
        cls.building = cls.env["c2p.building"].create(
            {"name": "Instrument Tower", "code": "PIT", "owner_id": cls.landlord.id}
        )

    def _journal(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.inbound_payment_method_line_ids:
            self.skipTest("no bank journal with an inbound payment method")
        return journal

    def _lease(self, name, cheque_count="4", annual_rent=120000.0):
        unit = self.env["c2p.unit"].create({"name": name, "building_id": self.building.id})
        return self.env["c2p.lease"].create(
            {
                "tenant_id": self.tenant.id,
                "unit_id": unit.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_rent": annual_rent,
                "cheque_count": cheque_count,
            }
        )

    def _cheque(self, lease=None, state="held", amount=30000.0, cheque_no="700001"):
        journal = self._journal()
        return self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.tenant.id,
                "amount": amount,
                "date": "2026-01-01",
                "journal_id": journal.id,
                "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
                "company_id": self.env.company.id,
                "lease_id": lease.id if lease else False,
                "cheque_no": cheque_no,
                "cheque_bank": "Test Bank",
                "maturity_date": "2026-01-01",
                "pdc_state": state,
            }
        )

    # ------------------------------------------------------------ the happy path
    def test_an_expected_cheque_is_received_then_banked_then_clears(self):
        cheque = self._cheque(state="expected")
        cheque.action_pdc_receive()
        self.assertEqual(cheque.pdc_state, "held")
        cheque.action_pdc_deposit()
        self.assertEqual(cheque.pdc_state, "deposited")
        cheque.action_pdc_clear()
        self.assertEqual(cheque.pdc_state, "cleared")

    def test_a_cheque_cannot_clear_without_being_presented(self):
        """§3 clears only from Deposited, and BR-118 wants bank confirmation
        before anything counts as cleared."""
        cheque = self._cheque(state="held")
        with self.assertRaises(UserError):
            cheque.action_pdc_clear()
        self.assertEqual(cheque.pdc_state, "held")

    def test_nothing_moves_out_of_cleared(self):
        cheque = self._cheque(state="cleared")
        for action in ("action_pdc_deposit", "action_pdc_bounce", "action_pdc_receive"):
            with self.assertRaises(UserError):
                getattr(cheque, action)()
        self.assertEqual(cheque.pdc_state, "cleared")

    # ------------------------------------------------------------------- bounce
    def test_bouncing_records_the_bounce_permanently(self):
        lease = self._lease("PIT-101")
        cheque = self._cheque(lease, state="deposited")
        cheque.action_pdc_bounce()
        self.assertEqual(cheque.pdc_state, "bounced")
        self.assertTrue(cheque.has_bounced)
        self.assertEqual(cheque.bounced_date, fields.Date.context_today(self.env.user))

    def test_bouncing_raises_a_follow_up_on_the_lease(self):
        lease = self._lease("PIT-102")
        cheque = self._cheque(lease, state="deposited")
        cheque.action_pdc_bounce()
        activities = self.env["mail.activity"].search([("res_model", "=", "c2p.lease"), ("res_id", "=", lease.id)])
        self.assertTrue(activities, "BR-117 requires a follow-up on bounce")

    def test_a_cheque_in_hand_cannot_bounce(self):
        """It has not been presented, so there is nothing to return it."""
        cheque = self._cheque(state="held")
        with self.assertRaises(UserError):
            cheque.action_pdc_bounce()

    # ---------------------------------------------------------------- replacement
    def _replace(self, cheque, cheque_no="700999", amount=None):
        wizard = self.env["c2p.pdc.replace"].create(
            {
                "payment_id": cheque.id,
                "cheque_no": cheque_no,
                "cheque_bank": "Replacement Bank",
                "maturity_date": fields.Date.context_today(self.env.user),
                "amount": amount if amount is not None else cheque.amount,
            }
        )
        wizard.action_confirm()
        return cheque.replacement_payment_id

    def test_a_replacement_is_linked_both_ways(self):
        lease = self._lease("PIT-103")
        cheque = self._cheque(lease, state="deposited")
        cheque.action_pdc_bounce()
        replacement = self._replace(cheque)
        self.assertEqual(cheque.pdc_state, "replaced")
        self.assertEqual(replacement.pdc_state, "held")
        self.assertEqual(cheque.replacement_payment_id, replacement)
        self.assertEqual(replacement.replaces_payment_id, cheque)

    def test_a_replacement_stays_on_the_same_lease(self):
        """lease_id is copy=False on the payment, so the link has to be carried
        over deliberately. Losing it would drop the replacement out of the
        register and out of the cover BR-075 reads."""
        lease = self._lease("PIT-104")
        cheque = self._cheque(lease, state="deposited")
        cheque.action_pdc_bounce()
        replacement = self._replace(cheque)
        self.assertEqual(replacement.lease_id, lease)
        self.assertIn(replacement, lease.payment_ids)

    def test_replacing_does_not_erase_the_bounce(self):
        lease = self._lease("PIT-105")
        cheque = self._cheque(lease, state="deposited")
        cheque.action_pdc_bounce()
        self._replace(cheque)
        self.assertTrue(cheque.has_bounced, "a replacement is a recovery, not a retraction")
        self.assertFalse(cheque.replacement_payment_id.has_bounced)

    def test_only_a_returned_cheque_can_be_replaced(self):
        cheque = self._cheque(state="held")
        with self.assertRaises(UserError):
            self._replace(cheque)

    def test_a_cheque_cannot_be_replaced_twice(self):
        lease = self._lease("PIT-106")
        cheque = self._cheque(lease, state="deposited")
        cheque.action_pdc_bounce()
        self._replace(cheque)
        with self.assertRaises(UserError):
            self._replace(cheque, cheque_no="700998")

    # --------------------------------------------------------- reasons and holds
    def _reason_move(self, cheque, move, reason="Because"):
        wizard = self.env["c2p.pdc.reason"].create({"payment_id": cheque.id, "move": move, "reason": reason})
        wizard.action_confirm()

    def test_cancelling_records_the_reason(self):
        cheque = self._cheque(state="expected")
        self._reason_move(cheque, "cancelled", reason="Tenant withdrew before signing")
        self.assertEqual(cheque.pdc_state, "cancelled")
        self.assertIn("withdrew", cheque.pdc_state_reason)

    def test_a_deposited_cheque_cannot_be_cancelled(self):
        """It is with the bank; the outcome is cleared or bounced."""
        cheque = self._cheque(state="deposited")
        with self.assertRaises(UserError):
            self._reason_move(cheque, "cancelled")

    def test_a_reversal_without_a_reason_is_refused(self):
        cheque = self._cheque(state="held")
        with self.assertRaises(UserError):
            cheque._pdc_move("expected")
        self.assertEqual(cheque.pdc_state, "held")

    def test_recalling_a_deposit_needs_a_reason_and_keeps_it(self):
        cheque = self._cheque(state="deposited")
        self._reason_move(cheque, "held", reason="Recalled before presentation")
        self.assertEqual(cheque.pdc_state, "held")
        self.assertIn("Recalled", cheque.pdc_state_reason)

    # ------------------------------------------------------------- the write guard
    def test_the_status_cannot_be_written_directly(self):
        """§3: status may not be set directly; each move is its own action with
        its own history. The form's status column writes this field."""
        cheque = self._cheque(state="held")
        with self.assertRaises(UserError):
            cheque.pdc_state = "cleared"
        self.assertEqual(cheque.pdc_state, "held")

    def test_writing_the_same_status_is_not_a_move(self):
        cheque = self._cheque(state="held")
        cheque.write({"pdc_state": "held", "cheque_bank": "Renamed Bank"})
        self.assertEqual(cheque.cheque_bank, "Renamed Bank")

    def test_other_fields_are_unaffected_by_the_guard(self):
        cheque = self._cheque(state="held")
        cheque.cheque_bank = "Another Bank"
        self.assertEqual(cheque.cheque_bank, "Another Bank")

    # ------------------------------------------------------------------- is_pdc
    def test_an_expected_instrument_is_in_the_register_without_a_number(self):
        """It has no cheque number until the cheque arrives, and leaving it out
        of the register would make the forward view useless."""
        lease = self._lease("PIT-107")
        cheque = self._cheque(lease, state="expected", cheque_no=False)
        self.assertTrue(cheque.is_pdc)

    def test_an_ordinary_payment_is_not_an_instrument(self):
        """pdc_state defaults to "held" on every payment in the database, so
        is_pdc cannot key off the status alone."""
        journal = self._journal()
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.tenant.id,
                "amount": 500.0,
                "journal_id": journal.id,
                "payment_method_line_id": journal.inbound_payment_method_line_ids[0].id,
                "company_id": self.env.company.id,
            }
        )
        self.assertFalse(payment.is_pdc)

    # ------------------------------------------------------ schedule and BR-075
    def test_the_schedule_covers_every_offered_cheque_count(self):
        """Regression: the PDC register carried its own months-per-instalment
        map, which never gained the 3-cheque schedule Stage 2 added - so
        registering cheques on a 3-cheque lease raised KeyError."""
        counts = [value for value, _label in self.env["c2p.lease"]._fields["cheque_count"].selection]
        for count in counts:
            lease = self._lease(f"PIT-SCH-{count}", cheque_count=count)
            schedule = lease._cheque_schedule()
            with self.subTest(cheque_count=count):
                self.assertEqual(len(schedule), int(count))

    def test_the_register_wizard_handles_a_three_cheque_lease(self):
        lease = self._lease("PIT-108", cheque_count="3")
        wizard = self.env["c2p.pdc.register"].create(
            {
                "lease_id": lease.id,
                "journal_id": self._journal().id,
                "first_maturity": "2026-01-01",
                "bank_name": "Test Bank",
                "first_cheque_no": "800001",
            }
        )
        wizard._onchange_generate()
        self.assertEqual(len(wizard.line_ids), 3)

    def test_generating_the_expected_schedule_creates_unreceived_instruments(self):
        self._journal()
        lease = self._lease("PIT-109")
        lease.action_generate_expected_cheques()
        self.assertEqual(len(lease.payment_ids), 4)
        self.assertEqual(set(lease.payment_ids.mapped("pdc_state")), {"expected"})

    def test_an_expected_schedule_does_not_satisfy_the_cheque_gate(self):
        """The mistake the generator makes easy, and the one that would hollow
        out BR-075: a schedule is a promise, not a cheque."""
        self._journal()
        lease = self._lease("PIT-110")
        lease.action_generate_expected_cheques()
        self.assertEqual(lease.cheques_received, 0)
        self.assertFalse(lease.cheques_complete)
        with self.assertRaises(UserError):
            lease.action_activate()

    def test_receiving_the_whole_expected_schedule_does_satisfy_it(self):
        self._journal()
        lease = self._lease("PIT-111")
        lease.action_generate_expected_cheques()
        for i, cheque in enumerate(lease.payment_ids):
            cheque.cheque_no = f"7101{i:02d}"
        lease.payment_ids.action_pdc_receive()
        lease.invalidate_recordset()
        self.assertEqual(lease.cheques_received, 4)
        self.assertTrue(lease.cheques_complete)
        lease.action_activate()
        self.assertEqual(lease.state, "active")

    def test_the_schedule_is_not_regenerated_over_existing_instruments(self):
        self._journal()
        lease = self._lease("PIT-112")
        lease.action_generate_expected_cheques()
        with self.assertRaises(UserError):
            lease.action_generate_expected_cheques()

    def test_a_cancelled_instrument_stops_counting_as_cover(self):
        self._journal()
        lease = self._lease("PIT-113")
        lease.action_generate_expected_cheques()
        for i, cheque in enumerate(lease.payment_ids):
            cheque.cheque_no = f"7102{i:02d}"
        lease.payment_ids.action_pdc_receive()
        lease.invalidate_recordset()
        self.assertTrue(lease.cheques_complete)
        self._reason_move(lease.payment_ids[0], "cancelled", reason="Wrong account")
        lease.invalidate_recordset()
        self.assertFalse(lease.cheques_complete)

    def test_a_replaced_instrument_hands_its_cover_to_the_replacement(self):
        """The pair must not double-count, and must not leave a hole either."""
        self._journal()
        lease = self._lease("PIT-114")
        lease.action_generate_expected_cheques()
        for i, cheque in enumerate(lease.payment_ids):
            cheque.cheque_no = f"7103{i:02d}"
        lease.payment_ids.action_pdc_receive()
        first = lease.payment_ids[0]
        first.action_pdc_deposit()
        first.action_pdc_bounce()
        lease.invalidate_recordset()
        self.assertEqual(lease.cheques_received, 3, "a bounced cheque is not cover")
        self._replace(first, cheque_no="700500")
        lease.invalidate_recordset()
        self.assertEqual(lease.cheques_received, 4)
        self.assertTrue(lease.cheques_complete)


@tagged("post_install", "-at_install")
class TestInstrumentLandlordSide(TransactionCase):
    """A landlord cheque moves through the same states, which is what the head
    lease's paid/outstanding figures read."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.landlord = cls.env["res.partner"].create({"name": "PI Owner"})
        cls.building = cls.env["c2p.building"].create(
            {"name": "Owner Tower", "code": "POT", "owner_id": cls.landlord.id}
        )

    def test_a_landlord_cheque_clears_through_deposited(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal or not journal.outbound_payment_method_line_ids:
            self.skipTest("no bank journal with an outbound payment method")
        head = self.env["c2p.head.lease"].create(
            {
                "building_id": self.building.id,
                "landlord_id": self.landlord.id,
                "date_start": fields.Date.context_today(self.env.user),
                "date_end": fields.Date.context_today(self.env.user) + timedelta(days=364),
                "annual_amount": 120000.0,
                "cheque_count": "4",
            }
        )
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.landlord.id,
                "amount": head.instalment_amount,
                "journal_id": journal.id,
                "payment_method_line_id": journal.outbound_payment_method_line_ids[0].id,
                "head_lease_id": head.id,
                "cheque_no": "410001",
            }
        )
        self.assertTrue(payment.is_landlord_cheque)
        payment.action_pdc_deposit()
        payment.action_pdc_clear()
        head.invalidate_recordset()
        self.assertEqual(head.paid_amount, head.instalment_amount)
