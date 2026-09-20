import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base
from app.db.types import GUID

# JSONB on PostgreSQL (indexable, binary), plain JSON elsewhere (SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")

# Lifecycle of a confirmation-gated AI action.
#   PENDING   -> prepared by the AI layer, waiting for the user's explicit click
#   CONFIRMED -> user confirmed; the deterministic service performed the write
#   CANCELLED -> user (or a group deletion) cancelled it; nothing was written
#   EXPIRED   -> nobody confirmed it in time; nothing was written
#   FAILED    -> user confirmed but backend re-validation rejected it; nothing was written
AI_ACTION_STATUSES = ("PENDING", "CONFIRMED", "CANCELLED", "EXPIRED", "FAILED")
AI_ACTION_KINDS = ("EXPENSE", "SETTLEMENT")


class AiAction(Base):
    """
    A server-side record of a draft the AI prepared. This table is what makes
    the confirmation gate real: the confirm endpoint accepts only a draft id and
    executes the payload that the *backend* stored, never a payload supplied by
    the client or the model at confirmation time.
    """

    __tablename__ = "ai_actions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # SET NULL (not CASCADE): deleting a group keeps the audit row but voids the target.
    group_id = Column(GUID(), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    payload = Column(JSONType, nullable=False)
    result_id = Column(GUID(), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AiAction id={self.id} kind={self.kind} status={self.status}>"
