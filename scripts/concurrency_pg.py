"""Concurrency safety on REAL PostgreSQL (row locks): run from backend/ like e2e_acceptance_pg.py.

1) the same AI draft confirmed from 6 sessions at once must write exactly ONE expense;
2) six simultaneous manual settlements of ₹300 when only ₹500 is owed must let at most one through."""
import uuid, threading
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.expense import Expense
from app.models.settlement import Settlement
from app.services import draft_service, settlement_service
from app.core.errors import DomainError

c = TestClient(app)
def reg(name):
    email = f"{name.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    c.post("/auth/register", json={"name": name, "email": email, "password": "SuperSecret123"})
    t = c.post("/auth/login", json={"email": email, "password": "SuperSecret123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    return {"h": h, "email": email, "id": c.get("/auth/me", headers=h).json()["id"]}
a, b = reg("Anwi"), reg("Ben")
g = c.post("/groups", json={"name": "Race", "member_emails": [b["email"]]}, headers=a["h"]).json()
d = c.post("/ai/chat", json={"message": "I paid 1000 for lunch with Ben in Race"}, headers=a["h"]).json()["expense_draft"]

# 1) same draft confirmed from 6 sessions at once
results = []
def confirm():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == uuid.UUID(a["id"])).one()
        r = draft_service.confirm_draft(db, u, uuid.UUID(d["draft_id"]))
        results.append(("ok", r.already_confirmed))
    except Exception as e:
        results.append(("err", type(e).__name__, str(getattr(e, "detail", e))[:60]))
    finally:
        db.close()
ts = [threading.Thread(target=confirm) for _ in range(6)]; [t.start() for t in ts]; [t.join() for t in ts]
db = SessionLocal()
print("results:", sorted(results, key=str))
n = db.query(Expense).filter(Expense.group_id == uuid.UUID(g["id"])).count(); print("expenses written:", n, "(expected 1)"); assert n == 1

# 2) six concurrent manual settlements of Rs 300 each when Ben owes only Rs 500 -> at most one may succeed
out = []
def settle(i):
    s = SessionLocal()
    try:
        u = s.query(User).filter(User.id == uuid.UUID(a["id"])).one()
        settlement_service.record_manual_settlement(s, group_id=uuid.UUID(g["id"]), actor=u, from_user=uuid.UUID(b["id"]),
            to_user=uuid.UUID(a["id"]), amount=Decimal("300"), idempotency_key=f"race-{i}")
        out.append("ok")
    except DomainError as e:
        out.append(e.code)
    finally:
        s.close()
ts = [threading.Thread(target=settle, args=(i,)) for i in range(6)]; [t.start() for t in ts]; [t.join() for t in ts]
print("settle outcomes:", sorted(out))
done = db.query(Settlement).filter(Settlement.group_id == uuid.UUID(g["id"]), Settlement.status == "COMPLETED").all()
total = sum(x.amount for x in done); print("completed settlements:", len(done), "total:", total, "(must be <= 500)"); assert total <= 500
print("\nCONCURRENCY CHECKS PASSED")
