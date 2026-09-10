# Setup

## Stage 10 clean-start verification

Normal startup remains `alembic upgrade head`, bootstrap, then Uvicorn. Migration 0011 now safely skips legacy ADMIN-holder conversion only when no users exist; it still fails closed if users exist without ADMIN. Do not use the older load-verification startup workaround for deployment. Migration 0014 adds three lookup indexes; plan a maintenance window for large existing tables because creation uses transactional, non-concurrent DDL.

An isolated smoke test uses `compose.load-verification.yaml` plus `compose.stage10-verification.yaml` with project name `azari-stage10-smoke`, disposable VERIFY_DB_PASSWORD/VERIFY_JWT_SECRET environment values, and the locally built `azari-stage10-final:latest` backend image. It exposes frontend14175/backend18104, not normal application ports, and uses its own database. Never run load/outage scripts against the real application database. Stage 10 verified fresh startup, clean drift and recovery, but **did not verify 250+ user capacity**. See [full results](../STAGE_10_PERFORMANCE_REPORT.md).

## Docker development

Install Docker Desktop (or Docker Engine with Compose), copy `.env.example` to
`.env`, replace all placeholder credentials, and run:

```shell
docker compose up --build
```

The Compose backend command waits for healthy PostgreSQL, runs
`alembic upgrade head`, idempotently seeds canonical roles/permissions, and then
starts Uvicorn. The image default itself only starts Uvicorn so migration policy
can be controlled independently outside the development Compose environment.
All three backend commands run as the image's unprivileged `azari` user.

The Persian frontend is available at `http://localhost:4173`; the API is at
`http://localhost:8100/api/v1`. The browser uses the host API URL while
containers retain Docker service-name networking internally. Light mode is the
default; display theme and Jalali/Gregorian calendar preferences persist in the
browser. JWT access tokens are session-scoped and removed on logout or HTTP 401.

## Backend without Docker

Python 3.12 is the supported runtime. From the repository root:

```shell
python -m venv .venv
.venv/Scripts/pip install -e "backend[dev]"
copy .env.example .env
.venv/Scripts/uvicorn backend.app.main:app --reload
```

Adjust `DATABASE_URL` for a reachable PostgreSQL instance. Apply migrations and
bootstrap RBAC before starting the local API:

```shell
.venv/Scripts/alembic -c backend/alembic.ini upgrade head
.venv/Scripts/python -m backend.app.db.bootstrap
```

Run tests with:

```shell
.venv/Scripts/pytest backend/tests
```

Stage 3 PostgreSQL verification must target a disposable database named exactly
`azari_stage3_test`. Apply migrations to it, run
`python -m backend.scripts.verify_stage3_postgres`, and remove it afterward.
The script refuses to run against any other database name.

Stage 4 PostgreSQL report verification similarly requires a disposable database
named `azari_stage4_test` and runs with
`python -m backend.scripts.verify_stage4_postgres`. Remove the database after
the check; the script refuses any other database name.

## Frontend without Docker

From `frontend/`, run `npm.cmd install` and `npm.cmd run dev` on Windows. The
frontend reads `VITE_API_URL`; its default is `http://localhost:8100/api/v1`.

Run frontend quality gates from the same directory:

```powershell
npm.cmd run typecheck
npm.cmd run build
.\test.cmd
```

`test.cmd` creates an ignored SSR test bundle and uses Node's test runner, so
the project does not require an additional browser-test runtime dependency.

## Required secrets

`JWT_SECRET` must be a random value at least 32 characters long. Never use the
example placeholder outside initial local setup and never commit `.env`.

`BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` are optional and must be
set together. The password must be 12–128 characters. Bootstrap is idempotent
and never overwrites an existing user. Omit both in production and provision
administrators through a controlled operational process.

### Rotate PostgreSQL and JWT secrets without deleting data

Changing `POSTGRES_PASSWORD` in `.env` does not change the password of a role
inside an already initialized PostgreSQL volume. The repository therefore
provides a manual rotation script that generates a 48-byte URL-safe database
password and a separate 64-byte URL-safe JWT secret. It executes `ALTER ROLE`
against the running database, then atomically updates `POSTGRES_PASSWORD`,
`DATABASE_URL`, and `JWT_SECRET` in `.env`. Secret values are never printed.

Run this yourself from the repository root during a maintenance window:

```powershell
.\scripts\rotate_secrets.ps1
docker compose up -d --force-recreate backend
docker compose ps
curl.exe -i http://localhost:8100/api/v1/health
```

The first command requires the existing `db` service to be running and performs
the live role-password update without recreating `postgres_data`. Existing JWT
access tokens become invalid after the backend is recreated, so users must sign
in again. Back up the database first and never paste generated values into logs,
shell history, tickets, or chat. If a deployment uses an external secret store,
perform the equivalent `ALTER ROLE` transaction and update the secret store
instead of using this local `.env` helper.

The repository ignores `.env`; verify that remains true with:

```powershell
git check-ignore -v .env
git log --all --full-history -- .env
```

The second command must produce no history when `.env` has never been committed.

## Database backup and restore

Create a timestamped plain-SQL PostgreSQL backup while the Compose database
is running:

```powershell
$backup = .\scripts\backup_db.ps1
$backup
```

Backups are written to the ignored `backups/db/` directory by default. Pass
`-OutputDirectory D:\secure\azari-backups` to store them on separate protected
storage. Copy backups off the application host, encrypt them at rest, restrict
access, and test restoration regularly.

Restore always targets a new database and refuses to overwrite the active
`POSTGRES_DB` or any database that already exists:

```powershell
.\scripts\restore_db.ps1 -BackupPath $backup -TargetDatabase azari_restore_test
docker compose exec -T db psql -U azari -d azari_restore_test -c "SELECT version_num FROM alembic_version;"
```

Validate the restored database before changing any deployment connection. For
a disaster recovery cutover, stop application writes, restore to a new database,
validate migrations and business data, then change the deployment's database
URL in a separately reviewed operation. The script deliberately does not drop
or overwrite the production database.

## Production HTTP hardening

Set `APP_ENV=production` to disable `/docs`, `/redoc`, and `/openapi.json` and
return a generic response for unexpected server errors. The API sends restrictive
JSON-oriented security headers and emits HSTS only when the request is HTTPS.
The frontend Nginx image sends browser security headers but does not claim HSTS
over plain HTTP.

Login and registration have a process-local, per-client-IP sliding-window limit,
configured with `AUTH_RATE_LIMIT_ATTEMPTS` and
`AUTH_RATE_LIMIT_WINDOW_SECONDS`. This is intentionally suitable only for the
current single backend instance. Before adding workers or replicas, replace it
with a shared limiter. At a reverse proxy, accept forwarded client IPs only from
trusted proxy addresses; do not trust arbitrary client-supplied forwarding
headers.

### Future TLS termination runbook

TLS certificates and termination are not configured by this stage. Before an
internet-facing deployment: terminate TLS at a maintained reverse proxy or load
balancer, redirect HTTP to HTTPS, set the frontend API URL to its HTTPS origin,
restrict CORS and CSP to the deployed origins, forward the original scheme from
trusted proxies, and confirm HSTS appears only on HTTPS responses. Validate
certificate renewal and rollback in staging before enabling HSTS in production.

## Clean database

On a clean PostgreSQL database, run the Alembic and bootstrap commands above.
Never use `Base.metadata.create_all()` for application deployment; it is used
only by isolated unit-test fixtures.
