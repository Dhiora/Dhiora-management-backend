"""Transport assignment: universal (student/teacher/staff). One active assignment per person."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TransportAssignment(Base):
    __tablename__ = "transport_assignments"
    __table_args__ = (
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("core.academic_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    person_type = Column(String(20), nullable=False)
    person_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    route_id = Column(UUID(as_uuid=True), ForeignKey("school.transport_routes.id", ondelete="RESTRICT"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("school.transport_vehicles.id", ondelete="SET NULL"), nullable=True, index=True)
    subscription_plan_id = Column(UUID(as_uuid=True), ForeignKey("school.transport_subscription_plans.id", ondelete="SET NULL"), nullable=True, index=True)
    pickup_point = Column(String(255), nullable=True)
    drop_point = Column(String(255), nullable=True)
    custom_fee = Column(Numeric(12, 2), nullable=True)
    fee_mode = Column(String(30), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="transport_assignments")
    route = relationship("TransportRoute", back_populates="assignments")
    vehicle = relationship("TransportVehicle", back_populates="assignments")
    subscription_plan = relationship("TransportSubscriptionPlan", back_populates="assignments")
