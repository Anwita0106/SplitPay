"""AI endpoints.

Read/prepare:  POST /ai/chat                   (never writes financial records)
Confirm gate:  POST /ai/drafts/{id}/confirm    (the ONLY way an AI-prepared write happens)
               POST /ai/drafts/{id}/cancel
History:       GET  /ai/actions
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AiActionOut,
    DraftCancelOut,
    DraftConfirmOut,
)
from app.services import agent_service, draft_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat", response_model=AgentChatResponse)
def ai_chat(
    request: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentChatResponse:
    result = agent_service.chat(db, current_user, request.message, request.conversation, request.group_id)
    return AgentChatResponse(
        reply=result.reply,
        used_tools=result.used_tools,
        model=settings.OLLAMA_MODEL,
        mode=result.mode,
        expense_draft=result.expense_draft,
        settlement_draft=result.settlement_draft,
        clarification=result.clarification,
    )


@router.post("/drafts/{draft_id}/confirm", response_model=DraftConfirmOut)
def confirm_draft(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DraftConfirmOut:
    """Executes the server-stored payload of the draft — the request body is ignored on purpose."""
    return draft_service.confirm_draft(db, current_user, draft_id)


@router.post("/drafts/{draft_id}/cancel", response_model=DraftCancelOut)
def cancel_draft(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DraftCancelOut:
    return draft_service.cancel_draft(db, current_user, draft_id)


@router.get("/actions", response_model=list[AiActionOut])
def list_ai_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AiActionOut]:
    return draft_service.list_actions(db, current_user)
