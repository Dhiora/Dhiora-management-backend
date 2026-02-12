"""Student fee assignment: frozen snapshot per student per academic year. Never update original_amount."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.enums import StudentFeeSourceType, StudentFeeStatus
from app.db.session import Base


class StudentFeeAssignment(Base):
    """
    Snapshot of fee assigned to a student per academic year.
    original_amount is immutable after creation.
    """

    __tablename__ = "student_fee_assignments"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('TEMPLATE','CUSTOM')",
            name="chk_student_fee_assignment_source_type",
        ),
        CheckConstraint(
            "("
            "(source_type = 'TEMPLATE' AND class_fee_structure_id IS NOT NULL AND custom_name IS NULL)"
            " OR "
            "(source_type = 'CUSTOM' AND class_fee_structure_id IS NULL AND custom_name IS NOT NULL)"
            ")",
            name="chk_student_fee_assignment_source_fields",
        ),
        CheckConstraint(
            "status IN ('unpaid','partial','paid')",
            name="chk_student_fee_assignment_status",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)

    # TEMPLATE = derived from class_fee_structure, CUSTOM = fully student-level fee row
    source_type = Column(String(20), nullable=False, default=StudentFeeSourceType.TEMPLATE.value)

    class_fee_structure_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.class_fee_structures.id", ondelete="RESTRICT"),
        nullable=True,
    )
    custom_name = Column(String(255), nullable=True)

    base_amount = Column(Numeric(12, 2), nullable=False)
    total_discount = Column(Numeric(12, 2), nullable=False, default=0)
    final_amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), nullable=False, default=StudentFeeStatus.unpaid.value)  # unpaid, partial, paid
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    student = relationship("User", foreign_keys=[student_id])
    class_fee_structure = relationship("ClassFeeStructure")
