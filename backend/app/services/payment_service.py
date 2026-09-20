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

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cache import invalidate_group_after_commit
from app.core.config import settings
from app.core.errors import DomainError, conflict, not_found
from app.models.payment import Payment
from app.models.settlement import Settlement

logger = logging.getLogger(__name__)


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
        # Compare BYTES: hmac.compare_digest() raises TypeError for non-ASCII str,
        # which would turn a garbage signature header into a 500 instead of a 401.
        return hmac.compare_digest(expected.encode("utf-8"), (signature or "").encode("utf-8"))


def get_payment_provider() -> PaymentProvider:
    # Single swap point for going live with a real gateway — see module docstring.
    return SandboxPaymentProvider()


# ---------------------------------------------------------------------
# Payment creation (idempotent)
# ---------------------------------------------------------------------
TERMINAL_PAYMENT_STATES = ("SUCCESS", "FAILED", "CANCELLED")


def create_payment(db: Session, settlement_id: uuid.UUID, idempotency_key: str) -> Payment:
    """
    Idempotency contract:
    If a payment already exists for this idempotency_key AND it belongs to the
    same settlement, return it unchanged — this is what makes it safe for a
    flaky client (or a double-tapped "Pay Now") to retry the exact same request
    without ever double-charging. Reusing a key for a DIFFERENT settlement is a
    client bug and is rejected (409) rather than silently returning someone
    else's payment.

    The database UNIQUE constraint on payments.idempotency_key is the real
    enforcement point: even under concurrent requests only one INSERT wins.

    One live payment per settlement: while a payment is in flight the
    settlement is PROCESSING and a *different* key is rejected — otherwise two
    parallel gateway orders could both succeed and the debt would be paid twice.
    """
    from app.services.group_service import lock_group
    from app.services.settlement_service import validate_settlement

    existing = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
    if existing is not None:
        if existing.settlement_id != settlement_id:
            raise conflict("That Idempotency-Key was already used for a different payment.", "IDEMPOTENCY_KEY_REUSED")
        return existing

    settlement = db.query(Settlement).filter(Settlement.id == settlement_id).first()
    if settlement is None:
        raise not_found("Settlement", "SETTLEMENT_NOT_FOUND")

    lock_group(db, settlement.group_id)  # serialize with manual settlements on the same group
    db.refresh(settlement)

    if settlement.status == "COMPLETED":
        raise conflict("This settlement is already completed.", "SETTLEMENT_COMPLETED")
    if settlement.status == "CANCELLED":
        raise conflict("This settlement is no longer active. Recalculate settlements.", "SETTLEMENT_CANCELLED")
    if settlement.status == "PROCESSING":
        raise conflict("A payment for this settlement is already in progress.", "PAYMENT_IN_PROGRESS")

    # The suggestion may be stale (an expense changed, or the debt was settled another way).
    try:
        validate_settlement(
            db,
            group_id=settlement.group_id,
            from_user=settlement.from_user,
            to_user=settlement.to_user,
            amount=settlement.amount,
            exclude_settlement_id=settlement.id,
        )
    except DomainError as exc:
        raise conflict(
            f"This settlement is out of date: {exc.detail} Recalculate settlements and try again.",
            "SETTLEMENT_OUT_OF_DATE",
        )

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
    invalidate_group_after_commit(db, settlement.group_id)

    try:
        db.commit()
    except IntegrityError:
        # Unique violation on idempotency_key: a concurrent request beat us to it.
        db.rollback()
        winner = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
        if winner is not None and winner.settlement_id == settlement_id:
            return winner
        raise conflict("Could not create payment; please retry.", "PAYMENT_CREATE_CONFLICT")

    db.refresh(payment)
    return payment


def get_payment_status(db: Session, payment_id: uuid.UUID) -> Optional[Payment]:
    return db.query(Payment).filter(Payment.id == payment_id).first()


# ---------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------
KNOWN_EVENT_TYPES = ("payment.success", "payment.failed")


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
    function, reached through a signature-verified webhook, may move a payment
    to SUCCESS/FAILED and cascade that into the settlement.

    Deterministic state machine:
        PENDING --payment.success--> SUCCESS   (settlement -> COMPLETED)
        PENDING --payment.failed --> FAILED    (settlement -> PENDING, retry allowed)
        SUCCESS / FAILED / CANCELLED are TERMINAL. A late or out-of-order event
        (e.g. `failed` arriving after `success`) is recorded for audit and
        ignored — it must never re-open a settlement that was paid.

    Duplicate delivery: gateways redeliver until they get a 2xx.
    `webhook_events.provider_event_id` is UNIQUE. The fast path checks it first;
    if two identical deliveries race, the loser hits the UNIQUE constraint,
    rolls back, and is answered as a duplicate — never a 500, never a second
    financial effect.
    """
    from app.models.webhook_event import WebhookEvent  # local import avoids a circular import at module load

    if event_type not in KNOWN_EVENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown event_type {event_type}")

    existing_event = db.query(WebhookEvent).filter(WebhookEvent.provider_event_id == event_id).first()
    if existing_event is not None and existing_event.processed_at is not None:
        return {"status": "duplicate_ignored", "event_id": event_id}

    payment = (
        db.query(Payment).filter(Payment.gateway_order_id == gateway_order_id).with_for_update().first()
    )
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No payment found for this gateway_order_id.")

    event_row = existing_event or WebhookEvent(
        provider_event_id=event_id, payment_id=payment.id, raw_payload=raw_payload
    )
    if existing_event is None:
        db.add(event_row)

    settlement = db.query(Settlement).filter(Settlement.id == payment.settlement_id).first()
    result: dict

    if payment.status in TERMINAL_PAYMENT_STATES:
        result = {"status": "ignored", "reason": "payment_already_final", "payment_status": payment.status}
    elif event_type == "payment.success":
        payment.status = "SUCCESS"
        payment.gateway_payment_id = gateway_payment_id
        if settlement is not None:
            settlement.status = "COMPLETED"
            invalidate_group_after_commit(db, settlement.group_id)  # completed money changes balances
        result = {"status": "processed", "payment_status": payment.status}
    else:  # payment.failed
        payment.status = "FAILED"
        if settlement is not None and settlement.status == "PROCESSING":
            settlement.status = "PENDING"  # allow the user to retry payment
            invalidate_group_after_commit(db, settlement.group_id)
        result = {"status": "processed", "payment_status": payment.status}

    event_row.processed_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Concurrent duplicate webhook %s resolved as duplicate", event_id)
        return {"status": "duplicate_ignored", "event_id": event_id}

    return result
