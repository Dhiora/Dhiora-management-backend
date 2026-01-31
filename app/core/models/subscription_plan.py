import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


class SubscriptionPlan(Base):
    """Subscription plan offered by the platform.

    Defines a plan name, organization type (School, College, etc.), included modules,
    price, discount price, and description. Managed by Platform Admin only.
    """

    __tablename__ = "subscription_plans"
    __table_args__ = (
        UniqueConstraint("name", "organization_type", name="uq_subscription_plan_name_org_type"),
        {"schema": "core"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    # Organization type: School, College, Software Company, etc.
    organization_type = Column(String(100), nullable=False)
    # Module UUIDs from core.modules (e.g. [uuid1, uuid2, ...])
    modules_include = Column(JSONB, nullable=False, default=list)
    # Display price (e.g. "99", "$99/mo", "Free")
    price = Column(String(100), nullable=False, default="")
    # Discounted price (e.g. "79", "$79/mo")
    discount_price = Column(String(100), nullable=True, default=None)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
