import json

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

    1. Verify the HMAC signature over the RAW body (never trust an unsigned
       payload — anyone could POST here otherwise).
    2. Parse defensively (a validly-signed but malformed body is a 4xx, not a 500).
    3. Delegate to process_webhook_event: idempotent per event id, terminal-state
       safe, and race-safe (see its docstring).
    """
    raw_body = await request.body()

    provider = get_payment_provider()
    if not provider.verify_webhook_signature(raw_body, x_webhook_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature.")

    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook body is not valid JSON.")

    required = ("event_id", "event_type", "gateway_order_id", "gateway_payment_id")
    if not isinstance(payload, dict) or not all(isinstance(payload.get(k), str) and payload.get(k) for k in required):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Payload must be an object with string fields {required}."
        )

    return process_webhook_event(
        db,
        event_id=payload["event_id"],
        event_type=payload["event_type"],
        gateway_order_id=payload["gateway_order_id"],
        gateway_payment_id=payload["gateway_payment_id"],
        raw_payload=payload,
    )
