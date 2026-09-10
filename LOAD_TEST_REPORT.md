# Isolated load-test results

## Outcome

The short 100-virtual-user scenario passed. The 1,000-virtual-user scenario failed
with severe unresponsiveness. 10,000 virtual users were **not run** because the
predefined stop threshold was exceeded. This is not production capacity certification.

| Active virtual users | Requests | Successful | Failed | p95 client response time | Readiness afterward |
|---|---:|---:|---:|---:|---|
| 10, original run | 274 | 274 | 0 | 47 ms | HTTP 200 |
| 100, resumed run | 2,635 | 2,635 | 0 | 188 ms | HTTP 200 |
| 1,000, resumed run | 1,027 | 27 | 1,000 | 10.063 s, timeout-dominated | Timed out |
| 10,000 | Not run | — | — | — | — |

At 100 VUs, median was 47 ms, p99 266 ms, and maximum 406 ms. Completed request
rate including measurement/drain overhead was 75.69 requests/s. Peak simultaneous
in-flight requests was 29, not 100, because users pause between actions.
At 1,000 VUs, peak in-flight requests reached 1,000 and 97.37% timed out. The
reported 38.91 completed attempts/s includes failures and must not be described
as successful application throughput (only 27 attempts succeeded).

## Environment and workload

- Separate Docker network `azari-load-test`, separate PostgreSQL container and
  database `azari_load_test`; no copies of real customer/accounting data.
- Backend: existing app image, single Uvicorn process, capped at 2 CPUs and 1 GiB RAM.
- PostgreSQL: version 16 image, capped at 2 CPUs and 1 GiB RAM.
- Frontend: existing Nginx image, capped at 0.5 CPU and 128 MiB RAM.
- Docker host reported 16 CPUs and approximately 11.5 GiB memory. The Python HTTP
  generator shares that physical computer; hosting/network performance is not reproduced.
- 10,000 synthetic OWNER accounts; each starts with 5 customers, 3 products,
  3 invoices (1 issued, 2 draft), 1 balanced posted journal, 2 journal lines,
  2 accounts, 2 account categories and a financial period.
- Each scenario uses a five-second ramp, a nominal 30-second request-launch
  window, 0.8–1.2-second think time, one in-flight request per VU, ten-second HTTP
  timeout, then outstanding-request draining and readiness checking.
- Approximately 90% reads: dashboard, invoice list, customer list/history summaries,
  trial balance, expenses, current user and products. Approximately 10% creates
  draft invoices. Actual endpoint counts and resource samples are in
  `LOAD_TEST_RESULTS.json`.
- Synthetic signed JWTs represent already logged-in users. JWT validation, database
  user lookup and permission checks remain active. Login hashing is tested separately.
- Stop escalation for p95 >2 seconds, errors >1%, or failed readiness; active stages
  also stop launching work once >5% failures are observed after 50 requests.

This is an HTTP-level, closed-loop smoke/stress test, not 1,000 real browser tabs,
an arrival-rate benchmark, or a long stability/soak test. Large individual workspaces,
AI inference/training, invoice issuance, payment posting, and distributed logins
were not load tested. First-run data remains from the interrupted run, including
its draft writes. The resumed stages did not start from pristine data.

## Failure evidence and recovery

Both backend and database remained running. Neither had an OOM kill or spontaneous
restart. PostgreSQL showed 15 sessions idle in transaction, waiting on ClientRead.
The backend logged:

```text
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached,
connection timed out, timeout 30.00
```

Readiness was still unavailable at a check 107 seconds after the load-test result
was saved. Restarting **only the isolated backend** restored readiness to HTTP 200.
Sampled peak RAM at 1,000 VUs was approximately 23.08% of the backend's 1 GiB limit;
there was no evidence of memory exhaustion. CPU samples during the stall were low.

Connection-pool exhaustion is confirmed. The idle transactions and low CPU suggest
application worker/session contention rather than PostgreSQL doing expensive queries.
The precise scheduling/session-lifetime cause requires a separate investigation;
this test does not prove that simply enlarging the pool would solve it.

Database integrity check after the run: 10,000 users, 10,000 issued invoices,
20,470 draft invoices, zero unbalanced journals, and total journal debits and credits
both 1,000,000,000 rials. Timed-out writes can continue server-side, so successful
client responses alone should not be used to count persisted drafts.

## Other observations

- A separate burst of ten logins from the same IP returned five HTTP 200 and five
  HTTP 429. This matches the existing five-per-minute limiter, not a crash and not
  evidence of distributed-login capacity.
- 100 parallel requests for the frontend login HTML returned HTTP 200 in 0.17 s.
  JavaScript was not executed; this is not an end-to-end login test.
- An empty-database startup failed at migration 0011 because ADMIN had not been
  seeded. The isolated initializer used migration to 0010, role bootstrap, then
  migration to head. The normal application startup order remains unchanged and
  this fresh-install defect remains unresolved.

## Files and next step

Test-only files: `scripts/seed_load_test.py`, `scripts/run_load_test.py`,
`scripts/run_load_test.ps1`, `scripts/resume_load_test.py`, `LOAD_TEST_RESULTS.json`,
and this report. Ruff passed for the Python load scripts. No application logic,
production configuration, real users, or real accounting records were changed by
this load-test task. No commit/push performed.

Isolated test containers were stopped after inspection; synthetic data was retained.
The earlier initializer container is named `azari-load-initializer`. Resume refuses
to escalate past a previously failed stage. Diagnose connection/session handling
before another 1,000-user attempt, then repeat with fresh fixtures, longer runs,
and finally on the intended hosting environment with a separate load generator.
