"""
School Profile API — tenant-scoped.

GET  /api/v1/school/profile          — any authenticated user
PATCH /api/v1/school/profile         — school ADMIN  OR  role with school_profile.update permission
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import SchoolProfileResponse, SchoolProfileUpdate

router = APIRouter(prefix="/api/v1/school", tags=["school-profile"])


@router.get("/profile", response_model=SchoolProfileResponse)
async def get_school_profile(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the profile of the authenticated user's school."""
    try:
        return await service.get_school_profile(db, current_user.tenant_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch("/profile", response_model=SchoolProfileResponse)
async def update_school_profile(
    payload: SchoolProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Update own school's profile.

    Access rules:
    - ADMIN role: always allowed.
    - Other roles: must have `school_profile.update` permission granted by the admin.
    - PLATFORM_ADMIN / SUPER_ADMIN: use the platform endpoint instead.
    """
    if current_user.role not in ("ADMIN", "SUPER_ADMIN", "PLATFORM_ADMIN"):
        perms = current_user.permissions.get("school_profile", {})
        if not perms.get("update", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update the school profile. "
                       "Ask your admin to grant school_profile.update access.",
            )

    try:
        return await service.update_school_profile(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
