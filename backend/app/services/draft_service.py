"""
DraftService — the confirmation gate for every AI-initiated financial write.

    AI prepares  ->  a PENDING `ai_actions` row (server-built, validated payload)
    user clicks Confirm  ->  POST /ai/drafts/{id}/confirm
        -> re-validate against CURRENT data  -> deterministic service performs the write
        -> the draft is marked CONFIRMED in the SAME transaction

The confirm endpoint accepts only a draft id. It executes the payload the
BACKEND stored — never anything the client (or the model) sends at confirmation
time — so a modified/forged request cannot change what gets written, and the
LLM has no tool that can confirm anything.

Confirming twice returns the first result (no duplicate expense / settlement).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import DomainError, conflict, invalid, not_found
from app.models.ai_action import AiAction
from app.models.group import Group
from app.models.settlement import Settlement
from app.models.user import User
from app.schemas.agent import (
    AiActionOut,
    DraftCancelOut,
    DraftConfirmOut,
    ExpenseDraft,
    ExpenseDraftParticipant,
    SettlementDraft,
)
from app.schemas.expense import ExpenseCreate
from app.services import expense_service, settlement_service
from app.services.balance_service import format_inr
from app.services.expense_service import _validated_shares
from app.services.group_service import require_member
from app.services.split_service import calculate_splits


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Prepare (no domain writes — only the draft row itself)
# ---------------------------------------------------------------------------
def prepare_expense_draft(
    db: Session,
    user: User,
    *,
    group: Group,
    description: str,
    total_amount: Decimal,
    payer: User,
    participants: list[User],
    assumptions: Optional[list[str]] = None,
) -> ExpenseDraft:
    expense = ExpenseCreate(
        group_id=group.id,
        description=description,
        total_amount=total_amount,
        split_type="EQUAL",
        paid_by=payer.id,
        participant_ids=[p.id for p in participants],
    )
    member_ids = require_member(db, group.id, user.id)
    _validated_shares(expense, member_ids)  # membership + Decimal split, raises on any problem
    shares = calculate_splits(expense)

    expires_at = _now() + timedelta(minutes=settings.AI_DRAFT_TTL_MINUTES)
    parts = [ExpenseDraftParticipant(user_id=p.id, name=p.name, amount=shares[p.id]) for p in participants]
    draft = AiAction(
        user_id=user.id,
        group_id=group.id,
        kind="EXPENSE",
        status="PENDING",
        expires_at=expires_at,
        payload={
            "expense": expense.model_dump(mode="json"),
            "group_name": group.name,
            "paid_by_name": payer.name,
            "participants": [p.model_dump(mode="json") for p in parts],
            "assumptions": assumptions or [],
        },
    )
    db.add(draft)
    db.commit()
    return ExpenseDraft(
        draft_id=draft.id,
        expires_at=expires_at,
        expense=expense,
        group_name=group.name,
        paid_by_name=payer.name,
        participants=parts,
        assumptions=assumptions or [],
    )


def prepare_settlement_draft(
    db: Session,
    user: User,
    *,
    group: Group,
    from_user: User,
    to_user: User,
    amount: Decimal,
) -> SettlementDraft:
    # Same gate a real settlement passes — a draft for an impossible settlement is never created.
    amount = settlement_service.validate_settlement(
        db, group_id=group.id, from_user=from_user.id, to_user=to_user.id, amount=amount
    )
    if user.id not in (from_user.id, to_user.id):
        raise invalid("You can only settle a balance that involves you.", "NOT_A_PARTY")

    expires_at = _now() + timedelta(minutes=settings.AI_DRAFT_TTL_MINUTES)
    draft = AiAction(
        user_id=user.id,
        group_id=group.id,
        kind="SETTLEMENT",
        status="PENDING",
        expires_at=expires_at,
        payload={
            "group_id": str(group.id),
            "group_name": group.name,
            "from_user": str(from_user.id),
            "from_name": from_user.name,
            "to_user": str(to_user.id),
            "to_name": to_user.name,
            "amount": str(amount),
        },
    )
    db.add(draft)
    db.commit()
    return SettlementDraft(
        draft_id=draft.id,
        expires_at=expires_at,
        group_id=group.id,
        group_name=group.name,
        from_user=from_user.id,
        from_name=from_user.name,
        to_user=to_user.id,
        to_name=to_user.name,
        amount=amount,
    )


# ---------------------------------------------------------------------------
# Confirm / cancel
# ---------------------------------------------------------------------------
def _load_own_draft(db: Session, user: User, draft_id: UUID, *, lock: bool) -> AiAction:
    q = db.query(AiAction).filter(AiAction.id == draft_id, AiAction.user_id == user.id)
    if lock:
        q = q.with_for_update()
    draft = q.first()
    if draft is None:
        raise not_found("Draft", "DRAFT_NOT_FOUND")  # someone else's draft looks identical to a missing one
    return draft


def _result_for(db: Session, draft: AiAction, *, already: bool) -> DraftConfirmOut:
    from app.api.routes.settlements import serialize_settlements

    if draft.kind == "EXPENSE":
        from app.models.expense import Expense
        from sqlalchemy.orm import selectinload

        expense = (
            db.query(Expense).options(selectinload(Expense.splits)).filter(Expense.id == draft.result_id).first()
        )
        out = expense_service.serialize_expenses(db, [expense])[0] if expense else None
        p = draft.payload
        return DraftConfirmOut(
            draft_id=draft.id,
            kind="EXPENSE",
            status=draft.status,
            already_confirmed=already,
            message=f"Expense saved: {p['expense']['description']} for {format_inr(Decimal(p['expense']['total_amount']))} in {p['group_name']}.",
            expense=out,
        )
    settlement = db.query(Settlement).filter(Settlement.id == draft.result_id).first()
    out = serialize_settlements(db, [settlement])[0] if settlement else None
    p = draft.payload
    return DraftConfirmOut(
        draft_id=draft.id,
        kind="SETTLEMENT",
        status=draft.status,
        already_confirmed=already,
        message=f"Settlement recorded: {p['from_name']} paid {p['to_name']} {format_inr(Decimal(p['amount']))} in {p['group_name']}.",
        settlement=out,
    )


def confirm_draft(db: Session, user: User, draft_id: UUID) -> DraftConfirmOut:
    draft = _load_own_draft(db, user, draft_id, lock=True)

    if draft.status == "CONFIRMED":
        return _result_for(db, draft, already=True)  # idempotent: never a second write
    if draft.status in ("CANCELLED", "FAILED"):
        raise conflict(f"This draft was {draft.status.lower()} and can't be confirmed.", "DRAFT_NOT_PENDING")
    if _aware(draft.expires_at) < _now():
        draft.status = "EXPIRED"
        draft.resolved_at = _now()
        db.commit()
        raise conflict("This draft expired. Please ask again to get a fresh one.", "DRAFT_EXPIRED")

    try:
        if draft.kind == "EXPENSE":
            expense_in = ExpenseCreate.model_validate(draft.payload["expense"])
            result = expense_service.create_expense(db, expense_in, user, commit=False)
        else:
            p = draft.payload
            result = settlement_service.record_manual_settlement(
                db,
                group_id=UUID(p["group_id"]),
                actor=user,
                from_user=UUID(p["from_user"]),
                to_user=UUID(p["to_user"]),
                amount=Decimal(p["amount"]),
                idempotency_key=f"ai-draft:{draft.id}",
                commit=False,
            )
        draft.status = "CONFIRMED"
        draft.result_id = result.id
        draft.resolved_at = _now()
        db.commit()
    except DomainError as exc:
        # Data changed since the draft was prepared (member removed, balance already settled, ...).
        db.rollback()
        failed = db.query(AiAction).filter(AiAction.id == draft_id).first()
        if failed is not None and failed.status == "PENDING":
            failed.status = "FAILED"
            failed.error = str(exc.detail)
            failed.resolved_at = _now()
            db.commit()
        raise

    db.refresh(draft)
    return _result_for(db, draft, already=False)


def cancel_draft(db: Session, user: User, draft_id: UUID) -> DraftCancelOut:
    draft = _load_own_draft(db, user, draft_id, lock=True)
    if draft.status == "CONFIRMED":
        raise conflict("This draft was already confirmed, so it can't be cancelled.", "DRAFT_ALREADY_CONFIRMED")
    if draft.status == "PENDING":
        draft.status = "CANCELLED"
        draft.resolved_at = _now()
        db.commit()
    return DraftCancelOut(draft_id=draft.id, status=draft.status, message="Cancelled — nothing was changed.")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def _summary(draft: AiAction) -> str:
    p = draft.payload or {}
    if draft.kind == "EXPENSE":
        e = p.get("expense", {})
        return f"Expense “{e.get('description', '')}” · {format_inr(Decimal(e.get('total_amount', '0')))} · {p.get('group_name', '')}"
    return f"Settlement {p.get('from_name', '')} → {p.get('to_name', '')} · {format_inr(Decimal(p.get('amount', '0')))} · {p.get('group_name', '')}"


def list_actions(db: Session, user: User, limit: int = 30) -> list[AiActionOut]:
    rows = (
        db.query(AiAction).filter(AiAction.user_id == user.id).order_by(AiAction.created_at.desc()).limit(limit).all()
    )
    now = _now()
    out = []
    for r in rows:
        status = "EXPIRED" if r.status == "PENDING" and _aware(r.expires_at) < now else r.status
        out.append(
            AiActionOut(
                id=r.id, kind=r.kind, status=status, summary=_summary(r),
                created_at=r.created_at, resolved_at=r.resolved_at, error=r.error,
            )
        )
    return out
