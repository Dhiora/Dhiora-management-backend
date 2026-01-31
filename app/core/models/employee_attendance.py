import uuid
from datetime import datetime, date

from sqlalchemy import Column, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class EmployeeAttendance(Base):
    """Employee attendance: one per employee per day."""

    __tablename__ = "employee_attendance"
    __table_args__ = {"schema": "hrms"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False)  # PRESENT, ABSENT, LATE, HALF_DAY, LEAVE
    marked_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    employee = relationship("User", foreign_keys=[employee_id])
    marker = relationship("User", foreign_keys=[marked_by])
