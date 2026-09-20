# SplitPay AI — Phase 2 & Phase 3 (confirmation-gated actions)

Full design: [`AI_AGENT.md`](AI_AGENT.md). This page is the short walkthrough.

## Phase 2: natural-language expense creation

> I paid ₹2400 for dinner with Anwi and Anwita in Goa Trip. Split it equally.

1. `/ai/chat` resolves **Goa Trip** to one group UUID (or asks which one if several share the name).
2. Participants are resolved against the group's real members; "Anwi" and "you" are the same person → 2 shares.
3. The backend computes the exact `Decimal` split (₹1200 + ₹1200) and stores a **PENDING draft**.
4. React shows a draft card: description, payer, each share, assumptions (e.g. "Split equally among all 3 members").
   **Nothing is saved.**
5. **Confirm expense** → `POST /ai/drafts/{draft_id}/confirm` → the same `expense_service` used by `POST /expenses`.
   Confirming again returns the first result; the expense is never duplicated.

## Phase 3: AI-assisted settlement

> Who owes me money?   →  Anwita owes you ₹1200 in Goa Trip.
> I want to settle the ₹1200 Anwita owes me.

- The draft is validated against current balances (in-flight UPI payments included) and can be started by the
  debtor **or** the creditor. Amounts above what is owed are refused with a plain sentence.
- Confirming records the settlement as **paid outside SplitPay** and balances update immediately;
  the next "Who owes me money?" answers "No one currently owes you money…".
- UPI payments (order → webhook → status) remain in the Settlements page and are unchanged by the AI.

## Draft lifecycle

`PENDING → CONFIRMED | CANCELLED | EXPIRED | FAILED` (persisted in `ai_actions`; expiry is `AI_DRAFT_TTL_MINUTES`).

```text
LLM / parser -> prepare_* -> draft (server payload) -> user clicks Confirm -> validated service -> PostgreSQL
```
