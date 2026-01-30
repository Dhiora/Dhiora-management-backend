from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SectionCreate(BaseModel):
    class_id: UUID = Field(..., description="Class this section belongs to (e.g. 1st, 2nd)")
    name: str = Field(..., max_length=50)
    display_order: Optional[int] = None


class SectionBulkItem(BaseModel):
    """Single item for bulk create: name and display order."""
    name: str = Field(..., max_length=50)
    order: int = Field(..., description="Display order (e.g. 1, 2, 3)")


class SectionBulkCreate(BaseModel):
    class_id: UUID = Field(..., description="Class these sections belong to")
    sections: List[SectionBulkItem] = Field(..., min_length=1, description="List of sections to create")


class SectionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class SectionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    class_id: UUID
    name: str
    display_order: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
