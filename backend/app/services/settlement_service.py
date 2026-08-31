"""
SettlementService

Two responsibilities:
1. compute_net_balances — sum(paid) - sum(owed) per user in a group.
2. simplify_settlements  — turn a set of net balances into the minimum
   number of "who pays whom" transactions using a greedy
   largest-creditor / largest-debtor matching algorithm.

Complexity (for the interview):
- compute_net_balances: O(E) where E = number of expense_splits in the group
  (one pass to accumulate paid amounts, one pass to subtract owed amounts).
- simplify_settlements: O(n log n) where n = number of users with a non-zero
  balance — sorting dominates; the matching loop itself is O(n) because
  every iteration fully resolves at least one side of the match.
  Space is O(n) for the balance lists.

This is NOT the theoretical minimum-transaction solution (that's NP-hard in
general — it's equivalent to a minimum-cost flow / subset-sum-like matching
problem). The greedy largest-vs-largest approach is the standard practical
solution used in real expense-splitting apps: deterministic, easy to reason
about and explain, and produces at most (n - 1) transactions for n people
with non-zero balances — already a strong simplification over the naive
"everyone pays everyone" approach.
"""

from decimal import Decimal
from uuid import UUID


def compute_net_balances(
    expenses: list[dict], splits_by_expense: dict[UUID, list[dict]]
) -> dict[UUID, Decimal]:
    """
    expenses: [{"id": UUID, "paid_by": UUID, "total_amount": Decimal}, ...]
    splits_by_expense: {expense_id: [{"user_id": UUID, "amount": Decimal}, ...]}

    Returns {user_id: net_balance}. Positive = is owed money (creditor).
    Negative = owes money (debtor).
    """
    balances: dict[UUID, Decimal] = {}

    for expense in expenses:
        payer = expense["paid_by"]
        balances[payer] = balances.get(payer, Decimal("0")) + expense["total_amount"]

        for split in splits_by_expense.get(expense["id"], []):
            uid = split["user_id"]
            balances[uid] = balances.get(uid, Decimal("0")) - split["amount"]

    # Users who net to exactly zero are settled — nothing to show.
    return {uid: bal for uid, bal in balances.items() if bal != 0}


def simplify_settlements(balances: dict[UUID, Decimal]) -> list[dict]:
    """
    Greedy debt simplification.

    1. Split users into creditors (balance > 0) and debtors (balance < 0).
    2. Sort each list by magnitude, descending.
    3. Repeatedly match the largest creditor with the largest debtor:
       transfer min(|creditor balance|, |debtor balance|).
    4. Reduce both balances by the transferred amount; advance past
       whichever side hit zero; repeat until both lists are exhausted.

    Deterministic given the same input balances, which matters both for
    reproducible test assertions and for a settlement suggestion the group
    can trust is consistent every time it's recomputed.
    """
    creditors = sorted(
        ((uid, bal) for uid, bal in balances.items() if bal > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    debtors = sorted(
        ((uid, -bal) for uid, bal in balances.items() if bal < 0),  # stored as a positive owed amount
        key=lambda item: item[1],
        reverse=True,
    )

    settlements: list[dict] = []
    i, j = 0, 0

    while i < len(creditors) and j < len(debtors):
        creditor_id, credit_amount = creditors[i]
        debtor_id, debt_amount = debtors[j]

        transfer = min(credit_amount, debt_amount)
        if transfer > 0:
            settlements.append({"from_user": debtor_id, "to_user": creditor_id, "amount": transfer})

        credit_amount -= transfer
        debt_amount -= transfer
        creditors[i] = (creditor_id, credit_amount)
        debtors[j] = (debtor_id, debt_amount)

        if credit_amount == 0:
            i += 1
        if debt_amount == 0:
            j += 1

    return settlements
