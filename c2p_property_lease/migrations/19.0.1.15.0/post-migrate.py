"""Record what existing head leases have been authorising all along.

BR-022 adds three fields that were previously assumptions baked into the code:
whether the landlord permits subleasing, who may sign tenancy contracts, and
in whose name rent is collected. BR-027 then refuses to activate a head lease
whose agreement terms are not on record.

Left to their defaults, both changes break existing data:

- `sublease_permitted` defaults to False, and a new constraint refuses an
  active head lease that does not permit subleasing. Every head lease already
  in the database would fail that constraint on its next write - not at
  migration time, but later, when somebody edits an unrelated field and
  cannot save.
- `collection_party` is NULL, and the payee rule now reads it. NULL is not
  "unknown" to that rule, it simply does not match 'owner', so the behaviour
  happens to stay correct - but it is correct by accident, and a later reader
  cannot tell an unanswered question from an answered one.

So this writes down what was true before rather than leaving a gap. Every
existing head lease was operated as a head lease: units were sublet, this
company signed the tenancies, and tenant cheques were made out to this company
because that is what the payee computation produced. Those are the values
below, and they change no behaviour at all.

What they are NOT is verified against the signed agreements. These rows are
marked in the log precisely so the delivery team can check them against the
documents during migration, where BRD 4.1 expects the agreement terms to be
entered from the document rather than assumed. A landlord agreement that
actually requires collection in the owner's name will move those cheques to
owner funds once corrected - which is the point of BR-022 and must not be
discovered after go-live.

This runs post-migrate: the columns are created by the ORM during module load,
so a pre-migrate script querying them fails with "column does not exist".

Reversal: the columns did not exist before this version, so undoing this is
dropping them.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # One statement rather than a SELECT then an UPDATE: RETURNING captures
    # exactly the rows this changed and leaves no window in which another
    # session could alter one of them between the two queries.
    cr.execute(
        """
        UPDATE c2p_head_lease
           SET sublease_permitted = TRUE,
               contracting_party  = COALESCE(contracting_party, 'manager'),
               collection_party   = COALESCE(collection_party, 'manager')
         WHERE sublease_permitted IS NOT TRUE
            OR contracting_party IS NULL
            OR collection_party IS NULL
        RETURNING id, state
        """
    )
    rows = cr.fetchall()
    if not rows:
        _logger.info("BR-022: every head lease already records its agreement authority.")
        return

    ids = [r[0] for r in rows]
    active = [r[0] for r in rows if r[1] == "active"]
    _logger.info(
        "BR-022: recorded the assumed agreement authority on %s head lease(s), ids %s "
        "(%s of them active, ids %s). Values written: sublease_permitted=TRUE, "
        "contracting_party='manager', collection_party='manager'. These preserve the "
        "behaviour these rows already had and change no figure. They are ASSUMED, not "
        "read from the signed agreements: check each against its document during "
        "migration. A landlord agreement requiring collection in the owner's name "
        "turns those tenant cheques into owner funds once corrected, which must not "
        "be discovered after go-live. To reverse, clear the three columns on exactly "
        "these ids.",
        len(ids),
        ids,
        len(active),
        active,
    )
