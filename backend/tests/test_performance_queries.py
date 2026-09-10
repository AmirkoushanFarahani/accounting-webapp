from datetime import date

from backend.app.db.database import SessionLocal, engine
from backend.app.db.models import Invoice, JournalEntry, Party, User
from backend.app.schemas.accounting import InvoiceCreate, InvoiceRead, JournalRead
from backend.app.services.accounting import AccountingService
from backend.app.services.reporting import ReportingService
from backend.tests.test_reporting import report_domain
from sqlalchemy import event


def test_customer_summary_batch_matches_individual_reports_without_n_plus_one():
    with SessionLocal() as session:
        values = report_domain(session)
        session.add_all(
            [
                Party(owner_id=values.actor.id, name=f"Empty {i}", is_customer=True)
                for i in range(20)
            ]
        )
        session.commit()
        service = ReportingService(session, values.actor.id)
        expected = [service._customer_summary(party) for party in service.repo.customers()]
        queries = []

        def capture(*args):
            queries.append(args[2])

        event.listen(engine, "before_cursor_execute", capture)
        try:
            actual = service.customers()
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert actual == expected
        assert len(queries) == 4


def test_invoice_and_journal_list_relationship_queries_are_bounded():
    with SessionLocal() as session:
        values = report_domain(session)
        service = AccountingService(session, values.actor)
        for i in range(8):
            service.create_invoice(
                InvoiceCreate(
                    invoice_number=f"PERF-{i}",
                    customer_id=values.party.id,
                    issue_date=date(2026, 1, 5),
                    due_date=date(2026, 1, 5),
                    items=[{"description": "Regression", "quantity": 1, "unit_price": 10}],
                )
            )
        owner_id = values.actor.id
    # New session ensures the identity map cannot hide lazy queries.
    with SessionLocal() as session:
        repo = AccountingService(session, session.get_one(User, owner_id))
        queries = []

        def capture(*args):
            queries.append(args[2])

        event.listen(engine, "before_cursor_execute", capture)
        try:
            invoices = [InvoiceRead.model_validate(item) for item in repo.list(Invoice)]
            assert len(invoices) >= 8
            assert len(queries) == 3
            queries.clear()
            journals = [JournalRead.model_validate(item) for item in repo.list(JournalEntry)]
            assert journals
            assert len(queries) == 2
        finally:
            event.remove(engine, "before_cursor_execute", capture)
