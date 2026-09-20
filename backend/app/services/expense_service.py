"""
ExpenseService — the authoritative create / edit / delete path, shared by the
REST API and the AI confirmation flow. Money is Decimal end to end.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from app.core.cache import invalidate_group_after_commit
from app.core.errors import invalid, not_found
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.user import User
from app.schemas.expense import ExpenseBase, ExpenseCreate, ExpenseOut, ExpenseSplitOut, ExpenseUpdate
from app.services.group_service import lock_group, require_member
from app.services.settlement_service import refresh_suggestions_if_present
from app.services.split_service import calculate_splits


def _validated_shares(expense_in: ExpenseBase, member_ids: set[UUID]) -> dict[UUID, "Decimal"]:  # noqa: F821
    if expense_in.paid_by not in member_ids:
        raise invalid("The person who paid must be a member of the group.", "PAYER_NOT_MEMBER")
    participants = expense_in.participant_ids or [s.user_id for s in expense_in.splits]
    for uid in participants:
        if uid not in member_ids:
            raise invalid("Everyone sharing the expense must be a member of the group.", "PARTICIPANT_NOT_MEMBER")
    return calculate_splits(expense_in)


def _write_splits(db: Session, expense: Expense, expense_in: ExpenseBase, shares) -> None:
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


def create_expense(db: Session, expense_in: ExpenseCreate, actor: User, *, commit: bool = True) -> Expense:
    member_ids = require_member(db, expense_in.group_id, actor.id)
    shares = _validated_shares(expense_in, member_ids)
    lock_group(db, expense_in.group_id)

    expense = Expense(
        group_id=expense_in.group_id,
        description=expense_in.description,
        total_amount=expense_in.total_amount,
        split_type=expense_in.split_type,
        paid_by=expense_in.paid_by,
    )
    db.add(expense)
    db.flush()
    _write_splits(db, expense, expense_in, shares)
    db.flush()

    refresh_suggestions_if_present(db, expense_in.group_id)
    invalidate_group_after_commit(db, expense_in.group_id)
    if commit:
        db.commit()
        db.refresh(expense)
    return expense


# Kept for callers that still use the old name.
create_expense_record = create_expense


def get_expense_or_404(db: Session, expense_id: UUID, actor: User) -> Expense:
    expense = (
        db.query(Expense).options(selectinload(Expense.splits)).filter(Expense.id == expense_id).first()
    )
    if expense is None:
        raise not_found("Expense", "EXPENSE_NOT_FOUND")
    require_member(db, expense.group_id, actor.id)  # non-members get the same 404 as a missing id
    return expense


def update_expense(db: Session, expense_id: UUID, expense_in: ExpenseUpdate, actor: User) -> Expense:
    """Replace an expense's fields and recompute every share, atomically."""
    expense = get_expense_or_404(db, expense_id, actor)
    member_ids = require_member(db, expense.group_id, actor.id)
    shares = _validated_shares(expense_in, member_ids)
    lock_group(db, expense.group_id)

    expense.description = expense_in.description
    expense.total_amount = expense_in.total_amount
    expense.split_type = expense_in.split_type
    expense.paid_by = expense_in.paid_by

    for old in list(expense.splits):
        db.delete(old)
    db.flush()  # remove old rows first: (expense_id, user_id) is UNIQUE
    _write_splits(db, expense, expense_in, shares)
    db.flush()

    refresh_suggestions_if_present(db, expense.group_id)
    invalidate_group_after_commit(db, expense.group_id)
    db.commit()
    db.refresh(expense)
    return expense


def delete_expense(db: Session, expense_id: UUID, actor: User) -> UUID:
    expense = get_expense_or_404(db, expense_id, actor)
    group_id = expense.group_id
    lock_group(db, group_id)
    db.delete(expense)  # splits go with it (ORM cascade + ON DELETE CASCADE)
    db.flush()
    refresh_suggestions_if_present(db, group_id)
    invalidate_group_after_commit(db, group_id)
    db.commit()
    return group_id


def list_group_expenses(db: Session, group_id: UUID, actor: User) -> list[Expense]:
    require_member(db, group_id, actor.id)
    return (
        db.query(Expense)
        .options(selectinload(Expense.splits))
        .filter(Expense.group_id == group_id)
        .order_by(Expense.created_at.desc(), Expense.id)
        .all()
    )


def serialize_expenses(db: Session, expenses: list[Expense]) -> list[ExpenseOut]:
    """Attach display names (resolved from users, not membership, so history stays readable)."""
    ids: set[UUID] = set()
    for e in expenses:
        ids.add(e.paid_by)
        ids.update(s.user_id for s in e.splits)
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    out: list[ExpenseOut] = []
    for e in expenses:
        out.append(
            ExpenseOut(
                id=e.id,
                group_id=e.group_id,
                description=e.description,
                total_amount=e.total_amount,
                split_type=e.split_type,
                paid_by=e.paid_by,
                paid_by_name=names.get(e.paid_by),
                created_at=e.created_at,
                updated_at=e.updated_at,
                splits=[
                    ExpenseSplitOut(
                        user_id=s.user_id, user_name=names.get(s.user_id), amount=s.amount, percentage=s.percentage
                    )
                    for s in e.splits
                ],
            )
        )
    return out
