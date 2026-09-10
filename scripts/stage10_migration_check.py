"""Index upgrade/downgrade integrity check, isolated load database only."""

import json
import subprocess

from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.db import models  # noqa: F401
from backend.app.db.base import Base
from backend.app.db.database import engine

assert get_settings().DATABASE_URL.endswith("/azari_load_test")


def snapshot():
    with engine.connect() as conn:
        return {
            table: list(conn.execute(text(
                f'SELECT count(*), md5(string_agg(row_to_json(t)::text, '\
                f"'' ORDER BY row_to_json(t)::text)) FROM \"{table}\" t"
            )).one())
            for table in Base.metadata.tables
        }


before = snapshot()
for revision, action in [("20260909_0013", "downgrade"), ("head", "upgrade")]:
    subprocess.run(["alembic", "-c", "/app/backend/alembic.ini", action, revision], check=True)
    assert snapshot() == before, "Index migration changed table data"
subprocess.run(["alembic", "-c", "/app/backend/alembic.ini", "check"], check=True)
print(json.dumps({"unchanged_tables": len(before), "upgrade_downgrade_upgrade": "PASS"}))
