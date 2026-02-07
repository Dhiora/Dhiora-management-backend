from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SectionCreate(BaseModel):
    class_id: UUID = Field(..., description="Class this section belongs to (e.g. 1st, 2nd)")
    name: str = Field(..., max_length=50)
    display_order: Optional[int] = None
    capacity: int = Field(50, ge=1, description="Max students per section (default 50)")


class SectionBulkItem(BaseModel):
    """Single item for bulk create: name, display order, and optional capacity."""
    name: str = Field(..., max_length=50)
    order: int = Field(..., description="Display order (e.g. 1, 2, 3)")
    capacity: int = Field(50, ge=1, description="Max students per section (default 50)")


class SectionBulkCreate(BaseModel):
    class_id: UUID = Field(..., description="Class these sections belong to")
    sections: List[SectionBulkItem] = Field(..., min_length=1, description="List of sections to create")


class SectionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    display_order: Optional[int] = None
    capacity: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None


class SectionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    academic_year_id: Optional[UUID] = None
    name: str
    display_order: Optional[int] = None
    capacity: int = Field(..., description="Max students per section")
    occupied: int = Field(0, description="Current enrollment in this section (current academic year)")
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CopySectionsToYearRequest(BaseModel):
    """Copy all sections from source academic year to target academic year (e.g. when year ends). Old data unchanged."""
    source_academic_year_id: UUID = Field(..., description="Year to copy from (e.g. ending year)")
    target_academic_year_id: UUID = Field(..., description="Year to copy into (e.g. new year)")
