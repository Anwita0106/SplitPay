"""
SettlementService

Pure algorithms live in balance_math.py (re-exported here so existing imports
keep working). This module adds the database-backed settlement lifecycle:

  suggestions  PENDING rows derived from balances ("who should pay whom").
               They are derived data: safe to delete/regenerate at any time.
  UPI payment  PENDING -> PROCESSING -> COMPLETED (via the signed webhook).
  MANUAL       a group member records that a debt was settled outside the app.
               Created directly as COMPLETED, in one transaction.

Every settlement — however it is created — is validated against the canonical
balances (balance_service). You can never settle more than is owed, settle a
person who owes nothing, settle between non-members, or settle the same money
twice (in-flight UPI payments are reserved, and the group row is locked so
concurrent requests are serialized).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cache import invalidate_group_after_commit
from app.core.errors import conflict, forbidden, invalid, not_found
from app.models.payment import Payment
from app.models.settlement import Settlement
from app.models.user import User
from app.schemas.expense import validate_money
from app.services.balance_math import compute_net_balances, simplify_settlements  # noqa: F401  (re-export)
from app.services.balance_service import format_inr, get_group_balances
from app.services.group_service import lock_group, member_ids_of

__all__ = [
    "compute_net_balances",
    "simplify_settlements",
    "coerce_amount",
    "validate_settlement",
    "record_manual_settlement",
    "regenerate_suggestions",
    "refresh_suggestions_if_present",
]


def coerce_amount(value) -> Decimal:
    """Parse and validate a positive money amount with at most 2 decimals."""
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise invalid("That isn't a valid amount.", "INVALID_AMOUNT")
    try:
        validate_money(amount, label="Amount")
    except ValueError as exc:
        raise invalid(str(exc), "INVALID_AMOUNT")
    if amount <= 0:
        raise invalid("Amount must be greater than zero.", "INVALID_AMOUNT")
    return amount


def _names(db: Session, ids: list[UUID]) -> dict[UUID, str]:
    return {u.id: u.name for u in db.query(User).filter(User.id.in_(ids)).all()}


def validate_settlement(
    db: Session,
    *,
    group_id: UUID,
    from_user: UUID,
    to_user: UUID,
    amount,
    exclude_settlement_id: Optional[UUID] = None,
) -> Decimal:
    """
    The single gate every settlement passes through. Returns the validated
    Decimal amount or raises a DomainError with a message a human can act on.
    """
    amount = coerce_amount(amount)
    members = member_ids_of(db, group_id)
    if not members:
        raise not_found("Group", "GROUP_NOT_FOUND")
    if from_user == to_user:
        raise invalid("The payer and the receiver must be different people.", "SAME_PARTY")
    for uid in (from_user, to_user):
        if uid not in members:
            raise invalid("Both people must be members of this group.", "NOT_A_MEMBER")

    # Decision read: PostgreSQL, never the cache; in-flight UPI payments are reserved.
    snapshot = get_group_balances(
        db, group_id, use_cache=False, include_in_flight=True, exclude_settlement_id=exclude_settlement_id
    )
    names = _names(db, [from_user, to_user])
    debt = -snapshot.position(from_user)
    credit = snapshot.position(to_user)
    if debt <= 0:
        raise invalid(f"{names[from_user]} doesn't currently owe anything in this group.", "NOTHING_OWED")
    if credit <= 0:
        raise invalid(f"{names[to_user]} isn't currently owed anything in this group.", "NOTHING_OWED")
    limit = min(debt, credit)
    if amount > limit:
        raise invalid(
            f"{names[from_user]} currently owes {names[to_user]} at most {format_inr(limit)}, "
            f"so {format_inr(amount)} is too much.",
            "EXCEEDS_OUTSTANDING",
        )
    return amount


def record_manual_settlement(
    db: Session,
    *,
    group_id: UUID,
    actor: User,
    from_user: UUID,
    to_user: UUID,
    amount,
    idempotency_key: Optional[str] = None,
    commit: bool = True,
) -> Settlement:
    """
    Record that `from_user` paid `to_user` `amount` outside SplitPay. Either
    party may record it (like Splitwise); a third party may not. The whole
    thing — validation, insert, suggestion refresh — is one transaction.
    Retrying with the same idempotency_key returns the original row.
    """
    if actor.id not in member_ids_of(db, group_id):
        raise not_found("Group", "GROUP_NOT_FOUND")
    if actor.id not in (from_user, to_user):
        raise forbidden("Only the payer or the receiver can record a settlement.", "NOT_A_PARTY")

    lock_group(db, group_id)

    if idempotency_key:
        existing = db.query(Settlement).filter(Settlement.idempotency_key == idempotency_key).first()
        if existing is not None:
            return _same_request_or_conflict(existing, group_id, from_user, to_user, amount)

    amount = validate_settlement(db, group_id=group_id, from_user=from_user, to_user=to_user, amount=amount)

    settlement = Settlement(
        group_id=group_id,
        from_user=from_user,
        to_user=to_user,
        amount=amount,
        status="COMPLETED",
        method="MANUAL",
        recorded_by=actor.id,
        idempotency_key=idempotency_key,
    )
    db.add(settlement)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent request with the same key won the race: return its row.
        db.rollback()
        winner = db.query(Settlement).filter(Settlement.idempotency_key == idempotency_key).first()
        if winner is not None:
            return _same_request_or_conflict(winner, group_id, from_user, to_user, amount)
        raise

    refresh_suggestions_if_present(db, group_id)
    invalidate_group_after_commit(db, group_id)
    if commit:
        db.commit()
        db.refresh(settlement)
    return settlement


def _same_request_or_conflict(existing: Settlement, group_id, from_user, to_user, amount) -> Settlement:
    if (
        existing.group_id != group_id
        or existing.from_user != from_user
        or existing.to_user != to_user
        or existing.amount != coerce_amount(amount)
    ):
        raise conflict("That idempotency key was already used for a different settlement.", "IDEMPOTENCY_KEY_REUSED")
    return existing


# ---------------------------------------------------------------------------
# Suggestions (derived data)
# ---------------------------------------------------------------------------
def _clear_stale_suggestions(db: Session, group_id: UUID) -> None:
    """
    Drop PENDING suggestions so they can be recomputed. A suggestion that
    already has a (failed) payment attempt can't be deleted — payments.settlement_id
    is ON DELETE RESTRICT, and that history matters — so it is CANCELLED instead.
    """
    pending = db.query(Settlement).filter(Settlement.group_id == group_id, Settlement.status == "PENDING").all()
    for s in pending:
        has_payment = db.query(Payment.id).filter(Payment.settlement_id == s.id).first() is not None
        if has_payment:
            s.status = "CANCELLED"
        else:
            db.delete(s)
    db.flush()


def regenerate_suggestions(db: Session, group_id: UUID) -> list[Settlement]:
    """Replace stale PENDING suggestions with a fresh simplification of what is STILL owed."""
    _clear_stale_suggestions(db, group_id)
    # include_in_flight: money already on its way must not be suggested a second time.
    snapshot = get_group_balances(db, group_id, use_cache=False, include_in_flight=True)
    created = [
        Settlement(group_id=group_id, from_user=d.from_user, to_user=d.to_user, amount=d.amount, status="PENDING", method="UPI")
        for d in snapshot.debts
    ]
    db.add_all(created)
    db.flush()
    return created


def refresh_suggestions_if_present(db: Session, group_id: UUID) -> None:
    """Keep suggestions honest after any balance change — only if the group uses them."""
    has_pending = (
        db.query(Settlement.id).filter(Settlement.group_id == group_id, Settlement.status == "PENDING").first()
    )
    if has_pending:
        regenerate_suggestions(db, group_id)
