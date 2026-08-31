import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Numeric, String, TIMESTAMP, text
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.db.types import GUID


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    group_id = Column(GUID(), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    split_type = Column(String(20), nullable=False)  # EQUAL | PERCENTAGE | EXACT
    paid_by = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    group = relationship("Group", back_populates="expenses")
    payer = relationship("User")
    splits = relationship("ExpenseSplit", back_populates="expense", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Expense id={self.id} desc={self.description} total={self.total_amount}>"
