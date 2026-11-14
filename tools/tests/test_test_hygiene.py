import ast
import unittest

from tools.check_test_hygiene import check
from tools.check_test_hygiene import test_files
from tools.check_test_hygiene import unreachable_in


def found(src):
    return unreachable_in(ast.parse(src))


class TestUnreachableDetection(unittest.TestCase):
    def test_it_catches_the_defect_this_was_written_for(self):
        """The real shape: a fixture pasted below a factory's return."""
        hits = found(
            "class T:\n"
            "    @classmethod\n"
            "    def _unit(cls, name):\n"
            "        unit = cls.make(name)\n"
            "        return unit\n"
            "        cls.lease = cls.make_lease()\n"
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "return")

    def test_it_catches_code_after_raise(self):
        hits = found("def f():\n    raise ValueError('x')\n    cleanup()\n")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "raise")

    def test_it_catches_code_after_break_and_continue(self):
        self.assertEqual(len(found("def f():\n    for i in x:\n        break\n        g()\n")), 1)
        self.assertEqual(len(found("def f():\n    for i in x:\n        continue\n        g()\n")), 1)

    def test_a_return_at_the_end_is_fine(self):
        self.assertEqual(found("def f():\n    a = 1\n    return a\n"), [])

    def test_a_return_inside_a_branch_is_fine(self):
        """The commonest early-return shape must not be flagged."""
        self.assertEqual(
            found("def f(x):\n    if x:\n        return 1\n    return 2\n"),
            [],
        )

    def test_a_return_in_a_loop_body_is_fine(self):
        self.assertEqual(
            found("def f(xs):\n    for x in xs:\n        if x:\n            return x\n    return None\n"),
            [],
        )

    def test_a_return_in_an_except_handler_is_fine(self):
        self.assertEqual(
            found("def f():\n    try:\n        return g()\n    except E:\n        return None\n"),
            [],
        )

    def test_it_catches_unreachable_inside_an_except_handler(self):
        hits = found("def f():\n    try:\n        g()\n    except E:\n        return None\n        log()\n")
        self.assertEqual(len(hits), 1)

    def test_it_reports_the_line_of_the_skipped_statement(self):
        hits = found("def f():\n    return 1\n    dead()\n")
        self.assertEqual(hits[0][0], 3)


class TestRepoIsClean(unittest.TestCase):
    def test_no_test_file_has_unreachable_code(self):
        problems = check(test_files())
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
