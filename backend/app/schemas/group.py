import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserOut


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    member_emails: list[str] = Field(
        default_factory=list,
        description="Emails of existing users to add as members alongside the creator.",
    )


class AddMemberRequest(BaseModel):
    email: str


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    created_at: datetime


class GroupMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user: UserOut
    joined_at: datetime


class BalanceEntry(BaseModel):
    user: UserOut
    net_balance: str  # Decimal serialized as string to avoid float precision issues in JSON


class GroupDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    created_at: datetime
    members: list[GroupMemberOut]
    balances: list[BalanceEntry]
