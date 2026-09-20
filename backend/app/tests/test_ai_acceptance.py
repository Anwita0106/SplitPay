"""End-to-end AI flow over the real HTTP API (deterministic intents — no Ollama needed).

Mirrors the critical acceptance scenario: dinner for ₹2400 split with Anwita in
"Goa Trip" -> draft -> confirm -> "who owes me" -> settle draft -> confirm -> settled.
"""
from decimal import Decimal

from app.tests.conftest import register_and_login, unique_email


def chat(client, who, message, **extra):
    r = client.post("/ai/chat", json={"message": message, **extra}, headers=who["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def setup_goa(client, group_name="Goa Trip"):
    anwi = register_and_login(client, "Anwi", unique_email("anwi"))
    anwita = register_and_login(client, "Anwita", unique_email("anwita"))
    g = client.post(
        "/groups", json={"name": group_name, "member_emails": [anwita["user"]["email"]]}, headers=anwi["headers"]
    )
    assert g.status_code == 201, g.text
    return anwi, anwita, g.json()


def expenses_of(client, who, group):
    return client.get(f"/groups/{group['id']}/expenses", headers=who["headers"]).json()


def test_critical_acceptance_scenario(client):
    anwi, anwita, group = setup_goa(client)

    # 1. AI prepares a draft — and writes nothing.
    r = chat(client, anwi, "I paid ₹2400 for dinner with Anwi and Anwita in Goa Trip. Split it equally.")
    draft = r["expense_draft"]
    assert draft is not None and r["mode"] == "deterministic"
    assert Decimal(draft["expense"]["total_amount"]) == Decimal("2400")
    assert draft["paid_by_name"] == "Anwi"
    assert sorted(p["name"] for p in draft["participants"]) == ["Anwi", "Anwita"]  # no duplicate Anwi
    assert all(Decimal(p["amount"]) == Decimal("1200") for p in draft["participants"])
    assert expenses_of(client, anwi, group) == []
    assert "Nothing is saved yet" in r["reply"]

    # 2. Confirm writes exactly one expense; a double-click does not write a second.
    c1 = client.post(f"/ai/drafts/{draft['draft_id']}/confirm", headers=anwi["headers"])
    assert c1.status_code == 200 and c1.json()["status"] == "CONFIRMED"
    c2 = client.post(f"/ai/drafts/{draft['draft_id']}/confirm", headers=anwi["headers"])
    assert c2.status_code == 200 and c2.json()["already_confirmed"] is True
    assert len(expenses_of(client, anwi, group)) == 1

    # 3. Balance question is answered from the backend.
    r = chat(client, anwi, "Who owes me money?")
    assert r["reply"] == "Anwita owes you ₹1200 in Goa Trip."
    assert "-" not in r["reply"]

    r = chat(client, anwita, "Who do I owe?")
    assert r["reply"] == "You owe Anwi ₹1200 in Goa Trip."

    # 4. The CREDITOR can start the settlement ("Anwita owes me").
    r = chat(client, anwi, "I want to settle the ₹1200 Anwita owes me.")
    s = r["settlement_draft"]
    assert s is not None
    assert (s["from_name"], s["to_name"], Decimal(s["amount"])) == ("Anwita", "Anwi", Decimal("1200"))

    # 5. Confirm -> settled everywhere.
    c = client.post(f"/ai/drafts/{s['draft_id']}/confirm", headers=anwi["headers"])
    assert c.status_code == 200 and c.json()["settlement"]["status"] == "COMPLETED"
    r = chat(client, anwi, "Who owes me money?")
    assert r["reply"].startswith("No one currently owes you money")
    r = chat(client, anwi, "Who owes me money in Goa Trip?")
    assert r["reply"] == "No one currently owes you money in Goa Trip."
    detail = client.get(f"/groups/{group['id']}", headers=anwi["headers"]).json()
    assert detail["debts"] == []


def test_draft_can_be_cancelled_and_then_not_confirmed(client):
    anwi, _, group = setup_goa(client)
    d = chat(client, anwi, "I paid 500 for cab with Anwita in Goa Trip")["expense_draft"]
    assert client.post(f"/ai/drafts/{d['draft_id']}/cancel", headers=anwi["headers"]).json()["status"] == "CANCELLED"
    r = client.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=anwi["headers"])
    assert r.status_code == 409 and r.json()["code"] == "DRAFT_NOT_PENDING"
    assert expenses_of(client, anwi, group) == []


def test_someone_elses_draft_is_indistinguishable_from_missing(client):
    anwi, anwita, _ = setup_goa(client)
    d = chat(client, anwi, "I paid 500 for cab with Anwita in Goa Trip")["expense_draft"]
    assert client.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=anwita["headers"]).status_code == 404
    assert client.post(f"/ai/drafts/{d['draft_id']}/cancel", headers=anwita["headers"]).status_code == 404
    assert client.post("/ai/drafts/00000000-0000-0000-0000-000000000000/confirm", headers=anwi["headers"]).status_code == 404


def test_typing_confirm_in_chat_never_saves(client):
    anwi, _, group = setup_goa(client)
    chat(client, anwi, "I paid 500 for cab with Anwita in Goa Trip")
    r = chat(client, anwi, "yes confirm")
    assert "Confirm button" in r["reply"] and r["expense_draft"] is None
    assert expenses_of(client, anwi, group) == []


def test_draft_fails_cleanly_if_data_changed_before_confirm(client):
    anwi, anwita, group = setup_goa(client)
    d = chat(client, anwi, "I paid 500 for cab with Anwita in Goa Trip")["expense_draft"]
    # Anwita leaves the group before the draft is confirmed.
    assert client.delete(f"/groups/{group['id']}/members/{anwita['user']['id']}", headers=anwi["headers"]).status_code == 204
    r = client.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=anwi["headers"])
    assert r.status_code in (409, 422)
    assert expenses_of(client, anwi, group) == []
    actions = client.get("/ai/actions", headers=anwi["headers"]).json()
    assert actions[0]["status"] == "FAILED" and actions[0]["error"]


def test_settlement_draft_cannot_exceed_outstanding(client):
    anwi, anwita, group = setup_goa(client)
    d = chat(client, anwi, "I paid 1000 for lunch with Anwita in Goa Trip")["expense_draft"]
    client.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=anwi["headers"])
    r = chat(client, anwi, "Anwita paid me back ₹900 in Goa Trip")
    assert r["settlement_draft"] is None
    assert "at most ₹500" in r["reply"]


def test_ai_history_lists_actions(client):
    anwi, _, _ = setup_goa(client)
    d = chat(client, anwi, "I paid 500 for cab with Anwita in Goa Trip")["expense_draft"]
    client.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=anwi["headers"])
    actions = client.get("/ai/actions", headers=anwi["headers"]).json()
    assert actions[0]["status"] == "CONFIRMED" and "Cab" in actions[0]["summary"]
