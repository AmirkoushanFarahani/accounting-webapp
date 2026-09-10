from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import (
    Account,
    AccountCategory,
    Bill,
    BillPayment,
    BillPaymentAllocation,
    Expense,
    Invoice,
    JournalEntry,
    JournalLine,
    Party,
    Payment,
    PaymentAllocation,
)


class ReportingRepository:
    def paid_expenses(self, start_date: date | None, end_date: date | None) -> list[Expense]:
        query = select(Expense).where(Expense.owner_id == self.owner_id)
        if start_date:
            query = query.where(Expense.payment_date >= start_date)
        if end_date:
            query = query.where(Expense.payment_date <= end_date)
        return list(self.session.scalars(query))

    def __init__(self, session: Session, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def account_activity(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        account_types: set[str] | None = None,
    ) -> list[tuple[Account, str, Decimal, Decimal]]:
        statement = (
            select(
                Account,
                AccountCategory.account_type,
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(Account.category)
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
            .where(
                Account.owner_id == self.owner_id,
                JournalEntry.owner_id == self.owner_id,
                JournalEntry.status == "POSTED",
            )
            .group_by(Account.id, AccountCategory.account_type)
            .order_by(Account.code)
        )
        if start_date is not None:
            statement = statement.where(JournalEntry.entry_date >= start_date)
        if end_date is not None:
            statement = statement.where(JournalEntry.entry_date <= end_date)
        if account_types:
            statement = statement.where(AccountCategory.account_type.in_(account_types))
        return [
            (row[0], row[1], Decimal(row[2]), Decimal(row[3]))
            for row in self.session.execute(statement)
        ]

    def receivables_as_of(
        self, *, as_of: date, customer_id: UUID | None = None
    ) -> list[tuple[Invoice, Decimal]]:
        paid = func.coalesce(
            func.sum(
                case(
                    (
                        (Payment.status == "POSTED") & (Payment.payment_date <= as_of),
                        PaymentAllocation.amount,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        statement = (
            select(Invoice, paid.label("paid_as_of"))
            .outerjoin(PaymentAllocation, PaymentAllocation.invoice_id == Invoice.id)
            .outerjoin(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(
                Invoice.owner_id == self.owner_id,
                Invoice.issue_date <= as_of,
                Invoice.status.in_(("ISSUED", "PARTIALLY_PAID", "PAID")),
            )
            .group_by(Invoice.id)
            .having(Invoice.total > paid)
            .order_by(Invoice.due_date, Invoice.invoice_number)
        )
        if customer_id is not None:
            statement = statement.where(Invoice.customer_id == customer_id)
        return [(row[0], Decimal(row[1])) for row in self.session.execute(statement)]

    def payables_as_of(self, *, as_of: date) -> list[tuple[Bill, Decimal]]:
        paid = func.coalesce(
            func.sum(
                case(
                    (
                        (BillPayment.status == "POSTED") & (BillPayment.payment_date <= as_of),
                        BillPaymentAllocation.amount,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        statement = (
            select(Bill, paid.label("paid_as_of"))
            .outerjoin(BillPaymentAllocation, BillPaymentAllocation.bill_id == Bill.id)
            .outerjoin(BillPayment, BillPayment.id == BillPaymentAllocation.bill_payment_id)
            .where(
                Bill.owner_id == self.owner_id,
                Bill.issue_date <= as_of,
                Bill.status.in_(("ISSUED", "PARTIALLY_PAID", "PAID")),
            )
            .group_by(Bill.id)
            .having(Bill.total > paid)
            .order_by(Bill.due_date, Bill.bill_number)
        )
        return [(row[0], Decimal(row[1])) for row in self.session.execute(statement)]

    def party(self, party_id: UUID) -> Party | None:
        return self.session.scalar(
            select(Party).where(Party.id == party_id, Party.owner_id == self.owner_id)
        )

    def customers(self) -> list[Party]:
        return list(
            self.session.scalars(
                select(Party)
                .where(
                    Party.owner_id == self.owner_id,
                    Party.is_customer.is_(True),
                )
                .order_by(Party.name, Party.id)
            )
        )

    def customer_accounting_invoices(self, party_id: UUID) -> list[Invoice]:
        return list(
            self.session.scalars(
                select(Invoice)
                .where(
                    Invoice.owner_id == self.owner_id,
                    Invoice.customer_id == party_id,
                    Invoice.status.in_(("ISSUED", "PARTIALLY_PAID", "PAID")),
                )
                .order_by(Invoice.issue_date, Invoice.id)
            )
        )

    def party_invoices(
        self, party_id: UUID, start_date: date | None, end_date: date | None
    ) -> list[Invoice]:
        statement = select(Invoice).options(
            selectinload(Invoice.items), selectinload(Invoice.checks)
        ).where(
            Invoice.owner_id == self.owner_id,
            Invoice.customer_id == party_id,
        )
        if start_date is not None:
            statement = statement.where(Invoice.issue_date >= start_date)
        if end_date is not None:
            statement = statement.where(Invoice.issue_date <= end_date)
        return list(self.session.scalars(statement))

    def customer_totals(self) -> dict[UUID, tuple[int, Decimal, Decimal, Decimal, Decimal]]:
        """Aggregate each source independently so joins cannot multiply financial totals."""
        invoices = {
            row[0]: (int(row[1]), Decimal(row[2]), Decimal(row[3]))
            for row in self.session.execute(
                select(
                    Invoice.customer_id, func.count(Invoice.id), func.sum(Invoice.total),
                    func.sum(Invoice.total - Invoice.amount_paid),
                ).where(
                    Invoice.owner_id == self.owner_id,
                    Invoice.status.in_(("ISSUED", "PARTIALLY_PAID", "PAID")),
                ).group_by(Invoice.customer_id)
            )
        }
        payments = {
            row[0]: Decimal(row[1])
            for row in self.session.execute(
                select(Payment.party_id, func.sum(Payment.amount)).where(
                    Payment.owner_id == self.owner_id, Payment.status == "POSTED",
                ).group_by(Payment.party_id)
            )
        }
        credits = {
            row[0]: Decimal(row[1])
            for row in self.session.execute(
                select(Payment.party_id, func.sum(JournalLine.credit - JournalLine.debit))
                .join(JournalEntry, JournalEntry.id == Payment.journal_id)
                .join(JournalLine, JournalLine.journal_id == JournalEntry.id)
                .join(Account, Account.id == JournalLine.account_id)
                .where(
                    Payment.owner_id == self.owner_id, JournalEntry.owner_id == self.owner_id,
                    Account.owner_id == self.owner_id, Payment.status == "POSTED",
                    JournalEntry.status == "POSTED", Account.posting_role == "CUSTOMER_CREDIT",
                ).group_by(Payment.party_id)
            )
        }
        zero = Decimal(0)
        return {
            party_id: (*invoices.get(party_id, (0, zero, zero)),
                       payments.get(party_id, zero), credits.get(party_id, zero))
            for party_id in invoices.keys() | payments.keys() | credits.keys()
        }

    def party_payments(
        self, party_id: UUID, start_date: date | None, end_date: date | None
    ) -> list[Payment]:
        statement = select(Payment).where(
            Payment.owner_id == self.owner_id,
            Payment.party_id == party_id,
        )
        if start_date is not None:
            statement = statement.where(Payment.payment_date >= start_date)
        if end_date is not None:
            statement = statement.where(Payment.payment_date <= end_date)
        return list(self.session.scalars(statement))

    def customer_credit_balance(self, party_id: UUID) -> Decimal:
        balance = self.session.scalar(
            select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0))
            .join(Account, Account.id == JournalLine.account_id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
            .join(Payment, Payment.journal_id == JournalEntry.id)
            .where(
                Payment.party_id == party_id,
                Payment.owner_id == self.owner_id,
                JournalEntry.owner_id == self.owner_id,
                Account.owner_id == self.owner_id,
                Payment.status == "POSTED",
                JournalEntry.status == "POSTED",
                Account.posting_role == "CUSTOMER_CREDIT",
            )
        )
        return Decimal(balance or 0)

    def posted_payments(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> list[Payment]:
        statement = select(Payment).where(
            Payment.owner_id == self.owner_id,
            Payment.status == "POSTED",
        )
        if start_date is not None:
            statement = statement.where(Payment.payment_date >= start_date)
        if end_date is not None:
            statement = statement.where(Payment.payment_date <= end_date)
        return list(self.session.scalars(statement))

    def posted_bill_payments(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> list[BillPayment]:
        statement = select(BillPayment).where(
            BillPayment.owner_id == self.owner_id,
            BillPayment.status == "POSTED",
        )
        if start_date is not None:
            statement = statement.where(BillPayment.payment_date >= start_date)
        if end_date is not None:
            statement = statement.where(BillPayment.payment_date <= end_date)
        return list(self.session.scalars(statement))
