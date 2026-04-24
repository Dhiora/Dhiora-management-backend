import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base

FREE_TOKEN_LIMIT = 3000


class Lead(Base):
    """Pre-login website visitor lead. Not tenant-scoped — platform-wide."""

    __tablename__ = "leads"
    __table_args__ = ({"schema": "core"},)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(64), unique=True, nullable=False, index=True)

    # Captured during chat
    name = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(200), nullable=True)

    # Lead lifecycle: new | contacted | converted | lost
    status = Column(String(20), nullable=False, default="new")

    # Cumulative OpenAI tokens consumed across the entire session
    total_tokens_used = Column(Integer, nullable=False, default=0)

    # Full conversation history: list of {"role": "user"|"assistant", "content": "..."}
    conversation = Column(JSONB, nullable=False, default=list)

    notes = Column(Text, nullable=True)

    # Set when status = converted
    converted_at = Column(DateTime(timezone=True), nullable=True)
    converted_to_tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("core.tenants.id"), nullable=True
    )

    source = Column(String(50), nullable=False, default="website")

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    converted_tenant = relationship("Tenant", foreign_keys=[converted_to_tenant_id])
