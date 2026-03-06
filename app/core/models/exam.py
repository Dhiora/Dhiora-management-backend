"""Exam (e.g. Unit Test 1, Half Yearly 2026) per class-section with date range and status."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'completed')",
            name="chk_exam_status",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_type_id = Column(UUID(as_uuid=True), ForeignKey("school.exam_types.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(255), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="exams", foreign_keys=[tenant_id])
    exam_type = relationship("ExamType", backref="exams", foreign_keys=[exam_type_id])
