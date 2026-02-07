"""Tenant-scoped sections (e.g. A, B, C) under a class, per academic year. Section name is unique per class per year."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Section(Base):
    """Section belongs to a class and academic year (e.g. Class 1st Section A for 2025-26). Copy to new year when year ends."""

    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("class_id", "academic_year_id", "name", name="uq_section_class_ay_name"),
        {"schema": "core"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=True,  # nullable for existing DBs until backfilled
    )
    name = Column(String(50), nullable=False)
    display_order = Column(Integer, nullable=True)
    capacity = Column(Integer, nullable=False, default=50)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="sections")
    school_class = relationship("SchoolClass", backref="sections", foreign_keys=[class_id])
    academic_year = relationship("AcademicYear", backref="sections", foreign_keys=[academic_year_id])