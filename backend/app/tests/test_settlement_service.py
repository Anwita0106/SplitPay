import uuid
from decimal import Decimal

from app.services.settlement_service import compute_net_balances, simplify_settlements


def make_uuids(n):
    return [uuid.uuid4() for _ in range(n)]


def test_compute_net_balances_goa_trip_example():
    # Matches the worked example from the project brief:
    # Anwita pays 4000 for hotel, split equally across 4 people.
    anwita, rahul, priya, arjun = make_uuids(4)
    expense_id = uuid.uuid4()

    expenses = [{"id": expense_id, "paid_by": anwita, "total_amount": Decimal("4000")}]
    splits_by_expense = {
        expense_id: [
            {"user_id": anwita, "amount": Decimal("1000")},
            {"user_id": rahul, "amount": Decimal("1000")},
            {"user_id": priya, "amount": Decimal("1000")},
            {"user_id": arjun, "amount": Decimal("1000")},
        ]
    }

    balances = compute_net_balances(expenses, splits_by_expense)
    assert balances[anwita] == Decimal("3000")
    assert balances[rahul] == Decimal("-1000")
    assert balances[priya] == Decimal("-1000")
    assert balances[arjun] == Decimal("-1000")


def test_compute_net_balances_settled_users_are_dropped():
    a, b = make_uuids(2)
    expense_id = uuid.uuid4()
    expenses = [{"id": expense_id, "paid_by": a, "total_amount": Decimal("100")}]
    splits_by_expense = {expense_id: [{"user_id": a, "amount": Decimal("100")}]}  # a pays for themself only
    balances = compute_net_balances(expenses, splits_by_expense)
    assert balances == {}


def test_simplify_settlements_single_creditor_multiple_debtors():
    a, b, c, d = make_uuids(4)
    balances = {
        a: Decimal("3000"),
        b: Decimal("-1500"),
        c: Decimal("-1000"),
        d: Decimal("-500"),
    }
    result = simplify_settlements(balances)

    assert len(result) == 3
    total_transferred = sum(r["amount"] for r in result)
    assert total_transferred == Decimal("3000")
    for r in result:
        assert r["to_user"] == a
    debtor_amounts = {r["from_user"]: r["amount"] for r in result}
    assert debtor_amounts[b] == Decimal("1500")
    assert debtor_amounts[c] == Decimal("1000")
    assert debtor_amounts[d] == Decimal("500")


def test_simplify_settlements_minimizes_transaction_count():
    # 4 people with non-zero balances should never need more than 3 (n-1) transactions.
    a, b, c, d = make_uuids(4)
    balances = {a: Decimal("100"), b: Decimal("50"), c: Decimal("-30"), d: Decimal("-120")}
    result = simplify_settlements(balances)
    assert len(result) <= 3


def test_simplify_settlements_every_transfer_amount_is_positive():
    a, b = make_uuids(2)
    balances = {a: Decimal("500"), b: Decimal("-500")}
    result = simplify_settlements(balances)
    assert len(result) == 1
    assert result[0] == {"from_user": b, "to_user": a, "amount": Decimal("500")}


def test_simplify_settlements_empty_balances_returns_empty():
    assert simplify_settlements({}) == []


def test_simplify_settlements_conserves_total_money():
    a, b, c = make_uuids(3)
    balances = {a: Decimal("700"), b: Decimal("-200"), c: Decimal("-500")}
    result = simplify_settlements(balances)
    assert sum(r["amount"] for r in result) == Decimal("700")
