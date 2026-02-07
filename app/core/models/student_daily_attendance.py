"""Daily attendance master and records. One master per class/section/date; records per student."""

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


STATUS_DRAFT = "DRAFT"
STATUS_SUBMITTED = "SUBMITTED"
STATUS_LOCKED = "LOCKED"

RECORD_STATUSES = ("PRESENT", "ABSENT", "LATE", "HALF_DAY", "LEAVE")


class StudentDailyAttendance(Base):
    """One row per (academic_year_id, class_id, section_id, attendance_date)."""

    __tablename__ = "student_daily_attendance"
    __table_args__ = (
        UniqueConstraint(
            "academic_year_id", "class_id", "section_id", "attendance_date",
            name="uq_daily_attendance_class_section_date",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=False)
    attendance_date = Column(Date, nullable=False)
    marked_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(20), nullable=False, default=STATUS_DRAFT)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="student_daily_attendances")
    academic_year = relationship("AcademicYear", backref="student_daily_attendances")
    school_class = relationship("SchoolClass", backref="student_daily_attendances")
    section = relationship("Section", backref="student_daily_attendances")
    records = relationship(
        "StudentDailyAttendanceRecord",
        back_populates="daily_attendance",
        cascade="all, delete-orphan",
    )
    overrides = relationship(
        "StudentSubjectAttendanceOverride",
        back_populates="daily_attendance",
        cascade="all, delete-orphan",
    )


class StudentDailyAttendanceRecord(Base):
    """One row per student per daily_attendance."""

    __tablename__ = "student_daily_attendance_records"
    __table_args__ = (
        UniqueConstraint("daily_attendance_id", "student_id", name="uq_daily_record_student"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    daily_attendance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.student_daily_attendance.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False)  # PRESENT, ABSENT, LATE, HALF_DAY, LEAVE

    daily_attendance = relationship("StudentDailyAttendance", back_populates="records")
    student = relationship("User", foreign_keys=[student_id])
