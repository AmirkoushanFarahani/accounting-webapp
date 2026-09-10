# Architecture

## Stage 10 measured read-path improvements

As of 2026-09-10, AccountingService list queries use select-in loading for invoice items/checks and journal lines. Customer summaries use three independent owner-scoped grouped financial queries plus one customer-list query, avoiding N+1 aggregates and join multiplication. Lookup indexes cover invoice_items.invoice_id and journal_lines.journal_id/account_id. Posting transactions, lock order, authorization, ML semantics and the existing bounded database admission remain unchanged. The test-only profiling ASGI wrapper in scripts/stage10_probe.py must not be exposed by production startup. See [Stage 10 evidence](../STAGE_10_PERFORMANCE_REPORT.md).

The system uses a React client, a versioned FastAPI REST API, PostgreSQL, and
offline scikit-learn/Prophet training pipelines. HTTP routes remain thin;
services enforce accounting rules and transactions; repositories isolate ORM
queries. The ML runtime consumes versioned artifacts through adapters and logs
predictions and corrections for later retraining.

Stage 3 request flow is:

```text
FastAPI route → authentication/RBAC dependency → service → repository
              → SQLAlchemy Session → PostgreSQL
```

Services own commits for identity transactions and create audit events in the
same transaction where practical. Repositories contain query mechanics. JWT and
Argon2 utilities are isolated in `core/`; database models never enter response
serialization without explicit safe Pydantic schemas. Permissions are resolved
through `user_roles` and `role_permissions`, avoiding scattered role-name checks.

`AccountingService` owns master-data validation and every ledger transaction.
Manual journals, invoice issuance, and payment posting all converge on one
posting validator. It verifies period/account state, two-line minimum,
positive one-sided lines, and debit/credit equality before changing a journal
to POSTED. Reversals create new opposite entries; posted entries have no update
or delete operation. Invoice/payment state and their journals commit together.

Stage 4 is a read-only reporting slice. `ReportingRepository` owns aggregate
SQL over existing journal, invoice, allocation, payment, account, and party
tables. `ReportingService` applies accounting normal-balance semantics,
historical as-of allocation logic, filters, and response composition. Reports
never create ledger state and never duplicate posting rules.

Stage 6 adds an application-integrated ML slice while preserving the offline
Stage 5 package:

```text
protected /api/v1/ml route
  -> MLService
  -> MLRepository + ArtifactRegistry/ModelCache
  -> active Stage 5 artifact
  -> append-only prediction/feedback + audit event
```

Routes never load joblib files, engineer features, query accounting tables for
ML logic, or train models. `MLService` builds point-in-time features from
repository data and owns prediction persistence. `ArtifactRegistry` resolves
only controlled identifiers beneath `ML_MODEL_DIR`, validates artifact and
feature schemas plus dependency major versions, and returns safe errors.
`ModelCache` is lock-protected and keyed by registry UUID. Every inference
request first resolves the active database row; activation invalidates that
pipeline's cache, so an old artifact cannot silently remain active.

Model training remains an explicit offline operation. Registration records an
already-trained artifact. Activation selects exactly one production version per
pipeline. Inference never trains. Feedback appends a correction or verification
to an immutable prediction rather than rewriting model output.

Stage 7 adds a typed React presentation layer without changing those backend
boundaries:

```text
Persian route/page -> typed API service -> existing /api/v1 contract
                  -> auth/permission context + shared UI/date/format utilities
```

The client keeps authentication, HTTP/error translation, permission checks,
theme/calendar preference, navigation, and formatting centralized. Page
components never own JWT signing material or accounting invariants. UI
permissions improve usability while the FastAPI dependency remains the security
boundary. Monetary totals shown in forms are previews only; persisted totals,
status transitions, posting, and allocations remain backend-authoritative.

Stage 8 keeps those boundaries intact. Manual-journal reversal now enforces
single reversal and source ownership in the accounting service, so a generic
operation cannot detach invoice/payment state from its generated ledger entry.
The backend container runs migration, bootstrap, and Uvicorn as the dedicated
unprivileged `azari` user.

The document root and component layout are RTL. Desktop uses grouped top
navigation; widths below 1220px use a right-side drawer. Tables become labeled
record cards on small screens, while printable reports retain tabular layout.
IRANSans is a preferred local font name only—no unlicensed font asset is shipped.
The Borkowski Jalali conversion from the MIT-licensed `jalaali-js` project is
vendored with attribution; API dates remain ISO Gregorian.

Compose performs development migration/bootstrap explicitly. The image default
does not mutate schema, and production deployment can run migrations as a
separate controlled job.

Detailed decisions and the delivery roadmap are in `PROJECT_ANALYSIS.md`.
