"""Tenant-level subscription (ERP or AI) with Razorpay payment tracking."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class TenantSubscription(Base):
    """
    Subscription record for a tenant (school/organization).

    category: 'ERP' or 'AI'
    status: 'PENDING' | 'ACTIVE' | 'CANCELLED' | 'EXPIRED'
    """

    __tablename__ = "tenant_subscriptions"
    __table_args__ = ({"schema": "core"},)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False)
    subscription_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    category = Column(String(50), nullable=False)  # ERP | AI
    status = Column(String(20), nullable=False, default="PENDING")

    razorpay_order_id = Column(String(255), nullable=True)
    razorpay_payment_id = Column(String(255), nullable=True)
    razorpay_signature = Column(String(1024), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", backref="subscriptions")
    plan = relationship("SubscriptionPlan", backref="tenant_subscriptions")
