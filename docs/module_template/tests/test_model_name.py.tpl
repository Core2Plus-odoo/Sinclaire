from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestModelName(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.record = cls.env["sinclaire.model.name"].create({"name": "Test"})

    def test_negative_sequence_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.record.sequence = -1
