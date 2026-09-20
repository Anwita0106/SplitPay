# SplitPay

### Smart Expense Sharing & UPI Settlement Platform

## Problem

Splitting shared expenses in a group — a trip, a flat, a recurring dinner
club — is easy to track but tedious to *settle*. People end up owing each
other small amounts across many transactions ("A owes B ₹200, B owes C
₹150, C owes A ₹50...") when in reality far fewer payments would clear
everyone's balance.

## Solution

SplitPay lets a group log shared expenses (split equally, by percentage,
or by exact amount), computes everyone's net balance, and **simplifies**
the debts into the minimum number of "who pays whom" transactions. Each
debtor can then pay their creditor directly through the app, with the
payment going through a real payment-gateway-style flow: order creation,
idempotent payment requests, and webhook-confirmed status — the frontend
never decides a payment succeeded on its own.

## Features

- JWT authentication (register / login / me)
- Groups with full lifecycle: create (duplicate-name aware), rename, add / remove /
  leave members, and **delete** (transactional cascade, blocked while a payment is in flight)
- Expenses with EQUAL, PERCENTAGE, and EXACT splitting — create, **edit** and delete,
  all with exact `Decimal` money (a share can never differ from the total by a paisa)
- One canonical balance engine: expenses **and completed settlements** are netted,
  so a settled debt actually disappears
- A settlement engine that simplifies debts into the fewest payments
- A payment flow with idempotent payment creation and webhook-confirmed
  status updates (sandbox gateway — see **Payment Flow** below), plus
  "mark as paid" for debts settled outside the app (cash / direct UPI)
- Transaction history covering both UPI payments and manually recorded settlements
- A local AI assistant (Ollama) whose writes are **draft → explicit confirm** only
- Redis-backed caching for the group page (display only — never used for decisions)
- Alembic migrations, 100+ backend tests and a frontend UI test suite

## Architecture

Modular monolith: one FastAPI service, internally split by domain (auth,
groups, expenses, settlements, payments, webhooks), each with its own
routes / schemas / service layer. Full diagram and rationale in
[`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

```
splitpay/
├── backend/            FastAPI + SQLAlchemy + PostgreSQL + Redis
├── frontend/            React + Vite + Tailwind + React Router
├── docs/                 SYSTEM_DESIGN.md and this README's companion docs
├── scripts/              DB init helpers used by docker-compose
└── docker-compose.yml
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, Tailwind CSS, React Router, Axios, Recharts |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, python-jose (JWT) |
| Database | PostgreSQL (NUMERIC for all money — never float) |
| Cache | Redis |
| DevOps | Docker, docker-compose |
| Testing | pytest, httpx (via FastAPI's TestClient) |

## Database Design

Schema is versioned with **Alembic** (`backend/alembic/versions`):
`0001_baseline` (the original eight tables, idempotent) and `0002_ledger_ai`
(settlement `method` / `recorded_by` / `idempotency_key`, `expenses.updated_at`,
and the `ai_actions` draft table). The raw Phase-1 DDL in
[`backend/app/db/schema.sql`](backend/app/db/schema.sql) is kept only as a reference.

Ten tables — `users`, `groups`, `group_members`, `expenses`, `expense_splits`,
`settlements`, `payments`, `webhook_events`, `ai_actions` (+ `alembic_version`) — with
foreign keys, cascade/restrict rules, and unique constraints
(`payments.idempotency_key`, `webhook_events.provider_event_id`,
`settlements.idempotency_key`) that enforce idempotency at the database level.
Full rationale in [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

**Identity rule:** every operation takes a **UUID**. Group *names* are display
labels only (two groups may both be called "Goa Trip"); name lookup exists in exactly
one place — `group_service.resolve_group` — used by the AI agent, which asks the user
to choose when a name is ambiguous instead of guessing.

### Money & balance conventions

- Money is `Decimal` end to end and `NUMERIC(12,2)` in PostgreSQL. Inputs with more than
  two decimal places are rejected; remainders are distributed to the paisa deterministically.
- Balance sign (API): **positive = is owed money, negative = owes money**; all balances
  in a group always sum to zero. UIs and the AI never show a signed number — they say
  "Anwita owes you ₹1200".
- `COMPLETED` settlements (UPI success **or** manually recorded) reduce balances.
  `PROCESSING` UPI payments are *reserved* when validating a new settlement, so the same
  debt can't be paid twice. `PENDING` suggestions and `CANCELLED` rows never count.

## Payment Flow

**Important — read this before the interview.** This project does not call
a real payment gateway's live API, because that would require a real
merchant account and credentials that don't exist for a personal portfolio
project. Instead, `SandboxPaymentProvider`
(`backend/app/services/payment_service.py`) simulates a UPI gateway's
test-mode behavior: it creates an "order", and a gated test-only endpoint
(`POST /payments/{id}/simulate`) plays the role of "the user completed
payment in their UPI app" — which triggers the **exact same webhook path**
a real provider's test-mode webhook would hit (signature verification,
deduplication, settlement status cascade included).

The `PaymentProvider` abstract class is the deliberate swap point: going
live with a real provider (e.g. Razorpay, which supports UPI in its own
test mode) means implementing one new class and changing one line in
`get_payment_provider()` — no other code changes. See the comments at the
top of `payment_service.py` and `.env.example` for exactly what that would
require.

```
User clicks "Pay Now"
  → POST /payments/create (Idempotency-Key header)
  → sandbox order created, payment = PENDING
  → simulate endpoint constructs a signed webhook payload
  → POST /webhooks/payment (signature verified, event deduped)
  → payment = SUCCESS, settlement = COMPLETED
```

## Settlement Algorithm

Greedy largest-creditor / largest-debtor matching. Deterministic (ties are broken by
user id, so the same balances always give the same suggestions), O(n log n)
time, O(n) space. The pure functions live in
[`backend/app/services/balance_math.py`](backend/app/services/balance_math.py); the
database-facing canonical read is
[`balance_service.get_group_balances`](backend/app/services/balance_service.py);
validation for every settlement (UPI or manual) is
[`settlement_service.validate_settlement`](backend/app/services/settlement_service.py).
See also [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

## Idempotency

Two independent mechanisms, each enforced by a database `UNIQUE`
constraint (not just application logic):

- **`payments.idempotency_key`** — protects against the *client* retrying
  (flaky network, double-tapped button). Same key → same payment returned,
  never a duplicate. A key is bound to one settlement: reusing it for a different
  settlement is a 409, and a settlement with a payment in flight rejects a *new* key
  (one live payment per settlement).
- **`webhook_events.provider_event_id`** — protects against the *provider*
  retrying (real gateways redeliver webhooks until they get a 2xx). Same
  event id → processed once, subsequent deliveries are detected and
  ignored.

## Webhooks

`POST /webhooks/payment` is the only path through which a payment is ever
marked successful. It verifies an HMAC-SHA256 signature over the raw
request body before trusting the payload, then delegates to the same
idempotent processing function whether the call came from a real gateway
or the sandbox's simulate endpoint. A late or out-of-order event for a payment that
is already `SUCCESS` / `FAILED` / `CANCELLED` is ignored, so a stray
`payment.failed` can never re-open a completed settlement. Only the *debtor* can call
the sandbox simulate endpoint.

## Redis

Used for exactly one thing: caching a group's computed balance summary
(the most expensive read — requires scanning every expense and split row
in the group). It serves **display reads only** (the group page): every
decision — validating a settlement, creating a payment, AI answers and drafts —
reads PostgreSQL. The cache is cleared **after the transaction commits** (and never
on a rollback), plus a short TTL as a backstop. If Redis is unreachable, the app
falls back to Postgres and backs off retrying for a few seconds — caching is a
performance optimization only, never a correctness dependency. See
[`backend/app/core/cache.py`](backend/app/core/cache.py).

---

## Setup

### Option A — Docker (recommended, gets everything running in one command)

```bash
git clone <this-repo>
cd splitpay

cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Edit backend/.env and set a real SECRET_KEY and PAYMENT_WEBHOOK_SECRET:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up --build
```

- Backend: http://localhost:8001 (docs at `/docs`)
- Frontend: http://localhost:5173

### Option B — Run locally without Docker

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # edit SECRET_KEY

docker run --name splitpay-postgres -e POSTGRES_USER=splitpay \
  -e POSTGRES_PASSWORD=splitpay -e POSTGRES_DB=splitpay -p 5432:5432 -d postgres:16
docker run --name splitpay-redis -p 6379:6379 -d redis:7-alpine

alembic upgrade head            # creates / upgrades the schema (safe to re-run)
uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend (separate terminal)
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Environment Variables

**`backend/.env`** — see [`backend/.env.example`](backend/.env.example)
for the full annotated list: `DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`,
`ACCESS_TOKEN_EXPIRE_MINUTES`, `CORS_ORIGINS`, `REDIS_URL`,
`CACHE_TTL_SECONDS`, `PAYMENT_SANDBOX_MODE`, `PAYMENT_WEBHOOK_SECRET`,
`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`,
`AI_DETERMINISTIC_INTENTS`, `AI_DRAFT_TTL_MINUTES`.

**`frontend/.env`** — `VITE_API_BASE_URL` (defaults to
`http://localhost:8001`).

**root `.env`** (docker-compose only) — `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`.

## Docker

`docker-compose.yml` runs four services: `postgres`, `redis`, `backend`,
`frontend` (served via nginx with SPA fallback routing). Postgres runs
`scripts/init-extensions.sql` on first startup; the **backend container runs
`alembic upgrade head` before starting the API**, so a fresh database gets the full
schema and an existing one is upgraded in place (no data is dropped — the migrations
add columns/tables and refuse to downgrade destructively).

### Upgrading an existing install

```bash
git pull && docker compose up --build      # migrations run automatically
```

One intentional behaviour change: before this version, balances ignored completed
settlements, so a debt that had been paid still showed as owed. After the upgrade,
groups that contain completed settlements will show **lower (correct)** balances.

## Testing

```bash
# Backend (SQLite in-memory; foreign keys enforced) — ~100 tests
cd backend && pytest app/tests/ -v

# Frontend UI tests (Vitest + Testing Library)
cd frontend && npm install && npm test
```

Backend test files:
- `test_split_service.py` — EQUAL / PERCENTAGE / EXACT math, remainder distribution, invalid input.
- `test_settlement_service.py` — net balances and the simplification algorithm.
- `test_auth.py` — registration, login, `/me`, missing / garbage token → 401.
- `test_expenses.py`, `test_ledger.py` — expense create / **edit** / delete, balances **net of settlements**,
  manual settlements (idempotent, limits, party rules), Decimal exactness, in-flight reservation.
- `test_groups.py` — UUID access, duplicate names, members, rename, **delete cascade** and its guards.
- `test_payments_idempotency.py`, `test_webhooks.py`, `test_security_and_webhooks.py` — idempotency keys,
  one-live-payment rule, signature checks, duplicate / late / malformed webhooks, authorization.
- `test_ai_acceptance.py`, `test_agent_service.py` — the full AI scenario (draft → confirm → balance →
  settle → settled), draft confirm-once / cancel / expiry, ambiguous groups, participant aliasing,
  the "no write tool" guarantee, and the Ollama tool loop (mocked).

Two extra checks need a real PostgreSQL (row locks, JSONB, partial unique index) and are run by hand:

```bash
cd backend && alembic upgrade head      # on an empty database
python ../scripts/e2e_acceptance_pg.py  # the acceptance scenario end to end
python ../scripts/concurrency_pg.py     # 6 parallel confirms -> 1 write; 6 parallel settles -> <= owed
```
(set `DATABASE_URL`, `SECRET_KEY`, `PAYMENT_WEBHOOK_SECRET`, `PYTHONPATH=.` as in the script headers).

## API Documentation

Interactive docs at `/docs` once running. Full endpoint list:

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create an account |
| POST | `/auth/login` | Get a JWT |
| GET | `/auth/me` | Current user |
| POST | `/groups` | Create a group (`409 DUPLICATE_GROUP_NAME` unless `allow_duplicate`) |
| GET | `/groups` | List my groups |
| GET | `/groups/{id}` | Group detail: members, balances and simplified `debts` |
| PATCH | `/groups/{id}` | Rename (creator only) |
| DELETE | `/groups/{id}` | Delete the group and everything in it (creator only) |
| POST | `/groups/{id}/members` | Add a member by email |
| DELETE | `/groups/{id}/members/{user_id}` | Remove a member / leave (needs a zero balance) |
| POST | `/expenses` | Create an expense (EQUAL / PERCENTAGE / EXACT) |
| GET | `/groups/{id}/expenses` | List a group's expenses |
| GET | `/expenses/{id}` | Expense detail |
| PUT | `/expenses/{id}` | Edit an expense (shares recomputed atomically) |
| DELETE | `/expenses/{id}` | Delete an expense |
| POST | `/groups/{id}/settlements/generate` | Recompute simplified settlements |
| POST | `/groups/{id}/settlements/record` | Record a debt settled outside the app (`Idempotency-Key` optional) |
| GET | `/groups/{id}/settlements` | List a group's settlements |
| GET | `/settlements/{id}` | Settlement detail |
| POST | `/payments/create` | Idempotent payment creation (`Idempotency-Key` header) |
| GET | `/payments` | My payments |
| GET | `/payments/{id}` | Payment detail |
| POST | `/payments/{id}/simulate` | **Sandbox only** — simulates gateway completion |
| GET | `/payments/transactions/list` | Enriched transaction history |
| GET | `/payments/transactions/{id}` | Transaction detail |
| POST | `/webhooks/payment` | Gateway webhook (signature-verified) |
| POST | `/ai/chat` | Ask the assistant; may return an expense / settlement **draft** or a group clarification |
| POST | `/ai/drafts/{id}/confirm` | The only way an AI-prepared write happens (idempotent) |
| POST | `/ai/drafts/{id}/cancel` | Discard a draft |
| GET | `/ai/actions` | My AI drafts and their outcomes |

Errors are `{"detail": "...", "code": "MACHINE_CODE", "extra"?: {...}}`; `detail` alone is what older clients read.

## System Design

See [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) for the full
write-up: functional/non-functional requirements, architecture, database
indexing strategy, failure handling, consistency guarantees, and how the
system would scale from 1,000 → 100,000 → 10,000,000 users.


## AI Agent (Free / Local)

A local assistant at `/ai` using Ollama (default `qwen2.5:3b`) — no paid API key.

- The model **cannot write**: it has read tools and two *prepare* tools that create a server-side draft.
  Only a user click on **Confirm** (`POST /ai/drafts/{id}/confirm`, draft id only) performs the write.
- Balance questions, "I paid ₹2400 for dinner with Anwita in Goa Trip" and "settle the ₹1200 Anwita owes me"
  are parsed and answered by deterministic backend code (`AI_DETERMINISTIC_INTENTS=true`), so they work
  even when Ollama is off and the wording of every amount comes from the database, not the model.
- Same-named groups are never guessed between; you get buttons to choose.
- Details, flow diagrams and the security model: [`docs/AI_AGENT.md`](docs/AI_AGENT.md) and
  [`docs/PHASE2_3_AI_ACTIONS.md`](docs/PHASE2_3_AI_ACTIONS.md). What changed in this rebuild:
  [`docs/REBUILD_CHANGELOG.md`](docs/REBUILD_CHANGELOG.md).
