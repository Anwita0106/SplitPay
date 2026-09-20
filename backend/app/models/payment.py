import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Numeric, String, TIMESTAMP, text
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.db.types import GUID


class Payment(Base):
    __tablename__ = "payments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    settlement_id = Column(GUID(), ForeignKey("settlements.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    gateway_order_id = Column(String(120), nullable=True, unique=True)
    gateway_payment_id = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="CREATED", index=True)
    idempotency_key = Column(String(120), nullable=False, unique=True)
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    settlement = relationship("Settlement", back_populates="payments")
    webhook_events = relationship("WebhookEvent", back_populates="payment")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment id={self.id} status={self.status} amount={self.amount}>"
