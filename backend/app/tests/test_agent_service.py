"""Unit-level tests of the REAL agent code (people resolution, group resolution, tool gate, LLM loop)."""
import uuid
from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.models.ai_action import AiAction
from app.models.expense import Expense
from app.models.user import User
from app.services import agent_service, draft_service
from app.services.agent_service import Run, ToolError, execute_tool, resolve_person
from app.services.group_service import AmbiguousGroup, GroupNotFound, members_of, resolve_group
from app.tests.conftest import register_and_login, unique_email


def make_group(client, owner, name, others=()):
    r = client.post("/groups", json={"name": name, "member_emails": [o["user"]["email"] for o in others]}, headers=owner["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def db_user(db, ctx):
    return db.query(User).filter(User.id == uuid.UUID(ctx["user"]["id"])).one()


@pytest.fixture()
def trio(client, db_session):
    anwi = register_and_login(client, "Anwi", unique_email("anwi"))
    anwita = register_and_login(client, "Anwita Sharma", unique_email("anwita"))
    carol = register_and_login(client, "Carol", unique_email("carol"))
    group = make_group(client, anwi, "Goa Trip", [anwita, carol])
    return {"anwi": anwi, "anwita": anwita, "carol": carol, "group": group, "db": db_session}


# ---- people ---------------------------------------------------------------
def test_self_aliases_all_resolve_to_the_same_user(trio):
    db = trio["db"]
    me = db_user(db, trio["anwi"])
    members = members_of(db, uuid.UUID(trio["group"]["id"]))
    ids = {resolve_person(x, me, members, "Goa Trip").id for x in ["Anwi", "you", "Me", "myself", " ANWI "]}
    assert ids == {me.id}


def test_first_name_matches_full_name_but_unknown_names_are_rejected(trio):
    db = trio["db"]
    me = db_user(db, trio["anwi"])
    members = members_of(db, uuid.UUID(trio["group"]["id"]))
    assert resolve_person("Anwita", me, members, "Goa Trip").name == "Anwita Sharma"
    with pytest.raises(ToolError) as e:
        resolve_person("Zed", me, members, "Goa Trip")
    assert "couldn't find" in e.value.message
    assert db.query(User).filter(User.name == "Zed").count() == 0  # nobody is ever invented


def test_ambiguous_first_name_is_not_guessed(client, db_session):
    a = register_and_login(client, "Me", unique_email("me"))
    s1 = register_and_login(client, "Sam Roy", unique_email("s1"))
    s2 = register_and_login(client, "Sam Das", unique_email("s2"))
    g = make_group(client, a, "Flat", [s1, s2])
    members = members_of(db_session, uuid.UUID(g["id"]))
    with pytest.raises(ToolError) as e:
        resolve_person("Sam", db_user(db_session, a), members, "Flat")
    assert "More than one" in e.value.message


# ---- groups ---------------------------------------------------------------
def test_duplicate_group_names_are_never_guessed(client, db_session):
    anwi = register_and_login(client, "Anwi", unique_email("anwi"))
    other = register_and_login(client, "Anwita", unique_email("anwita"))
    g1 = make_group(client, anwi, "Goa Trip", [other])
    r = client.post("/groups", json={"name": "Goa Trip", "member_emails": [], "allow_duplicate": True}, headers=anwi["headers"])
    assert r.status_code == 201
    g2 = r.json()
    me = db_user(db_session, anwi)

    with pytest.raises(AmbiguousGroup) as e:
        resolve_group(db_session, me, group_name="Goa Trip")
    assert {c.id for c in e.value.choices} == {uuid.UUID(g1["id"]), uuid.UUID(g2["id"])}

    # A group chosen in the UI breaks the tie; an explicit UUID always wins.
    assert resolve_group(db_session, me, group_name="goa trip", context_group_id=uuid.UUID(g2["id"])).id == uuid.UUID(g2["id"])
    assert resolve_group(db_session, me, group_id=g1["id"]).id == uuid.UUID(g1["id"])


def test_group_name_placed_in_the_id_slot_still_resolves(trio):
    me = db_user(trio["db"], trio["anwi"])
    assert str(resolve_group(trio["db"], me, group_id="Goa Trip").id) == trio["group"]["id"]  # small-model habit
    assert str(resolve_group(trio["db"], me, group_name="goa trp").id) == trio["group"]["id"]  # typo tolerant


def test_someone_elses_group_id_is_not_found(client, db_session):
    a = register_and_login(client, "A", unique_email("a"))
    b = register_and_login(client, "B", unique_email("b"))
    make_group(client, a, "Mine")
    theirs = make_group(client, b, "Theirs")
    with pytest.raises(GroupNotFound):
        resolve_group(db_session, db_user(db_session, a), group_id=theirs["id"])


def test_chat_asks_which_group_when_names_collide(client, db_session):
    anwi = register_and_login(client, "Anwi", unique_email("anwi"))
    anwita = register_and_login(client, "Anwita", unique_email("anwita"))
    g1 = make_group(client, anwi, "Goa Trip", [anwita])
    g2 = client.post("/groups", json={"name": "Goa Trip", "member_emails": [anwita["user"]["email"]], "allow_duplicate": True}, headers=anwi["headers"]).json()

    r = client.post("/ai/chat", json={"message": "I paid 800 for taxi with Anwita in Goa Trip"}, headers=anwi["headers"]).json()
    assert r["expense_draft"] is None
    assert len(r["clarification"]["options"]) == 2
    assert db_session.query(AiAction).count() == 0  # nothing prepared until the user chooses

    chosen = r["clarification"]["options"][1]["group_id"]
    r2 = client.post("/ai/chat", json={"message": "I paid 800 for taxi with Anwita in Goa Trip", "group_id": chosen}, headers=anwi["headers"]).json()
    assert r2["expense_draft"]["expense"]["group_id"] == chosen
    assert chosen in (g1["id"], g2["id"])


# ---- the tool gate ---------------------------------------------------------
def test_agent_has_no_write_or_confirm_tool():
    names = {t["function"]["name"] for t in agent_service.TOOLS}
    assert names == set(agent_service.READ_TOOLS) | set(agent_service.DRAFT_TOOLS)
    assert not any(w in n for n in names for w in ("confirm", "create", "delete", "save", "record"))


def test_unknown_tool_is_refused(trio):
    run = Run(db=trio["db"], user=db_user(trio["db"], trio["anwi"]))
    for bad in ("confirm_expense", "delete_group", "record_settlement"):
        with pytest.raises(ToolError):
            execute_tool(bad, {}, run)


def test_preparing_a_draft_writes_no_expense(trio):
    db = trio["db"]
    run = Run(db=db, user=db_user(db, trio["anwi"]))
    execute_tool("prepare_expense_draft", {"group_name": "Goa Trip", "description": "Dinner", "total_amount": "2400",
                                           "participant_names": ["Anwi", "You", "Anwita Sharma"]}, run)
    assert db.query(Expense).count() == 0
    assert db.query(AiAction).filter(AiAction.status == "PENDING").count() == 1
    assert len(run.expense_draft.participants) == 2  # "Anwi" + "You" collapsed


def test_failed_preparation_creates_no_draft(trio):
    db = trio["db"]
    run = Run(db=db, user=db_user(db, trio["anwi"]))
    with pytest.raises(ToolError):
        execute_tool("prepare_expense_draft", {"group_name": "Goa Trip", "description": "x", "total_amount": "10",
                                               "participant_names": ["Nobody"]}, run)
    with pytest.raises(ToolError):
        execute_tool("prepare_expense_draft", {"group_name": "Goa Trip", "description": "x", "total_amount": "10.005",
                                               "participant_names": ["me"]}, run)
    assert db.query(AiAction).count() == 0


def test_settlement_draft_requires_the_user_to_be_a_party(trio, client):
    db = trio["db"]
    anwi, anwita, carol = (db_user(db, trio[k]) for k in ("anwi", "anwita", "carol"))
    exp = {"group_id": trio["group"]["id"], "description": "Dinner", "total_amount": "900", "split_type": "EQUAL",
           "paid_by": trio["anwi"]["user"]["id"], "participant_ids": [str(u.id) for u in (anwi, anwita, carol)]}
    assert client.post("/expenses", json=exp, headers=trio["anwi"]["headers"]).status_code == 201
    group = resolve_group(db, anwi, group_id=trio["group"]["id"])
    with pytest.raises(DomainError) as e:
        draft_service.prepare_settlement_draft(db, carol, group=group, from_user=anwita, to_user=anwi, amount=Decimal("300"))
    assert e.value.code == "NOT_A_PARTY"


# ---- LLM path (Ollama mocked) ----------------------------------------------
class FakeOllama:
    """Replays scripted /api/chat responses."""

    script: list = []

    def __init__(self, *a, **k): ...
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def post(self, url, json=None):
        payload = FakeOllama.script.pop(0)

        class R:
            def raise_for_status(self): ...
            def json(self_inner): return {"message": payload}
        return R()


def test_llm_tool_call_with_group_name_in_id_slot_and_duplicate_self(trio, monkeypatch):
    monkeypatch.setattr(agent_service.httpx, "Client", FakeOllama)
    monkeypatch.setattr(agent_service.settings, "AI_DETERMINISTIC_INTENTS", False)
    FakeOllama.script = [
        {"content": "", "tool_calls": [{"function": {"name": "prepare_expense_draft", "arguments": {
            "group_id": "Goa Trip", "description": "Dinner", "total_amount": "2400", "split_type": "EQUAL",
            "participant_names": ["Anwi", "Anwita", "You"]}}}]},
        {"content": "Done! I saved your expense of ₹9999."},  # a lying model must not leak into the reply
    ]
    db = trio["db"]
    result = agent_service.chat(db, db_user(db, trio["anwi"]), "dinner 2400 with anwita", [])
    assert result.mode == "llm" and result.expense_draft is not None
    assert len(result.expense_draft.participants) == 2
    assert "9999" not in result.reply and "saved" not in result.reply.lower().replace("nothing is saved", "")
    assert db.query(Expense).count() == 0


def test_llm_ambiguity_is_reported_as_clarification(client, db_session, monkeypatch):
    monkeypatch.setattr(agent_service.httpx, "Client", FakeOllama)
    monkeypatch.setattr(agent_service.settings, "AI_DETERMINISTIC_INTENTS", False)
    a = register_and_login(client, "Anwi", unique_email("anwi"))
    make_group(client, a, "Goa Trip")
    client.post("/groups", json={"name": "Goa Trip", "member_emails": [], "allow_duplicate": True}, headers=a["headers"])
    FakeOllama.script = [
        {"content": "", "tool_calls": [{"function": {"name": "get_group_summary", "arguments": {"group_name": "Goa Trip"}}}]},
        {"content": "You have two groups with that name — which one?"},
    ]
    result = agent_service.chat(db_session, db_user(db_session, a), "summary of goa trip", [])
    assert result.clarification is not None and len(result.clarification.options) == 2


def test_ollama_down_gives_friendly_message_but_deterministic_intents_still_work(trio, monkeypatch):
    monkeypatch.setattr(agent_service.settings, "OLLAMA_BASE_URL", "http://127.0.0.1:9")  # nothing listens there
    db = trio["db"]
    r = agent_service.chat(db, db_user(db, trio["anwi"]), "Tell me a joke", [])
    assert "isn't connected" in r.reply
    r = agent_service.chat(db, db_user(db, trio["anwi"]), "Who owes me money?", [])
    assert r.mode == "deterministic"
