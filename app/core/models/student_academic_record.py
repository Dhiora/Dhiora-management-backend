import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class StudentAcademicRecord(Base):
    """
    Student enrollment per academic year. One record per (student, academic_year).
    Promotion creates NEW records; old record status → PROMOTED.
    student_profile does NOT store class/section; get from current record.
    """

    __tablename__ = "student_academic_records"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=False)
    roll_number = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE | PROMOTED | LEFT
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    student = relationship("User", backref="academic_records")
    academic_year = relationship("AcademicYear", backref="student_records")
    school_class = relationship("SchoolClass", foreign_keys=[class_id], lazy="joined")
    section = relationship("Section", foreign_keys=[section_id], lazy="joined")
