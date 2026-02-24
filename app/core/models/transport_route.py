"""Transport route. Unique route_code per tenant."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TransportRoute(Base):
    __tablename__ = "transport_routes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "route_code", name="uq_transport_route_tenant_code"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("core.academic_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    route_name = Column(String(255), nullable=False)
    route_code = Column(String(50), nullable=False)
    start_location = Column(String(255), nullable=False)
    end_location = Column(String(255), nullable=False)
    total_distance_km = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="transport_routes")
    subscription_plans = relationship("TransportSubscriptionPlan", back_populates="route")
    assignments = relationship("TransportAssignment", back_populates="route")
