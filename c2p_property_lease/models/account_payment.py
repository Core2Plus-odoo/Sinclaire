from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

# BR-114 / BRD §6.2. The register has to answer "where is every instrument"
# every day, and two of these states were missing:
#
#   expected  - the schedule says a cheque is due and none has been handed over
#               yet. Without it a missing cheque is indistinguishable from a
#               cheque nobody has entered, which is the difference between a
#               collection problem and a data-entry one.
#   replaced  - this instrument bounced and a replacement has been linked.
#               Leaving it Bounced forever makes the bounce register grow
#               without ever showing which bounces were made good.
#   cancelled - withdrawn before it was ever banked: the lease terminated
#               early, the terms were renegotiated, or the cheque was handed
#               back. Distinct from Bounced, which is a cheque that failed,
#               and from Replaced, which is a bounce made good. Without it
#               those cheques either sit In Hand forever, overstating the
#               cover, or get deleted, destroying the custody trail.
PDC_STATES = [
    ("expected", "Expected"),
    ("held", "In Hand"),
    ("deposited", "Deposited"),
    ("cleared", "Cleared"),
    ("bounced", "Bounced"),
    ("replaced", "Replaced"),
    ("cancelled", "Cancelled"),
]


class AccountPayment(models.Model):
    _inherit = "account.payment"

    lease_id = fields.Many2one("c2p.lease", string="Lease", index=True, copy=False)
    head_lease_id = fields.Many2one(
        "c2p.head.lease",
        string="Head Lease",
        index="btree_not_null",
        copy=False,
        help="Set on cheques we issue to a landlord under an underwriting agreement.",
    )
    is_landlord_cheque = fields.Boolean(
        compute="_compute_is_landlord_cheque",
        store=True,
        help="Money out to a landlord, as opposed to rent in from a tenant.",
    )
    unit_id = fields.Many2one(related="lease_id.unit_id", store=True)
    building_id = fields.Many2one(related="lease_id.building_id", store=True)
    operating_model = fields.Selection(related="building_id.operating_model", store=True, string="Operating Model")
    cheque_no = fields.Char(string="Cheque No.", copy=False)
    cheque_bank = fields.Char(string="Drawn On")
    maturity_date = fields.Date(help="Date the cheque may be banked.")
    is_pdc = fields.Boolean(string="Post-Dated Cheque", compute="_compute_is_pdc", store=True)
    pdc_state = fields.Selection(PDC_STATES, default="held", copy=False, tracking=True)

    # ---------------------------------------------------------- BR-047, payer
    drawer_partner_id = fields.Many2one(
        "res.partner",
        string="Drawer",
        copy=False,
        help="Whoever signed the instrument. Usually the tenant; a third-party cheque "
        "is one signed by somebody else on the tenant's behalf (BRD §4.2.3).",
    )
    is_third_party = fields.Boolean(
        compute="_compute_third_party",
        store=True,
        help="The drawer is not the tenant who owes the money.",
    )

    # -------------------------------------------------- BR-043, BR-116, payee
    payee_partner_id = fields.Many2one(
        "res.partner",
        string="Payee",
        compute="_compute_payee",
        store=True,
        readonly=False,
        copy=False,
        help="Who the instrument is payable to. Derived from the building's operating "
        "model (BRD §4.2.2) and overridable where the contract says otherwise.",
    )
    is_owner_funds = fields.Boolean(
        compute="_compute_payee",
        store=True,
        string="Owner Funds",
        help="Payable to the landlord, held by this company. Never this company's cash or rental income (BRD §6.1).",
    )
    # BR-116 wants "deposit evidence", and this deliberately does NOT reuse
    # account.payment.partner_bank_id. On an inbound payment Odoo already uses
    # that field for the account the money is received INTO, and computes it
    # from the journal - so it arrives pre-filled and would silently satisfy a
    # guard written against it. The landlord's account is a different fact and
    # needs a field of its own.
    owner_deposit_bank_id = fields.Many2one(
        "res.partner.bank",
        string="Deposited Into",
        copy=False,
        help="The landlord's own bank account this instrument was banked into on the due date (BRD §4.2.1).",
    )

    # ------------------------------------------------------------ BR-117, bounce
    bounce_reason = fields.Char(copy=False)
    bounce_charge = fields.Monetary(copy=False, help="Bank charge incurred on the return, recoverable from the tenant.")
    replacement_payment_id = fields.Many2one(
        "account.payment",
        string="Replaced By",
        copy=False,
        index="btree_not_null",
        help="The instrument given to make good this one after it bounced.",
    )

    @api.depends("head_lease_id")
    def _compute_is_landlord_cheque(self):
        for rec in self:
            rec.is_landlord_cheque = bool(rec.head_lease_id)

    @api.depends("cheque_no")
    def _compute_is_pdc(self):
        for rec in self:
            rec.is_pdc = bool(rec.cheque_no)

    @api.depends("drawer_partner_id", "lease_id.tenant_id")
    def _compute_third_party(self):
        """BR-047: the legal payer and the debtor are different questions.

        The receivable stays against the tenant whatever happens - somebody
        else paying does not move the obligation. What changes is who the bank
        will chase if the instrument is returned, and that is the person the
        undertaking has to name.
        """
        for rec in self:
            tenant = rec.lease_id.tenant_id
            rec.is_third_party = bool(rec.drawer_partner_id and tenant and rec.drawer_partner_id != tenant)

    @api.depends(
        "building_id.operating_model",
        "building_id.owner_id",
        # The STORED one2many, not building_id.head_lease_id: that one is a
        # non-stored compute, and a depends routed through it cannot build a
        # reliable trigger. The payee would then go stale whenever a landlord
        # agreement's collection authority was corrected - silently, and on
        # the field that decides whose money a cheque is.
        "building_id.head_lease_ids.collection_party",
        "building_id.head_lease_ids.state",
        "company_id",
        "head_lease_id",
    )
    def _compute_payee(self):
        """BR-043 / BRD §4.2.2: "Payee names shall be derived from the operating model".

        Under a head lease this company has bought the income, so tenant rent
        is payable to it. Under Owner Management the landlord owns the income
        and the cheque is written in the landlord's name - this company holds
        it and banks it into the landlord's account on the due date. Those are
        other people's funds passing through our hands, and the BRD says in
        terms they "must not be presented as company funds".

        A cheque this company issues to a landlord under a head lease is money
        out, so its payee is the landlord but the funds were always ours.
        """
        for rec in self:
            if rec.head_lease_id:
                rec.payee_partner_id = rec.head_lease_id.landlord_id
                rec.is_owner_funds = False
                continue
            model = rec.building_id.operating_model
            if model == "owner_management":
                rec.payee_partner_id = rec.building_id.owner_id
                rec.is_owner_funds = True
                continue

            # BR-022 / BRD §4.2.2: "...derived from the operating model AND
            # contract authority". The operating model was only ever half of
            # it. A head-lease agreement can authorise this company to sign
            # tenancy contracts while still requiring rent to be collected in
            # the landlord's name, and where it does, those cheques are the
            # landlord's money passing through our hands exactly as under
            # Owner Management - whatever the building's operating model says.
            active = rec.building_id.head_lease_ids.filtered(lambda h: h.state == "active")[:1]
            authority = active.collection_party
            if model == "head_lease" and authority == "owner":
                rec.payee_partner_id = rec.building_id.owner_id
                rec.is_owner_funds = True
                continue

            rec.payee_partner_id = rec.company_id.partner_id
            rec.is_owner_funds = False

    @api.constrains("owner_deposit_bank_id", "payee_partner_id")
    def _check_owner_deposit_account(self):
        """The account recorded has to be the payee's own.

        Otherwise "deposited to the landlord's account" can be satisfied by
        naming any account at all, including one of this company's, which is
        the thing BR-116 exists to rule out.
        """
        for rec in self:
            account = rec.owner_deposit_bank_id
            if not account or not rec.payee_partner_id:
                continue
            if account.partner_id != rec.payee_partner_id:
                raise ValidationError(
                    self.env._(
                        "%(account)s belongs to %(holder)s, not to %(payee)s. Owner funds "
                        "must be banked into the payee's own account.",
                        account=account.display_name,
                        holder=account.partner_id.display_name,
                        payee=rec.payee_partner_id.display_name,
                    )
                )

    @api.constrains("replacement_payment_id")
    def _check_replacement(self):
        for rec in self:
            link = rec.replacement_payment_id
            if not link:
                continue
            if link == rec:
                raise ValidationError(self.env._("An instrument cannot replace itself."))
            if link.lease_id != rec.lease_id:
                raise ValidationError(
                    self.env._("A replacement must sit on the same lease as the instrument it replaces.")
                )

    # ------------------------------------------------------------------ actions
    def action_pdc_deposit(self):
        self.filtered(lambda p: p.pdc_state == "held").write({"pdc_state": "deposited"})

    def action_pdc_clear(self):
        """BR-116: owner funds clear into the landlord's account, not ours.

        Without the bank account on the record there is nothing showing where
        the money went, and an owner-funds cheque marked Cleared with no
        destination is indistinguishable from one this company banked for
        itself. That is the exact confusion BRD §6.1 exists to prevent.
        """
        for rec in self:
            if rec.is_owner_funds and not rec.owner_deposit_bank_id:
                raise UserError(
                    rec.env._(
                        "%(ref)s is payable to %(payee)s and is owner funds. Record the "
                        "landlord's bank account it was deposited into before clearing it.",
                        ref=rec.cheque_no or rec.display_name,
                        payee=rec.payee_partner_id.name or "the landlord",
                    )
                )
        self.filtered(lambda p: p.pdc_state in ("held", "deposited")).write({"pdc_state": "cleared"})

    def action_pdc_bounce(self):
        for rec in self:
            rec.pdc_state = "bounced"
            rec.message_post(body=self.env._("Cheque returned unpaid. Follow up with the tenant."))

    def action_pdc_cancel(self, reason=None):
        """Withdraw an instrument that was never banked (BR-114).

        A cleared cheque cannot be cancelled - the money moved, and undoing
        that is a credit note or a refund, not a change of status on the
        register. A bounced one cannot either: it failed, which is a fact
        about what happened and not something to erase.
        """
        for rec in self:
            if rec.pdc_state in ("cleared", "bounced", "replaced"):
                raise UserError(
                    rec.env._(
                        "%(ref)s is %(state)s and cannot be cancelled. Cancelling is for "
                        "an instrument that was never banked.",
                        ref=rec.cheque_no or rec.display_name,
                        state=dict(rec._fields["pdc_state"].selection)[rec.pdc_state],
                    )
                )
            rec.pdc_state = "cancelled"
            if reason:
                note = rec.env._("Cheque cancelled: %(reason)s", reason=reason)
            else:
                note = rec.env._("Cheque cancelled before presentation.")
            rec.message_post(body=note)

    def action_link_replacement(self, replacement):
        """BR-117: a bounce is closed by the instrument that makes it good.

        The bounced cheque moves to Replaced rather than staying Bounced, so
        the bounce register shows what is still outstanding instead of every
        bounce that ever happened.
        """
        for rec in self:
            if rec.pdc_state != "bounced":
                raise UserError(rec.env._("Only a bounced instrument can be replaced."))
            rec.replacement_payment_id = replacement
            rec.pdc_state = "replaced"
            rec.message_post(
                body=rec.env._("Replaced by %(ref)s.", ref=replacement.cheque_no or replacement.display_name)
            )
