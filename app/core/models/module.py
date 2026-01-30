import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Module(Base):
    """System-defined modules available in the platform.

    Represents a functional capability (e.g., HRMS, ATTENDANCE, STUDENT).
    Modules are owned by the platform and then linked to tenants and
    organization types via mapping tables.
    """

    __tablename__ = "modules"
    __table_args__ = {"schema": "core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Stable programmatic key, used in code & foreign keys (e.g. 'ATTENDANCE')
    module_key = Column(String(100), nullable=False, unique=True)
    # Human-readable name (e.g. 'Attendance Management')
    module_name = Column(String(255), nullable=False)
    # Domain of the module, e.g. 'HRMS' or 'SCHOOL'
    module_domain = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    organization_type_mappings = relationship(
        "OrganizationTypeModule", back_populates="module", cascade="all, delete-orphan"
    )
    tenant_mappings = relationship(
        "TenantModule", back_populates="module", cascade="all, delete-orphan"
    )


class OrganizationTypeModule(Base):
    """Mapping of organization types to modules they can use.

    This defines which modules are available for a given organization_type
    (e.g., 'School', 'College', etc.), and whether they are enabled by default.
    """

    __tablename__ = "organization_type_modules"
    __table_args__ = (
        UniqueConstraint("organization_type", "module_key", name="uq_org_type_module"),
        {"schema": "core"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # E.g. 'School', 'College', 'Software Company', etc.
    organization_type = Column(String(100), nullable=False)
    # Reference to the system-defined module
    module_key = Column(
        String(100),
        ForeignKey("core.modules.module_key"),
        nullable=False,
    )
    # Whether this module should be enabled by default for the org type
    is_default = Column(Boolean, default=False, nullable=False)
    # Whether this module is allowed at all for the org type
    is_enabled = Column(Boolean, default=True, nullable=False)

    # Backref to the Module
    module = relationship("Module", back_populates="organization_type_mappings")

