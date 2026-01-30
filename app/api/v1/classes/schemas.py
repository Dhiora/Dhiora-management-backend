from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ClassCreate(BaseModel):
    name: str = Field(..., max_length=50)
    display_order: Optional[int] = None


class ClassBulkItem(BaseModel):
    """Single item for bulk create: name and order (display_order)."""
    name: str = Field(..., max_length=50)
    order: int = Field(..., description="Display order (e.g. 1, 2, 3)")


class ClassUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class ClassResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    display_order: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
