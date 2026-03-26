"""LessonPlanProgress – curriculum completion percentage per grade group per academic year."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class LessonPlanProgress(Base):
    """Tracks curriculum progress (0-100 %) for a named grade group within an academic year.

    Grade groups are free-text labels defined by the tenant admin, e.g.:
      - "Senior Secondary" (Grades 11-12)
      - "Lower Secondary"  (Grades 6-10)
      - "Primary Wing"     (Grades 1-5)
    """

    __tablename__ = "lesson_plan_progress"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "academic_year_id", "grade_group",
            name="uq_lesson_progress_tenant_ay_group",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grade_group = Column(String(100), nullable=False)   # human-readable label
    progress_percent = Column(Integer, nullable=False, default=0)  # 0-100
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    tenant = relationship("Tenant", backref="lesson_plan_progress")
    academic_year = relationship("AcademicYear", backref="lesson_plan_progress")
