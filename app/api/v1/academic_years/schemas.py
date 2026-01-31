from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AcademicYearCreate(BaseModel):
    """Create academic year. name must be unique per tenant."""

    name: str = Field(..., min_length=1, max_length=50, description="e.g. 2025-2026")
    start_date: date = Field(..., description="Academic year start date")
    end_date: date = Field(..., description="Academic year end date (must be after start_date)")
    is_current: bool = Field(False, description="If true, all other years for tenant become is_current=false")
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
