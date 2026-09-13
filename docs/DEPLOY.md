# Deploying `c2p_property_lease` to Odoo.sh

Module import over the web is disabled on Odoo.sh, so the addon goes in through
git. Modules live at the repository root, which is what Odoo.sh puts on the
addons path.

> **Before you deploy:** `c2p_property_lease` depends on `sale_subscription`
> (Enterprise). CI skips it for that reason — see the README — so its install is
> **not** verified by our pipeline. Deploy to a staging branch and check the
> build log before promoting to production.

```bash
git clone <odoo.sh repo url> sinclaire && cd sinclaire
git checkout <staging branch>
git merge <this branch>
git push origin <staging branch>
```

Odoo.sh rebuilds. Then install the app (Apps → Update Apps List → "C2P Property
& Lease Management") and add your user to the **Leasing Manager** group under
Settings → Users, or the Property menu will not appear.

## Configuration to complete after install

The module ships three service products by XML ID
(`product_residential_rent`, `product_commercial_rent`,
`product_property_management_fee`) with **no taxes set**, because the correct
tax records depend on the company's fiscal localisation. Set them before the
first invoice run:

| Product | UAE VAT treatment |
| --- | --- |
| Commercial Rent | Standard-rated, 5% |
| Residential Rent | Exempt |
| Property Management Fee | Standard-rated, 5% |

If the target database already has products with these names, reconcile them
with the module's records (repoint the XML ID via Settings → Technical →
External Identifiers) rather than leaving duplicates — subscriptions created
before the module was installed reference the pre-existing products.

## Backfilling the demo data

```bash
export ODOO_URL=https://<your-odoo.sh-build>.dev.odoo.com
export ODOO_DB=<your-database>
export ODOO_USER=admin
export ODOO_PWD=<use an API key, not the account password>

# Optional - these default to the Sinclair setup:
# export ODOO_COMPANY="New Sinclair Property Management LLC"
# export TENANT_TAG=Tenant
# export PDC_JOURNAL_CODE=PDCR

python3 tools/demo/backfill_property_data.py
```

Nothing is keyed to a fixed database id: the company is resolved by name and
the visible companies are read from the database. If the PDC journal is absent
(company 2 has none) the script says so and carries on without attaching
cheques rather than silently doing nothing.

It finishes with a reconciliation block — tenants read, units and leases
created, cheques attached, and every skipped tenant named with a reason. If the
counts do not add up it says so. Check that block before you treat the data as
good.

The script reads the existing tenants, derives their unit from the notes field,
creates the three buildings, ~54 units and 50 active leases, links each lease to
its existing rent subscription, and attaches the existing PDC payments with
cheque numbers, banks and cleared/bounced status. It is idempotent — buildings,
units and leases are matched by name and reused — and reads the building and
unit artwork from `tools/demo/demo_images/`.

Do not commit real hostnames, database names or credentials to this repository;
it is public. Use an Odoo API key rather than the admin password, and keep both
in your shell environment or a secret store.

## Notes

- Sequence `LSE/YYYY/#####` for leases.
- Two daily crons: renewal alerts at 90/60/30 days, and expiring leases
  releasing their unit.
- The landlord statement reads posted journal items by the building's analytic
  account, weighted by each line's analytic percentage, and excludes the
  module's own management-fee invoices.
- Management-fee invoices go to the company's `OWNI` journal where it exists,
  falling back to that company's sales journal.
- Rent subscriptions need the Subscriptions app. Without it the module still
  installs and everything else works; the subscription button is hidden and the
  action refuses with an explanation.
- The statement's **Rent Invoiced** figure is invoiced, not collected. A cheque
  that later bounces does not reduce it — check the PDC register before paying
  a landlord.
