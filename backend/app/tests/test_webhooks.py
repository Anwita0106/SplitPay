import hashlib
import hmac
import json

from app.tests.conftest import register_and_login, unique_email

WEBHOOK_SECRET = "test-webhook-secret"  # matches conftest.py's PAYMENT_WEBHOOK_SECRET env default


def _sign(body_bytes: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256).hexdigest()


def _setup_payment(client):
    anwita = register_and_login(client, "Anwita", unique_email("anwita"))
    rahul = register_and_login(client, "Rahul", unique_email("rahul"))

    group = client.post(
        "/groups",
        json={"name": "Trip", "member_emails": [rahul["user"]["email"]]},
        headers=anwita["headers"],
    ).json()

    client.post(
        "/expenses",
        json={
            "group_id": group["id"],
            "description": "Dinner",
            "total_amount": "1000",
            "split_type": "EQUAL",
            "paid_by": anwita["user"]["id"],
            "participant_ids": [anwita["user"]["id"], rahul["user"]["id"]],
        },
        headers=anwita["headers"],
    )

    settlement = client.post(f"/groups/{group['id']}/settlements/generate", headers=anwita["headers"]).json()[0]

    payment = client.post(
        "/payments/create",
        json={"settlement_id": settlement["id"]},
        headers={**rahul["headers"], "Idempotency-Key": "webhook-test-key"},
    ).json()

    return {"anwita": anwita, "rahul": rahul, "settlement": settlement, "payment": payment}


def test_webhook_without_valid_signature_rejected(client):
    ctx = _setup_payment(client)
    payload = {
        "event_id": "evt_1",
        "event_type": "payment.success",
        "gateway_order_id": ctx["payment"]["gateway_order_id"],
        "gateway_payment_id": "pay_abc",
    }
    body = json.dumps(payload).encode()
    r = client.post(
        "/webhooks/payment",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": "invalid-signature"},
    )
    assert r.status_code == 401


def test_webhook_success_marks_payment_and_settlement(client):
    ctx = _setup_payment(client)
    payload = {
        "event_id": "evt_2",
        "event_type": "payment.success",
        "gateway_order_id": ctx["payment"]["gateway_order_id"],
        "gateway_payment_id": "pay_xyz",
    }
    body = json.dumps(payload).encode()
    r = client.post(
        "/webhooks/payment",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": _sign(body)},
    )
    assert r.status_code == 200
    assert r.json()["payment_status"] == "SUCCESS"

    payment = client.get(f"/payments/{ctx['payment']['id']}", headers=ctx["rahul"]["headers"]).json()
    assert payment["status"] == "SUCCESS"

    settlement = client.get(f"/settlements/{ctx['settlement']['id']}", headers=ctx["rahul"]["headers"]).json()
    assert settlement["status"] == "COMPLETED"


def test_duplicate_webhook_delivery_is_idempotent(client):
    ctx = _setup_payment(client)
    payload = {
        "event_id": "evt_dup",
        "event_type": "payment.success",
        "gateway_order_id": ctx["payment"]["gateway_order_id"],
        "gateway_payment_id": "pay_dup",
    }
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-Webhook-Signature": _sign(body)}

    r1 = client.post("/webhooks/payment", content=body, headers=headers)
    r2 = client.post("/webhooks/payment", content=body, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["status"] == "processed"
    assert r2.json()["status"] == "duplicate_ignored"


def test_webhook_failed_payment_reopens_settlement_for_retry(client):
    ctx = _setup_payment(client)
    payload = {
        "event_id": "evt_fail",
        "event_type": "payment.failed",
        "gateway_order_id": ctx["payment"]["gateway_order_id"],
        "gateway_payment_id": "pay_fail",
    }
    body = json.dumps(payload).encode()
    r = client.post(
        "/webhooks/payment",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": _sign(body)},
    )
    assert r.status_code == 200
    assert r.json()["payment_status"] == "FAILED"

    settlement = client.get(f"/settlements/{ctx['settlement']['id']}", headers=ctx["rahul"]["headers"]).json()
    assert settlement["status"] == "PENDING"


def test_sandbox_simulate_endpoint_drives_real_webhook_path(client):
    ctx = _setup_payment(client)
    r = client.post(
        f"/payments/{ctx['payment']['id']}/simulate?outcome=success",
        headers=ctx["rahul"]["headers"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUCCESS"

    settlement = client.get(f"/settlements/{ctx['settlement']['id']}", headers=ctx["rahul"]["headers"]).json()
    assert settlement["status"] == "COMPLETED"
