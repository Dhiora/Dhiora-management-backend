import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AVAILABLE','ASSIGNED','UNDER_MAINTENANCE','DAMAGED','LOST','RETIRED')",
            name="chk_asset_status",
        ),
        {"schema": "asset"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_type_id = Column(UUID(as_uuid=True), ForeignKey("asset.asset_types.id", ondelete="RESTRICT"), nullable=False)
    asset_name = Column(String(255), nullable=False)
    asset_code = Column(String(100), nullable=False)
    serial_number = Column(String(255), nullable=True)
    purchase_date = Column(Date, nullable=True)
    purchase_cost = Column(Numeric(12, 2), nullable=True)
    warranty_expiry = Column(Date, nullable=True)
    status = Column(String(30), nullable=False, default="AVAILABLE")
    location = Column(String(255), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="assets", foreign_keys=[tenant_id])
    asset_type = relationship("AssetType", backref="assets", foreign_keys=[asset_type_id])

