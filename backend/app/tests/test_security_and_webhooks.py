"""Authorization boundaries and payment/webhook hardening."""
import hashlib
import hmac
import json
import uuid

from app.tests.conftest import register_and_login, unique_email
from app.tests.test_groups import add_expense, create_group, mk
from app.tests.test_webhooks import WEBHOOK_SECRET, _setup_payment


def _post_webhook(client, payload):
    body = json.dumps(payload).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/payment", content=body, headers={"Content-Type": "application/json", "X-Webhook-Signature": sig})


def _evt(ctx, event_id, event_type):
    return {"event_id": event_id, "event_type": event_type, "gateway_order_id": ctx["payment"]["gateway_order_id"], "gateway_payment_id": "pay_1"}


# ---- auth -------------------------------------------------------------------
def test_every_protected_route_requires_a_token(client):
    fake = uuid.uuid4()
    calls = [
        ("get", "/groups"), ("post", "/groups"), ("get", f"/groups/{fake}"), ("delete", f"/groups/{fake}"),
        ("post", "/expenses"), ("put", f"/expenses/{fake}"), ("delete", f"/expenses/{fake}"),
        ("post", f"/groups/{fake}/settlements/generate"), ("post", f"/groups/{fake}/settlements/record"),
        ("post", "/payments/create"), ("get", "/payments/transactions/list"),
        ("post", "/ai/chat"), ("post", f"/ai/drafts/{fake}/confirm"), ("get", "/ai/actions"),
    ]
    for method, path in calls:
        assert getattr(client, method)(path).status_code == 401, (method, path)


def test_ai_data_is_scoped_to_the_caller(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Secret Trip").json()
    add_expense(client, a, g, 1000, [a])
    r = client.post("/ai/chat", json={"message": "Who owes me money in Secret Trip?"}, headers=b["headers"]).json()
    assert "Secret Trip" not in r["reply"] or "couldn't find" in r["reply"]
    r = client.post("/ai/chat", json={"message": "hello", "group_id": g["id"]}, headers=b["headers"])
    assert r.status_code == 200


def test_ai_chat_input_validation(client):
    a = mk(client, "Anwi")
    assert client.post("/ai/chat", json={"message": ""}, headers=a["headers"]).status_code == 422
    assert client.post("/ai/chat", json={"message": "x" * 2001}, headers=a["headers"]).status_code == 422
    assert client.post("/ai/chat", json={"message": "hi", "group_id": "nope"}, headers=a["headers"]).status_code == 422


# ---- payments ---------------------------------------------------------------
def test_only_the_debtor_can_simulate_a_payment(client):
    ctx = _setup_payment(client)
    r = client.post(f"/payments/{ctx['payment']['id']}/simulate?outcome=success", headers=ctx["anwita"]["headers"])
    assert r.status_code == 404
    stranger = mk(client, "Stranger")
    assert client.post(f"/payments/{ctx['payment']['id']}/simulate?outcome=success", headers=stranger["headers"]).status_code == 404
    assert client.get(f"/payments/{ctx['payment']['id']}", headers=ctx["rahul"]["headers"]).json()["status"] == "PENDING"


def test_stranger_cannot_create_payment_for_someone_elses_settlement(client):
    ctx = _setup_payment(client)
    stranger = mk(client, "Stranger")
    r = client.post("/payments/create", json={"settlement_id": ctx["settlement"]["id"]}, headers={**stranger["headers"], "Idempotency-Key": "z"})
    assert r.status_code == 404


# ---- webhooks ---------------------------------------------------------------
def test_late_failure_webhook_cannot_reopen_a_completed_settlement(client):
    ctx = _setup_payment(client)
    assert _post_webhook(client, _evt(ctx, "e1", "payment.success")).json()["payment_status"] == "SUCCESS"
    late = _post_webhook(client, _evt(ctx, "e2", "payment.failed"))
    assert late.status_code == 200 and late.json()["status"] == "ignored"
    s = client.get(f"/settlements/{ctx['settlement']['id']}", headers=ctx["rahul"]["headers"]).json()
    assert s["status"] == "COMPLETED"


def test_late_success_after_failure_is_ignored_too(client):
    ctx = _setup_payment(client)
    _post_webhook(client, _evt(ctx, "e1", "payment.failed"))
    late = _post_webhook(client, _evt(ctx, "e2", "payment.success"))
    assert late.json()["status"] == "ignored"
    assert client.get(f"/payments/{ctx['payment']['id']}", headers=ctx["rahul"]["headers"]).json()["status"] == "FAILED"


def test_replayed_success_event_does_not_double_apply(client):
    ctx = _setup_payment(client)
    evt = _evt(ctx, "same", "payment.success")
    assert _post_webhook(client, evt).json()["status"] == "processed"
    assert _post_webhook(client, evt).json()["status"] == "duplicate_ignored"
    g = client.get(f"/groups/{ctx['settlement']['group_id']}", headers=ctx["rahul"]["headers"]).json()
    assert g["debts"] == []


def test_malformed_signed_webhook_bodies_are_4xx_not_500(client):
    _setup_payment(client)
    cases = [
        (b"not json", 400),
        (b"[]", 422),
        (json.dumps({"event_id": "x"}).encode(), 422),
        (json.dumps({"event_id": 1, "event_type": "payment.success", "gateway_order_id": "o", "gateway_payment_id": "p"}).encode(), 422),
    ]
    for body, expected in cases:
        sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = client.post("/webhooks/payment", content=body, headers={"Content-Type": "application/json", "X-Webhook-Signature": sig})
        assert r.status_code == expected, (body, r.status_code)


def test_unknown_event_type_and_unknown_order_are_rejected_cleanly(client):
    ctx = _setup_payment(client)
    assert _post_webhook(client, _evt(ctx, "u1", "payment.refunded")).status_code in (400, 422)
    bad = _evt(ctx, "u2", "payment.success")
    bad["gateway_order_id"] = "order_that_does_not_exist"
    assert _post_webhook(client, bad).status_code in (404, 422)


def test_non_ascii_signature_header_is_401_not_500(client):
    _setup_payment(client)
    r = client.post("/webhooks/payment", content=b"{}", headers={"Content-Type": "application/json", "X-Webhook-Signature": "sïgnature".encode("utf-8")})
    assert r.status_code == 401
