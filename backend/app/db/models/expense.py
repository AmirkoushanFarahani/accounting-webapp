from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, OwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Expense(UUIDPrimaryKeyMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("method IN ('CASH','CHECK','BANK_TRANSFER')", name="valid_method"),
    )
    name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    method: Mapped[str] = mapped_column(String(20))
    check_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    journal_id: Mapped[UUID] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"), unique=True
    )
