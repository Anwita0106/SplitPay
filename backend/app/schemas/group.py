import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserOut


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    member_emails: list[str] = Field(
        default_factory=list,
        description="Emails of existing users to add as members alongside the creator.",
    )
    allow_duplicate: bool = Field(
        default=False,
        description="Set true to knowingly create a second group with a name you already use.",
    )


class GroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class AddMemberRequest(BaseModel):
    email: EmailStr


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    created_at: datetime
    member_count: int = 0
    member_names: list[str] = Field(default_factory=list)


class GroupMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user: UserOut
    joined_at: datetime


class BalanceEntry(BaseModel):
    """net_balance: positive = is owed money, negative = owes money (Decimal as string)."""

    user: UserOut
    net_balance: str


class DebtEntry(BaseModel):
    """`from_user` owes `to_user` `amount` — the simplified 'who pays whom'."""

    from_user: UserOut
    to_user: UserOut
    amount: str


class GroupDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    created_at: datetime
    members: list[GroupMemberOut]
    balances: list[BalanceEntry]
    debts: list[DebtEntry] = Field(default_factory=list)


class GroupDeleteOut(BaseModel):
    id: str
    name: str
    deleted: dict[str, int]
