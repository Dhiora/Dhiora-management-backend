"""Whisper audio transcription usage tracking per teacher per school."""

import uuid
from datetime import datetime, date

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class AIWhisperUsage(Base):
    """
    Tracks each Whisper transcription call: audio duration billed (seconds).
    Whisper is charged by the minute of audio, so duration_seconds is the key metric.
    Scoped to tenant + teacher for school-level and per-teacher reporting.
    """

    __tablename__ = "ai_whisper_usage"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    lecture_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.ai_lecture_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    usage_date = Column(Date, nullable=False, default=date.today, index=True)
    # Duration of audio sent to Whisper for this call (seconds, from verbose_json response)
    audio_duration_seconds = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
