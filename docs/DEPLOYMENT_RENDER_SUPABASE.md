# Render + Supabase deployment preparation

Stage 2B, 2026-09-10. This is a runbook for a **later, explicitly authorized deployment**, not evidence of a cloud deployment. Production starts with fresh application tables. Do not copy, migrate, or change the local Docker database. No cloud resources or credentials were provisioned in this stage.

## A. Architecture

Browser -> Render Static Site (React/Vite) -> Render Docker Web Service (FastAPI) -> Supabase PostgreSQL.

Keep synchronous SQLAlchemy 2 and Psycopg 3 (`postgresql+psycopg`). Keep existing JWT authentication, RBAC, and `owner_id` isolation. Supabase supplies PostgreSQL, not application authentication. The browser receives neither database credentials nor direct database access.

Local development remains separate: existing `.env` and `compose.yaml`, database service `db:5432`, backend host port 8100/container 8000, frontend host port 4173/container 80. Do not replace those settings with cloud settings.

## B. Required accounts/services

- A Render account and a reviewed release accessible to its build system. Current uncommitted work is not automatically deployable from GitHub; review and authorize a release separately.
- A new Supabase project with no Azari application data. Provider-managed schemas/tables are normal and must not be removed.
- A controlled operator/CI environment for migrations, with the same application revision and dependencies as the backend image.
- Approved HTTPS frontend/backend hostnames, generated production secrets, and the database provider's TLS certificate material.

Free Render web services are suitable for a preview, not a production reliability commitment: they sleep after inactivity, have ephemeral storage, and lack persistent disks, shell access and one-off jobs. Run one-time operations from a controlled external runner if using Free. Choose paid capacity before relying on uptime. [Render free-service limitations](https://render.com/docs/free)

## C. Environment variables

The following are placeholder-only contracts, **not files to copy over the local `.env`**. Set values in the backend service's secret/environment settings. Do not print them in logs or shell history.

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+psycopg://<runtime-role>:<url-encoded-password>@<database-host>:5432/postgres?sslmode=verify-full&sslrootcert=/run/secrets/supabase-ca.crt
JWT_SECRET=<new-cryptographically-random-secret-at-least-32-characters>
CORS_ORIGINS=["https://<frontend-render-domain>"]
API_V1_PREFIX=/api/v1
ML_MODEL_DIR=/app/ml/models
ML_CONFIDENCE_THRESHOLD=0.65
PORT=8000
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT_SECONDS=2
DB_CONNECT_TIMEOUT_SECONDS=5
DB_MAX_CONCURRENT_SESSIONS=15
DB_ADMISSION_TIMEOUT_SECONDS=1
```

The certificate path above must actually be provisioned and readable in the deployment/runner; it is not provided by this repository. Use the exact provider hostname and certificate trust chain. `sslmode=require` encrypts transport but should not be mistaken for full certificate/hostname verification. Prefer `verify-full`; never disable TLS to bypass connection errors.

Encode the username/password URL components once. For example, a password's `@` becomes `%40` and a literal `%` becomes `%25`. Do not encode the entire URL or put `%%` into `DATABASE_URL`. Alembic now escapes percent signs only at its ConfigParser boundary; SQLAlchemy receives the original URL. Query parameters are preserved.

`PORT` is a Render setting, not an application Settings field. Setting it to 8000 matches the existing image command. Optional JWT algorithm/expiry and rate-limit settings retain their existing defaults. Production disables interactive API documentation; it does not itself validate that every supplied secret is strong.

Frontend build environment, separately:

```dotenv
VITE_API_URL=https://<backend-render-domain>/api/v1
NODE_VERSION=22
```

Vite embeds `VITE_*` values into public JavaScript. Never put `DATABASE_URL`, JWT secrets, Supabase keys or bootstrap credentials there. The API URL has no trailing slash. Rebuild after changing it.

### Connection budget

Retain the existing settings initially; do not increase workers or pools. `pool_pre_ping=True` remains enabled. One process can use up to 5 + 10 = 15 connections, with a 2-second pool wait and 5-second connection timeout. Admission allows at most 15 sessions with a 1-second wait. Alembic uses NullPool and normally one connection.

Before launch check the actual Supabase project and pooler limits: budget at least `15 * simultaneous backend processes + migration connections + operational reserve`. Count overlapping old/new deployments and other clients, not just steady-state workers. If the project cannot accommodate this, lower pool/admission values together in deployment configuration and measure before launch. Keep admission no greater than pool capacity. These defaults are not proof of free-tier capacity. Rate limiting is process-local, so adding workers has security as well as capacity implications.

## D. Supabase setup and access model (later only)

Use the exact endpoint, port, database and username from the project's connection settings, changing the SQLAlchemy scheme to `postgresql+psycopg`. A pooler username can include the project reference; do not guess it.

- Prefer direct PostgreSQL for the long-running backend and migration runner when reachable.
- If direct IPv6 is unavailable from a runner/backend, use the **session-mode** pooler endpoint as the IPv4-compatible alternative.
- Do not select transaction pooling for this unchanged driver configuration: Psycopg can use prepared statements, and transaction-pooler compatibility requires separate validation/configuration. No such driver change is included here.

[Supabase connection methods](https://supabase.com/docs/guides/database/connecting-to-postgres), [prepared statement constraints](https://supabase.com/docs/guides/troubleshooting/disabling-prepared-statements-qL8lEL)

Use separate database roles: a controlled migration/schema-owner role with the required DDL and migration-data permissions, and a runtime login with CONNECT, schema USAGE, and only required application-table CRUD/sequence privileges. Runtime should not own tables, create/drop schemas, manage roles, or have superuser privileges. Apply grants for existing and future objects created by the migration role. Include RBAC reads and audit writes. Verify both roles' search path resolves the same application tables (currently unqualified/public). Bootstrap uses a controlled role with permission to write identity/RBAC tables, not browser credentials. Do not create these roles in Stage 2B.

**Before creating application tables, disable Supabase's Data API for this backend-only application.** FastAPI permissions do not protect a separate Data API endpoint. If other applications require that API, stop and explicitly design exposure/grants so Azari tables are inaccessible to `anon`/`authenticated`, including default privileges. Do not expose the public accounting tables without this control. No Supabase Auth or replacement RLS scheme is required for the chosen backend-only access path. [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api)

## E. One-time database migration procedure

**Commands below are instructions for later, not commands executed against Supabase in Stage 2B.** Use the repository root in a controlled environment without the local development `.env`. Inject `DATABASE_URL` for the migration role plus required settings through the runner's secret mechanism. There is no separate migration-URL application setting.

1. Confirm the target project/host/database through secure configuration review. It must not be local `db`, a load-test database, or an existing production database.
2. Establish TLS connectivity with a read-only `SELECT 1` using the configured driver. Do not echo the URL; use a secret-injected diagnostic that reports success/failure without connection details.
3. Verify application tables are absent and provider-managed objects remain untouched.
4. Inspect the release graph and upgrade:

```sh
python -m alembic -c backend/alembic.ini heads
python -m alembic -c backend/alembic.ini history
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current
```

Expected head for this release: `20260910_0014`, one linear chain of 15 migrations. Use the config path on every command because the root has no default `alembic.ini`. There are 26 application tables plus `alembic_version`.

`stamp head` and `create_all()` are **not** substitutes for migrations. Do not autogenerate or apply a new schema diff against Supabase's own objects blindly: current metadata filtering does not explicitly exclude unrelated tables in the default schema. An `alembic check` result needs review in that environment.

Migrations 0010/0011 contain legacy ownership/role handling; the fresh-database path must use the reviewed current files, including the existing uncommitted fresh-database fix in 0011. Do not deploy an older GitHub snapshot by accident. Serialize migration execution. Do not run migrations in image builds or on every backend startup.

## F. RBAC bootstrap and first administrator

After migrations, before allowing public registration, inject BOTH temporary values through the controlled runner:

```dotenv
BOOTSTRAP_ADMIN_EMAIL=<owner-controlled-email>
BOOTSTRAP_ADMIN_PASSWORD=<new-unique-strong-password-12-to-128-characters>
```

Run:

```sh
python -m backend.app.db.bootstrap
```

This seeds canonical roles/permissions and creates the administrator if that email does not already exist. It does not promote an existing account or reset its password. If the email already exists unexpectedly, stop and investigate. Remove both bootstrap variables from the runner/runtime environment afterwards. Do not expose them in frontend configuration or rely on every service restart to bootstrap.

Verify controlled admin login, then public registration receives OWNER, not ADMIN. Confirm a second user cannot read/write the first user's accounting records and cannot manage platform users.

## G. Render backend configuration

| Setting | Value |
|---|---|
| Service | Web Service, Docker runtime |
| Repository root | Repository root (leave Root Directory unset) |
| Dockerfile | `backend/Dockerfile` |
| Docker build context | `.` (repository root, includes backend and ml source) |
| Port | `PORT=8000`, matching container port 8000 |
| Start command | Existing image CMD: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000` |
| Worker count | Existing single worker; do not add workers for this preparation |
| Health check path | `/api/v1/ready` |
| Environment | Backend contract in C, runtime DB role after migration/bootstrap |
| Migrations/bootstrap | Controlled one-time process in E/F; no startup override that runs them |

The Dockerfile exposes 8000 and runs as non-root `azari`. It does not execute migrations/bootstrap; local Compose adds those commands separately. Render does not need or run the local Compose database service. Bind to `0.0.0.0`, not localhost. [Render Docker configuration](https://render.com/docs/docker), [port binding](https://render.com/docs/web-services)

## H. Render frontend configuration

Deploy as a **Static Site**, not a second Docker Web Service: the frontend is a client-rendered Vite SPA with no Node server requirement.

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Publish directory | `dist` (relative to frontend root) |
| Build environment | `NODE_VERSION=22`, public `VITE_API_URL` from C |
| SPA rule | Source `/*`, destination `/index.html`, action **Rewrite** (200, not redirect) |

Test direct visits and refreshes on `/dashboard`, `/customers`, and other client routes. Static assets must still be served normally. [Render Static Sites](https://render.com/docs/static-sites), [rewrites](https://render.com/docs/redirects-rewrites)

Static hosting does not use `frontend/nginx.conf`. Recreate the existing security headers in Render's static-site header settings for `/*`:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://<backend-render-domain>; img-src 'self' data:; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
```

Replace the backend placeholder before launch. Validate browser network/CSP errors and self-hosted fonts; do not loosen to wildcard script sources to fix a configuration mistake.

## I. CORS

The actual Settings type is `list[str]`: the environment value must be a JSON array, not a bare URL or comma-separated string:

```dotenv
CORS_ORIGINS=["https://<frontend-render-domain>"]
```

Use exact origins, no paths/trailing slash, and no wildcard. Add an approved custom frontend domain to this array when applicable. Leave localhost origins only in local development configuration. Validate OPTIONS preflight and authenticated requests from the actual deployed frontend; CORS is not a substitute for authentication.

## J. ML artifact provisioning

Each approved model version needs `metadata.json` and `model.joblib` beneath `ML_MODEL_DIR`, with matching pipeline/schema/dependency/fingerprint/digest information. Current example artifact IDs are:

| Pipeline | Artifact directory relative to ML_MODEL_DIR |
|---|---|
| transaction_classification | `transaction/transaction-v1` |
| payment_delay_risk | `payment-risk/payment-risk-v1` |
| cash_flow_forecast | `cash-flow/cash-flow-v1` |
| customer_segmentation | `segmentation/customer-segments-v1` |

Confirm approved IDs/versions against actual release artifacts; do not assume directory existence means a model is trusted. Current models are synthetic/demo models, not evidence of real-world accuracy.

`.dockerignore` excludes model artifacts. The existing Dockerfile therefore does **not** deliver working model files to Render. Local Compose's read-only host bind is not available on Render. Supabase stores registry metadata/predictions, not these serialized model files.

For a later deployment, prefer a controlled, versioned image containing approved artifacts, assembled from a trusted release source. Artifact directories/files and their parent trust boundary must be root-owned and non-writable by `azari` (for example directory 0555/file 0444), with a pre-created model root. A later image build adjustment must occur after the current broad `/app` chown, not be undone by it. Verify non-writability as the runtime user. A properly read-only provisioned mount is an alternative on infrastructure that supports it; a writable persistent disk alone does not satisfy model trust. Do not download arbitrary Joblib files or train/upload models on public startup. No artifact/image provisioning change is made in Stage 2B.

Backend startup can succeed without model files if the configured model root exists or can be created. That is not ML readiness. On a fresh registry, active-model lookups and the four inference endpoints under `/api/v1/ml` (`transactions/classify`, `payment-risk/predict`, `cash-flow/forecast`, `segmentation/predict`) cannot produce predictions: no active model maps to 404. Invalid/missing artifact validation maps to a sanitized 422; execution errors map to 503. Registry/history listing can still work with an initialized database.

After trusted files are provisioned, use existing authenticated `/ml/models/register` and `/ml/models/{model_id}/activate` APIs for all four approved versions, then test each inference path with owner-scoped sample data. File presence alone does not create/activate database registry rows. Keep tokens/artifact paths out of public logs. ML management currently includes OWNER permission and the registry is global; review who may activate shared models before a multi-user production launch.

## K. Health checks

- `/api/v1/health`: process liveness, not database readiness.
- `/api/v1/ready`: obtains an admitted DB session and performs `SELECT 1`; use for Render health checks. Unavailable/overloaded DB returns 503.
- Neither proves migration head, RBAC seed, ownership isolation, accounting correctness, or ML readiness. Those require explicit smoke checks.

Local Compose already checks readiness, PostgreSQL with `pg_isready`, and frontend with an HTTP request. The Dockerfile itself has no embedded HEALTHCHECK; configure Render's HTTP health path separately.

## L. Verification checklist

Before release: backend/ML tests, frontend `test.cmd` (or its typecheck + SSR build + Node test commands), production build, Ruff, strict mypy, Alembic heads/history, Docker build and safe import/config validation. Unit fixtures use isolated in-memory SQLite; this is not a fresh Supabase migration rehearsal or PostgreSQL concurrency verification.

After separately authorized deployment:

- Confirm TLS, exact migration revision, runtime-role grants, and disabled accounting-table Data API exposure.
- Confirm admin bootstrap and OWNER registration; two-user read/write/report isolation.
- Check both health endpoints, SPA deep-link refresh, CORS, HTTPS, and response headers.
- Issue a small test invoice, post a receipt, verify balanced journal and matching receivables; test bills/expenses and owner isolation. Use only explicitly authorized cloud smoke-test data.
- Validate all four ML pipelines after registration/activation and confirm writable artifacts are rejected.
- Measure latency, 503/429 rates, DB connections, and memory on chosen capacity. Local load results do not certify cloud/free-tier capacity.

Do not restart/rebuild the local Compose stack merely to test cloud preparation: its startup command runs migrations/bootstrap against the local database. A config render, standalone image build, and network-disabled import test avoid that risk.

## M. Troubleshooting

| Symptom | Check |
|---|---|
| ConfigParser percent error | Deploy the corrected `alembic/env.py`; environment URL contains ordinary percent escapes, not doubled ones |
| Connection timeout/DNS failure | Exact endpoint/username, outbound connectivity, IPv6 versus session IPv4, and network restrictions |
| TLS failure | Provider hostname, certificate file provision/mount/readability, trust chain; do not disable verification |
| Ready is 200 but routes fail | Schema head, table grants, RBAC bootstrap; SELECT 1 does not test them |
| CORS failure | JSON array of exact frontend HTTPS origins and matching build-time API URL |
| Frontend still calls localhost | Rebuild with production VITE_API_URL; runtime env cannot change an old bundle |
| Deep link 404 | Static Site rewrite, not a redirect |
| No active model/model unavailable | Approved read-only files plus registry registration/activation and compatible dependencies |
| Cold first request | Free service sleep; not necessarily a DB/schema defect |
| 503 under load | Admission/pool budget, backend memory and DB capacity; do not blindly retry financial writes |

## N. Security notes

Generate new cloud credentials; do not reuse local/development credentials or values previously shared in chats. Store secrets only in controlled backend/runner environments. `.env` stays excluded from Docker/Git; never publish database dumps. Restrict migration credentials and keep them out of normal runtime. Review Supabase network controls and account access. Do not log DSNs, bootstrap passwords or JWTs.

Keep production API docs disabled, HTTPS public URLs, exact CORS, static security headers, and existing backend authorization. A working database login does not prove least privilege. Validate attempted DDL is denied for runtime and browser/Data API cannot read application tables. Avoid automatic rollback/retry of financial writes with uncertain commit outcome.

## O. Rollback/recovery

Record the application/image release, migration head, approved ML versions and secure configuration references before deployment. Before later schema changes, take a controlled cloud backup/snapshot and test recovery into a separate database according to the selected provider plan. Do not use or overwrite the local Docker database as a recovery target.

If a deploy fails before public use, stop traffic, inspect sanitized logs and migration state, and correct forward. An application rollback is safe only if the previous release supports the current schema. Do not automatically downgrade: ownership/role and phone migrations have data/security implications, including the OWNER-role downgrade restoring ADMIN membership. Never delete provider-managed schemas or stamp over a failed migration. After real users enter data, preserve it and use a reviewed forward fix or verified separate-target recovery with explicit approval.

## Stage 2B boundary

Only Alembic URL interpolation, its regression tests, and this guide are changed for Stage 2B. No migration graph, local configuration, frontend, authentication, model behavior or production infrastructure was changed. Cloud TLS/networking, actual grants, migration execution and ML provisioning remain future verification gates.

### Local verification performed, 2026-09-10

| Check | Result |
|---|---|
| Backend + ML pytest | 149 passed: 138 backend, 11 ML; 95% combined coverage |
| New online/offline URL regressions | 8 passed, no actual DB connections |
| Ruff (`backend ml`) | Passed |
| Strict mypy (`backend/app ml`, backend config) | Passed, 71 source files |
| Frontend `test.cmd` | 35 passed; includes TypeScript check |
| Frontend `npm run build` | Passed, 58 modules; includes TypeScript check |
| Alembic heads/history | One head `20260910_0014`, 15 revisions |
| Backend Docker build | Passed, local image `azari-stage2b-check` |
| Production-config image import | Passed in network-disabled disposable container, no DB connection |
| Local Compose configuration | `docker compose config --quiet` passed |
| Existing local services | Backend health/ready and frontend HTTP 200; all three containers healthy; no restart |
| `git diff --check` | Passed |

The initial `npm test` attempt found no script; the project's actual `test.cmd` passed. Ruff initially found an import-order issue in the new test, which was corrected before rerunning. A Windows shell quoting error in the first disposable import command was corrected; the application import then passed. Pytest reported non-failing Starlette/httpx and Joblib/NumPy deprecations and a Windows pytest-cache permission warning. Existing unit fixtures create temporary/in-memory SQLite tables, not local PostgreSQL tables. Test/build tooling produces its normal ignored output/cache files; no existing source changes were discarded. No external DB migrations, cloud smoke tests, or cloud capacity tests were performed.
