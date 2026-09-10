from collections.abc import AsyncGenerator

import anyio
from fastapi import HTTPException, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings


def create_database_engine(database_url: str) -> Engine:
    """Create an engine with safe defaults and deterministic in-memory test behavior."""
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("postgresql"):
        settings = get_settings()
        options.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
            connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS},
        )
    if database_url.startswith("sqlite") and ":memory:" in database_url:
        options.update(
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(database_url, **options)


engine = create_database_engine(get_settings().DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db(request: Request) -> AsyncGenerator[Session, None]:
    """Queue without occupying sync workers; hold admission through serialization."""
    limiter: anyio.CapacityLimiter = request.app.state.db_limiter
    try:
        with anyio.fail_after(request.app.state.settings.DB_ADMISSION_TIMEOUT_SECONDS):
            await limiter.acquire()
    except TimeoutError as exc:
        raise HTTPException(
            503, "Database capacity temporarily unavailable", headers={"Retry-After": "1"}
        ) from exc
    try:
        session = SessionLocal()
        try:
            yield session
        finally:
            # Rollback/close can do I/O; never block the event loop or abandon cleanup.
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(session.close)
    finally:
        limiter.release()
