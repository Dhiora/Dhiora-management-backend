from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrganizationType
from app.core.schemas import ModulesByOrganizationTypeResponse
from app.core.services import ServiceError, get_modules_by_organization_type
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/modules", tags=["modules"])


@router.get("/by-organization-type", response_model=ModulesByOrganizationTypeResponse)
async def get_modules(
    organization_type: OrganizationType,
    db: AsyncSession = Depends(get_db),
) -> ModulesByOrganizationTypeResponse:
    """Get all modules for an organization type (HRMS + org-specific)."""
    try:
        return await get_modules_by_organization_type(db, organization_type.value)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
