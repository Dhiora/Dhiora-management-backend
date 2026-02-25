"""AI Doubt Message models."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class MessageRole(str, Enum):
    STUDENT = "STUDENT"
    AI = "AI"


class AIDoubtMessage(Base):
    """Message in a doubt chat session."""

    __tablename__ = "ai_doubt_messages"
    __table_args__ = (
        Index("idx_ai_doubt_messages_chat_id", "chat_id"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("school.ai_doubt_chats.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Text, nullable=False)  # STUDENT or AI
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    chat = relationship("AIDoubtChat", back_populates="messages")

