from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.db.types import GUID


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id = Column(GUID(), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="memberships")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GroupMember group_id={self.group_id} user_id={self.user_id}>"
