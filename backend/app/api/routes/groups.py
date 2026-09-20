import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.group import Group
from app.models.user import User
from app.schemas.group import (
    AddMemberRequest,
    BalanceEntry,
    DebtEntry,
    GroupCreate,
    GroupDeleteOut,
    GroupDetailOut,
    GroupMemberOut,
    GroupOut,
    GroupUpdate,
)
from app.schemas.user import UserOut
from app.services import group_service
from app.services.balance_service import get_group_balances
from app.models.group_member import GroupMember

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", response_model=GroupOut, status_code=201)
def create_group(
    group_in: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = group_service.create_group(
        db, current_user, group_in.name, group_in.member_emails, allow_duplicate=group_in.allow_duplicate
    )
    members = group_service.members_of(db, group.id)
    return {
        "id": group.id,
        "name": group.name,
        "created_by": group.created_by,
        "created_at": group.created_at,
        "member_count": len(members),
        "member_names": [m.name for m in members],
    }


@router.get("", response_model=list[GroupOut])
def list_my_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return group_service.list_user_groups(db, current_user)


@router.get("/{group_id}", response_model=GroupDetailOut)
def get_group(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupDetailOut:
    group = group_service.get_group_or_404(db, group_id, current_user)
    memberships = (
        db.query(GroupMember).filter(GroupMember.group_id == group_id).order_by(GroupMember.joined_at).all()
    )
    user_by_id = {m.user_id: m.user for m in memberships}

    # Display read: the cache is allowed here (and only here).
    snapshot = get_group_balances(db, group_id, use_cache=True)

    def out(uid):
        user = user_by_id.get(uid)
        return UserOut.model_validate(user) if user is not None else None

    return GroupDetailOut(
        id=group.id,
        name=group.name,
        created_by=group.created_by,
        created_at=group.created_at,
        members=[GroupMemberOut(user=UserOut.model_validate(m.user), joined_at=m.joined_at) for m in memberships],
        balances=[
            BalanceEntry(user=out(uid), net_balance=str(bal))
            for uid, bal in snapshot.balances.items()
            if uid in user_by_id
        ],
        debts=[
            DebtEntry(from_user=out(d.from_user), to_user=out(d.to_user), amount=str(d.amount))
            for d in snapshot.debts
            if d.from_user in user_by_id and d.to_user in user_by_id
        ],
    )


@router.patch("/{group_id}", response_model=GroupOut)
def rename_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = group_service.rename_group(db, group_id, current_user, body.name)
    members = group_service.members_of(db, group.id)
    return {
        "id": group.id,
        "name": group.name,
        "created_by": group.created_by,
        "created_at": group.created_at,
        "member_count": len(members),
        "member_names": [m.name for m in members],
    }


@router.delete("/{group_id}", response_model=GroupDeleteOut)
def delete_group(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently deletes this ONE group (by UUID) and its expenses, splits, settlements, payments and memberships — in one transaction."""
    return group_service.delete_group(db, group_id, current_user)


@router.post("/{group_id}/members", response_model=GroupMemberOut, status_code=201)
def add_member(
    group_id: uuid.UUID,
    body: AddMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroupMemberOut:
    user, membership = group_service.add_member(db, group_id, current_user, str(body.email))
    return GroupMemberOut(user=UserOut.model_validate(user), joined_at=membership.joined_at)


@router.delete("/{group_id}/members/{user_id}", status_code=204)
def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    group_service.remove_member(db, group_id, current_user, user_id)
