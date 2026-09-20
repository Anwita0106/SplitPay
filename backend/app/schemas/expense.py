import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# NUMERIC(12,2) holds at most 10 integer digits.
MAX_MONEY = Decimal("9999999999.99")


def validate_money(value: Decimal, *, label: str = "Amount") -> Decimal:
    """
    Money must be an exact number of paise. Rejecting a third decimal place is
    what guarantees `sum(shares) == total` later: without it, 100.005 would be
    floor-split to 100.00 but stored by PostgreSQL as 100.01.
    """
    if not value.is_finite():
        raise ValueError(f"{label} must be a finite number.")
    if value.as_tuple().exponent < -2:
        raise ValueError(f"{label} can have at most 2 decimal places.")
    if value > MAX_MONEY:
        raise ValueError(f"{label} is too large.")
    return value


class ExpenseSplitInput(BaseModel):
    user_id: uuid.UUID
    amount: Optional[Decimal] = None       # required for split_type = EXACT
    percentage: Optional[Decimal] = None   # required for split_type = PERCENTAGE

    @field_validator("amount")
    @classmethod
    def _amount_ok(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return None if v is None else validate_money(v, label="Split amount")

    @field_validator("percentage")
    @classmethod
    def _pct_ok(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return v
        if not v.is_finite() or v.as_tuple().exponent < -2:
            raise ValueError("Percentage can have at most 2 decimal places.")
        if v < 0 or v > 100:
            raise ValueError("Percentage must be between 0 and 100.")
        return v


class ExpenseBase(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    total_amount: Decimal = Field(gt=0)
    split_type: Literal["EQUAL", "PERCENTAGE", "EXACT"]
    paid_by: uuid.UUID
    participant_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Used for EQUAL splits — who shares the expense."
    )
    splits: list[ExpenseSplitInput] = Field(
        default_factory=list, description="Used for PERCENTAGE and EXACT splits."
    )

    @field_validator("description")
    @classmethod
    def _desc_ok(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Description cannot be blank.")
        return v

    @field_validator("total_amount")
    @classmethod
    def _total_ok(cls, v: Decimal) -> Decimal:
        return validate_money(v, label="Total amount")

    @model_validator(mode="after")
    def check_shape(self):
        if self.split_type == "EQUAL":
            if not self.participant_ids:
                raise ValueError("participant_ids is required for an EQUAL split.")
        elif not self.splits:
            raise ValueError(f"splits is required for a {self.split_type} split.")
        return self


class ExpenseCreate(ExpenseBase):
    group_id: uuid.UUID


class ExpenseUpdate(ExpenseBase):
    """Full replacement of an expense's editable fields. The group can't change."""


class ExpenseSplitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: uuid.UUID
    user_name: Optional[str] = None
    amount: Decimal
    percentage: Optional[Decimal] = None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    group_id: uuid.UUID
    description: str
    total_amount: Decimal
    split_type: str
    paid_by: uuid.UUID
    paid_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    splits: list[ExpenseSplitOut]
