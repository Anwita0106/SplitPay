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
- Groups with membership management
- Expenses with EQUAL, PERCENTAGE, and EXACT splitting, fully validated
- A settlement engine that computes net balances and simplifies debts
- A payment flow with idempotent payment creation and webhook-confirmed
  status updates (sandbox gateway — see **Payment Flow** below)
- Transaction history with per-transaction detail view
- Redis-backed caching for group balance summaries
- 35 automated tests covering the business-critical logic end to end

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

Full DDL: [`backend/app/db/schema.sql`](backend/app/db/schema.sql). Eight
tables — `users`, `groups`, `group_members`, `expenses`, `expense_splits`,
`settlements`, `payments`, `webhook_events` — with proper foreign keys,
cascade/restrict rules, and the two unique constraints
(`payments.idempotency_key`, `webhook_events.provider_event_id`) that
enforce idempotency at the database level. Full rationale in
[`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

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

Greedy largest-creditor / largest-debtor matching. Deterministic, O(n log n)
time, O(n) space. Full explanation with complexity analysis:
[`backend/app/services/settlement_service.py`](backend/app/services/settlement_service.py)
and [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

## Idempotency

Two independent mechanisms, each enforced by a database `UNIQUE`
constraint (not just application logic):

- **`payments.idempotency_key`** — protects against the *client* retrying
  (flaky network, double-tapped button). Same key → same payment returned,
  never a duplicate.
- **`webhook_events.provider_event_id`** — protects against the *provider*
  retrying (real gateways redeliver webhooks until they get a 2xx). Same
  event id → processed once, subsequent deliveries are detected and
  ignored.

## Webhooks

`POST /webhooks/payment` is the only path through which a payment is ever
marked successful. It verifies an HMAC-SHA256 signature over the raw
request body before trusting the payload, then delegates to the same
idempotent processing function whether the call came from a real gateway
or the sandbox's simulate endpoint.

## Redis

Used for exactly one thing: caching a group's computed balance summary
(the most expensive read — requires scanning every expense and split row
in the group). Invalidated on any write that changes balances, plus a
short TTL as a backstop. If Redis is unreachable, the app transparently
falls back to Postgres — caching is a performance optimization only, never
a correctness dependency. See
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

- Backend: http://localhost:8000 (docs at `/docs`)
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

docker exec -i splitpay-postgres psql -U splitpay -d splitpay -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
docker exec -i splitpay-postgres psql -U splitpay -d splitpay < app/db/schema.sql

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
`CACHE_TTL_SECONDS`, `PAYMENT_SANDBOX_MODE`, `PAYMENT_WEBHOOK_SECRET`.

**`frontend/.env`** — `VITE_API_BASE_URL` (defaults to
`http://localhost:8000`).

**root `.env`** (docker-compose only) — `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`.

## Docker

`docker-compose.yml` runs four services: `postgres`, `redis`, `backend`,
`frontend` (served via nginx with SPA fallback routing). Postgres runs
`scripts/init-extensions.sql` then `backend/app/db/schema.sql`
automatically on first startup via the standard
`docker-entrypoint-initdb.d` mechanism.

## Testing

```bash
cd backend
source venv/bin/activate
pytest app/tests/ -v
```

35 tests across 5 files:
- `test_split_service.py` — EQUAL / PERCENTAGE / EXACT split math, including
  remainder distribution and rejection of invalid inputs.
- `test_settlement_service.py` — net balance computation and the
  simplification algorithm, including the exact Goa Trip example from the
  spec.
- `test_auth.py` — registration, login, `/me`, and auth failure modes.
- `test_expenses.py` — group/expense creation, authorization (non-members
  rejected), split validation via the real API.
- `test_payments_idempotency.py` — duplicate idempotency keys return the
  same payment; different keys are independent; only the debtor can pay.
- `test_webhooks.py` — signature verification, success/failure cascades to
  settlement status, and duplicate webhook delivery is a no-op the second
  time.

## API Documentation

Interactive docs at `/docs` once running. Full endpoint list:

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create an account |
| POST | `/auth/login` | Get a JWT |
| GET | `/auth/me` | Current user |
| POST | `/groups` | Create a group |
| GET | `/groups` | List my groups |
| GET | `/groups/{id}` | Group detail: members + computed balances |
| POST | `/groups/{id}/members` | Add a member by email |
| DELETE | `/groups/{id}/members/{user_id}` | Remove a member |
| POST | `/expenses` | Create an expense (EQUAL / PERCENTAGE / EXACT) |
| GET | `/groups/{id}/expenses` | List a group's expenses |
| GET | `/expenses/{id}` | Expense detail |
| DELETE | `/expenses/{id}` | Delete an expense |
| POST | `/groups/{id}/settlements/generate` | Recompute simplified settlements |
| GET | `/groups/{id}/settlements` | List a group's settlements |
| GET | `/settlements/{id}` | Settlement detail |
| POST | `/payments/create` | Idempotent payment creation (`Idempotency-Key` header) |
| GET | `/payments` | My payments |
| GET | `/payments/{id}` | Payment detail |
| POST | `/payments/{id}/simulate` | **Sandbox only** — simulates gateway completion |
| GET | `/payments/transactions/list` | Enriched transaction history |
| GET | `/payments/transactions/{id}` | Transaction detail |
| POST | `/webhooks/payment` | Gateway webhook (signature-verified) |

## System Design

See [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) for the full
write-up: functional/non-functional requirements, architecture, database
indexing strategy, failure handling, consistency guarantees, and how the
system would scale from 1,000 → 100,000 → 10,000,000 users.

