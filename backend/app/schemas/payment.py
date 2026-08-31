import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PaymentCreate(BaseModel):
    settlement_id: uuid.UUID


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    settlement_id: uuid.UUID
    amount: Decimal
    status: str
    gateway_order_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TransactionOut(BaseModel):
    """Enriched view of a payment for the transaction-history list/detail pages."""

    id: uuid.UUID
    settlement_id: uuid.UUID
    from_user_name: str
    to_user_name: str
    amount: Decimal
    status: str
    gateway_order_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None
    created_at: datetime


class WebhookPayload(BaseModel):
    """
    Shape of the payload sent to POST /webhooks/payment.
    Modeled on the common shape used by UPI/payment-gateway sandbox webhooks
    (e.g. Razorpay's payment.captured / payment.failed events): an event id
    for dedup, an event type, and the gateway's own order/payment ids.
    """

    event_id: str
    event_type: str  # "payment.success" | "payment.failed"
    gateway_order_id: str
    gateway_payment_id: str
