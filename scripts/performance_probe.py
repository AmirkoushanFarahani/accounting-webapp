"""Isolated-only diagnostics. Never imported by the application entrypoint."""

import asyncio
import sys
import threading
import time
from collections import Counter

import anyio.to_thread
from sqlalchemy import event

from backend.app.core.config import get_settings
from backend.app.db.database import engine
from backend.app.main import app

assert get_settings().DATABASE_URL.endswith("/azari_load_test")
counts = Counter()
held = {}
mutex = threading.Lock()


@event.listens_for(engine, "checkout")
def checkout(dbapi, record, proxy):
    with mutex:
        counts["checkout"] += 1
        held[id(record)] = time.monotonic()


@event.listens_for(engine, "checkin")
def checkin(dbapi, record):
    with mutex:
        counts["checkin"] += 1
        held.pop(id(record), None)


@event.listens_for(engine, "before_cursor_execute")
def before(conn, cursor, statement, parameters, context, many):
    context._probe_start = time.monotonic()


@event.listens_for(engine, "after_cursor_execute")
def after(conn, cursor, statement, parameters, context, many):
    with mutex:
        counts["queries"] += 1
        counts["query_seconds"] += time.monotonic() - context._probe_start


@app.get("/__probe", include_in_schema=False)
async def probe():
    limiter = anyio.to_thread.current_default_thread_limiter()
    thread_stacks = Counter()
    for frame in sys._current_frames().values():
        names = []
        while frame:
            names.append(frame.f_code.co_name)
            frame = frame.f_back
        thread_stacks[
            "/".join(reversed(names[-20:] if len(names) > 20 else names))
        ] += 1
    waits = Counter()
    for task in asyncio.all_tasks():
        obj = task.get_coro()
        names = []
        for _ in range(50):
            code = getattr(obj, "cr_code", None) or getattr(obj, "gi_code", None)
            if code:
                names.append(code.co_name)
            obj = getattr(obj, "cr_await", None) or getattr(obj, "gi_yieldfrom", None)
            if obj is None:
                break
        waits["/".join(names)] += 1
    with mutex:
        result = dict(counts)
        result["max_hold_seconds"] = max(
            (time.monotonic() - start for start in held.values()), default=0
        )
    result["admitted_sessions"] = getattr(
        getattr(app.state, "db_limiter", None), "borrowed_tokens", None
    )
    return {
        **result,
        "pool": engine.pool.status(),
        "borrowed_threads": limiter.borrowed_tokens,
        "thread_limit": limiter.total_tokens,
        "threads": dict(thread_stacks),
        "await_chains": dict(waits),
    }
