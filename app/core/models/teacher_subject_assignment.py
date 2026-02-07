"""Teacher–subject assignment (year-specific). Defines what subject a teacher can teach and override attendance for."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TeacherSubjectAssignment(Base):
    __tablename__ = "teacher_subject_assignments"
    __table_args__ = (
        UniqueConstraint(
            "academic_year_id", "teacher_id", "class_id", "section_id", "subject_id",
            name="uq_teacher_subject_assignment",
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
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("school.subjects.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    teacher = relationship("User", foreign_keys=[teacher_id])
    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    section = relationship("Section", foreign_keys=[section_id])
    subject = relationship("SchoolSubject")
