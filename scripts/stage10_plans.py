"""Capture actual ORM read-query plans on the isolated fixture database."""

import json
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import event, select

from backend.app.core.config import get_settings
from backend.app.db.database import SessionLocal, engine
from backend.app.db.models import Invoice, JournalEntry
from backend.app.schemas.accounting import InvoiceRead, JournalRead
from backend.app.services.reporting import ReportingService

assert get_settings().DATABASE_URL.endswith("/azari_load_test")
queries = {}


def capture(conn, cursor, statement, parameters, context, many):
    if statement.lstrip().startswith("SELECT"):
        queries.setdefault(statement, parameters)


event.listen(engine, "before_cursor_execute", capture)
owner = uuid5(NAMESPACE_URL, "azari-isolated-load/user-9998")
with SessionLocal() as session:
    service = ReportingService(session, owner)
    service.dashboard(as_of=date(2026, 9, 10))
    service.customers()
    for invoice in session.scalars(select(Invoice).where(Invoice.owner_id == owner)):
        InvoiceRead.model_validate(invoice)
    for journal in session.scalars(
        select(JournalEntry).where(JournalEntry.owner_id == owner)
    ):
        JournalRead.model_validate(journal)
event.remove(engine, "before_cursor_execute", capture)
plans = []
with engine.connect() as conn:
    for sql, params in queries.items():
        plan = conn.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
        ).scalar()
        plans.append({"sql": sql, "plan": plan})
print(json.dumps(plans, default=str))
