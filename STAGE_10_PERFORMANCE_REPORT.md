# Stage 10 — Performance profiling and capacity improvement

Date: 2026-09-10. Status: **PARTIAL PASS**. No commit or push performed.

## 1. Executive summary

Measured optimizations reduce database work without changing accounting rules. Customer summaries no longer perform three queries per customer; invoice/journal lists batch their child records; three demonstrated lookup scans now have indexes. Empty-database startup is repaired without granting roles to existing users differently.

100 virtual users passed both post-change runs. 250 failed both runs. 500/750/1,000 were deliberately not attempted after the stability gate failed. This is local Docker evidence, NOT a production capacity guarantee or a test of 10,000 simultaneous users.

## 2. Baseline configuration and isolation

Existing dirty work was retained on main (starting HEAD eddac1b). The pre-existing connection-admission fix was the baseline, not a Stage 10 change. Ordinary application containers/data were not used for load testing.

- One Uvicorn process; synchronous SQLAlchemy/psycopg operations dispatched through the existing worker mechanism; 40 AnyIO thread tokens.
- Pool size 5, overflow 10, maximum 15 connections/process; asynchronous admission 15, admission timeout 1s, pool timeout 2s, connect timeout 5s. No increase during this work.
- Test backend and PostgreSQL each limited to 2 CPUs/1 GiB. PostgreSQL 16: max_connections 100, shared_buffers 128 MiB, work_mem 4 MiB.
- Isolated database `azari_load_test`, Docker network `azari-load-test`. Existing 10,000 synthetic account fixtures, not real accounting data, were reused. API workflow probes create real persisted test transactions only in this isolated database; no mocked accounting implementation was introduced.
- Typical initial fixture per owner: five parties, three products, three invoices, accounts/categories, period and journal. This is many small workspaces, not a test of one very large enterprise ledger. Payables profiling uses an empty payable list and does not establish large-bill performance.
- Baseline image `azari-load-fixed-final`; final image `azari-stage10-final`. Probe ports 18102/18103. Diagnostic scripts are not imported by normal application startup and must not be deployed as public endpoints.

## 3. Baseline load results

The Stage 10 baseline is newly measured, not copied from the previous report.

| Users | Requests | Success | 503 | Other failures | p50 / p95 / p99 ms | Requests/s | Outcome |
|---|---:|---:|---:|---:|---|---:|---|
| 100 | 2,162 | 2,162 | 0 | 0 | 297 / 641 / 1,015 | 60.95 | Pass |
| 250 | 471 | 410 | 61 | 0 | 828 / 1,219 / 1,344 | 66.85 | Fail: 12.95% errors |

Evidence: `STAGE10_LOAD_BEFORE.json`.

## 4. Bottlenecks discovered

1. Customer summary listing executed three aggregate queries for every customer (3N+1 repository queries).
2. Invoice and journal response validation triggered lazy child SELECTs. Actual routes call `AccountingService.list`, not the similarly named repository method.
3. Invoice-item and journal-line lookup foreign keys lacked supporting indexes. Journal-line account aggregation also scanned unrelated rows.
4. At overload, admission queueing is still the primary observed wait. This is controlled load shedding, not evidence that simply increasing PostgreSQL connections is safe.
5. Migration 0011 required ADMIN before bootstrap even on a truly empty database, blocking ordinary fresh deployment.

## 5. Evidence and experiment history

For five customers, HTTP customer-summary queries fell from 19 to 7 (including three authentication queries). The repository component is now four queries regardless of customer count. Three-invoice HTTP listing fell from ten queries to six. Service-level tests verify invoice listing uses three queries and journal listing two, including response schema validation.

`STAGE10_PROFILE_AFTER.json` is an intermediate experiment, NOT the final result: it exposed that an initial repository-list optimization did not affect the actual API service path. That repository change was reverted. `STAGE10_PROFILE_FINAL.json` measures the corrected service implementation.

## 6. Database analysis

Actual ORM SQL and PostgreSQL EXPLAIN ANALYZE/BUFFERS are retained in `STAGE10_PLANS_BEFORE.json` and `STAGE10_PLANS_AFTER.json`, without query parameter values.

| Query family | Before ms | After ms | Plan change |
|---|---:|---:|---|
| Invoice items by invoice_id | 0.949 | 0.019 | Sequential scan to index scan |
| Journal lines by journal_id | 0.634 | 0.025 | Sequential scan/sort to indexed lookup/sort |
| Account activity aggregate | 1.905 | 0.146 | Scan-heavy aggregate to indexed nested-loop access |

These are individual warm/cached plan samples, not latency SLAs. New indexes: `ix_invoice_items_invoice_id`, `ix_journal_lines_journal_id`, `ix_journal_lines_account_id`. Existing owner and check lookup indexes were retained. No speculative broad index set was added.

Customer aggregation uses three separate grouped queries for issued invoice totals, posted receipts and posted CUSTOMER_CREDIT lines, then combines by party. Separate aggregates avoid multiplication from joining invoice items, payments and journal lines together. Decimal, owner filters and posted-state filters remain intact.

## 7. Connection-pool analysis

The repeat run gives the following mean instrumentation durations (milliseconds):

| Users | Admission | Pool acquisition | SQL cursor wall | Connection hold | Serialization wall | Total server wall |
|---|---:|---:|---:|---:|---:|---:|
| 100 | 31.19 | 1.97 | 49.89 | 82.78 | 6.88 | 133.20 |
| 250 | 491.39 | 1.33 | 70.00 | 122.95 | 11.93 | 640.09 |

At 250, admission reached 1,009ms, matching the configured load-shedding boundary. Pool acquisition is not the dominant wait. Acquisition includes physical connection creation, and cursor time includes scheduling/network wait: neither is pure PostgreSQL CPU time. Serialization may overlap lazy SQL; durations must NOT be added as independent CPU buckets. Remaining application wall time includes scheduling, framework, validation and transport; no CPU flamegraph was captured, so a precise CPU attribution is not claimed.

Sessions are created lazily and acquire connections on SQL. Posting may check out again after commit/refresh, but does not intentionally hold multiple simultaneous connections for a single service transaction. Nested accounting operations retain the existing session and atomic transaction. Audit work and serialization remain inside the existing lifetime where required. After overload and a deliberate database outage, checked-out connections, held connections and admission permits returned to zero.

## 8. Worker/concurrency budget

For W processes, maximum application connections are 15W, before migration, administration and other services. Current test W=1 leaves substantial headroom below PostgreSQL max_connections=100. Forty thread tokens are not forty database permissions. Admission bounds database users before they occupy all worker capacity; protected cleanup remains unchanged.

Do not infer that six workers are safe merely because 90 is below 100. CPU/memory, operational reserve and the process-local authentication rate limiter must be considered. No worker, pool, timeout, cache or rate-limit change was made in Stage 10.

## 9. Endpoint profiling

Final sequential samples, milliseconds. Each endpoint has 12 samples except login (3, preserving rate limits). Percentiles use sorted sample index floor((N-1)*p), as in the harness; with these small samples p95 and p99 coincide. Sequential requests/s is 1/mean latency, not concurrent capacity. All listed requests succeeded. Raw files retain admission, SQL, serialization and ML timings per request.

| Endpoint/workflow | p50 | p95 | p99 | Sequential req/s | Mean SQL ms |
|---|---:|---:|---:|---:|---:|
| auth/me | 8.3 | 27.8 | 27.8 | 45.2 | 2.33 |
| auth/login | 77.9 | 77.9 | 77.9 | 13.4 | 5.61 |
| parties | 9.4 | 25.7 | 25.7 | 61.3 | 2.28 |
| products | 9.1 | 24.6 | 24.6 | 67.8 | 2.01 |
| accounts | 9.4 | 28.6 | 28.6 | 62.6 | 1.94 |
| invoices | 11.6 | 33.2 | 33.2 | 50.6 | 3.11 |
| customers report | 11.9 | 26.0 | 26.0 | 61.3 | 4.29 |
| trial balance | 9.9 | 25.1 | 25.1 | 70.2 | 2.71 |
| income statement | 10.1 | 26.2 | 26.2 | 64.7 | 2.35 |
| balance sheet | 10.0 | 14.4 | 14.4 | 86.7 | 2.63 |
| receivables | 11.4 | 29.4 | 29.4 | 53.8 | 2.73 |
| payables | 9.7 | 23.0 | 23.0 | 74.0 | 2.47 |
| cash flow | 9.8 | 13.5 | 13.5 | 87.3 | 2.31 |
| dashboard | 14.1 | 14.6 | 14.6 | 63.7 | 4.24 |
| party history | 14.5 | 27.5 | 27.5 | 55.7 | 4.35 |
| journal create | 16.2 | 33.6 | 33.6 | 41.9 | 4.40 |
| journal post | 14.3 | 19.2 | 19.2 | 62.5 | 3.45 |
| journal reverse | 31.7 | 34.2 | 34.2 | 35.5 | 6.85 |
| invoice create | 15.4 | 31.9 | 31.9 | 49.7 | 4.30 |
| invoice issue | 24.6 | 40.8 | 40.8 | 29.6 | 8.48 |
| payment create | 14.0 | 31.6 | 31.6 | 51.6 | 3.11 |
| payment post | 24.6 | 44.2 | 44.2 | 34.1 | 8.33 |
| ML classification | 14.5 | 42.3 | 42.3 | 46.1 | 2.77 |
| ML payment risk | 30.7 | 52.0 | 52.0 | 22.8 | 4.27 |
| ML cash flow | 17.2 | 42.7 | 42.7 | 35.5 | 3.34 |
| ML segmentation | 16.9 | 40.5 | 40.5 | 36.5 | 3.74 |

Mean pool acquisition was about 0.01ms per endpoint except auth/me (3.26ms including initial connection). These low-load observations do not replace the loaded timings above.

## 10. Reporting/dashboard and frontend

Customer summary mean latency: 32.8ms to 16.3ms. Dashboard: 21.7ms to 15.7ms. Trial balance: 22.9ms to 14.2ms. Owner predicates, date predicates, issued/posted filters and Decimal arithmetic remain unchanged. Party-history child loading is batched, but its one-invoice profiling fixture does not establish large-history capacity.

Frontend inspection found dashboard fan-out to five APIs and repeated cash-flow computation (dashboard plus cash-flow API). Login can fetch auth/me both directly and through the token effect. No continuous polling was identified in the inspected loading hooks. Unbounded lists and large histories remain scalability limits. No frontend source, Persian wording, layout, theme or navigation was changed by Stage 10.

## 11. Accounting transactions

Invoice issuance still performs 22 queries and payment posting 25 in these fixtures. These include required lookups, row locking, journal creation, audit and refresh. They were not removed to inflate benchmark throughput. Direct journal posting, issuance and receipt posting retain shared validation and lock ordering. Closed-period, account-role/category, payment-allocation, immutable posted entries, balanced journals and rollback checks remain in place.

Mean issue latency: 35.4ms to 33.8ms; payment post: 33.6ms to 29.3ms. Gains here are modest; the primary improvements are read queries and indexes.

## 12. ML performance

Existing four trusted artifacts were used without retraining or changing prediction semantics. Initial model load times: classification 19.67ms, risk 105.25ms, cash flow 28.85ms, segmentation 17.15ms. Each subsequent set of 11 warm requests performed zero artifact loads. Mean warm inference: 0.84/13.11/0.44/1.10ms respectively.

The session still spans feature acquisition, inference and prediction/audit persistence. Splitting this safely requires an explicit snapshot/model-version consistency design; it was not justified by the measured warm inference cost in this narrow change. Model trust, digest, read-only artifact and ownership protections were not altered. Cold start and multi-process cache behavior remain operational concerns. Cash-flow and segmentation total mean latency increased slightly (24.8→28.1ms and 26.5→27.4ms); no universal speedup is claimed.

## 13. Implemented changes and startup fix

- Batched customer financial aggregates and eager child loading only on read-list/history paths.
- Migration 0014 adds the three measured indexes; no financial column or accounting rule changes.
- Migration 0011: when ADMIN is absent AND users table is empty, there are no legacy role holders to convert, so skip that conversion. Existing users without ADMIN still fail closed. Existing-user conversion remains unchanged.
- Reproduction: normal upgrade head on a fresh database previously stopped in 0011 before bootstrap could run. After the fix normal upgrade head then bootstrap succeeds, including the new isolated three-service Compose stack. Downgrade to 0010 then upgrade/bootstrap also succeeded on the test database.
- Two existing PostgreSQL verification scripts needed owner_id fixture fields to work with the current schema; their concurrency assertions were not relaxed.

0011 is a narrowly corrected historical migration because a later revision cannot repair a failure occurring before it. Index creation uses ordinary transactional DDL; large deployed tables require a planned maintenance window. No real database was migrated during testing.

## 14. Before/after measurements

At 100 users, first final run p95 improved 641→157ms (75.5%), throughput 60.95→78.15 requests/s (28.2%). The repeat achieved p95 328ms and 72.54 requests/s: still improved, but demonstrates local variability. Query-count and query-plan improvements are stronger causal evidence than isolated timing samples. Different isolated owners with equivalent initial shapes were used for destructive API workflow profiles; warm caches and accumulated test transactions can affect timings.

## 15. Regression verification

| Check | Result |
|---|---|
| Baseline backend + ML | 126 + 11 = 137 passed |
| Final backend + ML | 130 + 11 = 141 passed; combined coverage 95% (3,607 statements, 171 missed) |
| Frontend before and after | 35 passed |
| Ruff | Passed, including Stage 10 scripts |
| Strict mypy | Passed, 71 source files |
| TypeScript / production build | Passed, 58 modules |
| PostgreSQL Stage 9 Phase B | Passed allocation/tax replay |
| PostgreSQL Stage 9 locking | Passed period-close and account category/role mutation races |
| Populated migration 0014 down/up | Passed; row-content hashes/counts identical across 26 application tables |
| Alembic drift | Clean on populated test database and fresh Compose database |
| Fresh Compose | Valid; all three containers healthy; health/ready/frontend HTTP 200 |
| Database outage | health 200, ready sanitized 503, recovery without backend restart; no retained permits/connections |
| git diff --check | Passed; Windows line-ending advisories only |

Four new regression tests cover batched summary parity/query count, list child-query bounds, empty migration success and nonempty missing-ADMIN fail-closed behavior. Existing backend warnings (3,731) are non-failing dependency/deprecation warnings, not silently discarded failures. Frontend tests are not browser E2E load tests.

## 16. Final load tests

Five-second ramp, 0.8–1.2s think time, nominal 30-second phases, 10s request timeout, API clients not browsers. The existing harness can stop early on failures; durations include ramp/drain. Progression gate: error rate at most 1%, p95 at most 2s, readiness 200. Authentication is separately profiled, not a 1,000-user login storm. Endpoint workload and per-path timings are in scripts/run_load_test.py and raw artifacts.

| Run/users | Requests | Success | Controlled 503 | Other failures | p50/p95/p99 ms | req/s | Result |
|---|---:|---:|---:|---:|---|---:|---|
| Final/100 | 2,656 | 2,656 | 0 | 0 | 46/157/234 | 78.15 | Pass |
| Final/250 | 3,293 | 3,169 | 123 | 1 RemoteProtocolError | 1,032/3,063/5,907 | 95.36 | Fail (3.77%) |
| Repeat/100 | 2,488 | 2,488 | 0 | 0 | 109/328/391 | 72.54 | Pass |
| Repeat/250 | 449 | 423 | 26 | 0 | 703/1,156/1,203 | 67.62 | Fail (5.79%) |
| 500/750/1,000 | — | — | — | — | — | — | Not run: 250 failed |

No 4xx or timeout exceptions were recorded in these load phases. The single RemoteProtocolError was not reproduced in the repeat; backend remained running, OOMKilled=false, RestartCount=0, and no matching application traceback was found. Its precise transport cause is unresolved and is not relabeled a controlled 503.

## 17. Resource usage and recovery

Repeat sampled backend CPU peaks: 113.79% at 100, 117.26% at 250 (100% is one CPU). PostgreSQL peaks: 48.76% and 26.74%. Memory peaks: backend 16.62%/17.14% of 1GiB; PostgreSQL 10.02%/10.12%. Original final run backend CPU peaked at 178.15% at 100 users, illustrating host variability.

Repeat sampled checked-out application connections: mean 4.43/max14 at 100; mean6/max12 at 250. These sparse samples are NOT exact peaks; configured maximum is15. The short failed 250 phase has only two resource samples. Total PostgreSQL connections also include idle pooled and diagnostic connections; no high-resolution server-wide connection average was collected. Raw sampled pools, CPU, memory, thread and admission observations are retained in JSON rather than presented as exact utilization limits.

Readiness returned 200 after every phase. Deliberately stopping only azari-load-db caused a sanitized unavailable response; restarting the database restored readiness without a backend restart. The outage response was roughly 8 seconds in the first replay, so configured connect timeout is not a guarantee of subsecond readiness failure detection. No real database was stopped.

## 18. Maximum verified capacity

**100 simulated active API users for these short local phases**, approximately 73–78 requests/s after changes. This does not imply sustained production support, 100 simultaneous expensive posts, a browser test, or 10,000 concurrent users. 250 remains unsupported by the measured acceptance gate.

## 19. Remaining bottlenecks and limitations

- Admission saturation at 250; increased request/connection hold wall time under contention.
- No long-duration soak, independent load-generator host, production TLS/WAN, or large-single-owner history test.
- No precise CPU flamegraph or high-resolution PostgreSQL-wide connection series; cursor wall is not CPU attribution.
- Unbounded lists, dashboard fan-out and session-spanning ML inference remain candidates, not automatically authorized architectural changes.
- One unexplained transport failure, and considerable local run variability.
- Existing worktree contains substantial unrelated pending feature changes; whole-worktree diff is not solely Stage 10.

## 20. Recommended next experiments

Repeat on dedicated application/database/load-generator resources with long steady phases; profile CPU/scheduling at 150–250 users and collect high-frequency pool/pg_stat_activity observations. Add populated large-owner invoice/bill/history fixtures, then evaluate pagination and dashboard request deduplication as separate behavior-preserving work. Evaluate process scaling only alongside a shared rate-limiter design and explicit PostgreSQL connection/memory budget. Do not simply raise the pool.

## 21. Production readiness

PARTIAL PASS: correctness/regression and clean deployment checks pass, and measured improvements exist, but capacity beyond100 and sustained production operation are unverified. Diagnostic probe endpoints are test-only. Test smoke frontend is localhost:14175, backend localhost:18104 (container8000), database internal5432. Normal application port configuration was not changed. No secrets, production records, commits or pushes are included.

## 22. Exact Stage 10 files

Runtime/migrations: backend/app/services/accounting.py; backend/app/repositories/reporting.py; backend/app/services/reporting.py; backend/app/db/models/accounting.py; backend/alembic/versions/20260903_0011_owner_registration_role.py; backend/alembic/versions/20260910_0014_accounting_lookup_indexes.py.

Tests/fixtures: backend/tests/test_performance_queries.py; backend/tests/test_owner_role_migration.py; backend/scripts/verify_stage9_locking_postgres.py; backend/scripts/verify_stage9_phase_b_postgres.py.

Diagnostics: scripts/stage10_probe.py; scripts/stage10_profile.py; scripts/stage10_plans.py; scripts/stage10_load.py; scripts/stage10_migration_check.py; scripts/stage10_recovery.py; compose.stage10-verification.yaml.

Evidence: STAGE10_PROFILE_BEFORE.json; STAGE10_PROFILE_AFTER.json (intermediate); STAGE10_PROFILE_FINAL.json; STAGE10_PLANS_BEFORE.json; STAGE10_PLANS_AFTER.json; STAGE10_LOAD_BEFORE.json; STAGE10_LOAD_AFTER.json; STAGE10_LOAD_REPEAT.json; STAGE10_RECOVERY_RESULTS.json.

Documentation: this file; PROJECT_ANALYSIS.md; HOW_THE_PROJECT_WORKS.md; docs/ARCHITECTURE.md; docs/SETUP.md. Other modified/untracked files shown by git status predate Stage 10 and were preserved. Recommended eventual commit message: `Performance profiling and capacity improvements` (review and stage selectively).
