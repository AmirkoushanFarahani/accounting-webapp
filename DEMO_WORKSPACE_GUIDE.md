# Demo workspace for manual testing

## Additional business-profile demos (2026-09-08 Tehran)

| Profile | Login email | Sample catalog |
|---|---|---|
| Education | `demo.education.20260907211144@example.com` | Language, mathematics, programming and other courses |
| Online business | `demo.online.20260907211157@example.com` | Headphones, phone accessories and other products |
| Appointments & recurring services | `demo.services.20260907211205@example.com` | Consultation, maintenance, cleaning and other services |

Passwords were supplied in the conversation, not stored in this file.
Each new OWNER account contains 187 main synthetic records, with the same
counts and baseline financial totals documented below, but a category-specific
catalog and saved business profile. No existing workspace was modified.
Each creation run verified balanced journals, trial balance and balance sheet,
report totals, customer purchase histories, dashboard consistency and all four
AI prediction endpoints. AI outputs remain synthetic demonstrations, not validated
business predictions. Services data represents service invoices, not actual
appointment bookings or automated recurring schedules.

Sign out before switching accounts at http://localhost:4173. These new datasets
use 2026-09-07 as the UTC report cutoff; future check due dates extend beyond it.
To reproduce a new workspace, set `DEMO_CATEGORY` to `EDUCATION`, `ONLINE` or
`SERVICES` before running `scripts/seed_demo_workspace.py`.

## Original retail demo

Created on 2026-09-06 through the running application API.

- Login URL: http://localhost:4173
- Email: `demo.20260906232359@example.com`
- Password: supplied separately in the conversation; intentionally omitted here.
- Role: OWNER, with a separate accounting workspace.
- All names and transactions are synthetic. Amounts are rials.

## Dataset

187 main records were created, excluding the login user, invoice/bill items,
journal lines, allocations, and automatic audit events. Physical database row
count is therefore greater than 187.

| Record type | Count |
|---|---:|
| Customers / suppliers | 16 / 4 |
| Products/services | 8 |
| Account categories / accounts | 5 / 9 |
| Financial periods | 2 |
| Sales invoices | 24 |
| Supplier bills | 12 |
| Customer receipts | 15 |
| Supplier payments | 7 |
| Journals, including automatically generated entries | 54 |
| Invoice checks | 12 |
| AI predictions / feedback comments | 17 / 2 |

Invoice statuses: 6 paid, 8 partially paid, 6 issued/unpaid, 4 drafts.
Bill statuses: 3 paid, 3 partially paid, 4 issued/unpaid, 2 drafts.
Checks: 4 cleared, 6 pending, 2 bounced. Some have no Sayad identifier.
Receipts include one unposted draft; supplier payments include one unposted draft.

## Where to start

Sign out of your current account and sign in with the demo email and password.
Use all dates, or 2026-01-01 through 2026-09-06, for the baseline reports below.
Future checks extend beyond the report cutoff. Changing or posting demo records
will naturally change these baseline results.

| Example | What to inspect |
|---|---|
| DEMO-INV-001 | Fully paid, taxed invoice; revenue excludes tax |
| DEMO-INV-006 | Partially paid cash invoice |
| DEMO-INV-011 | Issued invoice with a draft receipt that has no financial effect |
| DEMO-INV-012 | Unpaid invoice suitable for payment-risk testing |
| DEMO-INV-015 | Two checks whose combined amount is less than the invoice total |
| DEMO-INV-016 | Cleared first check and bounced second check |
| DEMO-INV-017 | Cleared check exceeding invoice total, creating customer credit |
| DEMO-INV-019 | Unpaid invoice with a bounced check |
| DEMO-INV-021 through 024 | Draft invoices with no financial effect |
| DEMO-BILL-001 | Paid supplier bill with tax absorbed into expense |
| DEMO-BILL-004 | Partially paid supplier bill |
| DEMO-BILL-007 | Issued bill with an unposted draft payment |
| DEMO-BILL-011 and 012 | Draft supplier bills |
| DEMO-OPENING | Posted 500,000,000-rial capital contribution |
| DEMO-REVERSAL | Posted journal with a separate offsetting reversal |
| DEMO-DRAFT | Unposted manual journal |

The prior-year period is closed; the current-year period is open.
Customer history includes repeat purchases and both directions of debt:
14 customers owe the business; the business owes 2 customers on a net basis.

## Verified baseline totals

| Metric | Rials |
|---|---:|
| Revenue | 66,250,000 |
| Expenses | 8,700,000 |
| Net income | 57,550,000 |
| Outstanding customer invoices | 41,586,250 |
| Outstanding supplier bills | 5,900,000 |
| Posted incoming customer payments | 27,001,250 |
| Posted outgoing supplier payments | 2,800,000 |
| Net payment cash flow | 24,201,250 |

The app's cash-flow report uses posted customer/supplier payments. It does not
include the separate manual capital contribution; consequently it is not the
same as the bank ledger balance.

Verified through real HTTP API calls against the running PostgreSQL-backed app:

- Trial balance and balance sheet report balanced.
- Every journal has equal debit and credit totals.
- Income, revenue, expense, receivable, payable and cash-flow reports match
  independently summed transaction records.
- All 16 customer histories match their issued invoice counts and totals.
- Repeated dashboard reads leave totals unchanged.
- Draft invoices, bills and payments are excluded from the checked financial totals.
- AI predictions leave the dashboard financial totals unchanged.

## AI examples and limits

All four models were already active at prediction time. This seed did not
activate or replace shared models.

- Four text classifications, including two Persian descriptions.
- Four unpaid/partially paid invoice risk predictions.
- One 30-day cash-flow forecast, with 30 points and ordered prediction bounds.
- Eight customer segment predictions.
- Two COMMENT feedback records, explicitly not claiming real-world verification.

All calls succeeded, but accuracy is a separate issue. Both Persian descriptions
returned `meals` at confidence 0.20; `office rent payment` returned `software`
at about 0.294. The travel example returned `travel` at about 0.860. All eight
segmented customers landed in cluster 0, and all four risk examples returned low.
These are observed results, not evidence of useful real-world accuracy. The
existing models are trained on synthetic data and need separate evaluation for
Persian text and the business's actual amount/behavior distributions.

## Reusable creation script

`scripts/seed_demo_workspace.py` creates another demo account through the local
API when run without environment overrides. It prints generated credentials
once and does not write passwords to the repository.

For resuming the same demo account, supply `DEMO_EMAIL` and `DEMO_PASSWORD` in the
process environment. The script reuses matching records and skips completed
posting operations. Run resumption before manual changes, since manually edited
data may no longer match its verification expectations.

Application source, schema, and existing users' accounting data were not changed.
This is a seeded integration/demo exercise, not an exhaustive regression,
concurrency, or browser end-to-end test suite.
