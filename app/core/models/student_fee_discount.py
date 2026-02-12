"""Student fee discount: multiple discounts per assignment. Recalculate total_discount and final_amount."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class StudentFeeDiscount(Base):
    """Discount applied to a student fee assignment. Validated against allow_discount and original_amount."""

    __tablename__ = "student_fee_discounts"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    student_fee_assignment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.student_fee_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    discount_name = Column(String(100), nullable=False)
    discount_category = Column(String(30), nullable=False)  # MASTER, CUSTOM, SYSTEM
    discount_type = Column(String(20), nullable=False)  # fixed, percentage
    discount_value = Column(Numeric(12, 2), nullable=False)
    calculated_discount_amount = Column(Numeric(12, 2), nullable=False)
    reason = Column(Text, nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    student_fee_assignment = relationship("StudentFeeAssignment", backref="discounts")
    approved_by_user = relationship("User", foreign_keys=[approved_by])
