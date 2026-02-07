"""Subject-wise attendance override. Overrides daily record status for a specific subject."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class StudentSubjectAttendanceOverride(Base):
    """One row per (daily_attendance_id, subject_id, student_id)."""

    __tablename__ = "student_subject_attendance_overrides"
    __table_args__ = (
        UniqueConstraint(
            "daily_attendance_id", "subject_id", "student_id",
            name="uq_subject_override_daily_subject_student",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False)
    daily_attendance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.student_daily_attendance.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id = Column(UUID(as_uuid=True), ForeignKey("school.subjects.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    override_status = Column(String(20), nullable=False)  # PRESENT, ABSENT, LATE, HALF_DAY, LEAVE
    reason = Column(Text, nullable=True)
    marked_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    daily_attendance = relationship("StudentDailyAttendance", back_populates="overrides")
    subject = relationship("SchoolSubject", backref="attendance_overrides")
    student = relationship("User", foreign_keys=[student_id])
