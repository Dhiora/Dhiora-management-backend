"""AI Lecture Image model."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AILectureImage(Base):
    """Board/whiteboard image uploaded by teacher for a lecture."""

    __tablename__ = "ai_lecture_images"
    __table_args__ = (
        Index("idx_ai_lecture_images_tenant_id", "tenant_id"),
        Index("idx_ai_lecture_images_lecture_id", "lecture_id"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    lecture_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.ai_lecture_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.ai_lecture_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    image_url = Column(String(1024), nullable=False)
    sequence_order = Column(Integer, nullable=False, default=0)
    topic_label = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    lecture_session = relationship("AILectureSession", back_populates="images")
    chunk = relationship(
        "AILectureChunk",
        back_populates="images",
        foreign_keys=[chunk_id],
    )
    regions = relationship(
        "AIImageRegion",
        back_populates="lecture_image",
        cascade="all, delete-orphan",
    )
