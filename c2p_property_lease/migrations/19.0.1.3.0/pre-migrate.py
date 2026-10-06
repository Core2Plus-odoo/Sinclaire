"""Split the old single "vacant" state into Vacant and Available.

Before this version a unit was Vacant, Occupied, Under Notice or Blocked, and
"vacant" meant "not let, and lettable". BRD §3.2 separates two things that
single state conflated:

    Available  - re-lettable, ready to market
    Vacant     - just handed back, turnaround not yet complete

Existing rows carry no evidence of which they are, so every one becomes
Available. That is the safe direction: a unit wrongly marked Available is at
worst marketed early and corrected, where one wrongly marked Vacant would
disappear from the availability list with nothing to show why.

Vacancy reporting is unaffected either way - both states are in EMPTY_STATES,
so the counts and vacancy loss on the dashboard do not move.

This script is also the reference for the reversal rule in CONTRIBUTING.md: it
logs the primary keys it changed, so the edit can be undone exactly. Odoo keeps
no undo for a migration script, and `state` is overwritten in place - once this
has run, the set of rows it touched exists nowhere but this log. Ran against
production on 2026-10-06 and moved 23 units, before the logging below existed,
so for that one run the count is recorded and the identities are not.
"""


import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # RETURNING, rather than a SELECT beforehand, so the logged ids are exactly
    # the rows the UPDATE changed - no window in which the two could disagree.
    cr.execute("UPDATE c2p_unit SET state = 'available' WHERE state = 'vacant' RETURNING id")
    ids = sorted(row[0] for row in cr.fetchall())
    if not ids:
        _logger.info("c2p_property_lease: no units in Vacant, nothing to migrate")
        return

    _logger.info("c2p_property_lease: moved %s unit(s) from Vacant to Available", len(ids))
    # One line, however long. A reversal needs every id, and a truncated list is
    # worse than none: it reads as complete and is not.
    _logger.info(
        "c2p_property_lease: to reverse, run - UPDATE c2p_unit SET state = 'vacant' WHERE id IN (%s);",
        ", ".join(str(i) for i in ids),
    )
