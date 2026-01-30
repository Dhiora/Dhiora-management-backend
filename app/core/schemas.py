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
