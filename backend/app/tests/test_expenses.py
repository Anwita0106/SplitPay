from app.tests.conftest import register_and_login, unique_email


def _make_goa_trip_group(client):
    anwita = register_and_login(client, "Anwita", unique_email("anwita"))
    rahul = register_and_login(client, "Rahul", unique_email("rahul"))
    priya = register_and_login(client, "Priya", unique_email("priya"))
    arjun = register_and_login(client, "Arjun", unique_email("arjun"))

    r = client.post(
        "/groups",
        json={
            "name": "Goa Trip",
            "member_emails": [rahul["user"]["email"], priya["user"]["email"], arjun["user"]["email"]],
        },
        headers=anwita["headers"],
    )
    assert r.status_code == 201
    group = r.json()
    return {"group": group, "anwita": anwita, "rahul": rahul, "priya": priya, "arjun": arjun}


def test_create_group_and_add_expense_equal_split(client):
    ctx = _make_goa_trip_group(client)
    group_id = ctx["group"]["id"]
    ids = [ctx[p]["user"]["id"] for p in ("anwita", "rahul", "priya", "arjun")]

    r = client.post(
        "/expenses",
        json={
            "group_id": group_id,
            "description": "Hotel",
            "total_amount": "4000",
            "split_type": "EQUAL",
            "paid_by": ctx["anwita"]["user"]["id"],
            "participant_ids": ids,
        },
        headers=ctx["anwita"]["headers"],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["total_amount"] == "4000.00" or float(body["total_amount"]) == 4000
    assert len(body["splits"]) == 4
    assert all(float(s["amount"]) == 1000 for s in body["splits"])


def test_settlement_generation_matches_expected_debts(client):
    ctx = _make_goa_trip_group(client)
    group_id = ctx["group"]["id"]
    ids = [ctx[p]["user"]["id"] for p in ("anwita", "rahul", "priya", "arjun")]

    client.post(
        "/expenses",
        json={
            "group_id": group_id,
            "description": "Hotel",
            "total_amount": "4000",
            "split_type": "EQUAL",
            "paid_by": ctx["anwita"]["user"]["id"],
            "participant_ids": ids,
        },
        headers=ctx["anwita"]["headers"],
    )

    r = client.post(f"/groups/{group_id}/settlements/generate", headers=ctx["anwita"]["headers"])
    assert r.status_code == 200
    settlements = r.json()
    assert len(settlements) == 3
    for s in settlements:
        assert s["to_user"] == ctx["anwita"]["user"]["id"]
        assert float(s["amount"]) == 1000


def test_non_member_cannot_see_group(client):
    ctx = _make_goa_trip_group(client)
    outsider = register_and_login(client, "Outsider", unique_email("outsider"))
    r = client.get(f"/groups/{ctx['group']['id']}", headers=outsider["headers"])
    assert r.status_code == 404


def test_percentage_split_must_sum_to_100(client):
    ctx = _make_goa_trip_group(client)
    group_id = ctx["group"]["id"]
    a_id = ctx["anwita"]["user"]["id"]
    r_id = ctx["rahul"]["user"]["id"]

    r = client.post(
        "/expenses",
        json={
            "group_id": group_id,
            "description": "Cab",
            "total_amount": "1000",
            "split_type": "PERCENTAGE",
            "paid_by": a_id,
            "splits": [{"user_id": a_id, "percentage": "60"}, {"user_id": r_id, "percentage": "30"}],
        },
        headers=ctx["anwita"]["headers"],
    )
    assert r.status_code == 422


def test_expense_participant_must_be_group_member(client):
    ctx = _make_goa_trip_group(client)
    group_id = ctx["group"]["id"]
    a_id = ctx["anwita"]["user"]["id"]
    outsider = register_and_login(client, "Outsider2", unique_email("outsider2"))

    r = client.post(
        "/expenses",
        json={
            "group_id": group_id,
            "description": "Snacks",
            "total_amount": "200",
            "split_type": "EQUAL",
            "paid_by": a_id,
            "participant_ids": [a_id, outsider["user"]["id"]],
        },
        headers=ctx["anwita"]["headers"],
    )
    assert r.status_code == 422
