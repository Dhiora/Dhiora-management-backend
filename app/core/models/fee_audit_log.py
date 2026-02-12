"""Fee audit log: immutable financial change tracking for audit safety."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class FeeAuditLog(Base):
    """Immutable audit trail for fee-related financial changes."""

    __tablename__ = "fee_audit_logs"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    reference_table = Column(String(50), nullable=False)
    reference_id = Column(UUID(as_uuid=True), nullable=False)
    action_type = Column(String(30), nullable=False)  # CREATE, UPDATE, DEACTIVATE
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    changed_by_user = relationship("User", foreign_keys=[changed_by])
