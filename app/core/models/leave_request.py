"""Global leave requests: behavior by tenant_type and applicant_type; assigned_to resolved dynamically."""

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


# Status and type constants
LEAVE_STATUS_PENDING = "PENDING"
LEAVE_STATUS_APPROVED = "APPROVED"
LEAVE_STATUS_REJECTED = "REJECTED"

TENANT_TYPE_SCHOOL = "SCHOOL"
TENANT_TYPE_COLLEGE = "COLLEGE"
TENANT_TYPE_SOFTWARE = "SOFTWARE"

APPLICANT_TYPE_EMPLOYEE = "EMPLOYEE"
APPLICANT_TYPE_STUDENT = "STUDENT"


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = {"schema": "leave"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_type = Column(String(50), nullable=False)
    applicant_type = Column(String(50), nullable=False)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    leave_type_id = Column(UUID(as_uuid=True), ForeignKey("leave.leave_types.id", ondelete="SET NULL"), nullable=True)
    custom_reason = Column(Text, nullable=True)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    total_days = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=LEAVE_STATUS_PENDING)
    assigned_to_user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False, index=True)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="leave_requests", foreign_keys=[tenant_id])
    leave_type = relationship("LeaveType", backref="leave_requests", foreign_keys=[leave_type_id])
    employee = relationship("User", foreign_keys=[employee_id])
    student = relationship("User", foreign_keys=[student_id])
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id])
    approved_by_user = relationship("User", foreign_keys=[approved_by_user_id])
    created_by_user = relationship("User", foreign_keys=[created_by])
