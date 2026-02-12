"""Fee component master (Tuition, Bus, Exam, Hostel). Tenant-scoped."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.enums import FeeComponentCategory
from app.db.session import Base


class FeeComponent(Base):
    """Tenant-scoped fee component (e.g. Tuition, Bus, Exam, Hostel). Soft delete via is_active."""

    __tablename__ = "fee_components"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_fee_component_tenant_code"),
        CheckConstraint(
            "component_category IN ('ACADEMIC','TRANSPORT','HOSTEL','OTHER')",
            name="chk_fee_component_category",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    # Stored as string; constrained by chk_fee_component_category
    component_category = Column(String(50), nullable=False)
    allow_discount = Column(Boolean, nullable=False, default=True)
    is_mandatory_default = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="fee_components")
