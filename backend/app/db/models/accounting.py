from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, OwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.identity import User

MONEY = Numeric(18, 2)
QUANTITY = Numeric(18, 4)


class Party(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "parties"
    __table_args__ = (CheckConstraint("is_customer OR is_supplier", name="has_role"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    is_customer: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_supplier: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("owner_id", "sku", name="uq_products_sku"),
        CheckConstraint("unit_price >= 0", name="nonnegative_price"),
    )

    sku: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(30), default="each", server_default="each")
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class AccountCategory(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "account_categories"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_account_categories_name"),
        CheckConstraint(
            "account_type IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')",
            name="valid_type",
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    accounts: Mapped[list["Account"]] = relationship(back_populates="category")


class Account(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("owner_id", "code", name="uq_accounts_code"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        CheckConstraint(
            "posting_role IN ('GENERAL','CASH','RECEIVABLE','REVENUE','TAX_LIABILITY',"
            "'PAYABLE','EXPENSE','CUSTOMER_CREDIT')",
            name="valid_posting_role",
        ),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("account_categories.id"))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
    posting_role: Mapped[str] = mapped_column(
        String(20), default="GENERAL", server_default="GENERAL", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    category: Mapped[AccountCategory] = relationship(back_populates="accounts")
    parent: Mapped["Account | None"] = relationship(remote_side="Account.id")


class FinancialPeriod(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_financial_periods_name"),
        CheckConstraint("start_date <= end_date", name="valid_dates"),
        CheckConstraint("status IN ('OPEN','CLOSED')", name="valid_status"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), default="OPEN", server_default="OPEN")


class JournalEntry(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("owner_id", "entry_number", name="uq_journal_entries_entry_number"),
        CheckConstraint("status IN ('DRAFT','POSTED','CANCELLED')", name="valid_status"),
        Index("ix_journal_entries_status_entry_date", "status", "entry_date"),
    )

    entry_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    period_id: Mapped[UUID] = mapped_column(ForeignKey("financial_periods.id"))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT", server_default="DRAFT")
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reversal_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"), unique=True
    )
    period: Mapped[FinancialPeriod] = relationship()
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="journal", cascade="all, delete-orphan", order_by="JournalLine.id"
    )
    reversal_of: Mapped["JournalEntry | None"] = relationship(remote_side="JournalEntry.id")


class JournalLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        Index("ix_journal_lines_journal_id", "journal_id"),
        Index("ix_journal_lines_account_id", "account_id"),
        CheckConstraint("debit >= 0 AND credit >= 0", name="nonnegative_amounts"),
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="one_positive_side",
        ),
    )

    journal_id: Mapped[UUID] = mapped_column(ForeignKey("journal_entries.id", ondelete="CASCADE"))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    description: Mapped[str | None] = mapped_column(String(500))
    debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    journal: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship()


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("owner_id", "invoice_number", name="uq_invoices_invoice_number"),
        CheckConstraint("issue_date <= due_date", name="valid_dates"),
        CheckConstraint(
            "subtotal >= 0 AND tax >= 0 AND total >= 0 AND amount_paid >= 0",
            name="nonnegative_totals",
        ),
        CheckConstraint(
            "status IN ('DRAFT','ISSUED','PARTIALLY_PAID','PAID','CANCELLED')", name="valid_status"
        ),
        CheckConstraint(
            "payment_method IS NULL OR payment_method IN ('CASH','CHECK')",
            name="valid_payment_method",
        ),
        Index("ix_invoices_customer_issue_date", "customer_id", "issue_date"),
        Index("ix_invoices_status_due_date", "status", "due_date"),
    )

    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("parties.id", ondelete="RESTRICT"))
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", server_default="DRAFT")
    payment_method: Mapped[str | None] = mapped_column(String(10))
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    amount_paid: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    journal_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entries.id"), unique=True)
    customer: Mapped[Party] = relationship()
    journal: Mapped[JournalEntry | None] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    checks: Mapped[list["InvoiceCheck"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceCheck.due_date, InvoiceCheck.id",
    )

    @property
    def balance_due(self) -> Decimal:
        return self.total - self.amount_paid


class InvoiceItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        Index("ix_invoice_items_invoice_id", "invoice_id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint(
            "unit_price >= 0 AND tax >= 0 AND line_subtotal >= 0 AND line_total >= 0",
            name="nonnegative_totals",
        ),
    )

    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    line_subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    invoice: Mapped[Invoice] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class InvoiceCheck(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "invoice_checks"
    __table_args__ = (
        UniqueConstraint("owner_id", "sayad_id", name="uq_invoice_checks_sayad_id"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint(
            "status IN ('PENDING','CLEARED','BOUNCED')", name="valid_status"
        ),
        Index("ix_invoice_checks_invoice_id", "invoice_id"),
        Index("ix_invoice_checks_status_due_date", "status", "due_date"),
    )

    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sayad_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default="PENDING", server_default="PENDING", nullable=False
    )
    cleared_date: Mapped[date | None] = mapped_column(Date)
    cleared_payment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), unique=True
    )
    invoice: Mapped[Invoice] = relationship(back_populates="checks")
    cleared_payment: Mapped["Payment | None"] = relationship(
        foreign_keys=[cleared_payment_id]
    )


class Bill(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("owner_id", "bill_number", name="uq_bills_bill_number"),
        CheckConstraint("issue_date <= due_date", name="valid_dates"),
        CheckConstraint(
            "subtotal >= 0 AND tax >= 0 AND total >= 0 AND amount_paid >= 0",
            name="nonnegative_totals",
        ),
        CheckConstraint(
            "status IN ('DRAFT','ISSUED','PARTIALLY_PAID','PAID','CANCELLED')",
            name="valid_status",
        ),
        Index("ix_bills_supplier_issue_date", "supplier_id", "issue_date"),
        Index("ix_bills_status_due_date", "status", "due_date"),
    )

    bill_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("parties.id", ondelete="RESTRICT"))
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", server_default="DRAFT")
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    amount_paid: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    journal_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entries.id"), unique=True)
    supplier: Mapped[Party] = relationship()
    journal: Mapped[JournalEntry | None] = relationship()
    items: Mapped[list["BillItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )

    @property
    def balance_due(self) -> Decimal:
        return self.total - self.amount_paid


class BillItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bill_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint(
            "unit_price >= 0 AND tax >= 0 AND line_subtotal >= 0 AND line_total >= 0",
            name="nonnegative_totals",
        ),
    )

    bill_id: Mapped[UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    line_subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    bill: Mapped[Bill] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("owner_id", "reference", name="uq_payments_reference"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("status IN ('DRAFT','POSTED','CANCELLED')", name="valid_status"),
        Index("ix_payments_party_payment_date", "party_id", "payment_date"),
        Index("ix_payments_status_payment_date", "status", "payment_date"),
    )

    party_id: Mapped[UUID] = mapped_column(ForeignKey("parties.id", ondelete="RESTRICT"))
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    sayad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    check_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_credit_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(12), default="DRAFT", server_default="DRAFT")
    journal_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entries.id"), unique=True)
    party: Mapped[Party] = relationship()
    journal: Mapped[JournalEntry | None] = relationship()
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentAllocation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint("payment_id", "invoice_id", name="uq_payment_allocations_pair"),
        CheckConstraint("amount > 0", name="positive_amount"),
        Index("ix_payment_allocations_invoice_id", "invoice_id"),
    )

    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"))
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment: Mapped[Payment] = relationship(back_populates="allocations")
    invoice: Mapped[Invoice] = relationship()


class BillPayment(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "bill_payments"
    __table_args__ = (
        UniqueConstraint("owner_id", "reference", name="uq_bill_payments_reference"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("status IN ('DRAFT','POSTED','CANCELLED')", name="valid_status"),
        Index("ix_bill_payments_party_payment_date", "party_id", "payment_date"),
        Index("ix_bill_payments_status_payment_date", "status", "payment_date"),
    )

    party_id: Mapped[UUID] = mapped_column(ForeignKey("parties.id", ondelete="RESTRICT"))
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    sayad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    check_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="DRAFT", server_default="DRAFT")
    journal_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entries.id"), unique=True)
    party: Mapped[Party] = relationship()
    journal: Mapped[JournalEntry | None] = relationship()
    allocations: Mapped[list["BillPaymentAllocation"]] = relationship(
        back_populates="bill_payment", cascade="all, delete-orphan"
    )


class BillPaymentAllocation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bill_payment_allocations"
    __table_args__ = (
        UniqueConstraint(
            "bill_payment_id", "bill_id", name="uq_bill_payment_allocations_pair"
        ),
        CheckConstraint("amount > 0", name="positive_amount"),
        Index("ix_bill_payment_allocations_bill_id", "bill_id"),
    )

    bill_payment_id: Mapped[UUID] = mapped_column(
        ForeignKey("bill_payments.id", ondelete="CASCADE")
    )
    bill_id: Mapped[UUID] = mapped_column(ForeignKey("bills.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    bill_payment: Mapped[BillPayment] = relationship(back_populates="allocations")
    bill: Mapped[Bill] = relationship()
