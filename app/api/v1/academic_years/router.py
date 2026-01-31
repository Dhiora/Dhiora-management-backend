from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import AcademicYearCreate, AcademicYearResponse, AcademicYearUpdate
from . import service

router = APIRouter(prefix="/api/v1/academic-years", tags=["academic-years"])


@router.post(
    "",
    response_model=AcademicYearResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("academic_years", "create"))],
)
async def create_academic_year(
    payload: AcademicYearCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AcademicYearResponse:
    """Create academic year. Admin only. If is_current=true, others for tenant become non-current."""
    try:
        return await service.create_academic_year(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[AcademicYearResponse],
    dependencies=[Depends(check_permission("academic_years", "read"))],
)
async def list_academic_years(
    status_filter: Optional[str] = Query(None, description="Filter by status: ACTIVE, CLOSED"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AcademicYearResponse]:
    """List academic years for the current tenant. Admin only."""
    return await service.list_academic_years(db, current_user.tenant_id, status_filter=status_filter)


@router.get(
    "/current",
    response_model=Optional[AcademicYearResponse],
    dependencies=[Depends(check_permission("academic_years", "read"))],
)
async def get_current_academic_year(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Optional[AcademicYearResponse]:
    """Get the current academic year (is_current=true) for the tenant. Default for data operations."""
    return await service.get_current_academic_year(db, current_user.tenant_id)


@router.get(
    "/{academic_year_id}",
    response_model=AcademicYearResponse,
    dependencies=[Depends(check_permission("academic_years", "read"))],
)
async def get_academic_year(
    academic_year_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AcademicYearResponse:
    """Get one academic year by id. Admin only."""
    ay = await service.get_academic_year(db, current_user.tenant_id, academic_year_id)
    if not ay:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic year not found")
    return ay


@router.put(
    "/{academic_year_id}",
    response_model=AcademicYearResponse,
    dependencies=[Depends(check_permission("academic_years", "update"))],
)
async def update_academic_year(
    academic_year_id: UUID,
    payload: AcademicYearUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AcademicYearResponse:
    """Update academic year. Only allowed when status is ACTIVE. Admin only."""
    try:
        return await service.update_academic_year(db, current_user.tenant_id, academic_year_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{academic_year_id}/set-current",
    response_model=AcademicYearResponse,
    dependencies=[Depends(check_permission("academic_years", "update"))],
)
async def set_academic_year_current(
    academic_year_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AcademicYearResponse:
    """Set this academic year as current. All others for tenant become non-current. Admin only."""
    try:
        return await service.set_academic_year_current(db, current_user.tenant_id, academic_year_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{academic_year_id}/close",
    response_model=AcademicYearResponse,
    dependencies=[Depends(check_permission("academic_years", "update"))],
)
async def close_academic_year(
    academic_year_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AcademicYearResponse:
    """Close academic year (status=CLOSED). Becomes read-only. Admin only."""
    try:
        return await service.close_academic_year(
            db, current_user.tenant_id, academic_year_id, closed_by=current_user.id
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{academic_year_id}/reopen",
    response_model=AcademicYearResponse,
    dependencies=[Depends(check_permission("academic_years", "update"))],
)
async def reopen_academic_year(
    academic_year_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AcademicYearResponse:
    """Reopen a CLOSED academic year (e.g. accidental close). If no other year is current, sets this as current."""
    try:
        return await service.reopen_academic_year(db, current_user.tenant_id, academic_year_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
