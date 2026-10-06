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
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE c2p_unit SET state = 'available' WHERE state = 'vacant'")
    if cr.rowcount:
        print(f"c2p_property_lease: moved {cr.rowcount} unit(s) from Vacant to Available")
