from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payment_date: date
    method: Literal["CASH", "CHECK", "BANK_TRANSFER"]
    check_due_date: date | None = None
    tracking_code: str | None = Field(default=None, max_length=100)
    expense_account_id: UUID
    cash_account_id: UUID

    @model_validator(mode="after")
    def check_requires_due_date(self) -> "ExpenseCreate":
        if self.method == "CHECK" and self.check_due_date is None:
            raise ValueError("A check expense requires a due date")
        return self


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    amount: Decimal
    payment_date: date
    method: str
    check_due_date: date | None
    tracking_code: str | None
    journal_id: UUID


class ExpenseList(BaseModel):
    items: list[ExpenseRead]
    total: Decimal
