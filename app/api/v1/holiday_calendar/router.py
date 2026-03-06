"""FastAPI router for Holiday Calendar APIs."""

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import HolidayCreate, HolidayResponse, HolidayUpdate
from . import service

router = APIRouter(prefix="/api/v1/holiday-calendar", tags=["holiday_calendar"])


@router.post(
    "",
    response_model=HolidayResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("holiday_calendar", "create"))],
)
async def create_holiday(
    payload: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> HolidayResponse:
    """Create a holiday for an academic year. Admin / Super Admin only."""
    try:
        return await service.create_holiday(
            db,
            current_user.tenant_id,
            current_user.id,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[HolidayResponse],
    dependencies=[Depends(check_permission("holiday_calendar", "read"))],
)
async def get_holidays(
    academic_year_id: UUID = Query(..., description="Academic year ID"),
    month: Optional[int] = Query(
        None,
        description="Optional month filter (1-12)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[HolidayResponse]:
    """List holidays for an academic year, optionally filtered by month."""
    try:
        return await service.list_holidays_service(
            db,
            current_user.tenant_id,
            academic_year_id,
            month=month,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/calendar",
    response_model=Dict[str, str],
    dependencies=[Depends(check_permission("holiday_calendar", "read"))],
)
async def get_calendar_view(
    academic_year_id: UUID = Query(..., description="Academic year ID"),
    month: int = Query(..., description="Month (1-12)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, str]:
    """Calendar-style view: date string to holiday name for a given month."""
    try:
        return await service.get_calendar_view(
            db,
            current_user.tenant_id,
            academic_year_id,
            month=month,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/{holiday_id}",
    response_model=HolidayResponse,
    dependencies=[Depends(check_permission("holiday_calendar", "update"))],
)
async def update_holiday(
    holiday_id: UUID,
    payload: HolidayUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> HolidayResponse:
    """Update an existing holiday. Admin / Super Admin only."""
    try:
        return await service.update_holiday_service(
            db,
            current_user.tenant_id,
            holiday_id,
            current_user.id,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{holiday_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("holiday_calendar", "delete"))],
)
async def delete_holiday(
    holiday_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a holiday if it is not in the past. Admin / Super Admin only."""
    try:
        await service.delete_holiday_service(
            db,
            current_user.tenant_id,
            holiday_id,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

