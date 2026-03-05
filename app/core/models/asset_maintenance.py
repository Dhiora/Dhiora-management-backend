import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AssetMaintenance(Base):
    __tablename__ = "asset_maintenance"
    __table_args__ = (
        CheckConstraint(
            "maintenance_type IN ('REPAIR','SERVICE')",
            name="chk_asset_maintenance_type",
        ),
        CheckConstraint(
            "maintenance_status IN ('OPEN','IN_PROGRESS','COMPLETED')",
            name="chk_asset_maintenance_status",
        ),
        {"schema": "asset"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("asset.assets.id", ondelete="RESTRICT"), nullable=False, index=True)
    reported_issue = Column(Text, nullable=False)
    maintenance_type = Column(String(20), nullable=False)
    reported_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False)
    assigned_technician = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    maintenance_status = Column(String(20), nullable=False, default="OPEN")
    cost = Column(Numeric(12, 2), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="asset_maintenance", foreign_keys=[tenant_id])
    asset = relationship("Asset", backref="maintenance_records", foreign_keys=[asset_id])

