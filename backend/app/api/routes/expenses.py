import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import cache_delete, group_summary_cache_key
from app.core.deps import get_current_user, get_db
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.group_member import GroupMember
from app.models.user import User
from app.schemas.expense import ExpenseCreate, ExpenseOut
from app.services.split_service import calculate_splits

router = APIRouter(tags=["expenses"])


def _group_member_ids(db: Session, group_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.query(GroupMember.user_id).filter(GroupMember.group_id == group_id).all()
    return {r[0] for r in rows}


def _require_membership(db: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> set[uuid.UUID]:
    member_ids = _group_member_ids(db, group_id)
    if user_id not in member_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found.")
    return member_ids


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    expense_in: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Expense:
    member_ids = _require_membership(db, expense_in.group_id, current_user.id)

    if expense_in.paid_by not in member_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "paid_by must be a member of the group.")

    participants = expense_in.participant_ids or [s.user_id for s in expense_in.splits]
    for uid in participants:
        if uid not in member_ids:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"User {uid} is not a member of this group."
            )

    shares = calculate_splits(expense_in)  # raises 422 on any validation failure

    expense = Expense(
        group_id=expense_in.group_id,
        description=expense_in.description,
        total_amount=expense_in.total_amount,
        split_type=expense_in.split_type,
        paid_by=expense_in.paid_by,
    )
    db.add(expense)
    db.flush()

    percentage_by_user = {s.user_id: s.percentage for s in expense_in.splits}
    for user_id, amount in shares.items():
        db.add(
            ExpenseSplit(
                expense_id=expense.id,
                user_id=user_id,
                amount=amount,
                percentage=percentage_by_user.get(user_id),
            )
        )

    db.commit()
    db.refresh(expense)
    cache_delete(group_summary_cache_key(str(expense_in.group_id)))
    return expense


@router.get("/groups/{group_id}/expenses", response_model=list[ExpenseOut])
def list_group_expenses(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Expense]:
    _require_membership(db, group_id, current_user.id)
    return (
        db.query(Expense)
        .filter(Expense.group_id == group_id)
        .order_by(Expense.created_at.desc())
        .all()
    )


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Expense:
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found.")
    _require_membership(db, expense.group_id, current_user.id)
    return expense


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found.")
    _require_membership(db, expense.group_id, current_user.id)

    group_id = expense.group_id
    db.delete(expense)
    db.commit()
    cache_delete(group_summary_cache_key(str(group_id)))
