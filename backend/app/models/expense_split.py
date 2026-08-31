import uuid

from sqlalchemy import Column, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.db.types import GUID


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    expense_id = Column(GUID(), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    percentage = Column(Numeric(5, 2), nullable=True)

    expense = relationship("Expense", back_populates="splits")
    user = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ExpenseSplit expense_id={self.expense_id} user_id={self.user_id} amount={self.amount}>"
