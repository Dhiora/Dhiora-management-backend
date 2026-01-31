from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ModuleInfo(BaseModel):
    """Global module information from core.modules."""

    id: UUID
    module_key: str
    module_name: str
    module_domain: str
    description: Optional[str]
    price: str = "0"
    is_active: bool


class OrganizationTypeModuleInfo(BaseModel):
    """Module information with organization type mapping details."""

    # Global module info
    module: ModuleInfo
    # Organization type mapping details
    is_default: bool
    is_enabled: bool


class ModulesByOrganizationTypeResponse(BaseModel):
    """Response containing modules available for an organization type."""

    organization_type: str
    modules: List[OrganizationTypeModuleInfo]


class OrganizationTypeModuleCreate(BaseModel):
    """Payload to create an organization-type-to-module mapping."""

    organization_type: str
    module_key: str
    is_default: bool = False
    is_enabled: bool = True


class OrganizationTypeModuleUpdate(BaseModel):
    """Payload to update an organization-type-to-module mapping."""

    is_default: Optional[bool] = None
    is_enabled: Optional[bool] = None


class OrganizationTypeModuleResponse(BaseModel):
    """Single organization-type-module mapping (for create/update response)."""

    id: UUID
    organization_type: str
    module_key: str
    is_default: bool
    is_enabled: bool


# --- Subscription Plan ---


class SubscriptionPlanCreate(BaseModel):
    """Payload to create a subscription plan."""

    name: str
    organization_type: str  # School, College, Software Company, etc.
    modules_include: List[UUID]
    price: str = ""
    discount_price: Optional[str] = None
    description: Optional[str] = None


class SubscriptionPlanUpdate(BaseModel):
    """Payload to update a subscription plan."""

    name: Optional[str] = None
    organization_type: Optional[str] = None
    modules_include: Optional[List[UUID]] = None
    price: Optional[str] = None
    discount_price: Optional[str] = None
    description: Optional[str] = None


class SubscriptionPlanResponse(BaseModel):
    """Subscription plan response (list and get)."""

    id: UUID
    name: str
    organization_type: str
    modules_include: List[UUID]
    price: str
    discount_price: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
