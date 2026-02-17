from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SubjectCreate(BaseModel):
    department_id: UUID = Field(..., description="Department (core.departments - global)")
    name: str = Field(..., max_length=255)
    code: str = Field(..., max_length=50)
    display_order: Optional[int] = None


class SubjectUpdate(BaseModel):
    department_id: Optional[UUID] = None
    name: Optional[str] = Field(None, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class SubjectResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    department_id: UUID
    name: str
    code: str
    display_order: Optional[int] = None
    is_active: bool
    created_at: datetime
    department_name: Optional[str] = Field(None, description="Department name (core.departments); populated in list response")

    class Config:
        from_attributes = True


class SubjectDropdownItem(BaseModel):
    label: str
    value: UUID
