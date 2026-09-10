"""Verify expenses migration on a disposable populated database, never the app DB."""

import hashlib
import json
import os

from alembic.config import Config
from backend.app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from alembic import command


def main() -> None:
    settings = get_settings()
    original = make_url(settings.DATABASE_URL)
    database = os.environ["EXPENSE_VERIFY_DATABASE"]
    if not database.startswith("azari_expense_verify_") or database == original.database:
        raise ValueError("Use an explicitly isolated verification database")
    settings.DATABASE_URL = original.set(database=database).render_as_string(hide_password=False)
    engine = create_engine(settings.DATABASE_URL)
    config = Config("/app/backend/alembic.ini")

    def snapshot() -> dict[str, tuple[int, str]]:
        result = {}
        with engine.connect() as connection:
            for table in inspect(engine).get_table_names():
                if table in {"alembic_version", "expenses"}:
                    continue
                quoted = engine.dialect.identifier_preparer.quote(table)
                rows = connection.execute(text(f"SELECT to_jsonb(t) FROM {quoted} t")).scalars()
                normalized = sorted(json.dumps(row, sort_keys=True) for row in rows)
                result[table] = (
                    len(normalized),
                    hashlib.sha256("\n".join(normalized).encode()).hexdigest(),
                )
        return result

    before = snapshot()
    assert all(before[table][0] > 0 for table in ["users", "invoices", "bills"])
    command.upgrade(config, "head")
    assert snapshot() == before
    command.check(config)
    command.downgrade(config, "20260907_0012")
    assert snapshot() == before
    command.upgrade(config, "head")
    assert snapshot() == before
    command.check(config)
    print("PASS: PostgreSQL migration upgrade/downgrade/upgrade; existing data unchanged; no drift")
    print(json.dumps({table: value[0] for table, value in before.items()}, sort_keys=True))
    engine.dispose()


if __name__ == "__main__":
    main()
