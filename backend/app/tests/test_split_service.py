import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.schemas.expense import ExpenseCreate, ExpenseSplitInput
from app.services.split_service import (
    calculate_equal_split,
    calculate_exact_split,
    calculate_percentage_split,
)


def make_uuids(n):
    return [uuid.uuid4() for _ in range(n)]


def test_equal_split_divides_evenly():
    a, b, c = make_uuids(3)
    shares = calculate_equal_split(Decimal("3000"), [a, b, c])
    assert shares[a] == shares[b] == shares[c] == Decimal("1000.00")
    assert sum(shares.values()) == Decimal("3000")


def test_equal_split_distributes_remainder_deterministically():
    # 1000 / 3 = 333.33333... -> remainder must be spread as whole paise,
    # sum must equal the original amount exactly, no floats involved.
    a, b, c = make_uuids(3)
    shares = calculate_equal_split(Decimal("1000"), [a, b, c])
    assert sum(shares.values()) == Decimal("1000.00")
    # first participants absorb the extra paisa
    values = sorted(shares.values(), reverse=True)
    assert values[0] - values[-1] <= Decimal("0.01")


def test_equal_split_no_participants_raises():
    with pytest.raises(HTTPException):
        calculate_equal_split(Decimal("100"), [])


def test_percentage_split_sums_to_total():
    a, b, c = make_uuids(3)
    splits = [
        ExpenseSplitInput(user_id=a, percentage=Decimal("50")),
        ExpenseSplitInput(user_id=b, percentage=Decimal("30")),
        ExpenseSplitInput(user_id=c, percentage=Decimal("20")),
    ]
    shares = calculate_percentage_split(Decimal("1000"), splits)
    assert shares[a] == Decimal("500.00")
    assert shares[b] == Decimal("300.00")
    assert shares[c] == Decimal("200.00")
    assert sum(shares.values()) == Decimal("1000.00")


def test_percentage_split_not_summing_to_100_raises():
    a, b = make_uuids(2)
    splits = [
        ExpenseSplitInput(user_id=a, percentage=Decimal("50")),
        ExpenseSplitInput(user_id=b, percentage=Decimal("40")),  # 90, not 100
    ]
    with pytest.raises(HTTPException):
        calculate_percentage_split(Decimal("1000"), splits)


def test_exact_split_matching_total_passes():
    a, b, c = make_uuids(3)
    splits = [
        ExpenseSplitInput(user_id=a, amount=Decimal("500")),
        ExpenseSplitInput(user_id=b, amount=Decimal("1000")),
        ExpenseSplitInput(user_id=c, amount=Decimal("1500")),
    ]
    shares = calculate_exact_split(Decimal("3000"), splits)
    assert shares[a] == Decimal("500.00")
    assert sum(shares.values()) == Decimal("3000.00")


def test_exact_split_not_matching_total_raises():
    a, b = make_uuids(2)
    splits = [
        ExpenseSplitInput(user_id=a, amount=Decimal("500")),
        ExpenseSplitInput(user_id=b, amount=Decimal("400")),  # doesn't sum to 1000
    ]
    with pytest.raises(HTTPException):
        calculate_exact_split(Decimal("1000"), splits)


def test_exact_split_negative_amount_raises():
    a, b = make_uuids(2)
    splits = [
        ExpenseSplitInput(user_id=a, amount=Decimal("-100")),
        ExpenseSplitInput(user_id=b, amount=Decimal("1100")),
    ]
    with pytest.raises(HTTPException):
        calculate_exact_split(Decimal("1000"), splits)


def test_expense_create_requires_participant_ids_for_equal_split():
    with pytest.raises(ValueError):
        ExpenseCreate(
            group_id=uuid.uuid4(),
            description="Hotel",
            total_amount=Decimal("100"),
            split_type="EQUAL",
            paid_by=uuid.uuid4(),
            participant_ids=[],
        )
