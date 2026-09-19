from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PartyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    is_customer: bool = False
    is_supplier: bool = False


class PartyUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    is_customer: bool | None = None
    is_supplier: bool | None = None
    is_active: bool | None = None


class PartyRead(ORMModel):
    id: UUID
    name: str
    email: str | None
    phone: str | None
    address: str | None
    is_customer: bool
    is_supplier: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    unit: str = Field(default="each", min_length=1, max_length=30)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    is_active: bool | None = None


class ProductRead(ORMModel):
    id: UUID
    sku: str
    name: str
    description: str | None
    unit: str
    unit_price: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account_type: str = Field(pattern="^(ASSET|LIABILITY|EQUITY|REVENUE|EXPENSE)$")


class CategoryRead(ORMModel):
    id: UUID
    name: str
    account_type: str


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    category_id: UUID
    parent_id: UUID | None = None
    posting_role: str = Field(
        default="GENERAL",
        pattern="^(GENERAL|CASH|RECEIVABLE|REVENUE|TAX_LIABILITY|PAYABLE|EXPENSE|CUSTOMER_CREDIT)$",
    )


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: UUID | None = None
    parent_id: UUID | None = None
    is_active: bool | None = None
    posting_role: str | None = Field(
        default=None,
        pattern="^(GENERAL|CASH|RECEIVABLE|REVENUE|TAX_LIABILITY|PAYABLE|EXPENSE|CUSTOMER_CREDIT)$",
    )


class AccountRead(ORMModel):
    id: UUID
    code: str
    name: str
    category_id: UUID
    parent_id: UUID | None
    is_active: bool
    posting_role: str


class PeriodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date


class PeriodRead(ORMModel):
    id: UUID
    name: str
    start_date: date
    end_date: date
    status: str


class JournalLineCreate(BaseModel):
    account_id: UUID
    description: str | None = Field(default=None, max_length=500)
    debit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    credit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)


class JournalCreate(BaseModel):
    entry_number: str = Field(min_length=1, max_length=80)
    entry_date: date
    description: str = Field(min_length=1, max_length=500)
    period_id: UUID
    lines: list[JournalLineCreate] = Field(min_length=1)


class JournalLineRead(ORMModel):
    id: UUID
    account_id: UUID
    description: str | None
    debit: Decimal
    credit: Decimal


class JournalRead(ORMModel):
    id: UUID
    entry_number: str
    entry_date: date
    description: str
    period_id: UUID
    status: str
    reversal_of_id: UUID | None
    lines: list[JournalLineRead]


class InvoiceItemCreate(BaseModel):
    product_id: UUID | None = None
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)


class InvoiceCheckCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    sayad_id: str | None = Field(default=None, max_length=32)
    due_date: date
    status: str = Field(default="PENDING", pattern="^(PENDING|BOUNCED)$")

    @field_validator("sayad_id", mode="before")
    @classmethod
    def empty_sayad_is_none(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    invoice_number: str = Field(min_length=1, max_length=80)
    customer_id: UUID | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=200)
    issue_date: date
    due_date: date
    payment_method: str = Field(default="CASH", pattern="^(CASH|CHECK)$")
    checks: list[InvoiceCheckCreate] = Field(default_factory=list)
    items: list[InvoiceItemCreate] = Field(min_length=1)


class InvoiceItemRead(ORMModel):
    id: UUID
    product_id: UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax: Decimal
    line_subtotal: Decimal
    line_total: Decimal


class InvoiceCheckRead(ORMModel):
    id: UUID
    amount: Decimal
    sayad_id: str | None
    due_date: date
    status: str
    cleared_date: date | None
    cleared_payment_id: UUID | None


class InvoiceRead(ORMModel):
    id: UUID
    invoice_number: str
    customer_id: UUID
    issue_date: date
    due_date: date
    status: str
    payment_method: str | None
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    amount_paid: Decimal
    journal_id: UUID | None
    items: list[InvoiceItemRead]
    checks: list[InvoiceCheckRead]
    created_at: datetime

    balance_due: Decimal


class InvoiceIssue(BaseModel):
    receivable_account_id: UUID
    revenue_account_id: UUID
    tax_liability_account_id: UUID | None = None


class InvoiceCheckUpdate(BaseModel):
    status: str = Field(pattern="^(PENDING|CLEARED|BOUNCED)$")
    cash_account_id: UUID | None = None
    customer_credit_account_id: UUID | None = None
    cleared_date: date | None = None


class AllocationCreate(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class PaymentCreate(BaseModel):
    party_id: UUID
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reference: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=1, max_length=50)
    sayad_id: str | None = Field(default=None, max_length=100)
    check_due_date: date | None = None
    customer_credit_account_id: UUID | None = None
    allocations: list[AllocationCreate] = Field(min_length=1)

    @field_validator("sayad_id", mode="before")
    @classmethod
    def empty_sayad_is_none(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_requires_due_date(self) -> "PaymentCreate":
        if self.method.strip().upper() in {"CHECK", "چک"} and self.check_due_date is None:
            raise ValueError("A check payment requires a due date")
        return self


class AllocationRead(ORMModel):
    id: UUID
    invoice_id: UUID
    amount: Decimal


class PaymentRead(ORMModel):
    id: UUID
    party_id: UUID
    payment_date: date
    amount: Decimal
    reference: str
    method: str
    sayad_id: str | None
    check_due_date: date | None
    customer_credit_account_id: UUID | None
    status: str
    journal_id: UUID | None
    allocations: list[AllocationRead]


class PaymentPost(BaseModel):
    cash_account_id: UUID
    receivable_account_id: UUID
    customer_credit_account_id: UUID | None = None


class BillItemCreate(BaseModel):
    product_id: UUID | None = None
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)


class BillCreate(BaseModel):
    bill_number: str = Field(min_length=1, max_length=80)
    supplier_id: UUID
    issue_date: date
    due_date: date
    items: list[BillItemCreate] = Field(min_length=1)


class BillItemRead(ORMModel):
    id: UUID
    product_id: UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax: Decimal
    line_subtotal: Decimal
    line_total: Decimal


class BillRead(ORMModel):
    id: UUID
    bill_number: str
    supplier_id: UUID
    issue_date: date
    due_date: date
    status: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    amount_paid: Decimal
    journal_id: UUID | None
    items: list[BillItemRead]
    balance_due: Decimal


class BillIssue(BaseModel):
    expense_account_id: UUID
    payable_account_id: UUID


class BillPaymentAllocationCreate(BaseModel):
    bill_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class BillPaymentCreate(BaseModel):
    party_id: UUID
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reference: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=1, max_length=50)
    sayad_id: str | None = Field(default=None, max_length=100)
    check_due_date: date | None = None
    allocations: list[BillPaymentAllocationCreate] = Field(min_length=1)

    @field_validator("sayad_id", mode="before")
    @classmethod
    def empty_sayad_is_none(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_requires_due_date(self) -> "BillPaymentCreate":
        if self.method.strip().upper() in {"CHECK", "چک"} and self.check_due_date is None:
            raise ValueError("A check payment requires a due date")
        return self


class BillPaymentAllocationRead(ORMModel):
    id: UUID
    bill_id: UUID
    amount: Decimal


class BillPaymentRead(ORMModel):
    id: UUID
    party_id: UUID
    payment_date: date
    amount: Decimal
    reference: str
    method: str
    sayad_id: str | None
    check_due_date: date | None
    status: str
    journal_id: UUID | None
    allocations: list[BillPaymentAllocationRead]


class BillPaymentPost(BaseModel):
    cash_account_id: UUID
    payable_account_id: UUID
