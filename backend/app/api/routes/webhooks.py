from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.services.payment_service import get_payment_provider, process_webhook_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/payment", status_code=200)
async def payment_webhook(
    request: Request,
    x_webhook_signature: str = Header(..., alias="X-Webhook-Signature"),
    db: Session = Depends(get_db),
):
    """
    The single entrypoint through which a payment is EVER marked successful.
    The frontend calling /payments/{id}/simulate does not itself change any
    state — it just causes this endpoint to be called, exactly as a real
    gateway's webhook call would. This route:

    1. Verifies the signature over the raw body (never trust an unsigned
       payload — anyone could POST here otherwise).
    2. Delegates to process_webhook_event, which is itself idempotent via
       the webhook_events.provider_event_id UNIQUE constraint, so retried
       or duplicate-delivered webhooks are safe.
    """
    raw_body = await request.body()

    provider = get_payment_provider()
    if not provider.verify_webhook_signature(raw_body, x_webhook_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature.")

    payload = await request.json()
    required = ("event_id", "event_type", "gateway_order_id", "gateway_payment_id")
    if not all(k in payload for k in required):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Payload must include {required}.")

    result = process_webhook_event(
        db,
        event_id=payload["event_id"],
        event_type=payload["event_type"],
        gateway_order_id=payload["gateway_order_id"],
        gateway_payment_id=payload["gateway_payment_id"],
        raw_payload=payload,
    )
    return result
