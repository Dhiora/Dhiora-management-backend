"""Transport subscription plan per route. Fee and billing cycle."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TransportSubscriptionPlan(Base):
    __tablename__ = "transport_subscription_plans"
    __table_args__ = (
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("core.academic_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    route_id = Column(UUID(as_uuid=True), ForeignKey("school.transport_routes.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    fee_amount = Column(Numeric(12, 2), nullable=False)
    billing_cycle = Column(String(30), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="transport_subscription_plans")
    route = relationship("TransportRoute", back_populates="subscription_plans")
    assignments = relationship("TransportAssignment", back_populates="subscription_plan")
