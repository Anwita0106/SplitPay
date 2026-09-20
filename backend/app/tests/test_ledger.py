"""Expense edit/delete, the canonical balance engine, manual settlements, Decimal exactness."""
from decimal import Decimal

from app.tests.conftest import register_and_login, unique_email
from app.tests.test_groups import add_expense, create_group, mk


def net(client, who, group):
    """{user_id: Decimal} from the REST group page (positive = is owed)."""
    d = client.get(f"/groups/{group['id']}", headers=who["headers"]).json()
    return {b["user"]["id"]: Decimal(b["net_balance"]) for b in d["balances"]}


def trio(client):
    a, b, c = mk(client, "Anwi"), mk(client, "Ben"), mk(client, "Cy")
    g = create_group(client, a, "Trip", others=[b, c]).json()
    return a, b, c, g


# ---- Decimal exactness -------------------------------------------------------
def test_uneven_equal_split_sums_exactly_to_total(client):
    a, b, c, g = trio(client)
    e = add_expense(client, a, g, "100.00", [a, b, c])
    shares = sorted(Decimal(s["amount"]) for s in e["splits"])
    assert sum(shares) == Decimal("100.00")
    assert shares == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(net(client, a, g).values()) == Decimal("0")


def test_more_than_two_decimal_places_is_rejected(client):
    a, b, c, g = trio(client)
    r = client.post("/expenses", json={"group_id": g["id"], "description": "x", "total_amount": "10.005", "split_type": "EQUAL",
                                       "paid_by": a["user"]["id"], "participant_ids": [a["user"]["id"]]}, headers=a["headers"])
    assert r.status_code == 422


def test_zero_and_negative_amounts_rejected(client):
    a, b, c, g = trio(client)
    for amount in ("0", "-5"):
        r = client.post("/expenses", json={"group_id": g["id"], "description": "x", "total_amount": amount, "split_type": "EQUAL",
                                           "paid_by": a["user"]["id"], "participant_ids": [a["user"]["id"]]}, headers=a["headers"])
        assert r.status_code == 422


# ---- expense edit / delete ---------------------------------------------------
def test_edit_expense_recomputes_balances(client):
    a, b, c, g = trio(client)
    e = add_expense(client, a, g, 900, [a, b, c])
    assert net(client, a, g)[b["user"]["id"]] == Decimal("-300.00")
    r = client.put(f"/expenses/{e['id']}", json={"description": "Dinner + drinks", "total_amount": "600", "split_type": "EQUAL",
                                                 "paid_by": a["user"]["id"], "participant_ids": [a["user"]["id"], b["user"]["id"]]},
                   headers=a["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Dinner + drinks"
    n = net(client, a, g)
    assert n[b["user"]["id"]] == Decimal("-300.00")
    assert n.get(c["user"]["id"], Decimal("0")) == Decimal("0")  # Cy dropped out of the split
    assert len(r.json()["splits"]) == 2  # old splits replaced, not appended


def test_edit_with_non_member_participant_is_rejected_and_changes_nothing(client):
    a, b, c, g = trio(client)
    outsider = mk(client, "Out")
    e = add_expense(client, a, g, 900, [a, b, c])
    r = client.put(f"/expenses/{e['id']}", json={"description": "x", "total_amount": "900", "split_type": "EQUAL",
                                                 "paid_by": a["user"]["id"], "participant_ids": [a["user"]["id"], outsider["user"]["id"]]},
                   headers=a["headers"])
    assert r.status_code == 422
    assert client.get(f"/expenses/{e['id']}", headers=a["headers"]).json()["total_amount"] == "900.00"


def test_delete_expense_restores_balances(client):
    a, b, c, g = trio(client)
    e = add_expense(client, a, g, 900, [a, b, c])
    assert client.delete(f"/expenses/{e['id']}", headers=a["headers"]).status_code == 204
    assert all(v == 0 for v in net(client, a, g).values())
    assert client.get(f"/expenses/{e['id']}", headers=a["headers"]).status_code == 404


def test_non_member_cannot_read_edit_or_delete_expense(client):
    a, b, c, g = trio(client)
    outsider = mk(client, "Out")
    e = add_expense(client, a, g, 900, [a, b, c])
    assert client.get(f"/expenses/{e['id']}", headers=outsider["headers"]).status_code == 404
    assert client.delete(f"/expenses/{e['id']}", headers=outsider["headers"]).status_code == 404
    assert client.get(f"/groups/{g['id']}/expenses", headers=outsider["headers"]).status_code == 404


# ---- settlements reduce balances (the original bug) ----------------------------
def test_completed_upi_settlement_reduces_balance_and_does_not_recreate_suggestion(client):
    a, b, g = mk(client, "Anwi"), mk(client, "Ben"), None
    g = create_group(client, a, "Duo", others=[b]).json()
    add_expense(client, a, g, 2400, [a, b])
    s = client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"]).json()[0]
    p = client.post("/payments/create", json={"settlement_id": s["id"]}, headers={**b["headers"], "Idempotency-Key": "k"}).json()
    assert client.post(f"/payments/{p['id']}/simulate?outcome=success", headers=b["headers"]).status_code == 200

    assert all(v == 0 for v in net(client, a, g).values())
    assert client.get(f"/groups/{g['id']}", headers=a["headers"]).json()["debts"] == []
    again = client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"]).json()
    assert [x for x in again if x["status"] == "PENDING"] == []  # nothing left to suggest


def test_partial_settlement_leaves_the_remainder(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Duo", others=[b]).json()
    add_expense(client, a, g, 2400, [a, b])  # Ben owes 1200
    r = client.post(f"/groups/{g['id']}/settlements/record", json={"from_user": b["user"]["id"], "to_user": a["user"]["id"], "amount": "500"}, headers=a["headers"])
    assert r.status_code == 201 and r.json()["status"] == "COMPLETED" and r.json()["method"] == "MANUAL"
    assert net(client, a, g)[b["user"]["id"]] == Decimal("-700.00")


def test_cannot_settle_more_than_owed_or_when_nothing_owed(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Duo", others=[b]).json()
    body = {"from_user": b["user"]["id"], "to_user": a["user"]["id"], "amount": "1"}
    assert client.post(f"/groups/{g['id']}/settlements/record", json=body, headers=a["headers"]).status_code == 422  # nothing owed
    add_expense(client, a, g, 1000, [a, b])
    r = client.post(f"/groups/{g['id']}/settlements/record", json={**body, "amount": "501"}, headers=a["headers"])
    assert r.status_code == 422 and "at most ₹500" in r.json()["detail"]
    wrong_way = {"from_user": a["user"]["id"], "to_user": b["user"]["id"], "amount": "10"}
    assert client.post(f"/groups/{g['id']}/settlements/record", json=wrong_way, headers=a["headers"]).status_code == 422


def test_third_party_cannot_record_a_settlement(client):
    a, b, c, g = trio(client)
    add_expense(client, a, g, 900, [a, b, c])
    r = client.post(f"/groups/{g['id']}/settlements/record",
                    json={"from_user": b["user"]["id"], "to_user": a["user"]["id"], "amount": "100"}, headers=c["headers"])
    assert r.status_code in (403, 422)
    assert net(client, a, g)[b["user"]["id"]] == Decimal("-300.00")


def test_manual_settlement_is_idempotent_and_key_reuse_for_other_settlement_conflicts(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Duo", others=[b]).json()
    add_expense(client, a, g, 2000, [a, b])
    body = {"from_user": b["user"]["id"], "to_user": a["user"]["id"], "amount": "300"}
    h = {**a["headers"], "Idempotency-Key": "settle-1"}
    r1 = client.post(f"/groups/{g['id']}/settlements/record", json=body, headers=h)
    r2 = client.post(f"/groups/{g['id']}/settlements/record", json=body, headers=h)
    assert r1.status_code == r2.status_code == 201 and r1.json()["id"] == r2.json()["id"]
    assert net(client, a, g)[b["user"]["id"]] == Decimal("-700.00")  # applied once
    r3 = client.post(f"/groups/{g['id']}/settlements/record", json={**body, "amount": "400"}, headers=h)
    assert r3.status_code == 409


def test_in_flight_upi_payment_blocks_double_settling_the_same_debt(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Duo", others=[b]).json()
    add_expense(client, a, g, 1000, [a, b])
    s = client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"]).json()[0]
    assert client.post("/payments/create", json={"settlement_id": s["id"]}, headers={**b["headers"], "Idempotency-Key": "k"}).status_code == 201
    r = client.post(f"/groups/{g['id']}/settlements/record", json={"from_user": b["user"]["id"], "to_user": a["user"]["id"], "amount": "500"}, headers=a["headers"])
    assert r.status_code == 422  # the ₹500 is already reserved by the payment in flight


def test_changing_an_expense_makes_a_stale_payment_suggestion_unpayable(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Duo", others=[b]).json()
    e = add_expense(client, a, g, 1000, [a, b])
    s = client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"]).json()[0]
    client.delete(f"/expenses/{e['id']}", headers=a["headers"])
    r = client.post("/payments/create", json={"settlement_id": s["id"]}, headers={**b["headers"], "Idempotency-Key": "k"})
    # The stale suggestion is either removed with the change (404) or refused as out of date (409) — never payable.
    assert r.status_code == 404 or (r.status_code == 409 and r.json()["code"] in ("SETTLEMENT_OUT_OF_DATE", "SETTLEMENT_CANCELLED"))
    assert client.get("/payments", headers=b["headers"]).json() == []


def test_generation_is_deterministic_and_never_duplicates(client):
    a, b, c, g = trio(client)
    add_expense(client, a, g, 900, [a, b, c])
    first = client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"]).json()
    second = client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"]).json()
    pending = lambda xs: sorted((x["from_user"], x["to_user"], x["amount"]) for x in xs if x["status"] == "PENDING")
    assert pending(first) == pending(second) and len(pending(second)) == 2


def test_transactions_list_includes_manual_settlements(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Duo", others=[b]).json()
    add_expense(client, a, g, 1000, [a, b])
    client.post(f"/groups/{g['id']}/settlements/record", json={"from_user": b["user"]["id"], "to_user": a["user"]["id"], "amount": "500"}, headers=a["headers"])
    tx = client.get("/payments/transactions/list", headers=b["headers"]).json()
    assert len(tx) == 1 and tx[0]["method"] == "MANUAL" and tx[0]["group_name"] == "Duo"
    assert client.get(f"/payments/transactions/{tx[0]['id']}", headers=b["headers"]).status_code == 200
