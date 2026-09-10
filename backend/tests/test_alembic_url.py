"""Exercise the actual Alembic environment without opening any DB connection."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from alembic.config import Config
from backend.app.core import config as settings_module
from sqlalchemy.engine import make_url

from alembic import context


@pytest.mark.parametrize("offline", [False, True])
@pytest.mark.parametrize(
    ("url", "password"),
    [
        ("postgresql+psycopg://app:example@database.invalid:5432/postgres", "example"),
        (
            "postgresql+psycopg://app:p%40ss%25word%2F%3A@database.invalid:5432/postgres",
            "p@ss%word/:",
        ),
        (
            "postgresql+psycopg://app:example@database.invalid:5432/postgres"
            "?sslmode=verify-full&sslrootcert=%2Frun%2Fcerts%2Froot.crt",
            "example",
        ),
        ("postgresql+psycopg://app:percent%word@database.invalid/postgres", "percent%word"),
    ],
)
def test_alembic_preserves_database_url(monkeypatch, offline, url, password):
    config = Config()
    configure = MagicMock()
    engine_options = {}

    def engine_from_config(options, **kwargs):
        engine_options.update(options)
        assert kwargs["poolclass"] is sqlalchemy.pool.NullPool
        return MagicMock()  # connect() is a mock: no network or database operations.

    monkeypatch.setattr(settings_module, "get_settings", lambda: SimpleNamespace(DATABASE_URL=url))
    monkeypatch.setattr(context, "config", config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: offline)
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", MagicMock())
    run_migrations = MagicMock()
    monkeypatch.setattr(context, "run_migrations", run_migrations)
    monkeypatch.setattr(sqlalchemy, "engine_from_config", engine_from_config)
    runpy.run_path(str(Path(__file__).parents[1] / "alembic" / "env.py"))

    received = configure.call_args.kwargs["url"] if offline else engine_options["sqlalchemy.url"]
    assert received == url
    assert config.get_main_option("sqlalchemy.url") == url
    parsed = make_url(received)
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.password == password
    assert parsed.query == make_url(url).query
    # Construct the real driver arguments, but never connect.
    engine = sqlalchemy.create_engine(parsed)
    try:
        _, arguments = engine.dialect.create_connect_args(parsed)
        assert engine.dialect.driver == "psycopg"
        assert arguments["password"] == password
        if "sslmode" in parsed.query:
            assert arguments["sslmode"] == "verify-full"
            assert arguments["sslrootcert"] == "/run/certs/root.crt"
    finally:
        engine.dispose()
    run_migrations.assert_called_once_with()
