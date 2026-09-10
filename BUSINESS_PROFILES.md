# Business presentation profiles

Implemented 2026-09-07. Four business profiles share the existing routes,
accounting services, reports, ownership rules, and permission checks.

## Choose a profile

New users select **نوع کسب‌وکار** during registration. Existing users open
**مدیریت → تنظیمات نمایش** (or **تنظیمات کسب‌وکار و نمایش**) and choose a profile,
then press **ذخیره نوع کسب‌وکار**. The choice is saved to the account and follows
the user across browsers and devices. Existing accounts default to Retail.

| Profile | Examples | Presentation |
|---|---|---|
| RETAIL — فروشگاه و مغازه | Shops, bookstores, clothing, stationery | Existing sales/customer/product interface |
| EDUCATION — آموزشگاه و مؤسسه آموزشی | Schools, language institutes, academies | Tuition invoices, payer financial files, courses/services, course units |
| ONLINE — کسب‌وکار آنلاین | Online shops, social-media sellers | Order invoices, buyers, product catalog, order receipts |
| SERVICES — خدمات نوبتی و دوره‌ای | Salons, gyms, cleaning, maintenance | Service invoices, client files, services/packages, session units |

Non-retail dashboards have a profile-specific introduction, financial workflow,
shortcuts, and draft/outstanding/paid invoice counts. Revenue and receivable
headings reflect the profile; their values come from the same existing reports.
Main navigation prioritizes the business workflow ahead of general accounting
for non-retail profiles. Desktop and mobile use the same profile configuration.
Invoice, item, customer-history, and receipt forms reuse the current API contracts.
New item forms default to course/session units for Education/Services; changing
profile does not change the units of existing products.

## Boundaries

- A category is a presentation preference, not a permission or subscription tier.
- Changing it does not change roles, plan_status, prices, or data ownership.
- No subscription pricing, billing, or feature gating was added.
- Students/payers use the current Party financial record. Independent student,
  guardian, course enrollment, attendance, and grading records are not provided.
- Online order invoices are financial documents, not shipping or fulfillment records.
- Service packages are billable descriptions/items, not appointment schedules,
  session-consumption balances, or automatically recurring invoices.
- Posted journals, debit/credit semantics, tax treatment, checks, allocations,
  concurrency rules, and accounting-account roles remain unchanged.

## Persistence and API

- `users.business_category`: required VARCHAR(20), default RETAIL, named CHECK
  allowing RETAIL, EDUCATION, ONLINE, SERVICES.
- Migration `20260907_0012` adds the column and constraint; no business tables change.
- Registration accepts an optional category; user responses always include it.
- `PATCH /api/v1/auth/me/business-profile` accepts only `business_category`.
  Authentication selects the affected user; client-supplied user IDs, roles,
  subscription fields, and unknown categories are rejected.
- Changes are audited. The new setting does not grant access to user management.

## Verification

- Backend and ML suite: 124 passing tests (113 backend, 11 ML), including six
  new business-profile API tests.
- Frontend: 32 passing tests, including profile wording/routes and preserved amounts.
- Ruff passes; strict mypy with the project config passes for 68 source files.
- TypeScript and production build pass.
- PostgreSQL migration upgrade/downgrade/upgrade passed on a separate populated
  copy with 7 users, 27 invoices, 12 bills, and 56 journals. Counts and SHA-256
  digests of all existing row contents were preserved (excluding only the new
  category field). Alembic drift checks passed. The temporary copy was removed.
- Browser verification on the running app exercised all four profiles: saving
  through Settings, persistence after reload, dashboard and invoice labels,
  customer/item input prompts, product default units, and unchanged financial
  totals/roles/plan. The demo account was restored to its original Retail profile.

These presentation checks do not claim to implement or verify booking,
enrollment, shipping, or subscription workflows.
