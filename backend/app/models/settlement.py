import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Numeric, String, TIMESTAMP, text
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.db.types import GUID


class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    group_id = Column(GUID(), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    to_user = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    # UPI    -> paid through the sandbox payment flow (payments row + webhook)
    # MANUAL -> the amount was settled outside SplitPay (cash / direct UPI) and a
    #           group member recorded it; no payments row exists.
    method = Column(String(20), nullable=False, default="UPI", server_default="UPI")
    recorded_by = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    # Client/AI-supplied key that makes "record settlement" safe to retry.
    idempotency_key = Column(String(120), nullable=True, unique=True)
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    group = relationship("Group", back_populates="settlements")
    debtor = relationship("User", foreign_keys=[from_user])
    creditor = relationship("User", foreign_keys=[to_user])
    payments = relationship("Payment", back_populates="settlement")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Settlement {self.from_user}->{self.to_user} amount={self.amount} status={self.status}>"
