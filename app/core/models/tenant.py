import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Tenant(Base):
    """
    Tenant (organization) in the multi-tenant platform.

    - tenant_id (id): Internal primary key (UUID). Used for all FKs and internal logic.
    - organization_code: External/public human-readable identifier (e.g. SCH-A3K9).
      Never used as a foreign key; for login, imports, subdomain routing, and support only.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        # organization_code is unique globally but never used as FK (tenant_id remains the only FK target)
        {"schema": "core"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Human-readable public identifier; UNIQUE, never used as FK
    organization_code = Column(String(20), unique=True, nullable=False, index=True)
    # Optional short code for identification only (e.g. employee numbers). Uppercase, max 10 chars. Not editable after employees exist.
    org_short_code = Column(String(10), nullable=True)
    organization_name = Column(String(255), nullable=False)
    organization_type = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    timezone = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    modules = relationship("TenantModule", back_populates="tenant", cascade="all, delete-orphan")
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")


class TenantModule(Base):
    """Link table between tenants and modules (tenant owns modules)."""

    __tablename__ = "tenant_modules"
    __table_args__ = (
        # A tenant cannot have the same module_key more than once
        {"schema": "core"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id"), nullable=False)
    module_key = Column(
        String(100),
        ForeignKey("core.modules.module_key"),
        nullable=False,
    )
    is_enabled = Column(Boolean, default=True, nullable=False)
    enabled_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="modules")
    module = relationship("Module", back_populates="tenant_mappings")

