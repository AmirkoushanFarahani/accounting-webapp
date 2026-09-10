from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payment_date: date
    method: Literal["CASH", "CHECK", "BANK_TRANSFER"]
    tracking_code: str | None = Field(default=None, max_length=100)
    expense_account_id: UUID
    cash_account_id: UUID


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    amount: Decimal
    payment_date: date
    method: str
    tracking_code: str | None
    journal_id: UUID


class ExpenseList(BaseModel):
    items: list[ExpenseRead]
    total: Decimal
