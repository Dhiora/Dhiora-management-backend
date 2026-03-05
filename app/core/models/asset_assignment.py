import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class AssetAssignment(Base):
    __tablename__ = "asset_assignments"
    __table_args__ = (
        CheckConstraint(
            "asset_user_type IN ('EMPLOYEE','STUDENT')",
            name="chk_asset_assignment_user_type",
        ),
        CheckConstraint(
            "status IN ('ASSIGNED','RETURNED','OVERDUE')",
            name="chk_asset_assignment_status",
        ),
        CheckConstraint(
            "(asset_user_type = 'EMPLOYEE' AND employee_id IS NOT NULL AND student_id IS NULL) OR "
            "(asset_user_type = 'STUDENT' AND student_id IS NOT NULL AND employee_id IS NULL)",
            name="chk_asset_assignment_user",
        ),
        {"schema": "asset"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("asset.assets.id", ondelete="RESTRICT"), nullable=False, index=True)
    asset_user_type = Column(String(20), nullable=False)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="SET NULL"), nullable=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    expected_return_date = Column(Date, nullable=True)
    returned_at = Column(DateTime(timezone=True), nullable=True)
    return_condition = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="ASSIGNED")

    tenant = relationship("Tenant", backref="asset_assignments", foreign_keys=[tenant_id])
    asset = relationship("Asset", backref="assignments", foreign_keys=[asset_id])

