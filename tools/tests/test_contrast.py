import unittest

from tools.check_contrast import contrast
from tools.check_contrast import read_tokens
from tools.check_contrast import relative_luminance
from tools.check_contrast import run


class TestContrastMaths(unittest.TestCase):
    """Checked against the WCAG reference values, so a quiet change to the
    formula cannot make the whole design system silently 'pass'."""

    def test_black_on_white_is_the_maximum(self):
        self.assertAlmostEqual(contrast("#000000", "#FFFFFF"), 21.0, places=2)

    def test_a_colour_against_itself_is_one(self):
        self.assertAlmostEqual(contrast("#315DCE", "#315DCE"), 1.0, places=6)

    def test_it_is_symmetric(self):
        self.assertAlmostEqual(contrast("#14243A", "#FFFFFF"), contrast("#FFFFFF", "#14243A"), places=9)

    def test_known_luminances(self):
        self.assertAlmostEqual(relative_luminance("#FFFFFF"), 1.0, places=6)
        self.assertAlmostEqual(relative_luminance("#000000"), 0.0, places=6)

    def test_mid_grey_matches_the_published_value(self):
        # #767676 on white is the canonical "just passes AA" grey.
        self.assertGreaterEqual(contrast("#767676", "#FFFFFF"), 4.5)
        self.assertLess(contrast("#777777", "#FFFFFF"), 4.6)

    def test_the_low_channel_branch_is_exercised(self):
        """Channels at or below 0.04045 take the linear branch, and a formula
        that skipped it would still look roughly right on mid-tones.

        8/255 = 0.031373, which is under the threshold, so each channel is
        0.031373 / 12.92 = 0.00242822. The three weights sum to 1, so that is
        the luminance.
        """
        self.assertAlmostEqual(relative_luminance("#080808"), 0.00242822, places=7)


class TestTokenParsing(unittest.TestCase):
    def test_it_reads_the_real_token_file(self):
        tokens = read_tokens()
        self.assertIn("--sin-navy", tokens)
        self.assertEqual(tokens["--sin-navy"], "#14243A")

    def test_var_aliases_are_not_treated_as_colours(self):
        """--sin-ok is `var(--sin-emerald)`; measuring the literal string would
        throw, so the parser must skip aliases."""
        self.assertNotIn("--sin-ok", read_tokens())


class TestTheSystemItself(unittest.TestCase):
    def test_every_promised_pairing_meets_aa(self):
        failures, measured = run()
        self.assertEqual(failures, [], "\n".join(failures))
        self.assertGreater(len(measured), 15, "the promise list looks truncated")


if __name__ == "__main__":
    unittest.main()
