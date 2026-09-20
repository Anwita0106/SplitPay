import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.expense import ExpenseCreate, ExpenseOut
from app.schemas.settlement import SettlementOut


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # The UI sends the whole visible transcript; the server keeps only the tail.
    conversation: list[dict[str, str]] = Field(default_factory=list)
    # An unambiguous group chosen in the UI (e.g. the user clicked one of two
    # identically-named groups). Used to break ties; never a substitute for validation.
    group_id: Optional[uuid.UUID] = None


class ExpenseDraftParticipant(BaseModel):
    user_id: uuid.UUID
    name: str
    amount: Decimal


class ExpenseDraft(BaseModel):
    """A PREPARED (not saved) expense. Only confirming `draft_id` writes anything."""

    draft_id: uuid.UUID
    expires_at: datetime
    expense: ExpenseCreate
    group_name: str
    paid_by_name: str
    participants: list[ExpenseDraftParticipant]
    assumptions: list[str] = Field(default_factory=list)


class SettlementDraft(BaseModel):
    """A PREPARED (not saved) settlement. Only confirming `draft_id` writes anything."""

    draft_id: uuid.UUID
    expires_at: datetime
    group_id: uuid.UUID
    group_name: str
    from_user: uuid.UUID
    from_name: str
    to_user: uuid.UUID
    to_name: str
    amount: Decimal
    reason: str = "Recorded as settled (paid outside SplitPay)"


class ClarificationOption(BaseModel):
    label: str
    group_id: Optional[uuid.UUID] = None


class Clarification(BaseModel):
    question: str
    options: list[ClarificationOption] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    reply: str
    used_tools: list[str] = Field(default_factory=list)
    model: str
    mode: Literal["deterministic", "llm"] = "llm"
    expense_draft: Optional[ExpenseDraft] = None
    settlement_draft: Optional[SettlementDraft] = None
    clarification: Optional[Clarification] = None


class DraftConfirmOut(BaseModel):
    draft_id: uuid.UUID
    kind: Literal["EXPENSE", "SETTLEMENT"]
    status: str
    already_confirmed: bool = False
    message: str
    expense: Optional[ExpenseOut] = None
    settlement: Optional[SettlementOut] = None


class DraftCancelOut(BaseModel):
    draft_id: uuid.UUID
    status: str
    message: str


class AiActionOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    summary: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    error: Optional[str] = None
