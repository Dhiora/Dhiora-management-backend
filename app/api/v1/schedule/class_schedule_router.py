"""Class schedule API: GET weekly schedule derived from timetable with optional filters."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.db.session import get_db

from .schemas import ClassScheduleItemResponse, ClassScheduleResponse
from . import class_schedule_service

router = APIRouter(prefix="/api/v1/classes", tags=["schedule"])


@router.get(
    "/schedule",
    response_model=list[ClassScheduleItemResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_all_schedules(
    academic_year_id: UUID = Query(..., description="Academic year for timetable"),
    class_id: Optional[UUID] = Query(None, description="Filter by class (omit to return all classes)"),
    section_id: Optional[UUID] = Query(None, description="Filter by section (omit to return all sections)"),
    teacher_name: Optional[str] = Query(None, description="Filter by teacher name (ilike)"),
    class_name: Optional[str] = Query(None, description="Filter by class name (ilike)"),
    section_name: Optional[str] = Query(None, description="Filter by section name (ilike)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ClassScheduleItemResponse]:
    """Return all class/section schedules for the academic year. Omit class_id/section_id to get all; use them to filter."""
    return await class_schedule_service.get_all_schedules(
        db,
        current_user.tenant_id,
        academic_year_id,
        class_id=class_id,
        section_id=section_id,
        teacher_name=teacher_name,
        class_name=class_name,
        section_name=section_name,
    )


@router.get(
    "/{class_id}/sections/{section_id}/schedule",
    response_model=ClassScheduleResponse,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_class_section_schedule(
    class_id: UUID,
    section_id: UUID,
    academic_year_id: UUID = Query(..., description="Academic year for timetable"),
    teacher_name: Optional[str] = Query(None, description="Filter by teacher name (ilike)"),
    class_name: Optional[str] = Query(None, description="Filter by class name (ilike)"),
    section_name: Optional[str] = Query(None, description="Filter by section name (ilike)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ClassScheduleResponse:
    """Return weekly class schedule from timetable. Optional filters: teacher_name, class_name, section_name."""
    return await class_schedule_service.get_class_section_schedule(
        db,
        current_user.tenant_id,
        class_id,
        section_id,
        academic_year_id,
        teacher_name=teacher_name,
        class_name=class_name,
        section_name=section_name,
    )
