import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserOut


class SettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    group_id: uuid.UUID
    from_user: uuid.UUID
    to_user: uuid.UUID
    from_name: Optional[str] = None
    to_name: Optional[str] = None
    amount: Decimal
    status: str
    method: str = "UPI"
    recorded_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SettlementDetailOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    debtor: UserOut
    creditor: UserOut
    amount: Decimal
    status: str
    method: str = "UPI"
    created_at: datetime


class SettlementRecordRequest(BaseModel):
    """Record that `from_user` paid `to_user` outside SplitPay."""

    from_user: uuid.UUID
    to_user: uuid.UUID
    amount: Decimal
