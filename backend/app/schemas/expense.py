import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExpenseSplitInput(BaseModel):
    user_id: uuid.UUID
    amount: Optional[Decimal] = None       # required for split_type = EXACT
    percentage: Optional[Decimal] = None   # required for split_type = PERCENTAGE


class ExpenseCreate(BaseModel):
    group_id: uuid.UUID
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

    @model_validator(mode="after")
    def check_shape(self) -> "ExpenseCreate":
        if self.split_type == "EQUAL" and not self.participant_ids:
            raise ValueError("participant_ids is required for an EQUAL split.")
        if self.split_type in ("PERCENTAGE", "EXACT") and not self.splits:
            raise ValueError(f"splits is required for a {self.split_type} split.")
        return self


class ExpenseSplitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: uuid.UUID
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
    created_at: datetime
    splits: list[ExpenseSplitOut]
