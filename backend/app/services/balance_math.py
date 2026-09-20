"""
Pure balance math (no database, no framework). Everything here works on plain
dicts / Decimals so it is trivially unit-testable.

CANONICAL SIGN CONVENTION — used by every layer of SplitPay (API, UI, AI):

    balance  > 0   the person is OWED money    ("gets back")
    balance  < 0   the person OWES money       ("owes")
    balance == 0   settled (omitted from results)

    For each expense:   payer   += total_amount
                        each participant -= their share
    For each COMPLETED settlement (from_user paid to_user `amount`):
                        from_user += amount     (owes less)
                        to_user   -= amount     (is owed less)

The sum of all balances in a group is always exactly zero.

Complexity (for the interview):
- compute_net_balances: O(E + S) single pass over splits and settlements.
- simplify_settlements: O(n log n) for n users with a non-zero balance;
  the matching loop is O(n) because each iteration fully resolves at least one
  side. Greedy largest-creditor / largest-debtor matching is the standard
  practical solution (the true minimum is NP-hard); it produces at most n-1
  transfers and is fully deterministic.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional
from uuid import UUID


def compute_net_balances(
    expenses: list[dict],
    splits_by_expense: dict[UUID, list[dict]],
    settlements: Optional[Iterable[dict]] = None,
) -> dict[UUID, Decimal]:
    """
    expenses:          [{"id", "paid_by", "total_amount"}, ...]
    splits_by_expense: {expense_id: [{"user_id", "amount"}, ...]}
    settlements:       [{"from_user", "to_user", "amount"}, ...]  (already filtered
                       to the statuses that should count as money moved)

    Returns {user_id: net_balance}; zero balances are dropped.
    """
    balances: dict[UUID, Decimal] = {}

    for expense in expenses:
        payer = expense["paid_by"]
        balances[payer] = balances.get(payer, Decimal("0")) + expense["total_amount"]
        for split in splits_by_expense.get(expense["id"], []):
            uid = split["user_id"]
            balances[uid] = balances.get(uid, Decimal("0")) - split["amount"]

    for s in settlements or ():
        balances[s["from_user"]] = balances.get(s["from_user"], Decimal("0")) + s["amount"]
        balances[s["to_user"]] = balances.get(s["to_user"], Decimal("0")) - s["amount"]

    return {uid: bal for uid, bal in balances.items() if bal != 0}


def simplify_settlements(balances: dict[UUID, Decimal]) -> list[dict]:
    """
    Greedy debt simplification: repeatedly match the largest creditor with the
    largest debtor and transfer min(credit, debt). Ties are broken by user id so
    the same balances ALWAYS yield the same transfers (reproducible tests, and
    a settlement suggestion that doesn't reshuffle between recomputations).
    """
    creditors = sorted(
        ((uid, bal) for uid, bal in balances.items() if bal > 0),
        key=lambda item: (-item[1], str(item[0])),
    )
    debtors = sorted(
        ((uid, -bal) for uid, bal in balances.items() if bal < 0),
        key=lambda item: (-item[1], str(item[0])),
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
