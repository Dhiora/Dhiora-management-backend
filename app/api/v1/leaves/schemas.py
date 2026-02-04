from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----- Leave Type -----
class LeaveTypeCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=50)
    is_active: bool = True


class LeaveTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    code: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class LeaveTypeResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Apply Leave -----
class LeaveApply(BaseModel):
    """Apply for leave. applicant_type and employee_id/student_id set by backend from current user."""

    leave_type_id: Optional[UUID] = Field(None, description="Predefined leave type; omit for Other")
    custom_reason: Optional[str] = Field(None, max_length=2000, description="Required when leave_type_id is null (Other)")
    from_date: date = Field(...)
    to_date: date = Field(...)
    total_days: int = Field(..., ge=1)


# ----- Leave Request Response -----
class LeaveRequestResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_type: str
    applicant_type: str
    employee_id: Optional[UUID] = None
    student_id: Optional[UUID] = None
    leave_type_id: Optional[UUID] = None
    custom_reason: Optional[str] = None
    from_date: date
    to_date: date
    total_days: int
    status: str
    assigned_to_user_id: UUID
    approved_by_user_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----- Approve / Reject -----
class LeaveApproveReject(BaseModel):
    remarks: Optional[str] = Field(None, max_length=2000)
