import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.group_member import GroupMember
from app.models.settlement import Settlement
from app.models.user import User
from app.schemas.settlement import SettlementDetailOut, SettlementOut
from app.schemas.user import UserOut
from app.services.settlement_service import compute_net_balances, simplify_settlements

router = APIRouter(tags=["settlements"])


def _require_membership(db: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
    is_member = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        .first()
    )
    if is_member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found.")


@router.post("/groups/{group_id}/settlements/generate", response_model=list[SettlementOut])
def generate_settlements(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Settlement]:
    """
    Recomputes the group's net balances from scratch and replaces any
    still-PENDING settlement suggestions with a freshly simplified set.
    COMPLETED and PROCESSING settlements (payment already in flight or
    done) are left untouched — regenerating must never erase settlement
    history or double-count money that's already moved.
    """
    _require_membership(db, group_id, current_user.id)

    # Clear out stale, not-yet-acted-on suggestions before recomputing.
    db.query(Settlement).filter(Settlement.group_id == group_id, Settlement.status == "PENDING").delete()

    expenses = db.query(Expense).filter(Expense.group_id == group_id).all()
    splits_by_expense: dict[uuid.UUID, list[dict]] = {}
    for e in expenses:
        splits = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == e.id).all()
        splits_by_expense[e.id] = [{"user_id": s.user_id, "amount": s.amount} for s in splits]

    balances = compute_net_balances(
        [{"id": e.id, "paid_by": e.paid_by, "total_amount": e.total_amount} for e in expenses],
        splits_by_expense,
    )
    simplified = simplify_settlements(balances)

    new_settlements = [
        Settlement(
            group_id=group_id,
            from_user=s["from_user"],
            to_user=s["to_user"],
            amount=s["amount"],
            status="PENDING",
        )
        for s in simplified
    ]
    db.add_all(new_settlements)
    db.commit()
    for s in new_settlements:
        db.refresh(s)

    # Return the full current picture: newly generated PENDING + any settlements already in flight/done.
    return db.query(Settlement).filter(Settlement.group_id == group_id).order_by(Settlement.created_at.desc()).all()


@router.get("/groups/{group_id}/settlements", response_model=list[SettlementOut])
def list_settlements(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Settlement]:
    _require_membership(db, group_id, current_user.id)
    return (
        db.query(Settlement)
        .filter(Settlement.group_id == group_id)
        .order_by(Settlement.created_at.desc())
        .all()
    )


@router.get("/settlements/{settlement_id}", response_model=SettlementDetailOut)
def get_settlement(
    settlement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SettlementDetailOut:
    settlement = db.query(Settlement).filter(Settlement.id == settlement_id).first()
    if settlement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Settlement not found.")
    _require_membership(db, settlement.group_id, current_user.id)

    return SettlementDetailOut(
        id=settlement.id,
        group_id=settlement.group_id,
        debtor=UserOut.model_validate(settlement.debtor),
        creditor=UserOut.model_validate(settlement.creditor),
        amount=settlement.amount,
        status=settlement.status,
        created_at=settlement.created_at,
    )
