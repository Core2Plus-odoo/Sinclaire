"""A migration script must leave behind enough to undo itself.

Odoo keeps no undo for a migration script. When one overwrites a column in
place, the set of rows it changed exists nowhere afterwards: the old values are
gone and nothing records which rows held them. The only durable trace is what
the script itself logs while it still knows.

The 19.0.1.3.0 `vacant -> available` split ran against production on
2026-10-06 and moved 23 units. The count was logged; the identities were not,
so that edit cannot now be reversed from the data. These tests exist so the
next one can be.

Two layers:

* `TestVacantSplitLogsItsReversal` runs the real script against a fake cursor
  and asserts the logged reversal statement names *every* row it changed.
* `TestEveryMigrationIsReversible` is the general guard - it holds for
  migration scripts that do not exist yet, which is the point.
"""

import importlib.util
import logging
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# A script that mutates rows must capture which ones, and RETURNING is the only
# way to get exactly the affected set. A genuine exception (pure DDL, or a
# column being dropped outright) opts out with this marker plus a reason.
OPT_OUT = "# migration-reversal: not-applicable"
MUTATING = re.compile(r"\b(UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.IGNORECASE)


def migration_scripts():
    return sorted(REPO.glob("*/migrations/*/*-migrate.py"))


def load(path):
    spec = importlib.util.spec_from_file_location(f"_mig_{path.parent.name}_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    """Just enough psycopg2 cursor for a migration script.

    `execute` records the statement and arms `fetchall` with the rows the real
    UPDATE would have returned, so a script that forgets RETURNING but calls
    fetchall fails here rather than in production.
    """

    def __init__(self, returning=()):
        self.returning = [(i,) for i in returning]
        self.statements = []
        self._rows = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        self._rows = self.returning if "RETURNING" in sql.upper() else []

    def fetchall(self):
        return self._rows

    @property
    def rowcount(self):
        return len(self._rows)


SPLIT = REPO / "c2p_property_lease/migrations/19.0.1.3.0/pre-migrate.py"


class TestVacantSplitLogsItsReversal(unittest.TestCase):
    def setUp(self):
        self.module = load(SPLIT)

    def _run(self, ids, version="19.0.1.2.0"):
        cr = FakeCursor(ids)
        with self.assertLogs(level=logging.INFO) as captured:
            self.module.migrate(cr, version)
        return cr, "\n".join(captured.output)

    def test_a_fresh_install_is_left_alone(self):
        """`version` is falsy on an install, where there is nothing to migrate
        and the table may not even be populated yet."""
        cr = FakeCursor([1, 2])
        self.module.migrate(cr, None)
        self.assertEqual(cr.statements, [])

    def test_the_update_moves_only_vacant_rows(self):
        cr, _ = self._run([4, 9])
        self.assertEqual(len(cr.statements), 1)
        statement = cr.statements[0]
        self.assertIn("SET state = 'available'", statement)
        self.assertIn("WHERE state = 'vacant'", statement)

    def test_every_changed_id_appears_in_the_reversal_statement(self):
        """The regression this whole file is about. A count tells you the edit
        happened; only the ids let you undo it."""
        ids = [3, 17, 102, 2048]
        _, log = self._run(ids)
        reversal = [line for line in log.splitlines() if "to reverse" in line]
        self.assertEqual(len(reversal), 1, f"expected exactly one reversal line, got: {log}")
        logged = {int(n) for n in re.findall(r"\d+", reversal[0].split("IN (")[1])}
        self.assertEqual(logged, set(ids))

    def test_the_reversal_statement_restores_the_old_state(self):
        _, log = self._run([5])
        self.assertIn("SET state = 'vacant'", log)

    def test_the_count_matches_the_ids(self):
        _, log = self._run([1, 2, 3])
        self.assertIn("moved 3 unit(s)", log)

    def test_nothing_to_migrate_says_so_and_claims_no_reversal(self):
        _, log = self._run([])
        self.assertIn("nothing to migrate", log)
        self.assertNotIn("to reverse", log)


class TestEveryMigrationIsReversible(unittest.TestCase):
    def test_at_least_one_migration_script_is_being_checked(self):
        """Guards the glob. A pattern that matches nothing would make every
        test below pass while checking nothing - the vacuous-test failure mode
        this repo has already hit once."""
        self.assertTrue(migration_scripts(), "no migration scripts found - is the glob still right?")

    def test_a_script_that_mutates_rows_captures_which_rows(self):
        for path in migration_scripts():
            source = path.read_text(encoding="utf-8")
            with self.subTest(script=str(path.relative_to(REPO))):
                if OPT_OUT in source or not MUTATING.search(source):
                    continue
                self.assertIn(
                    "RETURNING",
                    source.upper(),
                    f"{path.relative_to(REPO)} changes rows without RETURNING, so the rows it "
                    f"touched cannot be recovered afterwards. Capture them and log the "
                    f"reversal, or mark the script '{OPT_OUT} <reason>'.",
                )

    def test_a_script_that_captures_rows_also_logs_them(self):
        """RETURNING with nothing logged is worse than neither: the script looks
        careful and still leaves no trace."""
        for path in migration_scripts():
            source = path.read_text(encoding="utf-8")
            with self.subTest(script=str(path.relative_to(REPO))):
                if "RETURNING" not in source.upper():
                    continue
                self.assertIn(
                    "_logger",
                    source,
                    f"{path.relative_to(REPO)} captures the affected rows but logs nothing.",
                )
                self.assertNotIn(
                    "print(",
                    source,
                    f"{path.relative_to(REPO)} uses print(); Odoo.sh captures the logger, not stdout.",
                )


if __name__ == "__main__":
    unittest.main()
