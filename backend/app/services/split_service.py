"""
SplitService — turns an expense + a split strategy into a list of
(user_id, amount) rows that sum EXACTLY to total_amount.

All money math uses Decimal, never float. Decimal is deterministic and
exact for base-10 currency values; float introduces binary rounding error
(0.1 + 0.2 != 0.3) that is unacceptable once real money is involved.
"""

from decimal import ROUND_DOWN, Decimal
from uuid import UUID

from fastapi import HTTPException, status

from app.schemas.expense import ExpenseCreate, ExpenseSplitInput

TWO_PLACES = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_DOWN)


def calculate_equal_split(total_amount: Decimal, participant_ids: list[UUID]) -> dict[UUID, Decimal]:
    """
    Splits total_amount evenly across participants. Because paise/cents don't
    always divide evenly (e.g. ₹1000 / 3 = ₹333.33333...), the remainder left
    over after equal-flooring every share is distributed one paisa at a time
    to the first N participants (deterministic by participant order), so the
    sum of all shares is always EXACTLY total_amount.
    """
    n = len(participant_ids)
    if n == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one participant is required.")

    base_share = _round_money(total_amount / n)
    shares = {uid: base_share for uid in participant_ids}

    distributed = base_share * n
    remainder = _round_money(total_amount - distributed)  # smallest currency unit remainder, e.g. Decimal("0.03")

    if remainder != 0:
        # Distribute leftover paise one at a time, in participant order, until exhausted.
        step = Decimal("0.01") if remainder > 0 else Decimal("-0.01")
        remaining_units = int((remainder / step).to_integral_value())
        for uid in participant_ids[:remaining_units]:
            shares[uid] = _round_money(shares[uid] + step)

    assert sum(shares.values()) == total_amount, "Equal split must sum exactly to total_amount"
    return shares


def calculate_percentage_split(
    total_amount: Decimal, splits: list[ExpenseSplitInput]
) -> dict[UUID, Decimal]:
    total_pct = sum((s.percentage or Decimal(0)) for s in splits)
    if total_pct != Decimal("100"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Percentages must sum to 100, got {total_pct}.",
        )

    shares: dict[UUID, Decimal] = {}
    running_total = Decimal("0")
    for i, s in enumerate(splits):
        if s.percentage is None or s.percentage < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Each split needs a non-negative percentage.")
        if i == len(splits) - 1:
            # Last participant absorbs any rounding remainder so the total is exact.
            amount = _round_money(total_amount - running_total)
        else:
            amount = _round_money(total_amount * s.percentage / Decimal("100"))
        shares[s.user_id] = amount
        running_total += amount

    assert sum(shares.values()) == total_amount, "Percentage split must sum exactly to total_amount"
    return shares


def calculate_exact_split(total_amount: Decimal, splits: list[ExpenseSplitInput]) -> dict[UUID, Decimal]:
    shares: dict[UUID, Decimal] = {}
    running_total = Decimal("0")
    for s in splits:
        if s.amount is None or s.amount < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Each split needs a non-negative amount.")
        shares[s.user_id] = _round_money(s.amount)
        running_total += shares[s.user_id]

    if running_total != total_amount:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Exact split amounts ({running_total}) must sum to total_amount ({total_amount}).",
        )
    return shares


def calculate_splits(expense_in: ExpenseCreate) -> dict[UUID, Decimal]:
    """Dispatches to the right strategy based on expense_in.split_type."""
    if expense_in.split_type == "EQUAL":
        return calculate_equal_split(expense_in.total_amount, expense_in.participant_ids)
    if expense_in.split_type == "PERCENTAGE":
        return calculate_percentage_split(expense_in.total_amount, expense_in.splits)
    if expense_in.split_type == "EXACT":
        return calculate_exact_split(expense_in.total_amount, expense_in.splits)
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown split_type {expense_in.split_type}")
