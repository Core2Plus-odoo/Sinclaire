"""Who can see the module after it is installed.

These tests exist because of a defect that every other test missed: the
Property root menu is gated on `group_property_user`, no user was a member of
either property group, and the module therefore installed successfully and was
completely invisible - administrator included.

Nothing caught it because the rest of the suite runs as superuser, which
ignores both group membership and menu visibility. CI installed the module,
ran 123 passing tests, and shipped something no human could open.
"""

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

    def test_the_property_menu_is_visible_to_the_administrator(self):
        """The end-to-end check: read the menu as the administrator, not as
        superuser, and confirm it is actually returned."""
        admin = self.env.ref("base.user_admin")
        root = self.env.ref("c2p_property_lease.menu_property_root")
        visible = self.env["ir.ui.menu"].with_user(admin).search([("id", "=", root.id)])
        self.assertTrue(visible, "The Property root menu is not visible to the administrator.")

    def test_a_plain_internal_user_does_not_see_the_property_menu(self):
        """The gate is real: being an employee is not enough."""
        plain = self.env["res.users"].create(
            {
                "name": "Plain Employee",
                "login": "plain_employee_menu",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        root = self.env.ref("c2p_property_lease.menu_property_root")
        visible = self.env["ir.ui.menu"].with_user(plain).search([("id", "=", root.id)])
        self.assertFalse(visible, "The Property menu should be gated on the leasing groups.")
