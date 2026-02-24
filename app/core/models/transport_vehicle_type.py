"""Transport vehicle type master. System defaults have tenant_id=NULL; tenant custom types have tenant_id set."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TransportVehicleType(Base):
    __tablename__ = "transport_vehicle_types"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("core.academic_years.id", ondelete="RESTRICT"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_system_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="transport_vehicle_types")
    vehicles = relationship("TransportVehicle", back_populates="vehicle_type", foreign_keys="TransportVehicle.vehicle_type_id")
