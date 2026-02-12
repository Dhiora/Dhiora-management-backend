"""Fee component schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import FeeComponentCategory


class FeeComponentCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=50)
    description: Optional[str] = None
    component_category: FeeComponentCategory
    allow_discount: bool = True
    is_mandatory_default: bool = True


class FeeComponentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    component_category: Optional[FeeComponentCategory] = None
    allow_discount: Optional[bool] = None
    is_mandatory_default: Optional[bool] = None
    is_active: Optional[bool] = None


class FeeComponentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    code: str
    description: Optional[str] = None
    component_category: FeeComponentCategory
    allow_discount: bool
    is_mandatory_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FeeComponentDropdownItem(BaseModel):
    id: UUID
    name: str
    code: str
    component_category: FeeComponentCategory

    class Config:
        from_attributes = True
