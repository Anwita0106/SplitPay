# SplitPay — Phase 1: Architecture & Foundations

## 1. Architectural style: Modular Monolith

One FastAPI process, cleanly separated into modules by domain (`auth`, `groups`,
`expenses`, `settlements`, `payments`, `webhooks`). Each module owns its routes,
schemas, and service logic. This gives you clean separation of concerns to talk
about in an interview, without the operational overhead of real microservices
that 3 days can't justify.

```
Client (React SPA)
        │  HTTPS / JSON
        ▼
FastAPI app (Uvicorn)
   ├── api/routes/*        → thin HTTP layer (request/response only)
   ├── services/*          → business logic (splitting, settlement, payments)
   ├── models/*             → SQLAlchemy ORM models
   ├── schemas/*             → Pydantic request/response contracts
   ├── core/                → config, security (JWT/hashing), dependencies
   └── db/                  → session management, schema
        │
        ├──► PostgreSQL   (system of record — users, groups, expenses, settlements, payments)
        └──► Redis        (cache + short-lived payment/session state)
```

**Why this split matters for the interview:** routes never contain business
logic, so the settlement algorithm and payment state machine can be unit
tested directly, with no HTTP layer involved.

## 2. Full project tree

```
splitpay/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app entrypoint (Phase 2)
│   │   ├── core/
│   │   │   ├── config.py            # settings via pydantic-settings, reads .env
│   │   │   ├── security.py          # password hashing, JWT encode/decode
│   │   │   └── deps.py              # get_current_user, get_db, etc.
│   │   ├── db/
│   │   │   ├── session.py           # SQLAlchemy engine/session
│   │   │   └── schema.sql           # raw DDL (reference / manual setup)
│   │   ├── models/                  # SQLAlchemy ORM models (1 file per table)
│   │   ├── schemas/                 # Pydantic schemas (1 file per domain)
│   │   ├── services/
│   │   │   ├── split_service.py     # equal/percentage/exact split logic
│   │   │   ├── settlement_service.py# debt simplification algorithm
│   │   │   └── payment_service.py   # payment provider abstraction
│   │   ├── api/routes/
│   │   │   ├── auth.py
│   │   │   ├── groups.py
│   │   │   ├── expenses.py
│   │   │   ├── settlements.py
│   │   │   ├── payments.py
│   │   │   └── webhooks.py
│   │   └── tests/                   # pytest suite
│   ├── alembic/                     # DB migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/                   # Login, Register, Dashboard, Groups, etc.
│   │   ├── components/              # reusable UI (Navbar, ExpenseCard, ...)
│   │   ├── services/                # axios API client
│   │   ├── context/                 # auth context
│   │   ├── hooks/
│   │   └── utils/
│   ├── public/
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── PHASE1_ARCHITECTURE.md       # this file
│   └── SYSTEM_DESIGN.md             # written in Phase 8
├── docker-compose.yml               # Phase 7
├── .env.example                     # Phase 7
└── README.md                        # Phase 8
```

## 3. Database schema — design rationale

Full DDL is in `backend/app/db/schema.sql`. Key decisions to be able to defend
in the interview:

- **`NUMERIC(12,2)` everywhere for money.** Floats introduce rounding errors
  that are unacceptable for financial data — `0.1 + 0.2 != 0.3` in binary
  floating point. `NUMERIC` is exact decimal arithmetic.
- **`group_members` uses a composite primary key** `(group_id, user_id)` —
  this is both the natural key and enforces "a user can only be in a group
  once" at the database level, not just in application code.
- **`expense_splits` has a `UNIQUE(expense_id, user_id)` constraint** for the
  same reason — one split row per participant per expense.
- **`payments.idempotency_key` is `UNIQUE`.** This is what makes payment
  creation idempotent at the database layer (details in Phase 5/6) — even
  if two identical requests race each other, the second INSERT fails the
  unique constraint and the service returns the existing row instead.
- **`webhook_events` table** logs every inbound webhook by
  `provider_event_id` (unique) so duplicate webhook deliveries — which all
  real payment providers can send — are detected and ignored rather than
  processed twice.
- **Cascade rules:** deleting a `group` cascades to `group_members` and
  `expenses` (a group's data has no meaning without the group). Deleting a
  `user` is deliberately `RESTRICT`ed on `expenses.paid_by` and
  `settlements` — you should never be able to delete a user who is party to
  financial records; that's a deactivation flow, not a deletion, in a real
  system.
- **Indexes** are placed on every foreign key and on the columns that will
  drive the dashboard/list queries (`group_id, created_at DESC` for expense
  feeds, `status` on settlements/payments for filtering).

## 4. What's intentionally deferred

- Alembic migration files — Phase 2 (schema.sql above is the source of truth
  for now; Alembic will version it).
- SQLAlchemy model classes, Pydantic schemas — Phase 2.
- Any route/service code — Phase 2 onward.
- Redis usage patterns — introduced when the caching need actually shows up
  (dashboard summaries), not before.

## 5. Confirm before Phase 2

Before I move on, please confirm:
1. This folder structure and schema look right to you.
2. You're OK with **UUID primary keys** (good practice, avoids ID-guessing,
   trivial to shard later) — the alternative is auto-increment integers,
   which are simpler to read in a demo/interview. Say the word if you'd
   rather use integers instead.
3. Any change to the MUST-HAVE table list before I build the auth layer.
