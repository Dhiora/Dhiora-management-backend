"""SQLAlchemy models for grades module: GradeScale and ExamMark."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class GradeScale(Base):
    __tablename__ = "grade_scales"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(10), nullable=False)
    min_percentage = Column(Numeric(5, 2), nullable=False)
    max_percentage = Column(Numeric(5, 2), nullable=False)
    gpa_points = Column(Numeric(4, 2), nullable=True)
    remarks = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class ExamMark(Base):
    __tablename__ = "exam_marks"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", "subject_id", name="uq_exam_mark"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("core.academic_years.id", ondelete="RESTRICT"), nullable=False)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("school.exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("school.subjects.id", ondelete="RESTRICT"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id", ondelete="SET NULL"), nullable=True)
    marks_obtained = Column(Numeric(6, 2), nullable=True)
    max_marks = Column(Numeric(6, 2), nullable=False, default=Decimal("100"))
    is_absent = Column(Boolean, nullable=False, default=False)
    remarks = Column(Text, nullable=True)
    entered_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
