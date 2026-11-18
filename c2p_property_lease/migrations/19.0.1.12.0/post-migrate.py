"""Backfill `has_bounced` for cheques that already bounced.

The dashboard's bounce rate now counts instruments that bounced *at any point*
rather than those currently sitting in the Bounced state, because BRD §3.2's
"no status may be overwritten without history" has to hold for the reporting
too: replacing a returned cheque is a recovery, not a retraction, and if a
replacement moved the cheque out of the numerator then working through the
bounces would walk the rate down to zero while the tenant's behaviour stayed
exactly as bad.

Rows that predate the flag have `has_bounced = false` with `pdc_state =
'bounced'`, which would read as "never bounced" and report a rate of zero over
the existing register. This sets the flag from the state.

post-migrate, not pre-: the column has to exist before it can be written.

`bounced_date` is deliberately left alone. The date the cheque was returned is
not recoverable from anything in the row - `maturity_date` is when it could be
banked, which is not the same thing - and inventing one would put a fabricated
date into an audit field. Empty is the honest answer.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        UPDATE account_payment
           SET has_bounced = true
         WHERE pdc_state = 'bounced'
           AND has_bounced IS NOT TRUE
        RETURNING id
        """
    )
    ids = sorted(row[0] for row in cr.fetchall())
    if not ids:
        _logger.info("c2p_property_lease: no bounced cheques to flag")
        return

    _logger.info("c2p_property_lease: flagged %s previously bounced cheque(s)", len(ids))
    _logger.info(
        "c2p_property_lease: to reverse, run - UPDATE account_payment SET has_bounced = false WHERE id IN (%s);",
        ", ".join(str(i) for i in ids),
    )
