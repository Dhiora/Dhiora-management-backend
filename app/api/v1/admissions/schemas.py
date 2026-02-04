from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ----- Admission Request -----

class AdmissionRequestCreate(BaseModel):
    """Raise an admission request. Track is set by backend from context/referral/source."""

    student_name: str = Field(..., min_length=1, max_length=255)
    parent_name: Optional[str] = Field(None, max_length=255)
    mobile: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    class_applied_for: UUID = Field(..., description="Class ID applying for")
    section_applied_for: Optional[UUID] = Field(None, description="Section ID (optional at request; can be set at approval)")
    referral_code: Optional[str] = Field(None, max_length=20, description="Teacher referral code; if valid, track=CAMPAIGN_REFERRAL")
    raised_via_website_form: bool = Field(False, description="If true and no teacher/referral, track=WEBSITE_FORM")


class AdmissionRequestApprove(BaseModel):
    """Body for approve: section is required to create student record."""

    section_id: UUID = Field(..., description="Section for the approved student (must belong to class)")
    remarks: Optional[str] = Field(None, max_length=2000)


class AdmissionRequestReject(BaseModel):
    remarks: Optional[str] = Field(None, max_length=2000)


class AdmissionRequestResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    student_name: str
    parent_name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    class_applied_for: UUID
    section_applied_for: Optional[UUID] = None
    academic_year_id: UUID
    track: str
    status: str
    raised_by_user_id: Optional[UUID] = None
    raised_by_role: Optional[str] = None
    referral_teacher_id: Optional[UUID] = None
    approved_by_user_id: Optional[UUID] = None
    approved_by_role: Optional[str] = None
    approved_at: Optional[datetime] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----- Admission Student (created on approval) -----

class AdmissionStudentActivate(BaseModel):
    """Body for activating a student (physical join). Optional joined_date."""

    joined_date: Optional[date] = Field(None, description="Date of physical joining; default today")
    password: str = Field(..., min_length=8, description="Initial password for the new user account")


class AdmissionStudentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    admission_request_id: UUID
    user_id: Optional[UUID] = None
    student_name: str
    parent_name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    class_id: UUID
    section_id: UUID
    academic_year_id: UUID
    track: str
    status: str
    joined_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----- Audit (read-only list) -----

class AuditLogEntry(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    track: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    action: str
    performed_by: Optional[UUID] = None
    performed_by_role: Optional[str] = None
    timestamp: datetime
    remarks: Optional[str] = None

    class Config:
        from_attributes = True
