from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import require_platform_admin
from app.core.enums import OrganizationType
from app.core.schemas import (
    ModulesByOrganizationTypeResponse,
    ModulesByTenantResponse,
    OrganizationTypeModuleCreate,
    OrganizationTypeModuleResponse,
    OrganizationTypeModuleUpdate,
)
from app.core.services import (
    ServiceError,
    create_organization_type_module,
    delete_organization_type_module,
    get_modules_by_organization_type,
    get_modules_by_tenant_id,
    update_organization_type_module,
)
from app.auth.schemas import CurrentUser
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/modules", tags=["modules"])


@router.get("/by-tenant", response_model=ModulesByTenantResponse)
async def get_modules_by_tenant(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ModulesByTenantResponse:
    """Get modules enabled for the current user's tenant. Uses tenant_id from auth token."""
    try:
        return await get_modules_by_tenant_id(db, current_user.tenant_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/by-organization-type", response_model=ModulesByOrganizationTypeResponse)
async def get_modules(
    organization_type: OrganizationType,
    db: AsyncSession = Depends(get_db),
) -> ModulesByOrganizationTypeResponse:
    """Get all modules for an organization type (HRMS + org-specific). No authentication required."""
    try:
        return await get_modules_by_organization_type(db, organization_type.value)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/by-organization-type",
    response_model=OrganizationTypeModuleResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_admin)],
)
async def create_organization_type_module_mapping(
    payload: OrganizationTypeModuleCreate,
    db: AsyncSession = Depends(get_db),
) -> OrganizationTypeModuleResponse:
    """Create a module-to-organization-type mapping. Platform Admin only."""
    try:
        return await create_organization_type_module(db, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/by-organization-type/{mapping_id}",
    response_model=OrganizationTypeModuleResponse,
    dependencies=[Depends(require_platform_admin)],
)
async def update_organization_type_module_mapping(
    mapping_id: UUID,
    payload: OrganizationTypeModuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrganizationTypeModuleResponse:
    """Update is_default/is_enabled for a mapping. Platform Admin only."""
    try:
        return await update_organization_type_module(db, mapping_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/by-organization-type/{mapping_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_platform_admin)],
)
async def delete_organization_type_module_mapping(
    mapping_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a module-to-organization-type mapping. Platform Admin only."""
    try:
        await delete_organization_type_module(db, mapping_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
