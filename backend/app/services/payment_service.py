"""
PaymentService

Design note on the payment provider (read this before the interview):
---------------------------------------------------------------------
This project deliberately does NOT call a real payment gateway's live API,
because doing so would require a real merchant account and real API
credentials that don't exist for a personal portfolio project, and
fabricating calls against a real provider's endpoints without verified
credentials would be dishonest about what's actually been tested.

Instead, `SandboxPaymentProvider` is a self-contained simulation of a UPI
payment gateway's *test-mode* behavior: it creates an "order", and a
test-only endpoint (`POST /payments/{id}/simulate`, gated behind
PAYMENT_SANDBOX_MODE=true) plays the role of "the user completed payment in
the UPI app", which triggers the exact same webhook path that a real
provider's test-mode webhook would hit. This exercises the FULL payment
lifecycle — order creation, idempotency, webhook signature verification,
webhook deduplication, and settlement status updates — end to end.

The `PaymentProvider` ABC is the swap point: to go live with a real
provider (e.g. Razorpay, which supports UPI in its own test/sandbox mode),
you would implement a `RazorpayProvider(PaymentProvider)` that calls their
real Orders API and verifies their real webhook signature scheme, add
RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET / RAZORPAY_WEBHOOK_SECRET to `.env`,
and change one line in `get_payment_provider()`. No other code changes.
"""

import hashlib
import hmac
import uuid
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import Payment
from app.models.settlement import Settlement


# ---------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------
class PaymentProvider(ABC):
    @abstractmethod
    def create_order(self, amount: Decimal, receipt: str) -> dict:
        """Returns {"gateway_order_id": str, "status": str}."""

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        """Verifies the webhook actually came from the provider."""


class SandboxPaymentProvider(PaymentProvider):
    """
    Simulated UPI gateway sandbox. See module docstring for the rationale.
    Signature scheme mirrors the common pattern real gateways use:
    HMAC-SHA256 of the raw request body, keyed by a shared webhook secret.
    """

    def create_order(self, amount: Decimal, receipt: str) -> dict:
        return {
            "gateway_order_id": f"sandbox_order_{uuid.uuid4().hex[:20]}",
            "status": "CREATED",
        }

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(
            settings.PAYMENT_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


def get_payment_provider() -> PaymentProvider:
    # Single swap point for going live with a real gateway — see module docstring.
    return SandboxPaymentProvider()


# ---------------------------------------------------------------------
# Payment creation (idempotent)
# ---------------------------------------------------------------------
def create_payment(db: Session, settlement_id: uuid.UUID, idempotency_key: str) -> Payment:
    """
    Idempotency contract:
    If a payment already exists for this idempotency_key, return it
    unchanged instead of creating a new one — this is what makes it safe
    for a flaky client (or a user double-tapping "Pay Now") to retry the
    exact same request without ever double-charging.

    The database's UNIQUE constraint on payments.idempotency_key is the
    real enforcement point: even under concurrent requests racing each
    other, only one INSERT can win. We catch that race below.
    """
    existing = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
    if existing is not None:
        return existing

    settlement = db.query(Settlement).filter(Settlement.id == settlement_id).first()
    if settlement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Settlement not found.")
    if settlement.status == "COMPLETED":
        raise HTTPException(status.HTTP_409_CONFLICT, "This settlement is already completed.")

    provider = get_payment_provider()
    order = provider.create_order(amount=settlement.amount, receipt=str(settlement.id))

    payment = Payment(
        settlement_id=settlement.id,
        amount=settlement.amount,
        gateway_order_id=order["gateway_order_id"],
        status="PENDING",
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    settlement.status = "PROCESSING"

    try:
        db.commit()
    except Exception:
        # Unique constraint violation on idempotency_key means a concurrent
        # request beat us to it — this is the race-safety net. Roll back
        # our attempt and return whichever row actually made it in.
        db.rollback()
        winner = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
        if winner is not None:
            return winner
        raise HTTPException(status.HTTP_409_CONFLICT, "Could not create payment; please retry.")

    db.refresh(payment)
    return payment


def get_payment_status(db: Session, payment_id: uuid.UUID) -> Optional[Payment]:
    return db.query(Payment).filter(Payment.id == payment_id).first()


# ---------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------
def process_webhook_event(
    db: Session,
    event_id: str,
    event_type: str,
    gateway_order_id: str,
    gateway_payment_id: str,
    raw_payload: dict,
) -> dict:
    """
    Contract: the frontend is NEVER trusted for payment success — only this
    function, triggered by a verified webhook call, is allowed to move a
    payment to SUCCESS/FAILED and cascade that into the settlement status.

    Duplicate delivery handling: real payment gateways retry webhooks until
    they get a 2xx response, so the SAME event can arrive more than once.
    `webhook_events.provider_event_id` has a UNIQUE constraint — we check
    for it first and short-circuit if this event_id was already processed,
    making the whole handler idempotent regardless of how many times the
    provider redelivers it.
    """
    from app.models.webhook_event import WebhookEvent  # local import avoids a circular import at module load

    existing_event = db.query(WebhookEvent).filter(WebhookEvent.provider_event_id == event_id).first()
    if existing_event is not None and existing_event.processed_at is not None:
        return {"status": "duplicate_ignored", "event_id": event_id}

    payment = db.query(Payment).filter(Payment.gateway_order_id == gateway_order_id).first()
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No payment found for this gateway_order_id.")

    from datetime import datetime, timezone

    event_row = existing_event or WebhookEvent(
        provider_event_id=event_id,
        payment_id=payment.id,
        raw_payload=raw_payload,
    )
    if existing_event is None:
        db.add(event_row)

    if event_type == "payment.success":
        payment.status = "SUCCESS"
        payment.gateway_payment_id = gateway_payment_id
        settlement = db.query(Settlement).filter(Settlement.id == payment.settlement_id).first()
        if settlement is not None:
            settlement.status = "COMPLETED"
    elif event_type == "payment.failed":
        payment.status = "FAILED"
        settlement = db.query(Settlement).filter(Settlement.id == payment.settlement_id).first()
        if settlement is not None:
            settlement.status = "PENDING"  # allow the user to retry payment
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown event_type {event_type}")

    event_row.processed_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "processed", "payment_status": payment.status}
