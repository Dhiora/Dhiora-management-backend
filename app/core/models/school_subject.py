"""School/college subject (year-agnostic). Belongs to core department (global for school/college/software)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class SchoolSubject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_school_subject_tenant_code"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    display_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="school_subjects")
    department = relationship("Department", foreign_keys=[department_id])
