import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, TIMESTAMP, text
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.db.types import GUID


class Group(Base):
    __tablename__ = "groups"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False)
    created_by = Column(GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    creator = relationship("User", back_populates="groups_created", foreign_keys=[created_by])
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="group", cascade="all, delete-orphan")
    settlements = relationship("Settlement", back_populates="group", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Group id={self.id} name={self.name}>"
