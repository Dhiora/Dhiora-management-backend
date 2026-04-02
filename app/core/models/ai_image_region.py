"""AI Image Region model."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AIImageRegion(Base):
    """Named region within a lecture board image, with normalized bounding box."""

    __tablename__ = "ai_image_regions"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lecture_image_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.ai_lecture_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(255), nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    w = Column(Float, nullable=False)
    h = Column(Float, nullable=False)
    color_hex = Column(String(10), nullable=True, default="#EF9F27")
    description = Column(String(1024), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    lecture_image = relationship("AILectureImage", back_populates="regions")
