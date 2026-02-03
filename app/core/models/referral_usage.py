"""
Persistent storage for students referred by teachers.
One row per referred student; immutable after admission.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class ReferralUsage(Base):
    """
    Records when a student was admitted using a teacher's referral code.
    One student can appear only once; one admission (student_academic_record) only once.
    Referral data is immutable after admission.
    """

    __tablename__ = "referral_usage"
    __table_args__ = (
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    referral_code = Column(String(20), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, unique=True)
    admission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.student_academic_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    used_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    student = relationship("User", foreign_keys=[student_id])
    teacher = relationship("User", foreign_keys=[teacher_id])
