"""
BalanceService — THE canonical source of group balances.

Every consumer (REST group page, dashboard, settlement validation, payment
creation, the AI agent and its drafts) obtains balances from here. Nothing else
in the codebase computes balances, and the AI never computes any itself.
See balance_math.py for the sign convention.

Which settlements count?
  COMPLETED   money has moved (UPI success, or a member recorded it)  -> always counted
  PROCESSING  a UPI payment is in flight                              -> counted only when
              `include_in_flight=True` (used when validating/creating settlements and when
              generating suggestions, so the same debt can't be paid twice)
  PENDING / CANCELLED  suggestions / dead rows                        -> never counted
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.cache import cache_get_json, cache_set_json, group_summary_cache_key
from app.models.expense import Expense
from app.models.expense_split import ExpenseSplit
from app.models.settlement import Settlement
from app.services.balance_math import compute_net_balances, simplify_settlements

ZERO = Decimal("0")


@dataclass(frozen=True)
class Debt:
    """`from_user` owes `to_user` `amount` (always positive)."""

    from_user: UUID
    to_user: UUID
    amount: Decimal


@dataclass
class GroupBalances:
    group_id: UUID
    balances: dict[UUID, Decimal] = field(default_factory=dict)
    debts: list[Debt] = field(default_factory=list)

    def position(self, user_id: UUID) -> Decimal:
        """Signed net balance: > 0 is owed money, < 0 owes money, 0 settled."""
        return self.balances.get(user_id, ZERO)

    def owed_to(self, user_id: UUID) -> list[Debt]:
        """Debts where others owe `user_id`."""
        return [d for d in self.debts if d.to_user == user_id]

    def owed_by(self, user_id: UUID) -> list[Debt]:
        """Debts where `user_id` owes others."""
        return [d for d in self.debts if d.from_user == user_id]


def build_snapshot(group_id: UUID, balances: dict[UUID, Decimal]) -> GroupBalances:
    debts = [Debt(d["from_user"], d["to_user"], d["amount"]) for d in simplify_settlements(balances)]
    return GroupBalances(group_id=group_id, balances=balances, debts=debts)


def _load_balances_from_db(
    db: Session,
    group_id: UUID,
    include_in_flight: bool,
    exclude_settlement_id: Optional[UUID],
) -> dict[UUID, Decimal]:
    # Two set-based queries (no per-expense N+1), summed in Python with Decimal.
    expense_rows = (
        db.query(Expense.id, Expense.paid_by, Expense.total_amount).filter(Expense.group_id == group_id).all()
    )
    split_rows = (
        db.query(ExpenseSplit.expense_id, ExpenseSplit.user_id, ExpenseSplit.amount)
        .join(Expense, Expense.id == ExpenseSplit.expense_id)
        .filter(Expense.group_id == group_id)
        .all()
    )
    splits_by_expense: dict[UUID, list[dict]] = {}
    for expense_id, user_id, amount in split_rows:
        splits_by_expense.setdefault(expense_id, []).append({"user_id": user_id, "amount": Decimal(amount)})

    counted = ["COMPLETED"] + (["PROCESSING"] if include_in_flight else [])
    q = db.query(Settlement.from_user, Settlement.to_user, Settlement.amount).filter(
        Settlement.group_id == group_id, Settlement.status.in_(counted)
    )
    if exclude_settlement_id is not None:
        q = q.filter(Settlement.id != exclude_settlement_id)
    settlement_rows = [
        {"from_user": f, "to_user": t, "amount": Decimal(a)} for f, t, a in q.all()
    ]

    return compute_net_balances(
        [{"id": i, "paid_by": p, "total_amount": Decimal(t)} for i, p, t in expense_rows],
        splits_by_expense,
        settlement_rows,
    )


def get_group_balances(
    db: Session,
    group_id: UUID,
    *,
    use_cache: bool = False,
    include_in_flight: bool = False,
    exclude_settlement_id: Optional[UUID] = None,
) -> GroupBalances:
    """
    Authoritative balances for a group, read straight from PostgreSQL.

    `use_cache=True` is allowed ONLY for display reads (the group page). It is
    ignored whenever `include_in_flight` / `exclude_settlement_id` is used,
    because those calls exist to make decisions.
    """
    cacheable = use_cache and not include_in_flight and exclude_settlement_id is None
    if cacheable:
        cached = cache_get_json(group_summary_cache_key(str(group_id)))
        if cached is not None:
            try:
                return build_snapshot(group_id, {UUID(k): Decimal(v) for k, v in cached.items()})
            except (ValueError, ArithmeticError):
                pass  # corrupt cache entry -> fall through to the database

    balances = _load_balances_from_db(db, group_id, include_in_flight, exclude_settlement_id)
    if cacheable:
        cache_set_json(group_summary_cache_key(str(group_id)), {str(k): str(v) for k, v in balances.items()})
    return build_snapshot(group_id, balances)


# ---------------------------------------------------------------------------
# Human-readable translation (used by the API and the AI so nobody ever
# shows a raw negative number like "owed -1200").
# ---------------------------------------------------------------------------
def position_status(amount: Decimal) -> str:
    if amount > 0:
        return "OWED"
    if amount < 0:
        return "OWES"
    return "SETTLED"


def format_inr(amount: Decimal) -> str:
    """₹1200, ₹1200.50 — whole rupees drop the '.00'; never a sign."""
    amount = abs(Decimal(amount)).quantize(Decimal("0.01"))
    text = f"{amount:.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    return f"₹{text}"
