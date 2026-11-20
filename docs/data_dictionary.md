# Data dictionary

Required by BRD §8.3.4, which closes with: *"The developer shall confirm actual
model names and installed Odoo edition/version, identify which fields are
standard versus custom, and return a final data dictionary… No proposed `x_`
field shall be treated as approved until blueprint sign-off."*

This document is that return. It has two halves:

1. **The naming decision and BRD mapping** — hand-written, below. This is what
   needs sign-off.
2. **The as-built field list** — generated from the module source by
   `tools/gen_data_dictionary.py`, between the markers near the end. Never
   edited by hand; CI fails if it drifts from the code.

**Edition and version confirmed:** Odoo **19.0 Enterprise** on Odoo.sh. Python
3.12 in CI; Odoo 19.0 itself requires ≥ 3.10.

---

## 1. The `x_` prefix: recommended against, with reasons

The BRD's §8.3.4 and §8.3.5 mapping tables propose names like
`x_property_building`, `x_building_code`, `x_property_lease`. The BRD marks
these as *proposed* and asks the developer to confirm. **The recommendation is
not to adopt the `x_` prefix, and not to rename the models already built.**

| | BRD proposal | Recommendation |
| --- | --- | --- |
| Models | `x_property_building`, `x_property_unit`, `x_property_lease`, `x_property_contract` | `c2p.building`, `c2p.unit`, `c2p.lease`, `c2p.head.lease` |
| Fields | `x_building_code`, `x_annual_rent`, `x_unit_code` | `code`, `annual_rent`, `name` |

**Why.**

`x_` is Odoo's marker for fields and models created through **Studio**, in the
database, by a user — not written in a module. The BRD itself requires the
opposite: §8.3.4 says the property objects "require a dedicated Property
Management module". A module's fields are ordinary Python attributes; prefixing
them `x_` says "this was clicked into existence" about code that was not, and
every future developer reads that signal wrongly. `CONTRIBUTING.md` already
carries the rule: keep `x_` only where a field must stay Studio-compatible.

Two practical reasons on top. The models in the first column **already exist,
are installed on the production database and hold live data** — renaming them
is a migration with no functional gain. And `x_` on every field makes
`rec.x_annual_rent / rec.x_payment_count` the house style for the next 26 weeks,
which is noise in every line of code anyone writes.

**What is preserved instead.** Section 3 below maps every BRD-proposed name to
its implemented name, so the BRD's mapping tables remain traceable. Nothing is
lost but the prefix.

**This needs sign-off**, per §8.3.4. If the client requires the `x_` convention
for a reason not visible here — a Studio-based support model, an existing
internal standard — say so and it will be applied to new fields; the existing
models should still not be renamed.

---

## 2. Columns, and which are not yet fillable

§8.3.4 asks for: field label, technical name, model, type, length, selection
values, mandatory condition, default, source, validation, security group,
import key, reporting use, migration rule.

The generated section carries label, technical name, model, type, mandatory,
default, selection values, comodel, computed/stored and tracked — everything
derivable from the field definition.

Four columns are **not** derivable and are not guessed here:

| Column | Why it is blank | Unblocked by |
| --- | --- | --- |
| Security group | No role-to-field mapping has been agreed | **OD-06** |
| Import key | Depends on the agreed migration identifiers | **OD-09** |
| Reporting use | Follows the report catalogue | `report_catalogue.md` |
| Migration rule | Depends on source data shape and volumes | **OD-09** |

`length` is omitted deliberately: Odoo `Char` fields have a `size` only when one
is set, and none here set one. A column of empty cells would imply a constraint
that does not exist.

---

## 3. BRD proposed name → implemented name

Traceability from the §8.3.4 / §8.3.5 mapping tables to the code. **Built**
means it exists today; **planned** means the BRD requires it and it is not built
yet, so the implemented name is the intended one and may still change at build.

### Building — BRD `x_property_building` → `c2p.building`

| BRD proposed | Implemented | Status |
| --- | --- | --- |
| `name` | `name` | built |
| `x_building_code` | `code` | built |
| `x_owner_id` | `owner_id` | built |
| `company_id` | `company_id` | built |
| `x_analytic_account_id` | `analytic_account_id` | built |
| `active` | `active` | built |
| `x_entrance_location` | `entrance_location` | planned |
| `x_plot_number` | `plot_number` | planned |
| `x_municipality_number` | `municipality_number` | planned |
| `x_declared_residential_units` | `declared_residential_units` | planned |
| `x_declared_commercial_units` | `declared_commercial_units` | planned |
| `x_operating_model` | `operating_model` | planned |

Control-total rule (§8.3.4): the declared counts are **control totals, not
calculated occupancy**. Unit import reconciles created residential and
commercial units against them and reports mismatches.

### Unit — BRD `x_property_unit` → `c2p.unit`

| BRD proposed | Implemented | Status |
| --- | --- | --- |
| `x_unit_code` | `name` | built |
| `x_building_id` | `building_id` | built |
| `x_unit_type_id` | `unit_type` | built — selection, not a model |
| `x_status` | `state` | built — **4 of 10 BRD states**, see `status_matrix.md` |
| `x_market_rent` | `market_rent` | built |
| `x_area_sqft` | `area_sqft` | built |
| `x_floor` | `floor` | planned |
| `x_permitted_use` | `permitted_use` | planned |
| `x_area_sqm` | `area_sqm` | planned — **one controlled source, the other computed** (§8.3.4) |
| `x_kitchen_type` | `kitchen_type` | planned |
| `x_bath_count`, `x_balcony_count` | `bath_count`, `balcony_count` | planned |
| `x_dewa_premise_number` | `dewa_premise_number` | planned |
| `x_furnishing_status` | `furnishing_status` | planned |
| `x_minimum_rent` | `minimum_rent` | planned — drives the price-override block, BR-036 |

### Head lease / management contract — BRD `x_property_contract`

The BRD maps one object. **The recommendation is two**, because the BRD itself
describes two different economic relationships (§4.1.1):

| BRD proposed | Implemented | Status |
| --- | --- | --- |
| `x_property_contract` (operating model = head lease) | `c2p.head.lease` | built |
| `x_property_contract` (operating model = owner management) | `c2p.management.contract` | planned |

Under a head lease Sinclair owns the tenancy income and carries vacancy; under
owner management the landlord owns the income and Sinclair earns a fee and
never touches the money. Sharing one model would mean one record whose
accounting, payee, cheque custody, statement and profitability behaviour all
fork on a selection field — and the client-money rule in §6.3.1 would be a
conditional branch rather than a structural separation. Two models keep owner
funds unable to reach company revenue by construction.

Field mapping for the built head lease:

| BRD proposed | Implemented | Status |
| --- | --- | --- |
| `x_building_id` | `building_id` | built |
| `partner_id` | `landlord_id` | built |
| `x_contract_amount` / `x_annual_commitment` | `annual_amount` | built |
| `date_start`, `date_end` | `date_start`, `date_end` | built |
| `state` | `state` | built |
| `x_operating_model` | on the building | built |
| `x_grace_period_days` | `grace_period_days` | planned |
| `x_renewal_status`, `x_notice_date` | `renewal_status`, `notice_date` | planned |
| `x_expected_annual_revenue` | `contracted_rent` (computed, live) | built — **computed from live data, never an editable field** (§8.3.4) |

### Tenancy — BRD `x_property_lease` → `c2p.lease`

| BRD proposed | Implemented | Status |
| --- | --- | --- |
| `partner_id` | `tenant_id` | built |
| `x_unit_id` | `unit_id` | built |
| `date_start`, `date_end` | `date_start`, `date_end` | built |
| `x_annual_rent` | `annual_rent` | built |
| `x_payment_count` | `cheque_count` | built |
| `x_security_deposit` | `security_deposit` | built |
| `state` | `state` | built — **5 of 12 BRD states** |
| `x_ejari_number`, `x_ejari_status` | `ejari_number`, `ejari_status` | planned |
| `x_monthly_rent` | `monthly_rent` | planned |
| `x_renewal_intention` | `renewal_intention` | planned |
| `x_previous_lease_id` | `previous_lease_id` | planned |
| `x_dewa_clearance_status` | `dewa_clearance_status` | planned |

### Payment instrument — BRD `x_payment_instrument`

The BRD proposes a dedicated custody object. **Implemented as fields on
`account.payment`**, which already carries partner, amount, currency, journal
and the accounting link, and gives tenant and landlord cheques one register —
which §6.2 asks for.

| BRD proposed | Implemented | Status |
| --- | --- | --- |
| `x_instrument_number` | `cheque_no` | built |
| `x_maturity_date` | `maturity_date` | built |
| `state` | `pdc_state` | built — **4 of 7 BRD states**; `expected`, `replaced`, `cancelled` missing |
| `x_is_undated` | `is_undated` | planned — **undated cheques are never cleared cash** (§6.2) |
| `x_custody_location_id` | `custody_location_id` | planned |
| `x_replacement_instrument_id` | `replacement_instrument_id` | planned |
| `x_cleared_date`, `x_returned_date` | `cleared_date`, `returned_date` | planned |
| `x_payee_id` | `payee_id` | planned — landlord-name cheques, §6.3.1 |

### Compliance — BRD `x_property_compliance` → `c2p.property.compliance`

Planned in full. One typed model for insurance, TPL, lift, fire, Civil Defence,
BMS and AMCs, per §8.3.4's instruction to "use the same model" for all of them,
with 90/60/30-day activities and a hard block on contract activation where
mandatory cover is missing or expired.

### Remaining planned models

Named here so the BRD mapping resolves; fields will be added as each is built.

| BRD proposed | Implemented | Phase |
| --- | --- | --- |
| `x_property_amenity` | `c2p.property.amenity` | S2 |
| `x_contract_recognition_line` | `c2p.contract.recognition.line` | S2 |
| `x_tenancy_checklist`, `x_tenancy_checklist_line` | `c2p.tenancy.checklist`, `.line` | S2 |
| `x_partner_document` | `c2p.partner.document` | S2 |
| `x_lease_clause`, `x_clause_set`, `x_lease_addendum` | `c2p.lease.clause`, `c2p.clause.set`, `c2p.lease.addendum` | S3 |
| `x_handover_template`, `x_handover_template_line` | `c2p.handover.template`, `.line` | S3 |
| `x_property_handover`, `x_handover_item` | `c2p.property.handover`, `c2p.handover.item` | S3 |
| `x_property_meter`, `x_meter_reading` | `c2p.property.meter`, `c2p.meter.reading` | S3 |
| `x_access_item`, `x_access_custody_line` | `c2p.access.item`, `c2p.access.custody.line` | S3 |
| `x_tenant_fitout` | `c2p.tenant.fitout` | S3 |
| `x_property_listing`, `x_brokerage_mandate` | `c2p.property.listing`, `c2p.brokerage.mandate` | S3 |
| `x_property_requirement` | `c2p.property.requirement` | S3 |
| `x_brokerage_transaction` | `c2p.brokerage.transaction` | S3 |
| `x_commission_entitlement`, `x_commission_split` | `c2p.commission.entitlement`, `c2p.commission.split` | S3 |
| `x_unit_pricing_scenario` | `c2p.unit.pricing.scenario` | S3 |
| `x_salary_transfer_batch`, `x_salary_transfer_line` | `c2p.salary.transfer.batch`, `.line` | S4 |
| `x_employee_letter_request` | `c2p.employee.letter.request` | S4 |
| (IFRS 16) | `c2p.lease.accounting` | S4 |

Three BRD proposals are **deliberately not custom models**:

- `x_employee_number` → `hr.employee.barcode` or a plain field on `hr.employee`;
  the BRD offers both and standard is enough.
- Payroll objects → `hr.payslip.run`, `hr.payslip`, `hr.payslip.line` as the BRD
  maps them. Standard Odoo Payroll, not a parallel model.
- `x_routing_code`, `x_payroll_identifier` → fields on `res.partner.bank` and
  `hr.employee`, not a new object.

---

## 4. Rules that apply to every field

From §8.3.4's cross-template services and §8.4:

- Every model holding money or company data carries `company_id` with
  `_check_company_auto = True` and a multi-company record rule.
- Every posted revenue, expense, deposit, receivable, payable and bank line
  carries company, partner, account, currency, the **building analytic account**
  and unit/lease analytic dimensions where applicable.
- Identity, bank and salary fields are restricted, masked on export, and their
  export is logged. Creation and change of bank details requires maker-checker.
- Forecast and scenario values are a **distinct data type and never post** to
  the ledger.
- Import staging retains template ID, workbook, worksheet, source row, batch,
  uploader, validation result, target model, target record and rejection reason.

---

## 5. As-built fields

<!-- BEGIN GENERATED: as-built fields -->

<!-- Generated by tools/gen_data_dictionary.py. Do not edit by hand.
     On a merge conflict here, do NOT resolve it line by line: keep
     either side, run `python tools/gen_data_dictionary.py`, and commit
     the result. The CI gate verifies this section matches the source. -->

Generated by `tools/gen_data_dictionary.py` from the module source. Do not edit between the markers — edit the field definition and regenerate.

**On a merge conflict in this section**, do not resolve it line by line: keep either side, re-run the generator, and commit that. Two branches that each add a field both rewrite this file, so conflicts here are routine and never meaningful.

**18 models, 319 fields** as built today.

### `account.move`

extension of a standard model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `c2p_building_id` | Building | Many2one |  |  | c2p.building |  |  |

### `account.payment`

extension of a standard model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bounce_charge` |  | Monetary |  |  |  |  |  |
| `bounce_reason` |  | Char |  |  |  |  |  |
| `bounced_date` |  | Date |  |  |  |  |  |
| `building_id` |  | Many2one |  |  | related: lease_id.building_id |  |  |
| `cheque_bank` | Drawn On | Char |  |  |  |  |  |
| `cheque_no` | Cheque No. | Char |  |  |  |  |  |
| `collection_alert` | Needs Attention | Char |  |  |  | _compute_collection (not stored) |  |
| `collection_bucket` | Bucket | Selection |  |  | missing, overdue, due_soon, later, bounced, settled, closed | _compute_collection (not stored) |  |
| `collection_tone` |  | Selection |  |  | ok, warn, critical | _compute_collection (not stored) |  |
| `days_to_maturity` | Days | Integer |  |  |  | _compute_collection (not stored) |  |
| `drawer_partner_id` | Drawer | Many2one |  |  | res.partner |  |  |
| `funds_label` | Funds | Char |  |  |  | _compute_funds_label (not stored) |  |
| `has_bounced` | Ever Bounced | Boolean |  |  |  |  |  |
| `head_lease_id` | Head Lease | Many2one |  |  | c2p.head.lease |  |  |
| `is_landlord_cheque` |  | Boolean |  |  |  | _compute_is_landlord_cheque (stored) |  |
| `is_owner_funds` | Owner Funds | Boolean |  |  |  | _compute_payee (stored) |  |
| `is_pdc` | Post-Dated Cheque | Boolean |  |  |  | _compute_is_pdc (stored) |  |
| `is_third_party` |  | Boolean |  |  |  | _compute_third_party (stored) |  |
| `lease_id` | Lease | Many2one |  |  | c2p.lease |  |  |
| `maturity_date` |  | Date |  |  |  |  |  |
| `operating_model` | Operating Model | Selection |  |  | related: building_id.operating_model |  |  |
| `owner_deposit_bank_id` | Deposited Into | Many2one |  |  | res.partner.bank |  |  |
| `payee_partner_id` | Payee | Many2one |  |  | res.partner | _compute_payee (stored) |  |
| `pdc_state` |  | Selection |  | held | dynamic |  | yes |
| `replacement_payment_id` | Replaced By | Many2one |  |  | account.payment |  |  |
| `unit_id` |  | Many2one |  |  | related: lease_id.unit_id |  |  |

### `c2p.bank.facility`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `active` |  | Boolean |  | True |  |  |  |
| `available_amount` |  | Monetary |  |  |  | _compute_available (stored) |  |
| `bank_id` | Bank | Many2one | yes |  | res.bank |  |  |
| `company_id` |  | Many2one | yes | lambda self: self.env.company | res.company |  |  |
| `currency_id` |  | Many2one |  |  | related: company_id.currency_id |  |  |
| `facility_type` |  | Selection | yes | overdraft | overdraft, cheque_discounting, term_loan, guarantee, other |  |  |
| `journal_id` |  | Many2one |  |  | account.journal |  |  |
| `limit_amount` | Limit | Monetary | yes |  |  |  |  |
| `name` |  | Char | yes |  |  |  |  |
| `review_date` |  | Date |  |  |  |  |  |
| `utilisation_pct` | Utilised % | Float |  |  |  | _compute_available (stored) |  |
| `utilised_amount` | Utilised | Monetary |  |  |  |  |  |

### `c2p.building`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `active` |  | Boolean |  | True |  |  |  |
| `amenities` | Amenities | Text |  |  |  |  |  |
| `analytic_account_id` | Analytic Account | Many2one |  |  | account.analytic.account |  |  |
| `breakeven_occupancy` | Break-even Occupancy % | Float |  |  |  | _compute_head_lease (not stored) |  |
| `city` |  | Char |  | Dubai |  |  |  |
| `code` |  | Char | yes |  |  |  |  |
| `community` |  | Char |  |  |  |  |  |
| `company_id` |  | Many2one | yes | lambda self: self.env.company | res.company |  |  |
| `contracted_rent` | Contracted Annual Rent | Monetary |  |  |  | _compute_unit_stats (stored) |  |
| `coverage_ratio` | Coverage | Float |  |  |  | _compute_head_lease (not stored) |  |
| `currency_id` |  | Many2one |  |  | related: company_id.currency_id |  |  |
| `declared_commercial_units` | Declared Commercial Units | Integer |  |  |  |  |  |
| `declared_residential_units` | Declared Residential Units | Integer |  |  |  |  |  |
| `declared_unit_count` | Declared Units | Integer |  |  |  | _compute_declared (stored) |  |
| `gross_margin` |  | Monetary |  |  |  | _compute_head_lease (not stored) |  |
| `handover_condition` | Handover Condition | Selection |  |  | shell, fitted, furnished |  |  |
| `handover_date` | Handed Over On | Date |  |  |  |  |  |
| `head_lease_cost` |  | Monetary |  |  |  | _compute_head_lease (not stored) |  |
| `head_lease_id` | Current Head Lease | Many2one |  |  | c2p.head.lease | _compute_head_lease (not stored) |  |
| `head_lease_ids` | Head Leases | One2many |  |  | c2p.head.lease |  |  |
| `makani_no` | Makani No. | Char |  |  |  |  |  |
| `managed_rent` | Rent Administered for the Owner | Monetary |  |  |  | _compute_unit_stats (stored) |  |
| `municipality_no` | Municipality No. | Char |  |  |  |  | yes |
| `name` |  | Char | yes |  |  |  | yes |
| `occupancy_rate` | Occupancy % | Float |  |  |  | _compute_unit_stats (stored) |  |
| `occupied_count` |  | Integer |  |  |  | _compute_unit_stats (stored) |  |
| `operating_model` |  | Selection | yes | head_lease | dynamic |  | yes |
| `owner_id` | Landlord | Many2one | yes |  | res.partner |  | yes |
| `plot_no` | Plot No. | Char |  |  |  |  | yes |
| `portfolio_alert` | Needs Attention | Char |  |  |  | _compute_portfolio_alert (not stored) |  |
| `portfolio_money` |  | Monetary |  |  |  | _compute_portfolio_money (not stored) |  |
| `portfolio_money_display` | Card Figure | Char |  |  |  | _compute_portfolio_money (not stored) |  |
| `portfolio_money_label` |  | Char |  |  |  | _compute_portfolio_money (not stored) |  |
| `portfolio_tone` |  | Selection |  |  | ok, warn, critical | _compute_portfolio_alert (not stored) |  |
| `potential_rent` | Market Rent of All Units | Monetary |  |  |  | _compute_unit_stats (stored) |  |
| `street` |  | Char |  |  |  |  |  |
| `unit_count` |  | Integer |  |  |  | _compute_unit_stats (stored) |  |
| `unit_ids` | Units | One2many |  |  | c2p.unit |  |  |
| `unit_variance` | Variance | Integer |  |  |  | _compute_unit_stats (stored) |  |
| `units_reconciled` |  | Boolean |  |  |  | _compute_unit_stats (stored) |  |
| `vacant_count` |  | Integer |  |  |  | _compute_unit_stats (stored) |  |

### `c2p.ceo.dashboard`

custom model — `c2p_ceo_command_center`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `active_lease_count` |  | Integer |  |  |  | _compute_leases (not stored) |  |
| `avg_rent_per_sqft` | Rent per sq ft | Float |  |  |  | _compute_portfolio (not stored) |  |
| `avg_rent_per_unit` | Average Rent | Monetary |  |  |  | _compute_portfolio (not stored) |  |
| `bounce_rate` | Bounce Rate % | Float |  |  |  | _compute_cheques (not stored) |  |
| `breakeven_occupancy` | Break-even Occupancy % | Float |  |  |  | _compute_underwriting (not stored) |  |
| `building_count` |  | Integer |  |  |  | _compute_portfolio (not stored) |  |
| `buildings_below_cost` | Buildings Below Cost | Integer |  |  |  | _compute_underwriting (not stored) |  |
| `company_id` |  | Many2one | yes | lambda self: self.env.company | res.company |  |  |
| `contracted_rent` |  | Monetary |  |  |  | _compute_portfolio (not stored) |  |
| `coverage_ratio` | Coverage | Float |  |  |  | _compute_underwriting (not stored) |  |
| `currency_id` |  | Many2one |  |  | related: company_id.currency_id |  |  |
| `date_from` |  | Date | yes | lambda self: fields.Date.context_today(self).replace(month=1, day=1) |  |  |  |
| `date_to` |  | Date | yes | fields.Date.context_today |  |  |  |
| `expiring_30` | Within 30 Days | Integer |  |  |  | _compute_leases (not stored) |  |
| `expiring_60` | 31-60 Days | Integer |  |  |  | _compute_leases (not stored) |  |
| `expiring_90` | 61-90 Days | Integer |  |  |  | _compute_leases (not stored) |  |
| `expiring_lease_count` | Expiring in 90 Days | Integer |  |  |  | _compute_leases (not stored) |  |
| `expiring_rent` | Rent at Risk | Monetary |  |  |  | _compute_leases (not stored) |  |
| `facility_available` | Headroom | Monetary |  |  |  | _compute_cash (not stored) |  |
| `facility_limit` | Facility Limit | Monetary |  |  |  | _compute_cash (not stored) |  |
| `facility_utilisation` | Facilities Used % | Float |  |  |  | _compute_cash (not stored) |  |
| `funding_gap` |  | Monetary |  |  |  | _compute_cash (not stored) |  |
| `gross_margin` |  | Monetary |  |  |  | _compute_underwriting (not stored) |  |
| `head_lease_cost` | Committed to Landlords | Monetary |  |  |  | _compute_underwriting (not stored) |  |
| `landlord_bounced_count` | Our Cheques Bounced | Integer |  |  |  | _compute_landlord_cheques (not stored) |  |
| `landlord_due_30` | Due in 30 Days | Monetary |  |  |  | _compute_landlord_cheques (not stored) |  |
| `landlord_due_90` | Due in 90 Days | Monetary |  |  |  | _compute_landlord_cheques (not stored) |  |
| `landlord_outstanding` | Issued, Not Cleared | Monetary |  |  |  | _compute_landlord_cheques (not stored) |  |
| `lease_at_risk_rate` | Portfolio at Risk % | Float |  |  |  | _compute_leases (not stored) |  |
| `margin_pct` | Margin % | Float |  |  |  | _compute_underwriting (not stored) |  |
| `net_position_90` | Net 90-Day Position | Monetary |  |  |  | _compute_cash (not stored) |  |
| `occupancy_rate` | Occupancy % | Float |  |  |  | _compute_portfolio (not stored) |  |
| `occupied_count` |  | Integer |  |  |  | _compute_portfolio (not stored) |  |
| `overdue_receivable` | Overdue | Monetary |  |  |  | _compute_income (not stored) |  |
| `pdc_bounced_amount` | Bounced | Monetary |  |  |  | _compute_cheques (not stored) |  |
| `pdc_bounced_count` |  | Integer |  |  |  | _compute_cheques (not stored) |  |
| `pdc_cleared_amount` | Cleared | Monetary |  |  |  | _compute_cheques (not stored) |  |
| `pdc_cleared_count` |  | Integer |  |  |  | _compute_cheques (not stored) |  |
| `pdc_deposited_amount` | Deposited | Monetary |  |  |  | _compute_cheques (not stored) |  |
| `pdc_deposited_count` |  | Integer |  |  |  | _compute_cheques (not stored) |  |
| `pdc_ever_bounced_count` | Ever Bounced | Integer |  |  |  | _compute_cheques (not stored) |  |
| `pdc_expected_amount` | Cheques Expected | Monetary |  |  |  | _compute_cheques (not stored) |  |
| `pdc_expected_count` |  | Integer |  |  |  | _compute_cheques (not stored) |  |
| `pdc_held_amount` | Cheques in Hand | Monetary |  |  |  | _compute_cheques (not stored) |  |
| `pdc_held_count` |  | Integer |  |  |  | _compute_cheques (not stored) |  |
| `rent_invoiced` |  | Monetary |  |  |  | _compute_income (not stored) |  |
| `tenant_inflow_90` | Tenant Cheques In | Monetary |  |  |  | _compute_cash (not stored) |  |
| `unit_count` |  | Integer |  |  |  | _compute_portfolio (not stored) |  |
| `vacant_count` |  | Integer |  |  |  | _compute_portfolio (not stored) |  |
| `vacant_market_rent` | Revenue Foregone | Monetary |  |  |  | _compute_portfolio (not stored) |  |

### `c2p.head.lease`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `activation_blockers` | Still Missing | Char |  |  |  | _compute_activation (not stored) |  |
| `agreement_ref` | Agreement Reference | Char |  |  |  |  | yes |
| `annual_amount` | Annual Amount Payable | Monetary | yes |  |  |  | yes |
| `breakeven_occupancy` | Break-even Occupancy % | Float |  |  |  | _compute_margin (stored) |  |
| `building_id` |  | Many2one | yes |  | c2p.building |  | yes |
| `cheque_count` | Paid In | Selection | yes | 4 | 1, 2, 3, 4, 6, 12 |  |  |
| `cheque_count_issued` |  | Integer |  |  |  | _compute_cheque_position (not stored) |  |
| `collection_party` | Rent Collected In The Name Of | Selection |  |  | dynamic |  | yes |
| `company_id` |  | Many2one | yes | lambda self: self.env.company | res.company |  |  |
| `contracted_rent` | Contracted Tenant Rent | Monetary |  |  | related: building_id.contracted_rent |  |  |
| `contracting_party` | Tenancy Contracts Signed By | Selection |  |  | dynamic |  | yes |
| `coverage_ratio` | Coverage | Float |  |  |  | _compute_margin (stored) |  |
| `currency_id` |  | Many2one |  |  | related: company_id.currency_id |  |  |
| `date_end` |  | Date | yes |  |  |  | yes |
| `date_signed` | Signed On | Date |  |  |  |  | yes |
| `date_start` |  | Date | yes | fields.Date.context_today |  |  | yes |
| `ejari_date` | Ejari Registered On | Date |  |  |  |  |  |
| `ejari_no` | Ejari No. | Char |  |  |  |  | yes |
| `escalation_pct` | Escalation % | Float |  |  |  |  |  |
| `free_period_days` | Rent-Free Days | Integer |  |  |  |  |  |
| `gross_margin` |  | Monetary |  |  |  | _compute_margin (stored) |  |
| `instalment_amount` |  | Monetary |  |  |  | _compute_instalment (stored) |  |
| `insurance_expiry` | Insurance Expires | Date |  |  |  |  | yes |
| `is_activatable` |  | Boolean |  |  |  | _compute_activation (not stored) |  |
| `landlord_bank_id` | Landlord Bank Account | Many2one |  |  | res.partner.bank |  |  |
| `landlord_id` | Landlord | Many2one | yes |  | res.partner |  | yes |
| `margin_pct` | Margin % | Float |  |  |  | _compute_margin (stored) |  |
| `may_appoint_legal` | May Appoint Legal Representatives | Boolean |  |  |  |  |  |
| `may_place_signage` | May Market And Place Signage | Boolean |  | True |  |  |  |
| `may_pursue_arrears` | May Pursue Arrears | Boolean |  | True |  |  |  |
| `may_register_ejari` | May Register Ejari | Boolean |  | True |  |  |  |
| `name` |  | Char |  | New |  |  |  |
| `outstanding_amount` | Still to Clear | Monetary |  |  |  | _compute_cheque_position (not stored) |  |
| `paid_amount` | Cleared | Monetary |  |  |  | _compute_cheque_position (not stored) |  |
| `payment_ids` | Landlord Cheques | One2many |  |  | account.payment |  |  |
| `potential_rent` | Market Rent of All Units | Monetary |  |  | related: building_id.potential_rent |  |  |
| `renewal_ids` | Renewed By | One2many |  |  | c2p.head.lease |  |  |
| `renewal_of_id` | Renewal Of | Many2one |  |  | c2p.head.lease |  |  |
| `security_deposit` |  | Monetary |  |  |  |  |  |
| `state` |  | Selection | yes | draft | draft, active, expired, terminated |  | yes |
| `sublease_permitted` | Subleasing Permitted | Boolean |  |  |  |  |  |

### `c2p.landlord.cheque.line`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `amount` |  | Monetary | yes |  |  |  |  |
| `cheque_no` | Cheque No. | Char |  |  |  |  |  |
| `currency_id` |  | Many2one |  |  | related: wizard_id.currency_id |  |  |
| `maturity_date` |  | Date | yes |  |  |  |  |
| `wizard_id` |  | Many2one | yes |  | c2p.landlord.cheque.register |  |  |

### `c2p.landlord.cheque.register`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `company_id` |  | Many2one |  |  | related: head_lease_id.company_id |  |  |
| `currency_id` |  | Many2one |  |  | related: head_lease_id.currency_id |  |  |
| `first_cheque_no` | First Cheque No. | Char |  |  |  |  |  |
| `first_maturity` |  | Date | yes |  |  |  |  |
| `head_lease_id` |  | Many2one | yes |  | c2p.head.lease |  |  |
| `journal_id` |  | Many2one | yes |  | account.journal |  |  |
| `line_ids` |  | One2many |  |  | c2p.landlord.cheque.line |  |  |

### `c2p.lease`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `annual_rent` |  | Monetary | yes |  |  |  | yes |
| `below_floor_approved` | Below-Floor Rent Approved | Boolean |  |  |  |  | yes |
| `building_id` |  | Many2one |  |  | related: unit_id.building_id |  |  |
| `cheque_count` | Payment Cheques | Selection | yes | 4 | 1, 2, 3, 4, 6, 12 |  |  |
| `cheque_cover` | Rent Covered by Cheques | Monetary |  |  |  | _compute_cheque_cover (stored) |  |
| `cheque_exception_count` |  | Integer |  |  |  | _compute_cheque_exceptions (not stored) |  |
| `cheque_exception_ids` | Cheque Exceptions | One2many |  |  | c2p.lease.cheque.exception |  |  |
| `cheque_shortfall` |  | Monetary |  |  |  | _compute_cheque_cover (stored) |  |
| `cheques_complete` |  | Boolean |  |  |  | _compute_cheque_cover (stored) |  |
| `cheques_expected` |  | Integer |  |  |  | _compute_cheque_cover (stored) |  |
| `cheques_received` |  | Integer |  |  |  | _compute_cheque_cover (stored) |  |
| `commission` |  | Monetary |  |  |  |  |  |
| `company_id` |  | Many2one | yes | lambda self: self.env.company | res.company |  |  |
| `currency_id` |  | Many2one |  |  | related: company_id.currency_id |  |  |
| `date_end` |  | Date | yes |  |  |  | yes |
| `date_start` |  | Date | yes | fields.Date.context_today |  |  | yes |
| `days_to_expiry` |  | Integer |  |  |  | _compute_days_to_expiry (not stored) |  |
| `dewa_no` | DEWA Premise No. | Char |  |  |  |  |  |
| `ejari_date` | Ejari Registered On | Date |  |  |  |  |  |
| `ejari_no` | Ejari No. | Char |  |  |  |  | yes |
| `floor_rent` | Unit Floor Rent | Monetary |  |  | related: unit_id.floor_rent |  |  |
| `has_open_cheque_exception` |  | Boolean |  |  |  | _compute_cheque_exceptions (not stored) |  |
| `instalment_amount` |  | Monetary |  |  |  | _compute_instalment (stored) |  |
| `is_commercial` |  | Boolean |  |  |  | _compute_is_commercial (stored) |  |
| `name` |  | Char |  | New |  |  |  |
| `owner_id` | Landlord | Many2one |  |  | related: building_id.owner_id |  |  |
| `payment_ids` | Cheques | One2many |  |  | account.payment |  |  |
| `pdc_count` |  | Integer |  |  |  | _compute_pdc (not stored) |  |
| `pdc_pending` | Cheques Outstanding | Monetary |  |  |  | _compute_pdc (not stored) |  |
| `renewed_from_id` |  | Many2one |  |  | c2p.lease |  |  |
| `security_deposit` |  | Monetary |  |  |  |  |  |
| `state` |  | Selection | yes | draft | dynamic |  | yes |
| `subscription_id` | Rent Subscription | Many2one |  |  | sale.order |  |  |
| `subscriptions_available` |  | Boolean |  |  |  | _compute_subscriptions_available (not stored) |  |
| `tenant_id` | Tenant | Many2one | yes |  | res.partner |  | yes |
| `unit_id` |  | Many2one | yes |  | c2p.unit |  | yes |

### `c2p.lease.cheque.exception`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `activation_date` |  | Datetime |  |  |  |  |  |
| `approval_date` |  | Datetime |  |  |  |  |  |
| `approved_by_id` | Decided By | Many2one |  |  | res.users |  | yes |
| `company_id` |  | Many2one |  |  | related: lease_id.company_id |  |  |
| `conditions` |  | Text | yes |  |  |  |  |
| `currency_id` |  | Many2one |  |  | related: company_id.currency_id |  |  |
| `deadline` |  | Date | yes |  |  |  | yes |
| `decision_note` |  | Text |  |  |  |  |  |
| `expected_cheque_count` |  | Integer |  |  |  |  |  |
| `is_overdue` |  | Boolean |  |  |  | _compute_outstanding (not stored) |  |
| `lease_id` |  | Many2one | yes |  | c2p.lease |  | yes |
| `missing_amount` |  | Monetary |  |  |  |  |  |
| `missing_cheque_count` |  | Integer |  |  |  |  |  |
| `outstanding_amount` |  | Monetary |  |  |  | _compute_outstanding (not stored) |  |
| `outstanding_cheque_count` |  | Integer |  |  |  | _compute_outstanding (not stored) |  |
| `reason` |  | Text | yes |  |  |  |  |
| `received_cheque_count` |  | Integer |  |  |  |  |  |
| `requested_by_id` | Requested By | Many2one | yes | lambda self: self.env.user | res.users |  |  |
| `responsible_user_id` | Responsible | Many2one | yes |  | res.users |  | yes |
| `state` |  | Selection | yes | draft | dynamic |  | yes |
| `tenant_id` |  | Many2one |  |  | related: lease_id.tenant_id |  |  |
| `unit_id` |  | Many2one |  |  | related: lease_id.unit_id |  |  |

### `c2p.lease.renew`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cheque_count` |  | Selection |  |  | related: lease_id.cheque_count |  |  |
| `currency_id` |  | Many2one |  |  | related: lease_id.currency_id |  |  |
| `current_rent` | Current Rent | Monetary |  |  | related: lease_id.annual_rent |  |  |
| `date_end` |  | Date | yes |  |  |  |  |
| `date_start` |  | Date | yes |  |  |  |  |
| `increase_pct` | Increase % | Float |  |  |  | _compute_increase (not stored) |  |
| `lease_id` |  | Many2one | yes |  | c2p.lease |  |  |
| `new_rent` |  | Monetary | yes |  |  |  |  |
| `rera_warning` |  | Char |  |  |  | _compute_increase (not stored) |  |

### `c2p.lease.terminate`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `currency_id` |  | Many2one |  |  | related: lease_id.currency_id |  |  |
| `date_termination` |  | Date | yes | fields.Date.context_today |  |  |  |
| `deduction` | Deductions | Monetary |  |  |  |  |  |
| `deduction_reason` |  | Char |  |  |  |  |  |
| `deposit_held` | Deposit Held | Monetary |  |  | related: lease_id.security_deposit |  |  |
| `lease_id` |  | Many2one | yes |  | c2p.lease |  |  |
| `refund_amount` |  | Monetary |  |  |  | _compute_refund (not stored) |  |

### `c2p.pdc.register`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bank_name` | Drawn On | Char | yes |  |  |  |  |
| `currency_id` |  | Many2one |  |  | related: lease_id.currency_id |  |  |
| `first_cheque_no` |  | Char | yes |  |  |  |  |
| `first_maturity` |  | Date | yes | fields.Date.context_today |  |  |  |
| `journal_id` | PDC Journal | Many2one | yes | lambda self: self.env['account.journal'].search([('code', '=', 'PDCR'), ('company_id', '=', self.env.company.id)], limit=1) | account.journal |  |  |
| `lease_id` |  | Many2one | yes |  | c2p.lease |  |  |
| `line_ids` | Cheques | One2many |  |  | c2p.pdc.register.line |  |  |
| `payee_is_landlord` |  | Boolean |  |  |  | _compute_payee_hint (not stored) |  |
| `payee_partner_id` | Cheques Payable To | Many2one |  |  | res.partner | _compute_payee_hint (not stored) |  |

### `c2p.pdc.register.line`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `amount` |  | Monetary | yes |  |  |  |  |
| `bank_name` | Drawn On | Char |  |  |  |  |  |
| `cheque_no` |  | Char | yes |  |  |  |  |
| `currency_id` |  | Many2one |  |  | related: wizard_id.currency_id |  |  |
| `drawer_partner_id` | Signed By | Many2one |  |  | res.partner |  |  |
| `maturity_date` |  | Date | yes |  |  |  |  |
| `wizard_id` |  | Many2one |  |  | c2p.pdc.register |  |  |

### `c2p.sample.loader`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `result` |  | Text |  |  |  |  |  |
| `with_accounting` | Include cheques and invoices | Boolean |  | True |  |  |  |

### `c2p.unit`

custom model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `area_sqft` | Area (sq ft) | Float |  |  |  |  |  |
| `building_id` |  | Many2one | yes |  | c2p.building |  |  |
| `company_id` |  | Many2one |  |  | related: building_id.company_id |  |  |
| `currency_id` |  | Many2one |  |  | related: company_id.currency_id |  |  |
| `current_lease_id` | Current Lease | Many2one |  |  | c2p.lease |  |  |
| `dewa_no` | DEWA Premise No. | Char |  |  |  |  |  |
| `floor` |  | Char |  |  |  |  |  |
| `floor_rent` | Floor Rent (Annual) | Monetary |  |  |  |  |  |
| `floor_rent_daily` | Floor Rent (Daily) | Monetary |  |  |  |  |  |
| `floor_rent_monthly` | Floor Rent (Monthly) | Monetary |  |  |  |  |  |
| `is_releasable` |  | Boolean |  |  |  | _compute_release_blockers (not stored) |  |
| `lease_end` | Lease Ends | Date |  |  | related: current_lease_id.date_end |  |  |
| `lease_ids` | Lease History | One2many |  |  | c2p.lease |  |  |
| `market_rent` | Market Rent (Annual) | Monetary |  |  |  |  |  |
| `market_rent_daily` | Market Rent (Daily) | Monetary |  |  |  |  |  |
| `market_rent_monthly` | Market Rent (Monthly) | Monetary |  |  |  |  |  |
| `name` | Unit No. | Char | yes |  |  |  |  |
| `release_blockers` | Missing Before Release | Char |  |  |  | _compute_release_blockers (not stored) |  |
| `release_checklist` | Readiness | Html |  |  |  | _compute_release_checklist (not stored) |  |
| `rera_index_high` | RERA Index High | Monetary |  |  |  |  |  |
| `rera_index_low` | RERA Index Low | Monetary |  |  |  |  |  |
| `state` |  | Selection | yes | draft | dynamic |  | yes |
| `state_before_block` |  | Selection |  |  | dynamic |  |  |
| `tenant_id` | Tenant | Many2one |  |  | related: current_lease_id.tenant_id |  |  |
| `unit_type` |  | Selection | yes | 1br | dynamic |  |  |

### `res.partner`

extension of a standard model — `sinclaire_workspace`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `tenant_alert` | Needs attention | Html |  |  |  | _compute_tenant_alert (not stored) |  |
| `tenant_bounce_rate` | Bounce rate | Float |  |  |  | _compute_tenant_cheques (not stored) |  |
| `tenant_cheque_breakdown` | Cheque register | Html |  |  |  | _compute_tenant_cheques (not stored) |  |
| `tenant_cheque_shortfall` | Cheque shortfall | Monetary |  |  |  | _compute_tenant_standing (not stored) |  |
| `tenant_cheque_tone` |  | Selection |  |  | ok, warn, critical | _compute_tenant_cheques (not stored) |  |
| `tenant_cleared_count` | Cleared | Integer |  |  |  | _compute_tenant_cheques (not stored) |  |
| `tenant_currency_id` |  | Many2one |  |  | res.currency | _compute_tenant_currency (not stored) |  |
| `tenant_custody_amount` | Value in hand | Monetary |  |  |  | _compute_tenant_cheques (not stored) |  |
| `tenant_custody_count` | Cheques in hand | Integer |  |  |  | _compute_tenant_cheques (not stored) |  |
| `tenant_deposit_held` | Deposit held | Monetary |  |  |  | _compute_tenant_standing (not stored) |  |
| `tenant_ever_bounced_count` | Ever bounced | Integer |  |  |  | _compute_tenant_cheques (not stored) |  |
| `tenant_lease_count` |  | Integer |  |  |  | _compute_tenant_tenure (not stored) |  |
| `tenant_lease_ids` | Tenancies | One2many |  |  | c2p.lease |  |  |
| `tenant_live_lease_count` |  | Integer |  |  |  | _compute_tenant_tenure (not stored) |  |
| `tenant_live_rent` | Contracted rent | Monetary |  |  |  | _compute_tenant_standing (not stored) |  |
| `tenant_renewal_count` |  | Integer |  |  |  | _compute_tenant_tenure (not stored) |  |
| `tenant_since` |  | Date |  |  |  | _compute_tenant_tenure (not stored) |  |
| `tenant_tenure_display` | Tenant for | Char |  |  |  | _compute_tenant_tenure (not stored) |  |

### `sale.order`

extension of a standard model — `c2p_property_lease`

| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `c2p_lease_id` | Lease | Many2one |  |  | c2p.lease |  |  |

<!-- END GENERATED -->
