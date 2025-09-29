from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator

from .database import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, nullable=False)
    session_id = Column(String(255), nullable=False, index=True)
    message = Column(Text, nullable=False)
    is_from_user = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index(
            "idx_chat_messages_session_created",
            "session_id",
            "created_at",
        ),
    )

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "message": self.message,
            "is_from_user": self.is_from_user,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }