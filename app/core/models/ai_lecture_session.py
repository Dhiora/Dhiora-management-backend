"""AI Lecture Session models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AILectureSession(Base):
    """AI Lecture Session created by teacher."""

    __tablename__ = "ai_lecture_sessions"
    __table_args__ = (
        Index("idx_ai_lecture_sessions_tenant_id", "tenant_id"),
        Index("idx_ai_lecture_sessions_teacher_id", "teacher_id"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("core.academic_years.id", ondelete="RESTRICT"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id", ondelete="RESTRICT"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id", ondelete="RESTRICT"), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("school.subjects.id", ondelete="RESTRICT"), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    transcript = Column(Text, nullable=False, default="")
    structured_notes = Column(JSONB, nullable=True)
    status = Column(
        String(20), nullable=False, default="IDLE"
    )  # IDLE, RECORDING, PAUSED, UPLOADING, PROCESSING, COMPLETED, FAILED
    recording_started_at = Column(DateTime(timezone=True), nullable=True)
    recording_paused_at = Column(DateTime(timezone=True), nullable=True)
    total_recording_seconds = Column(Integer, nullable=False, default=0)
    is_active_recording = Column(Boolean, nullable=False, default=False)
    audio_buffer_size_bytes = Column(Integer, nullable=False, default=0)
    upload_completed = Column(Boolean, nullable=False, default=False)
    audio_file_path = Column(String(1024), nullable=True)
    processing_stage = Column(String(50), nullable=True)
    last_chunk_received_at = Column(DateTime(timezone=True), nullable=True)
    upload_progress_percent = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    chunks = relationship("AILectureChunk", back_populates="lecture_session", cascade="all, delete-orphan")
    doubt_chats = relationship("AIDoubtChat", back_populates="lecture_session", cascade="all, delete-orphan")

