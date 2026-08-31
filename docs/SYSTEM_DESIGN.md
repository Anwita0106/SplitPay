# SplitPay — System Design

## 1. Functional Requirements

- Users register, log in, and manage their profile.
- Users create groups and add/remove members.
- Users record shared expenses, split EQUAL / PERCENTAGE / EXACT.
- The system computes each member's net balance and simplifies debts into
  the minimum number of "who pays whom" transactions.
- Users pay a settlement through a payment gateway (sandbox in this
  project); payment success is confirmed via webhook, never the frontend.
- Users view transaction history and per-group spending summaries.

## 2. Non-Functional Requirements

- **Correctness of money math** — no floating-point error, ever.
- **Consistency** — a payment is never marked successful without gateway
  confirmation; a settlement's status always reflects its actual payment
  state.
- **Idempotency** — retried payment-creation requests never double-charge.
- **Availability of reads** — group summaries stay fast as expense history
  grows, via caching.
- **Auditability** — every webhook delivery is logged, so payment state
  transitions can be traced.

## 3. Architecture

```
┌─────────────┐      HTTPS/JSON      ┌───────────────────┐
│  React SPA  │ ───────────────────► │  FastAPI (Uvicorn) │
└─────────────┘                      └─────────┬──────────┘
                                                │
                     ┌──────────────────────────┼───────────────────────┐
                     ▼                          ▼                       ▼
              ┌─────────────┐           ┌──────────────┐        ┌──────────────┐
              │ PostgreSQL  │           │    Redis     │        │  Payment      │
              │(system of   │           │ (group       │        │  Provider     │
              │  record)    │           │  summary     │        │  (sandbox,    │
              │             │           │  cache)      │        │  swappable)   │
              └─────────────┘           └──────────────┘        └──────┬───────┘
                                                                        │ webhook
                                                                        ▼
                                                                 ┌──────────────┐
                                                                 │ POST         │
                                                                 │ /webhooks/   │
                                                                 │  payment     │
                                                                 └──────────────┘
```

A **modular monolith**: one deployable FastAPI service, internally split by
domain (`auth`, `groups`, `expenses`, `settlements`, `payments`,
`webhooks`), each with its own routes/schemas/service layer. This gives
clean separation of concerns without the operational cost of real
microservices, which a 3-day timeline can't justify — and it's an honest
answer if asked "why not microservices?" in the interview: the boundaries
already exist in code; splitting into services later is a deployment
change, not a redesign.

## 4. API Design

See `README.md` → API Documentation for the full endpoint list with
request/response shapes. Design principles used throughout:

- Resource-oriented URLs (`/groups/{id}/expenses`, not `/getExpensesForGroup`).
- Every mutating endpoint enforces group membership before touching data;
  non-members get `404` (not `403`) so group *existence* isn't leaked.
- List endpoints return arrays directly; detail endpoints return the full
  object with resolved relationships (e.g. `GroupDetailOut` includes
  members and computed balances, not just foreign keys).

## 5. Database Schema

Full DDL: `backend/app/db/schema.sql`. Highlights:

- `NUMERIC(12,2)` for every money column — exact decimal arithmetic.
- `group_members` and `expense_splits` use composite/unique constraints to
  make "no duplicate membership" and "one split row per participant" a
  database-level guarantee, not just an application-level check.
- `payments.idempotency_key UNIQUE` is what makes payment creation
  idempotent even under concurrent duplicate requests.
- `webhook_events.provider_event_id UNIQUE` is what makes webhook
  processing idempotent even under duplicate delivery.
- Indexes on every foreign key plus the columns that drive list views
  (`expenses(group_id, created_at DESC)`, `settlements(status)`, etc).

## 6. Settlement Algorithm

Two-phase, implemented in `app/services/settlement_service.py`:

**Phase 1 — compute_net_balances.** One pass over all expenses (add the
full amount to the payer's balance) and their splits (subtract each
participant's share). O(E) time where E = number of expense_split rows in
the group, O(U) space where U = number of users with a non-zero balance.

**Phase 2 — simplify_settlements.** Split users into creditors (positive
balance) and debtors (negative balance), sort each by magnitude descending,
then greedily match the largest creditor against the largest debtor,
transferring `min(credit, debt)` and advancing past whichever side hits
zero. O(n log n) time (sorting dominates), O(n) space.

This produces at most `n - 1` transactions for `n` people with non-zero
balances — not the theoretical minimum in every case (that's an NP-hard
matching problem in general), but the standard, explainable, deterministic
approach used by real expense-splitting products. Determinism matters:
regenerating settlements from the same balances always produces the same
transfers, which is what makes the "Recalculate" button in the UI safe to
click repeatedly.

## 7. Payment Flow

```
User clicks "Pay Now"
  → POST /payments/create  (Idempotency-Key header)
     → PaymentService creates a sandbox "order", payment row = PENDING
  → Frontend "completes" the sandbox payment (simulate endpoint)
     → constructs the same signed payload a real gateway's webhook would send
  → POST /webhooks/payment  (signature verified, event deduped)
     → payment.status = SUCCESS, settlement.status = COMPLETED
  → Frontend polls / re-fetches and shows the confirmed result
```

The frontend is never the source of truth for payment success — see
`app/services/payment_service.py` and `app/api/routes/webhooks.py` for the
full rationale on the sandbox provider design and why a real gateway
integration isn't shipped without verified credentials.

## 8. Webhook Flow & Idempotency

Two independent idempotency mechanisms protect two different failure modes:

1. **Payment creation** (`payments.idempotency_key UNIQUE`): protects
   against the *client* retrying — a flaky network, or a user double
   tapping "Pay Now" — from creating two orders for the same intent.
2. **Webhook processing** (`webhook_events.provider_event_id UNIQUE`):
   protects against the *provider* retrying — real gateways redeliver
   webhooks until they get a 2xx response, so the same event can arrive
   more than once. The handler checks for the event id first and
   short-circuits on a duplicate.

Both are enforced at the database layer (unique constraints), not just in
application code — the correctness guarantee doesn't depend on the
application never racing itself.

## 9. Redis (Caching)

Used for exactly one thing: caching a group's computed balance summary,
the most expensive read in the app (requires scanning every expense and
split row for a group). Cache is invalidated on any write that changes
balances (new expense, deleted expense) plus a short TTL as a backstop. If
Redis is unreachable, the app transparently falls back to computing from
Postgres — caching is a performance optimization, never a correctness
dependency. See `app/core/cache.py`.

## 10. Indexing Strategy

Every foreign key is indexed (standard practice — without it, cascading
deletes and JOINs force full table scans). Additional indexes target the
actual query patterns: `expenses(group_id, created_at DESC)` for the
expense feed, `settlements(status)` and `payments(status)` for filtering
in-flight vs completed records, `payments(idempotency_key)` and
`webhook_events(provider_event_id)` as the enforcement points for the two
idempotency mechanisms above.

## 11. Scaling: 1,000 → 100,000 → 10,000,000 users

**At 1,000 users (current architecture):** the modular monolith on a
single instance, single Postgres, single Redis handles this comfortably.
Bottleneck, if any, is developer velocity, not load.

**At 100,000 users:**
- Run multiple stateless backend instances behind a **load balancer** — the
  JWT-based auth already makes this trivial, since there's no server-side
  session to share.
- Add a **Postgres read replica** for read-heavy endpoints (group listing,
  transaction history) while writes (expenses, payments) go to the primary.
- Redis becomes more important: cache hit rate on group summaries matters
  more as concurrent users grow.
- Move webhook processing off the request path into a **queue** (e.g.
  Redis-backed or SQS) if payment volume grows — acknowledge the webhook
  fast, process asynchronously, so a slow DB write never causes the
  provider to time out and retry unnecessarily.
- Add **rate limiting** (e.g. per-user, per-IP) at the API gateway or
  middleware layer, particularly on `/auth/login` and `/payments/create`.

**At 10,000,000 users:**
- **Horizontal scaling** of backend instances behind the load balancer
  becomes the norm, not the exception; instances are fully stateless and
  scale independently of the database.
- **Database partitioning/sharding** becomes necessary — a natural shard
  key is `group_id` or `user_id`, since almost all queries are scoped to a
  group or a user. `expenses` and `payments` are the largest, fastest
  growing tables and the first candidates.
- Split the monolith into services **only where the data now justifies
  it** — e.g. a dedicated Payments service with its own database, since
  payment data has different consistency, compliance, and audit
  requirements than social/group data. This is the point where the
  modular boundaries already in the codebase pay off: extracting a service
  is a deployment change, because the code was never entangled.
- Full **observability stack**: structured logging, distributed tracing
  (a payment's lifecycle spans create → webhook → settlement update — you
  need to trace that as one flow across retries), metrics/alerting on
  payment failure rates and webhook processing latency specifically, since
  those are the highest-cost failures.
- **Async processing** for anything not on the critical path of a user
  request — settlement recalculation for very large groups, notification
  delivery, analytics aggregation.

## 12. Failure Handling & Consistency

- **Payment succeeds, server goes down before responding:** no problem —
  the webhook is the source of truth, not the response to any particular
  request. When the server comes back, the webhook (or its retry) still
  arrives and updates state correctly. The client can also poll
  `GET /payments/{id}` to recover the real status.
- **Webhook arrives twice:** the second delivery is detected via
  `webhook_events.provider_event_id` and ignored — no double-processing,
  no double-updating the settlement.
- **User clicks "Pay Now" twice:** if it's the same logical attempt (same
  idempotency key, e.g. a client-side retry), the second request returns
  the existing payment. If it's genuinely a second attempt with a new key
  (e.g. after a failed first attempt), a new payment row is created for
  the same settlement — allowed, because retrying a failed payment is
  legitimate.
- **Redis is down:** cache reads/writes fail silently and the code path
  falls through to computing directly from Postgres. Slower, still
  correct.

## 13. Bottlenecks & Trade-offs

- **Greedy settlement algorithm isn't provably minimal** — accepted
  trade-off for determinism, explainability, and O(n log n) performance
  over an NP-hard optimal-matching approach.
- **Stateless JWT auth can't be revoked before expiry** — accepted for
  simplicity in a 3-day project; a production system would add short-lived
  access tokens + refresh tokens, or a revocation list for compromised
  tokens.
- **No formal DB migrations (Alembic) in this build** — `schema.sql` is
  the single source of truth, applied directly. Fine for a project with
  no live production data to migrate; a real production system would use
  Alembic (or similar) from day one so schema changes are versioned and
  reversible.
- **Sandbox payment provider, not a real gateway** — the honest trade-off
  given no real merchant credentials exist for a portfolio project; the
  provider abstraction is the designed extension point for a real
  integration later.

## 14. Future Architecture

- Real payment gateway integration behind the existing `PaymentProvider`
  abstraction (see `app/services/payment_service.py`).
- Push notifications (e.g. "X added an expense", "Y paid you back").
- Multi-currency support (would touch the schema — `amount` + `currency`
  columns, and the settlement algorithm would need to group by currency).
- Recurring/scheduled expenses.
- Read replicas + sharding, as detailed in the scaling section above, once
  real load data indicates where the actual bottleneck is (never
  pre-optimize for a scale that hasn't been measured).
