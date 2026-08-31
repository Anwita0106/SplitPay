import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.settlement import Settlement
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentOut, TransactionOut
from app.services.payment_service import create_payment, get_payment_status, process_webhook_event

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create", response_model=PaymentOut, status_code=201)
def create_payment_route(
    body: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settlement = db.query(Settlement).filter(Settlement.id == body.settlement_id).first()
    if settlement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Settlement not found.")

    # Only the debtor (the person who owes money) can pay it.
    if settlement.from_user != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the debtor can initiate this payment.")

    return create_payment(db, body.settlement_id, idempotency_key)


@router.get("", response_model=list[PaymentOut])
def list_my_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transaction history: every payment where the current user is the payer or payee."""
    from app.models.payment import Payment  # local import keeps module-level imports tidy

    return (
        db.query(Payment)
        .join(Settlement, Settlement.id == Payment.settlement_id)
        .filter((Settlement.from_user == current_user.id) | (Settlement.to_user == current_user.id))
        .order_by(Payment.created_at.desc())
        .all()
    )


@router.get("/transactions/list", response_model=list[TransactionOut])
def list_my_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enriched transaction history for the Transactions page: same underlying
    payments as GET /payments, but with the counterparty's name resolved so
    the frontend can render "Rahul -> Anwita" without an extra round trip
    per row.
    """
    from app.models.payment import Payment  # local import keeps module-level imports tidy

    rows = (
        db.query(Payment, Settlement)
        .join(Settlement, Settlement.id == Payment.settlement_id)
        .filter((Settlement.from_user == current_user.id) | (Settlement.to_user == current_user.id))
        .order_by(Payment.created_at.desc())
        .all()
    )

    results = []
    for payment, settlement in rows:
        results.append(
            TransactionOut(
                id=payment.id,
                settlement_id=settlement.id,
                from_user_name=settlement.debtor.name,
                to_user_name=settlement.creditor.name,
                amount=payment.amount,
                status=payment.status,
                gateway_order_id=payment.gateway_order_id,
                gateway_payment_id=payment.gateway_payment_id,
                created_at=payment.created_at,
            )
        )
    return results


@router.get("/transactions/{payment_id}", response_model=TransactionOut)
def get_transaction_detail(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = get_payment_status(db, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found.")

    settlement = db.query(Settlement).filter(Settlement.id == payment.settlement_id).first()
    is_party = settlement is not None and current_user.id in (settlement.from_user, settlement.to_user)
    if not is_party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found.")

    return TransactionOut(
        id=payment.id,
        settlement_id=settlement.id,
        from_user_name=settlement.debtor.name,
        to_user_name=settlement.creditor.name,
        amount=payment.amount,
        status=payment.status,
        gateway_order_id=payment.gateway_order_id,
        gateway_payment_id=payment.gateway_payment_id,
        created_at=payment.created_at,
    )


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = get_payment_status(db, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found.")

    settlement = db.query(Settlement).filter(Settlement.id == payment.settlement_id).first()
    is_party = settlement is not None and current_user.id in (settlement.from_user, settlement.to_user)
    if not is_party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found.")

    return payment


@router.post("/{payment_id}/simulate", response_model=PaymentOut)
def simulate_payment_completion(
    payment_id: uuid.UUID,
    outcome: str = "success",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    TEST-ONLY endpoint, gated by PAYMENT_SANDBOX_MODE. Plays the role of
    "the user completed the UPI payment in their app", by constructing the
    exact same webhook payload + signature a real gateway would send, and
    routing it through the real webhook handler. This is what lets the
    project demonstrate the complete payment -> webhook -> settlement
    lifecycle without a real payment gateway account. See
    app/services/payment_service.py for the full design rationale.

    IMPORTANT: this endpoint's *result* is never trusted directly — it
    only triggers process_webhook_event(), the same function a real
    inbound webhook call would go through, so the flow you're testing is
    identical to production regardless of where the event came from.
    """
    if not settings.PAYMENT_SANDBOX_MODE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sandbox simulation is disabled.")

    payment = get_payment_status(db, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found.")

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
