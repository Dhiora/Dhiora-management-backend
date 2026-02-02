from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AcademicYearCreate(BaseModel):
    """Create academic year. name must be unique per tenant."""

    name: str = Field(..., min_length=1, max_length=50, description="e.g. 2025-2026")
    start_date: date = Field(..., description="Academic year start date")
    end_date: date = Field(..., description="Academic year end date (must be after start_date)")
    set_as_current: bool = Field(
        False,
        description="Set this year as current? If true, all other years for tenant become non-current and a new access_token is returned.",
    )
    admissions_allowed: bool = Field(True, description="Whether student admissions are allowed for this year")




class AcademicYearUpdate(BaseModel):
    """Update academic year. Only allowed when status is ACTIVE."""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    admissions_allowed: Optional[bool] = None


class AcademicYearResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    start_date: date
    end_date: date
    is_current: bool
    status: str
    admissions_allowed: bool
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    closed_by: Optional[UUID] = None

    class Config:
        from_attributes = True


class CreateAcademicYearResponse(BaseModel):
    """Response when creating an academic year. Returns new access_token when set_as_current=true."""

    academic_year: AcademicYearResponse
    access_token: Optional[str] = Field(
        None,
        description="New JWT with academic_year_id and academic_year_status. Present only when set_as_current=true.",
    )
