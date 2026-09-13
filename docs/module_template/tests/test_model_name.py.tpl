from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestModelName(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.record = cls.env["sinclaire.model.name"].create({"name": "Test"})

    def test_negative_sequence_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.record.sequence = -1

    def test_records_are_scoped_to_the_active_company(self):
        self.assertEqual(self.record.company_id, self.env.company)
