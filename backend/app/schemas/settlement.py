import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserOut


class SettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    group_id: uuid.UUID
    from_user: uuid.UUID
    to_user: uuid.UUID
    amount: Decimal
    status: str
    created_at: datetime


class SettlementDetailOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    debtor: UserOut
    creditor: UserOut
    amount: Decimal
    status: str
    created_at: datetime
