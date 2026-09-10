"""Private test-only queue/CPU/PG instrumentation; never imported by normal startup."""

import asyncio
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import psycopg
import stage10_probe as probe
from fastapi import Request

app = probe.app
samples = deque(maxlen=20000)
pg_samples = deque(maxlen=20000)
original_lifespan = app.router.lifespan_context
original_run = anyio.to_thread.run_sync


async def run_sync(func, *args, **kwargs):
    queued = time.perf_counter()

    def measured():
        start = time.perf_counter()
        cpu = time.thread_time()
        probe.add("worker_wait_seconds", start - queued)
        probe.add("worker_calls", 1)
        try:
            return func(*args)
        finally:
            probe.add("worker_seconds", time.perf_counter() - start)
            probe.add("worker_cpu_seconds", time.thread_time() - cpu)

    return await original_run(measured, **kwargs)


anyio.to_thread.run_sync = run_sync


async def session(request: Request):
    metrics = probe.current.get()
    if metrics is not None:
        metrics["arrival"] = request.scope["stage11_arrival"]
        metrics["method"] = request.method
        metrics["dependency_enter"] = time.perf_counter()
    generator = probe.profiled_db(request)
    try:
        value = await anext(generator)
        if metrics is not None:
            metrics["admitted"] = time.perf_counter()
        yield value
    finally:
        await generator.aclose()
        if metrics is not None:
            metrics["cleanup_complete"] = time.perf_counter()


app.dependency_overrides[probe.original_db] = session


class Arrival:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope["stage11_arrival"] = time.perf_counter()
        await self.app(scope, receive, send)


app.add_middleware(Arrival)


def pg_monitor(stop):
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
    while not stop.is_set():
        try:
            with psycopg.connect(url, autocommit=True, application_name="stage11-observer") as conn:
                while not stop.is_set():
                    start = time.perf_counter()
                    rows = conn.execute("""
                        SELECT state, wait_event_type, wait_event, count(*),
                          max(extract(epoch from clock_timestamp()-query_start)),
                          max(extract(epoch from clock_timestamp()-xact_start)),
                          sum(CASE WHEN cardinality(pg_blocking_pids(pid)) > 0 THEN 1 ELSE 0 END)
                        FROM pg_stat_activity
                        WHERE datname=current_database() AND pid<>pg_backend_pid()
                        GROUP BY state,wait_event_type,wait_event
                    """).fetchall()
                    pg_samples.append({"time": start, "groups": [
                        [r[0], r[1], r[2], r[3], float(r[4] or 0), float(r[5] or 0), r[6]]
                        for r in rows], "sample_seconds": time.perf_counter()-start})
                    stop.wait(0.2)
        except psycopg.Error:
            pg_samples.append({"time": time.perf_counter(), "unavailable": True})
            stop.wait(1)


async def monitor():
    while True:
        start = time.perf_counter()
        threads = anyio.to_thread.current_default_thread_limiter().statistics()
        gate = app.state.db_limiter.statistics()
        pool = probe.database.engine.pool
        samples.append({
            "time": start, "threads": threads.borrowed_tokens,
            "worker_queue": threads.tasks_waiting, "thread_capacity": threads.total_tokens,
            "admitted": gate.borrowed_tokens, "admission_queue": gate.tasks_waiting,
            "admission_capacity": gate.total_tokens, "checkedout": pool.checkedout(),
            "available": pool.checkedin(), "overflow": pool.overflow(),
            "process_cpu": time.process_time(),
            "cpu_stat": Path("/sys/fs/cgroup/cpu.stat").read_text(),
            "memory": int(Path("/sys/fs/cgroup/memory.current").read_text()),
        })
        await asyncio.sleep(0.1)
        samples[-1]["loop_lag"] = max(0, time.perf_counter()-start-0.1)


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        stop = threading.Event()
        thread = threading.Thread(target=pg_monitor, args=(stop,), daemon=True)
        thread.start()
        task = asyncio.create_task(monitor())
        try:
            yield
        finally:
            stop.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app.router.lifespan_context = lifespan


@app.post("/__stage11/reset", include_in_schema=False)
async def reset(request: Request):
    data = await request.json()
    assert app.state.db_limiter.borrowed_tokens == 0
    tokens = int(data.get("tokens", 40))
    admission = int(data.get("admission", 15))
    assert tokens in (20, 40, 80) and admission in (10, 15) and tokens > admission
    anyio.to_thread.current_default_thread_limiter().total_tokens = tokens
    app.state.db_limiter.total_tokens = admission
    samples.clear()
    pg_samples.clear()
    probe.records.clear()
    return {"tokens": tokens, "admission": admission}


@app.get("/__stage11", include_in_schema=False)
async def snapshot():
    return {"samples": list(samples), "postgres": list(pg_samples), "requests": list(probe.records)}
