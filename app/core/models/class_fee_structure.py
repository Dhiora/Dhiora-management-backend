"""Class fee structure: fee per class per academic year."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class ClassFeeStructure(Base):
    """Fee structure per class per academic year. Defines amount, frequency, due date per component."""

    __tablename__ = "class_fee_structures"
    __table_args__ = (
        UniqueConstraint(
            "academic_year_id",
            "class_id",
            "fee_component_id",
            name="uq_class_fee_structure_ay_class_component",
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
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id", ondelete="CASCADE"), nullable=False)
    fee_component_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.fee_components.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount = Column(Numeric(12, 2), nullable=False)
    frequency = Column(String(30), nullable=False)  # one_time, monthly, term_wise
    due_date = Column(Date, nullable=True)
    is_mandatory = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    academic_year = relationship("AcademicYear")
    school_class = relationship("SchoolClass", foreign_keys=[class_id])
    fee_component = relationship("FeeComponent")
