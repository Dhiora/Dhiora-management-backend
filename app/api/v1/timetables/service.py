from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import AcademicYear, SchoolClass, SchoolSubject, Section, TimeSlot, Timetable

from app.api.v1.class_subjects import service as class_subjects_service

from .schemas import TimeSlotInfo, TimetableSlotCreate, TimetableSlotResponse, TimetableSlotUpdate


def _to_response(t: Timetable, slot: Optional[TimeSlot] = None) -> TimetableSlotResponse:
    if slot is None:
        slot = getattr(t, "time_slot", None)
    slot_info = TimeSlotInfo(
        id=slot.id,
        name=slot.name,
        start_time=slot.start_time.strftime("%H:%M") if slot else "",
        end_time=slot.end_time.strftime("%H:%M") if slot else "",
        slot_type=slot.slot_type if slot else "",
    ) if slot else None
    return TimetableSlotResponse(
        id=t.id,
        tenant_id=t.tenant_id,
        academic_year_id=t.academic_year_id,
        class_id=t.class_id,
        section_id=t.section_id,
        subject_id=t.subject_id,
        teacher_id=t.teacher_id,
        day_of_week=t.day_of_week,
        slot=slot_info,
        created_at=t.created_at,
    )


async def create_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TimetableSlotCreate,
) -> TimetableSlotResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot add timetable slot for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
    cl = await db.get(SchoolClass, payload.class_id)
    if not cl or cl.tenant_id != tenant_id:
        raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    sec = await db.get(Section, payload.section_id)
    if not sec or sec.tenant_id != tenant_id or sec.class_id != payload.class_id:
        raise ServiceError("Invalid section for this class", status.HTTP_400_BAD_REQUEST)
    subj = await db.get(SchoolSubject, payload.subject_id)
    if not subj or subj.tenant_id != tenant_id:
        raise ServiceError("Invalid subject", status.HTTP_400_BAD_REQUEST)
    if not await class_subjects_service.check_subject_in_class_for_year(
        db, tenant_id, payload.academic_year_id, payload.class_id, payload.subject_id
    ):
        raise ServiceError(
            "Subject must be assigned to this class for this academic year (class_subjects) first",
            status.HTTP_400_BAD_REQUEST,
        )
    # Validate time slot belongs to tenant and is active
    time_slot = await db.get(TimeSlot, payload.slot_id)
    if not time_slot or time_slot.tenant_id != tenant_id or not time_slot.is_active:
        raise ServiceError("Invalid time slot", status.HTTP_400_BAD_REQUEST)

    # Prevent duplicate: same class + day_of_week + slot_id in same year
    dup_stmt = select(Timetable.id).where(
        Timetable.tenant_id == tenant_id,
        Timetable.academic_year_id == payload.academic_year_id,
        Timetable.class_id == payload.class_id,
        Timetable.section_id == payload.section_id,
        Timetable.day_of_week == payload.day_of_week,
        Timetable.slot_id == payload.slot_id,
    ).limit(1)
    dup_result = await db.execute(dup_stmt)
    if dup_result.scalar_one_or_none() is not None:
        raise ServiceError(
            "Timetable slot already exists for this class/section/day/slot",
            status.HTTP_409_CONFLICT,
        )

    # Prevent teacher double-booking: same teacher + day_of_week + slot_id in same year
    teacher_conflict_stmt = select(Timetable.id).where(
        Timetable.tenant_id == tenant_id,
        Timetable.academic_year_id == payload.academic_year_id,
        Timetable.teacher_id == payload.teacher_id,
        Timetable.day_of_week == payload.day_of_week,
        Timetable.slot_id == payload.slot_id,
    ).limit(1)
    teacher_conflict = await db.execute(teacher_conflict_stmt)
    if teacher_conflict.scalar_one_or_none() is not None:
        raise ServiceError(
            "Teacher already has a class in this slot for this day",
            status.HTTP_409_CONFLICT,
        )
    try:
        obj = Timetable(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            class_id=payload.class_id,
            section_id=payload.section_id,
            subject_id=payload.subject_id,
            teacher_id=payload.teacher_id,
            day_of_week=payload.day_of_week,
            slot_id=payload.slot_id,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Timetable slot creation failed", status.HTTP_409_CONFLICT)


async def list_timetable_slots(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: Optional[UUID] = None,
    section_id: Optional[UUID] = None,
) -> List[TimetableSlotResponse]:
    stmt = select(Timetable, TimeSlot).join(
        TimeSlot, Timetable.slot_id == TimeSlot.id
    ).where(
        Timetable.tenant_id == tenant_id,
        Timetable.academic_year_id == academic_year_id,
    )
    if class_id is not None:
        stmt = stmt.where(Timetable.class_id == class_id)
    if section_id is not None:
        stmt = stmt.where(Timetable.section_id == section_id)
    stmt = stmt.order_by(Timetable.day_of_week, TimeSlot.order_index)
    result = await db.execute(stmt)
    rows = result.all()
    return [_to_response(t, slot) for t, slot in rows]


async def get_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    slot_id: UUID,
) -> Optional[TimetableSlotResponse]:
    result = await db.execute(
        select(Timetable, TimeSlot).join(TimeSlot, Timetable.slot_id == TimeSlot.id).where(
            Timetable.id == slot_id,
            Timetable.tenant_id == tenant_id,
        )
    )
    row = result.one_or_none()
    if not row:
        return None
    t, slot = row
    return _to_response(t, slot)


async def update_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    slot_id: UUID,
    payload: TimetableSlotUpdate,
) -> Optional[TimetableSlotResponse]:
    result = await db.execute(
        select(Timetable).where(
            Timetable.id == slot_id,
            Timetable.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    if payload.teacher_id is not None:
        obj.teacher_id = payload.teacher_id
    if payload.slot_id is not None:
        time_slot = await db.get(TimeSlot, payload.slot_id)
        if not time_slot or time_slot.tenant_id != tenant_id or not time_slot.is_active:
            raise ServiceError("Invalid time slot", status.HTTP_400_BAD_REQUEST)
        obj.slot_id = payload.slot_id
    await db.commit()
    await db.refresh(obj)
    # load slot for response
    slot = await db.get(TimeSlot, obj.slot_id)
    return _to_response(obj, slot)


async def delete_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    slot_id: UUID,
) -> bool:
    result = await db.execute(
        select(Timetable).where(
            Timetable.id == slot_id,
            Timetable.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True


async def has_timetable_slot_for_class_section_subject(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: UUID,
    subject_id: UUID,
) -> bool:
    result = await db.execute(
        select(Timetable.id).where(
            Timetable.tenant_id == tenant_id,
            Timetable.academic_year_id == academic_year_id,
            Timetable.class_id == class_id,
            Timetable.section_id == section_id,
            Timetable.subject_id == subject_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
