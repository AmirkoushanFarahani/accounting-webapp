import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Annotated

import anyio
import pytest
from backend.app.core.config import get_settings
from backend.app.db import database
from backend.app.main import create_app
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request


def test_admission_sheds_load_without_holding_workers_and_recovers(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pool.db'}",
        pool_size=1,
        max_overflow=0,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    settings = get_settings().model_copy(
        update={
            "DB_POOL_SIZE": 1,
            "DB_MAX_OVERFLOW": 0,
            "DB_MAX_CONCURRENT_SESSIONS": 1,
            "DB_ADMISSION_TIMEOUT_SECONDS": 0.1,
        }
    )
    app = create_app(settings)
    entered = threading.Event()
    release = threading.Event()
    counters = {"out": 0, "in": 0}
    event.listen(engine, "checkout", lambda *args: counters.update(out=counters["out"] + 1))
    event.listen(engine, "checkin", lambda *args: counters.update({"in": counters["in"] + 1}))

    @app.get("/hold")
    def hold(session: Annotated[Session, Depends(database.get_db)]):
        session.execute(text("SELECT 1"))
        entered.set()
        assert release.wait(5)
        return {"ok": True}

    @app.get("/raises")
    def raises(session: Annotated[Session, Depends(database.get_db)]):
        session.execute(text("SELECT 1"))
        raise RuntimeError("test failure")

    with (
        TestClient(app, raise_server_exceptions=False) as client,
        ThreadPoolExecutor(12) as workers,
    ):
        request = workers.submit(client.get, "/hold")
        assert entered.wait(2)
        try:
            responses = list(workers.map(lambda _: client.get("/api/v1/ready"), range(10)))
            assert all(response.status_code == 503 for response in responses)
            assert all(response.headers["retry-after"] == "1" for response in responses)
            assert client.get("/api/v1/health").status_code == 200
        finally:
            release.set()
        assert request.result(timeout=3).status_code == 200
        assert engine.pool.checkedout() == 0
        assert client.get("/raises").status_code == 500
        assert engine.pool.checkedout() == 0
        assert client.get("/api/v1/ready").status_code == 200
        assert counters["in"] == counters["out"]
        assert app.state.db_limiter.borrowed_tokens == 0
    engine.dispose()


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("private SQL", {}, Exception("secret host")),
        PoolTimeoutError("private pool detail"),
    ],
)
def test_database_failures_are_sanitized_503_and_not_false_readiness(error, monkeypatch):
    class BrokenSession:
        closed = False

        def execute(self, statement):
            raise error

        def close(self):
            self.closed = True

    session = BrokenSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database temporarily unavailable"}
        assert response.headers["retry-after"] == "1"
        assert session.closed
        assert app.state.db_limiter.borrowed_tokens == 0
        assert client.get("/api/v1/health").status_code == 200


def test_postgres_pool_limits_are_explicit_and_bounded():
    engine = database.create_database_engine("postgresql+psycopg://test:unused@localhost/test")
    assert engine.pool.size() == 5
    assert engine.pool.timeout() == 2
    assert engine.pool._max_overflow == 10
    engine.dispose()


def test_cancelled_request_closes_session_off_loop_and_releases_admission(monkeypatch):
    closed_threads = []

    class FakeSession:
        def close(self):
            closed_threads.append(threading.get_ident())

    monkeypatch.setattr(database, "SessionLocal", FakeSession)

    async def scenario():
        limiter = anyio.CapacityLimiter(1)
        state = SimpleNamespace(db_limiter=limiter, settings=get_settings())
        request = Request({"type": "http", "app": SimpleNamespace(state=state)})
        entered = anyio.Event()

        async def work():
            generator = database.get_db(request)
            try:
                await anext(generator)
                entered.set()
                await anyio.sleep_forever()
            finally:
                await generator.aclose()

        async with anyio.create_task_group() as group:
            group.start_soon(work)
            await entered.wait()
            group.cancel_scope.cancel()
        assert limiter.borrowed_tokens == 0
        assert len(closed_threads) == 1
        assert closed_threads[0] != threading.get_ident()

    anyio.run(scenario)
