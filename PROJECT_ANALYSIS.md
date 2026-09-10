# Project Analysis

## Stage 10 performance verification — 2026-09-10

Stage 10 is **PARTIAL PASS**, not production capacity certification. Batched customer aggregates, batched invoice/journal child loading and three measured lookup indexes improve the isolated 100-user run (p95 641ms before; 157ms and 328ms in two final runs). Both 250-user runs failed the error gate; higher levels were not attempted. Fresh-database migration/bootstrap now succeeds without the previous workaround. Final regression: 130 backend + 11 ML tests, 35 frontend tests; quality, migration, PostgreSQL concurrency and recovery checks passed. See [the full report](STAGE_10_PERFORMANCE_REPORT.md) for evidence, limitations and exact Stage 10 files. Prior pending changes are preserved; no commit/push was performed.

## Audit date and baseline

The repository was inspected on 2026-08-17 before implementation began. It was
empty: there were no source files, dependency manifests, configuration files,
database definitions, tests, documentation, or Git metadata. Consequently,
there is no legacy implementation to migrate or preserve.

Available host tooling at audit time:

- Python 3.14.6 and Python 3.12
- Node.js 24.18.0
- npm is installed, but PowerShell blocks `npm.ps1`; `npm.cmd` can be used
- Docker 29.7.2 and Docker Compose v5.4.0; Docker Engine execution is verified

## Missing components at baseline

All requested capabilities were missing, including authentication/RBAC,
accounting entities, double-entry posting, invoices and payments, reports,
audit logs, the four ML pipelines, model registry, frontend, migrations,
synthetic data, tests, containers, and operational documentation.

## Recommended architecture

The application will be a modular monorepo:

```text
frontend/                 React + TypeScript + Vite
  src/
    components/           reusable UI
    layouts/              navigation and page shells
    pages/                route-level screens
    services/             typed HTTP access
    hooks/ types/ charts/
backend/                  FastAPI application
  app/
    api/routes/           transport and request authorization only
    core/                 settings, security, RBAC
    db/models/            SQLAlchemy persistence model
    schemas/              Pydantic API contracts
    repositories/         persistence queries
    services/             accounting and application rules
    ml/                   inference adapters and model registry
  alembic/                database migrations
  tests/                  API, service, security, and integration tests
ml/                       framework-independent ML training package
  preprocessing/ training/ evaluation/ inference/ models/
scripts/                  synthetic data and operational utilities
docs/                     architecture, database, ML, API, and setup docs
```

FastAPI routes will call application services; services own transaction
boundaries and business rules; repositories isolate database access. ML
training remains independent of the web process. Inference adapters load
versioned artifacts and record predictions in PostgreSQL. This prevents model
code from becoming coupled to HTTP or ORM concerns.

PostgreSQL is the primary database. SQLAlchemy types and constraints will avoid
vendor-specific behavior where practical to retain reasonable MySQL
portability. Monetary values use fixed-precision decimals, never floats.

## Domain and data design

The accounting core will use a journal header plus journal lines. Each posted
journal must have at least two lines and equal debit and credit totals. Draft
invoices do not affect the ledger; issuing and paying invoices create journal
entries through one posting service. Invoice payment allocation supports
partial payments and derives status from amount paid and due date.

The normalized model will include users, roles, permissions, parties
(customer/supplier specializations where useful), products, accounts, account
categories, journals, journal lines, invoices, invoice items, payments,
financial periods, audit events, ML model versions, predictions, feedback, and
cluster assignments. Soft deletion is limited to master data; ledger records
are immutable after posting and corrected with reversing entries.

## ML design

- Transaction classification: TF-IDF plus Multinomial Naive Bayes and linear
  SVM comparison. The selected calibrated pipeline returns category,
  confidence, and manual-review status.
- Payment-delay risk: Random Forest trained on features computed strictly as of
  the prediction timestamp. Permutation or impurity feature contributions are
  translated into concise explanations.
- Cash flow: Prophet when supported by the runtime; a deterministic statistical
  fallback will be documented if Prophet cannot support Python 3.14. Forecasts
  include intervals and are evaluated with chronological backtesting.
- Segmentation: standardized financial features plus K-Means. Candidate `k`
  values are evaluated with inertia and silhouette score; labels are inferred
  from centroid characteristics rather than cluster IDs.

Every pipeline implements train, evaluate, save, load, and predict operations.
Artifacts, feature schemas, seeds, metrics, dataset fingerprints, and model
versions are stored together. Synthetic demo records are explicitly marked and
generated with behavioral profiles and temporal patterns.

## Architectural risks and mitigations

- **Empty baseline / large scope:** deliver vertical, tested milestones rather
  than disconnected modules.
- **Python 3.14 dependency support:** containerize on Python 3.12 and pin tested
  dependency ranges; treat the newer host interpreter as optional.
- **Forecasting dependency weight:** keep Prophet behind an adapter and out of
  the request lifecycle.
- **Accounting correctness:** centralize posting, use database transactions and
  decimal arithmetic, and test balance/period/immutability invariants.
- **Data leakage:** produce time-aware feature snapshots and chronological
  train/test splits.
- **Insufficient real data:** use realistic, labeled synthetic profiles without
  presenting demo metrics as real-world performance.
- **Security:** fail configuration when secrets are absent, hash passwords with
  Argon2, use short-lived JWTs, enforce permissions in dependencies, constrain
  CORS, audit mutations, and never serialize sensitive fields.
- **Host port reservation (resolved):** Windows excludes TCP ports 5141-5240,
  including attempted frontend ports 5173 and 5174. The approved host port 4173
  is outside that range and the complete Compose stack is verified running.
- **Backend host port reservation (resolved):** Windows also excludes TCP ports
  7927-8026, including host port 8000. Compose publishes backend container port
  8000 on host port 8100; the container and its internal healthcheck continue to
  use port 8000.

## Assumptions

- One organization and one base currency are sufficient for the bachelor's
  prototype; identifiers and service boundaries will allow later tenancy.
- PostgreSQL 16 and Python 3.12 are the supported deployment targets.
- Accounting periods and timestamps are stored in UTC; display timezone is a
  user-facing concern.
- Tax rules are configurable data, not jurisdiction-specific tax compliance.
- The initial frontend targets modern evergreen browsers and desktop/tablet
  dashboard layouts.

## Implementation roadmap

1. **Foundation:** monorepo layout, validated settings, backend/frontend health
   path, containers, test/lint tooling, documentation skeleton.
2. **Persistence and identity:** SQLAlchemy model base, Alembic migration,
   users, roles, permissions, JWT authentication, audit service.
3. **Accounting vertical slice:** customers/suppliers/products/accounts,
   balanced journals, invoices, payment allocation, and service/API tests.
4. **Reports and dashboard API:** statements, receivables/payables, filters, and
   aggregates derived from persisted records.
5. **ML pipelines:** reproducible training/evaluation/artifacts for all four
   algorithms plus synthetic behavioral data.
6. **ML integration:** prediction/training endpoints, registry and feedback,
   permission checks, explanations, and persisted results.
7. **Frontend:** authenticated workflows, accounting screens, reports,
   operational dashboard, and dedicated AI dashboard.
8. **Hardening:** integration/e2e tests, Docker verification, security review,
   complete docs, and a reproducible demonstration run.

## First implementation milestone

Milestone 1 is complete when configuration fails safely without required
secrets, `/api/v1/health` returns a typed response, the React shell reads that
endpoint, backend tests pass, frontend type checking/build passes, and the
three-service Compose topology runs with both host endpoints reachable. No mock
accounting or hardcoded ML predictions are introduced during this milestone.

### Milestone 1 status

Implemented and verified: validated fail-fast configuration, versioned backend
health API, React connectivity shell, pinned dependencies and lockfile, backend
container, frontend Nginx container, PostgreSQL Compose service, documentation
skeleton, and quality-tool configuration. Backend tests/lint/type checks and the
frontend production build pass. Docker installation and Compose configuration
are verified. After adding context-specific Docker ignore rules, both images
build successfully and the backend health endpoint returns HTTP 200. Compose
correctly renders frontend host port 4173 targeting container port 80. The
Stage 1 backend mapping was 8000:8000; it was later adjusted during Stage 2 to
8100:8000 because Windows reserves host port 8000. The complete three-service
stack is running: PostgreSQL is healthy, the backend health endpoint returns
HTTP 200, and the frontend returns HTTP 200 at `http://localhost:4173`. Backend tests, Ruff,
strict mypy, and the frontend production build all pass. Stage 1 is **PASS**.
See `STAGE_1_VERIFICATION.md` for command-level evidence. At the Stage 1
checkpoint, Stage 2 had not begun.

## Stage 2 — Persistence and identity

### Implemented architecture

Stage 2 adds a synchronous SQLAlchemy 2 session foundation, typed UUID models,
Alembic migration authority, repositories, identity services, and thin FastAPI
routes. The schema contains users, roles, permissions, user-role links,
role-permission links, and append-oriented audit events. It deliberately adds no
accounting, reporting, or ML tables.

Passwords use Argon2id. JWT access tokens use the configured HMAC algorithm,
secret, and lifetime. Stage 2 originally fixed public registration to VIEWER;
the current owner-directed policy assigns ADMIN while still rejecting role
input. Authorization resolves database permissions inherited across all
roles through centralized FastAPI dependencies. Registration and login
success/failure create audit events, while audit metadata rejects sensitive-key
payloads.

Compose runs Alembic and idempotent RBAC bootstrap as an explicit development
startup command; the backend image default starts only Uvicorn. Optional admin
bootstrap requires paired environment credentials and has no hardcoded default.

### Stage 2 status

Stage 2 is **PASS**. Verification completed on Python 3.12 and PostgreSQL 16:

- 25 backend tests passed with 94% application coverage;
- Ruff passed;
- strict mypy passed across 38 source files;
- frontend TypeScript/Vite production build passed;
- isolated PostgreSQL migration upgrade/downgrade/upgrade passed;
- PostgreSQL constraints, timezone-aware timestamps, RBAC bootstrap, and model
  schema alignment passed;
- registration, login, `/auth/me`, 401, 403, safe serialization, and audit
  persistence passed;
- final Compose rebuild has all three services running, PostgreSQL/backend
  healthy, backend HTTP 200 on host port 8100 (container port 8000), and
  frontend HTTP 200 on host port 4173.

Detailed implementation, security decisions, tests, and limitations are in
`STAGE_2_IMPLEMENTATION.md`. Stage 3 has not started.

## Stage 3 — Accounting vertical slice

Stage 3 is **PASS**. It adds normalized master data, financial periods,
double-entry journals with immutable posting and reversal, backend-calculated
receivable invoices, and allocated customer payments. Invoice issuance and
payment posting are atomic and use the centralized posting engine. The new
Alembic revision was verified upgrade/downgrade/upgrade with no model drift on
isolated PostgreSQL. The suite passes 42 tests at 93% total application coverage
and 93% accounting-service coverage, strict mypy, Ruff, frontend build, and the
three-service Compose runtime. Details are in `STAGE_3_IMPLEMENTATION.md`.
Stage 4 has not started.

## Stage 4 — Reports and dashboard API

Stage 4 is **PASS**. The authoritative boundary is roadmap item 4: statements,
receivables/payables, filters, and dashboard aggregates derived from persisted
records. It adds a read-only reporting repository/service/API for trial balance,
income statement, revenue, expenses, balance sheet, historical receivables,
liability-account payable exposure, customer history, posted cash receipts, and
operational dashboard metrics. Index-only migration `20260818_0002` supports
the report filters without changing domain data. The suite passes
46 tests at 95% application coverage; reporting repository/service coverage is
100%/99%. Strict mypy, Ruff, frontend build, PostgreSQL aggregation/drift, and
the Compose runtime all pass. Stage 5 is documented below.

## Stage 5 — Offline ML pipelines

Stage 5 is **PASS**. Four framework-independent pipelines now implement
training, evaluation, versioned save/load, and typed inference: calibrated
TF-IDF transaction classification, timestamp-aware Random Forest payment-delay
risk, harmonic linear cash-flow forecasting with chronological backtesting, and
scaled K-Means customer segmentation with centroid-derived descriptions.

Seeded synthetic generators provide noisy, overlapping demo datasets for each
pipeline. Artifact metadata records the dataset fingerprint, feature schema,
configuration, seed, metrics, timestamp, dependency versions, and compatibility
schema. Generated data/models remain outside Git. Leakage and reproducibility
tests cover train-only text/scaling preprocessing, point-in-time payment
snapshots, chronological forecasting, repeated training, and save/load parity.

The complete 57-test backend/ML suite passes at 96% combined coverage, along
with Ruff, strict mypy, the frontend production build, and all four training
runs. The Python 3.12 backend image installs inference dependencies and the
three-service Compose stack remains healthy at 8100→8000 and 4173→80, with
PostgreSQL at Alembic head `20260818_0002`. Synthetic benchmark metrics are not
claims of real-world performance. See `STAGE_5_IMPLEMENTATION.md`. Stage 6 has
now been implemented as described below.

## Stage 6 — ML integration

Stage 6 is **PASS**. Migration `20260825_0003` adds a database-backed model
registry, append-oriented predictions, and append-only feedback without
changing accounting tables. Protected `/api/v1/ml` routes delegate to an ML
application service and repository. Controlled artifact identifiers, metadata
and feature-schema validation, dependency compatibility checks, one-active-model
constraints, and a lock-protected invalidating cache prevent arbitrary or stale
model selection.

All four Stage 5 pipelines use active registered artifacts. Transaction text is
classified directly without persisting its raw description. Payment risk,
cash-flow forecasts, and customer segmentation derive features from persisted
accounting history available at the requested cutoff. Predictions store only
structured outputs, safe references, confidence/review/explanation metadata,
and user/model context. Registration, activation, and feedback are audited;
new `ml:predict`, `ml:manage`, and `ml:feedback` permissions extend existing
database RBAC.

The final 67-test suite passes at 96% combined coverage, Ruff and strict mypy
pass, the migration passes upgrade/downgrade/upgrade and zero-drift checks, and
the Python 3.12 Compose runtime verifies model registration, activation,
inference, PostgreSQL persistence, feedback, audit, RBAC, and both host health
checks. Details are in `STAGE_6_IMPLEMENTATION.md`. Stage 7 is described below.

## Stage 7 — Production frontend

Stage 7 is **PASS**. The technical connectivity shell has been replaced by a
complete Persian/RTL React application. It provides session JWT login/logout,
protected routes, permission-aware grouped top navigation and mobile right-side
drawer, persistent light/dark themes, English-digit financial formatting, and
Jalali/Gregorian input and display while retaining Gregorian API storage.

Operational pages consume the existing APIs for the dashboard, parties,
products, accounts/categories, financial periods, journals, invoices, payments,
all nine report views, users, model/prediction history, feedback, model
registration/activation, and all four inference workflows. No mock financial or
AI values were added. The frontend documents the existing lack of supplier-level
payable detail instead of inventing it.

Frontend type checking and production build pass; 12 focused frontend tests
pass. The complete 67-test backend/ML suite, Ruff, strict mypy, Compose config,
the rebuilt frontend container, three-service runtime, PostgreSQL/backend health,
both host HTTP checks, and `git diff --check` pass. A separate uncached rebuild
of the unchanged backend image was attempted twice and was blocked by host
outbound timeouts to PyPI; the already verified Stage 6 backend image remained
healthy in the final runtime. See `STAGE_7_IMPLEMENTATION.md` for full evidence.
Stage 8 is described below.

## Stage 8 — Production readiness and hardening

Stage 8 is **PASS WITH DOCUMENTED LIMITATIONS**. It closes a high-severity
ledger/source consistency hole by rejecting generic reversal of journals owned
by invoices or payments, and makes other invalid reversal cases explicit. It
also hardens frontend RBAC reflection, Persian presentation, mobile table
context, validation errors, modal keyboard focus, and the backend container's
non-root execution.

The final suite passes 68 backend/ML tests at 96% coverage, Ruff, strict mypy
across 91 files, 17 frontend tests, TypeScript, and the production build. Clean
Compose rebuild, Alembic head/no-drift, host and container health, live
accounting reconciliation, 401/403 RBAC, all four ML APIs, feedback,
low-confidence review, restart persistence, and audit/log safety passed. The
npm advisory endpoint was unavailable due to an external connection reset;
synthetic-model fitness and documented product gaps remain limitations. See
`STAGE_8_IMPLEMENTATION.md`. Stage 9 has not started.

## Stage 9 — Audit and Phase B HIGH remediation

Stage 9 Phase B is **PASS** for the owner-approved HIGH-remediation scope.
Draft invoices have no financial effect; invoice/payment source accounts use
explicit semantic posting roles; posted account category/role is immutable;
zero invoices are rejected; tax posts separately to liability; closed-period
reversal attempts roll back; concurrent payments cannot over-allocate; and
production ML artifacts require a pinned digest and read-only runtime access.

Migration `20260827_0004` is at PostgreSQL head with no Alembic drift. The final
verification passes 83 backend/ML tests at 95% combined coverage, 19 frontend
tests, TypeScript, production build, project-scoped Ruff, strict mypy, a real
PostgreSQL tax/concurrency probe, a clean Compose rebuild, three healthy
services, backend liveness/readiness HTTP 200, and frontend HTTP 200. See
`STAGE_9_DEBUG_AUDIT.md`. Stage 10 has not started.
