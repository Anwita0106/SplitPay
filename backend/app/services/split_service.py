"""
SplitService — turns an expense + a split strategy into a {user_id: amount}
mapping whose values sum EXACTLY to total_amount.

All money math uses Decimal, never float: Decimal is exact for base-10
currency; float has binary rounding error (0.1 + 0.2 != 0.3).

Every failure is a DomainError (HTTP 422) — never an `assert`, which would
surface as a 500 and disappear entirely under `python -O`.
"""
from decimal import ROUND_DOWN, Decimal
from uuid import UUID

from app.core.errors import invalid
from app.schemas.expense import ExpenseBase, ExpenseSplitInput

TWO_PLACES = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_DOWN)


def dedupe_preserving_order(ids: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    out: list[UUID] = []
    for uid in ids:
        if uid not in seen:
            seen.add(uid)
            out.append(uid)
    return out


def calculate_equal_split(total_amount: Decimal, participant_ids: list[UUID]) -> dict[UUID, Decimal]:
    """
    Splits total_amount evenly. When paise don't divide evenly (₹100 / 3 =
    33.333…), every share is floored to 33.33 and the leftover paise are handed
    out one at a time to the first participants in order, so ₹100 / 3 becomes
    33.34 + 33.33 + 33.33 and the shares always sum to exactly the total.

    The same person listed twice is ONE participant (a duplicate would
    otherwise silently shrink everyone's share or, worse, be dropped by the
    dict and break the sum).
    """
    participants = dedupe_preserving_order(participant_ids)
    n = len(participants)
    if n == 0:
        raise invalid("At least one participant is required.")

    base_share = _round_money(total_amount / n)
    shares = {uid: base_share for uid in participants}

    remainder = total_amount - base_share * n  # a whole number of paise, 0 <= r < n paise
    extra_paise = int((remainder / TWO_PLACES).to_integral_value())
    for uid in participants[:extra_paise]:
        shares[uid] = shares[uid] + TWO_PLACES

    if sum(shares.values()) != total_amount:  # defensive; unreachable for valid input
        raise invalid("Could not split this amount exactly. Please check the amount.")
    return shares


def _reject_duplicate_users(splits: list[ExpenseSplitInput]) -> None:
    ids = [s.user_id for s in splits]
    if len(ids) != len(set(ids)):
        raise invalid("Each person can appear only once in a split.")


def calculate_percentage_split(
    total_amount: Decimal, splits: list[ExpenseSplitInput]
) -> dict[UUID, Decimal]:
    _reject_duplicate_users(splits)
    total_pct = sum((s.percentage or Decimal(0)) for s in splits)
    if total_pct != Decimal("100"):
        raise invalid(f"Percentages must sum to 100, got {total_pct}.")

    shares: dict[UUID, Decimal] = {}
    running_total = Decimal("0")
    for i, s in enumerate(splits):
        if s.percentage is None or s.percentage < 0:
            raise invalid("Each split needs a non-negative percentage.")
        if i == len(splits) - 1:
            # Last participant absorbs the rounding remainder so the total is exact.
            amount = _round_money(total_amount - running_total)
        else:
            amount = _round_money(total_amount * s.percentage / Decimal("100"))
        shares[s.user_id] = amount
        running_total += amount

    if sum(shares.values()) != total_amount:
        raise invalid("Could not split this amount exactly. Please check the percentages.")
    return shares


def calculate_exact_split(total_amount: Decimal, splits: list[ExpenseSplitInput]) -> dict[UUID, Decimal]:
    _reject_duplicate_users(splits)
    shares: dict[UUID, Decimal] = {}
    running_total = Decimal("0")
    for s in splits:
        if s.amount is None or s.amount < 0:
            raise invalid("Each split needs a non-negative amount.")
        shares[s.user_id] = _round_money(s.amount)
        running_total += shares[s.user_id]

    if running_total != total_amount:
        raise invalid(f"Exact split amounts ({running_total}) must sum to the total amount ({total_amount}).")
    return shares


def calculate_splits(expense_in: ExpenseBase) -> dict[UUID, Decimal]:
    """Dispatches to the right strategy based on expense_in.split_type."""
    if expense_in.split_type == "EQUAL":
        return calculate_equal_split(expense_in.total_amount, expense_in.participant_ids)
    if expense_in.split_type == "PERCENTAGE":
        return calculate_percentage_split(expense_in.total_amount, expense_in.splits)
    if expense_in.split_type == "EXACT":
        return calculate_exact_split(expense_in.total_amount, expense_in.splits)
    raise invalid(f"Unknown split_type {expense_in.split_type}")
