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


def _pay(client, ctx, key):
    return client.post(
        "/payments/create",
        json={"settlement_id": ctx["settlement"]["id"]},
        headers={**ctx["rahul"]["headers"], "Idempotency-Key": key},
    )


def test_different_keys_for_different_settlements_are_independent(client):
    first = _setup_settlement(client)
    second = _setup_settlement(client)
    r1, r2 = _pay(client, first, "key-A"), _pay(client, second, "key-B")
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


def test_second_key_for_a_settlement_already_in_flight_is_rejected(client):
    """One live payment per settlement: a fresh key must not open a second gateway order."""
    ctx = _setup_settlement(client)
    assert _pay(client, ctx, "key-A").status_code == 201
    r2 = _pay(client, ctx, "key-B")
    assert r2.status_code == 409
    assert r2.json()["code"] == "PAYMENT_IN_PROGRESS"


def test_same_key_for_a_different_settlement_is_rejected(client):
    """A reused key must never hand back someone else's payment."""
    first = _setup_settlement(client)
    second = _setup_settlement(client)
    assert _pay(client, first, "shared-key").status_code == 201
    r = _pay(client, second, "shared-key")
    assert r.status_code == 409
    assert r.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
