"""
Admission request: raised by teacher/admin; TRACK immutable, STATUS mutable.
Approval creates an admission_student record with INACTIVE status.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


# Admission request status (mutable)
ADMISSION_STATUS_PENDING = "PENDING_APPROVAL"
ADMISSION_STATUS_APPROVED = "APPROVED"
ADMISSION_STATUS_REJECTED = "REJECTED"

# Track values (immutable, set once at creation)
TRACK_TEACHER_RAISED = "TEACHER_RAISED"
TRACK_ADMIN_RAISED = "ADMIN_RAISED"
TRACK_WEBSITE_FORM = "WEBSITE_FORM"
TRACK_CAMPAIGN_REFERRAL = "CAMPAIGN_REFERRAL"
TRACK_PARENT_DIRECT = "PARENT_DIRECT"

TRACK_VALUES = (
    TRACK_TEACHER_RAISED,
    TRACK_ADMIN_RAISED,
    TRACK_WEBSITE_FORM,
    TRACK_CAMPAIGN_REFERRAL,
    TRACK_PARENT_DIRECT,
)


class AdmissionRequest(Base):
    __tablename__ = "admission_requests"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    student_name = Column(String(255), nullable=False)
    parent_name = Column(String(255), nullable=True)
    mobile = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    class_applied_for = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_applied_for = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=True)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    track = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default=ADMISSION_STATUS_PENDING)
    raised_by_user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    raised_by_role = Column(String(50), nullable=True)
    referral_teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    approved_by_role = Column(String(50), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="admission_requests", foreign_keys=[tenant_id])
    academic_year = relationship("AcademicYear", backref="admission_requests", foreign_keys=[academic_year_id])
    school_class = relationship("SchoolClass", foreign_keys=[class_applied_for])
    section = relationship("Section", foreign_keys=[section_applied_for])
