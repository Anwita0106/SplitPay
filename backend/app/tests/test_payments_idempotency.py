from app.tests.conftest import register_and_login, unique_email


def _setup_settlement(client):
    anwita = register_and_login(client, "Anwita", unique_email("anwita"))
    rahul = register_and_login(client, "Rahul", unique_email("rahul"))

    group = client.post(
        "/groups",
        json={"name": "Weekend Trip", "member_emails": [rahul["user"]["email"]]},
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

    settlements = client.post(f"/groups/{group['id']}/settlements/generate", headers=anwita["headers"]).json()
    settlement = settlements[0]
    assert settlement["from_user"] == rahul["user"]["id"]
    assert settlement["to_user"] == anwita["user"]["id"]
    return {"anwita": anwita, "rahul": rahul, "settlement": settlement}


def test_payment_creation_requires_idempotency_key_header(client):
    ctx = _setup_settlement(client)
    r = client.post(
        "/payments/create",
        json={"settlement_id": ctx["settlement"]["id"]},
        headers=ctx["rahul"]["headers"],
    )
    assert r.status_code == 422  # missing required Idempotency-Key header


def test_only_debtor_can_create_payment(client):
    ctx = _setup_settlement(client)
    r = client.post(
        "/payments/create",
        json={"settlement_id": ctx["settlement"]["id"]},
        headers={**ctx["anwita"]["headers"], "Idempotency-Key": "key-1"},
    )
    assert r.status_code == 403


def test_duplicate_idempotency_key_returns_same_payment(client):
    ctx = _setup_settlement(client)
    headers = {**ctx["rahul"]["headers"], "Idempotency-Key": "fixed-key-abc"}

    r1 = client.post("/payments/create", json={"settlement_id": ctx["settlement"]["id"]}, headers=headers)
    r2 = client.post("/payments/create", json={"settlement_id": ctx["settlement"]["id"]}, headers=headers)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["gateway_order_id"] == r2.json()["gateway_order_id"]


def test_different_idempotency_keys_are_independent(client):
    ctx = _setup_settlement(client)
    r1 = client.post(
        "/payments/create",
        json={"settlement_id": ctx["settlement"]["id"]},
        headers={**ctx["rahul"]["headers"], "Idempotency-Key": "key-A"},
    )
    r2 = client.post(
        "/payments/create",
        json={"settlement_id": ctx["settlement"]["id"]},
        headers={**ctx["rahul"]["headers"], "Idempotency-Key": "key-B"},
    )
    assert r1.json()["id"] != r2.json()["id"]
