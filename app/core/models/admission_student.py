"""
Admission student: created on approval of an admission request. STATUS INACTIVE until admin activates.
On activation: create auth User + StudentProfile + StudentAcademicRecord and set user_id + status=ACTIVE.
TRACK is immutable.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


STUDENT_STATUS_INACTIVE = "INACTIVE"
STUDENT_STATUS_ACTIVE = "ACTIVE"


class AdmissionStudent(Base):
    __tablename__ = "admission_students"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    admission_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.admission_requests.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True, unique=True)
    student_name = Column(String(255), nullable=False)
    parent_name = Column(String(255), nullable=True)
    mobile = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    track = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default=STUDENT_STATUS_INACTIVE)
    joined_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="admission_students", foreign_keys=[tenant_id])
    admission_request = relationship(
        "AdmissionRequest", backref="admission_student", uselist=False, foreign_keys=[admission_request_id]
    )
    user = relationship("User", foreign_keys=[user_id])
    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    section = relationship("Section", foreign_keys=[section_id])
    academic_year = relationship("AcademicYear", foreign_keys=[academic_year_id])
