"""Audit log for leave lifecycle: APPLIED, APPROVED, REJECTED."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class LeaveAuditLog(Base):
    __tablename__ = "leave_audit_logs"
    __table_args__ = {"schema": "leave"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    leave_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leave.leave_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(50), nullable=False)
    performed_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    performed_by_role = Column(String(50), nullable=True)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    leave_request = relationship("LeaveRequest", backref="audit_logs", foreign_keys=[leave_request_id])
