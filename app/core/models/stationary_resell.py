import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


class StationaryItem(Base):
    """Stationary item published by school management (official catalog).

    Admins create and manage these items. Students/parents can browse them.
    """

    __tablename__ = "items"
    __table_args__ = {"schema": "stationary"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    brand = Column(String(150), nullable=True)
    category = Column(String(100), nullable=False)
    # e.g. "per piece", "per pack", "per set"
    unit = Column(String(50), nullable=False, default="per piece")
    price = Column(Numeric(10, 2), nullable=False)
    original_price = Column(Numeric(10, 2), nullable=True)
    stock_quantity = Column(Integer, nullable=False, default=0)
    class_level = Column(String(50), nullable=True)
    academic_year = Column(String(20), nullable=True)
    condition = Column(String(20), nullable=True)   # NEW | USED | REFURBISHED
    images = Column(JSONB, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class StationaryResellPayment(Base):
    """Tracks Razorpay listing-fee orders for stationery resell.

    Created when a seller initiates checkout; updated to PAID after signature
    verification. txn_id is generated only on successful verification and is
    the token required to create a resell listing.
    """

    __tablename__ = "resell_payments"
    __table_args__ = {"schema": "stationary"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    order_id = Column(String(100), nullable=False, unique=True)   # Razorpay order_id
    payment_id = Column(String(100), nullable=True)               # Razorpay payment_id (post-verify)
    signature = Column(String(500), nullable=True)
    seller_type = Column(String(20), nullable=False)              # STUDENT | PARENT
    seller_id = Column(String(100), nullable=False)
    amount = Column(Integer, nullable=False)                      # Rupees (not paise)
    currency = Column(String(10), nullable=False, default="INR")
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING | PAID | FAILED
    txn_id = Column(String(50), nullable=True, unique=True)         # Generated after PAID
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class StationaryResellItem(Base):
    """A stationery item listed for resale by a student or parent.

    Can only be created after a PAID listing-fee payment (validated via
    payment_txn_id). Follows an approval workflow: PENDING_APPROVAL →
    APPROVED | REJECTED. Sellers can then mark SOLD or INACTIVE.
    """

    __tablename__ = "resell_items"
    __table_args__ = {"schema": "stationary"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)
    condition = Column(String(20), nullable=False)    # NEW | LIKE_NEW | GOOD | FAIR
    price = Column(Numeric(10, 2), nullable=False)
    seller_type = Column(String(20), nullable=False)  # STUDENT | PARENT
    seller_id = Column(String(100), nullable=False)
    payment_txn_id = Column(String(50), nullable=False)  # FK validated in service
    images = Column(JSONB, nullable=False, default=list)
    status = Column(String(30), nullable=False, default="PENDING_APPROVAL")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
