# Data migration plan

Required by BRD §9.1; method fixed by §8.6, staging and reconciliation controls
by §8.3.6 and §8.3.7.

§8.6 sets the sequence and one rule that governs everything else:

> Extract and clean the data, remove duplicates, map it to Odoo, run a test
> load, reconcile totals, obtain business approval, complete the final load, and
> archive the source files. **No source record or amount may be omitted without
> a documented reason.**

That last sentence is the plan's spine. A rejected row is corrected and
reloaded; it is never silently dropped, and the count of rejected rows is a
reconciliation output, not an internal detail.

**Blocked on OD-09** — opening data volumes, quality, cutover date and
historical retention. Everything below is the method, the object order and the
controls, which do not depend on those answers. The schedule does.

---

## 1. Three objects are never imported

Head leases, owner-management contracts and banking facilities are **entered by
hand from the signed agreements**. No import may originate them.

They are commitments to pay real money, and every margin, coverage and
break-even figure on the dashboard divides by them. Inferring one from whatever
is in a spreadsheet produces an authoritative-looking number with nothing behind
it — worse than an empty screen, which at least looks wrong.

`tools/import_head_leases.py` exists and does **not** contradict this: it
transcribes a CSV that a person has filled in from the signed agreements, with a
dry run that writes nothing until the report is read. The template ships with
every amount blank and a test asserts it stays that way.

---

## 2. Object order

Each object depends on the ones above it. Loading out of order produces orphan
references that reconcile to the right totals and point at nothing.

| # | Object | Depends on | Key / duplicate rule | Hand-entered |
| --- | --- | --- | --- | --- |
| 1 | Companies, fiscal years, period locks | — | legal name | yes |
| 2 | Chart of accounts, taxes, tax grids, journals | 1 | account code per company | config |
| 3 | Analytic plan and accounts | 1 | one per building, created with the building | — |
| 4 | Products — rent, deposit, commission, fees, service charges, penalties | 2 | XML ID | config |
| 5 | Reference data — unit types, document types, compliance types, clause families, checklist item types | 1 | code | config |
| 6 | Landlords and owners | 1 | name + trade licence / ID; **restricted fields** | — |
| 7 | Tenants — individual and company | 1 | permitted identifier; duplicate detection **without exposing restricted values** (§4.2.1) | — |
| 8 | Suppliers, brokers, referrers | 1 | name + TRN | — |
| 9 | Buildings | 3, 6 | `company_id` + `code`, unique | — |
| 10 | Units | 9 | `building_id` + unit code, unique. **Reconcile to the building's declared residential and commercial counts** (§8.3.4) | — |
| 11 | **Head leases** | 9, 6 | building + start date | **yes — never imported** |
| 12 | **Owner-management contracts** | 9, 6 | building + start date | **yes — never imported** |
| 13 | **Banking facilities** | 1 | bank + facility reference | **yes — never imported** |
| 14 | Active tenant leases | 10, 7 | **one active tenancy per unit per date range** | — |
| 15 | Security and utility deposits | 14 | lease + deposit type | — |
| 16 | Payment instruments — tenant and landlord cheques | 14, 11, 2 | **cheque number + bank + account**, duplicates rejected | — |
| 17 | Opening ledger balances | 2, 3 | must balance to zero | — |
| 18 | Opening bank balances | 2 | per account, to the statement | — |
| 19 | Unpaid invoices and bills | 7, 8, 14 | source document number | — |
| 20 | Outstanding balances and ageing | 19 | reconciles to the receivables control account | — |
| 21 | Maintenance tickets | 9, 10 | source ticket reference | — |
| 22 | Documents and attachments | all | source path + target record | — |

Items 11 to 13 sit in dependency order deliberately: everything below them
references them, so they must be **entered and approved before** leases and
cheques load, even though no file carries them.

---

## 3. Import staging

Every load passes through staging, which retains, per §8.3.6:

| Retained | Why |
| --- | --- |
| Template ID, workbook, worksheet, source row | a rejected row must be findable in the original file |
| Upload batch, uploader, upload time | who loaded what, when |
| Validation result and rejection reason | the documented reason §8.6 requires |
| Target model and target record | the forward link, for reversal |
| Reversal reference | so a bad batch can be undone, not patched |

**Rejections, per §8.3.6**, are mandatory for: invalid dates, duplicate document
or cheque numbers, unknown building or unit codes, unbalanced totals, invalid
status values.

A row that fails is corrected in the source and reloaded. The staging record of
the failure is kept — it is the audit evidence that nothing was dropped.

---

## 4. Reconciliation, per object

§8.3.7 requires reconciling opening plus additions less recognised, paid or
refunded amounts to closing, for prepayments, deposits, facilities, receivables,
payables and deferred income. Per object, before sign-off:

| Control | Applies to |
| --- | --- |
| **Record count** — source rows vs. loaded vs. rejected; the three must sum | every object |
| **Amount total** — source sum vs. loaded sum, per currency | 15–20 |
| **Date range** — earliest and latest, to catch truncated extracts | 14–16, 19 |
| **Control-total reconciliation** — units created vs. the building's declared counts | 10 |
| **Ledger tie** — opening balances to trial balance; ageing to the receivables control account | 17–20 |
| **Bank tie** — opening bank balance to the closing statement at cutover | 18 |
| **Physical count** — cheques in hand vs. cheques in the register | 16 |

The cheque physical count is not a formality. §8.3.1 requires a
physical-to-system count as a standing monthly control; at migration it is the
only thing that proves the instrument register matches what is actually in the
safe.

---

## 5. Cutover sequence

1. **Freeze** — source systems read-only from an agreed timestamp. Record it;
   every reconciliation is "as at" that moment.
2. **Final extract** — from the frozen sources, with row counts captured at
   extraction, not after cleaning.
3. **Clean and de-duplicate** — in the source files, not in Odoo. Every change
   is a tracked edit against the archived original.
4. **Hand-enter** objects 11 to 13 from the signed agreements, with Finance
   approval, **before** the dependent loads.
5. **Test load** into a staging database. Reconcile all of section 4. Fix,
   reload, repeat until clean.
6. **Migration rehearsal sign-off** — §9.1 names this as its own stage with
   written sign-off, distinct from UAT.
7. **Final load** to production.
8. **Reconcile again** on production. The test-load reconciliation does not
   carry over.
9. **Business approval** against the §8.6 checklist.
10. **Archive** the source files with their extraction timestamps, batch
    references and reconciliation statements.
11. **Lock** the periods before the cutover date.

Steps 5 and 8 are the same reconciliation run twice. That is deliberate: a
staging database that reconciles proves the mapping; only production reconciling
proves the migration.

---

## 6. What sample data must never reach

§5.1.3 and §5.1.4 are explicit, and it is a migration rule rather than a
build-time one because the risk arrives with the source workbooks:

- Tenant names, unit numbers, lease dates, contact details and email addresses
  from the supplied addenda and checklists **never become template defaults**.
- The residential addenda (CBD, Deyafa, Emerald, Hassan Jassim 2, Karama,
  Marwan, Reem, Satwa, Tawaweesh) migrate as **reference clause sets after legal
  harmonisation** — not as per-unit copies.
- Commercial addenda (Hassan Jassim 2, Karama, Satwa) form separate commercial
  clause sets.
- §9.2.4 makes this testable: sample tenant, contact and salary data must appear
  in **no production template or test export**.

A related live issue, already logged as N2 in `decisions_required.md`: on
16 September the production database was displaying sample-portfolio figures
(6 buildings, 100 units, AED 7,622,400 contracted rent). Whether that was
deliberate, and whether it has been cleared, should be settled before any real
load.

---

## 7. What OD-09 still gates

| Needed | Blocks |
| --- | --- |
| Opening data volumes per object | effort, load windows, whether staged loads are needed |
| Source data quality assessment | cleaning effort, expected rejection rate |
| Cutover date | the whole schedule, and the period-lock date |
| Historical data retention — how many prior years | objects 17 to 21, and the archive scope |

The method does not change when these arrive. The schedule does not exist until
they do.
