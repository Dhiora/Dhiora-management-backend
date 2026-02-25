"""AI Lecture Chunk models."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AILectureChunk(Base):
    """Chunk of lecture transcript with embedding for vector search."""

    __tablename__ = "ai_lecture_chunks"
    __table_args__ = (
        Index("idx_ai_lecture_chunks_tenant_id", "tenant_id"),
        Index("idx_ai_lecture_chunks_lecture_id", "lecture_id"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    lecture_id = Column(UUID(as_uuid=True), ForeignKey("school.ai_lecture_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    lecture_session = relationship("AILectureSession", back_populates="chunks")

