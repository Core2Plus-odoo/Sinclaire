from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSinclaireBase(TransactionCase):
    """Smoke tests proving the module installs with its security data."""

    def test_security_groups_exist(self):
        user_group = self.env.ref("sinclaire_base.group_sinclaire_user")
        manager_group = self.env.ref("sinclaire_base.group_sinclaire_manager")
        self.assertIn(user_group, manager_group.implied_ids)

    def test_groups_are_under_the_sinclaire_privilege(self):
        privilege = self.env.ref("sinclaire_base.res_groups_privilege_sinclaire")
        self.assertEqual(
            self.env.ref("sinclaire_base.group_sinclaire_user").privilege_id,
            privilege,
        )

    def test_admin_is_sinclaire_manager(self):
        admin = self.env.ref("base.user_admin")
        self.assertTrue(admin.has_group("sinclaire_base.group_sinclaire_manager"))
