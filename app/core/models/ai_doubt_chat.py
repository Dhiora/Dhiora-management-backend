"""AI Doubt Chat models."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UUID as SQLUUID
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AIDoubtChat(Base):
    """Chat session for student doubts about a lecture."""

    __tablename__ = "ai_doubt_chats"
    __table_args__ = (
        Index("idx_ai_doubt_chats_tenant_id", "tenant_id"),
        Index("idx_ai_doubt_chats_student_id", "student_id"),
        Index("idx_ai_doubt_chats_lecture_id", "lecture_id"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    lecture_id = Column(UUID(as_uuid=True), ForeignKey("school.ai_lecture_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    session_stage = Column(String(50), nullable=True)  # ULTRA: START | TEACHING | CHALLENGING | EVALUATING
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    lecture_session = relationship("AILectureSession", back_populates="doubt_chats")
    messages = relationship("AIDoubtMessage", back_populates="chat", cascade="all, delete-orphan", order_by="AIDoubtMessage.created_at")

