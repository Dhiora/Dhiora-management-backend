"""Class Teacher Assignment: ONE teacher responsible for ONE class-section in ONE academic year.
Used for attendance finalization, leave approvals, parent communication. Not subject/timetable logic."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class ClassTeacherAssignment(Base):
    __tablename__ = "class_teacher_assignments"
    __table_args__ = (
        UniqueConstraint(
            "academic_year_id", "class_id", "section_id",
            name="uq_class_teacher_assignment",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="CASCADE"),
        nullable=False,
    )
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    section = relationship("Section", foreign_keys=[section_id])
    teacher = relationship("User", foreign_keys=[teacher_id])
