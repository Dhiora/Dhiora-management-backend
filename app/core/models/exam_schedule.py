"""Exam schedule: one row per subject exam (date, time, room, optional invigilator)."""

import uuid
from datetime import date, datetime, time

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class ExamSchedule(Base):
    __tablename__ = "exam_schedule"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("school.exams.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("school.subjects.id", ondelete="RESTRICT"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id", ondelete="CASCADE"), nullable=False)
    exam_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    room_number = Column(String(50), nullable=True)
    invigilator_teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="exam_schedules", foreign_keys=[tenant_id])
    exam = relationship("Exam", backref="schedules", foreign_keys=[exam_id])
