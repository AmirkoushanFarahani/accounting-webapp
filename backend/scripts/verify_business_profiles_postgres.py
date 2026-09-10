"""Verify revision 0012 on an explicitly isolated, populated PostgreSQL copy.

Set PROFILE_VERIFY_DATABASE to a pre-created copy named azari_profile_verify_*.
Never runs downgrade on the application's configured database.
"""

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
    database = os.environ["PROFILE_VERIFY_DATABASE"]
    if not database.startswith("azari_profile_verify_") or database == original.database:
        raise ValueError("An isolated verification database is required")
    settings.DATABASE_URL = original.set(database=database).render_as_string(hide_password=False)
    engine = create_engine(settings.DATABASE_URL)
    config = Config("/app/backend/alembic.ini")

    def snapshot() -> dict[str, tuple[int, str]]:
        result = {}
        with engine.connect() as connection:
            for table in inspect(engine).get_table_names():
                if table == "alembic_version":
                    continue
                quoted = engine.dialect.identifier_preparer.quote(table)
                rows = connection.execute(text(f"SELECT to_jsonb(t) FROM {quoted} t")).scalars()
                normalized = []
                for row in rows:
                    if table == "users":
                        row.pop("business_category", None)
                    normalized.append(json.dumps(row, sort_keys=True))
                digest = hashlib.sha256("\n".join(sorted(normalized)).encode()).hexdigest()
                result[table] = (len(normalized), digest)
        return result

    before = snapshot()
    assert all(before[table][0] > 0 for table in ["users", "invoices", "bills"])
    command.upgrade(config, "head")
    assert snapshot() == before, "Upgrade changed existing data"
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM users WHERE business_category != 'RETAIL'")
            )
            == 0
        )
    command.check(config)
    command.downgrade(config, "20260903_0011")
    assert snapshot() == before, "Downgrade changed existing data"
    command.upgrade(config, "head")
    assert snapshot() == before, "Re-upgrade changed existing data"
    command.check(config)
    print("PASS: populated PostgreSQL upgrade / downgrade / upgrade; no data loss; no schema drift")
    print(json.dumps({table: values[0] for table, values in before.items()}, sort_keys=True))
    engine.dispose()


if __name__ == "__main__":
    main()
