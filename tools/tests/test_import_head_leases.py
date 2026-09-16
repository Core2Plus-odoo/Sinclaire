"""Tests for the CSV half of tools/import_head_leases.py.

Everything here runs without an Odoo connection: `read_rows` parses and
validates, `resolve` is what needs a database. The point of these is that a
malformed head-lease CSV is caught on the report rather than half way through
writing commitments into the database.

    python -m unittest discover -s tools/tests
"""

import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("import_head_leases", REPO / "tools" / "import_head_leases.py")
ihl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ihl)

HEADER = (
    "building_code,landlord,date_start,date_end,annual_amount,cheque_count,security_deposit,ejari_no,ejari_date,state\n"
)


def parse(body, header=HEADER):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as fh:
        fh.write(header + body)
        path = fh.name
    try:
        return ihl.read_rows(path)
    finally:
        Path(path).unlink()


class TestTermDefault(unittest.TestCase):
    def test_a_january_start_ends_on_new_years_eve(self):
        self.assertEqual(ihl.one_year_less_a_day(date(2026, 1, 1)), date(2026, 12, 31))

    def test_a_mid_month_start_ends_the_day_before_its_anniversary(self):
        self.assertEqual(ihl.one_year_less_a_day(date(2026, 6, 15)), date(2027, 6, 14))

    def test_a_leap_day_start_falls_back_rather_than_raising(self):
        self.assertEqual(ihl.one_year_less_a_day(date(2024, 2, 29)), date(2025, 2, 27))

    def test_term_is_filled_in_when_date_end_is_blank(self):
        rows, errors = parse("MKH,,2026-01-01,,1200000,4,,,,draft\n")
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["date_end"], date(2026, 12, 31))


class TestValidation(unittest.TestCase):
    def test_a_complete_row_parses(self):
        rows, errors = parse("MKH,Some Landlord,2026-01-01,2026-12-31,1200000,4,100000,E123,2026-01-05,active\n")
        self.assertEqual(errors, [])
        row = rows[0]
        self.assertEqual(row["code"], "MKH")
        self.assertEqual(row["annual_amount"], 1200000.0)
        self.assertEqual(row["security_deposit"], 100000.0)
        self.assertEqual(row["ejari_date"], date(2026, 1, 5))
        self.assertEqual(row["state"], "active")

    def test_thousands_separators_are_accepted(self):
        rows, errors = parse('MKH,,2026-01-01,,"1,200,000",4,,,,draft\n')
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["annual_amount"], 1200000.0)

    def test_an_unfilled_template_row_is_reported_not_imported(self):
        rows, errors = parse("MKH,Some Landlord,,,,4,,,,draft\n")
        self.assertEqual(rows, [])
        self.assertIn("no date_start or annual_amount", errors[0])

    def test_a_zero_amount_is_rejected(self):
        _, errors = parse("MKH,,2026-01-01,,0,4,,,,draft\n")
        self.assertTrue(any("greater than zero" in e for e in errors))

    def test_a_negative_deposit_is_rejected(self):
        _, errors = parse("MKH,,2026-01-01,,1200000,4,-5,,,draft\n")
        self.assertTrue(any("security_deposit" in e for e in errors))

    def test_an_end_before_the_start_is_rejected(self):
        _, errors = parse("MKH,,2026-06-01,2026-01-01,1200000,4,,,,draft\n")
        self.assertTrue(any("on or before its start" in e for e in errors))

    def test_an_unpayable_cheque_count_is_rejected(self):
        _, errors = parse("MKH,,2026-01-01,,1200000,5,,,,draft\n")
        self.assertTrue(any("cheque_count" in e for e in errors))

    def test_an_unknown_state_is_rejected(self):
        _, errors = parse("MKH,,2026-01-01,,1200000,4,,,,expired\n")
        self.assertTrue(any("must be draft or active" in e for e in errors))

    def test_a_malformed_date_is_rejected(self):
        _, errors = parse("MKH,,01/01/2026,,1200000,4,,,,draft\n")
        self.assertTrue(any("YYYY-MM-DD" in e for e in errors))

    def test_the_same_building_and_start_twice_is_rejected(self):
        _, errors = parse("MKH,,2026-01-01,,1200000,4,,,,draft\nMKH,,2026-01-01,,900000,4,,,,draft\n")
        self.assertTrue(any("also appears on row" in e for e in errors))

    def test_the_same_building_in_consecutive_years_is_fine(self):
        rows, errors = parse("MKH,,2026-01-01,,1200000,4,,,,draft\nMKH,,2027-01-01,,1300000,4,,,,draft\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)

    def test_blank_lines_are_skipped(self):
        rows, errors = parse("MKH,,2026-01-01,,1200000,4,,,,draft\n,,,,,,,,,\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)

    def test_cheque_count_defaults_to_four(self):
        rows, _ = parse("MKH,,2026-01-01,,1200000,,,,,\n")
        self.assertEqual(rows[0]["cheque_count"], "4")

    def test_state_defaults_to_draft(self):
        rows, _ = parse("MKH,,2026-01-01,,1200000,4,,,,\n")
        self.assertEqual(rows[0]["state"], "draft")

    def test_a_missing_required_column_stops_the_run(self):
        with self.assertRaises(SystemExit):
            parse("MKH,2026-01-01\n", header="building_code,date_start\n")


class TestShippedTemplate(unittest.TestCase):
    def test_the_template_has_no_amounts_and_reports_every_row(self):
        """The template must never carry invented figures: a head lease is a
        real commitment, so an unfilled row has to fail loudly rather than
        import a number nobody signed."""
        rows, errors = ihl.read_rows(REPO / "tools" / "head_leases_template.csv")
        self.assertEqual(rows, [])
        self.assertTrue(errors)
        self.assertTrue(all("no date_start or annual_amount" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
