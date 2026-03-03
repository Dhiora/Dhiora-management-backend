from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import TimeSlot, Timetable

from .schemas import TimeSlotCreateItem, TimeSlotResponse


def _to_response(slot: TimeSlot) -> TimeSlotResponse:
    return TimeSlotResponse(
        id=slot.id,
        tenant_id=slot.tenant_id,
        name=slot.name,
        start_time=slot.start_time,
        end_time=slot.end_time,
        slot_type=slot.slot_type,
        order_index=slot.order_index,
        is_active=slot.is_active,
        created_at=slot.created_at,
    )


def _times_overlap(start1, end1, start2, end2) -> bool:
    return start1 < end2 and end1 > start2


async def create_time_slots(
    db: AsyncSession,
    tenant_id: UUID,
    items: List[TimeSlotCreateItem],
) -> List[TimeSlotResponse]:
    if not items:
        return []

    # Normalize times to datetime.time
    parsed_items = []
    for item in items:
        start = datetime.strptime(item.start_time.strip(), "%H:%M").time()
        end = datetime.strptime(item.end_time.strip(), "%H:%M").time()
        if end <= start:
            raise ServiceError("end_time must be after start_time", status.HTTP_400_BAD_REQUEST)
        stype = item.slot_type.strip().upper()
        if stype not in ("CLASS", "BREAK"):
            raise ServiceError("slot_type must be CLASS or BREAK", status.HTTP_400_BAD_REQUEST)
        parsed_items.append(
            (item.name.strip(), start, end, stype, item.order_index),
        )

    # Load existing slots for this tenant to check order_index and overlaps
    result = await db.execute(
        select(TimeSlot).where(TimeSlot.tenant_id == tenant_id, TimeSlot.is_active.is_(True))
    )
    existing = list(result.scalars().all())

    # Check new items do not conflict with each other or existing slots
    for i, (name_i, start_i, end_i, stype_i, order_i) in enumerate(parsed_items):
        # order_index unique per tenant (within request and vs DB)
        for j in range(i + 1, len(parsed_items)):
            _, start_j, end_j, _, order_j = parsed_items[j]
            if order_i == order_j:
                raise ServiceError("order_index must be unique per tenant", status.HTTP_400_BAD_REQUEST)
            if _times_overlap(start_i, end_i, start_j, end_j):
                raise ServiceError("New slots overlap with each other", status.HTTP_400_BAD_REQUEST)
        for slot in existing:
            if slot.order_index == order_i:
                raise ServiceError("order_index must be unique per tenant", status.HTTP_400_BAD_REQUEST)
            if _times_overlap(start_i, end_i, slot.start_time, slot.end_time):
                raise ServiceError("New slot overlaps with existing slot", status.HTTP_400_BAD_REQUEST)

    created: List[TimeSlot] = []
    try:
        for name, start, end, stype, order_idx in parsed_items:
            obj = TimeSlot(
                tenant_id=tenant_id,
                name=name,
                start_time=start,
                end_time=end,
                slot_type=stype,
                order_index=order_idx,
                is_active=True,
            )
            db.add(obj)
            await db.flush()
            created.append(obj)
        await db.commit()
        for obj in created:
            await db.refresh(obj)
        return [_to_response(s) for s in created]
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "Duplicate order_index or overlapping slots detected for this tenant",
            status.HTTP_409_CONFLICT,
        )


async def list_time_slots(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[TimeSlotResponse]:
    result = await db.execute(
        select(TimeSlot).where(TimeSlot.tenant_id == tenant_id, TimeSlot.is_active.is_(True)).order_by(
            TimeSlot.order_index
        )
    )
    slots = result.scalars().all()
    return [_to_response(s) for s in slots]


async def delete_time_slot(
    db: AsyncSession,
    tenant_id: UUID,
    slot_id: UUID,
) -> bool:
    """Delete a time slot if it is not used by any timetable."""
    # Check slot exists and belongs to tenant
    result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.id == slot_id,
            TimeSlot.tenant_id == tenant_id,
        )
    )
    slot = result.scalar_one_or_none()
    if not slot:
        return False

    # Block delete if any timetable uses this slot
    in_use = await db.execute(
        select(Timetable.id).where(
            Timetable.tenant_id == tenant_id,
            Timetable.slot_id == slot_id,
        ).limit(1)
    )
    if in_use.scalar_one_or_none() is not None:
        raise ServiceError(
            "Cannot delete slot: it is used in at least one timetable entry",
            status.HTTP_400_BAD_REQUEST,
        )

    await db.delete(slot)
    await db.commit()
    return True

