import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import cache_delete, cache_get_json, cache_set_json, group_summary_cache_key
from app.core.deps import get_current_user, get_db
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.user import User
from app.schemas.group import AddMemberRequest, BalanceEntry, GroupCreate, GroupDetailOut, GroupMemberOut, GroupOut
from app.schemas.user import UserOut
from app.services.settlement_service import compute_net_balances

router = APIRouter(prefix="/groups", tags=["groups"])


def _require_membership(db: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
    is_member = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        .first()
    )
    if is_member is None:
        # 404, not 403 — don't reveal that a group exists to non-members.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found.")


@router.post("", response_model=GroupOut, status_code=201)
def create_group(
    group_in: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Group:
    group = Group(name=group_in.name, created_by=current_user.id)
    db.add(group)
    db.flush()  # get group.id before inserting members

    db.add(GroupMember(group_id=group.id, user_id=current_user.id))

    for email in group_in.member_emails:
        member = db.query(User).filter(User.email == email).first()
        if member is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user found with email {email}.")
        if member.id == current_user.id:
            continue
        db.add(GroupMember(group_id=group.id, user_id=member.id))

    db.commit()
    db.refresh(group)
    return group


@router.get("", response_model=list[GroupOut])
def list_my_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Group]:
    return (
        db.query(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .filter(GroupMember.user_id == current_user.id)
        .order_by(Group.created_at.desc())
        .all()
    )


@router.get("/{group_id}", response_model=GroupDetailOut)
def get_group(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupDetailOut:
    _require_membership(db, group_id, current_user.id)

    group = db.query(Group).filter(Group.id == group_id).first()
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found.")

    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()

    cache_key = group_summary_cache_key(str(group_id))
    cached_balances = cache_get_json(cache_key)

    if cached_balances is not None:
        balances_by_user = {k: Decimal(v) for k, v in cached_balances.items()}
    else:
        expenses = db.query(Expense).filter(Expense.group_id == group_id).all()
        splits_by_expense: dict[uuid.UUID, list[dict]] = {}
        for e in expenses:
            splits = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == e.id).all()
            splits_by_expense[e.id] = [{"user_id": s.user_id, "amount": s.amount} for s in splits]

        balances_by_user = compute_net_balances(
            [{"id": e.id, "paid_by": e.paid_by, "total_amount": e.total_amount} for e in expenses],
            splits_by_expense,
        )
        cache_set_json(cache_key, {str(k): str(v) for k, v in balances_by_user.items()})

    user_by_id = {m.user_id: m.user for m in members}
    balances = [
        BalanceEntry(user=UserOut.model_validate(user_by_id[uid]), net_balance=str(bal))
        for uid, bal in balances_by_user.items()
        if uid in user_by_id
    ]

    return GroupDetailOut(
        id=group.id,
        name=group.name,
        created_by=group.created_by,
        created_at=group.created_at,
        members=[GroupMemberOut(user=UserOut.model_validate(m.user), joined_at=m.joined_at) for m in members],
        balances=balances,
    )


@router.post("/{group_id}/members", response_model=GroupMemberOut, status_code=201)
def add_member(
    group_id: uuid.UUID,
    body: AddMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupMemberOut:
    _require_membership(db, group_id, current_user.id)

    user_to_add = db.query(User).filter(User.email == body.email).first()
    if user_to_add is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user found with email {body.email}.")

    already_member = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_to_add.id)
        .first()
    )
    if already_member is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member of this group.")

    membership = GroupMember(group_id=group_id, user_id=user_to_add.id)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return GroupMemberOut(user=UserOut.model_validate(user_to_add), joined_at=membership.joined_at)


@router.delete("/{group_id}/members/{user_id}", status_code=204)
def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _require_membership(db, group_id, current_user.id)

    membership = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        .first()
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found.")

    db.delete(membership)
    db.commit()
    cache_delete(group_summary_cache_key(str(group_id)))
