import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.errors import forbidden, not_found
from app.models.group import Group
from app.models.payment import Payment
from app.models.settlement import Settlement
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentOut, TransactionOut
from app.services.payment_service import create_payment, get_payment_status, process_webhook_event

router = APIRouter(prefix="/payments", tags=["payments"])


def _party(settlement: Settlement | None, user: User) -> bool:
    return settlement is not None and user.id in (settlement.from_user, settlement.to_user)


def _tx_from_payment(db: Session, payment: Payment, settlement: Settlement) -> TransactionOut:
    group = db.query(Group).filter(Group.id == settlement.group_id).first()
    return TransactionOut(
        id=payment.id,
        settlement_id=settlement.id,
        from_user_name=settlement.debtor.name,
        to_user_name=settlement.creditor.name,
        amount=payment.amount,
        status=payment.status,
        method="UPI",
        group_id=settlement.group_id,
        group_name=group.name if group else None,
        gateway_order_id=payment.gateway_order_id,
        gateway_payment_id=payment.gateway_payment_id,
        created_at=payment.created_at,
    )


def _tx_from_manual(db: Session, settlement: Settlement) -> TransactionOut:
    group = db.query(Group).filter(Group.id == settlement.group_id).first()
    return TransactionOut(
        id=settlement.id,
        settlement_id=settlement.id,
        from_user_name=settlement.debtor.name,
        to_user_name=settlement.creditor.name,
        amount=settlement.amount,
        status=settlement.status,
        method="MANUAL",
        group_id=settlement.group_id,
        group_name=group.name if group else None,
        created_at=settlement.created_at,
    )


@router.post("/create", response_model=PaymentOut, status_code=201)
def create_payment_route(
    body: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settlement = db.query(Settlement).filter(Settlement.id == body.settlement_id).first()
    if settlement is None or current_user.id not in (settlement.from_user, settlement.to_user):
        raise not_found("Settlement", "SETTLEMENT_NOT_FOUND")

    # Only the debtor (the person who owes money) can pay it.
    if settlement.from_user != current_user.id:
        raise forbidden("Only the debtor can initiate this payment.", "NOT_THE_DEBTOR")

    return create_payment(db, body.settlement_id, idempotency_key)


@router.get("", response_model=list[PaymentOut])
def list_my_payments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Every payment where the current user is the payer or payee."""
    return (
        db.query(Payment)
        .join(Settlement, Settlement.id == Payment.settlement_id)
        .filter((Settlement.from_user == current_user.id) | (Settlement.to_user == current_user.id))
        .order_by(Payment.created_at.desc())
        .all()
    )


@router.get("/transactions/list", response_model=list[TransactionOut])
def list_my_transactions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Money-movement history for the Transactions page: UPI payments AND
    settlements recorded manually, newest first, with names resolved so the
    frontend can render "Anwita -> Anwi" without extra round trips.
    """
    payment_rows = (
        db.query(Payment, Settlement)
        .join(Settlement, Settlement.id == Payment.settlement_id)
        .filter((Settlement.from_user == current_user.id) | (Settlement.to_user == current_user.id))
        .all()
    )
    manual_rows = (
        db.query(Settlement)
        .filter(
            Settlement.method == "MANUAL",
            Settlement.status == "COMPLETED",
            (Settlement.from_user == current_user.id) | (Settlement.to_user == current_user.id),
        )
        .all()
    )
    results = [_tx_from_payment(db, p, s) for p, s in payment_rows] + [_tx_from_manual(db, s) for s in manual_rows]
    results.sort(key=lambda t: t.created_at, reverse=True)
    return results


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction_detail(
    transaction_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = get_payment_status(db, transaction_id)
    if payment is not None:
        settlement = db.query(Settlement).filter(Settlement.id == payment.settlement_id).first()
        if _party(settlement, current_user):
            return _tx_from_payment(db, payment, settlement)
        raise not_found("Transaction", "TRANSACTION_NOT_FOUND")

    settlement = db.query(Settlement).filter(Settlement.id == transaction_id, Settlement.method == "MANUAL").first()
    if _party(settlement, current_user):
        return _tx_from_manual(db, settlement)
    raise not_found("Transaction", "TRANSACTION_NOT_FOUND")


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = get_payment_status(db, payment_id)
    if payment is None:
        raise not_found("Payment", "PAYMENT_NOT_FOUND")
    settlement = db.query(Settlement).filter(Settlement.id == payment.settlement_id).first()
    if not _party(settlement, current_user):
        raise not_found("Payment", "PAYMENT_NOT_FOUND")
    return payment


@router.post("/{payment_id}/simulate", response_model=PaymentOut)
def simulate_payment_completion(
    payment_id: uuid.UUID,
    outcome: str = "success",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    TEST-ONLY endpoint, gated by PAYMENT_SANDBOX_MODE. Plays the role of "the
    user completed the UPI payment in their app" by routing a synthetic event
    through the REAL webhook handler, so the flow is identical to production.

    Only the payer (the debtor) may simulate their own payment: without this
    check any logged-in user could mark someone else's payment as paid.
    """
    if not settings.PAYMENT_SANDBOX_MODE:
        raise forbidden("Sandbox simulation is disabled.", "SANDBOX_DISABLED")

    payment = get_payment_status(db, payment_id)
    settlement = (
        db.query(Settlement).filter(Settlement.id == payment.settlement_id).first() if payment is not None else None
    )
    if payment is None or settlement is None or settlement.from_user != current_user.id:
        raise not_found("Payment", "PAYMENT_NOT_FOUND")

    event_type = "payment.success" if outcome == "success" else "payment.failed"
    process_webhook_event(
        db,
        event_id=f"sim_{uuid.uuid4().hex}",
        event_type=event_type,
        gateway_order_id=payment.gateway_order_id,
        gateway_payment_id=f"sandbox_pay_{uuid.uuid4().hex[:16]}",
        raw_payload={"simulated": True, "outcome": outcome},
    )

    db.refresh(payment)
    return payment
