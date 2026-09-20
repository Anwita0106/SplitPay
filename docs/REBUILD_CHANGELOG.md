# Rebuild changelog — audit findings, fixes and additions

Every "bug" below was reproduced against a running database before being fixed, and each fix has a test.

## Bugs fixed

| # | Problem found | Fix |
|---|---|---|
| 1 | **Completed settlements never reduced balances** — a fully paid debt still showed as owed, and "Recalculate" created a duplicate PENDING next to the COMPLETED one | One canonical balance engine (`balance_math` / `balance_service`) nets out COMPLETED settlements; stale suggestions are refreshed or cancelled, never duplicated |
| 2 | **AI "group not found / more than one group matches"** — duplicate group names errored, and a group *name* in the `group_id` argument failed as "not a valid UUID" | `group_service.resolve_group`: UUID-first, names only as a search phrase, ambiguity → a clarification with choices, UI `group_id` as tie-break |
| 3 | AI could only settle the **debtor's** own debt, so "settle the ₹1200 Anwita owes me" was a 403 | Draft rules: either party of the debt may start it; still validated against current balances |
| 4 | AI drafts existed only in the HTTP response; confirm took a **raw client payload** | Server-stored drafts (`ai_actions`); confirm takes only a draft id, re-validates, is idempotent |
| 5 | Any logged-in user could **mark someone else's payment as paid** (`/simulate` had no ownership check) | Only the debtor; others get 404 |
| 6 | Idempotency key not tied to a settlement; two payments could be opened for one settlement | Key bound to one settlement (409 on reuse); one live payment per settlement; stale suggestions are re-validated before payment |
| 7 | A late webhook could overwrite a final payment state and re-open a completed settlement | Terminal states are immutable; late events are ignored; concurrent duplicate deliveries resolve to `duplicate_ignored` |
| 8 | A non-ASCII webhook signature header could raise (500); a signed-but-malformed body was not handled | 401 / clean 4xx |
| 9 | Cache invalidated outside the commit boundary; cache used for decisions | Invalidate after commit only (never on rollback); decisions read PostgreSQL; Redis outage backs off |
| 10 | Duplicate participants ("Anwi" + "You") could become two shares | Alias resolution + de-duplication by user id |
| 11 | Equal-balance ties made settlement suggestions non-reproducible | Deterministic tie-break by user id |
| 12 | Money inputs with 3 decimals slipped through (`10.005`) and broke `sum(shares) == total` | Rejected at the schema; `assert`-based checks replaced by real errors |
| 13 | Missing token returned 403 instead of 401 | 401 |
| 14 | `test_agent_participants.py` tested re-implemented logic, not the real code | Replaced by tests of the real agent |

## Features added

- Group delete (transactional cascade; blocked while a payment is in flight), rename, leave / remove member
- Expense edit; duplicate-group-name prompt ("Create anyway"); simplified `debts` on the group page
- Manual settlement ("Mark as paid") and transaction history that includes it
- AI draft/confirm/cancel/history endpoints; clarification buttons; deterministic intents that work without Ollama
- Alembic migrations (idempotent baseline + `0002_ledger_ai`); backend runs them on container start
- Frontend: confirmation dialogs, toasts, loading / empty / error states, edit-expense route, resume payment
- Tests: backend ~100 (was 37); frontend 18 UI tests; two real-PostgreSQL scripts

## Files (high level)

- **Backend new:** `services/{balance_math,balance_service,group_service,draft_service}.py`, `core/errors.py`,
  `models/ai_action.py`, `alembic/**`
- **Backend rewritten:** `services/{agent,expense,settlement,payment,split,auth}_service.py`, `core/{cache,config,deps}.py`,
  all route and schema modules
- **Frontend new:** `components/{ConfirmDialog,PageState}.jsx`, `context/ToastContext.jsx`, `utils/errors.js`, `__tests__/**`
- **Frontend changed:** `pages/{AI,GroupDetails,Groups,AddExpense,Settlements,Dashboard,Transactions,TransactionDetails}.jsx`,
  `App.jsx`, `main.jsx` (visual design, colours and dark-mode CSS untouched)
- **Ops/docs:** `docker-compose.yml`, `backend/Dockerfile`, `backend/.env.example`, `README.md`, `docs/*`, `scripts/*_pg.py`

## Behaviour changes to be aware of

- After upgrading, groups with COMPLETED settlements show lower balances — that is the fix for bug 1.
- The old `/ai/expense/confirm` and `/ai/settlement/confirm` endpoints are gone (replaced by `/ai/drafts/{id}/confirm`).
- Only the group creator can rename or delete a group; a member with a non-zero balance can't leave or be removed.
- `HTTPBearer` now returns 401 (not 403) when the token is missing.
