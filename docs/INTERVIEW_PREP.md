# SplitPay — Likely Interview Questions & Answers

Ten questions a PhonePe SDE interviewer is likely to ask about this
project, with answers grounded in what's actually implemented.

---

**1. Why did you model money as `NUMERIC(12,2)` instead of `FLOAT`?**

Floats are binary fractions — many decimal values (like 0.1) can't be
represented exactly, so repeated arithmetic accumulates rounding error.
`0.1 + 0.2` literally doesn't equal `0.3` in IEEE 754 float. For money,
that's unacceptable — an expense split has to sum to *exactly* the total,
every time. `NUMERIC` (and Python's `Decimal` in the application layer) is
exact base-10 arithmetic, so `calculate_equal_split` and friends can
`assert sum(shares.values()) == total_amount` and mean it.

**2. Walk me through what happens end-to-end when a user clicks "Pay Now".**

The frontend generates a fresh idempotency key and calls
`POST /payments/create` with it. The backend checks whether a payment with
that key already exists (it doesn't, first time), verifies the caller is
actually the debtor on that settlement, creates a sandbox "order", and
inserts a `Payment` row with status `PENDING`, moving the `Settlement` to
`PROCESSING`. The frontend then triggers what plays the role of gateway
confirmation, which fires a signed webhook to `POST /webhooks/payment`.
That handler verifies the HMAC signature, checks it hasn't processed this
event id before, then updates the payment to `SUCCESS` and the settlement
to `COMPLETED` — all inside one flow the frontend only observes, never
drives.

**3. How do you guarantee a user is never double-charged?**

Two layers: application logic checks for an existing payment with the same
idempotency key before creating a new one, and — critically — the database
has a `UNIQUE` constraint on `payments.idempotency_key`. If two requests
with the same key race each other, the application-level check can lose
that race, but the database constraint can't: one `INSERT` wins, the other
fails, and the code catches that failure and returns the winning row. The
guarantee lives in the database, not just in careful code.

**4. Why not just trust the frontend when it says "payment succeeded"?**

Because the frontend only knows what the user's browser told it, which can
be wrong, spoofed by a malicious client, or simply never received if the
tab closed mid-payment. The actual outcome of a payment is known only to
the payment provider. That's why `/webhooks/payment` — a signed
server-to-server call — is the *only* code path in this entire codebase
that can set a payment's status to `SUCCESS`. Search the codebase: no
other route touches that field.

**5. You don't have a real payment gateway integration — why, and how would you add one?**

Because integrating against a real provider's live API would require a
real merchant account and verified credentials that don't exist for a
personal project — and shipping code that calls a real endpoint I've never
actually tested against would be dishonest about what's been verified.
Instead, I built `PaymentProvider` as an abstract interface with a
`SandboxPaymentProvider` implementation that simulates a UPI gateway's
test-mode behavior closely enough to exercise the entire real flow: order
creation, idempotency, signed webhook delivery, deduplication, and status
cascade. Going live means implementing one new class (e.g.
`RazorpayProvider`) and changing one line in `get_payment_provider()` — no
other code changes, because nothing else in the codebase depends on which
provider is behind the interface.

**6. Explain the settlement simplification algorithm and its complexity.**

Split users into creditors (positive net balance) and debtors (negative),
sort each list by magnitude descending — O(n log n) — then repeatedly
match the largest creditor against the largest debtor, transferring
`min(credit, debt)`, and advance past whichever side hits zero. The
matching loop itself is O(n) since each step fully resolves at least one
side. Overall O(n log n) time, O(n) space. It's a greedy heuristic, not
provably optimal (true minimum-transaction settlement is an NP-hard
matching problem), but it's deterministic, easy to explain, and bounds the
result to at most n-1 transactions for n people — which is what real
expense-splitting products actually ship.

**7. How would this scale to millions of users?**

The backend is already stateless (JWT auth, no server-side session), so
horizontal scaling behind a load balancer is a deployment change, not a
redesign. Beyond that: a Postgres read replica for read-heavy endpoints,
moving webhook processing off the request path into a queue at high
payment volume, and eventually partitioning the largest tables (`expenses`,
`payments`) by `group_id` or `user_id` — the natural shard key, since
almost every query is already scoped to one of those. Full detail in
`docs/SYSTEM_DESIGN.md`.

**8. What's your caching strategy and why only there?**

Redis caches one thing: a group's computed balance summary, because
computing it requires scanning every expense and split row in that group —
the single most expensive read in the app. Everything else reads straight
from Postgres because there's no repeated-computation cost to amortize;
caching auth or a single expense lookup would add complexity for no
benefit. The cache is invalidated on any write that changes balances, with
a short TTL as a backstop, and if Redis is down the code transparently
falls back to Postgres — caching is a performance layer, never a
correctness dependency.

**9. How do you handle authorization — can any user see any group?**

Every group/expense/settlement endpoint checks group membership before
returning anything, via a shared `_require_membership` check that queries
the `group_members` table. Critically, a non-member gets a `404`, not a
`403` — returning 403 would confirm the group exists, which leaks
information to someone who isn't part of it.

**10. What would you do differently with more time?**

Formal Alembic migrations instead of a single `schema.sql` applied
directly — fine for a project with no live data to migrate, but a real
production system needs versioned, reversible schema changes from day one.
I'd also add refresh tokens (the current JWT can't be revoked before it
expires, which is an acceptable trade-off for a 3-day project but not for
production), and move webhook processing onto a queue so a slow database
write can never cause the payment provider to time out and unnecessarily
retry.
