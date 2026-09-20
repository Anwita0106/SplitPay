import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, TIMESTAMP, JSON
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.db.types import GUID


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    provider_event_id = Column(String(150), nullable=False, unique=True)
    payment_id = Column(GUID(), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    raw_payload = Column(JSON, nullable=False)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    payment = relationship("Payment", back_populates="webhook_events")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WebhookEvent id={self.id} provider_event_id={self.provider_event_id}>"
