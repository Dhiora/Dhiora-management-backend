"""DashboardAlert – tenant-scoped alert records surfaced on the admin dashboard."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class DashboardAlert(Base):
    """Persisted alerts (warnings, critical notices) shown on the dashboard.

    Alerts can be created programmatically (e.g. automatic attendance checks)
    or manually by admins.  expired / dismissed alerts are soft-deleted via
    is_active=False.
    """

    __tablename__ = "dashboard_alerts"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "info" | "warning" | "critical"
    alert_type = Column(String(20), nullable=False, default="warning")
    message = Column(Text, nullable=False)
    # optional URL the frontend can navigate to for resolution
    action_url = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    tenant = relationship("Tenant", backref="dashboard_alerts")
