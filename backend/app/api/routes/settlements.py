import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import not_found
from app.models.settlement import Settlement
from app.models.user import User
from app.schemas.settlement import SettlementDetailOut, SettlementOut, SettlementRecordRequest
from app.schemas.user import UserOut
from app.services import group_service, settlement_service

router = APIRouter(tags=["settlements"])


def serialize_settlements(db: Session, rows: list[Settlement]) -> list[SettlementOut]:
    ids = {r.from_user for r in rows} | {r.to_user for r in rows}
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    return [
        SettlementOut(
            id=r.id,
            group_id=r.group_id,
            from_user=r.from_user,
            to_user=r.to_user,
            from_name=names.get(r.from_user),
            to_name=names.get(r.to_user),
            amount=r.amount,
            status=r.status,
            method=r.method or "UPI",
            recorded_by=r.recorded_by,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def _history(db: Session, group_id: uuid.UUID) -> list[Settlement]:
    return (
        db.query(Settlement)
        .filter(Settlement.group_id == group_id, Settlement.status != "CANCELLED")  # cancelled = internal, never shown
        .order_by(Settlement.created_at.desc())
        .all()
    )


@router.post("/groups/{group_id}/settlements/generate", response_model=list[SettlementOut])
def generate_settlements(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recomputes what is STILL owed (completed and in-flight settlements are
    netted out) and replaces the not-yet-acted-on PENDING suggestions.
    COMPLETED / PROCESSING settlements are never touched.
    """
    group_service.require_member(db, group_id, current_user.id)
    group_service.lock_group(db, group_id)
    settlement_service.regenerate_suggestions(db, group_id)
    db.commit()
    return serialize_settlements(db, _history(db, group_id))


@router.post("/groups/{group_id}/settlements/record", response_model=SettlementOut, status_code=201)
def record_settlement(
    group_id: uuid.UUID,
    body: SettlementRecordRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record that a debt was settled outside the app (cash / direct UPI). Either party may record it."""
    settlement = settlement_service.record_manual_settlement(
        db,
        group_id=group_id,
        actor=current_user,
        from_user=body.from_user,
        to_user=body.to_user,
        amount=body.amount,
        idempotency_key=idempotency_key,
    )
    return serialize_settlements(db, [settlement])[0]


@router.get("/groups/{group_id}/settlements", response_model=list[SettlementOut])
def list_settlements(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group_service.require_member(db, group_id, current_user.id)
    return serialize_settlements(db, _history(db, group_id))


@router.get("/settlements/{settlement_id}", response_model=SettlementDetailOut)
def get_settlement(
    settlement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SettlementDetailOut:
    settlement = db.query(Settlement).filter(Settlement.id == settlement_id).first()
    if settlement is None:
        raise not_found("Settlement", "SETTLEMENT_NOT_FOUND")
    group_service.require_member(db, settlement.group_id, current_user.id)
    return SettlementDetailOut(
        id=settlement.id,
        group_id=settlement.group_id,
        debtor=UserOut.model_validate(settlement.debtor),
        creditor=UserOut.model_validate(settlement.creditor),
        amount=settlement.amount,
        status=settlement.status,
        method=settlement.method or "UPI",
        created_at=settlement.created_at,
    )
