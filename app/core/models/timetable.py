"""Timetable (source of truth). One slot per class/section/subject/teacher/day/time."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Timetable(Base):
    __tablename__ = "timetables"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("school.subjects.id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    section = relationship("Section", foreign_keys=[section_id])
    subject = relationship("SchoolSubject")
    teacher = relationship("User", foreign_keys=[teacher_id])
