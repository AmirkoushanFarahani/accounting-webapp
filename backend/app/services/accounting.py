from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.db.base import Base
from backend.app.db.models import (
    Account,
    AccountCategory,
    Bill,
    BillItem,
    BillPayment,
    BillPaymentAllocation,
    Expense,
    FinancialPeriod,
    Invoice,
    InvoiceCheck,
    InvoiceItem,
    JournalEntry,
    JournalLine,
    Party,
    Payment,
    PaymentAllocation,
    Product,
    User,
)
from backend.app.repositories.accounting import AccountingRepository
from backend.app.repositories.audit import AuditRepository
from backend.app.schemas.accounting import (
    AccountCreate,
    AccountUpdate,
    BillCreate,
    BillIssue,
    BillPaymentCreate,
    BillPaymentPost,
    CategoryCreate,
    InvoiceCheckUpdate,
    InvoiceCreate,
    InvoiceIssue,
    JournalCreate,
    JournalLineCreate,
    PartyCreate,
    PartyUpdate,
    PaymentCreate,
    PaymentPost,
    PeriodCreate,
    ProductCreate,
    ProductUpdate,
)
from backend.app.schemas.expense import ExpenseCreate

CENT = Decimal("0.01")
ModelT = TypeVar("ModelT", bound=Base)


class AccountingError(ValueError):
    pass


class NotFoundError(AccountingError):
    pass


class ConflictError(AccountingError):
    pass


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class AccountingService:
    def create_expense(self, data: ExpenseCreate) -> Expense:
        """Immediately paid expense, including checks by explicit owner decision."""
        from uuid import uuid4

        try:
            period = self.session.scalar(
                select(FinancialPeriod).where(
                    FinancialPeriod.owner_id == self.actor.id,
                    FinancialPeriod.start_date <= data.payment_date,
                    FinancialPeriod.end_date >= data.payment_date,
                )
            )
            if period is None:
                raise AccountingError("No financial period covers the payment date")
            self._get_for_update(FinancialPeriod, period.id)
            for account_id in sorted({data.expense_account_id, data.cash_account_id}, key=str):
                self._get_for_update(Account, account_id)
            self._posting_account(data.expense_account_id, "EXPENSE", "EXPENSE", "Expense")
            self._posting_account(data.cash_account_id, "ASSET", "CASH", "Cash")
            journal = self.create_journal(
                JournalCreate(
                    entry_number=f"EXP-{uuid4()}",
                    entry_date=data.payment_date,
                    period_id=period.id,
                    description=data.name,
                    lines=[
                        JournalLineCreate(account_id=data.expense_account_id, debit=data.amount),
                        JournalLineCreate(account_id=data.cash_account_id, credit=data.amount),
                    ],
                ),
                commit=False,
            )
            self._post_journal(journal)
            expense = Expense(
                owner_id=self.actor.id,
                journal_id=journal.id,
                **data.model_dump(exclude={"expense_account_id", "cash_account_id"}),
            )
            self.session.add(expense)
            self._flush()
            self._audit("accounting.expense.created", expense)
            self._commit()
            return expense
        except Exception:
            self.session.rollback()
            raise

    def __init__(self, session: Session, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.repo = AccountingRepository(session, actor.id)
        self.audit = AuditRepository(session)

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("A unique or database constraint was violated") from exc

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("A unique or database constraint was violated") from exc

    def _get(self, model: type[ModelT], item_id: UUID) -> ModelT:
        item = self.session.scalar(
            select(model).where(
                model.id == item_id,  # type: ignore[attr-defined]
                model.owner_id == self.actor.id,  # type: ignore[attr-defined]
            )
        )
        if item is None:
            raise NotFoundError(f"{model.__name__} not found")
        return item

    def _get_for_update(self, model: type[ModelT], item_id: UUID) -> ModelT:
        item = self.session.scalar(
            select(model)
            .where(
                model.id == item_id,  # type: ignore[attr-defined]
                model.owner_id == self.actor.id,  # type: ignore[attr-defined]
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise NotFoundError(f"{model.__name__} not found")
        return item

    def _posting_account(
        self, account_id: UUID, expected_type: str, expected_role: str, label: str
    ) -> Account:
        account = self._get(Account, account_id)
        if not account.is_active:
            raise ConflictError(f"Inactive {label.casefold()} account cannot receive postings")
        if account.category.account_type != expected_type:
            raise AccountingError(f"{label} account must have type {expected_type}")
        if account.posting_role != expected_role:
            raise AccountingError(f"{label} account must have posting role {expected_role}")
        return account

    @staticmethod
    def _validate_posting_role(category: AccountCategory, posting_role: str) -> None:
        required_types = {
            "CASH": "ASSET",
            "RECEIVABLE": "ASSET",
            "REVENUE": "REVENUE",
            "TAX_LIABILITY": "LIABILITY",
            "PAYABLE": "LIABILITY",
            "EXPENSE": "EXPENSE",
            "CUSTOMER_CREDIT": "LIABILITY",
        }
        required_type = required_types.get(posting_role)
        if required_type is not None and category.account_type != required_type:
            raise AccountingError(
                f"Posting role {posting_role} requires account type {required_type}"
            )

    def _audit(self, action: str, resource: Base) -> None:
        self.audit.record(
            action=action,
            resource_type=type(resource).__name__.casefold(),
            resource_id=str(resource.id),  # type: ignore[attr-defined]
            actor_id=self.actor.id,
            success=True,
        )

    def create_party(self, data: PartyCreate) -> Party:
        if not data.is_customer and not data.is_supplier:
            raise AccountingError("A party must be a customer or supplier")
        party = Party(owner_id=self.actor.id, **data.model_dump())
        self.session.add(party)
        self._flush()
        self._audit("accounting.party.created", party)
        self._commit()
        return party

    def update_party(self, party_id: UUID, data: PartyUpdate) -> Party:
        party = self._get(Party, party_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(party, key, value)
        if not party.is_customer and not party.is_supplier:
            raise AccountingError("A party must retain at least one role")
        self._audit("accounting.party.updated", party)
        self._commit()
        return party

    def create_product(self, data: ProductCreate) -> Product:
        product = Product(owner_id=self.actor.id, **data.model_dump())
        self.session.add(product)
        self._flush()
        self._audit("accounting.product.created", product)
        self._commit()
        return product

    def update_product(self, product_id: UUID, data: ProductUpdate) -> Product:
        product = self._get(Product, product_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(product, key, value)
        self._audit("accounting.product.updated", product)
        self._commit()
        return product

    def create_category(self, data: CategoryCreate) -> AccountCategory:
        category = AccountCategory(owner_id=self.actor.id, **data.model_dump())
        self.session.add(category)
        self._commit()
        return category

    def create_account(self, data: AccountCreate) -> Account:
        category = self._get(AccountCategory, data.category_id)
        self._validate_posting_role(category, data.posting_role)
        if data.parent_id is not None:
            self._get(Account, data.parent_id)
        account = Account(owner_id=self.actor.id, **data.model_dump())
        self.session.add(account)
        self._flush()
        self._audit("accounting.account.created", account)
        self._commit()
        return account

    def update_account(self, account_id: UUID, data: AccountUpdate) -> Account:
        account = self._get_for_update(Account, account_id)
        values = data.model_dump(exclude_unset=True)
        category = account.category
        if "category_id" in values:
            category_id = values["category_id"]
            if category_id is None:
                raise AccountingError("Account category is required")
            category = self._get(AccountCategory, category_id)
            if category_id != account.category_id:
                posted_line = self.session.scalar(
                    select(JournalLine.id)
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                    .where(
                        JournalLine.account_id == account.id,
                        JournalEntry.status == "POSTED",
                    )
                    .limit(1)
                )
                if posted_line is not None:
                    raise ConflictError(
                        "The category of an account used in posted journals cannot be changed"
                    )
        posting_role = values.get("posting_role", account.posting_role)
        if posting_role is None:
            raise AccountingError("Account posting role is required")
        self._validate_posting_role(category, posting_role)
        if posting_role != account.posting_role:
            posted_line = self.session.scalar(
                select(JournalLine.id)
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                .where(
                    JournalLine.account_id == account.id,
                    JournalEntry.status == "POSTED",
                )
                .limit(1)
            )
            if posted_line is not None:
                raise ConflictError(
                    "The posting role of an account used in posted journals cannot be changed"
                )
        parent_id = values.get("parent_id")
        if parent_id == account.id:
            raise AccountingError("An account cannot be its own parent")
        if parent_id is not None:
            parent: Account | None = self._get(Account, parent_id)
            seen = {account.id}
            while parent is not None:
                if parent.id in seen:
                    raise AccountingError("Circular account hierarchy")
                seen.add(parent.id)
                parent = parent.parent
        for key, value in values.items():
            setattr(account, key, value)
        self._audit("accounting.account.updated", account)
        self._commit()
        return account

    def create_period(self, data: PeriodCreate) -> FinancialPeriod:
        if data.start_date > data.end_date:
            raise AccountingError("Period start date must not exceed end date")
        overlap = self.session.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.owner_id == self.actor.id,
                FinancialPeriod.start_date <= data.end_date,
                FinancialPeriod.end_date >= data.start_date,
            )
        )
        if overlap is not None:
            raise ConflictError("Financial periods cannot overlap")
        period = FinancialPeriod(owner_id=self.actor.id, **data.model_dump())
        self.session.add(period)
        self._flush()
        self._audit("accounting.period.created", period)
        self._commit()
        return period

    def close_period(self, period_id: UUID) -> FinancialPeriod:
        period = self._get_for_update(FinancialPeriod, period_id)
        period.status = "CLOSED"
        self._audit("accounting.period.closed", period)
        self._commit()
        return period

    @staticmethod
    def _validate_line(debit: Decimal, credit: Decimal) -> None:
        if debit < 0 or credit < 0:
            raise AccountingError("Journal amounts cannot be negative")
        if (debit > 0) == (credit > 0):
            raise AccountingError("Each line requires a positive amount on exactly one side")

    def create_journal(self, data: JournalCreate, *, commit: bool = True) -> JournalEntry:
        period = self._get(FinancialPeriod, data.period_id)
        if not period.start_date <= data.entry_date <= period.end_date:
            raise AccountingError("Journal date is outside the financial period")
        lines: list[JournalLine] = []
        for value in data.lines:
            self._validate_line(value.debit, value.credit)
            self._get(Account, value.account_id)
            lines.append(JournalLine(**value.model_dump()))
        journal = JournalEntry(
            owner_id=self.actor.id,
            entry_number=data.entry_number,
            entry_date=data.entry_date,
            description=data.description,
            period_id=data.period_id,
            created_by_id=self.actor.id,
            lines=lines,
        )
        self.session.add(journal)
        self._flush()
        self._audit("accounting.journal.created", journal)
        if commit:
            self._commit()
        return journal

    def _post_journal(self, journal: JournalEntry) -> JournalEntry:
        if journal.status != "DRAFT":
            raise ConflictError("Only draft journals can be posted")
        period = self._get_for_update(FinancialPeriod, journal.period_id)
        if period.status != "OPEN":
            raise ConflictError("Cannot post into a closed period")
        accounts = {
            account_id: self._get_for_update(Account, account_id)
            for account_id in sorted({line.account_id for line in journal.lines}, key=str)
        }
        if len(journal.lines) < 2:
            raise AccountingError("A posted journal requires at least two lines")
        debit = Decimal("0")
        credit = Decimal("0")
        for line in journal.lines:
            self._validate_line(line.debit, line.credit)
            if not accounts[line.account_id].is_active:
                raise ConflictError("Inactive accounts cannot receive postings")
            debit += line.debit
            credit += line.credit
        if money(debit) != money(credit):
            raise AccountingError("Journal debits and credits must balance")
        journal.status = "POSTED"
        self._audit("accounting.journal.posted", journal)
        return journal

    def post_journal(self, journal_id: UUID) -> JournalEntry:
        journal = self._get(JournalEntry, journal_id)
        try:
            self._post_journal(journal)
            self._commit()
        except Exception:
            self.session.rollback()
            raise
        return journal

    def reverse_journal(self, journal_id: UUID) -> JournalEntry:
        original = self._get(JournalEntry, journal_id)
        if original.status != "POSTED":
            raise ConflictError("Only posted journals can be reversed")
        if original.reversal_of_id is not None:
            raise ConflictError("Reversal journals cannot be reversed")
        existing_reversal = self.session.scalar(
            select(JournalEntry).where(
                JournalEntry.owner_id == self.actor.id,
                JournalEntry.reversal_of_id == original.id,
            )
        )
        if existing_reversal is not None:
            raise ConflictError("Journal has already been reversed")
        invoice_source = self.session.scalar(
            select(Invoice.id).where(Invoice.journal_id == original.id)
        )
        payment_source = self.session.scalar(
            select(Payment.id).where(Payment.journal_id == original.id)
        )
        bill_source = self.session.scalar(select(Bill.id).where(Bill.journal_id == original.id))
        bill_payment_source = self.session.scalar(
            select(BillPayment.id).where(BillPayment.journal_id == original.id)
        )
        expense_source = self.session.scalar(
            select(Expense.id).where(Expense.journal_id == original.id)
        )
        if any(
            source is not None
            for source in (
                invoice_source,
                payment_source,
                bill_source,
                bill_payment_source,
                expense_source,
            )
        ):
            raise ConflictError("Source-document journals cannot be reversed directly")
        reversal = JournalEntry(
            owner_id=self.actor.id,
            entry_number=f"REV-{original.entry_number}",
            entry_date=original.entry_date,
            description=f"Reversal of {original.entry_number}: {original.description}",
            period_id=original.period_id,
            created_by_id=self.actor.id,
            reversal_of_id=original.id,
            lines=[
                JournalLine(
                    account_id=line.account_id,
                    description=line.description,
                    debit=line.credit,
                    credit=line.debit,
                )
                for line in original.lines
            ],
        )
        self.session.add(reversal)
        try:
            self._flush()
            self._post_journal(reversal)
            self._audit("accounting.journal.reversed", reversal)
            self._commit()
        except Exception:
            self.session.rollback()
            raise
        return reversal

    def create_invoice(self, data: InvoiceCreate) -> Invoice:
        if (data.customer_id is None) == (data.customer_name is None):
            raise AccountingError("Provide either customer_id or customer_name")
        if data.customer_id is not None:
            customer = self._get(Party, data.customer_id)
            if not customer.is_customer or not customer.is_active:
                raise AccountingError("Invoice party must be an active customer")
        else:
            customer_name = data.customer_name
            if customer_name is None:  # guarded by the exclusive-or check above
                raise AccountingError("Customer name is required")
            existing_customer = self.session.scalar(
                select(Party).where(
                    Party.owner_id == self.actor.id,
                    Party.name == customer_name,
                    Party.is_active.is_(True),
                )
            )
            if existing_customer is None:
                customer = Party(
                    owner_id=self.actor.id,
                    name=customer_name,
                    is_customer=True,
                    is_supplier=False,
                )
                self.session.add(customer)
                self._flush()
            else:
                customer = existing_customer
            if not customer.is_customer:
                customer.is_customer = True
        if data.issue_date > data.due_date:
            raise AccountingError("Invoice due date cannot precede issue date")
        items: list[InvoiceItem] = []
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        for value in data.items:
            product = self._get(Product, value.product_id) if value.product_id else None
            if product is not None and not product.is_active:
                raise AccountingError("Inactive products cannot be invoiced")
            unit_price = (
                value.unit_price
                if value.unit_price is not None
                else product.unit_price
                if product
                else None
            )
            if unit_price is None:
                raise AccountingError("Unit price is required without a product")
            line_subtotal = money(value.quantity * unit_price)
            line_total = money(line_subtotal + value.tax)
            subtotal += line_subtotal
            tax_total += value.tax
            items.append(
                InvoiceItem(
                    **value.model_dump(exclude={"unit_price"}),
                    unit_price=unit_price,
                    line_subtotal=line_subtotal,
                    line_total=line_total,
                )
            )
        invoice = Invoice(
            owner_id=self.actor.id,
            invoice_number=data.invoice_number,
            customer_id=customer.id,
            issue_date=data.issue_date,
            due_date=data.due_date,
            payment_method=data.payment_method,
            subtotal=money(subtotal),
            tax=money(tax_total),
            total=money(subtotal + tax_total),
            items=items,
        )
        if invoice.total == 0:
            raise AccountingError("Invoice total must be greater than zero")
        if data.payment_method == "CASH" and data.checks:
            raise AccountingError("Cash invoices cannot contain checks")
        if data.payment_method == "CHECK":
            if not data.checks:
                raise AccountingError("Check invoices require at least one check")
            sayad_ids = [check.sayad_id for check in data.checks if check.sayad_id is not None]
            if len(sayad_ids) != len(set(sayad_ids)):
                raise AccountingError("Each check must have a unique Sayad identifier")
            if any(check.due_date < data.issue_date for check in data.checks):
                raise AccountingError("Check due dates cannot precede the invoice issue date")
            invoice.checks = [
                InvoiceCheck(owner_id=self.actor.id, **check.model_dump())
                for check in data.checks
            ]
        self.session.add(invoice)
        self._flush()
        self._audit("accounting.invoice.created", invoice)
        self._commit()
        return invoice

    def issue_invoice(self, invoice_id: UUID, data: InvoiceIssue) -> Invoice:
        invoice = self._get(Invoice, invoice_id)
        if invoice.status != "DRAFT":
            raise ConflictError("Only draft invoices can be issued")
        if invoice.tax > 0 and data.tax_liability_account_id is None:
            raise AccountingError("A tax liability account is required for a taxed invoice")
        account_ids = {data.receivable_account_id, data.revenue_account_id}
        if data.tax_liability_account_id is not None:
            account_ids.add(data.tax_liability_account_id)
        required_count = 3 if invoice.tax > 0 else 2
        if len(account_ids) != required_count:
            raise AccountingError("Invoice posting accounts must be different")
        self._posting_account(
            data.receivable_account_id, "ASSET", "RECEIVABLE", "Receivable"
        )
        self._posting_account(data.revenue_account_id, "REVENUE", "REVENUE", "Revenue")
        if data.tax_liability_account_id is not None:
            self._posting_account(
                data.tax_liability_account_id,
                "LIABILITY",
                "TAX_LIABILITY",
                "Tax liability",
            )
        period = self._period_for(invoice.issue_date)
        journal_lines = [
            JournalLineCreate(
                account_id=data.receivable_account_id, debit=invoice.total, credit=0
            ),
            JournalLineCreate(
                account_id=data.revenue_account_id, debit=0, credit=invoice.subtotal
            ),
        ]
        if invoice.tax > 0:
            if data.tax_liability_account_id is None:  # guarded above; narrows the type
                raise AccountingError("A tax liability account is required for a taxed invoice")
            journal_lines.append(
                JournalLineCreate(
                    account_id=data.tax_liability_account_id,
                    debit=0,
                    credit=invoice.tax,
                )
            )
        journal = self.create_journal(
            JournalCreate(
                entry_number=f"INV-{invoice.invoice_number}",
                entry_date=invoice.issue_date,
                description=f"Invoice {invoice.invoice_number}",
                period_id=period.id,
                lines=journal_lines,
            ),
            commit=False,
        )
        try:
            self._post_journal(journal)
            invoice.status = "ISSUED"
            invoice.journal = journal
            self._audit("accounting.invoice.issued", invoice)
            self._commit()
        except Exception:
            self.session.rollback()
            raise
        return invoice

    def _period_for(self, value: date) -> FinancialPeriod:
        period = self.session.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.owner_id == self.actor.id,
                FinancialPeriod.start_date <= value,
                FinancialPeriod.end_date >= value,
            )
        )
        if period is None:
            raise AccountingError("No financial period contains this date")
        return period

    def create_bill(self, data: BillCreate) -> Bill:
        supplier = self._get(Party, data.supplier_id)
        if not supplier.is_supplier or not supplier.is_active:
            raise AccountingError("Bill party must be an active supplier")
        if data.issue_date > data.due_date:
            raise AccountingError("Bill due date cannot precede issue date")
        items: list[BillItem] = []
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        for value in data.items:
            product = self._get(Product, value.product_id) if value.product_id else None
            if product is not None and not product.is_active:
                raise AccountingError("Inactive products cannot be billed")
            unit_price = (
                value.unit_price
                if value.unit_price is not None
                else product.unit_price
                if product
                else None
            )
            if unit_price is None:
                raise AccountingError("Unit price is required without a product")
            line_subtotal = money(value.quantity * unit_price)
            line_total = money(line_subtotal + value.tax)
            subtotal += line_subtotal
            tax_total += value.tax
            items.append(
                BillItem(
                    **value.model_dump(exclude={"unit_price"}),
                    unit_price=unit_price,
                    line_subtotal=line_subtotal,
                    line_total=line_total,
                )
            )
        bill = Bill(
            owner_id=self.actor.id,
            bill_number=data.bill_number,
            supplier_id=data.supplier_id,
            issue_date=data.issue_date,
            due_date=data.due_date,
            subtotal=money(subtotal),
            tax=money(tax_total),
            total=money(subtotal + tax_total),
            items=items,
        )
        if bill.total == 0:
            raise AccountingError("Bill total must be greater than zero")
        self.session.add(bill)
        self._flush()
        self._audit("accounting.bill.created", bill)
        self._commit()
        return bill

    def issue_bill(self, bill_id: UUID, data: BillIssue) -> Bill:
        bill = self._get(Bill, bill_id)
        if bill.status != "DRAFT":
            raise ConflictError("Only draft bills can be issued")
        if data.expense_account_id == data.payable_account_id:
            raise AccountingError("Bill posting accounts must be different")
        self._posting_account(data.expense_account_id, "EXPENSE", "EXPENSE", "Expense")
        self._posting_account(data.payable_account_id, "LIABILITY", "PAYABLE", "Payable")
        period = self._period_for(bill.issue_date)
        journal = self.create_journal(
            JournalCreate(
                entry_number=f"BILL-{bill.bill_number}",
                entry_date=bill.issue_date,
                description=f"Bill {bill.bill_number}",
                period_id=period.id,
                lines=[
                    {
                        "account_id": data.expense_account_id,
                        "debit": bill.total,
                        "credit": 0,
                    },
                    {
                        "account_id": data.payable_account_id,
                        "debit": 0,
                        "credit": bill.total,
                    },
                ],
            ),
            commit=False,
        )
        try:
            self._post_journal(journal)
            bill.status = "ISSUED"
            bill.journal = journal
            self._audit("accounting.bill.issued", bill)
            self._commit()
        except Exception:
            self.session.rollback()
            raise
        return bill

    def create_payment(self, data: PaymentCreate) -> Payment:
        party = self._get(Party, data.party_id)
        if not party.is_customer or not party.is_active:
            raise AccountingError("Payment party must be an active customer")
        allocation_total = money(
            sum((item.amount for item in data.allocations), Decimal("0"))
        )
        if allocation_total > money(data.amount):
            raise AccountingError("Payment allocations cannot exceed the payment amount")
        if data.customer_credit_account_id is not None:
            self._posting_account(
                data.customer_credit_account_id,
                "LIABILITY",
                "CUSTOMER_CREDIT",
                "Customer credit",
            )
        seen: set[UUID] = set()
        allocations: list[PaymentAllocation] = []
        for value in data.allocations:
            if value.invoice_id in seen:
                raise AccountingError("An invoice may be allocated only once per payment")
            seen.add(value.invoice_id)
            invoice = self._get(Invoice, value.invoice_id)
            if invoice.customer_id != party.id or invoice.status not in {
                "ISSUED",
                "PARTIALLY_PAID",
            }:
                raise ConflictError("Payment allocation targets an invalid invoice")
            if value.amount > invoice.balance_due:
                raise AccountingError("Allocation exceeds invoice balance")
            allocations.append(PaymentAllocation(**value.model_dump()))
        payment = Payment(
            owner_id=self.actor.id,
            **data.model_dump(exclude={"allocations"}),
            allocations=allocations,
        )
        self.session.add(payment)
        self._flush()
        self._audit("accounting.payment.created", payment)
        self._commit()
        return payment

    def post_payment(self, payment_id: UUID, data: PaymentPost) -> Payment:
        payment = self._get_for_update(Payment, payment_id)
        return self._post_payment(payment, data, commit=True)

    def _post_payment(
        self, payment: Payment, data: PaymentPost, *, commit: bool
    ) -> Payment:
        if payment.status != "DRAFT":
            raise ConflictError("Only draft payments can be posted")
        if data.cash_account_id == data.receivable_account_id:
            raise AccountingError("Cash and receivable accounts must be different")
        self._posting_account(data.cash_account_id, "ASSET", "CASH", "Cash")
        self._posting_account(
            data.receivable_account_id, "ASSET", "RECEIVABLE", "Receivable"
        )
        allocation_total = money(
            sum((allocation.amount for allocation in payment.allocations), Decimal("0"))
        )
        if allocation_total > money(payment.amount):
            raise AccountingError("Payment allocations cannot exceed the payment amount")
        customer_credit = money(payment.amount - allocation_total)
        if customer_credit > 0:
            if data.customer_credit_account_id is None:
                raise AccountingError(
                    "Customer credit account is required when payment exceeds allocations"
                )
            self._posting_account(
                data.customer_credit_account_id,
                "LIABILITY",
                "CUSTOMER_CREDIT",
                "Customer credit",
            )

        invoice_ids = sorted(
            (allocation.invoice_id for allocation in payment.allocations), key=str
        )
        locked_invoices = list(
            self.session.scalars(
                select(Invoice)
                .where(
                    Invoice.owner_id == self.actor.id,
                    Invoice.id.in_(invoice_ids),
                )
                .order_by(Invoice.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        invoices = {invoice.id: invoice for invoice in locked_invoices}
        if len(invoices) != len(invoice_ids):
            raise NotFoundError("Invoice not found")
        for allocation in payment.allocations:
            invoice = invoices[allocation.invoice_id]
            if invoice.customer_id != payment.party_id or invoice.status not in {
                "ISSUED",
                "PARTIALLY_PAID",
            }:
                raise ConflictError("Payment allocation targets an invalid invoice")
            if allocation.amount > invoice.balance_due:
                raise AccountingError("Allocation exceeds current invoice balance")
            receivable_accounts = {
                line.account_id
                for line in invoice.journal.lines
                if line.debit > 0
            } if invoice.journal is not None else set()
            if receivable_accounts != {data.receivable_account_id}:
                raise AccountingError(
                    "Payment receivable account must match the invoice receivable account"
                )
        period = self._period_for(payment.payment_date)
        journal_lines = [
            JournalLineCreate(
                account_id=data.cash_account_id,
                debit=payment.amount,
                credit=Decimal("0"),
            )
        ]
        if allocation_total > 0:
            journal_lines.append(
                JournalLineCreate(
                    account_id=data.receivable_account_id,
                    debit=Decimal("0"),
                    credit=allocation_total,
                )
            )
        if customer_credit > 0:
            if data.customer_credit_account_id is None:  # guarded above; narrows the type
                raise AccountingError(
                    "Customer credit account is required when payment exceeds allocations"
                )
            journal_lines.append(
                JournalLineCreate(
                    account_id=data.customer_credit_account_id,
                    debit=Decimal("0"),
                    credit=customer_credit,
                )
            )
        journal = self.create_journal(
            JournalCreate(
                entry_number=f"PAY-{payment.reference}",
                entry_date=payment.payment_date,
                description=f"Payment {payment.reference}",
                period_id=period.id,
                lines=journal_lines,
            ),
            commit=False,
        )
        try:
            self._post_journal(journal)
            for allocation in payment.allocations:
                invoice = invoices[allocation.invoice_id]
                invoice.amount_paid = money(invoice.amount_paid + allocation.amount)
                invoice.status = "PAID" if invoice.balance_due == 0 else "PARTIALLY_PAID"
            payment.status = "POSTED"
            payment.journal = journal
            self._audit("accounting.payment.posted", payment)
            if commit:
                self._commit()
        except Exception:
            self.session.rollback()
            raise
        return payment

    def update_invoice_check(
        self, check_id: UUID, data: InvoiceCheckUpdate
    ) -> InvoiceCheck:
        check = self._get_for_update(InvoiceCheck, check_id)
        if check.status == "CLEARED":
            raise ConflictError("Cleared checks are immutable")
        invoice = self._get_for_update(Invoice, check.invoice_id)
        if data.status != "CLEARED":
            if (
                data.cash_account_id is not None
                or data.customer_credit_account_id is not None
                or data.cleared_date is not None
            ):
                raise AccountingError(
                    "Posting accounts and cleared date are only valid when clearing a check"
                )
            check.status = data.status
            self._audit("accounting.invoice_check.updated", check)
            self._commit()
            return check
        if invoice.status not in {"ISSUED", "PARTIALLY_PAID", "PAID"}:
            raise ConflictError("Only checks for issued invoices can be cleared")
        if data.cash_account_id is None or data.cleared_date is None:
            raise AccountingError("Cash account and cleared date are required")
        allocation_amount = min(check.amount, invoice.balance_due)
        customer_credit = money(check.amount - allocation_amount)
        if customer_credit > 0 and data.customer_credit_account_id is None:
            raise AccountingError(
                "Customer credit account is required when a check exceeds the invoice balance"
            )
        if invoice.journal is None:
            raise ConflictError("Issued invoice journal is missing")
        receivable_ids = {
            line.account_id for line in invoice.journal.lines if line.debit > 0
        }
        if len(receivable_ids) != 1:
            raise ConflictError("Invoice receivable account is ambiguous")
        receivable_account_id = next(iter(receivable_ids))
        payment = Payment(
            owner_id=self.actor.id,
            party_id=invoice.customer_id,
            payment_date=data.cleared_date,
            amount=check.amount,
            reference=f"CHECK-{check.sayad_id or check.id}",
            method="CHECK",
            sayad_id=check.sayad_id,
            customer_credit_account_id=data.customer_credit_account_id,
            allocations=(
                [PaymentAllocation(invoice_id=invoice.id, amount=allocation_amount)]
                if allocation_amount > 0
                else []
            ),
        )
        self.session.add(payment)
        self._flush()
        self._audit("accounting.payment.created", payment)
        self._post_payment(
            payment,
            PaymentPost(
                cash_account_id=data.cash_account_id,
                receivable_account_id=receivable_account_id,
                customer_credit_account_id=data.customer_credit_account_id,
            ),
            commit=False,
        )
        check.status = "CLEARED"
        check.cleared_date = data.cleared_date
        check.cleared_payment_id = payment.id
        self._audit("accounting.invoice_check.cleared", check)
        self._commit()
        return check

    def create_bill_payment(self, data: BillPaymentCreate) -> BillPayment:
        party = self._get(Party, data.party_id)
        if not party.is_supplier or not party.is_active:
            raise AccountingError("Bill payment party must be an active supplier")
        if money(sum((item.amount for item in data.allocations), Decimal("0"))) != money(
            data.amount
        ):
            raise AccountingError("Bill payment allocations must equal the payment amount")
        seen: set[UUID] = set()
        allocations: list[BillPaymentAllocation] = []
        for value in data.allocations:
            if value.bill_id in seen:
                raise AccountingError("A bill may be allocated only once per payment")
            seen.add(value.bill_id)
            bill = self._get(Bill, value.bill_id)
            if bill.supplier_id != party.id or bill.status not in {
                "ISSUED",
                "PARTIALLY_PAID",
            }:
                raise ConflictError("Bill payment allocation targets an invalid bill")
            if value.amount > bill.balance_due:
                raise AccountingError("Allocation exceeds bill balance")
            allocations.append(BillPaymentAllocation(**value.model_dump()))
        payment = BillPayment(
            owner_id=self.actor.id,
            **data.model_dump(exclude={"allocations"}),
            allocations=allocations,
        )
        self.session.add(payment)
        self._flush()
        self._audit("accounting.bill_payment.created", payment)
        self._commit()
        return payment

    def post_bill_payment(self, payment_id: UUID, data: BillPaymentPost) -> BillPayment:
        payment = self._get_for_update(BillPayment, payment_id)
        if payment.status != "DRAFT":
            raise ConflictError("Only draft bill payments can be posted")
        if data.cash_account_id == data.payable_account_id:
            raise AccountingError("Cash and payable accounts must be different")
        self._posting_account(data.cash_account_id, "ASSET", "CASH", "Cash")
        self._posting_account(data.payable_account_id, "LIABILITY", "PAYABLE", "Payable")

        bill_ids = sorted((allocation.bill_id for allocation in payment.allocations), key=str)
        locked_bills = list(
            self.session.scalars(
                select(Bill)
                .where(Bill.owner_id == self.actor.id, Bill.id.in_(bill_ids))
                .order_by(Bill.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        bills = {bill.id: bill for bill in locked_bills}
        if len(bills) != len(bill_ids):
            raise NotFoundError("Bill not found")
        for allocation in payment.allocations:
            bill = bills[allocation.bill_id]
            if bill.supplier_id != payment.party_id or bill.status not in {
                "ISSUED",
                "PARTIALLY_PAID",
            }:
                raise ConflictError("Bill payment allocation targets an invalid bill")
            if allocation.amount > bill.balance_due:
                raise AccountingError("Allocation exceeds current bill balance")
            payable_accounts = (
                {line.account_id for line in bill.journal.lines if line.credit > 0}
                if bill.journal is not None
                else set()
            )
            if payable_accounts != {data.payable_account_id}:
                raise AccountingError(
                    "Bill payment payable account must match the bill payable account"
                )
        period = self._period_for(payment.payment_date)
        journal = self.create_journal(
            JournalCreate(
                entry_number=f"BPAY-{payment.reference}",
                entry_date=payment.payment_date,
                description=f"Bill payment {payment.reference}",
                period_id=period.id,
                lines=[
                    {
                        "account_id": data.payable_account_id,
                        "debit": payment.amount,
                        "credit": 0,
                    },
                    {"account_id": data.cash_account_id, "debit": 0, "credit": payment.amount},
                ],
            ),
            commit=False,
        )
        try:
            self._post_journal(journal)
            for allocation in payment.allocations:
                bill = bills[allocation.bill_id]
                bill.amount_paid = money(bill.amount_paid + allocation.amount)
                bill.status = "PAID" if bill.balance_due == 0 else "PARTIALLY_PAID"
            payment.status = "POSTED"
            payment.journal = journal
            self._audit("accounting.bill_payment.posted", payment)
            self._commit()
        except Exception:
            self.session.rollback()
            raise
        return payment

    def list(
        self,
        model: type[Account]
        | type[AccountCategory]
        | type[FinancialPeriod]
        | type[Bill]
        | type[BillPayment]
        | type[Invoice]
        | type[JournalEntry]
        | type[Party]
        | type[Payment]
        | type[Product],
    ) -> list[object]:
        statement = select(model).where(model.owner_id == self.actor.id)
        # Read/list only; posting queries keep their existing row-locking behavior.
        if model is Invoice:
            statement = statement.options(selectinload(Invoice.items), selectinload(Invoice.checks))
        elif model is JournalEntry:
            statement = statement.options(selectinload(JournalEntry.lines))
        return list(self.session.scalars(statement))

    def get(
        self,
        model: type[Account]
        | type[AccountCategory]
        | type[FinancialPeriod]
        | type[Bill]
        | type[BillPayment]
        | type[Invoice]
        | type[JournalEntry]
        | type[Party]
        | type[Payment]
        | type[Product],
        item_id: UUID,
    ) -> object:
        return self._get(model, item_id)
