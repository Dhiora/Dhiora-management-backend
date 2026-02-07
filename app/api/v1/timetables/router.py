from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import TimetableSlotCreate, TimetableSlotResponse, TimetableSlotUpdate
from . import service

router = APIRouter(prefix="/api/v1/timetables", tags=["timetables"])


@router.post(
    "",
    response_model=TimetableSlotResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_writable_academic_year)],
)
async def create_timetable_slot(
    payload: TimetableSlotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await service.create_timetable_slot(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[TimetableSlotResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def list_timetable_slots(
    academic_year_id: UUID,
    class_id: Optional[UUID] = Query(None),
    section_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await service.list_timetable_slots(
        db, current_user.tenant_id, academic_year_id, class_id=class_id, section_id=section_id
    )


@router.get(
    "/{slot_id}",
    response_model=TimetableSlotResponse,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_timetable_slot(
    slot_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    obj = await service.get_timetable_slot(db, current_user.tenant_id, slot_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timetable slot not found")
    return obj


@router.put(
    "/{slot_id}",
    response_model=TimetableSlotResponse,
    dependencies=[Depends(check_permission("attendance", "update")), Depends(require_writable_academic_year)],
)
async def update_timetable_slot(
    slot_id: UUID,
    payload: TimetableSlotUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        obj = await service.update_timetable_slot(db, current_user.tenant_id, slot_id, payload)
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timetable slot not found")
        return obj
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("attendance", "delete")), Depends(require_writable_academic_year)],
)
async def delete_timetable_slot(
    slot_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = await service.delete_timetable_slot(db, current_user.tenant_id, slot_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timetable slot not found")
