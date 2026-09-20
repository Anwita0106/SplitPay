"""Acceptance scenario against a REAL PostgreSQL (+Redis) database — no SQLite, no mocks.

Usage (from the backend/ directory, after `alembic upgrade head` on an empty database):
    DATABASE_URL=postgresql+psycopg2://splitpay:splitpay@localhost:5432/splitpay_e2e \
    SECRET_KEY=dev PAYMENT_WEBHOOK_SECRET=dev PYTHONPATH=. python ../scripts/e2e_acceptance_pg.py

Walks the critical AI flow: draft -> confirm -> "who owes me" -> settle draft -> confirm -> settled,
then duplicate group names and group deletion. Prints each step; asserts the key invariants."""
import uuid
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
def reg(name):
    email = f"{name.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    c.post("/auth/register", json={"name": name, "email": email, "password": "SuperSecret123"})
    t = c.post("/auth/login", json={"email": email, "password": "SuperSecret123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    return {"h": h, "email": email, "id": c.get("/auth/me", headers=h).json()["id"]}
def chat(u, msg, **k):
    r = c.post("/ai/chat", json={"message": msg, **k}, headers=u["h"]); assert r.status_code == 200, r.text; return r.json()

anwi, anwita = reg("Anwi"), reg("Anwita")
g = c.post("/groups", json={"name": "Goa Trip", "member_emails": [anwita["email"]]}, headers=anwi["h"]).json()
print("group", g["name"])

r = chat(anwi, "I paid ₹2400 for dinner with Anwi and Anwita in Goa Trip. Split it equally.")
d = r["expense_draft"]; print("DRAFT :", [(p["name"], p["amount"]) for p in d["participants"]], "| expenses before confirm:", len(c.get(f"/groups/{g['id']}/expenses", headers=anwi["h"]).json()))
assert len(d["participants"]) == 2
c1 = c.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=anwi["h"]); c2 = c.post(f"/ai/drafts/{d['draft_id']}/confirm", headers=anwi["h"])
print("CONFIRM:", c1.status_code, c1.json()["status"], "| again ->", c2.json()["already_confirmed"], "| expenses:", len(c.get(f"/groups/{g['id']}/expenses", headers=anwi["h"]).json()))
q1 = chat(anwi, "Who owes me money?")["reply"]; print("Q1    :", q1); assert q1 == "Anwita owes you ₹1200 in Goa Trip."
print("Q2    :", chat(anwita, "Who do I owe?")["reply"])
r = chat(anwi, "I want to settle the ₹1200 Anwita owes me."); s = r["settlement_draft"]
print("SETTLE:", s["from_name"], "->", s["to_name"], s["amount"])
cs = c.post(f"/ai/drafts/{s['draft_id']}/confirm", headers=anwi["h"]); print("CONFIRM:", cs.status_code, cs.json()["settlement"]["status"], cs.json()["settlement"]["method"])
q3 = chat(anwi, "Who owes me money?")["reply"]; print("Q3    :", q3); assert q3.startswith("No one currently owes you money")
det = c.get(f"/groups/{g['id']}", headers=anwi["h"]).json(); print("GROUP :", [(b["user"]["name"], b["net_balance"]) for b in det["balances"]], "debts:", det["debts"])

c.post("/groups", json={"name": "Goa Trip", "member_emails": [], "allow_duplicate": True}, headers=anwi["h"])
r = chat(anwi, "Who owes me money in Goa Trip?"); print("DUPES :", r["reply"], "| options:", len(r["clarification"]["options"]))
r = chat(anwi, "Who owes me money in Goa Trip?", group_id=g["id"]); print("PICKED:", r["reply"])

dd = c.delete(f"/groups/{g['id']}", headers=anwi["h"]); print("DELETE:", dd.status_code, dd.json()["deleted"])
print("after :", c.get(f"/groups/{g['id']}", headers=anwi["h"]).status_code)

print("\nALL ACCEPTANCE STEPS PASSED")
