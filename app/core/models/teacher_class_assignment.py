import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TeacherClassAssignment(Base):
    """Links teacher to class-section (and optionally subject) for an academic year.
    subject_id NULL = can mark daily attendance only; set = can mark subject overrides for that subject.
    """

    __tablename__ = "teacher_class_assignments"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.subjects.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    teacher = relationship("User", foreign_keys=[teacher_id])
    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    section = relationship("Section", foreign_keys=[section_id])
    academic_year = relationship("AcademicYear", foreign_keys=[academic_year_id])
    subject = relationship("Subject", foreign_keys=[subject_id])
