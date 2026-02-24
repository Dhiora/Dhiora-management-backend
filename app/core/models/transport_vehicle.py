"""Transport vehicle. vehicle_number unique per tenant."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TransportVehicle(Base):
    __tablename__ = "transport_vehicles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vehicle_number", name="uq_transport_vehicle_tenant_number"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("core.academic_years.id", ondelete="RESTRICT"), nullable=True, index=True)
    vehicle_number = Column(String(50), nullable=False)
    vehicle_type_id = Column(UUID(as_uuid=True), ForeignKey("school.transport_vehicle_types.id", ondelete="RESTRICT"), nullable=False, index=True)
    capacity = Column(Integer, nullable=False)
    driver_name = Column(String(255), nullable=True)
    insurance_expiry = Column(Date, nullable=True)
    fitness_expiry = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="transport_vehicles")
    vehicle_type = relationship("TransportVehicleType", back_populates="vehicles", foreign_keys=[vehicle_type_id])
    assignments = relationship("TransportAssignment", back_populates="vehicle")
