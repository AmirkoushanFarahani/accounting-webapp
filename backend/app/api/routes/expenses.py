from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import require_permission
from backend.app.db.database import get_db
from backend.app.db.models import Expense, User
from backend.app.schemas.expense import ExpenseCreate, ExpenseList, ExpenseRead
from backend.app.services.accounting import AccountingService

router = APIRouter()


@router.post(
    "/expenses",
    response_model=ExpenseRead,
    status_code=201,
    dependencies=[Depends(require_permission("bills:issue"))],
)
def create_expense(
    data: ExpenseCreate,
    session: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission("bill_payments:post"))],
) -> Expense:
    return AccountingService(session, actor).create_expense(data)


@router.get("/expenses", response_model=ExpenseList)
def list_expenses(
    session: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission("bills:read"))],
    start_date: date | None = None,
    end_date: date | None = None,
) -> ExpenseList:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "Invalid date range")
    query = select(Expense).where(Expense.owner_id == actor.id)
    if start_date:
        query = query.where(Expense.payment_date >= start_date)
    if end_date:
        query = query.where(Expense.payment_date <= end_date)
    rows = list(
        session.scalars(query.order_by(Expense.payment_date.desc(), Expense.created_at.desc()))
    )
    return ExpenseList(
        items=[ExpenseRead.model_validate(row) for row in rows],
        total=sum((row.amount for row in rows), Decimal("0.00")),
    )
