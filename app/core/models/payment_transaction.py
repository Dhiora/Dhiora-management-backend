"""Payment transaction: records payments against student fee assignments."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class PaymentTransaction(Base):
    """Payment against a student fee assignment. Supports partial payments."""

    __tablename__ = "payment_transactions"
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
        ForeignKey("school.student_fee_assignments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount_paid = Column(Numeric(12, 2), nullable=False)
    payment_mode = Column(String(30), nullable=False)  # UPI, CARD, CASH, BANK
    transaction_reference = Column(String(100), nullable=True)
    payment_status = Column(String(20), nullable=False)  # success, failed
    paid_at = Column(DateTime(timezone=True), nullable=False)
    collected_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    student_fee_assignment = relationship("StudentFeeAssignment", backref="payments")
    collected_by_user = relationship("User", foreign_keys=[collected_by])
