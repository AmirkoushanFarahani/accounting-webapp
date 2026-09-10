# Paid expenses

Added under Purchase & Payments → هزینه‌ها (`/expenses`) for every business profile.

Fields: name, amount in rials, payment date, cash/check/interbank-transfer method,
and optional tracking code. The existing date picker and thousands separators are reused.
The user selects an EXPENSE-role expense account and a CASH-role cash/bank account;
when there is only one eligible account it is selected automatically. An open
financial period must cover the payment date.

## Owner-approved accounting behavior

Saving immediately posts a balanced journal: debit EXPENSE, credit CASH for the
same amount. Check payments are also deducted immediately, as explicitly requested.
There is no later clearance action for these expense checks. This is distinct from
customer invoice checks. Do not record the same expense again as a supplier bill.

No supplier, bill, tax split, or allocation is created. This feature is for paid
operating costs, not inventory purchases or unpaid liabilities. Saved entries are
not editable/deletable; direct reversal of their source journal is blocked to keep
the expense history and financial reports consistent.

The page's date range is inclusive and its total covers entries made in this
section. The existing expense and income-statement reports include both these
expenses and other posted expense-account activity. Cash-flow and dashboard
outflows now include these payments once, without counting a supplier payment too.

## Access and implementation

- GET `/api/v1/expenses?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`:
  owner's entries and a Decimal total; requires `bills:read`.
- POST `/api/v1/expenses`: immediately posts; requires both `bills:issue`
  and `bill_payments:post`. The client cannot supply another owner.
- Migration `20260909_0013` adds `expenses` linked to an immutable source journal.
- Posting locks the period first, then account UUIDs in sorted order, and checks
  account roles under those locks. Posting and expense creation are atomic.
- No notification, subscription or ML model behavior changes.

## Verification — 2026-09-09

- Backend + ML: 132 passing tests (121 backend, 11 ML), including eight new expense cases.
- Frontend: 35 passing tests; TypeScript and production build passed.
- Ruff, strict mypy (71 source files) and `git diff --check` passed.
- PostgreSQL populated-copy upgrade/downgrade/upgrade and Alembic drift checks passed.
  Existing data hashes remained unchanged (11 users, 100 invoices, 48 bills and 220 journals).
- Real browser test against the PostgreSQL copy created cash/check/bank expenses,
  verified optional tracking, persistence, mobile page display and a 375,000-rial
  total matching the dashboard and balanced ledger. No test expenses were written
  to the live database.
- Live database is at revision 0013; all three Compose services healthy;
  frontend `/expenses`, backend `/health` and `/ready` return HTTP 200.
- The ordinary backend Docker build failed because PyPI timed out downloading
  setuptools. Local runtime verification used a temporary Dockerfile inheriting
  the existing backend image's installed dependencies and copying current backend
  source. No dependencies or repository Docker configuration changed. A clean
  standard Docker build still needs verification when PyPI connectivity recovers.

Temporary database/container used for verification are disposable, not application data.
No commit or push performed.
