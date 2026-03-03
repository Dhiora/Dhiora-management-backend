from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import TimeSlotCreateRequest, TimeSlotResponse

router = APIRouter(prefix="/api/v1/time-slots", tags=["time-slots"])


@router.post(
    "",
    response_model=List[TimeSlotResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("timetables", "create"))],
)
async def create_time_slots(
    payload: TimeSlotCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TimeSlotResponse]:
    """
    Create multiple time slots (periods/breaks) for the tenant.

    Validates:
    - start_time < end_time
    - slot_type in {CLASS, BREAK}
    - order_index unique per tenant
    - no overlapping time ranges for active slots of the tenant
    """
    try:
        return await service.create_time_slots(db, current_user.tenant_id, payload.slots)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[TimeSlotResponse],
    dependencies=[Depends(check_permission("timetables", "read"))],
)
async def list_time_slots(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TimeSlotResponse]:
    """List active time slots for the tenant, ordered by order_index."""
    return await service.list_time_slots(db, current_user.tenant_id)


@router.delete(
    "/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("timetables", "delete")), Depends(require_writable_academic_year)],
)
async def delete_time_slot(
    slot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete a single time slot, if not used in any timetable."""
    from uuid import UUID as _UUID

    try:
        slot_uuid = _UUID(slot_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid slot_id")

    try:
        deleted = await service.delete_time_slot(db, current_user.tenant_id, slot_uuid)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time slot not found")
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

