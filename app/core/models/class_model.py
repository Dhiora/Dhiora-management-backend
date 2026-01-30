"""Tenant-scoped classes (e.g. Nursery, LKG, 1st, 10th). Model named SchoolClass to avoid Python 'class' keyword."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class SchoolClass(Base):
    """Tenant-scoped class master (Nursery, LKG, 1st, 10th). Soft delete via is_active."""

    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_class_tenant_name"),
        {"schema": "core"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id"), nullable=False)
    name = Column(String(50), nullable=False)
    display_order = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="school_classes")
