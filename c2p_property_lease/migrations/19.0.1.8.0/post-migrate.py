"""Give every existing building an operating model.

BR-019 adds `operating_model` to c2p.building. Before this version the module
had no such concept: it was written when the engagement was head-lease only,
and margin, coverage and break-even were computed for every building without
asking whether underwriting was what was happening.

Every existing row becomes `head_lease`, which is what they have been all
along - the figures already on them were computed on that assumption, so this
changes no number. A building that is actually owner-managed has to be
switched by hand, and that switch is the point: it zeroes the margin and moves
the tenant rent into `managed_rent`, where BRD §6.1 says the landlord's money
belongs.

This runs **post**-migrate, not pre: the column is created by the ORM during
the module load, so a pre-migrate script querying it fails with
`column "operating_model" does not exist`. Odoo applies the field default to
existing rows when it adds the column, so this script usually finds nothing to
do - it exists to log how many rows were assumed rather than decided, and to
catch the case where the default did not reach them.

Reversal: the column did not exist before this version, so undoing this is
dropping it.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # One statement, not a SELECT then an UPDATE: RETURNING captures exactly
    # the rows this changed, and leaves no window in which another session
    # could set one of them between the two queries.
    cr.execute(
        """
        UPDATE c2p_building
           SET operating_model = 'head_lease'
         WHERE operating_model IS NULL
        RETURNING id
        """
    )
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        _logger.info("BR-019: every building already carries an operating model.")
        return
    _logger.info(
        "BR-019: set operating_model='head_lease' on %s building(s), ids %s. "
        "To reverse, clear operating_model on exactly those ids. These were "
        "assumed, not decided - any owner-managed building must be switched "
        "by hand, which zeroes its margin and moves the tenant rent to "
        "managed_rent where BRD 6.1 says the landlord's money belongs.",
        len(ids),
        ids,
    )
