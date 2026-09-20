"""
GroupService — every group / membership operation, UUID-first.

Group NAMES are display labels only. Two groups may share a name (e.g. two
"Goa Trip"s). Every operation here takes a group UUID; name-based lookup exists
only in `resolve_group`, which turns a human phrase into ONE group UUID (or
tells the caller it is ambiguous / missing) and is used by the AI layer.
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.cache import invalidate_group_after_commit
from app.core.errors import DomainError, conflict, forbidden, invalid, not_found
from app.models.ai_action import AiAction
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.payment import Payment
from app.models.settlement import Settlement
from app.models.user import User
from app.models.webhook_event import WebhookEvent
from app.services.balance_service import format_inr, get_group_balances

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Basic lookups
# ---------------------------------------------------------------------------
def normalize_text(value: str) -> str:
    """casefold, drop punctuation, collapse whitespace — for tolerant name matching."""
    return " ".join(re.sub(r"[^\w\s]", " ", (value or "").casefold()).split())


def clean_group_name(name: str) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise invalid("Group name cannot be blank.", "INVALID_GROUP_NAME")
    if len(cleaned) > 150:
        raise invalid("Group name is too long (max 150 characters).", "INVALID_GROUP_NAME")
    return cleaned


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def find_user_by_email(db: Session, email: str) -> Optional[User]:
    """Case-insensitive: 'Rahul@X.com' and 'rahul@x.com' are the same person."""
    return db.query(User).filter(func.lower(User.email) == normalize_email(email)).first()


def lock_group(db: Session, group_id: UUID) -> Optional[Group]:
    """
    Row-lock the group so concurrent balance-changing operations (record a
    settlement, edit an expense, ...) on the SAME group are serialized. This is
    what stops two simultaneous "settle ₹1200" requests from both passing the
    balance check. (No-op on SQLite, which serializes writers anyway.)
    """
    return db.query(Group).filter(Group.id == group_id).with_for_update().first()


def member_ids_of(db: Session, group_id: UUID) -> set[UUID]:
    return {r[0] for r in db.query(GroupMember.user_id).filter(GroupMember.group_id == group_id).all()}


def require_member(db: Session, group_id: UUID, user_id: UUID) -> set[UUID]:
    """
    Returns the group's member ids if `user_id` belongs to the group. A
    non-member gets 404 (not 403) so the existence of a group isn't leaked.
    """
    ids = member_ids_of(db, group_id)
    if user_id not in ids:
        raise not_found("Group", "GROUP_NOT_FOUND")
    return ids


def get_group_or_404(db: Session, group_id: UUID, user: User) -> Group:
    require_member(db, group_id, user.id)
    group = db.query(Group).filter(Group.id == group_id).first()
    if group is None:
        raise not_found("Group", "GROUP_NOT_FOUND")
    return group


def members_of(db: Session, group_id: UUID) -> list[User]:
    return (
        db.query(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .filter(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at, User.name)
        .all()
    )


def list_user_groups(db: Session, user: User) -> list[dict]:
    groups = (
        db.query(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .filter(GroupMember.user_id == user.id)
        .order_by(Group.created_at.desc())
        .all()
    )
    if not groups:
        return []
    ids = [g.id for g in groups]
    rows = (
        db.query(GroupMember.group_id, User.name)
        .join(User, User.id == GroupMember.user_id)
        .filter(GroupMember.group_id.in_(ids))
        .order_by(GroupMember.joined_at, User.name)
        .all()
    )
    names_by_group: dict[UUID, list[str]] = {}
    for gid, name in rows:
        names_by_group.setdefault(gid, []).append(name)
    return [
        {
            "id": g.id,
            "name": g.name,
            "created_by": g.created_by,
            "created_at": g.created_at,
            "member_count": len(names_by_group.get(g.id, [])),
            "member_names": names_by_group.get(g.id, []),
        }
        for g in groups
    ]


# ---------------------------------------------------------------------------
# Create / rename
# ---------------------------------------------------------------------------
def create_group(
    db: Session,
    creator: User,
    name: str,
    member_emails: list[str],
    allow_duplicate: bool = False,
) -> Group:
    name = clean_group_name(name)

    if not allow_duplicate:
        mine = list_user_groups(db, creator)
        same = [g for g in mine if normalize_text(g["name"]) == normalize_text(name)]
        if same:
            raise conflict(
                f"You already have a group named “{name}”. Create another one with the same name?",
                "DUPLICATE_GROUP_NAME",
                {"existing": [{"id": str(g["id"]), "name": g["name"], "member_count": g["member_count"], "created_at": g["created_at"].isoformat()} for g in same]},
            )

    # Normalise + dedupe emails; the creator is always a member already.
    wanted: dict[str, None] = {}
    for raw in member_emails:
        email = normalize_email(raw)
        if email and email != normalize_email(creator.email):
            wanted[email] = None

    members: list[User] = []
    missing: list[str] = []
    for email in wanted:
        user = find_user_by_email(db, email)
        (members if user else missing).append(user or email)  # type: ignore[arg-type]
    if missing:
        raise not_found_email(missing)

    try:
        group = Group(name=name, created_by=creator.id)
        db.add(group)
        db.flush()
        db.add(GroupMember(group_id=group.id, user_id=creator.id))
        for m in members:
            db.add(GroupMember(group_id=group.id, user_id=m.id))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise DomainError(500, "Could not create the group. Nothing was saved.", "CREATE_FAILED")
    db.refresh(group)
    return group


def not_found_email(missing: list[str]) -> DomainError:
    if len(missing) == 1:
        return DomainError(404, f"No user found with email {missing[0]}.", "USER_NOT_FOUND")
    return DomainError(404, f"No users found with emails: {', '.join(missing)}.", "USER_NOT_FOUND")


def rename_group(db: Session, group_id: UUID, actor: User, new_name: str) -> Group:
    group = get_group_or_404(db, group_id, actor)
    if group.created_by != actor.id:
        raise forbidden("Only the group creator can rename the group.", "NOT_GROUP_CREATOR")
    group.name = clean_group_name(new_name)
    db.commit()
    db.refresh(group)
    return group


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------
def add_member(db: Session, group_id: UUID, actor: User, email: str) -> tuple[User, GroupMember]:
    require_member(db, group_id, actor.id)
    user = find_user_by_email(db, email)
    if user is None:
        raise DomainError(404, f"No user found with email {email.strip()}.", "USER_NOT_FOUND")
    if user.id in member_ids_of(db, group_id):
        raise conflict(f"{user.name} is already a member of this group.", "ALREADY_MEMBER")
    membership = GroupMember(group_id=group_id, user_id=user.id)
    db.add(membership)
    invalidate_group_after_commit(db, group_id)
    db.commit()
    db.refresh(membership)
    return user, membership


def remove_member(db: Session, group_id: UUID, actor: User, user_id: UUID) -> None:
    """
    Rules (each protects the ledger):
      * only the creator can remove someone else; anyone can leave (remove themselves);
      * the creator can't be removed / can't leave — delete the group instead;
      * a member with an outstanding balance or a payment in flight can't go,
        otherwise their debt would silently vanish from every balance view.
    """
    require_member(db, group_id, actor.id)
    group = db.query(Group).filter(Group.id == group_id).first()
    membership = (
        db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id).first()
    )
    if membership is None:
        raise not_found("Membership", "MEMBERSHIP_NOT_FOUND")
    if user_id == group.created_by:
        raise conflict(
            "The group creator can't leave or be removed. Delete the group instead.", "CREATOR_CANNOT_LEAVE"
        )
    if actor.id != user_id and actor.id != group.created_by:
        raise forbidden("Only the group creator can remove other members.", "NOT_GROUP_CREATOR")

    lock_group(db, group_id)
    target = db.query(User).filter(User.id == user_id).first()
    snapshot = get_group_balances(db, group_id, use_cache=False)
    outstanding = snapshot.position(user_id)
    if outstanding != 0:
        verb = "is owed" if outstanding > 0 else "owes"
        raise conflict(
            f"{target.name} {verb} {format_inr(outstanding)} in this group. Settle up before removing them.",
            "MEMBER_HAS_BALANCE",
        )
    in_flight = (
        db.query(Settlement.id)
        .filter(
            Settlement.group_id == group_id,
            Settlement.status == "PROCESSING",
            (Settlement.from_user == user_id) | (Settlement.to_user == user_id),
        )
        .first()
    )
    if in_flight:
        raise conflict(f"{target.name} has a payment in progress. Wait for it to finish.", "PAYMENT_IN_PROGRESS")

    db.delete(membership)
    invalidate_group_after_commit(db, group_id)
    db.commit()


# ---------------------------------------------------------------------------
# Delete (transactional, explicit, FK-safe)
# ---------------------------------------------------------------------------
def delete_group(db: Session, group_id: UUID, actor: User) -> dict:
    """
    Permanently deletes ONE group (by UUID) and everything that belongs to it,
    in a single transaction, in foreign-key order:

        webhook_events.payment_id -> NULL   (audit rows kept; dedupe key survives)
        payments   -> settlements -> expense_splits -> expenses -> group_members -> group

    `payments.settlement_id` is ON DELETE RESTRICT, so payments must be removed
    before their settlements — relying on cascades alone would fail. Any error
    rolls the whole transaction back and nothing is deleted.
    """
    group = db.query(Group).filter(Group.id == group_id).with_for_update().first()
    if group is None or actor.id not in member_ids_of(db, group_id):
        raise not_found("Group", "GROUP_NOT_FOUND")
    if group.created_by != actor.id:
        raise forbidden(
            "Only the person who created this group can delete it. You can leave the group instead.",
            "NOT_GROUP_CREATOR",
        )
    in_flight = (
        db.query(Settlement.id).filter(Settlement.group_id == group_id, Settlement.status == "PROCESSING").first()
    )
    if in_flight:
        raise conflict(
            "A payment is in progress in this group. Wait for it to finish before deleting the group.",
            "PAYMENT_IN_PROGRESS",
        )

    name = group.name
    try:
        settlement_ids = select(Settlement.id).where(Settlement.group_id == group_id)
        expense_ids = select(Expense.id).where(Expense.group_id == group_id)
        payment_ids = select(Payment.id).where(Payment.settlement_id.in_(settlement_ids))

        counts = {
            "expenses": db.query(func.count(Expense.id)).filter(Expense.group_id == group_id).scalar() or 0,
            "settlements": db.query(func.count(Settlement.id)).filter(Settlement.group_id == group_id).scalar() or 0,
            "members": db.query(func.count(GroupMember.user_id)).filter(GroupMember.group_id == group_id).scalar() or 0,
        }

        db.query(WebhookEvent).filter(WebhookEvent.payment_id.in_(payment_ids)).update(
            {WebhookEvent.payment_id: None}, synchronize_session=False
        )
        counts["payments"] = (
            db.query(Payment).filter(Payment.settlement_id.in_(settlement_ids)).delete(synchronize_session=False)
        )
        db.query(Settlement).filter(Settlement.group_id == group_id).delete(synchronize_session=False)
        db.query(ExpenseSplit).filter(ExpenseSplit.expense_id.in_(expense_ids)).delete(synchronize_session=False)
        db.query(Expense).filter(Expense.group_id == group_id).delete(synchronize_session=False)

        # AI drafts: void anything still waiting, keep the rows as history.
        now = datetime.now(timezone.utc)
        db.query(AiAction).filter(AiAction.group_id == group_id, AiAction.status == "PENDING").update(
            {
                AiAction.status: "CANCELLED",
                AiAction.error: "The group was deleted.",
                AiAction.resolved_at: now,
            },
            synchronize_session=False,
        )
        db.query(AiAction).filter(AiAction.group_id == group_id).update(
            {AiAction.group_id: None}, synchronize_session=False
        )

        db.query(GroupMember).filter(GroupMember.group_id == group_id).delete(synchronize_session=False)
        db.query(Group).filter(Group.id == group_id).delete(synchronize_session=False)

        invalidate_group_after_commit(db, group_id)
        db.commit()
    except DomainError:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001 - anything unexpected must roll back and be reported
        db.rollback()
        logger.exception("delete_group failed for %s", group_id)
        raise DomainError(500, "Could not delete the group. Nothing was deleted.", "DELETE_FAILED")

    db.expire_all()
    return {"id": str(group_id), "name": name, "deleted": counts}


# ---------------------------------------------------------------------------
# Name -> UUID resolution (used by the AI; never used for writes by name)
# ---------------------------------------------------------------------------
@dataclass
class GroupChoice:
    id: UUID
    name: str
    member_names: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    expense_count: int = 0

    def label(self) -> str:
        bits = [self.name]
        if self.member_names:
            bits.append("members: " + ", ".join(self.member_names))
        if self.created_at:
            bits.append(f"created {self.created_at:%d %b %Y}")
        bits.append(f"{self.expense_count} expense{'s' if self.expense_count != 1 else ''}")
        return " · ".join(bits)


class GroupResolutionError(Exception):
    """Base for 'I could not pick exactly one group'. `choices` may help the user decide."""

    def __init__(self, message: str, choices: Optional[list[GroupChoice]] = None):
        super().__init__(message)
        self.message = message
        self.choices = choices or []


class NoGroups(GroupResolutionError):
    pass


class GroupNotFound(GroupResolutionError):
    pass


class AmbiguousGroup(GroupResolutionError):
    pass


def _choices(db: Session, groups: list[dict]) -> list[GroupChoice]:
    ids = [g["id"] for g in groups]
    counts = dict(
        db.query(Expense.group_id, func.count(Expense.id)).filter(Expense.group_id.in_(ids)).group_by(Expense.group_id).all()
    ) if ids else {}
    return [
        GroupChoice(
            id=g["id"],
            name=g["name"],
            member_names=g["member_names"],
            created_at=g["created_at"],
            expense_count=int(counts.get(g["id"], 0)),
        )
        for g in groups
    ]


def resolve_group(
    db: Session,
    user: User,
    *,
    group_id: Optional[str | UUID] = None,
    group_name: Optional[str] = None,
    context_group_id: Optional[UUID] = None,
) -> Group:
    """
    Resolve a reference to exactly one of the user's groups, or raise a typed
    GroupResolutionError that says precisely why not.

    Order of evidence:
      1. an explicit UUID (`group_id`)            -> exact membership lookup
         (a non-UUID string in that slot is treated as a NAME — small models
          often put the name there — instead of failing)
      2. a group name                              -> normalised exact match, then
         word-containment, then typo-tolerant match
      3. `context_group_id` (UI-supplied, unambiguous) or the user's only group

    If several groups match — including several groups with the IDENTICAL name —
    nothing is guessed: AmbiguousGroup carries enough detail (members, date,
    expense count) for the user to choose.
    """
    groups = list_user_groups(db, user)
    if not groups:
        raise NoGroups("You aren't a member of any group yet.")
    by_id = {g["id"]: g for g in groups}

    def to_group(gid: UUID) -> Group:
        return db.query(Group).filter(Group.id == gid).one()

    name_query = group_name
    if group_id:
        try:
            gid = UUID(str(group_id))
        except ValueError:
            name_query = name_query or str(group_id)
        else:
            if gid in by_id:
                return to_group(gid)
            raise GroupNotFound("I couldn't find that group among yours.", _choices(db, groups))

    if name_query and name_query.strip():
        needle = normalize_text(name_query)
        exact = [g for g in groups if normalize_text(g["name"]) == needle]
        if len(exact) == 1:
            return to_group(exact[0]["id"])
        if len(exact) > 1:
            # A group the UI explicitly selected is an unambiguous tie-break.
            if context_group_id and any(g["id"] == context_group_id for g in exact):
                return to_group(context_group_id)
            raise AmbiguousGroup(
                f"You have {len(exact)} groups named “{exact[0]['name']}”. Which one do you mean?",
                _choices(db, exact),
            )
        words = set(needle.split())
        partial = [
            g for g in groups
            if words and (words <= set(normalize_text(g["name"]).split()) or set(normalize_text(g["name"]).split()) <= words)
        ]
        if not partial and len(needle) >= 3:
            close = set(difflib.get_close_matches(needle, [normalize_text(g["name"]) for g in groups], n=5, cutoff=0.8))
            partial = [g for g in groups if normalize_text(g["name"]) in close]
        if len(partial) == 1:
            return to_group(partial[0]["id"])
        if len(partial) > 1:
            if context_group_id and any(g["id"] == context_group_id for g in partial):
                return to_group(context_group_id)
            raise AmbiguousGroup(
                f"More than one group matches “{name_query.strip()}”. Which one do you mean?",
                _choices(db, partial),
            )
        raise GroupNotFound(f"I couldn't find a group called “{name_query.strip()}”.", _choices(db, groups))

    if context_group_id and context_group_id in by_id:
        return to_group(context_group_id)
    if len(groups) == 1:
        return to_group(groups[0]["id"])
    raise AmbiguousGroup("Which group do you mean?", _choices(db, groups))
