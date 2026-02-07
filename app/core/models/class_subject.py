"""Class–subject mapping (year-specific). Which subjects are taught in which class for an academic year."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class ClassSubject(Base):
    __tablename__ = "class_subjects"
    __table_args__ = (
        UniqueConstraint(
            "academic_year_id", "class_id", "subject_id",
            name="uq_class_subjects_ay_class_subject",
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
    subject_id = Column(UUID(as_uuid=True), ForeignKey("school.subjects.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    subject = relationship("SchoolSubject")
