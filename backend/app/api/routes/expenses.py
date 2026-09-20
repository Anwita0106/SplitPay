import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.expense import ExpenseCreate, ExpenseOut, ExpenseUpdate
from app.services import expense_service

router = APIRouter(tags=["expenses"])


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    expense_in: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = expense_service.create_expense(db, expense_in, current_user)
    return expense_service.serialize_expenses(db, [expense])[0]


@router.get("/groups/{group_id}/expenses", response_model=list[ExpenseOut])
def list_group_expenses(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expenses = expense_service.list_group_expenses(db, group_id, current_user)
    return expense_service.serialize_expenses(db, expenses)


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = expense_service.get_expense_or_404(db, expense_id, current_user)
    return expense_service.serialize_expenses(db, [expense])[0]


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: uuid.UUID,
    expense_in: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit an expense; every share is recomputed and group balances update immediately."""
    expense = expense_service.update_expense(db, expense_id, expense_in, current_user)
    return expense_service.serialize_expenses(db, [expense])[0]


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense_service.delete_expense(db, expense_id, current_user)
    return Response(status_code=204)
