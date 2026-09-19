from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from backend.app.db.database import SessionLocal, engine
from backend.app.db.models import (
    Account,
    AccountCategory,
    AuditEvent,
    Bill,
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
    AccountCreate,
    AccountUpdate,
    BillCreate,
    BillIssue,
    BillPaymentCreate,
    BillPaymentPost,
    CategoryCreate,
    InvoiceCheckCreate,
    InvoiceCheckUpdate,
    InvoiceCreate,
    InvoiceIssue,
    JournalCreate,
    PartyCreate,
    PartyUpdate,
    PaymentCreate,
    PaymentPost,
    PeriodCreate,
    ProductCreate,
    ProductUpdate,
)
from backend.app.schemas.expense import ExpenseCreate
from backend.app.services.accounting import (
    AccountingError,
    AccountingService,
    ConflictError,
    NotFoundError,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.orm import Session


@dataclass
class Domain:
    admin: User
    cash: Account
    receivable: Account
    revenue: Account
    tax_liability: Account
    customer_credit: Account
    payable: Account
    expense: Account
    period: FinancialPeriod
    customer: Party
    supplier: Party
    product: Product


def test_check_payment_schemas_require_a_due_date() -> None:
    party_id = uuid4()
    invoice_id = uuid4()
    with pytest.raises(ValidationError):
        PaymentCreate(
            party_id=party_id,
            payment_date=date(2030, 1, 1),
            amount=Decimal("100"),
            reference="CHECK-RECEIPT",
            method="چک",
            allocations=[{"invoice_id": invoice_id, "amount": "100"}],
        )
    payment = PaymentCreate(
        party_id=party_id,
        payment_date=date(2030, 1, 1),
        amount=Decimal("100"),
        reference="CHECK-RECEIPT",
        method="چک",
        check_due_date=date(2030, 2, 1),
        allocations=[{"invoice_id": invoice_id, "amount": "100"}],
    )
    assert payment.check_due_date == date(2030, 2, 1)

    with pytest.raises(ValidationError):
        ExpenseCreate(
            name="Check expense",
            amount=Decimal("100"),
            payment_date=date(2030, 1, 1),
            method="CHECK",
            expense_account_id=uuid4(),
            cash_account_id=uuid4(),
        )


def domain(session: Session) -> tuple[AccountingService, Domain]:
    admin = User(
        email="accounting@example.com",
        password_hash="not-used",
        first_name="Stage",
        last_name="Three",
        roles=[session.scalar(select(Role).where(Role.name == "ADMIN"))],
    )
    session.add(admin)
    session.flush()
    asset = AccountCategory(owner_id=admin.id, name="Assets", account_type="ASSET")
    revenue_category = AccountCategory(
        owner_id=admin.id, name="Revenue", account_type="REVENUE"
    )
    liability = AccountCategory(
        owner_id=admin.id, name="Liabilities", account_type="LIABILITY"
    )
    expense_category = AccountCategory(
        owner_id=admin.id, name="Purchase expenses", account_type="EXPENSE"
    )
    session.add_all([asset, revenue_category, liability, expense_category])
    cash = Account(
        owner_id=admin.id,
        code="1000",
        name="Cash",
        category=asset,
        posting_role="CASH",
    )
    receivable = Account(
        owner_id=admin.id,
        code="1100", name="Receivable", category=asset, posting_role="RECEIVABLE"
    )
    revenue = Account(
        owner_id=admin.id,
        code="4000", name="Sales", category=revenue_category, posting_role="REVENUE"
    )
    tax_liability = Account(
        owner_id=admin.id,
        code="2100", name="Tax payable", category=liability, posting_role="TAX_LIABILITY"
    )
    customer_credit = Account(
        owner_id=admin.id,
        code="2200", name="Customer credit", category=liability, posting_role="CUSTOMER_CREDIT"
    )
    payable = Account(
        owner_id=admin.id,
        code="2000",
        name="Payable",
        category=liability,
        posting_role="PAYABLE",
    )
    expense = Account(
        owner_id=admin.id,
        code="5050", name="Purchases", category=expense_category, posting_role="EXPENSE"
    )
    period = FinancialPeriod(
        owner_id=admin.id,
        name="2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    customer = Party(owner_id=admin.id, name="Customer", is_customer=True)
    supplier = Party(owner_id=admin.id, name="Supplier", is_supplier=True)
    product = Product(
        owner_id=admin.id,
        sku="P-1",
        name="Service",
        unit="hour",
        unit_price=Decimal("100.00"),
    )
    session.add_all(
        [
            cash,
            receivable,
            revenue,
            tax_liability,
            customer_credit,
            payable,
            expense,
            period,
            customer,
            supplier,
            product,
        ]
    )
    session.commit()
    return AccountingService(session, admin), Domain(
        admin,
        cash,
        receivable,
        revenue,
        tax_liability,
        customer_credit,
        payable,
        expense,
        period,
        customer,
        supplier,
        product,
    )


def journal_data(
    values: Domain,
    *,
    debit: Decimal = Decimal("100"),
    credit: Decimal = Decimal("100"),
    one_line: bool = False,
) -> JournalCreate:
    lines = [{"account_id": values.cash.id, "debit": debit, "credit": 0}]
    if not one_line:
        lines.append({"account_id": values.revenue.id, "debit": 0, "credit": credit})
    return JournalCreate(
        entry_number="J-1",
        entry_date=date(2026, 2, 1),
        description="Test journal",
        period_id=values.period.id,
        lines=lines,
    )


def invoice_data(values: Domain, number: str = "I-1") -> InvoiceCreate:
    return InvoiceCreate(
        invoice_number=number,
        customer_id=values.customer.id,
        issue_date=date(2026, 2, 1),
        due_date=date(2026, 3, 1),
        items=[
            {
                "product_id": values.product.id,
                "description": "Consulting",
                "quantity": Decimal("2.5"),
                "tax": Decimal("25"),
            }
        ],
    )


def test_balanced_posting_and_reversal_preserve_original() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        journal = service.create_journal(journal_data(values))
        assert service.post_journal(journal.id).status == "POSTED"
        reversal = service.reverse_journal(journal.id)
        assert reversal.status == "POSTED"
        assert reversal.reversal_of_id == journal.id
        assert sum(line.debit for line in reversal.lines) == sum(
            line.credit for line in reversal.lines
        )
        assert journal.status == "POSTED"
        assert journal.lines[0].debit == Decimal("100")


def test_reversal_cannot_be_repeated_or_reversed() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        original = service.create_journal(journal_data(values))
        service.post_journal(original.id)
        reversal = service.reverse_journal(original.id)

        with pytest.raises(ConflictError, match="already been reversed"):
            service.reverse_journal(original.id)
        with pytest.raises(ConflictError, match="cannot be reversed"):
            service.reverse_journal(reversal.id)

        assert len(session.scalars(select(JournalEntry)).all()) == 2


def test_reversal_cannot_post_into_a_closed_period() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        original = service.create_journal(journal_data(values))
        service.post_journal(original.id)
        values.period.status = "CLOSED"
        session.commit()

        with pytest.raises(ConflictError, match="closed period"):
            service.reverse_journal(original.id)

        assert session.scalar(
            select(JournalEntry).where(JournalEntry.reversal_of_id == original.id)
        ) is None
        assert original.status == "POSTED"


@pytest.mark.parametrize(
    ("debit", "credit", "one_line", "message"),
    [
        (Decimal("100"), Decimal("50"), False, "balance"),
        (Decimal("100"), Decimal("100"), True, "at least two"),
    ],
)
def test_invalid_journals_roll_back(
    debit: Decimal, credit: Decimal, one_line: bool, message: str
) -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        journal = service.create_journal(
            journal_data(values, debit=debit, credit=credit, one_line=one_line)
        )
        with pytest.raises(AccountingError, match=message):
            service.post_journal(journal.id)
        persisted = session.get(JournalEntry, journal.id)
        assert persisted is not None and persisted.status == "DRAFT"


@pytest.mark.parametrize(
    ("debit", "credit"),
    [(Decimal("0"), Decimal("0")), (Decimal("10"), Decimal("10")), (Decimal("-1"), Decimal("0"))],
)
def test_line_amount_rules(debit: Decimal, credit: Decimal) -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        with pytest.raises(ValueError):
            data = JournalCreate(
                entry_number="INVALID",
                entry_date=date(2026, 2, 1),
                description="Invalid line",
                period_id=values.period.id,
                lines=[{"account_id": values.cash.id, "debit": debit, "credit": credit}],
            )
            service.create_journal(data)


def test_inactive_account_and_closed_period_reject_posting() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        journal = service.create_journal(journal_data(values))
        values.cash.is_active = False
        session.commit()
        with pytest.raises(ConflictError, match="Inactive"):
            service.post_journal(journal.id)
        values.cash.is_active = True
        values.period.status = "CLOSED"
        session.commit()
        with pytest.raises(ConflictError, match="closed"):
            service.post_journal(journal.id)


def test_posted_journal_has_no_mutation_or_delete_api(client: TestClient) -> None:
    assert client.patch("/api/v1/journals/00000000-0000-0000-0000-000000000000").status_code == 405
    assert client.delete("/api/v1/journals/00000000-0000-0000-0000-000000000000").status_code == 405


def test_invoice_totals_issue_and_failed_issue_are_atomic() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = service.create_invoice(invoice_data(values))
        assert invoice.status == "DRAFT" and invoice.journal_id is None
        assert invoice.subtotal == Decimal("250.00")
        assert invoice.total == Decimal("275.00")
        issued = service.issue_invoice(
            invoice.id,
            InvoiceIssue(
                receivable_account_id=values.receivable.id,
                revenue_account_id=values.revenue.id,
                tax_liability_account_id=values.tax_liability.id,
            ),
        )
        assert issued.status == "ISSUED"
        assert issued.journal is not None
        assert sum(line.debit for line in issued.journal.lines) == issued.total
        assert next(
            line.credit
            for line in issued.journal.lines
            if line.account_id == values.revenue.id
        ) == Decimal("250.00")
        assert next(
            line.credit
            for line in issued.journal.lines
            if line.account_id == values.tax_liability.id
        ) == Decimal("25.00")
        with pytest.raises(ConflictError, match="Source-document"):
            service.reverse_journal(issued.journal.id)
        failed = service.create_invoice(invoice_data(values, "I-2"))
        values.revenue.is_active = False
        session.commit()
        before = len(session.scalars(select(JournalEntry)).all())
        with pytest.raises(ConflictError):
            service.issue_invoice(
                failed.id,
                InvoiceIssue(
                    receivable_account_id=values.receivable.id,
                    revenue_account_id=values.revenue.id,
                    tax_liability_account_id=values.tax_liability.id,
                ),
            )
        persisted = session.get(Invoice, failed.id)
        assert persisted is not None and persisted.status == "DRAFT"
        assert len(session.scalars(select(JournalEntry)).all()) == before


def test_invoice_issue_requires_distinct_asset_receivable_and_revenue_accounts() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = service.create_invoice(invoice_data(values))

        with pytest.raises(AccountingError, match="different"):
            service.issue_invoice(
                invoice.id,
                InvoiceIssue(
                    receivable_account_id=values.receivable.id,
                    revenue_account_id=values.receivable.id,
                    tax_liability_account_id=values.tax_liability.id,
                ),
            )
        with pytest.raises(AccountingError, match="REVENUE"):
            service.issue_invoice(
                invoice.id,
                InvoiceIssue(
                    receivable_account_id=values.receivable.id,
                    revenue_account_id=values.cash.id,
                    tax_liability_account_id=values.tax_liability.id,
                ),
            )

        session.refresh(invoice)
        assert invoice.status == "DRAFT" and invoice.journal_id is None


def test_invoice_issue_rejects_broad_category_accounts_without_semantic_roles() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        generic_asset = Account(
            owner_id=values.admin.id,
            code="1200", name="Generic asset", category=values.receivable.category
        )
        session.add(generic_asset)
        session.commit()
        invoice = service.create_invoice(invoice_data(values))

        with pytest.raises(AccountingError, match="posting role RECEIVABLE"):
            service.issue_invoice(
                invoice.id,
                InvoiceIssue(
                    receivable_account_id=generic_asset.id,
                    revenue_account_id=values.revenue.id,
                    tax_liability_account_id=values.tax_liability.id,
                ),
            )


def test_taxed_invoice_requires_liability_and_never_credits_tax_as_revenue() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = service.create_invoice(invoice_data(values))

        with pytest.raises(AccountingError, match="tax liability account is required"):
            service.issue_invoice(
                invoice.id,
                InvoiceIssue(
                    receivable_account_id=values.receivable.id,
                    revenue_account_id=values.revenue.id,
                ),
            )

        issued = service.issue_invoice(
            invoice.id,
            InvoiceIssue(
                receivable_account_id=values.receivable.id,
                revenue_account_id=values.revenue.id,
                tax_liability_account_id=values.tax_liability.id,
            ),
        )
        journal = issued.journal
        assert journal is not None
        credits = {line.account_id: line.credit for line in journal.lines}
        assert credits[values.revenue.id] == issued.subtotal
        assert credits[values.tax_liability.id] == issued.tax


def test_zero_value_invoice_is_rejected() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        data = invoice_data(values)
        data.items[0].unit_price = Decimal("0")
        data.items[0].tax = Decimal("0")

        with pytest.raises(AccountingError, match="greater than zero"):
            service.create_invoice(data)

        assert session.scalar(select(Invoice).where(Invoice.invoice_number == "I-1")) is None


def test_typed_customer_and_check_details_are_persisted_and_validated() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        data = invoice_data(values)
        data.customer_id = None
        data.customer_name = "مشتری جدید"
        data.payment_method = "CHECK"
        data.checks = [
            InvoiceCheckCreate(
                amount=Decimal("100"),
                sayad_id="SAYAD-001",
                due_date=date(2026, 2, 15),
                status="PENDING",
            ),
            InvoiceCheckCreate(
                amount=Decimal("175"),
                sayad_id=None,
                due_date=date(2026, 3, 1),
                status="BOUNCED",
            ),
        ]

        invoice = service.create_invoice(data)

        assert invoice.customer.name == "مشتری جدید"
        assert invoice.customer.is_customer
        assert invoice.payment_method == "CHECK"
        assert [check.sayad_id for check in invoice.checks] == ["SAYAD-001", None]
        assert sum(check.amount for check in invoice.checks) == invoice.total

        underpaid = invoice_data(values, "I-PARTIAL-CHECKS")
        underpaid.payment_method = "CHECK"
        underpaid.checks = [
            InvoiceCheckCreate(
                amount=Decimal("200"),
                sayad_id="SAYAD-003",
                due_date=date(2026, 3, 1),
            )
        ]
        partial_invoice = service.create_invoice(underpaid)
        assert sum(check.amount for check in partial_invoice.checks) == Decimal(
            "200.00"
        )
        assert partial_invoice.total == Decimal("275.00")


def test_underpaid_invoice_check_leaves_customer_receivable_balance() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        data = invoice_data(values, "I-UNDERPAID-CHECK")
        data.payment_method = "CHECK"
        data.checks = [
            InvoiceCheckCreate(
                amount=Decimal("200"),
                sayad_id="UNDERPAID-001",
                due_date=date(2026, 2, 15),
            )
        ]
        invoice = service.create_invoice(data)
        issued = service.issue_invoice(
            invoice.id,
            InvoiceIssue(
                receivable_account_id=values.receivable.id,
                revenue_account_id=values.revenue.id,
                tax_liability_account_id=values.tax_liability.id,
            ),
        )

        cleared = service.update_invoice_check(
            issued.checks[0].id,
            InvoiceCheckUpdate(
                status="CLEARED",
                cash_account_id=values.cash.id,
                cleared_date=date(2026, 2, 20),
            ),
        )
        payment = session.get(Payment, cleared.cleared_payment_id)
        assert payment is not None and payment.journal is not None
        assert payment.amount == Decimal("200.00")
        assert all(
            line.account_id != values.customer_credit.id
            for line in payment.journal.lines
        )
        session.refresh(issued)
        assert issued.amount_paid == Decimal("200.00")
        assert issued.balance_due == Decimal("75.00")
        assert issued.status == "PARTIALLY_PAID"


def test_overpaid_invoice_check_posts_customer_credit_only_when_cleared() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        data = invoice_data(values, "I-OVERPAID-CHECK")
        data.payment_method = "CHECK"
        data.checks = [
            InvoiceCheckCreate(
                amount=Decimal("300"),
                sayad_id="",
                due_date=date(2026, 2, 15),
            )
        ]
        invoice = service.create_invoice(data)
        assert invoice.checks[0].sayad_id is None
        assert invoice.amount_paid == 0

        issued = service.issue_invoice(
            invoice.id,
            InvoiceIssue(
                receivable_account_id=values.receivable.id,
                revenue_account_id=values.revenue.id,
                tax_liability_account_id=values.tax_liability.id,
            ),
        )
        assert issued.journal is not None
        issue_credits = {
            line.account_id: line.credit
            for line in issued.journal.lines
            if line.credit > 0
        }
        assert issue_credits == {
            values.revenue.id: issued.subtotal,
            values.tax_liability.id: issued.tax,
        }

        check = issued.checks[0]
        with pytest.raises(AccountingError, match="Customer credit account is required"):
            service.update_invoice_check(
                check.id,
                InvoiceCheckUpdate(
                    status="CLEARED",
                    cash_account_id=values.cash.id,
                    cleared_date=date(2026, 2, 20),
                ),
            )

        cleared = service.update_invoice_check(
            check.id,
            InvoiceCheckUpdate(
                status="CLEARED",
                cash_account_id=values.cash.id,
                customer_credit_account_id=values.customer_credit.id,
                cleared_date=date(2026, 2, 20),
            ),
        )
        payment = session.get(Payment, cleared.cleared_payment_id)
        assert payment is not None and payment.journal is not None
        debits = {
            line.account_id: line.debit
            for line in payment.journal.lines
            if line.debit > 0
        }
        credits = {
            line.account_id: line.credit
            for line in payment.journal.lines
            if line.credit > 0
        }
        assert debits == {values.cash.id: Decimal("300.00")}
        assert credits == {
            values.receivable.id: Decimal("275.00"),
            values.customer_credit.id: Decimal("25.00"),
        }
        assert sum(debits.values()) == sum(credits.values())
        session.refresh(issued)
        assert issued.amount_paid == issued.total
        assert issued.status == "PAID"


def test_only_cleared_check_posts_payment_and_cleared_check_is_immutable() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        data = invoice_data(values)
        data.payment_method = "CHECK"
        data.checks = [
            InvoiceCheckCreate(
                amount=Decimal("100"),
                sayad_id="CLEAR-001",
                due_date=date(2026, 2, 15),
            ),
            InvoiceCheckCreate(
                amount=Decimal("175"),
                sayad_id="CLEAR-002",
                due_date=date(2026, 3, 1),
            ),
        ]
        invoice = service.create_invoice(data)
        issued = service.issue_invoice(
            invoice.id,
            InvoiceIssue(
                receivable_account_id=values.receivable.id,
                revenue_account_id=values.revenue.id,
                tax_liability_account_id=values.tax_liability.id,
            ),
        )
        first, second = issued.checks

        bounced = service.update_invoice_check(
            first.id, InvoiceCheckUpdate(status="BOUNCED")
        )
        assert bounced.status == "BOUNCED"
        assert issued.amount_paid == Decimal("0")
        assert len(service.list(Payment)) == 0

        cleared = service.update_invoice_check(
            first.id,
            InvoiceCheckUpdate(
                status="CLEARED",
                cash_account_id=values.cash.id,
                cleared_date=date(2026, 2, 20),
            ),
        )
        session.refresh(issued)
        assert cleared.status == "CLEARED"
        assert cleared.cleared_payment_id is not None
        assert issued.amount_paid == Decimal("100.00")
        assert issued.status == "PARTIALLY_PAID"
        payment = session.scalars(select(Payment)).one()
        assert payment.status == "POSTED" and payment.amount == Decimal("100.00")

        with pytest.raises(ConflictError, match="immutable"):
            service.update_invoice_check(
                first.id, InvoiceCheckUpdate(status="PENDING")
            )

        service.update_invoice_check(
            second.id,
            InvoiceCheckUpdate(
                status="CLEARED",
                cash_account_id=values.cash.id,
                cleared_date=date(2026, 3, 1),
            ),
        )
        session.refresh(issued)
        assert issued.amount_paid == issued.total
        assert issued.status == "PAID"


def post_invoice(service: AccountingService, values: Domain, number: str = "I-1") -> Invoice:
    invoice = service.create_invoice(invoice_data(values, number))
    return service.issue_invoice(
        invoice.id,
        InvoiceIssue(
            receivable_account_id=values.receivable.id,
            revenue_account_id=values.revenue.id,
            tax_liability_account_id=values.tax_liability.id,
        ),
    )


def payment_data(
    values: Domain, invoice: Invoice, amount: Decimal, reference: str
) -> PaymentCreate:
    return PaymentCreate(
        party_id=values.customer.id,
        payment_date=date(2026, 2, 5),
        amount=amount,
        reference=reference,
        method="bank",
        allocations=[{"invoice_id": invoice.id, "amount": amount}],
    )


def bill_data(values: Domain, number: str = "B-1") -> BillCreate:
    return BillCreate(
        bill_number=number,
        supplier_id=values.supplier.id,
        issue_date=date(2026, 2, 1),
        due_date=date(2026, 3, 1),
        items=[
            {
                "product_id": values.product.id,
                "description": "Purchased service",
                "quantity": Decimal("2.5"),
                "tax": Decimal("25"),
            }
        ],
    )


def post_bill(service: AccountingService, values: Domain, number: str = "B-1") -> Bill:
    bill = service.create_bill(bill_data(values, number))
    return service.issue_bill(
        bill.id,
        BillIssue(
            expense_account_id=values.expense.id,
            payable_account_id=values.payable.id,
        ),
    )


def bill_payment_data(
    values: Domain, bill: Bill, amount: Decimal, reference: str
) -> BillPaymentCreate:
    return BillPaymentCreate(
        party_id=values.supplier.id,
        payment_date=date(2026, 2, 5),
        amount=amount,
        reference=reference,
        method="bank",
        allocations=[{"bill_id": bill.id, "amount": amount}],
    )


def test_partial_and_full_payments_post_through_same_ledger() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = post_invoice(service, values)
        first = service.create_payment(payment_data(values, invoice, Decimal("100"), "P-1"))
        service.post_payment(
            first.id,
            PaymentPost(cash_account_id=values.cash.id, receivable_account_id=values.receivable.id),
        )
        assert invoice.amount_paid == Decimal("100.00")
        assert invoice.status == "PARTIALLY_PAID"
        second = service.create_payment(payment_data(values, invoice, Decimal("175"), "P-2"))
        service.post_payment(
            second.id,
            PaymentPost(cash_account_id=values.cash.id, receivable_account_id=values.receivable.id),
        )
        assert invoice.balance_due == 0 and invoice.status == "PAID"
        assert second.journal is not None
        assert second.journal.status == "POSTED"
        assert sum(line.debit for line in second.journal.lines) == sum(
            line.credit for line in second.journal.lines
        )
        with pytest.raises(ConflictError, match="Source-document"):
            service.reverse_journal(second.journal.id)


def test_payment_post_requires_distinct_accounts_and_matching_invoice_receivable() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = post_invoice(service, values)
        payment = service.create_payment(
            payment_data(values, invoice, Decimal("100"), "ACCOUNT-CHECK")
        )

        with pytest.raises(AccountingError, match="different"):
            service.post_payment(
                payment.id,
                PaymentPost(
                    cash_account_id=values.receivable.id,
                    receivable_account_id=values.receivable.id,
                ),
            )
        other_receivable = Account(
            owner_id=values.admin.id,
            code="1199",
            name="Other receivable",
            category=values.receivable.category,
            posting_role="RECEIVABLE",
        )
        session.add(other_receivable)
        session.commit()
        with pytest.raises(AccountingError, match="match the invoice"):
            service.post_payment(
                payment.id,
                PaymentPost(
                    cash_account_id=values.cash.id,
                    receivable_account_id=other_receivable.id,
                ),
            )

        session.refresh(payment)
        session.refresh(invoice)
        assert payment.status == "DRAFT" and payment.journal_id is None
        assert invoice.amount_paid == 0 and invoice.status == "ISSUED"


def test_customer_overpayment_posts_receivable_and_credit_liability() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = post_invoice(service, values)
        payment = service.create_payment(
            PaymentCreate(
                party_id=values.customer.id,
                payment_date=date(2026, 2, 5),
                amount=Decimal("300"),
                reference="OVERPAYMENT",
                method="check",
                sayad_id="OPTIONAL-SAYAD",
                check_due_date=date(2026, 3, 5),
                allocations=[{"invoice_id": invoice.id, "amount": invoice.total}],
            )
        )

        with pytest.raises(AccountingError, match="Customer credit account is required"):
            service.post_payment(
                payment.id,
                PaymentPost(
                    cash_account_id=values.cash.id,
                    receivable_account_id=values.receivable.id,
                ),
            )

        posted = service.post_payment(
            payment.id,
            PaymentPost(
                cash_account_id=values.cash.id,
                receivable_account_id=values.receivable.id,
                customer_credit_account_id=values.customer_credit.id,
            ),
        )
        assert posted.sayad_id == "OPTIONAL-SAYAD"
        assert posted.journal is not None
        debits = {line.account_id: line.debit for line in posted.journal.lines if line.debit > 0}
        credits = {
            line.account_id: line.credit for line in posted.journal.lines if line.credit > 0
        }
        assert debits == {values.cash.id: Decimal("300.00")}
        assert credits == {
            values.receivable.id: Decimal("275.00"),
            values.customer_credit.id: Decimal("25.00"),
        }
        assert sum(debits.values()) == sum(credits.values())
        assert invoice.status == "PAID" and invoice.balance_due == 0


def test_payment_post_locks_payment_and_invoice_rows_before_allocation() -> None:
    locked_selects = 0

    def count_locks(*args: object) -> None:
        nonlocal locked_selects
        clause = args[1]
        if getattr(clause, "_for_update_arg", None) is not None:
            locked_selects += 1

    event.listen(engine, "before_execute", count_locks)
    try:
        with SessionLocal() as session:
            service, values = domain(session)
            invoice = post_invoice(service, values)
            payment = service.create_payment(
                payment_data(values, invoice, Decimal("100"), "LOCK-CHECK")
            )
            service.post_payment(
                payment.id,
                PaymentPost(
                    cash_account_id=values.cash.id,
                    receivable_account_id=values.receivable.id,
                ),
            )
    finally:
        event.remove(engine, "before_execute", count_locks)

    assert locked_selects >= 2


def test_period_account_mutation_and_journal_post_use_row_locks() -> None:
    locked_entities: list[type[object]] = []

    def record_lock(*args: object) -> None:
        clause = args[1]
        if getattr(clause, "_for_update_arg", None) is None:
            return
        locked_entities.extend(
            description["entity"]
            for description in getattr(clause, "column_descriptions", [])
            if description.get("entity") is not None
        )

    event.listen(engine, "before_execute", record_lock)
    try:
        with SessionLocal() as session:
            service, values = domain(session)
            service.update_account(values.cash.id, AccountUpdate(name="Locked cash"))
            assert locked_entities.count(Account) == 1

            journal = service.create_journal(journal_data(values))
            service.post_journal(journal.id)
            assert locked_entities.count(FinancialPeriod) == 1
            assert locked_entities.count(Account) == 3

            service.close_period(values.period.id)
            assert locked_entities.count(FinancialPeriod) == 2
    finally:
        event.remove(engine, "before_execute", record_lock)


def test_payment_overallocation_and_cancelled_invoice_fail() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = post_invoice(service, values)
        with pytest.raises(AccountingError, match="balance"):
            service.create_payment(payment_data(values, invoice, Decimal("300"), "P-1"))
        invalid = payment_data(values, invoice, Decimal("50"), "P-2")
        invalid.allocations[0].amount = Decimal("100")
        with pytest.raises(AccountingError, match="cannot exceed"):
            service.create_payment(invalid)
        invoice.status = "CANCELLED"
        session.commit()
        with pytest.raises(ConflictError, match="invalid"):
            service.create_payment(payment_data(values, invoice, Decimal("10"), "P-3"))


def test_failed_payment_post_rolls_back_journal_invoice_and_payment() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        invoice = post_invoice(service, values)
        payment = service.create_payment(payment_data(values, invoice, Decimal("100"), "ROLLBACK"))
        values.cash.is_active = False
        session.commit()
        before = len(session.scalars(select(JournalEntry)).all())
        with pytest.raises(ConflictError, match="Inactive"):
            service.post_payment(
                payment.id,
                PaymentPost(
                    cash_account_id=values.cash.id,
                    receivable_account_id=values.receivable.id,
                ),
            )
        session.refresh(payment)
        session.refresh(invoice)
        assert payment.status == "DRAFT" and payment.journal_id is None
        assert invoice.amount_paid == 0 and invoice.status == "ISSUED"
        assert len(session.scalars(select(JournalEntry)).all()) == before


def test_taxed_bill_issues_full_total_to_expense_and_payable() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        bill = service.create_bill(bill_data(values))

        assert bill.status == "DRAFT"
        assert bill.subtotal == Decimal("250.00")
        assert bill.tax == Decimal("25.00")
        assert bill.total == Decimal("275.00")
        issued = service.issue_bill(
            bill.id,
            BillIssue(
                expense_account_id=values.expense.id,
                payable_account_id=values.payable.id,
            ),
        )

        assert issued.status == "ISSUED"
        assert issued.journal is not None and len(issued.journal.lines) == 2
        debits = {line.account_id: line.debit for line in issued.journal.lines if line.debit > 0}
        credits = {
            line.account_id: line.credit for line in issued.journal.lines if line.credit > 0
        }
        assert debits == {values.expense.id: Decimal("275.00")}
        assert credits == {values.payable.id: Decimal("275.00")}
        assert values.tax_liability.id not in debits | credits
        with pytest.raises(ConflictError, match="Source-document"):
            service.reverse_journal(issued.journal.id)


def test_bill_issue_rejects_zero_closed_period_and_wrong_or_duplicate_roles() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        zero = bill_data(values, "B-ZERO")
        zero.items[0].unit_price = Decimal("0")
        zero.items[0].tax = Decimal("0")
        with pytest.raises(AccountingError, match="greater than zero"):
            service.create_bill(zero)

        bill = service.create_bill(bill_data(values, "B-ROLE"))
        generic_expense = Account(
            owner_id=values.admin.id,
            code="5099", name="Generic expense", category=values.expense.category
        )
        generic_liability = Account(
            owner_id=values.admin.id,
            code="2199", name="Generic liability", category=values.payable.category
        )
        session.add_all([generic_expense, generic_liability])
        session.commit()
        with pytest.raises(AccountingError, match="different"):
            service.issue_bill(
                bill.id,
                BillIssue(
                    expense_account_id=values.payable.id,
                    payable_account_id=values.payable.id,
                ),
            )
        with pytest.raises(AccountingError, match="posting role EXPENSE"):
            service.issue_bill(
                bill.id,
                BillIssue(
                    expense_account_id=generic_expense.id,
                    payable_account_id=values.payable.id,
                ),
            )
        with pytest.raises(AccountingError, match="posting role PAYABLE"):
            service.issue_bill(
                bill.id,
                BillIssue(
                    expense_account_id=values.expense.id,
                    payable_account_id=generic_liability.id,
                ),
            )

        values.period.status = "CLOSED"
        session.commit()
        with pytest.raises(ConflictError, match="closed period"):
            service.issue_bill(
                bill.id,
                BillIssue(
                    expense_account_id=values.expense.id,
                    payable_account_id=values.payable.id,
                ),
            )
        session.refresh(bill)
        assert bill.status == "DRAFT" and bill.journal_id is None


def test_partial_and_full_bill_payments_reduce_payable_and_are_not_reversible() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        bill = post_bill(service, values)
        first = service.create_bill_payment(
            bill_payment_data(values, bill, Decimal("100"), "BP-1")
        )
        service.post_bill_payment(
            first.id,
            BillPaymentPost(
                cash_account_id=values.cash.id,
                payable_account_id=values.payable.id,
            ),
        )
        assert bill.amount_paid == Decimal("100.00")
        assert bill.status == "PARTIALLY_PAID"

        second = service.create_bill_payment(
            bill_payment_data(values, bill, Decimal("175"), "BP-2")
        )
        service.post_bill_payment(
            second.id,
            BillPaymentPost(
                cash_account_id=values.cash.id,
                payable_account_id=values.payable.id,
            ),
        )
        assert bill.balance_due == 0 and bill.status == "PAID"
        assert second.journal is not None
        debits = {line.account_id: line.debit for line in second.journal.lines if line.debit > 0}
        credits = {
            line.account_id: line.credit for line in second.journal.lines if line.credit > 0
        }
        assert debits == {values.payable.id: Decimal("175.00")}
        assert credits == {values.cash.id: Decimal("175.00")}
        with pytest.raises(ConflictError, match="Source-document"):
            service.reverse_journal(second.journal.id)


def test_bill_payment_rejects_overallocation_invalid_sum_and_wrong_payable() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        bill = post_bill(service, values)
        with pytest.raises(AccountingError, match="balance"):
            service.create_bill_payment(
                bill_payment_data(values, bill, Decimal("300"), "BP-OVER")
            )
        invalid = bill_payment_data(values, bill, Decimal("100"), "BP-SUM")
        invalid.allocations[0].amount = Decimal("50")
        with pytest.raises(AccountingError, match="equal"):
            service.create_bill_payment(invalid)

        payment = service.create_bill_payment(
            bill_payment_data(values, bill, Decimal("100"), "BP-WRONG")
        )
        other_payable = Account(
            owner_id=values.admin.id,
            code="2099",
            name="Other payable",
            category=values.payable.category,
            posting_role="PAYABLE",
        )
        session.add(other_payable)
        session.commit()
        with pytest.raises(AccountingError, match="match the bill"):
            service.post_bill_payment(
                payment.id,
                BillPaymentPost(
                    cash_account_id=values.cash.id,
                    payable_account_id=other_payable.id,
                ),
            )


def test_bill_payment_post_locks_payment_and_bill_rows_before_allocation() -> None:
    locked_selects = 0

    def count_locks(*args: object) -> None:
        nonlocal locked_selects
        clause = args[1]
        if getattr(clause, "_for_update_arg", None) is not None:
            locked_selects += 1

    event.listen(engine, "before_execute", count_locks)
    try:
        with SessionLocal() as session:
            service, values = domain(session)
            bill = post_bill(service, values)
            payment = service.create_bill_payment(
                bill_payment_data(values, bill, Decimal("100"), "BP-LOCK")
            )
            service.post_bill_payment(
                payment.id,
                BillPaymentPost(
                    cash_account_id=values.cash.id,
                    payable_account_id=values.payable.id,
                ),
            )
    finally:
        event.remove(engine, "before_execute", count_locks)

    assert locked_selects >= 2


def test_audits_cover_accounting_mutations_without_secrets() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        journal = service.create_journal(journal_data(values))
        service.post_journal(journal.id)
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action.like("accounting.%"))
        ).all()
        assert {event.action for event in events} >= {
            "accounting.journal.created",
            "accounting.journal.posted",
        }
        assert "password" not in str([event.details for event in events]).casefold()


def test_master_data_period_and_hierarchy_rules() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        with pytest.raises(AccountingError, match="customer or supplier"):
            service.create_party(PartyCreate(name="No role"))
        supplier = service.create_party(PartyCreate(name="Supplier", is_supplier=True))
        service.update_party(supplier.id, PartyUpdate(phone="555", is_customer=True))
        assert supplier.phone == "555" and supplier.is_customer
        with pytest.raises(AccountingError, match="retain"):
            service.update_party(supplier.id, PartyUpdate(is_customer=False, is_supplier=False))
        session.rollback()

        product = service.create_product(
            ProductCreate(sku="P-2", name="Other", unit_price=Decimal("1.23"))
        )
        service.update_product(product.id, ProductUpdate(unit_price=Decimal("2.34")))
        assert product.unit_price == Decimal("2.34")
        with pytest.raises(ConflictError):
            service.create_product(
                ProductCreate(sku="P-2", name="Duplicate", unit_price=Decimal("1"))
            )

        category = service.create_category(CategoryCreate(name="Expenses", account_type="EXPENSE"))
        parent = service.create_account(
            AccountCreate(code="5000", name="Expenses", category_id=category.id)
        )
        child = service.create_account(
            AccountCreate(code="5100", name="Office", category_id=category.id, parent_id=parent.id)
        )
        service.update_account(child.id, AccountUpdate(name="Office costs"))
        assert child.name == "Office costs"
        with pytest.raises(AccountingError, match="own parent"):
            service.update_account(child.id, AccountUpdate(parent_id=child.id))

        with pytest.raises(AccountingError, match="start date"):
            service.create_period(
                PeriodCreate(name="Invalid", start_date=date(2027, 2, 1), end_date=date(2027, 1, 1))
            )
        with pytest.raises(ConflictError, match="overlap"):
            service.create_period(
                PeriodCreate(name="Overlap", start_date=date(2026, 6, 1), end_date=date(2027, 1, 1))
            )
        service.close_period(values.period.id)
        assert values.period.status == "CLOSED"
        assert service.get(Product, product.id) is product
        assert product in service.list(Product)
        with pytest.raises(NotFoundError):
            service.get(Product, values.admin.id)


def test_posted_account_category_cannot_rewrite_historical_reports() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        post_invoice(service, values)
        expense = service.create_category(
            CategoryCreate(name="Reclassification target", account_type="EXPENSE")
        )

        with pytest.raises(ConflictError, match="posted journals"):
            service.update_account(
                values.receivable.id,
                AccountUpdate(category_id=expense.id),
            )

        session.refresh(values.receivable)
        assert values.receivable.category_id != expense.id

        with pytest.raises(ConflictError, match="posting role"):
            service.update_account(
                values.receivable.id,
                AccountUpdate(posting_role="CASH"),
            )


def test_invalid_invoice_and_payment_parties_and_products() -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        values.customer.is_active = False
        session.commit()
        with pytest.raises(AccountingError, match="active customer"):
            service.create_invoice(invoice_data(values))
        values.customer.is_active = True
        values.product.is_active = False
        session.commit()
        with pytest.raises(AccountingError, match="Inactive products"):
            service.create_invoice(invoice_data(values))
        values.product.is_active = True
        session.commit()
        invalid_dates = invoice_data(values)
        invalid_dates.due_date = date(2026, 1, 1)
        with pytest.raises(AccountingError, match="due date"):
            service.create_invoice(invalid_dates)


def test_party_contract_rejects_blank_names_and_invalid_email() -> None:
    with pytest.raises(ValidationError):
        PartyCreate(name="   ", is_customer=True)
    with pytest.raises(ValidationError):
        PartyCreate(name="Customer", email="not-an-email", is_customer=True)
