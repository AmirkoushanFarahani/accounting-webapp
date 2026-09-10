"""Verify Phase B tax posting and concurrent allocation on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

from backend.app.db.bootstrap import seed_rbac
from backend.app.db.database import SessionLocal, engine
from backend.app.db.models import (
    Account,
    AccountCategory,
    FinancialPeriod,
    Invoice,
    JournalEntry,
    Party,
    Payment,
    Product,
    Role,
    User,
)
from backend.app.schemas.accounting import (
    AllocationCreate,
    InvoiceCreate,
    InvoiceIssue,
    InvoiceItemCreate,
    PaymentCreate,
    PaymentPost,
)
from backend.app.services.accounting import AccountingService
from sqlalchemy import select, text

EXPECTED_DATABASE = "azari_stage9_phase_b_test"


def post_payment(payment_id: UUID, actor_id: UUID, barrier: Barrier) -> str:
    with SessionLocal() as session:
        actor = session.get_one(User, actor_id)
        payment = session.get_one(Payment, payment_id)
        cash_id = session.scalar(select(Account.id).where(Account.posting_role == "CASH"))
        receivable_id = session.scalar(
            select(Account.id).where(Account.posting_role == "RECEIVABLE")
        )
        assert cash_id is not None and receivable_id is not None
        barrier.wait()
        try:
            AccountingService(session, actor).post_payment(
                payment.id,
                PaymentPost(
                    cash_account_id=cash_id,
                    receivable_account_id=receivable_id,
                ),
            )
        except ValueError:
            return "REJECTED"
        return "POSTED"


def main() -> None:
    with engine.connect() as connection:
        database = connection.scalar(text("select current_database()"))
        if database != EXPECTED_DATABASE:
            raise RuntimeError(f"Refusing Phase B verification against {database!r}")

    suffix = uuid4().hex[:8]
    with SessionLocal.begin() as session:
        seed_rbac(session)
    with SessionLocal() as session:
        admin_role = session.scalar(select(Role).where(Role.name == "ADMIN"))
        assert admin_role is not None
        actor = User(
            email=f"phase-b-{suffix}@example.com",
            password_hash="unused",
            first_name="Phase",
            last_name="B",
            roles=[admin_role],
        )
        session.add(actor)
        session.flush()
        assets = AccountCategory(owner_id=actor.id, name=f"Assets {suffix}", account_type="ASSET")
        revenues = AccountCategory(
            owner_id=actor.id, name=f"Revenue {suffix}", account_type="REVENUE"
        )
        liabilities = AccountCategory(
            owner_id=actor.id, name=f"Liabilities {suffix}", account_type="LIABILITY"
        )
        session.add_all([actor, assets, revenues, liabilities])
        session.flush()
        cash = Account(code=f"C-{suffix}", name="Cash", category=assets, posting_role="CASH")
        receivable = Account(
            code=f"AR-{suffix}",
            name="Receivable",
            category=assets,
            posting_role="RECEIVABLE",
        )
        revenue = Account(
            code=f"REV-{suffix}",
            name="Revenue",
            category=revenues,
            posting_role="REVENUE",
        )
        tax_liability = Account(
            code=f"TAX-{suffix}",
            name="Tax payable",
            category=liabilities,
            posting_role="TAX_LIABILITY",
        )
        period = FinancialPeriod(
            name=f"Phase B {suffix}",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        party = Party(name=f"Customer {suffix}", is_customer=True)
        product = Product(sku=f"PB-{suffix}", name="Service", unit_price=Decimal("100.00"))
        for item in (cash, receivable, revenue, tax_liability, period, party, product):
            item.owner_id = actor.id
        session.add_all([cash, receivable, revenue, tax_liability, period, party, product])
        session.commit()

        service = AccountingService(session, actor)
        invoice = service.create_invoice(
            InvoiceCreate(
                invoice_number=f"PB-{suffix}",
                customer_id=party.id,
                issue_date=date(2026, 8, 1),
                due_date=date(2026, 8, 31),
                items=[
                    InvoiceItemCreate(
                        product_id=product.id,
                        description="Taxed service",
                        quantity=Decimal("1"),
                        tax=Decimal("10.00"),
                    )
                ],
            )
        )
        issued = service.issue_invoice(
            invoice.id,
            InvoiceIssue(
                receivable_account_id=receivable.id,
                revenue_account_id=revenue.id,
                tax_liability_account_id=tax_liability.id,
            ),
        )
        assert issued.journal is not None
        credits = {line.account_id: line.credit for line in issued.journal.lines}
        assert credits[revenue.id] == Decimal("100.00")
        assert credits[tax_liability.id] == Decimal("10.00")

        payment_ids = []
        for number in (1, 2):
            payment = service.create_payment(
                PaymentCreate(
                    party_id=party.id,
                    payment_date=date(2026, 8, 2),
                    amount=Decimal("110.00"),
                    reference=f"PB-{suffix}-{number}",
                    method="bank",
                    allocations=[AllocationCreate(invoice_id=invoice.id, amount=Decimal("110.00"))],
                )
            )
            payment_ids.append(payment.id)
        actor_id = actor.id
        invoice_id = invoice.id

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(
            executor.map(
                lambda payment_id: post_payment(payment_id, actor_id, barrier),
                payment_ids,
            )
        )
    assert results == ["POSTED", "REJECTED"]

    with SessionLocal() as session:
        invoice = session.get_one(Invoice, invoice_id)
        posted_payments = session.scalars(
            select(Payment).where(Payment.id.in_(payment_ids), Payment.status == "POSTED")
        ).all()
        payment_journals = session.scalars(
            select(JournalEntry).where(JournalEntry.entry_number.like(f"PAY-PB-{suffix}-%"))
        ).all()
        assert invoice.amount_paid == Decimal("110.00")
        assert invoice.status == "PAID"
        assert len(posted_payments) == 1
        assert len(payment_journals) == 1

    print("Phase B PostgreSQL tax and concurrent allocation checks passed: POSTED, REJECTED")


if __name__ == "__main__":
    main()
