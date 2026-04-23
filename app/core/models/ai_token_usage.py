"""AI Token Usage tracking per tenant (school-level aggregation)."""

import uuid
from datetime import datetime, date

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AITokenUsage(Base):
    """
    Tracks OpenAI token consumption per request, scoped to tenant + student.

    Aggregated at school level for super admin dashboards.
    usage_date allows daily/monthly rollups.
    """

    __tablename__ = "ai_token_usage"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    chat_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.ai_doubt_chats.id", ondelete="SET NULL"),
        nullable=True,
    )
    usage_date = Column(Date, nullable=False, default=date.today, index=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    model_used = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
