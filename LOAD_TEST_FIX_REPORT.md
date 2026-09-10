# Backend load-test investigation and fix

Verification: September 9–10, 2026. **Overall: PARTIAL PASS.**

## Executive summary

The reproduced unresponsiveness was a circular dependency between synchronous worker
availability and database-pool availability, not a demonstrated missing session.close().
Bounded asynchronous session admission now protects the worker pool and returns controlled
HTTP 503 under overload. Successful requests, exceptions and cancellation release sessions.
Repeated PostgreSQL load tests recovered without backend restarts. This is a reliability
fix, **not evidence that this deployment supports 1,000 simultaneous active users**.
100 simulated users passed; 250 exceeded the error threshold. Escalation stopped there.
No real accounting database was accessed or altered. No commit or push was made.

## Original failure and investigation

The original preserved LOAD_TEST_RESULTS.json records 2,635 requests at 100 users,
zero errors, p95 188 ms; at 1,000 users, 97.37% timed out and readiness was unreachable.
Containers did not crash. The diagnostic reproduction in LOAD_DIAG_BEFORE.json produced
1,012 requests, 12 successes and 1,000 ReadTimeout errors (98.81%); p95 was 10.046 s.

Inspection covered engine/session construction, get_db, authentication dependencies,
routes, service/repository session use, response serialization, health/readiness and
Docker settings. Request dependencies share one request-scoped session. The original
context manager already closed it on exit; no independent per-request repository pools
or proven exception-driven permanent connection leak explained the freeze.

The diagnosis plan was: reproduce on synthetic PostgreSQL, sample pool checkout/checkin,
PostgreSQL state/waits, worker usage/stacks, coroutine waits, query time and container
resources; identify the blocked resource chain before making a small change; repeat the
same workload progressively and verify recovery. No query/index tuning was justified.

## Evidence and root cause

- Runtime: synchronous SQLAlchemy ORM, FastAPI 0.141.1, Starlette 1.6.0,
  SQLAlchemy 2.0.52; one Uvicorn process, 40 AnyIO worker tokens.
- Original pool: default 5 retained connections + 10 overflow, 30-second pool wait.
- During the reproduced freeze, all 15 connections were checked out and all 40 worker
  tokens were occupied. Samples showed 38 workers waiting for pool acquisition during
  authentication and two in response validation/lazy database access.
- PostgreSQL showed 15 idle-in-transaction connections waiting on ClientRead, not a
  database lock convoy. These were application-held transactions waiting for Python work.
- Completed SQL time in an early frozen sample was approximately 1.65 seconds for 142
  statements, while connection holds reached approximately 18 seconds with no checkin
  progress. This does not prove every query is optimal, but SQL execution did not explain
  the stalled resource chain.
- PostgreSQL max_connections was 100; the server connection limit was not reached.
  Containers had no OOM/restart, and CPU/RAM exhaustion did not explain the frozen state.

Authentication checks out a connection before the synchronous endpoint and response
validation finish. Under overload, other authentication calls occupy the shared workers
waiting for those connections. Requests already holding connections need shared workers
to progress through endpoint/serialization before dependency cleanup can release them.
This produces worker/pool starvation. A larger pool alone would move the threshold rather
than remove this resource-ordering hazard. Long transaction holds were a consequence of
the stalled lifecycle, not evidence of an intentional long PostgreSQL query.

## Exact fix and session lifecycle

- get_db is now an asynchronous generator. It awaits a per-application AnyIO capacity
  permit without occupying a synchronous worker, before constructing the session.
- The permit remains held through endpoint execution and response serialization. The
  synchronous ORM, service transaction boundaries, commits and accounting locks remain
  unchanged. No async ORM conversion or early financial commit was introduced.
- finally closes/rolls back the session in a worker under cancellation shielding, then
  releases admission, including when session construction raises.
- Lifespan initializes the limiter and rejects settings that leave no worker capacity
  for completion. The gate defaults to 15, below the existing 40 worker tokens.
- Admission timeout, pool timeout and database OperationalError return sanitized 503
  with Retry-After: 1. Clients must not blindly retry non-idempotent financial writes.
- Liveness remains /api/v1/health. /api/v1/ready executes a real database query and may
  return 503 when the database or request capacity is unavailable; success remains 200.
- Diagnostics are isolated wrappers, not imported by the normal app. They record aggregate
  metrics and function names, not credentials, SQL values, personal or financial data.

### Pool and worker budget

| Setting | Default |
|---|---:|
| DB_POOL_SIZE | 5 |
| DB_MAX_OVERFLOW | 10 |
| DB_POOL_TIMEOUT_SECONDS | 2 |
| DB_CONNECT_TIMEOUT_SECONDS | 5 |
| DB_MAX_CONCURRENT_SESSIONS | 15 |
| DB_ADMISSION_TIMEOUT_SECONDS | 1 |

pool_pre_ping remains enabled. Maximum pooled connections are unchanged at 15 per process.
For W workers, budget W × (pool_size + max_overflow), plus migrations, administrative
connections and PostgreSQL reserves. For example, four workers permit 60 application
connections, but that is not a recommendation to run four workers on this tested host.
No worker-count increase, pool_recycle, new index or migration was introduced.

## Isolated environment and methodology

- azari-load-test Docker network and azari_load_test database, never the normal volume.
- Backend: 2 CPUs / 1 GiB, 127.0.0.1:18100 → 8000; PostgreSQL: 2 CPUs / 1 GiB,
  network-only 5432; frontend: 0.5 CPU / 128 MiB, 127.0.0.1:14173 → 80.
- Docker host reports 16 CPUs and approximately 11.5 GiB. Generator and services share
  the host; measurements are local, not an independent production benchmark.
- 10,000 synthetic OWNER accounts. Each seeded with 5 parties, 3 products, 3 invoices
  (1 issued, 2 draft), accounts/categories, a period and a balanced journal.
- Closed-loop API users, 5-second ramp, approximately 30-second stage, 0.8–1.2-second
  think time, 10-second request timeout. Approximately 90% reads / 10% draft invoice
  writes with preauthenticated JWTs. Added drafts are retained only in the synthetic DB.
- Samples include PostgreSQL state/waits, pool events, thread occupancy and Docker stats.
  Stage stops early after >5% observed errors once 50 requests complete; escalation stops
  if errors exceed 1%, p95 exceeds 2 seconds or post-stage readiness is not 200.
- VUs are simulated users, not necessarily simultaneously executing requests. Counts
  include successes and failures; latency includes unsuccessful requests. RPS uses total
  stage elapsed time including ramp/drain. Short aborted stages are not sustained capacity.

## Load results

| Run | VUs | Requests | Success | Fail | Average / median ms | p95 / p99 ms | Total / successful RPS | Readiness after |
|---|---:|---:|---:|---:|---|---|---|---|
| Original | 100 | 2,635 | 2,635 | 0 | Not recorded here | 188 / — | See original JSON | 200 |
| Baseline diagnostic | 1,000 | 1,012 | 12 | 1,000 timeouts | — / 10,016 | 10,046 / 10,062 | 38.48 / 0.46 | Unreachable |
| Fixed final image, Sep 9 | 100 | 2,502 | 2,502 | 0 | 130 / 94 | 343 / 500 | 70.54 / 70.54 | 200 |
| Fixed final image, Sep 9 | 250 | 536 | 492 | 44 HTTP 503 (8.21%) | 700 / 766 | 1,218 / 1,281 | 71.31 / 65.46 | 200 |
| Resumed repeat, Sep 10 | 100 | 2,247 | 2,247 | 0 | 256 / 219 | 594 / 812 | 64.17 / 64.17 | 200 |
| Resumed repeat, Sep 10 | 250 | 486 | 441 | 45 HTTP 503 (9.26%) | 716 / 797 | 1,203 / 1,359 | 49.53 / 44.94 | 200 |
| Fixed | 500 / 1,000 / higher | Not run | — | — | — | — | — | Escalation stopped |

The repeated 250-VU stage aborted after 9.81 seconds; maximum latency was 1.547 seconds,
peak in-flight requests 162. The 100-VU repeat lasted 35.01 seconds, maximum latency
1.219 seconds, peak in-flight 60. Client event-loop lag p95 was 3–4 ms.

### Connection and resource behavior

During the resumed 100/250 runs, sampled admission and worker usage stayed at or below 15.
Maximum sampled connection hold age was 0.760 / 0.525 seconds respectively. After drain:
zero checked-out connections, zero admission permits, zero borrowed workers and zero
PostgreSQL idle-in-transaction sessions. No backend restart was needed.

| Resumed VUs | Backend peak sampled CPU / memory | PostgreSQL peak sampled CPU / memory |
|---|---|---|
| 100 | 116.67% / 17.41% of 1 GiB | 60.06% / 8.03% of 1 GiB |
| 250 | 115.47% / 17.38% of 1 GiB | 44.87% / 7.64% of 1 GiB |

Docker CPU percentage can exceed 100% (one core); samples are not continuous maxima.
The Sep 9 sample likewise bounded admission to 15 and returned every connection.

An initial fixed test was launched before the server was ready and returned connection
errors. It is preserved as LOAD_DIAG_STARTUP_INVALID.json, excluded from capacity claims;
the diagnostic runner now waits for readiness. A first outage-check assertion incorrectly
assumed raw checkout/checkin event counts must always match. Failed pre-ping/reconnection
can emit checkin(None) without checkout. The corrected test checks actual zero pool
occupancy, no held connections and no admission permits instead; raw evidence is retained.

## Verification

| Check | Result |
|---|---|
| Backend pytest | 126 passed, including 5 new capacity/lifecycle cases |
| ML pytest | 11 passed |
| Combined full run | 137 passed; 95% combined coverage (3,590 statements, 171 missed) |
| Ruff | Pass: project-discovered backend/ML configuration and new diagnostic scripts |
| Strict mypy | Pass: 71 source files, backend/app and ml |
| Frontend test.cmd | 35 passed; TypeScript and Vite SSR test transform passed |
| Frontend production build | Pass; tsc --noEmit and Vite, 58 modules |
| Clean Docker builds | Backend --no-cache final image and isolated Compose frontend --no-cache passed |
| Normal docker compose config --quiet | Pass; no secret-bearing rendered output printed |
| Isolated Compose config/up -d --wait/ps | Pass; all three azari-capacity-smoke services healthy |
| Alembic current | 20260909_0013 (head), isolated load and smoke databases |
| Alembic check | No new upgrade operations detected |
| New migration / downgrade | None required: this task changes no schema |
| Smoke HTTP | /health 200, /ready 200, frontend 200 |
| Real PostgreSQL outage | /health 200, /ready 503 with sanitized body; recovered without backend restart |
| Connection recovery | Zero pool occupancy/admitted sessions after load and outage |
| Synthetic accounting integrity | Zero unbalanced POSTED journals; 10,000 issued invoices retained |
| git diff --check | Pass |

The real outage check took 7.891 seconds including liveness and readiness calls. Admission
timeouts bound waiting for capacity, not every SQL statement; a hard upper bound for all
queries/network outages is not claimed. No SQL statement_timeout was silently introduced.

New tests in backend/tests/test_database_capacity.py cover capacity shedding without
starving liveness, successful/exception cleanup and actual pool return, sanitized database
and pool errors (two cases), explicit PostgreSQL pool settings, and cancellation cleanup.
SQLite unit tests protect the lifecycle; the retained PostgreSQL load/outage scripts supply
the actual database evidence. Existing accounting, auth/RBAC and ML tests remain passing.
Warnings are pre-existing Starlette/httpx and Joblib/NumPy deprecations plus Windows pytest
cache permissions. An attempted direct Node TSX invocation was invalid; the repository's
frontend/test.cmd was used successfully instead. An explicit alternative Ruff config
invocation found existing import-order disagreements; the normal discovered project
configuration passes and unrelated files were not reformatted to satisfy that invocation.

### Docker smoke limitation

The normal compose.yaml remains unchanged: host backend 8100 → 8000, frontend 4173 → 80.
The smoke stack uses 18101 → 8000 and 14174 → 80 with a separate new synthetic database.
Existing migration 0011 requires seeded ADMIN before running against an empty DB. The
isolated smoke command explicitly upgrades to 0010, bootstraps roles, then upgrades head.
This verifies the app build, migrations and services, but **does not certify the normal
unchanged startup command on a brand-new empty database**. That pre-existing bootstrap
ordering issue is outside this performance fix and needs separate review.

## Files changed by this task

Runtime modifications only:

- .env.example: bounded DB capacity configuration documentation.
- backend/app/core/config.py: six validated settings.
- backend/app/db/database.py: pool options and asynchronous admission/cleanup.
- backend/app/main.py: limiter lifespan and sanitized transient database errors.

Verification/support:

- backend/tests/test_database_capacity.py (new).
- scripts/run_load_test.py: added average latency and successful RPS metrics.
- scripts/diagnose_load.py, scripts/performance_probe.py (new isolated diagnostics).
- scripts/verify_load_recovery.py (new guarded synthetic database outage check).
- compose.load-verification.yaml (new isolated smoke definition).
- LOAD_DIAG_BEFORE.json, LOAD_DIAG_AFTER.json, LOAD_DIAG_FINAL.json,
  LOAD_DIAG_RESUMED.json, LOAD_DIAG_STARTUP_INVALID.json, LOAD_RECOVERY_RESULTS.json.
- LOAD_TEST_FIX_REPORT.md (this report).

Existing dirty files from prior business-profile/expense/frontend/documentation work were
preserved. They are not performance-fix changes. .env, real volumes, business services,
RBAC, ML semantics, frontend functionality and migrations were not changed by this task.

## Remaining limits and recommendations

100 users is the highest tested passing short stage, not a guaranteed production limit.
250 exceeds this one-process deployment's configured admission throughput/queue budget.
It fails gracefully now, but increasing to 1,000 would violate the escalation rule.
Therefore whether a tuned deployment can serve 1,000 remains unverified; 10,000 registered
synthetic accounts do not imply 10,000 simultaneous active users.

Next, profile endpoint/query fan-out at the stable load level, measure longer soaks using
an independent generator, and compare modest worker counts with explicit total connection
and CPU/memory budgets. Adjust admission only with measured latency/throughput evidence.
Instrument queue wait, rejection rate, session hold time and DB statement latency in
production-safe metrics. Consider network/query deadlines separately, with accounting
rollback and concurrency regression coverage. Benchmark login hashing, ML inference,
payment posting, mixed reporting, browser/network behavior and realistic large accounts
separately; none are represented by this read/draft-write capacity claim. No distributed
rate limit, automatic write retry, async ORM redesign or larger pool was added speculatively.

## Git recommendation

Review and commit the performance fix separately from the existing dirty feature work.
Review retained diagnostic artifacts before inclusion. Do not stage .env or database dumps.
No commit or push has been performed.
