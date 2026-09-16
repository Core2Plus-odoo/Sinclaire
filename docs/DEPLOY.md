# Deploying `c2p_property_lease` to Odoo.sh

Module import over the web is disabled on Odoo.sh, so the addon goes in through
git. Modules live at the repository root, which is what Odoo.sh puts on the
addons path.

> **Before you deploy:** CI installs and tests `c2p_property_lease` on the
> Community image, so the install itself is verified. What is *not* verified is
> the `sale_subscription` (Enterprise) path — it is a soft dependency and its
> three tests skip on Community. Deploy to a staging branch, check the build
> log, and exercise a rent subscription there before promoting to production.

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
`product_head_lease_rent`) with **no taxes set**, because the correct tax
records depend on the company's fiscal localisation. Nothing in the code
enforces these treatments — set them before the first invoice run:

| Product | Direction | UAE VAT treatment |
| --- | --- | --- |
| Commercial Rent | Sold to tenants | Standard-rated, 5% |
| Residential Rent | Sold to tenants | Exempt |
| Head Lease Rent | Payable to landlords | Per the landlord's own tax status |

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
- Four daily crons: lease renewal alerts at 90/60/30 days, expiring leases
  releasing their unit, head leases expiring when their term ends, and landlord
  cheque alerts raising an activity 14 days before each instalment falls due.
- Landlord cheques are **outbound** payments sharing the register with inbound
  tenant cheques. Issue them from the wizard on the head lease so the schedule
  matches the agreement. A bounced outbound cheque is our cheque failing
  against a head-lease obligation, and says so in the message it posts.
- Rent subscriptions need the Subscriptions app. Without it the module still
  installs and everything else works; the subscription button is hidden and the
  action refuses with an explanation.
- Coverage, margin and break-even read **contracted** rent, not collected. A
  cheque that later bounces does not reduce them — check the PDC register
  alongside the dashboard.

## Head leases are entered by hand, on purpose

The backfill script does not create head leases and will not be changed to.
They are signed commitments to pay real money, and inferring them from whatever
happens to be in the database would produce authoritative-looking numbers with
nothing behind them.

Until the signed agreements are entered, **every margin, coverage and
break-even figure reads as though the buildings cost nothing** — the dashboard
will look excellent and mean nothing. Enter them before anyone uses that screen
to make a decision.

`c2p.bank.facility` records (limits, utilisation, review dates) are likewise
entered by hand. Without them the dashboard's funding gap treats headroom as
zero, so a negative 90-day position shows as fully unfunded.

### Importing them from a CSV

For more than a handful, `tools/import_head_leases.py` takes a CSV. The
figures still come off the signed agreements — the tool transcribes, it does
not infer.

```bash
cp tools/head_leases_template.csv myleases.csv    # one row per building; fill in the numbers
python3 tools/import_head_leases.py myleases.csv  # DRY RUN - reports, writes nothing
python3 tools/import_head_leases.py myleases.csv --commit
```

The dry run resolves every building code and landlord name, applies the same
rules the model enforces (term, amount, cheque count, and whether an active
row would clash with an existing agreement) and prints each row as it would be
written, with the instalment worked out. Nothing is written if any row has a
problem, so a typo cannot leave half a portfolio imported.

Leave `date_end` blank for a one-year term and it fills in the day before the
anniversary; leave `landlord` blank to take the building's owner. Rows are
matched on building and start date, so a corrected CSV can be re-run without
duplicating anything.

Import as `draft`, read the coverage and break-even figures, and activate only
once they look right — the dashboard counts active head leases, and only
active ones are checked for overlap.

## Sample data for a demo database

For a demo or training database with no real tenants, skip the backfill and use
**Property → Configuration → Load Sample Portfolio**. It builds buildings,
units, leases, head leases, cheques both ways and bank facilities, is
idempotent, and deliberately includes buildings underwritten below cost so the
dashboard's warning states are visible. Do not run it against a database
holding real client data.
