"""Group lifecycle: UUID-first access, duplicate names, members, rename, delete-with-cascade."""
import uuid

from app.models.ai_action import AiAction
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.settlement import Settlement
from app.tests.conftest import register_and_login, unique_email


def mk(client, name="Goa Trip"):
    return register_and_login(client, name, unique_email(name.split()[0].lower()))


def create_group(client, owner, name="Goa Trip", others=(), **extra):
    return client.post(
        "/groups", json={"name": name, "member_emails": [o["user"]["email"] for o in others], **extra}, headers=owner["headers"]
    )


def add_expense(client, payer, group, amount, users):
    r = client.post(
        "/expenses",
        json={"group_id": group["id"], "description": "Dinner", "total_amount": str(amount), "split_type": "EQUAL",
              "paid_by": payer["user"]["id"], "participant_ids": [u["user"]["id"] for u in users]},
        headers=payer["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---- creation / duplicates -------------------------------------------------
def test_duplicate_group_name_asks_before_creating_a_second(client):
    a = mk(client, "Anwi")
    assert create_group(client, a).status_code == 201
    r = create_group(client, a)
    assert r.status_code == 409 and r.json()["code"] == "DUPLICATE_GROUP_NAME"
    assert len(r.json()["extra"]["existing"]) == 1
    assert create_group(client, a, allow_duplicate=True).status_code == 201
    assert len(client.get("/groups", headers=a["headers"]).json()) == 2


def test_duplicate_name_check_is_case_and_punctuation_insensitive(client):
    a = mk(client, "Anwi")
    create_group(client, a, "Goa Trip")
    assert create_group(client, a, "  goa   trip! ").status_code == 409


def test_same_name_for_different_owners_is_fine(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    assert create_group(client, a).status_code == 201
    assert create_group(client, b).status_code == 201


def test_blank_group_name_rejected(client):
    a = mk(client, "Anwi")
    assert create_group(client, a, "   ").status_code == 422


def test_group_lookup_is_by_uuid_and_bad_uuid_is_422(client):
    a = mk(client, "Anwi")
    g = create_group(client, a).json()
    assert client.get(f"/groups/{g['id']}", headers=a["headers"]).status_code == 200
    assert client.get("/groups/not-a-uuid", headers=a["headers"]).status_code == 422
    assert client.get(f"/groups/{uuid.uuid4()}", headers=a["headers"]).status_code == 404


# ---- members ---------------------------------------------------------------
def test_add_member_case_insensitive_email_and_duplicates(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a).json()
    r = client.post(f"/groups/{g['id']}/members", json={"email": b["user"]["email"].upper()}, headers=a["headers"])
    assert r.status_code == 201
    r = client.post(f"/groups/{g['id']}/members", json={"email": b["user"]["email"]}, headers=a["headers"])
    assert r.status_code == 409
    r = client.post(f"/groups/{g['id']}/members", json={"email": "nobody@example.com"}, headers=a["headers"])
    assert r.status_code == 404


def test_non_member_cannot_add_members(client):
    a, b, c = mk(client, "Anwi"), mk(client, "Ben"), mk(client, "Cy")
    g = create_group(client, a).json()
    r = client.post(f"/groups/{g['id']}/members", json={"email": c["user"]["email"]}, headers=b["headers"])
    assert r.status_code in (403, 404)


def test_member_with_outstanding_balance_cannot_be_removed(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, others=[b]).json()
    add_expense(client, a, g, 1000, [a, b])
    r = client.delete(f"/groups/{g['id']}/members/{b['user']['id']}", headers=a["headers"])
    assert r.status_code == 409 and r.json()["code"] == "MEMBER_HAS_BALANCE"


def test_settled_member_can_leave_and_creator_cannot(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, others=[b]).json()
    assert client.delete(f"/groups/{g['id']}/members/{a['user']['id']}", headers=a["headers"]).status_code == 409  # creator
    assert client.delete(f"/groups/{g['id']}/members/{b['user']['id']}", headers=b["headers"]).status_code == 204  # leaves
    assert client.get(f"/groups/{g['id']}", headers=b["headers"]).status_code == 404


# ---- rename ----------------------------------------------------------------
def test_rename_group(client):
    a = mk(client, "Anwi")
    g = create_group(client, a).json()
    r = client.patch(f"/groups/{g['id']}", json={"name": "Goa 2026"}, headers=a["headers"])
    assert r.status_code == 200 and r.json()["name"] == "Goa 2026"


def test_only_creator_can_rename_group(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, others=[b]).json()
    r = client.patch(f"/groups/{g['id']}", json={"name": "Hijacked"}, headers=b["headers"])
    assert r.status_code == 403 and r.json()["code"] == "NOT_GROUP_CREATOR"


# ---- delete ----------------------------------------------------------------
def test_delete_group_removes_everything_and_only_that_group(client, db_session):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, others=[b]).json()
    keep = create_group(client, a, "Keep Me", others=[b]).json()
    add_expense(client, a, g, 1000, [a, b])
    add_expense(client, a, keep, 400, [a, b])
    client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"])

    r = client.delete(f"/groups/{g['id']}", headers=a["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["deleted"]["expenses"] == 1

    gid = uuid.UUID(g["id"])
    assert db_session.query(Group).filter(Group.id == gid).count() == 0
    assert db_session.query(GroupMember).filter(GroupMember.group_id == gid).count() == 0
    assert db_session.query(Expense).filter(Expense.group_id == gid).count() == 0
    assert db_session.query(Settlement).filter(Settlement.group_id == gid).count() == 0
    # ...and nothing else was touched
    kid = uuid.UUID(keep["id"])
    assert db_session.query(Expense).filter(Expense.group_id == kid).count() == 1
    assert db_session.query(ExpenseSplit).count() == 2
    assert client.get(f"/groups/{g['id']}", headers=a["headers"]).status_code == 404


def test_only_creator_can_delete_group(client):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, others=[b]).json()
    r = client.delete(f"/groups/{g['id']}", headers=b["headers"])
    assert r.status_code in (403, 404)
    assert client.get(f"/groups/{g['id']}", headers=a["headers"]).status_code == 200


def test_delete_group_with_payment_in_flight_is_blocked_and_rolls_back_nothing(client, db_session):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, others=[b]).json()
    add_expense(client, a, g, 1000, [a, b])
    s = client.post(f"/groups/{g['id']}/settlements/generate", headers=a["headers"]).json()[0]
    assert client.post("/payments/create", json={"settlement_id": s["id"]}, headers={**b["headers"], "Idempotency-Key": "k1"}).status_code == 201
    r = client.delete(f"/groups/{g['id']}", headers=a["headers"])
    assert r.status_code == 409
    assert db_session.query(Expense).filter(Expense.group_id == uuid.UUID(g["id"])).count() == 1  # untouched


def test_deleting_a_group_cancels_its_pending_ai_drafts_instead_of_leaving_them_confirmable(client, db_session):
    a, b = mk(client, "Anwi"), mk(client, "Ben")
    g = create_group(client, a, "Goa Trip", others=[b]).json()
    d = client.post("/ai/chat", json={"message": f"I paid 500 for cab with {b['user']['name']} in Goa Trip"}, headers=a["headers"]).json()["expense_draft"]
    assert client.delete(f"/groups/{g['id']}", headers=a["headers"]).status_code == 200
    r = client.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=a["headers"])
    assert r.status_code == 409
    assert db_session.query(Expense).count() == 0
    assert db_session.query(AiAction).one().status == "CANCELLED"
