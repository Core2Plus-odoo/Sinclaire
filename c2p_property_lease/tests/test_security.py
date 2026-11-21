"""Who can see the module after it is installed.

These tests exist because of a defect that every other test missed: the
Property root menu is gated on `group_property_user`, no user was a member of
either property group, and the module therefore installed successfully and was
completely invisible - administrator included.

Nothing caught it because the rest of the suite runs as superuser, which
ignores both group membership and menu visibility. CI installed the module,
ran 123 passing tests, and shipped something no human could open.
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase
from odoo.tests.common import tagged


@tagged("post_install", "-at_install")
class TestMenuVisibility(TransactionCase):
    def test_the_administrator_is_a_leasing_manager(self):
        """The seeded membership that makes the menu reachable on a fresh
        install."""
        admin = self.env.ref("base.user_admin")
        manager = self.env.ref("c2p_property_lease.group_property_manager")
        self.assertIn(
            admin,
            manager.user_ids,
            "No user in group_property_manager means nobody sees the Property menu.",
        )

    def test_the_manager_group_implies_the_user_group(self):
        """The root menu is gated on the user group, so the manager group has
        to imply it or a manager still sees nothing."""
        manager = self.env.ref("c2p_property_lease.group_property_manager")
        user = self.env.ref("c2p_property_lease.group_property_user")
        self.assertIn(user, manager.implied_ids)

    def _root_menus_for(self, user):
        """The root menus this user actually sees.

        Menu visibility does NOT run through `search`: `_visible_menu_ids`
        filters on the menu's `group_ids` against the user's groups, and
        `get_user_roots` applies it. Searching `ir.ui.menu` as a user returns
        menus they cannot see, so a test written that way passes whatever the
        groups say - which is how the original defect survived.
        """
        return self.env["ir.ui.menu"].with_user(user).get_user_roots()

    def test_the_property_menu_is_visible_to_the_administrator(self):
        """The end-to-end check, and the one that reproduces the defect."""
        admin = self.env.ref("base.user_admin")
        root = self.env.ref("c2p_property_lease.menu_property_root")
        self.assertIn(
            root,
            self._root_menus_for(admin),
            "The Property root menu is not visible to the administrator.",
        )

    def test_a_plain_internal_user_does_not_see_the_property_menu(self):
        """The gate is real: being an employee is not enough. Seeding the
        manager group must not turn into showing the menu to everybody."""
        plain = self.env["res.users"].create(
            {
                "name": "Plain Employee",
                "login": "plain_employee_menu",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        root = self.env.ref("c2p_property_lease.menu_property_root")
        self.assertNotIn(
            root,
            self._root_menus_for(plain),
            "The Property menu should be gated on the leasing groups.",
        )

    def test_a_leasing_user_sees_the_property_menu(self):
        """The group the menu is actually gated on."""
        leasing = self.env["res.users"].create(
            {
                "name": "Leasing Staff",
                "login": "leasing_staff_menu",
                "group_ids": [(4, self.env.ref("c2p_property_lease.group_property_user").id)],
            }
        )
        root = self.env.ref("c2p_property_lease.menu_property_root")
        self.assertIn(root, self._root_menus_for(leasing))


@tagged("post_install", "-at_install")
class TestCompanyScope(TransactionCase):
    """BR-004: two legal entities, and what keeps their records apart.

    A `company_id` field scopes nothing by itself - Odoo creates no record rule
    implicitly. `c2p.head.lease` and `c2p.bank.facility` carried the field from
    the start with no rule, so every head lease in the database was readable by
    any leasing user and every banking facility by a manager of either company.
    Landlord commitments and bank limits: the two most commercially sensitive
    models in this module.

    Every test here runs `with_user`. The rest of the suite runs as superuser,
    which **ignores record rules entirely** - so a test written the ordinary way
    passes whether or not the rules exist, which is exactly how the menu defect
    at the top of this file survived 123 passing tests.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "Scope Property LLC"})
        cls.company_b = cls.env["res.company"].create({"name": "Scope Brokers LLC"})
        cls.landlord = cls.env["res.partner"].create({"name": "Scope Landlord"})
        cls.bank = cls.env["res.bank"].create({"name": "Scope Bank"})

        cls.user_a = cls.env["res.users"].create(
            {
                "name": "Scope User A",
                "login": "scope_user_a",
                "company_id": cls.company_a.id,
                "company_ids": [(6, 0, [cls.company_a.id])],
                "group_ids": [(4, cls.env.ref("c2p_property_lease.group_property_manager").id)],
            }
        )
        cls.both = cls.env["res.users"].create(
            {
                "name": "Scope User Both",
                "login": "scope_user_both",
                "company_id": cls.company_a.id,
                "company_ids": [(6, 0, [cls.company_a.id, cls.company_b.id])],
                "group_ids": [(4, cls.env.ref("c2p_property_lease.group_property_manager").id)],
            }
        )

    def _head_lease(self, company):
        building = self.env["c2p.building"].create(
            {
                "name": f"{company.name} Tower",
                "code": f"SC{company.id}",
                "owner_id": self.landlord.id,
                "operating_model": "head_lease",
                "company_id": company.id,
            }
        )
        return self.env["c2p.head.lease"].create(
            {
                "building_id": building.id,
                "landlord_id": self.landlord.id,
                "company_id": company.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "annual_amount": 500000.0,
            }
        )

    def _facility(self, company):
        return self.env["c2p.bank.facility"].create(
            {
                "name": f"{company.name} Overdraft",
                "company_id": company.id,
                "bank_id": self.bank.id,
                "facility_type": "overdraft",
                "limit_amount": 1000000.0,
            }
        )

    # --- the registry walk, so the next model cannot be missed the same way ---
    def test_every_company_scoped_model_has_a_record_rule(self):
        """The guard, and the reason this class exists rather than two fixtures.

        Adding a model with `company_id` and forgetting the rule is invisible:
        it installs, every superuser test passes, and the leak only shows when
        two companies hold data. This walks the registry instead of listing the
        models, so a model added later is covered without anybody remembering.
        """
        Rule = self.env["ir.rule"]
        unscoped = []
        for name in sorted(self.env.registry):
            if not name.startswith("c2p."):
                continue
            model = self.env[name]
            if model._transient or model._abstract:
                continue  # a wizard row belongs to its session, not a company
            if "company_id" not in model._fields:
                continue
            rules = Rule.sudo().search([("model_id.model", "=", name)])
            if not any("company_id" in (rule.domain_force or "") for rule in rules):
                unscoped.append(name)
        self.assertFalse(
            unscoped,
            "These models carry company_id with no record rule scoping it, so their "
            f"records are readable across every company: {', '.join(unscoped)}",
        )

    # --- head leases -------------------------------------------------------
    def test_a_head_lease_is_invisible_to_the_other_company(self):
        mine = self._head_lease(self.company_a)
        theirs = self._head_lease(self.company_b)
        visible = self.env["c2p.head.lease"].with_user(self.user_a).search([])
        self.assertIn(mine, visible)
        self.assertNotIn(theirs, visible, "a head lease leaked across the two legal entities")

    def test_reading_another_company_s_head_lease_by_id_is_refused(self):
        """Search filtering is not the control. A record rule has to refuse a
        direct read too, or anyone who knows an id walks straight past it."""
        theirs = self._head_lease(self.company_b)
        with self.assertRaises(AccessError):
            theirs.with_user(self.user_a).read(["annual_amount"])

    # --- banking facilities ------------------------------------------------
    def test_a_banking_facility_is_invisible_to_the_other_company(self):
        mine = self._facility(self.company_a)
        theirs = self._facility(self.company_b)
        visible = self.env["c2p.bank.facility"].with_user(self.user_a).search([])
        self.assertIn(mine, visible)
        self.assertNotIn(theirs, visible, "a banking facility leaked across the two legal entities")

    def test_reading_another_company_s_facility_by_id_is_refused(self):
        theirs = self._facility(self.company_b)
        with self.assertRaises(AccessError):
            theirs.with_user(self.user_a).read(["limit_amount"])

    # --- and the rules must not over-reach ---------------------------------
    def test_a_user_of_both_companies_sees_both(self):
        """The rule scopes on `company_ids`, not `company_id`, so somebody with
        both entities enabled sees both. Scoping on the active company alone
        would hide half the group from whoever runs it."""
        mine = self._head_lease(self.company_a)
        theirs = self._head_lease(self.company_b)
        visible = self.env["c2p.head.lease"].with_user(self.both).search([])
        self.assertIn(mine, visible)
        self.assertIn(theirs, visible)

    def test_the_existing_five_rules_still_hold(self):
        """A regression guard on the rules that were already there, because
        this change edits the file they live in."""
        for xmlid in (
            "rule_building_company",
            "rule_unit_company",
            "rule_lease_company",
            "rule_cheque_exception_company",
            "rule_tenancy_event_company",
        ):
            with self.subTest(rule=xmlid):
                rule = self.env.ref(f"c2p_property_lease.{xmlid}")
                self.assertIn("company_id", rule.domain_force)
